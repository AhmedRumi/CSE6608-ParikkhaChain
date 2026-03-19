// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "./RBAC.sol";
import "./ExamLifecycle.sol";

contract HashRegistry {
    RBAC public rbacContract;
    ExamLifecycle public examContract;
    
    struct ScriptRecord {
        string scriptId;          // Anonymous ID like "SCRIPT_001"
        uint256 examId;           // Which exam
        string topsheetHash;      // Hash of (name + studentId + courseCode)
        address studentAddress;   // Student wallet address (private!)
        string studentName;       // Student name (private!)
        string studentId;         // Student ID like "0424052015" (private!)
        string courseCode;        // Course code (private!)
        uint256 uploadedAt;       // Timestamp
        bool exists;              // To check if exists
    }
    
    uint256 public scriptCount;
    
    // Mappings to store and retrieve scripts
    mapping(string => ScriptRecord) private scripts;     // scriptId => ScriptRecord (PRIVATE!)
    mapping(uint256 => string[]) public examScripts;     // examId => scriptIds[]
    mapping(address => string[]) public studentScripts;  // student => scriptIds[]
    mapping(string => bool) private usedHashes;          // Prevent hash collisions (PRIVATE!)
    
    // Mapping to prevent duplicate uploads
    mapping(uint256 => mapping(address => bool)) public hasSubmitted;
    
    constructor(address rbacAddress, address examAddress) {
        rbacContract = RBAC(rbacAddress);
        examContract = ExamLifecycle(examAddress);
        scriptCount = 0;
    }
    
    event ScriptRegistered(
        string indexed scriptId,
        uint256 indexed examId,
        address indexed student,
        string topsheetHash
    );
    event StudentRevealed(string indexed scriptId, address student, string studentName);
    
    modifier onlyAdmin() {
        require(
            rbacContract.hasRole(msg.sender, RBAC.Role.ADMIN),
            "Only admin can perform this action"
        );
        _;
    }
    
    modifier scriptExists(string memory scriptId) {
        require(scripts[scriptId].exists, "Script does not exist");
        _;
    }
    
    // Generate anonymous script ID
    function generateScriptId(uint256 examId) 
        internal 
        returns (string memory) 
    {
        scriptCount++;
        
        return string(
            abi.encodePacked(
                "SCRIPT_",
                uintToString(examId),
                "_",
                uintToString(scriptCount)
            )
        );
    }
    
    // Helper function to convert uint to string
    function uintToString(uint256 value) internal pure returns (string memory) {
        if (value == 0) {
            return "0";
        }
        
        uint256 temp = value;
        uint256 digits;
        
        while (temp != 0) {
            digits++;
            temp /= 10;
        }
        
        bytes memory buffer = new bytes(digits);
        
        while (value != 0) {
            digits -= 1;
            buffer[digits] = bytes1(uint8(48 + uint256(value % 10)));
            value /= 10;
        }
        
        return string(buffer);
    }
    
    // Generate hash from topsheet information (Name + StudentID + CourseCode)
    function generateTopsheetHash(
        string memory studentName,
        string memory studentId,
        string memory courseCode
    ) public pure returns (string memory) {
        // Combine topsheet data
        bytes memory combined = abi.encodePacked(
            studentName,
            studentId,
            courseCode
        );
        
        // Generate keccak256 hash
        bytes32 hash = keccak256(combined);
        
        // Convert to readable format with prefix
        return string(abi.encodePacked("TS_", bytes32ToString(hash)));
    }
    
    // Helper function to convert bytes32 to hex string
    function bytes32ToString(bytes32 data) internal pure returns (string memory) {
        bytes memory alphabet = "0123456789abcdef";
        bytes memory str = new bytes(64);
        
        for (uint256 i = 0; i < 32; i++) {
            str[i*2] = alphabet[uint8(data[i] >> 4)];
            str[i*2+1] = alphabet[uint8(data[i] & 0x0f)];
        }
        
        return string(str);
    }
    
    // Main function: Register script by scanning topsheet
    // This is what admin does when replacing topsheet with anonymous ID
    function registerScriptFromTopsheet(
        uint256 examId,
        address studentAddress,
        string memory studentName,
        string memory studentId,
        string memory courseCode
    ) public onlyAdmin returns (string memory scriptId, string memory topsheetHash) {
        // Validations
        require(bytes(studentName).length > 0, "Student name cannot be empty");
        require(bytes(studentId).length > 0, "Student ID cannot be empty");
        require(bytes(courseCode).length > 0, "Course code cannot be empty");
        require(studentAddress != address(0), "Invalid student address");
        
        // Check if student is enrolled in this exam
        require(
            examContract.isStudentEnrolled(examId, studentAddress),
            "Student not enrolled in this exam"
        );
        
        // Check if student hasn't already submitted
        require(
            !hasSubmitted[examId][studentAddress],
            "Student already submitted for this exam"
        );
        
        // Check exam is in correct state (ACTIVE or EVALUATION)
        ExamLifecycle.ExamState currentState = examContract.getExamState(examId);
        require(
            currentState == ExamLifecycle.ExamState.ACTIVE ||
            currentState == ExamLifecycle.ExamState.EVALUATION,
            "Exam not in correct state for submission"
        );
        
        // Generate topsheet hash from student info
        topsheetHash = generateTopsheetHash(studentName, studentId, courseCode);
        
        // Check for hash collision (very rare, but good practice)
        require(!usedHashes[topsheetHash], "Hash collision detected");
        
        // Generate anonymous script ID
        scriptId = generateScriptId(examId);
        
        // Create script record (stores private info on-chain but hidden from examiners)
        scripts[scriptId] = ScriptRecord({
            scriptId: scriptId,
            examId: examId,
            topsheetHash: topsheetHash,
            studentAddress: studentAddress,
            studentName: studentName,
            studentId: studentId,
            courseCode: courseCode,
            uploadedAt: block.timestamp,
            exists: true
        });
        
        // Add to tracking mappings
        examScripts[examId].push(scriptId);
        studentScripts[studentAddress].push(scriptId);
        hasSubmitted[examId][studentAddress] = true;
        usedHashes[topsheetHash] = true;
        
        emit ScriptRegistered(scriptId, examId, studentAddress, topsheetHash);
        
        return (scriptId, topsheetHash);
    }
    
    // Get anonymous script ID only (for examiner to use)
    function getExamScripts(uint256 examId) 
        public 
        view 
        returns (string[] memory) 
    {
        return examScripts[examId];
    }
    
    // Get script details WITHOUT revealing student info (for examiners)
    function getAnonymousScriptDetails(string memory scriptId)
        public
        view
        scriptExists(scriptId)
        returns (
            uint256 examId,
            string memory topsheetHash,
            uint256 uploadedAt
        )
    {
        ScriptRecord memory record = scripts[scriptId];
        return (
            record.examId,
            record.topsheetHash,
            record.uploadedAt
        );
    }
    
    // Reveal student identity (Admin only - after marking complete)
    function revealStudent(string memory scriptId)
        public
        view
        onlyAdmin
        scriptExists(scriptId)
        returns (
            address studentAddress,
            string memory studentName,
            string memory studentId,
            string memory courseCode
        )
    {
        ScriptRecord memory record = scripts[scriptId];
        return (
            record.studentAddress,
            record.studentName,
            record.studentId,
            record.courseCode
        );
    }
    
    // Verify topsheet hash matches (for integrity checking)
    function verifyTopsheet(
        string memory scriptId,
        string memory studentName,
        string memory studentId,
        string memory courseCode
    ) public view scriptExists(scriptId) returns (bool) {
        string memory expectedHash = generateTopsheetHash(studentName, studentId, courseCode);
        return keccak256(bytes(scripts[scriptId].topsheetHash)) == keccak256(bytes(expectedHash));
    }
    
    // Get all scripts submitted by a student
    function getStudentScripts(address student)
        public
        view
        returns (string[] memory)
    {
        return studentScripts[student];
    }
    
    // Check if student has submitted for an exam
    function hasStudentSubmitted(uint256 examId, address student)
        public
        view
        returns (bool)
    {
        return hasSubmitted[examId][student];
    }
    
    // Get total number of scripts
    function getTotalScripts() public view returns (uint256) {
        return scriptCount;
    }
    
    // Check if a script exists (for other contracts to call)
    function scriptExistsPublic(string memory scriptId) public view returns (bool) {
        return scripts[scriptId].exists;
    }
    
    // Get topsheet hash for a script (public - for tracking purposes)
    function getTopsheetHash(string memory scriptId)
        public
        view
        scriptExists(scriptId)
        returns (string memory)
    {
        return scripts[scriptId].topsheetHash;
    }
    
    // Get examId for a script (safe - doesn't reveal student info)
    function getExamId(string memory scriptId)
        public
        view
        scriptExists(scriptId)
        returns (uint256)
    {
        return scripts[scriptId].examId;
    }
}