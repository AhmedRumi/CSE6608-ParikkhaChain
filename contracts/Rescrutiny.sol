// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "./RBAC.sol";
import "./ExamLifecycle.sol";
import "./Hashregistry.sol";
import "./ResultAudit.sol";

/**
 * @title Rescrutiny — Post-Completion Re-Evaluation (per section)
 * @notice After an exam reaches COMPLETED, students may apply for a
 *         rescrutiny of ONE section of a course — each section is an
 *         independent application (its own script). Sections are numbered
 *         per exam: 1, 2, 3, ... up to getSectionCount(examId).
 *
 * FLOW
 *   APPLIED   → scrutinizer finds NO issue        → APPROVED (directly,
 *                 marks unchanged)
 *   APPLIED   → scrutinizer finds an issue        → RETURNED to THAT
 *                 section's examiner with suggested marks + comment
 *   RETURNED  → examiner verifies and revises     → REVISED (marks NOT yet
 *                 written)
 *   REVISED   → scrutinizer rechecks and approves → APPROVED → marks are
 *                 written to ResultAudit
 *
 * ANONYMITY
 *   • Events carry NO addresses (scriptId + examId + section only).
 *   • getExamApplications() (scrutinizer/admin) never reveals the student.
 *   • getStudentApplications() reveals identity — student/admin only.
 *
 * WINDOW
 *   Students may apply only while the exam is COMPLETED. The admin closes the
 *   window by moving the exam COMPLETED → FINALIZED (no more applications).
 */
contract Rescrutiny {
    RBAC public rbacContract;
    ExamLifecycle public examContract;
    HashRegistry public hashContract;
    ResultAudit public resultContract;

    // Sections are numbered 1..getSectionCount(examId); each section is an
    // independent rescrutiny application.

    enum RescrutinyStatus {
        APPLIED,   // 0 — submitted by the student; scrutinizer may act
        RETURNED,  // 1 — scrutinizer found an issue; sent to section examiner
        REVISED,   // 2 — examiner responded with revised marks; awaiting recheck
        APPROVED   // 3 — approved (directly or after revision)
    }

    struct Application {
        uint256 examId;
        uint8 section;
        address student;        // PRIVATE — never revealed to scrutinizer
        string scriptId;
        string reason;
        uint256 appliedAt;
        RescrutinyStatus status;
        bool marksUpdated;      // true if ResultAudit marks were changed
        // scrutinizer side
        uint256 suggestedMarks; // marks the scrutinizer suggested (RETURNED)
        string comment;         // latest comment
        uint256 reviewedAt;
        // examiner side
        uint256 revisedMarks;   // examiner's revised marks (REVISED)
        string examinerNote;
        uint256 respondedAt;
        uint256 resolvedAt;
    }

    // scriptId => application (one per script = per section per exam)
    // NOTE: intentionally private — the auto-generated public getter for a
    // 15-field struct overflows the legacy codegen stack. All reads go
    // through the view helpers below.
    mapping(string => Application) private applications;
    mapping(uint256 => string[]) public examApplications;   // examId => scriptIds
    mapping(address => string[]) public studentApplications; // student => scriptIds

    constructor(
        address rbacAddress,
        address examAddress,
        address hashAddress,
        address resultAddress
    ) {
        rbacContract = RBAC(rbacAddress);
        examContract = ExamLifecycle(examAddress);
        hashContract = HashRegistry(hashAddress);
        resultContract = ResultAudit(resultAddress);
    }

    // ─── Events (address-free — anonymity) ────────────────────────────────

    event RescrutinyApplied(
        string indexed scriptId,
        uint256 indexed examId,
        uint8 section,
        string reason
    );
    event RescrutinyReturned(
        string indexed scriptId,
        uint256 indexed examId,
        uint8 section,
        uint256 suggestedMarks,
        string comment
    );
    event RescrutinyResponded(
        string indexed scriptId,
        uint256 indexed examId,
        uint8 section,
        uint256 revisedMarks
    );
    event RescrutinyApproved(
        string indexed scriptId,
        uint256 indexed examId,
        uint8 section,
        uint256 finalMarks
    );

    // ─── Modifiers ────────────────────────────────────────────────────────

    modifier scriptExists(string memory scriptId) {
        require(
            hashContract.scriptExistsPublic(scriptId),
            "Script does not exist"
        );
        _;
    }

    modifier onlyAdminOrSelf(address student) {
        require(
            rbacContract.hasRole(msg.sender, RBAC.Role.ADMIN) ||
            msg.sender == student,
            "Only admin or the student themselves can view this"
        );
        _;
    }

    function _requireAssignedScrutinizer(uint256 examId) internal view {
        require(
            rbacContract.isAssignedScrutinizer(msg.sender, examId),
            "Not assigned as scrutinizer for this exam"
        );
    }

    function _sectionTotal(uint256 examId, uint8 section)
        internal
        view
        returns (uint256)
    {
        try examContract.getSectionTotal(examId, section) returns (
            uint256 total
        ) {
            return total;
        } catch {
            return 0;
        }
    }

    // ─── Student application ──────────────────────────────────────────────

    /**
     * @notice A student applies for rescrutiny of ONE section of a course.
     *         The section must exist for this exam (1..getSectionCount) and
     *         the exam must be COMPLETED (the admin closes the window by
     *         setting FINALIZED).
     */
    function applyForRescrutiny(
        uint256 examId,
        uint8 section,
        string memory reason
    ) public {
        require(
            rbacContract.hasRole(msg.sender, RBAC.Role.STUDENT),
            "Not a registered student"
        );
        require(
            section >= 1 && section <= examContract.getSectionCount(examId),
            "Invalid section"
        );
        require(bytes(reason).length > 0, "Reason is required");

        ExamLifecycle.ExamState st = examContract.getExamState(examId);
        require(
            st == ExamLifecycle.ExamState.COMPLETED,
            "Rescrutiny is only open while the exam is COMPLETED"
        );

        string[] memory own = hashContract.getStudentScripts(msg.sender);
        string memory sid = "";
        for (uint256 i = 0; i < own.length; i++) {
            if (
                hashContract.getExamId(own[i]) == examId &&
                hashContract.getScriptSection(own[i]) == section
            ) {
                sid = own[i];
                break;
            }
        }
        require(
            bytes(sid).length > 0,
            "No script for this section in this exam"
        );
        require(
            bytes(applications[sid].scriptId).length == 0,
            "Already applied for rescrutiny of this section"
        );
        require(resultContract.hasMarks(sid), "No marks recorded for this script yet");

        Application storage app = applications[sid];
        app.examId       = examId;
        app.section      = section;
        app.student      = msg.sender;
        app.scriptId     = sid;
        app.reason       = reason;
        app.appliedAt    = block.timestamp;
        app.status       = RescrutinyStatus.APPLIED;

        examApplications[examId].push(sid);
        studentApplications[msg.sender].push(sid);

        emit RescrutinyApplied(sid, examId, section, reason);
    }

    // ─── Scrutinizer actions ──────────────────────────────────────────────

    /**
     * @notice Scrutinizer found NO issue — approve directly, marks unchanged.
     *         APPLIED → APPROVED.
     */
    function approveDirectly(string memory scriptId, string memory comment)
        public
        scriptExists(scriptId)
    {
        Application storage app = applications[scriptId];
        require(bytes(app.scriptId).length > 0, "No application for this script");
        require(
            app.status == RescrutinyStatus.APPLIED,
            "Not awaiting first review"
        );
        _requireAssignedScrutinizer(app.examId);

        app.status     = RescrutinyStatus.APPROVED;
        app.comment    = comment;
        app.resolvedAt = block.timestamp;

        (uint256 currentMarks, , ) = resultContract.getMarks(scriptId);
        emit RescrutinyApproved(
            scriptId, app.examId, app.section, currentMarks
        );
    }

    /**
     * @notice Scrutinizer found an issue — send the script back to THAT
     *         section's examiner with suggested marks + comment.
     *         APPLIED → RETURNED.
     */
    function returnForRescrutiny(
        string memory scriptId,
        uint256 suggestedMarks,
        string memory comment
    ) public scriptExists(scriptId) {
        Application storage app = applications[scriptId];
        require(bytes(app.scriptId).length > 0, "No application for this script");
        require(
            app.status == RescrutinyStatus.APPLIED,
            "Not awaiting first review"
        );
        _requireAssignedScrutinizer(app.examId);
        require(
            suggestedMarks <= _sectionTotal(app.examId, app.section),
            "Suggested marks exceed section total"
        );
        require(bytes(comment).length > 0, "Comment is required");

        app.status         = RescrutinyStatus.RETURNED;
        app.suggestedMarks = suggestedMarks;
        app.comment        = comment;
        app.reviewedAt     = block.timestamp;

        emit RescrutinyReturned(
            scriptId, app.examId, app.section, suggestedMarks, comment
        );
    }

    // ─── Examiner action ──────────────────────────────────────────────────

    /**
     * @notice The examiner of the script's section verifies the scrutiny
     *         comment and revises their marks. Marks are NOT written to
     *         ResultAudit yet. RETURNED → REVISED.
     */
    function respondToRescrutiny(
        string memory scriptId,
        uint256 revisedMarks,
        string memory note
    ) public scriptExists(scriptId) {
        Application storage app = applications[scriptId];
        require(bytes(app.scriptId).length > 0, "No application for this script");
        require(
            app.status == RescrutinyStatus.RETURNED,
            "No pending examiner response"
        );
        require(
            rbacContract.getExaminerSection(msg.sender, app.examId) == app.section,
            "Not the examiner of this section"
        );
        require(
            revisedMarks <= _sectionTotal(app.examId, app.section),
            "Revised marks exceed section total"
        );

        app.status        = RescrutinyStatus.REVISED;
        app.revisedMarks  = revisedMarks;
        app.examinerNote  = note;
        app.respondedAt   = block.timestamp;

        emit RescrutinyResponded(
            scriptId, app.examId, app.section, revisedMarks
        );
    }

    // ─── Scrutinizer recheck ──────────────────────────────────────────────

    /**
     * @notice Scrutinizer rechecks the examiner's revision and approves —
     *         the revised marks are now written to ResultAudit.
     *         REVISED → APPROVED.
     */
    function approveAfterRevision(string memory scriptId, string memory comment)
        public
        scriptExists(scriptId)
    {
        Application storage app = applications[scriptId];
        require(bytes(app.scriptId).length > 0, "No application for this script");
        require(
            app.status == RescrutinyStatus.REVISED,
            "No revised marks awaiting recheck"
        );
        _requireAssignedScrutinizer(app.examId);

        uint256 finalMarks = app.revisedMarks;
        resultContract.updateMarksAfterRescrutiny(scriptId, finalMarks);

        app.status       = RescrutinyStatus.APPROVED;
        app.comment      = comment;
        app.marksUpdated = true;
        app.resolvedAt   = block.timestamp;

        emit RescrutinyApproved(
            scriptId, app.examId, app.section, finalMarks
        );
    }

    // ─── View functions ───────────────────────────────────────────────────

    /**
     * @notice All applications of an exam — NO student identity (scrutinizer
     *         and admin view; reveals only script IDs, which are anonymous).
     *         Split across two getters to stay under the legacy stack limit.
     */
    function getExamApplications(uint256 examId)
        public
        view
        returns (
            string[]  memory scriptIds,
            uint8[]   memory sections,
            uint8[]   memory statuses,
            uint256[] memory suggestedMarks,
            uint256[] memory revisedMarks,
            uint256[] memory finalMarks
        )
    {
        string[] memory sids = examApplications[examId];
        uint256 n = sids.length;
        scriptIds      = new string[](n);
        sections       = new uint8[](n);
        statuses       = new uint8[](n);
        suggestedMarks = new uint256[](n);
        revisedMarks   = new uint256[](n);
        finalMarks     = new uint256[](n);
        for (uint256 i = 0; i < n; i++) {
            scriptIds[i]      = sids[i];
            sections[i]       = applications[sids[i]].section;
            statuses[i]       = uint8(applications[sids[i]].status);
            suggestedMarks[i] = applications[sids[i]].suggestedMarks;
            revisedMarks[i]   = applications[sids[i]].revisedMarks;
            finalMarks[i]     = _finalMarksOf(sids[i]);
        }
    }

    function getExamApplicationNotes(uint256 examId)
        public
        view
        returns (
            string[]  memory scriptIds,
            string[]  memory reasons,
            string[]  memory comments,
            string[]  memory examinerNotes,
            uint256[] memory appliedAt,
            uint256[] memory resolvedAt
        )
    {
        string[] memory sids = examApplications[examId];
        uint256 n = sids.length;
        scriptIds     = new string[](n);
        reasons       = new string[](n);
        comments      = new string[](n);
        examinerNotes = new string[](n);
        appliedAt     = new uint256[](n);
        resolvedAt    = new uint256[](n);
        for (uint256 i = 0; i < n; i++) {
            scriptIds[i]     = sids[i];
            reasons[i]       = applications[sids[i]].reason;
            comments[i]      = applications[sids[i]].comment;
            examinerNotes[i] = applications[sids[i]].examinerNote;
            appliedAt[i]     = applications[sids[i]].appliedAt;
            resolvedAt[i]    = applications[sids[i]].resolvedAt;
        }
    }

    // Final marks of an application (revised marks if the marks were
    // actually updated, otherwise the current on-chain marks).
    function _finalMarksOf(string memory sid)
        public
        view
        returns (uint256)
    {
        if (applications[sid].marksUpdated) return applications[sid].revisedMarks;
        return resultContract.getMarksValue(sid);
    }

    /**
     * @notice The caller's OWN applications (or admin viewing a student).
     */
    function getStudentApplications(address student)
        public
        view
        onlyAdminOrSelf(student)
        returns (
            string[]  memory scriptIds,
            uint256[] memory examIds,
            uint8[]   memory sections,
            uint8[]   memory statuses,
            bool[]    memory marksUpdated,
            string[]  memory reasons
        )
    {
        string[] memory sids = studentApplications[student];
        uint256 n = sids.length;
        scriptIds    = new string[](n);
        examIds      = new uint256[](n);
        sections     = new uint8[](n);
        statuses     = new uint8[](n);
        marksUpdated = new bool[](n);
        reasons      = new string[](n);
        for (uint256 i = 0; i < n; i++) {
            scriptIds[i]    = sids[i];
            examIds[i]      = applications[sids[i]].examId;
            sections[i]     = applications[sids[i]].section;
            statuses[i]     = uint8(applications[sids[i]].status);
            marksUpdated[i] = applications[sids[i]].marksUpdated;
            reasons[i]      = applications[sids[i]].reason;
        }
    }

    function getStudentApplicationTimes(address student)
        public
        view
        onlyAdminOrSelf(student)
        returns (
            string[]  memory scriptIds,
            uint256[] memory appliedAt,
            uint256[] memory resolvedAt
        )
    {
        string[] memory sids = studentApplications[student];
        uint256 n = sids.length;
        scriptIds  = new string[](n);
        appliedAt  = new uint256[](n);
        resolvedAt = new uint256[](n);
        for (uint256 i = 0; i < n; i++) {
            scriptIds[i]  = sids[i];
            appliedAt[i]  = applications[sids[i]].appliedAt;
            resolvedAt[i] = applications[sids[i]].resolvedAt;
        }
    }

    /**
     * @notice Single-application status by script (public, anonymous).
     *         0 = none.
     */
    function getApplicationStatus(string memory scriptId)
        public
        view
        scriptExists(scriptId)
        returns (uint8)
    {
        if (bytes(applications[scriptId].scriptId).length == 0) return 0;
        return uint8(applications[scriptId].status) + 1;
    }

    function getExamApplicationCount(uint256 examId)
        public
        view
        returns (uint256)
    {
        return examApplications[examId].length;
    }

    function getStudentApplicationCount(address student)
        public
        view
        returns (uint256)
    {
        return studentApplications[student].length;
    }
}
