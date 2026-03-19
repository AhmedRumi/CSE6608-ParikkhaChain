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
        COMPLETED    // 4
    }
    
    struct Exam {
        uint256 examId;
        string examName;
        string courseCode;
        uint256 examDate;
        ExamState state;
        address createdBy;
        uint256 createdAt;
        bool exists;
    }
    
    // Storage
    mapping(uint256 => Exam) public exams;
    mapping(uint256 => mapping(address => bool)) public enrollments;
    mapping(address => uint256[]) private studentExams;
    mapping(uint256 => address[]) private enrolledStudents;  // ← NEW!
    
    uint256 public examCount;
    
    // Events
    event ExamCreated(uint256 indexed examId, string examName, string courseCode, uint256 examDate);
    event StudentEnrolled(uint256 indexed examId, address indexed student);
    event ExamStateUpdated(uint256 indexed examId, ExamState newState);
    
    constructor(address rbacAddress) {
        rbacContract = RBAC(rbacAddress);
        examCount = 0;
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
    
    // Create exam
    function createExam(
        string memory examName,
        string memory courseCode,
        uint256 examDate
    ) public onlyAdmin returns (uint256) {
        require(bytes(examName).length > 0, "Exam name cannot be empty");
        require(bytes(courseCode).length > 0, "Course code cannot be empty");
        require(examDate > block.timestamp, "Exam date must be in the future");
        
        examCount++;
        
        exams[examCount] = Exam({
            examId: examCount,
            examName: examName,
            courseCode: courseCode,
            examDate: examDate,
            state: ExamState.CREATED,
            createdBy: msg.sender,
            createdAt: block.timestamp,
            exists: true
        });
        
        emit ExamCreated(examCount, examName, courseCode, examDate);
        
        return examCount;
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
            (currentState == ExamState.SCRUTINY && newState == ExamState.COMPLETED),
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
            address createdBy
        )
    {
        Exam memory exam = exams[examId];
        return (
            exam.examName,
            exam.courseCode,
            exam.examDate,
            exam.state,
            exam.createdBy
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