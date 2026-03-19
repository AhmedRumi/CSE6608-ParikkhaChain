// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/**
 * @title RBAC — Multi-Role Access Control
 * @notice Each address can hold multiple roles simultaneously using bitmasks.
 *         A faculty member can be both EXAMINER and SCRUTINIZER at the same time.
 *
 * Role bits:
 *   ADMIN       = 1  (bit 0)
 *   EXAMINER    = 2  (bit 1)
 *   SCRUTINIZER = 4  (bit 2)
 *   STUDENT     = 8  (bit 3)
 *
 * Example: address with roles = 6 (binary 0110) has EXAMINER + SCRUTINIZER
 */
contract RBAC {
    address public admin;

    // Keep enum for backward compatibility with other contracts
    enum Role {
        NONE,        // 0
        ADMIN,       // 1
        EXAMINER,    // 2
        SCRUTINIZER, // 3
        STUDENT      // 4
    }

    // Role bit constants
    uint8 public constant ROLE_ADMIN       = 1;
    uint8 public constant ROLE_EXAMINER    = 2;
    uint8 public constant ROLE_SCRUTINIZER = 4;
    uint8 public constant ROLE_STUDENT     = 8;

    // address => bitmask of roles
    mapping(address => uint8) public roleBits;

    // examId => examiner address => assigned?
    mapping(uint256 => mapping(address => bool)) public examinerAssignments;

    // examId => scrutinizer address => assigned?
    mapping(uint256 => mapping(address => bool)) public scrutinizerAssignments;

    // examId => list of assigned examiners
    mapping(uint256 => address[]) public examExaminers;

    // examId => list of assigned scrutinizers
    mapping(uint256 => address[]) public examScrutinizers;

    constructor() {
        admin = msg.sender;
        roleBits[msg.sender] = ROLE_ADMIN;
    }

    event RoleGranted(address indexed account, uint8 roleBit);
    event RoleRevoked(address indexed account, uint8 roleBit);
    event ExaminerAssigned(address indexed examiner, uint256 indexed examId);
    event ExaminerRevoked(address indexed examiner, uint256 indexed examId);
    event ScrutinizerAssigned(address indexed scrutinizer, uint256 indexed examId);
    event ScrutinizerRevoked(address indexed scrutinizer, uint256 indexed examId);

    // ─── Modifiers ────────────────────────────────────────────────────────

    modifier onlyAdmin() {
        require(roleBits[msg.sender] & ROLE_ADMIN != 0, "Not admin");
        _;
    }

    modifier onlyExaminer() {
        require(
            roleBits[msg.sender] & ROLE_EXAMINER  != 0 ||
            roleBits[msg.sender] & ROLE_ADMIN     != 0,
            "Not examiner"
        );
        _;
    }

    modifier onlyScrutinizer() {
        require(
            roleBits[msg.sender] & ROLE_SCRUTINIZER != 0 ||
            roleBits[msg.sender] & ROLE_ADMIN       != 0,
            "Not scrutinizer"
        );
        _;
    }

    modifier onlyStudent() {
        require(
            roleBits[msg.sender] & ROLE_STUDENT != 0,
            "Not student"
        );
        _;
    }

    // ─── Role Management ─────────────────────────────────────────────────

    /**
     * @notice Grant a role to an address (additive — does not remove other roles).
     * @param account  Address to grant role to.
     * @param role     Role enum value (ADMIN=1, EXAMINER=2, SCRUTINIZER=3, STUDENT=4).
     *
     * Remix: RBAC → grantRole(address, 2)  — grants EXAMINER
     *        RBAC → grantRole(address, 3)  — grants SCRUTINIZER (stacks with EXAMINER)
     */
    function grantRole(address account, Role role) public onlyAdmin {
        require(account != address(0), "Invalid address");
        require(role != Role.NONE, "Cannot grant NONE");
        uint8 bit = _roleToBit(role);
        roleBits[account] |= bit;
        emit RoleGranted(account, bit);
    }

    /**
     * @notice Revoke a specific role from an address (other roles are kept).
     */
    function revokeRole(address account, Role role) public onlyAdmin {
        require(account != admin || role != Role.ADMIN, "Cannot revoke admin");
        uint8 bit = _roleToBit(role);
        roleBits[account] &= ~bit;
        emit RoleRevoked(account, bit);
    }

    /**
     * @notice Revoke ALL roles from an address.
     */
    function revokeAllRoles(address account) public onlyAdmin {
        require(account != admin, "Cannot revoke admin");
        roleBits[account] = 0;
    }

    /**
     * @notice Check if an address has a specific role.
     *         Compatible with existing contract calls.
     */
    function hasRole(address account, Role role) public view returns (bool) {
        if (role == Role.NONE) return roleBits[account] == 0;
        uint8 bit = _roleToBit(role);
        return roleBits[account] & bit != 0;
    }
    function hasRoleBit(address account, uint8 bit) public view returns (bool) {
    return roleBits[account] & bit != 0;
}

    /**
     * @notice Returns the PRIMARY role for backward compatibility.
     *         Priority: ADMIN > STUDENT > EXAMINER > SCRUTINIZER
     *         Use hasRole() for accurate multi-role checks.
     */
    function getRole(address account) public view returns (Role) {
        uint8 bits = roleBits[account];
        if (bits & ROLE_ADMIN       != 0) return Role.ADMIN;
        if (bits & ROLE_STUDENT     != 0) return Role.STUDENT;
        if (bits & ROLE_EXAMINER    != 0) return Role.EXAMINER;
        if (bits & ROLE_SCRUTINIZER != 0) return Role.SCRUTINIZER;
        return Role.NONE;
    }

    /**
     * @notice Returns the full role bitmask for an address.
     * Remix: RBAC → getRoleBits(address)
     *   0 = no role
     *   2 = EXAMINER only
     *   4 = SCRUTINIZER only
     *   6 = EXAMINER + SCRUTINIZER
     *   8 = STUDENT
     */
    function getRoleBits(address account) public view returns (uint8) {
        return roleBits[account];
    }

    // ─── Exam-Specific Assignment ─────────────────────────────────────────

    /**
     * @notice Assign an examiner to a specific exam.
     *         Account must have EXAMINER or ADMIN role.
     */
    function assignExaminerToExam(address examiner, uint256 examId)
        public
        onlyAdmin
    {
        require(
            roleBits[examiner] & ROLE_EXAMINER != 0 ||
            roleBits[examiner] & ROLE_ADMIN    != 0,
            "No EXAMINER role"
        );
        require(
            !examinerAssignments[examId][examiner],
            "Already assigned"
        );
        examinerAssignments[examId][examiner] = true;
        examExaminers[examId].push(examiner);
        emit ExaminerAssigned(examiner, examId);
    }

    /**
     * @notice Assign a scrutinizer to a specific exam.
     *         Account must have SCRUTINIZER or EXAMINER or ADMIN role.
     *         (Faculty can scrutinize even if primarily an examiner.)
     */
    function assignScrutinizerToExam(address scrutinizer, uint256 examId)
        public
        onlyAdmin
    {
        require(
            roleBits[scrutinizer] & ROLE_SCRUTINIZER != 0 ||
            roleBits[scrutinizer] & ROLE_EXAMINER    != 0 ||
            roleBits[scrutinizer] & ROLE_ADMIN       != 0,
            "No SCRUTINIZER or EXAMINER role"
        );
        require(
            !scrutinizerAssignments[examId][scrutinizer],
            "Already assigned"
        );
        scrutinizerAssignments[examId][scrutinizer] = true;
        examScrutinizers[examId].push(scrutinizer);
        emit ScrutinizerAssigned(scrutinizer, examId);
    }

    function revokeExaminerFromExam(address examiner, uint256 examId)
        public
        onlyAdmin
    {
        require(examinerAssignments[examId][examiner], "Not assigned");
        examinerAssignments[examId][examiner] = false;
        emit ExaminerRevoked(examiner, examId);
    }

    function revokeScrutinizerFromExam(address scrutinizer, uint256 examId)
        public
        onlyAdmin
    {
        require(scrutinizerAssignments[examId][scrutinizer], "Not assigned");
        scrutinizerAssignments[examId][scrutinizer] = false;
        emit ScrutinizerRevoked(scrutinizer, examId);
    }

    // ─── Assignment Checks (called by ResultAudit) ────────────────────────

    function isAssignedExaminer(address account, uint256 examId)
        public view returns (bool)
    {
        if (roleBits[account] & ROLE_ADMIN != 0) return true;
        return examinerAssignments[examId][account];
    }

    function isAssignedScrutinizer(address account, uint256 examId)
        public view returns (bool)
    {
        if (roleBits[account] & ROLE_ADMIN != 0) return true;
        return scrutinizerAssignments[examId][account];
    }

    // ─── Getters ──────────────────────────────────────────────────────────

    function getExamExaminers(uint256 examId)
        public view returns (address[] memory)
    {
        return examExaminers[examId];
    }

    function getExamScrutinizers(uint256 examId)
        public view returns (address[] memory)
    {
        return examScrutinizers[examId];
    }

    // ─── Internal ─────────────────────────────────────────────────────────

    function _roleToBit(Role role) internal pure returns (uint8) {
        if (role == Role.ADMIN)       return ROLE_ADMIN;
        if (role == Role.EXAMINER)    return ROLE_EXAMINER;
        if (role == Role.SCRUTINIZER) return ROLE_SCRUTINIZER;
        if (role == Role.STUDENT)     return ROLE_STUDENT;
        return 0;
    }
}
