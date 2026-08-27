// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "./RBAC.sol";

contract ExamLifecycle {
    RBAC public rbacContract;
    
    enum ExamState {
        CREATED,     // 0
        ACTIVE,      // 1
        EVALUATION,  // 2
        SCRUTINY,    // 3
        COMPLETED,   // 4
        FINALIZED    // 5 — rescrutiny window closed; results are final
    }
    
    struct Exam {
        uint256 examId;
        string examName;
        string courseCode;
        uint256 examDate;
        ExamState state;
        address createdBy;
        uint256 createdAt;
        uint256 termId;          // 0 = "General" (legacy exams)
        uint256[] sectionTotals; // per-section mark totals — the array length
                                 // IS the section count (admin-defined: 1..10)
        bool exists;
    }

    // Maximum number of marking sections an exam may have (admin inputs the
    // actual count and each section's total at exam creation).
    uint8 public constant MAX_SECTIONS = 10;
    
    // Storage
    mapping(uint256 => Exam) public exams;
    mapping(uint256 => mapping(address => bool)) public enrollments;
    mapping(address => uint256[]) private studentExams;
    mapping(uint256 => address[]) private enrolledStudents;  // ← NEW!
    
    // Term (examination type) registry
    uint256 public termCount;
    mapping(uint256 => string) public termNames;
    
    uint256 public examCount;
    
    // Events
    event ExamCreated(uint256 indexed examId, string examName, string courseCode, uint256 examDate);
    event StudentEnrolled(uint256 indexed examId, address indexed student);
    event ExamStateUpdated(uint256 indexed examId, ExamState newState);
    event TermCreated(uint256 indexed termId, string termName);
    
    constructor(address rbacAddress) {
        rbacContract = RBAC(rbacAddress);
        examCount = 0;
        termCount = 0;
    }
    
    // Modifiers
    modifier onlyAdmin() {
        require(
            rbacContract.hasRole(msg.sender, RBAC.Role.ADMIN),
            "Only admin can perform this action"
        );
        _;
    }
    
    modifier examExists(uint256 examId) {
        require(exams[examId].exists, "Exam does not exist");
        _;
    }
    
    // Create exam (legacy — General term, single section of 50)
    function createExam(
        string memory examName,
        string memory courseCode,
        uint256 examDate
    ) public onlyAdmin returns (uint256) {
        require(bytes(examName).length > 0, "Exam name cannot be empty");
        require(bytes(courseCode).length > 0, "Course code cannot be empty");
        require(examDate > block.timestamp, "Exam date must be in the future");

        uint256[] memory totals = new uint256[](1);
        totals[0] = 50;

        examCount++;

        exams[examCount] = Exam({
            examId: examCount,
            examName: examName,
            courseCode: courseCode,
            examDate: examDate,
            state: ExamState.CREATED,
            createdBy: msg.sender,
            createdAt: block.timestamp,
            termId: 0,
            sectionTotals: totals,
            exists: true
        });
        
        emit ExamCreated(examCount, examName, courseCode, examDate);
        
        return examCount;
    }
    
    // Create term (examination type): e.g. "BSc Jan-26", "Supply 2025"
    function createTerm(string memory termName)
        public
        onlyAdmin
        returns (uint256)
    {
        require(bytes(termName).length > 0, "Term name cannot be empty");
        termCount++;
        termNames[termCount] = termName;
        emit TermCreated(termCount, termName);
        return termCount;
    }
    
    function getTermName(uint256 termId) public view returns (string memory) {
        if (termId == 0 || termId > termCount) return "General";
        return termNames[termId];
    }
    
    function getTermCount() public view returns (uint256) {
        return termCount;
    }
    
    // Create a course exam under a term with an admin-defined number of
    // marking sections; each section has its own total (e.g. one section of
    // 100, two sections of 50/50, three sections of 30/30/40, ...).
    function createTermExam(
        uint256 termId,
        string memory examName,
        string memory courseCode,
        uint256 examDate,
        uint256[] memory sectionTotals
    ) public onlyAdmin returns (uint256) {
        require(termId > 0 && termId <= termCount, "Invalid term");
        require(bytes(examName).length > 0, "Exam name cannot be empty");
        require(bytes(courseCode).length > 0, "Course code cannot be empty");
        require(examDate > block.timestamp, "Exam date must be in the future");
        require(
            sectionTotals.length >= 1 && sectionTotals.length <= MAX_SECTIONS,
            "Section count must be between 1 and MAX_SECTIONS"
        );
        for (uint256 i = 0; i < sectionTotals.length; i++) {
            require(sectionTotals[i] > 0, "Section totals must be positive");
            require(sectionTotals[i] <= 1000, "Section total cannot exceed 1000");
        }
        
        examCount++;
        
        exams[examCount] = Exam({
            examId: examCount,
            examName: examName,
            courseCode: courseCode,
            examDate: examDate,
            state: ExamState.CREATED,
            createdBy: msg.sender,
            createdAt: block.timestamp,
            termId: termId,
            sectionTotals: sectionTotals,
            exists: true
        });
        
        emit ExamCreated(examCount, examName, courseCode, examDate);
        
        return examCount;
    }
    
    // Student self-registration for an offered course (auto-enrolled).
    // Admin can still customize enrollment afterwards (enroll/unenroll).
    function registerForCourse(uint256 examId)
        public
        examExists(examId)
    {
        require(
            rbacContract.hasRole(msg.sender, RBAC.Role.STUDENT),
            "Not a registered student"
        );
        require(
            exams[examId].state == ExamState.CREATED ||
            exams[examId].state == ExamState.ACTIVE,
            "Course is not open for registration"
        );
        require(!enrollments[examId][msg.sender], "Already registered for this course");
        
        enrollments[examId][msg.sender] = true;
        studentExams[msg.sender].push(examId);
        enrolledStudents[examId].push(msg.sender);
        
        emit StudentEnrolled(examId, msg.sender);
    }
    
    // Number of marking sections of an exam — admin-defined at creation
    // (1..MAX_SECTIONS). Derived from the sectionTotals array length.
    function getSectionCount(uint256 examId)
        public
        view
        examExists(examId)
        returns (uint8)
    {
        return uint8(exams[examId].sectionTotals.length);
    }

    // Total marks of ONE section of an exam (0 when the section does not
    // exist). Sections are numbered 1..getSectionCount().
    function getSectionTotal(uint256 examId, uint8 section)
        public
        view
        examExists(examId)
        returns (uint256)
    {
        if (section == 0 || section > exams[examId].sectionTotals.length) {
            return 0;
        }
        return exams[examId].sectionTotals[section - 1];
    }
    
    // Enroll student
    function enrollStudent(uint256 examId, address student)
        public
        onlyAdmin
        examExists(examId)
    {
        require(
            rbacContract.hasRole(student, RBAC.Role.STUDENT),
            "Address does not have STUDENT role"
        );
        require(!enrollments[examId][student], "Student already enrolled");
        
        enrollments[examId][student] = true;
        studentExams[student].push(examId);
        enrolledStudents[examId].push(student);  // ← NEW!
        
        emit StudentEnrolled(examId, student);
    }
    
    // Batch enroll students
    function enrollStudentsBatch(uint256 examId, address[] memory students)
        public
        onlyAdmin
        examExists(examId)
    {
        for (uint256 i = 0; i < students.length; i++) {
            require(
                rbacContract.hasRole(students[i], RBAC.Role.STUDENT),
                "Address does not have STUDENT role"
            );
            
            if (enrollments[examId][students[i]]) {
                continue;
            }
            
            enrollments[examId][students[i]] = true;
            studentExams[students[i]].push(examId);
            enrolledStudents[examId].push(students[i]);  // ← NEW!
            
            emit StudentEnrolled(examId, students[i]);
        }
    }
    
    // Update exam state
    function updateExamState(uint256 examId, ExamState newState)
        public
        onlyAdmin
        examExists(examId)
    {
        ExamState currentState = exams[examId].state;
        
        // Valid transitions
        require(
            (currentState == ExamState.CREATED && newState == ExamState.ACTIVE) ||
            (currentState == ExamState.ACTIVE && newState == ExamState.EVALUATION) ||
            (currentState == ExamState.EVALUATION && (newState == ExamState.SCRUTINY || newState == ExamState.COMPLETED)) ||
            (currentState == ExamState.SCRUTINY && newState == ExamState.COMPLETED) ||
            (currentState == ExamState.COMPLETED && newState == ExamState.FINALIZED),
            "Invalid state transition"
        );
        
        exams[examId].state = newState;
        
        emit ExamStateUpdated(examId, newState);
    }
    
    // Check if student is enrolled
    function isStudentEnrolled(uint256 examId, address student)
        public
        view
        examExists(examId)
        returns (bool)
    {
        return enrollments[examId][student];
    }
    
    // Get exam details
    function getExamDetails(uint256 examId)
        public
        view
        examExists(examId)
        returns (
            string memory examName,
            string memory courseCode,
            uint256 examDate,
            ExamState state,
            address createdBy,
            uint256 termId,
            uint256[] memory sectionTotals
        )
    {
        Exam memory exam = exams[examId];
        return (
            exam.examName,
            exam.courseCode,
            exam.examDate,
            exam.state,
            exam.createdBy,
            exam.termId,
            exam.sectionTotals
        );
    }
    
    // Get all exams for a student
    function getStudentExams(address student) 
        public 
        view 
        returns (uint256[] memory) 
    {
        return studentExams[student];
    }
    
    // Get current exam state
    function getExamState(uint256 examId)
        public
        view
        examExists(examId)
        returns (ExamState)
    {
        return exams[examId].state;
    }
    
    // Get total number of exams
    function getTotalExams() public view returns (uint256) {
        return examCount;
    }
    
    // ========================================
    // NEW FUNCTIONS (ADD THESE)
    // ========================================
    
    // Get all enrolled students for an exam
    function getEnrolledStudents(uint256 examId)
        public
        view
        examExists(examId)
        returns (address[] memory)
    {
        return enrolledStudents[examId];
    }
    
    // Get enrollment count for an exam
    function getEnrollmentCount(uint256 examId)
        public
        view
        examExists(examId)
        returns (uint256)
    {
        return enrolledStudents[examId].length;
    }
}