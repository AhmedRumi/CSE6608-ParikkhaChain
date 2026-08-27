// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "./RBAC.sol";
import "./ExamLifecycle.sol";
import "./Hashregistry.sol";

/**
 * @title ResultAudit — Separate-Scripts Anonymous Marking & Scrutiny
 * @notice Each exam has an admin-defined number of marking sections
 *         (1..10); every section is a DIFFERENT physical answer script,
 *         each evaluated by a different examiner. Every script in
 *         HashRegistry belongs to exactly ONE section (numbered 1, 2, 3, ...)
 *         and holds that section's marks only. A course result = the SUM of
 *         the scripts belonging to the same student + exam, combined on the
 *         fly. Section totals come from ExamLifecycle.getSectionTotal().
 *
 * ANONYMITY MODEL
 *   • All marking state that links a script to a person (examiner addresses,
 *     scrutinizer address, audit trail) is PRIVATE.
 *   • Events carry NO addresses — only scriptId + section + marks. The
 *     section is the script's own section (a script is never mixed).
 *   • Identity-revealing getters are admin-only.
 *   • Examiner can read only their own section's scripts via
 *     getExamSectionScripts() / getMySectionMarks().
 *
 * SCRUTINY FLOW (per script — each script is one section)
 *   1. Scrutinizer returns suggested marks + comment for a script
 *      → UNDER_SCRUTINY (only that script's section examiner is involved).
 *   2. The corresponding examiner revises their script's marks
 *      → SCRUTINIZED.
 *   3. The SAME scrutinizer rechecks → approve (APPROVED) or reject (new round).
 *   4. Final marks are ALWAYS computed on the fly: Script A + Script B.
 */
contract ResultAudit {
    RBAC public rbacContract;
    ExamLifecycle public examContract;
    HashRegistry public hashContract;

    // Sections are numbered 1..getSectionCount(examId); each section is a
    // separate script with its own marks out of getSectionTotal(examId, s).

    enum GradeStatus {
        NOT_SUBMITTED,   // 0  — no section script marked yet
        SUBMITTED,       // 1  — at least one script marked, nothing pending
        UNDER_SCRUTINY,  // 2  — a script returned to its examiner (awaiting response)
        SCRUTINIZED,     // 3  — a script revised (awaiting scrutinizer recheck)
        APPROVED,        // 4  — both scripts approved after scrutiny
        FINALIZED        // 5  — locked by admin
    }

    // Script marking state: FINALIZED (5) is stamped by the admin on finalize.
    enum SectionStatus {
        NOT_SUBMITTED,   // 0
        SUBMITTED,       // 1  — marks in
        UNDER_SCRUTINY,  // 2  — returned to the section examiner
        SCRUTINIZED,     // 3  — examiner revised, awaiting recheck
        APPROVED,        // 4  — scrutinizer approved after recheck
        FINALIZED        // 5  — locked by admin
    }

    // Per-script marking record (each script = one section, out of that
    // section's total — admin-defined per exam in ExamLifecycle).
    struct MarksRecord {
        uint64 examId;
        uint64 submittedAt;
        uint32 marks;
        SectionStatus status;
        bool exists;
    }

    // Per-script scrutiny state — the scrutinizer returns a script's marks
    // with a comment to THAT section's examiner only; the same scrutinizer
    // rechecks and approves. Identity stored here is PRIVATE (admin audit).
    struct ScrutinyRecord {
        bool    pending;        // out for review (awaiting examiner or recheck)
        bool    approved;       // scrutinizer approved after recheck
        uint256 suggestedMarks; // marks the scrutinizer suggested
        string  comment;        // latest comment from scrutinizer
        address scrutinizer;    // scrutinizer who returned the script
        uint256 returnedAt;
        uint256 responseMarks;  // examiner's revised marks
        address respondedBy;    // PRIVATE — only visible via admin audit trail
        uint256 respondedAt;
        uint256 round;          // how many times the script was returned
    }

    struct AuditEntry {
        uint32  oldMarks;
        uint32  newMarks;
        uint64  timestamp;
        address changedBy;      // PRIVATE — admin-only audit
        string  reason;
        string  changeType;     // "EXAMINER_S1" | "EXAMINER_S2" | ...
                                // | "SCRUTINY_RETURN_S1" | "SCRUTINY_RESPONSE_S1"
                                // | "SCRUTINY_APPROVE_S1" | "SCRUTINY_REJECT_S1"
                                // | "RESCRUTINY_S1" (suffix = section number)
    }

    // ─── PRIVATE storage (anonymity core) ─────────────────────────────────
    mapping(string => MarksRecord)          private marks;
    mapping(string => ScrutinyRecord)       private scrutinyData;
    mapping(string => AuditEntry[])         private auditTrail;
    mapping(uint256 => string[])            private examResults;

    // Public, non-identifying state
    mapping(uint256 => bool) public examFinalized;

    constructor(
        address rbacAddress,
        address examAddress,
        address hashAddress
    ) {
        rbacContract = RBAC(rbacAddress);
        examContract = ExamLifecycle(examAddress);
        hashContract = HashRegistry(hashAddress);
    }

    // ─── Events (address-free — never leak identities) ────────────────────
    //
    // "Notifications" for the demo: examiners watch SectionMarksSubmitted /
    // ScriptReturnedForScrutiny / ScrutinyResponse for their own scripts;
    // scrutinizers watch the same events for the scripts of their exams.
    // `section` is always the script's own section (each script = one section).

    event SectionMarksSubmitted(
        string indexed scriptId,
        uint256 indexed examId,
        uint8 section,
        uint256 marksValue
    );
    event ScriptReturnedForScrutiny(
        string indexed scriptId,
        uint8 section,
        uint256 suggestedMarks,
        string comment
    );
    event ScrutinyResponse(
        string indexed scriptId,
        uint8 section,
        uint256 oldMarks,
        uint256 newMarks
    );
    event ScrutinyApproved(
        string indexed scriptId,
        uint8 section
    );
    event ScrutinyRejected(
        string indexed scriptId,
        uint8 section,
        string comment
    );
    event MarksUpdatedAfterRescrutiny(
        string indexed scriptId,
        uint256 indexed examId,
        uint8 section,
        uint256 oldMarks,
        uint256 newMarks
    );
    event ResultFinalized(uint256 indexed examId, uint256 totalScripts);

    // ─── Modifiers ────────────────────────────────────────────────────────

    modifier onlyAdmin() {
        require(
            rbacContract.hasRole(msg.sender, RBAC.Role.ADMIN),
            "Admin only"
        );
        _;
    }

    modifier onlyAssignedScrutinizer(string memory scriptId) {
        uint256 examId = hashContract.getExamId(scriptId);
        require(
            rbacContract.isAssignedScrutinizer(msg.sender, examId),
            "Not scrut for exam"
        );
        _;
    }

    modifier onlyAdminOrSelf(address student) {
        require(
            rbacContract.hasRole(msg.sender, RBAC.Role.ADMIN) ||
            msg.sender == student,
            "Admin or self only"
        );
        _;
    }

    modifier examNotFinalized(uint256 examId) {
        require(!examFinalized[examId], "Already finalized");
        _;
    }

    modifier scriptExists(string memory scriptId) {
        require(
            hashContract.scriptExistsPublic(scriptId),
            "Script does not exist"
        );
        _;
    }

    // ─── Internal helpers ─────────────────────────────────────────────────

    // Single audit-trail writer (used by every marking path — kept out of
    // line to save deployed bytecode; 6 call sites).
    function _pushAudit(
        string memory scriptId,
        uint32 oldMarks,
        uint32 newMarks,
        string memory reason,
        string memory changeType
    ) internal {
        auditTrail[scriptId].push(AuditEntry({
            oldMarks:   oldMarks,
            newMarks:   newMarks,
            timestamp:  uint64(block.timestamp),
            changedBy:  msg.sender,
            reason:     reason,
            changeType: changeType
        }));
    }

    function _scriptSection(string memory scriptId)
        internal
        view
        returns (uint8)
    {
        return hashContract.getScriptSection(scriptId);
    }

    function _sectionTotal(uint256 examId, uint8 section)
        public
        view
        returns (uint256)
    {
        // Same-deployment ExamLifecycle always exposes getSectionTotal
        return examContract.getSectionTotal(examId, section);
    }

    // NOTE: The helpers below are `public` (external call), not `internal`,
    // because getFullTranscript's loops already sit at the legacy codegen
    // stack limit — inlined internals would push it over 16 slots.

    // Exam total = SUM of all section totals (dynamic section count).
    function _examTotal(uint256 examId) public view returns (uint256) {
        uint8 count = examContract.getSectionCount(examId);
        uint256 total = 0;
        for (uint8 s = 1; s <= count; s++) {
            total += examContract.getSectionTotal(examId, s);
        }
        return total;
    }

    // Audit-trail suffix for a script's section: "_S1", "_S2", ...
    function _changeTypePrefix(uint8 section) internal pure returns (string memory) {
        return string(abi.encodePacked("_S", _uint8ToString(section)));
    }

    // Section numbers are 1..10 — single- or double-digit conversion.
    function _uint8ToString(uint8 value) internal pure returns (string memory) {
        if (value >= 10) return "10";
        bytes memory b = new bytes(1);
        b[0] = bytes1(uint8(48 + value));
        return string(b);
    }

    // Marking status of a script (NOT_SUBMITTED when no marks record exists).
    function _scriptStatus(string memory scriptId)
        public
        view
        returns (SectionStatus)
    {
        return marks[scriptId].exists ? marks[scriptId].status
                                      : SectionStatus.NOT_SUBMITTED;
    }

    // Find the caller-provided student's script of a given section + exam.
    // Returns "" when the student has no such script. Public (non-inlined)
    // so getFullTranscript's loop stays under the EVM stack limit.
    function _findScript(
        string[] memory own,
        uint256 examId,
        uint8 section
    ) public view returns (string memory) {
        for (uint256 i = 0; i < own.length; i++) {
            if (
                hashContract.getExamId(own[i]) == examId &&
                hashContract.getScriptSection(own[i]) == section
            ) {
                return own[i];
            }
        }
        return "";
    }

    // Aggregate course GradeStatus from the scripts' statuses (all scripts of
    // ONE exam — dynamic section count). Empty input → NOT_SUBMITTED.
    function _deriveGrade(SectionStatus[] memory sts)
        public
        pure
        returns (GradeStatus)
    {
        if (sts.length == 0) return GradeStatus.NOT_SUBMITTED;
        bool allFinalized    = true;
        bool allApproved     = true;
        bool allNotSubmitted = true;
        for (uint256 i = 0; i < sts.length; i++) {
            if (sts[i] == SectionStatus.UNDER_SCRUTINY)
                return GradeStatus.UNDER_SCRUTINY;
            if (sts[i] == SectionStatus.SCRUTINIZED)
                return GradeStatus.SCRUTINIZED;
            if (sts[i] != SectionStatus.FINALIZED) allFinalized = false;
            if (sts[i] != SectionStatus.APPROVED)  allApproved = false;
            if (sts[i] != SectionStatus.NOT_SUBMITTED) allNotSubmitted = false;
        }
        if (allFinalized)    return GradeStatus.FINALIZED;
        if (allApproved)     return GradeStatus.APPROVED;
        if (allNotSubmitted) return GradeStatus.NOT_SUBMITTED;
        return GradeStatus.SUBMITTED;
    }

    // True if a script was returned for scrutiny at least once.
    function _hasScrutiny(string memory sid) public view returns (bool) {
        return scrutinyData[sid].round > 0;
    }

    // All exams the student has scripts for must be COMPLETED (or FINALIZED)
    // before the student may read their results (admin can always view).
    // Public (non-inlined) so getFullTranscript's loop stays under the EVM
    // stack limit.
    function _examsCompleted(address student) public view returns (bool) {
        string[] memory sids = hashContract.getStudentScripts(student);
        for (uint256 i = 0; i < sids.length; i++) {
            uint256 eid = hashContract.getExamId(sids[i]);
            ExamLifecycle.ExamState st = examContract.getExamState(eid);
            if (
                st != ExamLifecycle.ExamState.COMPLETED &&
                st != ExamLifecycle.ExamState.FINALIZED
            ) {
                return false;
            }
        }
        return true;
    }

    // Number of the student's REGISTERED courses whose marks are recorded but
    // not yet approved. A student cannot see any result until this reaches
    // zero (all registered courses approved). Courses without a marks record
    // (either section script unmarked) are not counted.
    function _pendingCourses(address student) internal view returns (uint256) {
        string[] memory sids = hashContract.getStudentScripts(student);
        uint256[] memory pendingExamIds = new uint256[](sids.length);
        uint256 count = 0;
        for (uint256 i = 0; i < sids.length; i++) {
            MarksRecord storage rec = marks[sids[i]];
            if (!rec.exists) continue;
            if (
                rec.status == SectionStatus.APPROVED ||
                rec.status == SectionStatus.FINALIZED
            ) continue;
            bool dup = false;
            for (uint256 j = 0; j < count; j++) {
                if (pendingExamIds[j] == rec.examId) { dup = true; break; }
            }
            if (!dup) pendingExamIds[count++] = rec.examId;
        }
        return count;
    }

    // ─── Core marking functions ───────────────────────────────────────────

    /**
     * @notice Marks submission for a script. The script's section number
     *         decides who may mark it: only the examiner assigned to that
     *         section (RBAC — the other examiners are never revealed).
     */
    function submitMarks(
        string memory scriptId,
        uint256 marksValue
    ) public scriptExists(scriptId) {

        uint256 examId = hashContract.getExamId(scriptId);
        uint8 section = _scriptSection(scriptId);
        require(
            rbacContract.isAssignedExaminer(msg.sender, examId),
            "Not examiner for exam"
        );
        require(
            rbacContract.getExaminerSection(msg.sender, examId) == section,
            "Not your section"
        );

        ExamLifecycle.ExamState examState = examContract.getExamState(examId);
        require(
            examState == ExamLifecycle.ExamState.EVALUATION ||
            examState == ExamLifecycle.ExamState.SCRUTINY,
            "Exam not in marking state"
        );
        require(marksValue <= _sectionTotal(examId, section), "Marks exceed total");

        MarksRecord storage rec = marks[scriptId];
        require(
            rec.status == SectionStatus.NOT_SUBMITTED,
            "Already marked"
        );

        if (!rec.exists) {
            rec.exists = true;
            rec.examId  = uint64(examId);
            examResults[examId].push(scriptId);
        }

        rec.marks       = uint32(marksValue);
        rec.submittedAt = uint64(block.timestamp);
        rec.status      = SectionStatus.SUBMITTED;

        _pushAudit(
            scriptId,
            0,
            uint32(marksValue),
            "Initial marks",
            string(abi.encodePacked("EXAMINER", _changeTypePrefix(section)))
        );

        emit SectionMarksSubmitted(scriptId, examId, section, marksValue);
    }

    // ─── Scrutiny workflow (per script = per section) ─────────────────────
    //
    // Real-life flow (for EACH section script independently):
    //   1. Scrutinizer REVIEWS marks → RETURNS suggested marks + comment for
    //      that script to ITS section examiner only (marks NOT changed here).
    //   2. The corresponding examiner VERIFIES and updates their script's
    //      marks (revised marks stored).
    //   3. The SAME scrutinizer RECHECKS the revised marks and approves.
    //   4. Admin finalizes — blocked while any script is still pending.
//   Final marks are automatically the SUM of the student's scripts for the
//   exam (sections are independent) — see getFullTranscript().

    /**
     * @notice Scrutinizer returns a SCRIPT to its section examiner with
     *         suggested marks and a comment. Marks are NOT changed here.
     *         Status: SUBMITTED/SCRUTINIZED → UNDER_SCRUTINY.
     */
    function returnScriptForScrutiny(
        string memory scriptId,
        uint256 suggestedMarks,
        string memory comment
    ) public onlyAssignedScrutinizer(scriptId) scriptExists(scriptId) {

        MarksRecord storage rec = marks[scriptId];
        require(rec.exists, "No marks yet");
        require(
            rec.status == SectionStatus.SUBMITTED ||
            rec.status == SectionStatus.SCRUTINIZED,
            "Not reviewable"
        );

        uint8 section = _scriptSection(scriptId);
        require(suggestedMarks <= _sectionTotal(rec.examId, section), "Sug. marks exceed total");
        require(bytes(comment).length > 0, "Comment required");

        uint256 examId = rec.examId;
        ExamLifecycle.ExamState examState = examContract.getExamState(examId);
        require(
            examState == ExamLifecycle.ExamState.SCRUTINY,
            "Not scrutiny state"
        );

        ScrutinyRecord storage sc = scrutinyData[scriptId];
        sc.pending        = true;
        sc.approved       = false;
        sc.suggestedMarks = suggestedMarks;
        sc.comment        = comment;
        sc.scrutinizer    = msg.sender;
        sc.returnedAt     = block.timestamp;
        sc.round += 1;

        uint256 oldMarks = rec.marks;
        rec.status = SectionStatus.UNDER_SCRUTINY;

        _pushAudit(
            scriptId,
            uint32(oldMarks),
            uint32(suggestedMarks),
            comment,
            string(abi.encodePacked("SCRUTINY_RETURN", _changeTypePrefix(section)))
        );

        emit ScriptReturnedForScrutiny(
            scriptId, section, suggestedMarks, comment
        );
    }

    /**
     * @notice The examiner assigned to this SCRIPT responds to the scrutiny
     *         by revising their script's marks after verifying the comment.
     *         Marks ARE updated here. Status: UNDER_SCRUTINY → SCRUTINIZED.
     */
    function respondToScrutiny(
        string memory scriptId,
        uint256 revisedMarks,
        string memory note
    ) public scriptExists(scriptId) {

        MarksRecord storage rec = marks[scriptId];
        require(rec.exists, "No marks yet");
        require(
            rec.status == SectionStatus.UNDER_SCRUTINY,
            "No pending scrutiny"
        );

        uint256 examId = rec.examId;
        uint8 section = _scriptSection(scriptId);
        require(
            rbacContract.isAssignedExaminer(msg.sender, examId),
            "Not examiner for exam"
        );
        // ONLY the examiner of this script's section may respond — the other
        // examiner is never notified and cannot interfere.
        require(
            rbacContract.getExaminerSection(msg.sender, examId) == section,
            "Not your section"
        );
        require(revisedMarks <= _sectionTotal(rec.examId, section), "Revised marks exceed total");

        ExamLifecycle.ExamState examState = examContract.getExamState(examId);
        require(
            examState == ExamLifecycle.ExamState.SCRUTINY,
            "Not scrutiny state"
        );

        uint256 oldMarks = rec.marks;
        rec.marks   = uint32(revisedMarks);
        rec.status  = SectionStatus.SCRUTINIZED;

        ScrutinyRecord storage sc = scrutinyData[scriptId];
        sc.responseMarks = revisedMarks;
        sc.respondedBy   = msg.sender;
        sc.respondedAt   = block.timestamp;

        _pushAudit(
            scriptId,
            uint32(oldMarks),
            uint32(revisedMarks),
            bytes(note).length > 0 ? note : "Scrutiny response",
            string(abi.encodePacked("SCRUTINY_RESPONSE", _changeTypePrefix(section)))
        );

        emit ScrutinyResponse(scriptId, section, oldMarks, revisedMarks);
    }

    /**
     * @notice The assigned scrutinizer approves a script's marks. Two paths:
     *         - SUBMITTED  → APPROVED: the scrutinizer reviewed the submitted
     *           marks and is satisfied (direct approval, marks unchanged).
     *         - SCRUTINIZED → APPROVED: recheck of the examiner's response to
     *           a returned script (only the scrutinizer who returned it).
     */
    function approveScrutiny(string memory scriptId)
        public
        onlyAssignedScrutinizer(scriptId)
        scriptExists(scriptId)
    {
        MarksRecord storage rec = marks[scriptId];
        require(rec.exists, "No marks yet");
        require(
            rec.status == SectionStatus.SUBMITTED ||
            rec.status == SectionStatus.SCRUTINIZED,
            "Not reviewable"
        );

        bool directApprove = (rec.status == SectionStatus.SUBMITTED);
        if (!directApprove) {
            ScrutinyRecord storage sc = scrutinyData[scriptId];
            require(
                sc.scrutinizer == msg.sender,
                "Not your script to recheck"
            );
            sc.pending  = false;
            sc.approved = true;
        }

        uint8 section = _scriptSection(scriptId);
        uint256 examId = rec.examId;
        ExamLifecycle.ExamState examState = examContract.getExamState(examId);
        require(
            examState == ExamLifecycle.ExamState.SCRUTINY,
            "Not scrutiny state"
        );

        rec.status = SectionStatus.APPROVED;

        _pushAudit(
            scriptId,
            uint32(rec.marks),
            uint32(rec.marks),
            directApprove
                ? "Approved submitted"
                : "Approved revised",
            string(abi.encodePacked("SCRUTINY_APPROVE", _changeTypePrefix(section)))
        );

        emit ScrutinyApproved(scriptId, section);
    }

    /**
     * @notice If the recheck is not satisfied, the scrutinizer can reject the
     *         revision and send the script back to its examiner again.
     *         Status: SCRUTINIZED → UNDER_SCRUTINY (new round).
     */
    function rejectScrutiny(
        string memory scriptId,
        string memory comment
    ) public onlyAssignedScrutinizer(scriptId) scriptExists(scriptId) {

        MarksRecord storage rec = marks[scriptId];
        require(rec.exists, "No marks yet");
        require(
            rec.status == SectionStatus.SCRUTINIZED,
            "Not awaiting recheck"
        );
        require(bytes(comment).length > 0, "Comment required");

        ScrutinyRecord storage sc = scrutinyData[scriptId];
        require(
            sc.scrutinizer == msg.sender,
            "Not your recheck"
        );

        uint8 section = _scriptSection(scriptId);
        uint256 examId = rec.examId;
        ExamLifecycle.ExamState examState = examContract.getExamState(examId);
        require(
            examState == ExamLifecycle.ExamState.SCRUTINY,
            "Not scrutiny state"
        );

        sc.comment  = comment;
        sc.pending  = true;
        sc.approved = false;
        sc.round += 1;

        rec.status = SectionStatus.UNDER_SCRUTINY;

        _pushAudit(
            scriptId,
            uint32(rec.marks),
            uint32(rec.marks),
            comment,
            string(abi.encodePacked("SCRUTINY_REJECT", _changeTypePrefix(section)))
        );

        emit ScrutinyRejected(scriptId, section, comment);
    }

    /**
     * @notice Finalize exam results. Every marked script of the exam must
     *         either be untouched (SUBMITTED) or scrutinized AND approved
     *         (APPROVED) — nothing may still be pending scrutiny review.
     *         Final marks are computed on the fly from the section scripts.
     */
    function finalizeExamResults(uint256 examId)
        public
        onlyAdmin
        examNotFinalized(examId)
    {
        ExamLifecycle.ExamState examState = examContract.getExamState(examId);
        require(
            examState == ExamLifecycle.ExamState.EVALUATION ||
            examState == ExamLifecycle.ExamState.SCRUTINY  ||
            examState == ExamLifecycle.ExamState.COMPLETED,
            "Not ready to finalize"
        );

        string[] memory scriptIds = examResults[examId];
        require(scriptIds.length > 0, "No results to finalize");

        for (uint256 i = 0; i < scriptIds.length; i++) {
            if (!marks[scriptIds[i]].exists) continue;
            SectionStatus st = marks[scriptIds[i]].status;
            require(
                st == SectionStatus.SUBMITTED || st == SectionStatus.APPROVED,
                "Script still pending review"
            );
        }

        for (uint256 i = 0; i < scriptIds.length; i++) {
            if (marks[scriptIds[i]].exists) {
                marks[scriptIds[i]].status = SectionStatus.FINALIZED;
            }
        }

        examFinalized[examId] = true;
        emit ResultFinalized(examId, scriptIds.length);
    }

    // ─── Rescrutiny integration ───────────────────────────────────────────

    // Whether a marks record exists for a script (used by Rescrutiny to
    // ensure students only apply for scripts that have been evaluated).
    function hasMarks(string memory scriptId)
        public
        view
        scriptExists(scriptId)
        returns (bool)
    {
        return marks[scriptId].exists;
    }

    // Current marks value of a script (0 when not marked). Used by Rescrutiny
    // to report the final marks of directly-approved applications.
    function getMarksValue(string memory scriptId)
        public
        view
        scriptExists(scriptId)
        returns (uint256)
    {
        return marks[scriptId].marks;
    }

    /**
     * @notice Write a script's REVISED marks after a rescrutiny approval.
     *         Only the whitelisted Rescrutiny contract may call this — the
     *         examiner's revision is applied by Rescrutiny, never directly.
     *         Blocked once the script's marks are FINALIZED.
     */
    function updateMarksAfterRescrutiny(
        string memory scriptId,
        uint256 newMarks
    ) public scriptExists(scriptId) {
        require(
            rbacContract.isTrustedRescrutiny(msg.sender),
            "Rescrutiny only"
        );
        MarksRecord storage rec = marks[scriptId];
        require(rec.exists, "No marks yet");
        require(
            rec.status != SectionStatus.FINALIZED,
            "Already finalized"
        );
        uint8 section = _scriptSection(scriptId);
        require(
            newMarks <= _sectionTotal(rec.examId, section),
            "Revised marks exceed total"
        );

        uint256 oldMarks = rec.marks;
        rec.marks       = uint32(newMarks);
        rec.submittedAt = uint64(block.timestamp);

        _pushAudit(
            scriptId,
            uint32(oldMarks),
            uint32(newMarks),
            "Updated after rescrutiny",
            string(abi.encodePacked("RESCRUTINY", _changeTypePrefix(section)))
        );

        emit MarksUpdatedAfterRescrutiny(
            scriptId, rec.examId, section, oldMarks, newMarks
        );
    }

    // ─── Result view functions ────────────────────────────────────────────

    /**
     * @notice Get marks for ONE script — its own section's marks out of that
     *         section's total (anonymous, no identity). Callable by anyone
     *         who knows the script ID. The course total is the sum across the
     *         student's two scripts — see getFullTranscript().
     */
    function getMarks(string memory scriptId)
        public
        view
        scriptExists(scriptId)
        returns (
            uint256 marksValue,
            uint256 sectionTotal,
            uint8 status
        )
    {
        MarksRecord storage record = marks[scriptId];
        uint256 examId = hashContract.getExamId(scriptId);
        uint8 section = _scriptSection(scriptId);
        if (!record.exists) return (0, _sectionTotal(examId, section), uint8(SectionStatus.NOT_SUBMITTED));
        return (
            record.marks,
            _sectionTotal(record.examId, section),
            uint8(record.status)
        );
    }

    /**
     * @notice Examiner's OWN script view — only scripts of the caller's
     *         assigned section are readable; anything else reverts.
     */
    function getMySectionMarks(string memory scriptId)
        public
        view
        scriptExists(scriptId)
        returns (
            uint8 section,
            uint256 marksValue,
            uint8 status
        )
    {
        uint256 examId = hashContract.getExamId(scriptId);
        require(
            rbacContract.isAssignedExaminer(msg.sender, examId),
            "Not examiner for exam"
        );
        uint8 mySection = rbacContract.getExaminerSection(msg.sender, examId);
        require(mySection != 0, "No section for this exam");
        require(
            _scriptSection(scriptId) == mySection,
            "Not your script"
        );

        MarksRecord storage rec = marks[scriptId];
        return (mySection, rec.marks, uint8(rec.status));
    }

    /**
     * @notice Single-script progress — ADMIN ONLY (section comes from the
     *         script itself).
     */
    function getSectionProgress(string memory scriptId)
        public
        view
        onlyAdmin
        scriptExists(scriptId)
        returns (
            bool    submitted,
            uint256 marksValue,
            uint8   status,
            uint8   section
        )
    {
        MarksRecord storage rec = marks[scriptId];
        return (
            rec.status != SectionStatus.NOT_SUBMITTED,
            rec.marks,
            uint8(rec.status),
            _scriptSection(scriptId)
        );
    }

    /**
     * @notice Get result for a specific student in a specific exam — the
     *         student's scripts for that exam (one per section the student
     *         submitted), with each script's marks. The course total is the
     *         SUM of the section totals. Callable by the student or admin.
     */
    function getStudentExamResult(uint256 examId, address student)
        public
        view
        onlyAdminOrSelf(student)
        returns (
            string[] memory scripts,
            uint256[] memory marksObtained,
            uint256 totalMarks,
            uint256 marksTotal,
            GradeStatus status
        )
    {
        require(
            rbacContract.hasRole(student, RBAC.Role.STUDENT),
            "Not a registered student"
        );

        string[] memory own = hashContract.getStudentScripts(student);
        require(own.length > 0, "No scripts for student");

        if (msg.sender == student) {
            require(
                _pendingCourses(student) == 0,
                "Results pending"
            );
            ExamLifecycle.ExamState st = examContract.getExamState(examId);
            require(
                st == ExamLifecycle.ExamState.COMPLETED ||
                st == ExamLifecycle.ExamState.FINALIZED,
                "Results locked"
            );
        }

        // Gather this exam's scripts of the student, in section order
        uint8 secCount = examContract.getSectionCount(examId);
        string[] memory all = new string[](secCount);
        uint256 n = 0;
        for (uint8 s = 1; s <= secCount; s++) {
            string memory sid = _findScript(own, examId, s);
            if (bytes(sid).length > 0) { all[n] = sid; n++; }
        }
        require(n > 0, "No result in this exam");

        uint256 examTotal = _examTotal(examId);

        scripts = new string[](n);
        marksObtained = new uint256[](n);
        SectionStatus[] memory sts = new SectionStatus[](n);
        totalMarks = 0;
        for (uint256 i = 0; i < n; i++) {
            scripts[i] = all[i];
            marksObtained[i] = marks[all[i]].marks;
            totalMarks += marks[all[i]].marks;
            sts[i] = _scriptStatus(all[i]);
        }

        return (
            scripts,
            marksObtained,
            totalMarks,
            examTotal,
            _deriveGrade(sts)
        );
    }

    /**
     * @notice Get ALL results for a student — ONE ROW PER COURSE. For each
     *         exam the student's scripts (one per section submitted) and
     *         their marks are returned as a nested list. Callable by the
     *         student OR admin.
     */
    function getFullTranscript(address student)
        public
        view
        onlyAdminOrSelf(student)
        returns (
            uint256[]   memory examIds,
            string[][]  memory scripts,
            uint256[][] memory marksObtained,
            uint256[]   memory totalMarks,
            GradeStatus[] memory statuses,
            bool[]      memory hasScrutiny
        )
    {
        require(
            rbacContract.hasRole(student, RBAC.Role.STUDENT),
            "Not a registered student"
        );

        string[] memory own = hashContract.getStudentScripts(student);
        uint256 n = own.length;
        require(n > 0, "No scripts for student");

        if (msg.sender == student) {
            require(
                _pendingCourses(student) == 0,
                "Results pending"
            );
            require(
                _examsCompleted(student),
                "Results locked"
            );
        }

        // Distinct exams the student has scripts for (one row per course)
        uint256[] memory uniq = new uint256[](n);
        uint256 m = 0;
        for (uint256 i = 0; i < n; i++) {
            uint256 eid = hashContract.getExamId(own[i]);
            bool dup = false;
            for (uint256 j = 0; j < m; j++) {
                if (uniq[j] == eid) { dup = true; break; }
            }
            if (!dup) uniq[m++] = eid;
        }

        // Allocate return arrays
        examIds       = new uint256[](m);
        scripts       = new string[][](m);
        marksObtained = new uint256[][](m);
        totalMarks    = new uint256[](m);
        statuses      = new GradeStatus[](m);
        hasScrutiny   = new bool[](m);

        // Build per-exam script rows (two passes keep the legacy stack OK)
        for (uint256 i = 0; i < m; i++) {
            uint256 eid = uniq[i];
            (string[] memory rowScripts, uint256[] memory rowMarks) =
                _examRowScripts(own, eid);
            scripts[i]       = rowScripts;
            marksObtained[i] = rowMarks;
        }
        for (uint256 i = 0; i < m; i++) {
            uint256 eid = uniq[i];
            examIds[i]    = eid;
            totalMarks[i] = _examTotal(eid);
            (,, GradeStatus st, bool hasScr) = _examRow(own, eid);
            statuses[i]    = st;
            hasScrutiny[i] = hasScr;
        }

        return (examIds, scripts, marksObtained, totalMarks,
                statuses, hasScrutiny);
    }

    // One student's transcript row for a single exam: all metadata —
    // scripts in section order, their marks, the derived grade, and whether
    // any script was returned for scrutiny. Public (not inlined) so
    // getFullTranscript's loops stay under the legacy codegen stack limit.
    function _examRow(string[] memory own, uint256 eid)
        public
        view
        returns (
            string[] memory rowScripts,
            uint256[] memory rowMarks,
            GradeStatus status,
            bool hasScrutiny
        )
    {
        (rowScripts, rowMarks) = _examRowScripts(own, eid);
        SectionStatus[] memory sts = new SectionStatus[](rowScripts.length);
        for (uint256 j = 0; j < rowScripts.length; j++) {
            sts[j] = _scriptStatus(rowScripts[j]);
            if (_hasScrutiny(rowScripts[j])) hasScrutiny = true;
        }
        return (rowScripts, rowMarks, _deriveGrade(sts), hasScrutiny);
    }

    // Per-exam script list + marks of a student, in section order.
    function _examRowScripts(string[] memory own, uint256 eid)
        public
        view
        returns (string[] memory rowScripts, uint256[] memory rowMarks)
    {
        uint8 secCount = examContract.getSectionCount(eid);
        uint256 k = 0;
        for (uint8 s = 1; s <= secCount; s++) {
            if (bytes(_findScript(own, eid, s)).length > 0) k++;
        }

        rowScripts = new string[](k);
        rowMarks = new uint256[](k);
        uint256 j = 0;
        for (uint8 s = 1; s <= secCount; s++) {
            string memory sid = _findScript(own, eid, s);
            if (bytes(sid).length == 0) continue;
            rowScripts[j] = sid;
            rowMarks[j] = marks[sid].marks;
            j++;
        }
    }

    /**
     * @notice Get the audit trail for a script.
     *         Admin only — reveals who marked and changed marks.
     */
    function getAuditTrail(string memory scriptId)
        public
        view
        onlyAdmin
        scriptExists(scriptId)
        returns (AuditEntry[] memory)
    {
        return auditTrail[scriptId];
    }

    /**
     * @notice Get all script IDs for an exam (both sections; admin only).
     */
    function getExamResults(uint256 examId)
        public
        view
        onlyAdmin
        returns (string[] memory)
    {
        return examResults[examId];
    }

    function isExamFinalized(uint256 examId) public view returns (bool) {
        return examFinalized[examId];
    }

    function getExamResultCount(uint256 examId) public view returns (uint256) {
        return examResults[examId].length;
    }
}
