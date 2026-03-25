// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "./RBAC.sol";

contract ZKPCommitment {

    RBAC public rbacContract;

    uint256 constant GP_APLUS  = 400;
    uint256 constant GP_A      = 375;
    uint256 constant GP_AMINUS = 350;
    uint256 constant GP_BPLUS  = 325;
    uint256 constant GP_B      = 300;
    uint256 constant GP_BMINUS = 275;
    uint256 constant GP_CPLUS  = 250;
    uint256 constant GP_C      = 225;
    uint256 constant GP_D      = 200;
    uint256 constant GP_F      = 0;
    uint256 constant PASS_MARK = 40;

    struct TranscriptCommitment {
        address student;
        bytes32 commitment;
        uint256 courseCount;
        uint256 totalCredits;
        uint256 committedAt;
        bool    exists;
    }

    struct Criteria {
        uint256 criteriaId;
        address postedBy;
        string  description;
        uint256 minCGPA_scaled;
        uint256 minCourseGrade;
        uint256 courseIndex;
        uint256 minCredits;
        bool    requireAllPass;
        uint256 deadline;
        bool    active;
    }

    struct ProofRecord {
        bool    submitted;
        bool    verified;
        uint256 submittedAt;
    }

    mapping(address => TranscriptCommitment)            public commitments;
    mapping(uint256 => Criteria)                        public criteriaList;
    mapping(uint256 => mapping(address => ProofRecord)) public proofs;
    mapping(uint256 => address[])                       public eligibleStudents;

    uint256 public criteriaCount;

    event TranscriptCommitted(address indexed student, bytes32 commitment,
                               uint256 courseCount, uint256 timestamp);
    event CriteriaPosted(uint256 indexed criteriaId, address indexed postedBy,
                          string description, uint256 minCGPA_scaled);
    event ProofSubmitted(uint256 indexed criteriaId, address indexed student,
                          bool result);

    constructor(address rbacAddress) {
        rbacContract = RBAC(rbacAddress);
    }

    // ── Phase 1: COMMIT ──────────────────────────────────────────────────

    function commitTranscript(
        address student,
        bytes32 commitment,
        uint256 courseCount,
        uint256 totalCredits
    ) public {
        require(rbacContract.hasRole(msg.sender, RBAC.Role.ADMIN),
                "Only admin can commit");
        require(rbacContract.hasRole(student, RBAC.Role.STUDENT),
                "Target must be a student");
        require(courseCount > 0 && courseCount <= 6,
                "courseCount must be 1-6");

        commitments[student] = TranscriptCommitment({
            student:      student,
            commitment:   commitment,
            courseCount:  courseCount,
            totalCredits: totalCredits,
            committedAt:  block.timestamp,
            exists:       true
        });

        emit TranscriptCommitted(student, commitment, courseCount, block.timestamp);
    }

    function getCommitment(address student)
        public view
        returns (bytes32 commitment, uint256 courseCount,
                 uint256 totalCredits, uint256 committedAt)
    {
        TranscriptCommitment memory c = commitments[student];
        require(c.exists, "No commitment found");
        return (c.commitment, c.courseCount, c.totalCredits, c.committedAt);
    }

    // ── Phase 2: CRITERIA ────────────────────────────────────────────────

    function postCriteria(
        string  memory description,
        uint256 minCGPA_scaled,
        uint256 minCourseGrade,
        uint256 courseIndex,
        uint256 minCredits,
        bool    requireAllPass,
        uint256 deadline
    ) public returns (uint256) {
        require(minCGPA_scaled <= 400,          "Max CGPA scaled is 400");
        require(minCourseGrade <= 100,          "Max course grade is 100");
        require(deadline > block.timestamp,     "Deadline must be future");

        criteriaCount++;
        criteriaList[criteriaCount] = Criteria({
            criteriaId:     criteriaCount,
            postedBy:       msg.sender,
            description:    description,
            minCGPA_scaled: minCGPA_scaled,
            minCourseGrade: minCourseGrade,
            courseIndex:    courseIndex,
            minCredits:     minCredits,
            requireAllPass: requireAllPass,
            deadline:       deadline,
            active:         true
        });

        emit CriteriaPosted(criteriaCount, msg.sender, description, minCGPA_scaled);
        return criteriaCount;
    }

    function getCriteria(uint256 criteriaId)
        public view
        returns (
            address postedBy, string memory description,
            uint256 minCGPA_scaled, uint256 minCourseGrade,
            uint256 courseIndex, uint256 minCredits,
            bool requireAllPass, uint256 deadline, bool active
        )
    {
        Criteria memory c = criteriaList[criteriaId];
        require(c.criteriaId != 0, "Criteria not found");
        return (c.postedBy, c.description, c.minCGPA_scaled,
                c.minCourseGrade, c.courseIndex, c.minCredits,
                c.requireAllPass, c.deadline, c.active);
    }

    function getTotalCriteria() public view returns (uint256) {
        return criteriaCount;
    }

    // ── Phase 3: PROVE ───────────────────────────────────────────────────

    // ── Internal helpers to avoid stack-too-deep in submitProof ────────────

    function _verifyCommitment(
        address          student,
        uint256          cgpa_scaled,
        uint256[] calldata marks,
        uint256[] calldata credits,
        bytes32          salt
    ) internal view {
        bytes32 recomputed = keccak256(abi.encodePacked(
            cgpa_scaled, marks, credits, salt
        ));
        require(recomputed == commitments[student].commitment,
                "Commitment mismatch");
    }

    function _calcPassedCredits(
        uint256[] calldata marks,
        uint256[] calldata credits
    ) internal pure returns (uint256 passedCredits) {
        for (uint256 i = 0; i < marks.length; i++) {
            if (marks[i] >= PASS_MARK) passedCredits += credits[i];
        }
    }

    function _allPassed(uint256[] calldata marks)
        internal pure returns (bool)
    {
        for (uint256 i = 0; i < marks.length; i++) {
            if (marks[i] < PASS_MARK) return false;
        }
        return true;
    }

    function _checkCriteria(
        uint256          criteriaId,
        uint256          cgpa_scaled,
        uint256[] calldata marks,
        uint256[] calldata credits
    ) internal view returns (bool) {
        Criteria memory c = criteriaList[criteriaId];
        bool cgpaOk    = cgpa_scaled >= c.minCGPA_scaled;
        bool courseOk  = marks[c.courseIndex] >= c.minCourseGrade;
        bool creditsOk = _calcPassedCredits(marks, credits) >= c.minCredits;
        bool passOk    = c.requireAllPass ? _allPassed(marks) : true;
        return cgpaOk && courseOk && creditsOk && passOk;
    }

    function submitProof(
        uint256          criteriaId,
        uint256          cgpa_scaled,
        uint256[] calldata marks,
        uint256[] calldata credits,
        bytes32          salt
    ) public returns (bool verified) {
        address student = msg.sender;

        require(rbacContract.hasRole(student, RBAC.Role.STUDENT),
                "Only students can submit proofs");

        TranscriptCommitment storage tc = commitments[student];
        require(tc.exists,                          "No commitment found");
        require(marks.length   == tc.courseCount,   "marks length mismatch");
        require(credits.length == tc.courseCount,   "credits length mismatch");

        Criteria storage c = criteriaList[criteriaId];
        require(c.active,                               "Criteria not active");
        require(block.timestamp <= c.deadline,          "Deadline passed");
        require(!proofs[criteriaId][student].submitted, "Already submitted");
        require(c.courseIndex < marks.length,           "courseIndex out of range");

        // Verify commitment then check criteria (split into helpers)
        _verifyCommitment(student, cgpa_scaled, marks, credits, salt);
        verified = _checkCriteria(criteriaId, cgpa_scaled, marks, credits);

        proofs[criteriaId][student] = ProofRecord({
            submitted:   true,
            verified:    verified,
            submittedAt: block.timestamp
        });

        if (verified) eligibleStudents[criteriaId].push(student);

        emit ProofSubmitted(criteriaId, student, verified);
    }

    // ── Phase 4: VERIFY ──────────────────────────────────────────────────

    function checkEligibility(uint256 criteriaId, address student)
        public view returns (bool)
    {
        return proofs[criteriaId][student].verified;
    }

    function getEligibleStudents(uint256 criteriaId)
        public view returns (address[] memory)
    {
        return eligibleStudents[criteriaId];
    }

    function getProofStatus(uint256 criteriaId, address student)
        public view
        returns (bool submitted, bool verified, uint256 submittedAt)
    {
        ProofRecord memory p = proofs[criteriaId][student];
        return (p.submitted, p.verified, p.submittedAt);
    }

    // ── Helpers ──────────────────────────────────────────────────────────

    function computeCommitment(
        uint256          cgpa_scaled,
        uint256[] calldata marks,
        uint256[] calldata credits,
        bytes32          salt
    ) public pure returns (bytes32) {
        return keccak256(abi.encodePacked(cgpa_scaled, marks, credits, salt));
    }

    function computeCGPA(
        uint256[] calldata marks,
        uint256[] calldata credits
    ) public pure returns (uint256 cgpa_scaled) {
        require(marks.length == credits.length, "Length mismatch");
        uint256 totalWeighted = 0;
        uint256 totalCredits  = 0;
        for (uint256 i = 0; i < marks.length; i++) {
            totalWeighted += _marksToGP(marks[i]) * credits[i];
            totalCredits  += credits[i];
        }
        if (totalCredits == 0) return 0;
        return totalWeighted / totalCredits;
    }

    function _marksToGP(uint256 m) internal pure returns (uint256) {
        if (m >= 80) return GP_APLUS;
        if (m >= 75) return GP_A;
        if (m >= 70) return GP_AMINUS;
        if (m >= 65) return GP_BPLUS;
        if (m >= 60) return GP_B;
        if (m >= 55) return GP_BMINUS;
        if (m >= 50) return GP_CPLUS;
        if (m >= 45) return GP_C;
        if (m >= 40) return GP_D;
        return GP_F;
    }
}
