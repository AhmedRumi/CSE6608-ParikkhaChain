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

    struct MarksRecord {
        string scriptId;
        uint256 examId;
        uint256 marksObtained;
        uint256 totalMarks;
        address submittedBy;
        uint256 submittedAt;
        GradeStatus status;
        bool exists;
    }

    struct AuditEntry {
        string scriptId;
        uint256 oldMarks;
        uint256 newMarks;
        address changedBy;
        string reason;
        uint256 timestamp;
        string changeType;
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

    mapping(string => MarksRecord) public marks;
    mapping(string => AuditEntry[]) public auditTrail;
    mapping(uint256 => bool) public examFinalized;
    mapping(uint256 => string[]) public examResults;

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
            "Only admin can perform this action"
        );
        _;
    }

    modifier onlyAssignedExaminer(string memory scriptId) {
        uint256 examId = hashContract.getExamId(scriptId);
        require(
            rbacContract.isAssignedExaminer(msg.sender, examId),
            "Not assigned as examiner for this exam"
        );
        _;
    }

    modifier onlyAssignedScrutinizer(string memory scriptId) {
        uint256 examId = hashContract.getExamId(scriptId);
        require(
            rbacContract.isAssignedScrutinizer(msg.sender, examId),
            "Not assigned as scrutinizer for this exam"
        );
        _;
    }

    modifier onlyAdminOrSelf(address student) {
        require(
            rbacContract.hasRole(msg.sender, RBAC.Role.ADMIN) ||
            msg.sender == student,
            "Only admin or the student themselves can view this result"
        );
        _;
    }

    modifier examNotFinalized(uint256 examId) {
        require(!examFinalized[examId], "Exam results already finalized");
        _;
    }

    modifier scriptExists(string memory scriptId) {
        require(
            hashContract.scriptExistsPublic(scriptId),
            "Script does not exist"
        );
        _;
    }

    // ─── Core marking functions ───────────────────────────────────────────

    function submitMarks(
        string memory scriptId,
        uint256 marksObtained,
        uint256 totalMarks
    ) public onlyAssignedExaminer(scriptId) scriptExists(scriptId) {

        (uint256 examId, , ) = hashContract.getAnonymousScriptDetails(scriptId);

        ExamLifecycle.ExamState examState = examContract.getExamState(examId);
        require(
            examState == ExamLifecycle.ExamState.EVALUATION ||
            examState == ExamLifecycle.ExamState.SCRUTINY,
            "Exam not in correct state for marking"
        );
        require(!marks[scriptId].exists, "Marks already submitted for this script");
        require(marksObtained <= totalMarks, "Marks obtained cannot exceed total marks");
        require(totalMarks > 0, "Total marks must be greater than zero");

        marks[scriptId] = MarksRecord({
            scriptId:      scriptId,
            examId:        examId,
            marksObtained: marksObtained,
            totalMarks:    totalMarks,
            submittedBy:   msg.sender,
            submittedAt:   block.timestamp,
            status:        GradeStatus.SUBMITTED,
            exists:        true
        });

        examResults[examId].push(scriptId);

        auditTrail[scriptId].push(AuditEntry({
            scriptId:   scriptId,
            oldMarks:   0,
            newMarks:   marksObtained,
            changedBy:  msg.sender,
            reason:     "Initial marking",
            timestamp:  block.timestamp,
            changeType: "INITIAL"
        }));

        emit MarksSubmitted(scriptId, examId, marksObtained, msg.sender);
    }

    function submitScrutiny(
        string memory scriptId,
        uint256 newMarks,
        string memory reason
    ) public onlyAssignedScrutinizer(scriptId) scriptExists(scriptId) {

        require(marks[scriptId].exists, "No marks submitted for this script");
        require(
            marks[scriptId].status != GradeStatus.FINALIZED,
            "Cannot scrutinize finalized grades"
        );

        uint256 examId = marks[scriptId].examId;
        ExamLifecycle.ExamState examState = examContract.getExamState(examId);
        require(
            examState == ExamLifecycle.ExamState.SCRUTINY,
            "Exam not in scrutiny state"
        );
        require(newMarks <= marks[scriptId].totalMarks, "New marks exceed total marks");
        require(bytes(reason).length > 0, "Reason is required for scrutiny");

        uint256 oldMarks = marks[scriptId].marksObtained;
        marks[scriptId].marksObtained = newMarks;
        marks[scriptId].status        = GradeStatus.SCRUTINIZED;

        auditTrail[scriptId].push(AuditEntry({
            scriptId:   scriptId,
            oldMarks:   oldMarks,
            newMarks:   newMarks,
            changedBy:  msg.sender,
            reason:     reason,
            timestamp:  block.timestamp,
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
            "Exam not ready for finalization"
        );

        string[] memory scriptIds = examResults[examId];
        require(scriptIds.length > 0, "No results to finalize");

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
        return (record.marksObtained, record.totalMarks, record.status);
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
            "Address is not a registered student"
        );

        string[] memory studentScripts = hashContract.getStudentScripts(student);
        require(studentScripts.length > 0, "No scripts found for this student");

        for (uint256 i = 0; i < studentScripts.length; i++) {
            if (marks[studentScripts[i]].examId == examId &&
                marks[studentScripts[i]].exists) {
                MarksRecord memory record = marks[studentScripts[i]];
                return (
                    record.scriptId,
                    record.marksObtained,
                    record.totalMarks,
                    record.status
                );
            }
        }

        revert("No result found for this student in this exam");
    }

    /**
     * @notice Get ALL results for a student across every exam they sat.
     *         Returns parallel arrays — one entry per script/course.
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
            string[]  memory scriptIds,
            uint256[] memory examIds,
            string[]  memory courseCodes,
            uint256[] memory marksObtained,
            uint256[] memory totalMarks,
            GradeStatus[] memory statuses,
            bool[]    memory hasScrutiny
        )
    {
        require(
            rbacContract.hasRole(student, RBAC.Role.STUDENT),
            "Address is not a registered student"
        );

        string[] memory studentScripts = hashContract.getStudentScripts(student);
        uint256 n = studentScripts.length;
        require(n > 0, "No scripts found for this student");

        // Allocate return arrays
        scriptIds      = new string[](n);
        examIds        = new uint256[](n);
        courseCodes    = new string[](n);
        marksObtained  = new uint256[](n);
        totalMarks     = new uint256[](n);
        statuses       = new GradeStatus[](n);
        hasScrutiny    = new bool[](n);

        for (uint256 i = 0; i < n; i++) {
            string memory sid = studentScripts[i];
            scriptIds[i] = sid;

            if (marks[sid].exists) {
                MarksRecord memory rec = marks[sid];
                examIds[i]       = rec.examId;
                marksObtained[i] = rec.marksObtained;
                totalMarks[i]    = rec.totalMarks;
                statuses[i]      = rec.status;

                // Fetch course code from ExamLifecycle
                try examContract.getExam(rec.examId) returns (
                    uint256, string memory, string memory courseCode,
                    uint256, ExamLifecycle.ExamState
                ) {
                    courseCodes[i] = courseCode;
                } catch {
                    courseCodes[i] = "N/A";
                }

                // Check if scrutiny happened (audit trail has > 1 entry)
                hasScrutiny[i] = auditTrail[sid].length > 1;
            }
        }

        return (scriptIds, examIds, courseCodes, marksObtained,
                totalMarks, statuses, hasScrutiny);
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
