// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "./RBAC.sol";
import "./ExamLifecycle.sol";
import "./Hashregistry.sol";

contract ResultAudit {
    RBAC public rbacContract;
    ExamLifecycle public examContract;
    HashRegistry public hashContract;

    enum GradeStatus {
        NOT_SUBMITTED,   // 0
        SUBMITTED,       // 1
        UNDER_SCRUTINY,  // 2
        SCRUTINIZED,     // 3
        FINALIZED        // 4
    }

    // Split into two structs to avoid stack-too-deep
    // Packing: address(20) + bool + bool = 22 bytes → fits in one 32-byte slot
    struct ExaminerRecord {
        address examiner1Address;   // 20 bytes ─┐ packed into
        bool    examiner1Submitted; //  1 byte   ─┤ one slot
        bool    examiner2Submitted; //  1 byte   ─┘ (22 bytes total)
        address examiner2Address;   // 20 bytes (own slot)
        uint128 examiner1Marks;     //  16 bytes ─┐ packed into
        uint128 examiner2Marks;     //  16 bytes ─┘ one slot
    }

    struct MarksRecord {
        // scriptId removed — it is already the mapping key
        uint64      examId;        //  8 bytes ─┐
        uint64      submittedAt;   //  8 bytes  │ packed into
        uint32      marksObtained; //  4 bytes  │ one 32-byte slot
        uint32      totalMarks;    //  4 bytes  │
        GradeStatus status;        //  1 byte   │ (GradeStatus is uint8)
        bool        exists;        //  1 byte  ─┘
        // totalMarks is always 100 but kept for interface compatibility
    }

    struct AuditEntry {
        // scriptId removed — it is already the mapping key, no need to store again
        uint32  oldMarks;    //  4 bytes ─┐ packed: 4+4+8+20 = 36 bytes
        uint32  newMarks;    //  4 bytes  │ (2 slots instead of 7)
        uint64  timestamp;   //  8 bytes  │
        address changedBy;   // 20 bytes ─┘
        string  reason;      // dynamic (separate slot)
        string  changeType;  // dynamic (separate slot — short: "EXAMINER1" etc.)
    }

    // ── New: per-script result view struct (returned to caller) ──────────
    struct ScriptResult {
        string  scriptId;
        uint256 examId;
        string  courseCode;
        uint256 marksObtained;
        uint256 totalMarks;
        GradeStatus status;
        bool    hasScrutiny;
    }

    mapping(string => MarksRecord)   public marks;
    mapping(string => ExaminerRecord) public examinerData;
    mapping(string => AuditEntry[])  public auditTrail;
    mapping(uint256 => bool)         public examFinalized;
    mapping(uint256 => string[])     public examResults;

    constructor(
        address rbacAddress,
        address examAddress,
        address hashAddress
    ) {
        rbacContract = RBAC(rbacAddress);
        examContract = ExamLifecycle(examAddress);
        hashContract = HashRegistry(hashAddress);
    }

    // ─── Events ──────────────────────────────────────────────────────────

    event MarksSubmitted(
        string indexed scriptId,
        uint256 examId,
        uint256 marksValue,
        address indexed examiner
    );
    event MarksScrutinized(
        string indexed scriptId,
        uint256 oldMarks,
        uint256 newMarks,
        address indexed scrutinizer,
        string reason
    );
    event ResultFinalized(uint256 indexed examId, uint256 totalScripts);

    // ─── Modifiers ────────────────────────────────────────────────────────

    modifier onlyAdmin() {
        require(
            rbacContract.hasRole(msg.sender, RBAC.Role.ADMIN),
            "Not admin"
        );
        _;
    }

    modifier onlyAssignedExaminer(string memory scriptId) {
        uint256 examId = hashContract.getExamId(scriptId);
        require(
            rbacContract.isAssignedExaminer(msg.sender, examId),
            "Not assigned"
        );
        _;
    }

    modifier onlyAssignedScrutinizer(string memory scriptId) {
        uint256 examId = hashContract.getExamId(scriptId);
        require(
            rbacContract.isAssignedScrutinizer(msg.sender, examId),
            "Not assigned"
        );
        _;
    }

    modifier onlyAdminOrSelf(address student) {
        require(
            rbacContract.hasRole(msg.sender, RBAC.Role.ADMIN) ||
            msg.sender == student,
            "Unauthorized"
        );
        _;
    }

    modifier examNotFinalized(uint256 examId) {
        require(!examFinalized[examId], "Finalized");
        _;
    }

    modifier scriptExists(string memory scriptId) {
        require(
            hashContract.scriptExistsPublic(scriptId),
            "No script"
        );
        _;
    }

    // ─── Core marking functions ───────────────────────────────────────────

    /**
     * @notice Examiner submits their portion of marks (out of 50).
     *         Two examiners must both submit before the script is SUBMITTED.
     *         First examiner to call registers as examiner1, second as examiner2.
     *         Total marks = examiner1Marks + examiner2Marks (out of 100).
     *
     * Remix: ResultAudit → submitMarks(scriptId, 42)
     *        Call from examiner1 wallet, then examiner2 wallet.
     */
    function submitMarks(
        string memory scriptId,
        uint256 marksOutOf50
    ) public onlyAssignedExaminer(scriptId) scriptExists(scriptId) {

        require(marksOutOf50 <= 50, "Max 50");

        (uint256 examId, , ) = hashContract.getAnonymousScriptDetails(scriptId);

        ExamLifecycle.ExamState examState = examContract.getExamState(examId);
        require(
            examState == ExamLifecycle.ExamState.EVALUATION ||
            examState == ExamLifecycle.ExamState.SCRUTINY,
            "Wrong state"
        );

        MarksRecord storage rec = marks[scriptId];

        ExaminerRecord storage er = examinerData[scriptId];

        if (!rec.exists) {
            // First examiner — initialise both records
            marks[scriptId] = MarksRecord({
                examId:        uint64(examId),
                submittedAt:   0,
                marksObtained: 0,
                totalMarks:    100,
                status:        GradeStatus.NOT_SUBMITTED,
                exists:        true
            });
            examinerData[scriptId] = ExaminerRecord({
                examiner1Marks:     uint128(marksOutOf50),
                examiner2Marks:     uint128(0),
                examiner1Address:   msg.sender,
                examiner2Address:   address(0),
                examiner1Submitted: true,
                examiner2Submitted: false
            });

            examResults[examId].push(scriptId);

            auditTrail[scriptId].push(AuditEntry({
                oldMarks:   0,
                newMarks:   uint32(marksOutOf50),
                changedBy:  msg.sender,
                reason:     "Examiner 1 submitted",
                timestamp:  uint64(block.timestamp),
                changeType: "EXAMINER1"
            }));

            emit MarksSubmitted(scriptId, examId, marksOutOf50, msg.sender);

        } else {
            // Second examiner — must be a different address
            require(
                msg.sender != er.examiner1Address,
                "Duplicate examiner"
            );
            require(!er.examiner2Submitted, "Already submitted");

            er.examiner2Marks     = uint128(marksOutOf50);
            er.examiner2Address   = msg.sender;
            er.examiner2Submitted = true;

            uint32 combined       = uint32(er.examiner1Marks + uint128(marksOutOf50));
            rec.marksObtained     = combined;
            rec.submittedAt       = uint64(block.timestamp);
            rec.status            = GradeStatus.SUBMITTED;

            // oldMarks = ex1 individual, newMarks = ex2 individual (NOT combined)
            // combined total = oldMarks + newMarks, readable in audit display
            auditTrail[scriptId].push(AuditEntry({
                oldMarks:   uint32(er.examiner1Marks),
                newMarks:   uint32(marksOutOf50),
                changedBy:  msg.sender,
                reason:     "Examiner 2 submitted",
                timestamp:  uint64(block.timestamp),
                changeType: "EXAMINER2"
            }));

            emit MarksSubmitted(scriptId, examId, combined, msg.sender);
        }
    }

    /**
    /**
     * @notice Get examiner 1 marking status.
     * Remix: ResultAudit → getExaminer1Progress(scriptId)
     */
    function getExaminer1Progress(string memory scriptId)
        public view
        returns (
            bool    submitted,
            uint256 marksGiven,
            address examinerAddr
        )
    {
        ExaminerRecord storage er = examinerData[scriptId];
        return (er.examiner1Submitted, uint256(er.examiner1Marks), er.examiner1Address);
    }

    /**
     * @notice Get examiner 2 status + combined total.
     * Remix: ResultAudit → getExaminer2Progress(scriptId)
     */
    function getExaminer2Progress(string memory scriptId)
        public view
        returns (
            bool    submitted,
            uint256 marksGiven,
            address examinerAddr,
            uint256 combinedTotal,
            bool    bothSubmitted
        )
    {
        ExaminerRecord storage er = examinerData[scriptId];
        return (
            er.examiner2Submitted,
            uint256(er.examiner2Marks),
            er.examiner2Address,
            uint256(marks[scriptId].marksObtained),
            er.examiner1Submitted && er.examiner2Submitted
        );
    }

    function submitScrutiny(
        string memory scriptId,
        uint256 newMarks,
        string memory reason
    ) public onlyAssignedScrutinizer(scriptId) scriptExists(scriptId) {

        require(marks[scriptId].exists, "No marks record for this script");
        require(
            examinerData[scriptId].examiner1Submitted &&
            examinerData[scriptId].examiner2Submitted,
            "Awaiting both examiners"
        );
        require(
            marks[scriptId].status != GradeStatus.FINALIZED,
            "Finalized"
        );

        uint256 examId = marks[scriptId].examId;
        ExamLifecycle.ExamState examState = examContract.getExamState(examId);
        require(
            examState == ExamLifecycle.ExamState.SCRUTINY,
            "Exam not in scrutiny state"
        );
        require(newMarks <= marks[scriptId].totalMarks, "Exceeds total");
        require(bytes(reason).length > 0, "Need reason");

        uint32 oldMarks = marks[scriptId].marksObtained;
        marks[scriptId].marksObtained = uint32(newMarks);
        marks[scriptId].status        = GradeStatus.SCRUTINIZED;

        auditTrail[scriptId].push(AuditEntry({
            oldMarks:   uint32(oldMarks),
            newMarks:   uint32(newMarks),
            changedBy:  msg.sender,
            reason:     reason,
            timestamp:  uint64(block.timestamp),
            changeType: "SCRUTINY"
        }));

        emit MarksScrutinized(scriptId, oldMarks, newMarks, msg.sender, reason);
    }

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
            "Wrong state"
        );

        string[] memory scriptIds = examResults[examId];
        require(scriptIds.length > 0, "No results");

        for (uint256 i = 0; i < scriptIds.length; i++) {
            if (marks[scriptIds[i]].exists) {
                marks[scriptIds[i]].status = GradeStatus.FINALIZED;
            }
        }

        examFinalized[examId] = true;
        emit ResultFinalized(examId, scriptIds.length);
    }

    // ─── Result view functions ────────────────────────────────────────────

    /**
     * @notice Get marks for a single script (anonymous — no identity revealed).
     *         Callable by anyone who knows the script ID.
     */
    function getMarks(string memory scriptId)
        public
        view
        scriptExists(scriptId)
        returns (
            uint256 marksObtained,
            uint256 totalMarks,
            GradeStatus status
        )
    {
        MarksRecord memory record = marks[scriptId];
        return (uint256(record.marksObtained), uint256(record.totalMarks), record.status);
    }

    /**
     * @notice Get result for a specific student in a specific exam.
     *         Callable by the student themselves OR admin.
     * @param examId  The exam to look up.
     * @param student The student's wallet address.
     * @return scriptId      The anonymous script ID used in this exam.
     * @return marksObtained Final marks on blockchain.
     * @return totalMarks    Out of this many marks.
     * @return status        Current grade status.
     */
    function getStudentExamResult(uint256 examId, address student)
        public
        view
        onlyAdminOrSelf(student)
        returns (
            string memory scriptId,
            uint256 marksObtained,
            uint256 totalMarks,
            GradeStatus status
        )
    {
        require(
            rbacContract.hasRole(student, RBAC.Role.STUDENT),
            "Not student"
        );

        string[] memory studentScripts = hashContract.getStudentScripts(student);
        require(studentScripts.length > 0, "No scripts");

        for (uint256 i = 0; i < studentScripts.length; i++) {
            if (marks[studentScripts[i]].examId == examId &&
                marks[studentScripts[i]].exists) {
                MarksRecord memory record = marks[studentScripts[i]];
                return (
                    studentScripts[i],
                    uint256(record.marksObtained),
                    uint256(record.totalMarks),
                    record.status
                );
            }
        }

        revert("No result found for this student in this exam");
    }

    // Internal helper: fetch course code without adding stack depth
    function _getCourseCode(uint256 examId) internal view returns (string memory) {
        try examContract.getExamDetails(examId) returns (
            string memory,
            string memory courseCode,
            uint256,
            ExamLifecycle.ExamState,
            address
        ) {
            return courseCode;
        } catch {
            return "N/A";
        }
    }

    // Internal helper: fill one transcript slot (avoids stack-too-deep in caller)
    function _fillSlot(
        uint256 i,
        string memory sid,
        uint256[] memory examIds,
        string[]  memory courseCodes,
        uint256[] memory marksObtained,
        uint256[] memory totalMarks,
        GradeStatus[] memory statuses,
        bool[]    memory hasScrutiny
    ) internal view {
        MarksRecord storage rec = marks[sid];
        examIds[i]       = uint256(rec.examId);
        marksObtained[i] = uint256(rec.marksObtained);
        totalMarks[i]    = uint256(rec.totalMarks);
        statuses[i]      = rec.status;
        courseCodes[i]   = _getCourseCode(rec.examId);
        hasScrutiny[i]   = auditTrail[sid].length > 1;
    }

    /**
     * @notice Get ALL results for a student across every exam they sat.
     *         Returns parallel arrays -- one entry per script/course.
     *         Callable by the student themselves OR admin.
     *
     * @param student  Student wallet address.
     * @return scriptIds      Array of anonymous script IDs.
     * @return examIds        Corresponding exam IDs.
     * @return courseCodes    Course code for each exam (from ExamLifecycle).
     * @return marksObtained  Final marks for each script.
     * @return totalMarks     Total marks for each script.
     * @return statuses       GradeStatus for each script.
     * @return hasScrutiny    Whether marks were revised by scrutinizer.
     */
    function getFullTranscript(address student)
        public
        view
        onlyAdminOrSelf(student)
        returns (
            string[]      memory scriptIds,
            uint256[]     memory examIds,
            string[]      memory courseCodes,
            uint256[]     memory marksObtained,
            uint256[]     memory totalMarks,
            GradeStatus[] memory statuses,
            bool[]        memory hasScrutiny
        )
    {
        require(
            rbacContract.hasRole(student, RBAC.Role.STUDENT),
            "Not student"
        );

        string[] memory studentScripts = hashContract.getStudentScripts(student);
        uint256 n = studentScripts.length;
        require(n > 0, "No scripts");

        scriptIds     = new string[](n);
        examIds       = new uint256[](n);
        courseCodes   = new string[](n);
        marksObtained = new uint256[](n);
        totalMarks    = new uint256[](n);
        statuses      = new GradeStatus[](n);
        hasScrutiny   = new bool[](n);

        for (uint256 i = 0; i < n; i++) {
            string memory sid = studentScripts[i];
            scriptIds[i] = sid;

            // Always resolve examId and courseCode from HashRegistry
            // so unsubmitted scripts still show correct exam info
            uint256 eid = hashContract.getExamId(sid);
            examIds[i]     = eid;
            courseCodes[i] = _getCourseCode(eid);

            if (marks[sid].exists) {
                // Marks submitted — fill all fields from marks record
                MarksRecord storage rec = marks[sid];
                marksObtained[i] = rec.marksObtained;
                totalMarks[i]    = rec.totalMarks;
                statuses[i]      = rec.status;
                hasScrutiny[i]   = auditTrail[sid].length > 1;
            }
            // If marks not submitted: marksObtained=0, totalMarks=0,
            // status=NOT_SUBMITTED(0), hasScrutiny=false — default zero values
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
     * @notice Get all script IDs for an exam (admin only).
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
