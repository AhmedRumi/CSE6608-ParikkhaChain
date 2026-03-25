"""
ParikkhaChain - Student Result Viewer
100% blockchain-driven via ResultAudit contract functions.

Contract functions used:
  RBAC.getRole(address)                               -> role verification
  ResultAudit.getFullTranscript(studentAddr)          -> all courses + marks
  ResultAudit.getStudentExamResult(examId, studentAddr) -> single exam result
  ResultAudit.getAuditTrail(scriptId)                 -> admin only
  HashRegistry.revealStudent(scriptId)                -> admin only, identity
  ExamLifecycle.getExamDetails(examId)                -> course name + credits

From Remix IDE call directly:
  getFullTranscript(studentAddress)         -- student or admin
  getStudentExamResult(examId, address)     -- student or admin
  getAuditTrail(scriptId)                   -- admin only
"""

import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

import contract_config as config
from blockchain_interface import BlockchainInterface
from grading_rules import get_grade_summary, calculate_cgpa
from generate_transcript_pdf import generate_from_view_result

PROJECT_ROOT = Path(__file__).parent.parent

ROLE_ADMIN   = 1
ROLE_STUDENT = 4

GRADE_STATUS = {
    0: "NOT_SUBMITTED",
    1: "SUBMITTED",
    2: "UNDER_SCRUTINY",
    3: "SCRUTINIZED",
    4: "FINALIZED",
}


# ─── Connect ──────────────────────────────────────────────────────────────────

def connect():
    config.load_addresses_from_file()
    bc = BlockchainInterface()
    w3 = bc.web3

    def ctr(name):
        return w3.eth.contract(
            address=w3.to_checksum_address(config.CONTRACT_ADDRESSES[name]),
            abi=config.load_abi(name),
        )

    return w3, {
        "rbac":   ctr("RBAC"),
        "exam":   ctr("ExamLifecycle"),
        "hash":   ctr("HashRegistry"),
        "result": ctr("ResultAudit"),
    }


# ─── Step 1 — Verify caller on-chain ─────────────────────────────────────────

def verify_caller(w3, contracts):
    """
    Ask who is calling. Verify role on-chain.
    Admin can query any student. Student can only query themselves.
    Returns (role_int, caller_addr, target_addr).
    """
    rbac = contracts["rbac"]

    print("\n  Who are you?")
    print("  [1] Admin")
    print("  [2] Student")
    while True:
        choice = input("  Enter 1 or 2: ").strip()
        if choice in ("1", "2"):
            break

    caller_raw = input("\n  Enter YOUR wallet address: ").strip()
    try:
        caller_addr = w3.to_checksum_address(caller_raw)
    except Exception:
        print("❌ Invalid wallet address.")
        sys.exit(1)

    # Use hasRole() for accurate multi-role check
    is_admin   = rbac.functions.hasRole(caller_addr, ROLE_ADMIN).call()
    is_student = rbac.functions.hasRole(caller_addr, ROLE_STUDENT).call()

    if choice == "1":
        if not is_admin:
            print(f"❌ {caller_addr} does not have ADMIN role on blockchain.")
            sys.exit(1)
        print(f"\n  ✅ Admin verified on blockchain")

        target_raw = input("\n  Enter STUDENT wallet address to look up: ").strip()
        try:
            target_addr = w3.to_checksum_address(target_raw)
        except Exception:
            print("❌ Invalid student address.")
            sys.exit(1)

        target_is_student = rbac.functions.hasRole(target_addr, ROLE_STUDENT).call()
        if not target_is_student:
            print(f"❌ {target_addr} does not have STUDENT role.")
            sys.exit(1)

        return ROLE_ADMIN, caller_addr, target_addr

    else:
        if not is_student:
            print(f"❌ {caller_addr} does not have STUDENT role on blockchain.")
            sys.exit(1)
        print(f"\n  ✅ Student verified on blockchain")
        return ROLE_STUDENT, caller_addr, caller_addr


# ─── Step 2 — Fetch full transcript from blockchain ──────────────────────────

def _fetch_exam_details(contracts, exam_id, fallback_course_code=""):
    """
    Fetch exam name and course code from ExamLifecycle.getExamDetails(examId).
    Returns safe defaults if call fails or examId is 0.
    """
    if exam_id == 0:
        return {
            "exam_name":   "Unknown Exam",
            "course_code": fallback_course_code or "N/A",
            "credits":     3,
        }
    try:
        det = contracts["exam"].functions.getExamDetails(exam_id).call()
        # getExamDetails returns (examName, courseCode, examDate, state, createdBy)
        return {
            "exam_name":   det[0] if det[0] else f"Exam {exam_id}",
            "course_code": det[1] if det[1] else fallback_course_code or "N/A",
            "credits":     3,   # credits not stored on-chain; default 3
        }
    except Exception:
        return {
            "exam_name":   f"Exam {exam_id}",
            "course_code": fallback_course_code or "N/A",
            "credits":     3,
        }


def fetch_full_transcript(contracts, caller_addr, student_addr):
    """
    Calls ResultAudit.getFullTranscript(studentAddress).
    Enriches each result with course name + credits from ExamLifecycle.
    Returns list of course result dicts. Empty list if no marks on-chain yet.
    """
    print(f"\n  📡 Calling ResultAudit.getFullTranscript({student_addr[:12]}...)")
    print(f"     from: {caller_addr[:12]}...")

    try:
        result = contracts["result"].functions.getFullTranscript(
            student_addr
        ).call({"from": caller_addr})
    except Exception as e:
        err = str(e)
        if "No scripts found" in err:
            print("  ⚠️  No scripts registered for this student yet.")
            print("      Has the exam workflow been run (Step 4 — script registration)?")
        elif "not a registered student" in err.lower():
            print("  ⚠️  This address does not have STUDENT role on blockchain.")
        else:
            print(f"  ⚠️  getFullTranscript returned: {err[:120]}")
        return []

    script_ids, exam_ids, course_codes, marks_obtained, \
        total_marks, statuses, has_scrutiny = result

    if not script_ids:
        print("  ⚠️  No results found for this student on blockchain.")
        return []

    # Enrich with exam details (course name, credits) from ExamLifecycle
    exam_detail_cache = {}

    courses = []
    for i in range(len(script_ids)):
        eid = exam_ids[i]

        # Cache exam details — fetch from ExamLifecycle by examId
        if eid not in exam_detail_cache:
            exam_detail_cache[eid] = _fetch_exam_details(contracts, eid, course_codes[i])

        det    = exam_detail_cache[eid]
        status = statuses[i]

        # Use course_code from contract return first; fall back to ExamLifecycle
        final_code = course_codes[i] if course_codes[i] and course_codes[i] != "N/A"                      else det["course_code"]

        # Fetch individual examiner marks from blockchain
        ex1_marks = ex2_marks = "—"
        sid = script_ids[i]
        if status >= 1:   # only if marks were submitted
            try:
                r1 = contracts["result"].functions.getExaminer1Progress(sid).call()
                # returns (submitted, marksGiven, examinerAddr)
                if r1[0]:
                    ex1_marks = r1[1]
            except Exception:
                pass
            try:
                r2 = contracts["result"].functions.getExaminer2Progress(sid).call()
                # returns (submitted, marksGiven, examinerAddr, combinedTotal, bothSubmitted)
                if r2[0]:
                    ex2_marks = r2[1]
            except Exception:
                pass

        courses.append({
            "script_id":       sid,
            "exam_id":         eid,
            "exam_name":       det["exam_name"],
            "course_code":     final_code,
            "credits":         det["credits"],
            "marks_obtained":  marks_obtained[i],
            "total_marks":     total_marks[i],
            "examiner1_marks": ex1_marks,
            "examiner2_marks": ex2_marks,
            "status_int":      status,
            "status":          GRADE_STATUS.get(status, str(status)),
            "finalized":       status == 4,
            "has_scrutiny":    has_scrutiny[i],
            "has_marks":       status >= 1,
        })

    submitted = sum(1 for c in courses if c["has_marks"])
    print(f"  ✅ {len(courses)} script(s) found | {submitted} with marks submitted")
    return courses


# ─── Step 3 — Scope selection ─────────────────────────────────────────────────

def select_scope(courses):
    """Let user pick one course or all. Shows which have marks and which don't."""
    if not courses:
        return []

    print(f"\n  [0] ALL courses (full CGPA report)")
    for i, c in enumerate(courses, 1):
        if c["has_marks"]:
            status_icon = "✅" if c["finalized"] else "⏳"
            marks_str   = f"{c['marks_obtained']}/{c['total_marks']}"
        else:
            status_icon = "❌"
            marks_str   = "no marks yet"
        print(f"  [{i}] {c['course_code']:<12} "
              f"{c['exam_name'][:28]:<28}  "
              f"{marks_str:<12} "
              f"{status_icon} {c['status']}")

    while True:
        try:
            choice = int(input("\n  Select: ").strip())
            if choice == 0:
                return courses
            if 1 <= choice <= len(courses):
                return [courses[choice - 1]]
        except ValueError:
            pass
        print("  ⚠️  Invalid choice")


# ─── Step 4 — Audit trail & identity (admin only) ────────────────────────────

def fetch_audit(contracts, script_id, caller_addr):
    """ResultAudit.getAuditTrail(scriptId) — admin only on-chain."""
    try:
        trail = contracts["result"].functions.getAuditTrail(
            script_id
        ).call({"from": caller_addr})
        return [
            {
                # AuditEntry fields (scriptId removed):
                # [0]=oldMarks [1]=newMarks [2]=changedBy [3]=reason [4]=timestamp [5]=changeType
                "old_marks":   e[0],
                "new_marks":   e[1],
                "changed_by":  e[2],
                "reason":      e[3],
                "timestamp":   datetime.fromtimestamp(e[4]).strftime("%Y-%m-%d %H:%M:%S"),
                "change_type": e[5],
            }
            for e in trail
        ]
    except Exception:
        return []


def fetch_identity(contracts, script_id, caller_addr):
    """HashRegistry.revealStudent(scriptId) — admin only on-chain."""
    try:
        r = contracts["hash"].functions.revealStudent(script_id).call(
            {"from": caller_addr}
        )
        return {"name": r[1], "student_id": r[2]}
    except Exception:
        return None


def fetch_own_identity(contracts, student_addr, caller_addr):
    """
    HashRegistry.getMyIdentity(studentAddress)
    Student calls with their own address — returns name + student_id from blockchain.
    Admin can also call for any student.
    Falls back to revealStudent via first script if getMyIdentity not available.
    """
    try:
        r = contracts["hash"].functions.getMyIdentity(student_addr).call(
            {"from": caller_addr}
        )
        # returns (studentAddress, studentName, studentId, courseCode)
        return {"name": r[1], "student_id": r[2]}
    except Exception:
        # Fallback: use revealStudent on first available script
        try:
            scripts = contracts["hash"].functions.getStudentScripts(
                student_addr
            ).call()
            if scripts:
                r = contracts["hash"].functions.revealStudent(scripts[0]).call(
                    {"from": caller_addr}
                )
                return {"name": r[1], "student_id": r[2]}
        except Exception:
            pass
    return None


# ─── Display result card ──────────────────────────────────────────────────────

def display(role, caller_addr, student_addr, scope, contracts):
    W   = 70
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not scope:
        print("\n  ⚠️  No results to display.")
        return

    # Admin: fetch audit trail and identity
    audit_map = {}
    identity  = None
    if role == ROLE_ADMIN:
        for c in scope:
            if c["has_marks"]:
                audit_map[c["script_id"]] = fetch_audit(
                    contracts, c["script_id"], caller_addr
                )
        # Reveal identity from first script that has marks
        first_with_marks = next((c for c in scope if c["has_marks"]), None)
        if first_with_marks:
            identity = fetch_identity(
                contracts, first_with_marks["script_id"], caller_addr
            )

    # ── Header ────────────────────────────────────────────────────────────
    print("\n")
    print("╔" + "═" * W + "╗")
    print("║" + "PARIKKHCHAIN — OFFICIAL RESULT TRANSCRIPT".center(W) + "║")
    print("╠" + "═" * W + "╣")

    if identity:
        print("║" + f"  Student : {identity['name']}".ljust(W) + "║")
        print("║" + f"  ID/Roll : {identity['student_id']}".ljust(W) + "║")

    print("║" + f"  Address : {student_addr}".ljust(W) + "║")
    print("║" + f"  Date    : {now}".ljust(W) + "║")
    print("║" + f"  Source  : ResultAudit.getFullTranscript() on blockchain".ljust(W) + "║")

    # ── Course results ────────────────────────────────────────────────────
    print("╠" + "═" * W + "╣")
    print("║" + "COURSE-WISE RESULTS".center(W) + "║")
    print("╠" + "═" * W + "╣")
    print("║ " + f"{'Code':<12} {'Exam':<22} {'Marks':>8}  "
          f"{'Grade':<6} {'GP':>5}  {'Status':<14} {'S'}" + " ║")
    print("║" + "─" * W + "║")

    course_data = []
    for c in scope:
        if c["has_marks"]:
            gi      = get_grade_summary(c["marks_obtained"])
            m_str   = f"{c['marks_obtained']}/{c['total_marks']}"
            grade   = gi["letter_grade"]
            gp_str  = f"{gi['grade_point']:.2f}"
            sc_flag = "✓" if c["has_scrutiny"] else " "
            status  = c["status"]
        else:
            m_str   = "—/—"
            grade   = "—"
            gp_str  = "—"
            sc_flag = " "
            status  = "NOT SUBMITTED"

        print("║ " + (
            f"{c['course_code']:<12} "
            f"{c['exam_name'][:22]:<22} "
            f"{m_str:>8}  "
            f"{grade:<6} "
            f"{gp_str:>5}  "
            f"{status:<14} "
            f"{sc_flag}"
        ) + " ║")

        if c["has_marks"]:
            course_data.append({
                "course":  c["course_code"],
                "marks":   c["marks_obtained"],
                "credits": c["credits"],
            })

    print("╠" + "═" * W + "╣")

    # ── CGPA ──────────────────────────────────────────────────────────────
    if course_data:
        cgpa = calculate_cgpa(course_data)
        if   cgpa >= 3.75: cls = "First Class with Distinction"
        elif cgpa >= 3.25: cls = "First Class"
        elif cgpa >= 3.00: cls = "Second Class"
        elif cgpa >= 2.00: cls = "Pass"
        else:              cls = "Fail"
        print("║" + f"  CGPA   : {cgpa:.2f} / 4.00  ({len(course_data)} course(s) with marks)".ljust(W) + "║")
        print("║" + f"  Class  : {cls}".ljust(W) + "║")

    no_marks = [c for c in scope if not c["has_marks"]]
    if no_marks:
        print("║" + f"  ⚠️  {len(no_marks)} course(s) have no marks submitted yet".ljust(W) + "║")

    print("╠" + "═" * W + "╣")

    # ── Finalization status ───────────────────────────────────────────────
    marked   = [c for c in scope if c["has_marks"]]
    fin_all  = marked and all(c["finalized"] for c in marked)
    note = "✅ All submitted results FINALIZED — immutable on blockchain" \
           if fin_all else "⏳ Results not yet finalized"
    print("║" + f"  {note}".ljust(W) + "║")

    # ── Script IDs ────────────────────────────────────────────────────────
    print("╠" + "═" * W + "╣")
    print("║" + "  Anonymous Script IDs (blockchain audit reference):".ljust(W) + "║")
    for c in scope:
        marks_note = f"  [{c['status']}]" if not c["has_marks"] else ""
        line = f"    {c['course_code']}: {c['script_id']}{marks_note}"
        print("║" + line.ljust(W) + "║")
    print("╚" + "═" * W + "╝")

    # ── Audit trail (admin only) ──────────────────────────────────────────
    if role == ROLE_ADMIN and any(audit_map.values()):
        print(f"\n{'─'*W}")
        print("  📜 AUDIT TRAIL  —  ResultAudit.getAuditTrail()  (Admin only)")
        print(f"{'─'*W}")
        for c in scope:
            trail = audit_map.get(c["script_id"], [])
            if not trail:
                continue
            print(f"\n  {c['course_code']}  —  script: {c['script_id']}")
            for j, e in enumerate(trail, 1):
                print(f"  [{j}] {e['change_type']:<10} "
                      f"{e['old_marks']:>3} → {e['new_marks']:>3} marks  "
                      f"{e['timestamp']}")
                print(f"       By     : {e['changed_by']}")
                print(f"       Reason : {e['reason']}")
        print(f"{'─'*W}")

    # ── Remix IDE tip ─────────────────────────────────────────────────────
    print(f"\n  💡 Same results available directly in Remix IDE:")
    print(f"     Contract : ResultAudit")
    print(f"     Function : getFullTranscript(\"{student_addr}\")")
    if len(scope) == 1 and scope[0]["has_marks"]:
        print(f"     Or       : getStudentExamResult({scope[0]['exam_id']}, \"{student_addr}\")")
    if role == ROLE_ADMIN:
        first = next((c for c in scope if c["has_marks"]), None)
        if first:
            print(f"     Audit    : getAuditTrail(\"{first['script_id']}\")")
    print(f"     ⚠️  Call from the correct address (admin or student wallet)")


# ─── PDF Transcript ───────────────────────────────────────────────────────────

def get_transcript(student_info, courses, student_addr):
    """Generate PDF transcript and save to transcripts/ folder."""
    print("\n  Generating PDF transcript...")

    # Merge address into student_info
    info = {**student_info, "address": student_addr}

    try:
        path = generate_from_view_result(info, courses)
        print(f"  ✅ Transcript saved: {path}")
        print(f"     Open it from your project folder:")
        print(f"     {path}")
        return path
    except Exception as e:
        print(f"  ❌ PDF generation failed: {e}")
        import traceback
        traceback.print_exc()
        return None


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 70)
    print("  PARIKKHCHAIN — STUDENT RESULT PORTAL")
    print("  Powered by ResultAudit.getFullTranscript() on blockchain")
    print("=" * 70)

    try:
        w3, contracts = connect()
    except Exception as e:
        print(f"\n❌ Cannot connect to blockchain: {e}")
        sys.exit(1)

    print(f"\n  ✅ Blockchain connected | Chain {w3.eth.chain_id} | Block {w3.eth.block_number}")

    role, caller_addr, student_addr = verify_caller(w3, contracts)

    courses = fetch_full_transcript(contracts, caller_addr, student_addr)

    if not courses:
        print("\n  No data to display. Check that:")
        print("    1. Scripts were registered (Step 4 of workflow)")
        print("    2. Marks were submitted (Step 5 of workflow)")
        print("    3. The correct student address was entered")
        return

    scope = select_scope(courses)

    display(role, caller_addr, student_addr, scope, contracts)

    # Offer PDF transcript
    print()
    if input("  Generate PDF transcript? (yes/no): ").strip().lower() == "yes":
        # Fetch identity from blockchain using wallet address
        # getMyIdentity() allows student to read their own data
        # revealStudent() is admin-only but fetch_own_identity tries both
        print("\n  Fetching identity from blockchain...")
        identity = fetch_own_identity(contracts, student_addr, caller_addr)

        if identity and identity.get("name") and identity["name"] != "—":
            print(f"  ✅ Identity confirmed: {identity['name']} ({identity['student_id']})")
        else:
            print("  ⚠️  Could not fetch identity from blockchain.")
            print("       Add getMyIdentity() to HashRegistry.sol (see HashRegistry_addition.sol)")
            print("       For now, enter your details manually:")
            name = input("  Full name  : ").strip()
            sid  = input("  Student ID : ").strip()
            identity = {
                "name":       name if name else "—",
                "student_id": sid  if sid  else "—",
            }

        get_transcript(identity, scope, student_addr)

    if input("\n  Look up another? (yes/no): ").strip().lower() == "yes":
        main()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Cancelled")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()