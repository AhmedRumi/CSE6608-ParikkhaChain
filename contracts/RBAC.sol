// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/**
 * @title RBAC — Multi-Role Access Control (Anonymous Assignment Edition)
 * @notice Each address can hold multiple roles simultaneously using bitmasks.
 *         A faculty member can be both EXAMINER and SCRUTINIZER at the same time.
 *
 * Role bits:
 *   ADMIN       = 1  (bit 0)
 *   EXAMINER    = 2  (bit 1)
 *   SCRUTINIZER = 4  (bit 2)
 *   STUDENT     = 8  (bit 3)
 *
 * ANONYMITY MODEL
 *   • Per-exam assignments are PRIVATE. No examiner/scrutinizer can see who
 *     else is assigned to any exam — not the other examiner, not the
 *     scrutinizer, and vice versa.
 *   • Assignment events carry NO addresses (only examId + section), so the
 *     event log leaks nothing about identities.
 *   • Identity-revealing getters (getExamExaminers / getExamScrutinizers /
 *     isAssignedExaminer / getExaminerSection) are admin-only, plus the
 *     whitelisted ResultAudit / Rescrutiny contracts that enforce the rules.
 *   • A faculty member can always check their OWN assignment via the
 *     self-check getters (getMyExamSection / isScrutinizerForExam).
 *
 * SECTIONS
 *   Each exam has an admin-defined number of marking sections (1..10) with
 *   per-section totals set in ExamLifecycle at creation. Each section is
 *   assigned its own examiner — examiners never see other sections or other
 *   examiners. Section numbers are validated here against 1..MAX_SECTIONS;
 *   the actual per-exam section count is enforced by ExamLifecycle.
 *   An examiner can NEVER be the scrutinizer of the SAME exam (can be of
 *   another course's exam).
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

    // Max marking sections per exam (1..MAX_SECTIONS). The exact per-exam
    // section count is defined by the admin in ExamLifecycle at creation;
    // RBAC bounds assignment checks against this maximum.
    uint8 public constant MAX_SECTIONS = 10;

    // address => bitmask of roles
    mapping(address => uint8) public roleBits;

    // ─── PRIVATE assignment state (anonymity core) ─────────────────────────
    // examId => section (1=A, 2=B) => assigned examiner address
    mapping(uint256 => mapping(uint8 => address)) private examExaminers;

    // examId => scrutinizer address => assigned?
    mapping(uint256 => mapping(address => bool)) private scrutinizerAssignments;

    // examId => list of assigned scrutinizers (kept for admin getter)
    mapping(uint256 => address[]) private examScrutinizers;

    // Whitelisted contracts allowed to verify assignments
    address private resultAudit;
    address private rescrutiny;

    constructor() {
        admin = msg.sender;
        roleBits[msg.sender] = ROLE_ADMIN;
    }

    // ─── Events (address-free — never leak identities) ─────────────────────

    event RoleGranted(address indexed account, uint8 roleBit);
    event RoleRevoked(address indexed account, uint8 roleBit);
    event ExaminerAssigned(uint256 indexed examId, uint8 section);
    event ExaminerRevoked(uint256 indexed examId, uint8 section);
    event ScrutinizerAssigned(uint256 indexed examId);
    event ScrutinizerRevoked(uint256 indexed examId);

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

    // Admin or the whitelisted ResultAudit / Rescrutiny contracts
    // (cross-contract checks)
    modifier onlyAdminOrTrusted() {
        require(
            roleBits[msg.sender] & ROLE_ADMIN != 0 ||
            (resultAudit != address(0) && msg.sender == resultAudit) ||
            (rescrutiny != address(0) && msg.sender == rescrutiny),
            "Not authorized"
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

    // ─── Whitelist Management ──────────────────────────────────────────────
    //
    // ResultAudit enforces the marking rules on-chain (only the examiner of a
    // script's section may submit, only assigned scrutinizers may return);
    // Rescrutiny enforces the post-completion re-evaluation flow. They need
    // access to the PRIVATE assignment state, but no other caller may read
    // it. The admin links their addresses after deployment.

    /**
     * @notice Whitelist the ResultAudit contract for assignment checks.
     *         Call AFTER deploying ResultAudit: setResultAudit(resultAuditAddr).
     */
    function setResultAudit(address resultAuditAddress) public onlyAdmin {
        require(resultAuditAddress != address(0), "Invalid address");
        resultAudit = resultAuditAddress;
    }

    function getResultAuditAddress() public view returns (address) {
        return resultAudit;
    }

    /**
     * @notice Whitelist the Rescrutiny contract (post-completion re-evaluation
     *         flow). Call AFTER deploying Rescrutiny: setRescrutiny(addr).
     */
    function setRescrutiny(address rescrutinyAddress) public onlyAdmin {
        require(rescrutinyAddress != address(0), "Invalid address");
        rescrutiny = rescrutinyAddress;
    }

    function getRescrutinyAddress() public view returns (address) {
        return rescrutiny;
    }

    /**
     * @notice True if `account` is the whitelisted Rescrutiny contract
     *         (used by ResultAudit.updateMarksAfterRescrutiny).
     */
    function isTrustedRescrutiny(address account) public view returns (bool) {
        return rescrutiny != address(0) && account == rescrutiny;
    }

    // ─── Exam-Specific Assignment ─────────────────────────────────────────

    /**
     * @notice Assign an examiner to a specific section of a specific exam.
     *         Sections are numbered 1..getSectionCount() per exam
     *         (1 = first section, 2 = second, ... — EXAMINER A/B naming is
     *         just "section 1"/"section 2" now). A section can hold only one
     *         examiner. Emits an address-free event — nobody learns who was
     *         assigned.
     */
    function assignExaminerToExam(address examiner, uint256 examId, uint8 section)
        public
        onlyAdmin
    {
        require(
            section >= 1 && section <= MAX_SECTIONS,
            "Invalid section"
        );
        require(
            roleBits[examiner] & ROLE_EXAMINER != 0 ||
            roleBits[examiner] & ROLE_ADMIN    != 0,
            "No EXAMINER role"
        );
        require(
            examExaminers[examId][section] == address(0),
            "Section already assigned"
        );
        // One person cannot mark two sections of the same exam
        for (uint8 i = 1; i <= MAX_SECTIONS; i++) {
            if (i == section) continue;
            require(
                examExaminers[examId][i] != examiner,
                "Examiner already assigned to another section"
            );
        }
        // An examiner can never scrutinize the SAME exam (can scrutinize
        // other courses' exams, though)
        require(
            !scrutinizerAssignments[examId][examiner],
            "Cannot be examiner and scrutinizer of the same exam"
        );

        examExaminers[examId][section] = examiner;
        emit ExaminerAssigned(examId, section);
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
        // A scrutinizer can never be an examiner of the SAME exam (they can
        // scrutinize another course's exam, though)
        for (uint8 i = 1; i <= MAX_SECTIONS; i++) {
            require(
                examExaminers[examId][i] != scrutinizer,
                "Cannot be examiner and scrutinizer of the same exam"
            );
        }
        scrutinizerAssignments[examId][scrutinizer] = true;
        examScrutinizers[examId].push(scrutinizer);
        emit ScrutinizerAssigned(examId);
    }

    function revokeExaminerFromExam(address examiner, uint256 examId)
        public
        onlyAdmin
    {
        uint8 foundSection = 0;
        for (uint8 i = 1; i <= MAX_SECTIONS; i++) {
            if (examExaminers[examId][i] == examiner) {
                foundSection = i;
                break;
            }
        }
        require(foundSection != 0, "Not assigned");
        examExaminers[examId][foundSection] = address(0);
        emit ExaminerRevoked(examId, foundSection);
    }

    function revokeScrutinizerFromExam(address scrutinizer, uint256 examId)
        public
        onlyAdmin
    {
        require(scrutinizerAssignments[examId][scrutinizer], "Not assigned");
        scrutinizerAssignments[examId][scrutinizer] = false;

        address[] storage list = examScrutinizers[examId];
        for (uint256 i = 0; i < list.length; i++) {
            if (list[i] == scrutinizer) {
                list[i] = list[list.length - 1];
                list.pop();
                break;
            }
        }
        emit ScrutinizerRevoked(examId);
    }

    // ─── Assignment Checks (called by ResultAudit / Rescrutiny) ───────────
    //
    // These REVEAL WHO IS ASSIGNED, so they are restricted to the admin and
    // the whitelisted contracts. They call them with the caller's own address
    // when enforcing marking / scrutiny / rescrutiny rules.

    function isAssignedExaminer(address account, uint256 examId)
        public
        view
        onlyAdminOrTrusted
        returns (bool)
    {
        for (uint8 i = 1; i <= MAX_SECTIONS; i++) {
            if (examExaminers[examId][i] == account) return true;
        }
        return false;
    }

    /**
     * @notice Which section number is `examiner` assigned to for `examId`?
     *         0 = not assigned.
     */
    function getExaminerSection(address examiner, uint256 examId)
        public
        view
        onlyAdminOrTrusted
        returns (uint8)
    {
        for (uint8 i = 1; i <= MAX_SECTIONS; i++) {
            if (examExaminers[examId][i] == examiner) return i;
        }
        return 0;
    }

    function isAssignedScrutinizer(address account, uint256 examId)
        public
        view
        onlyAdminOrTrusted
        returns (bool)
    {
        return scrutinizerAssignments[examId][account];
    }

    // ─── Self-Checks (reveal only the caller's OWN assignment) ─────────────

    /**
     * @notice Caller's own section number for an exam: 1..getSectionCount()
     *         or 0 (none).
     */
    function getMyExamSection(uint256 examId) public view returns (uint8) {
        for (uint8 i = 1; i <= MAX_SECTIONS; i++) {
            if (examExaminers[examId][i] == msg.sender) return i;
        }
        return 0;
    }

    /**
     * @notice Whether the caller is an assigned scrutinizer for an exam.
     */
    function isScrutinizerForExam(uint256 examId) public view returns (bool) {
        return scrutinizerAssignments[examId][msg.sender];
    }

    // ─── Getters (admin only — reveal identities) ─────────────────────────

    /**
     * @notice Assigned examiners for an exam as a dense list paired with each
     *         examiner's section number. ADMIN ONLY.
     */
    function getExamExaminers(uint256 examId)
        public
        view
        onlyAdmin
        returns (address[] memory examiners, uint8[] memory sections)
    {
        address[] memory tmpExaminers = new address[](MAX_SECTIONS);
        uint8[] memory tmpSections = new uint8[](MAX_SECTIONS);
        uint256 n = 0;
        for (uint8 i = 1; i <= MAX_SECTIONS; i++) {
            if (examExaminers[examId][i] != address(0)) {
                tmpExaminers[n] = examExaminers[examId][i];
                tmpSections[n] = i;
                n++;
            }
        }
        examiners = new address[](n);
        sections = new uint8[](n);
        for (uint256 i = 0; i < n; i++) {
            examiners[i] = tmpExaminers[i];
            sections[i] = tmpSections[i];
        }
    }

    /**
     * @notice Assigned scrutinizers for an exam. ADMIN ONLY.
     */
    function getExamScrutinizers(uint256 examId)
        public
        view
        onlyAdmin
        returns (address[] memory)
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
