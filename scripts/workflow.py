"""
ParikkhaChain - Complete Workflow Automation (Single Exam Demo)
Demonstrates the entire examination lifecycle from creation to CGPA calculation
"""

import sys
import json
import random
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent))

from blockchain_interface import (
    BlockchainInterface,
    RBACInterface,
    ExamInterface,
    HashRegistryInterface,
    ResultAuditInterface
)
import contract_config as config
from grading_rules import get_grade_summary, calculate_cgpa


def print_section(title):
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70)


def print_step(step_num, description):
    print(f"\n{'─'*70}")
    print(f"STEP {step_num}: {description}")
    print(f"{'─'*70}")


# ═══════════════════════════════════════════════════════
# DEPLOYMENT VALIDATOR
# ═══════════════════════════════════════════════════════

def validate_deployment():
    """
    Verify all contracts are actually deployed and responsive on the
    current Ganache instance. Catches stale deployed_addresses.json
    from a previous Ganache session before any real work begins.
    """
    bc = BlockchainInterface()
    w3 = bc.web3

    checks = [
        ("RBAC",          "admin",       []),
        ("ExamLifecycle", "getTotalExams",   []),
        ("HashRegistry",  "scriptCount",     None),   # public var
        ("ResultAudit",   "getExamResultCount", [1]),
    ]

    all_ok = True
    print()
    for name, fn, args in checks:
        try:
            addr = config.CONTRACT_ADDRESSES.get(name)
            if not addr:
                print(f"   ❌ {name}: address missing in deployed_addresses.json")
                all_ok = False
                continue
            ctr = w3.eth.contract(
                address=w3.to_checksum_address(addr),
                abi=config.load_abi(name)
            )
            if args is None:
                # public state variable — just check bytecode exists
                code = w3.eth.get_code(w3.to_checksum_address(addr))
                if code == b"" or code == "0x":
                    raise Exception("no bytecode at address")
            else:
                ctr.functions[fn](*args).call()
            print(f"   ✅ {name} at {addr[:12]}... — responsive")
        except Exception as e:
            print(f"   ❌ {name} at {addr[:12] if addr else '?'}... — NOT RESPONDING")
            print(f"      Reason: {str(e)[:80]}")
            all_ok = False

    if not all_ok:
        print()
        print("  ─────────────────────────────────────────────────────")
        print("  One or more contracts are not reachable.")
        print("  This usually means Ganache was restarted and the old")
        print("  contract addresses are no longer valid.")
        print()
        print("  Fix:")
        print("    1. In Remix — redeploy all 4 contracts in order:")
        print("       RBAC → ExamLifecycle → HashRegistry → ResultAudit")
        print("    2. Run: python scripts/deploy_contracts.py")
        print("       (enter the new addresses from Remix)")
        print("  ─────────────────────────────────────────────────────")
        return False

    print("  All contracts verified on current chain ✅")
    return True


# ═══════════════════════════════════════════════════════
# STEP 0 — LOAD MOCK DATA
# ═══════════════════════════════════════════════════════

def load_mock_data():
    print_step("0", "Loading Mock Data")

    mock_data_file = Path(__file__).parent.parent / "mock_data" / "complete_mock_data.json"

    if not mock_data_file.exists():
        print("❌ Mock data not found!")
        print("   Please run: python generate_mock_data.py")
        sys.exit(1)

    with open(mock_data_file, 'r') as f:
        data = json.load(f)

    print(f"✅ Loaded mock data:")
    print(f"   Students: {len(data['students'])}")
    print(f"   Exams: {len(data['exams'])}")
    print(f"   Marks records: {sum(len(e['student_marks']) for e in data['marks'])}")

    return data


# ═══════════════════════════════════════════════════════
# STEP 1 — SETUP & ROLES
# ═══════════════════════════════════════════════════════

def step1_setup_and_roles(mock_data):
    print_step("1", "Setup & Role Assignment")

    config.load_addresses_from_file()
    rbac     = RBACInterface()
    accounts = rbac.get_accounts()
    admin    = accounts[0]

    # ── Read account layout — config file OR mock data (converter sets both) ──
    cfg_file   = Path(__file__).parent.parent / "parikkhchain_config.json"
    mock_file  = Path(__file__).parent.parent / "mock_data" / "complete_mock_data.json"

    if cfg_file.exists():
        with open(cfg_file) as f:
            cfg = json.load(f)
    elif mock_file.exists():
        # Fallback: converter saves config_snapshot inside mock data
        print("  ℹ️  parikkhchain_config.json not found — reading from complete_mock_data.json")
        with open(mock_file) as f:
            md = json.load(f)
        cfg = md.get("config_snapshot", md)
    else:
        print("❌ Neither parikkhchain_config.json nor complete_mock_data.json found.")
        print("   Run: python scripts/convert_mock_data.py")
        sys.exit(1)

    layout = cfg["account_layout"]
    total_needed = layout["total_needed"]
    if len(accounts) < total_needed:
        print(f"❌ Config requires {total_needed} accounts but Ganache has {len(accounts)}.")
        print(f"   Restart Ganache with: ganache --accounts {total_needed + 2} --deterministic --database.dbPath ./ganache-db")
        sys.exit(1)

    # Build examiner / scrutinizer / student address lists from live accounts
    examiner_addrs    = [accounts[i] for i in layout["examiner_indices"]]
    scrutinizer_addrs = [accounts[i] for i in layout["scrutinizer_indices"]]
    student_addrs     = [accounts[i] for i in layout["student_indices"]]

    # ── Refresh ALL addresses from live Ganache accounts ─────────────────
    # This makes the workflow work with both --deterministic AND random
    # Ganache starts. account_index is the source of truth — not the
    # stored address strings.
    print("\n  🔄 Refreshing addresses from live Ganache accounts...")

    def refresh(obj):
        """Update address field using account_index from live Ganache."""
        if isinstance(obj, dict):
            idx = obj.get("account_index")
            if idx is not None and idx < len(accounts):
                obj["address"] = accounts[idx]

    # Students
    for st in mock_data["students"]:
        refresh(st)

    # Examiners + scrutinizers at top level
    for ex in mock_data.get("examiners", []):
        refresh(ex)
    for sc in mock_data.get("scrutinizers", []):
        refresh(sc)

    # Per-exam examiner/scrutinizer lists
    for ex_list in mock_data.get("exam_examiners", {}).values():
        for ex in ex_list:
            refresh(ex)
    for sc_list in mock_data.get("exam_scrutinizers", {}).values():
        for sc in sc_list:
            refresh(sc)
    for st_list in mock_data.get("exam_students", {}).values():
        for st in st_list:
            refresh(st)

    # Marks — sync student_address by student_id
    stu_addr_map = {s["student_id"]: s["address"] for s in mock_data["students"]}
    for exam_marks in mock_data["marks"]:
        for sm in exam_marks["student_marks"]:
            sid = sm.get("student_id")
            if sid and sid in stu_addr_map:
                sm["student_address"] = stu_addr_map[sid]
            # Sync examiner addresses in marks too
            ex1_name = sm.get("examiner1_name")
            ex2_name = sm.get("examiner2_name")
            for ex in mock_data.get("examiners", []):
                if ex["name"] == ex1_name:
                    sm["examiner1_address"] = ex["address"]
                if ex["name"] == ex2_name:
                    sm["examiner2_address"] = ex["address"]

    print(f"  ✅ Addresses refreshed from {len(accounts)} live Ganache accounts")

    roles = {
        "admin":             admin,
        "examiner":          examiner_addrs[0],
        "scrutinizer":       scrutinizer_addrs[0],
        "examiner_addrs":    examiner_addrs,
        "scrutinizer_addrs": scrutinizer_addrs,
        "students":          student_addrs,
    }

    print(f"\n👥 Account mapping:")
    print(f"   Admin:       {admin}")
    for i, (e, cfg_e) in enumerate(zip(examiner_addrs, cfg["examiners"]), 1):
        print(f"   Examiner {i}:  {e}  ({cfg_e['name']})")
    for i, (s, cfg_s) in enumerate(zip(scrutinizer_addrs, cfg["scrutinizers"]), 1):
        print(f"   Scrutinizer {i}: {s}  ({cfg_s['name']})")
    for i, (s, cfg_s) in enumerate(zip(student_addrs, cfg["students"]), 1):
        print(f"   Student {i}:   {s}  ({cfg_s['name']})")

    print("\n🔑 Assigning roles...")

    def grant_safe(address, role_name):
        # Use has_role() instead of get_role() so multi-role addresses
        # are checked correctly — get_role() only returns the primary role
        if rbac.has_role(address, config.ROLES.get(role_name, 0)):
            print(f"   ℹ️  {role_name} already assigned to {address[:10]}...")
        else:
            rbac.grant_role(address, role_name, admin)
            print(f"   ✅ {role_name} → {address[:10]}...")

    for addr in examiner_addrs:
        grant_safe(addr, "EXAMINER")
    for addr in scrutinizer_addrs:
        grant_safe(addr, "SCRUTINIZER")
    for addr in student_addrs:
        grant_safe(addr, "STUDENT")

    # Multi-role: grant SCRUTINIZER to any examiner who also scrutinizes an exam.
    # With bitmask RBAC this is additive — EXAMINER role is not overwritten.
    all_exam_scrutinizer_addrs = set()
    for sc_list in mock_data.get("exam_scrutinizers", {}).values():
        for sc in sc_list:
            addr = sc.get("address", "")
            if addr:
                all_exam_scrutinizer_addrs.add(addr)
    for addr in all_exam_scrutinizer_addrs:
        if addr not in scrutinizer_addrs:
            # This faculty is primarily an examiner but also scrutinizes — grant both
            current_bits = rbac.get_role_bits(addr) if hasattr(rbac, 'get_role_bits') else 0
            print(f"   🔑 Granting additional SCRUTINIZER role to {addr[:12]}... (multi-role)")
            rbac.grant_role(addr, "SCRUTINIZER", admin)


    print("\n✅ Step 1 Complete: All roles assigned")
    return roles


# ═══════════════════════════════════════════════════════
# STEP 2 — CREATE EXAM
# ═══════════════════════════════════════════════════════

def step2_create_exam(mock_data, roles, exam_index):
    exam_data     = mock_data['exams'][exam_index]
    print_step("2", f"Create Exam [{exam_index+1}/{len(mock_data['exams'])}]: {exam_data['name']}")

    exam_iface    = ExamInterface()
    admin         = roles['admin']
    exam_contract = exam_iface.get_contract("ExamLifecycle")

    print(f"\n📝 Creating: {exam_data['name']}")
    print(f"   Course: {exam_data['course_code']}")

    count_before = exam_contract.functions.getTotalExams().call()
    future_date  = int((datetime.now() + timedelta(days=30 + exam_index * 7)).timestamp())

    receipt = exam_iface.create_exam(
        name         = exam_data['name'],
        course_code  = exam_data['course_code'],
        exam_date    = future_date,
        from_account = admin
    )

    count_after = exam_contract.functions.getTotalExams().call()

    if count_after > count_before:
        exam_id = count_after
        print(f"\n✅ Exam created — On-chain ID: {exam_id}")
    else:
        print(f"\n❌ Exam creation FAILED for {exam_data['name']}")
        return None

    exam_iface.update_exam_state(exam_id, "ACTIVE", admin)
    print(f"   ✅ Exam {exam_id} set to ACTIVE")
    return exam_id




# ═══════════════════════════════════════════════════════
# STEP 2b — ASSIGN EXAMINER & SCRUTINIZER TO EXAM
# ═══════════════════════════════════════════════════════

def step2b_assign_to_exam(exam_id, roles, mock_data, exam_index):
    """Assign the configured examiners and scrutinizers to this specific exam."""
    print_step("2b", f"Assign Examiners & Scrutinizers to Exam {exam_id}")

    base          = BlockchainInterface()
    rbac_contract = base.web3.eth.contract(
        address = base.web3.to_checksum_address(config.CONTRACT_ADDRESSES["RBAC"]),
        abi     = config.load_abi("RBAC")
    )
    admin = roles["admin"]

    # Get per-exam lists from mock data
    key = str(exam_index)
    examiners_for_exam    = mock_data.get("exam_examiners",    {}).get(key, [])
    scrutinizers_for_exam = mock_data.get("exam_scrutinizers", {}).get(key, [])

    # Fallback to roles if mock data doesn't have per-exam lists
    if not examiners_for_exam:
        examiners_for_exam = [{"address": roles["examiner"], "name": "Examiner"}]
    if not scrutinizers_for_exam:
        scrutinizers_for_exam = [{"address": roles["scrutinizer"], "name": "Scrutinizer"}]

    print(f"\n🔑 Assigning examiners to Exam {exam_id}...")
    for ex in examiners_for_exam:
        addr = ex["address"]
        name = ex.get("name", addr[:10])
        try:
            tx = rbac_contract.functions.assignExaminerToExam(
                addr, exam_id
            ).transact({"from": admin})
            base.web3.eth.wait_for_transaction_receipt(tx)
            print(f"   ✅ {name} assigned as examiner for Exam {exam_id}")
        except Exception as e:
            if "already assigned" in str(e):
                print(f"   ℹ️  {name} already assigned to Exam {exam_id}")
            else:
                print(f"   ❌ Failed to assign {name}: {e}")

    print(f"\n🔑 Assigning scrutinizers to Exam {exam_id}...")
    for sc in scrutinizers_for_exam:
        addr = sc["address"]
        name = sc.get("name", addr[:10])
        try:
            tx = rbac_contract.functions.assignScrutinizerToExam(
                addr, exam_id
            ).transact({"from": admin})
            base.web3.eth.wait_for_transaction_receipt(tx)
            print(f"   ✅ {name} assigned as scrutinizer for Exam {exam_id}")
        except Exception as e:
            if "already assigned" in str(e):
                print(f"   ℹ️  {name} already assigned to Exam {exam_id}")
            else:
                print(f"   ❌ Failed to assign {name}: {e}")

    print(f"\n✅ Step 2b Complete — only assigned staff can act on Exam {exam_id}")

# ═══════════════════════════════════════════════════════
# STEP 3 — ENROLL STUDENTS
# ═══════════════════════════════════════════════════════

def step3_enroll_students(exam_id, mock_data, roles, exam_index):
    print_step("3", f"Enroll Students in Exam {exam_id}")

    exam_iface = ExamInterface()
    admin      = roles['admin']

    # exam_students["0"], ["1"] etc. — list of student dicts for each exam
    key      = str(exam_index)
    students = mock_data.get("exam_students", {}).get(key) or mock_data["students"]

    print(f"\n👨‍🎓 Enrolling {len(students)} students in Exam {exam_id}...")

    for student in students:
        receipt = exam_iface.enroll_student(
            exam_id         = exam_id,
            student_address = student['address'],
            from_account    = admin
        )
        if receipt:
            print(f"   ✅ {student['name']} ({student['student_id']})")
        else:
            print(f"   ❌ Failed: {student['name']}")

    print(f"\n✅ Step 3 Complete — {len(students)} students enrolled")
    return students

# ═══════════════════════════════════════════════════════
# STEP 4 — REGISTER SCRIPTS (ANONYMIZATION)
# ═══════════════════════════════════════════════════════

def step4_register_scripts(exam_id, mock_data, roles, exam_index, enrolled_students):
    print_step("4", f"Script Registration — Anonymization (Exam {exam_id})")

    hash_iface    = HashRegistryInterface()
    admin         = roles['admin']
    exam_data     = mock_data['exams'][exam_index]
    hash_contract = hash_iface.get_contract("HashRegistry")

    unique_course_code = exam_data['course_code'] + "_E" + str(exam_id)

    print(f"\n📄 Replacing topsheets with anonymous script IDs...")
    print(f"   Course tag: {unique_course_code} (unique per exam run)")

    for student in enrolled_students:
        receipt = hash_iface.register_script(
            exam_id         = exam_id,
            student_address = student['address'],
            student_name    = student['name'],
            student_id      = student['student_id'],
            course_code     = unique_course_code,
            from_account    = admin
        )
        if not receipt:
            print(f"   ❌ Failed to register script for {student['name']}")

    script_ids = hash_contract.functions.getExamScripts(exam_id).call()

    if not script_ids:
        print(f"\n❌ No scripts registered on blockchain.")
        return []

    print(f"\n   📋 Script IDs from blockchain:")
    for sid in script_ids:
        print(f"      • {sid}")

    print(f"\n✅ Step 4 Complete — {len(script_ids)} scripts anonymized")
    return script_ids


# ═══════════════════════════════════════════════════════
# STEP 5 — EXAMINER SUBMITS MARKS
# ═══════════════════════════════════════════════════════

def step5_submit_marks(exam_id, script_ids, mock_data, roles, exam_index=0):
    print_step("5", "Dual-Examiner Marks Submission (each out of 50 → total 100)")

    exam_iface   = ExamInterface()
    result_iface = ResultAuditInterface()
    admin        = roles['admin']
    exam_marks   = mock_data['marks'][exam_index]

    # Must have exactly 2 examiners assigned to this exam
    key               = str(exam_index)
    assigned_examiners = mock_data.get("exam_examiners", {}).get(key, [])

    if len(assigned_examiners) < 2:
        print(f"\n❌ Exam {exam_id} needs exactly 2 assigned examiners, "
              f"found {len(assigned_examiners)}.")
        print(f"   Re-run setup_config.py and assign 2 examiners per exam.")
        return

    ex1 = assigned_examiners[0]
    ex2 = assigned_examiners[1]
    print(f"\n   Examiner 1: {ex1['name']} ({ex1['address'][:12]}...)")
    print(f"   Examiner 2: {ex2['name']} ({ex2['address'][:12]}...)")

    # Transition to EVALUATION
    exam_iface.update_exam_state(exam_id, "EVALUATION", admin)

    print(f"\n👨‍🏫 Both examiners submitting marks out of 50 each...\n")

    for i, script_id in enumerate(script_ids):
        sm            = exam_marks['student_marks'][i]
        total_initial = sm['initial_marks']   # 0-100 from mock data

        # Use pre-split marks from mock data (generated by generate_mock_data.py)
        ex1_marks = min(sm.get("examiner1_marks", total_initial // 2), 50)
        ex2_marks = min(sm.get("examiner2_marks", total_initial - total_initial // 2), 50)

        print(f"   📝 {script_id}:")
        print(f"      {ex1['name'][:30]}: {ex1_marks}/50")

        r1 = result_iface.submit_marks(
            script_id      = script_id,
            marks_obtained = ex1_marks,
            total_marks    = 50,
            from_account   = ex1['address']
        )
        if not r1:
            print(f"      ❌ Examiner 1 submission failed")
            continue

        print(f"      {ex2['name'][:30]}: {ex2_marks}/50")

        r2 = result_iface.submit_marks(
            script_id      = script_id,
            marks_obtained = ex2_marks,
            total_marks    = 50,
            from_account   = ex2['address']
        )
        if r2:
            print(f"      ✅ Combined: {ex1_marks + ex2_marks}/100")
        else:
            print(f"      ❌ Examiner 2 submission failed")

    print(f"\n✅ Step 5 Complete")


# ═══════════════════════════════════════════════════════
# STEP 6 — SCRUTINY
# ═══════════════════════════════════════════════════════

def step6_scrutiny(exam_id, script_ids, mock_data, roles, exam_index=0):
    print_step("6", "Scrutiny — Scrutinizer Reviews Scripts")

    exam_iface   = ExamInterface()
    result_iface = ResultAuditInterface()
    admin        = roles['admin']
    exam_marks   = mock_data['marks'][exam_index]

    # Use the scrutinizer ASSIGNED to this specific exam (from mock data)
    key = str(exam_index)
    assigned_scrutinizers = mock_data.get("exam_scrutinizers", {}).get(key, [])
    if assigned_scrutinizers:
        scrutinizer = assigned_scrutinizers[0]["address"]
        print(f"\n   Using assigned scrutinizer: {assigned_scrutinizers[0]['name']} ({scrutinizer[:12]}...)")
    else:
        scrutinizer = roles['scrutinizer']
        print(f"\n   Using default scrutinizer: {scrutinizer[:12]}...")

    scrutiny_reasons = [
        "Re-evaluated Question 3, gave partial credit for correct approach",
        "Checked calculation in Question 5, found minor error in marking",
        "Reviewed diagram in Question 2, awarded additional points for accuracy",
        "Re-assessed answer quality, gave benefit of doubt on borderline answer",
        "Found missed marks in Question 4, answer was partially correct",
        "Rechecked Question 6, awarded marks for alternative valid method",
    ]

    # Transition to SCRUTINY
    exam_iface.update_exam_state(exam_id, "SCRUTINY", admin)

    print(f"\n🔍 Scrutinizer reviewing scripts (sees only script IDs)...\n")

    # Randomly pick 1 or 2 scripts to change
    num_to_change   = random.randint(1, min(2, len(script_ids)))
    scripts_to_change = set(random.sample(range(len(script_ids)), num_to_change))
    scrutiny_count  = 0

    for idx, script_id in enumerate(script_ids):
        sm            = exam_marks['student_marks'][idx]
        initial_marks = sm['initial_marks']

        if idx in scripts_to_change:
            change    = random.randint(1, 7)
            new_marks = min(initial_marks + change, sm['total_marks'])
            reason    = random.choice(scrutiny_reasons)

            receipt = result_iface.submit_scrutiny(
                script_id    = script_id,
                new_marks    = new_marks,
                reason       = reason,
                from_account = scrutinizer
            )

            if receipt:
                scrutiny_count += 1
                print(f"   ✅ {script_id}: {initial_marks} → {new_marks} (+{new_marks - initial_marks})")
                print(f"      Reason: {reason}")
                # Update in-memory so reports reflect scrutinized marks
                sm['final_marks']     = new_marks
                sm['scrutiny_change'] = new_marks - initial_marks
                sm['scrutiny_reason'] = reason
            else:
                print(f"   ❌ Scrutiny failed: {script_id}")
        else:
            print(f"   ─  {script_id}: Confirmed unchanged ({initial_marks}/100)")

    print(f"\n✅ Step 6 Complete — {scrutiny_count} scripts updated")
    return scrutiny_count


# ═══════════════════════════════════════════════════════
# STEP 7 — FINALIZE
# ═══════════════════════════════════════════════════════

def step7_finalize(exam_id, roles):
    print_step("7", f"Finalize Results — Lock on Blockchain (Exam {exam_id})")

    exam_iface   = ExamInterface()
    result_iface = ResultAuditInterface()
    admin        = roles['admin']

    exam_iface.update_exam_state(exam_id, "COMPLETED", admin)

    receipt = result_iface.finalize_results(exam_id, admin)

    if receipt:
        print(f"\n✅ Exam {exam_id} results FINALIZED and LOCKED")
        print(f"   Block: {receipt['blockNumber']} | Gas: {receipt['gasUsed']}")
    else:
        print(f"\n❌ Finalization failed for Exam {exam_id}")

    print(f"\n✅ Step 7 Complete")


# ═══════════════════════════════════════════════════════
# STEP 8 — REVEAL IDENTITIES
# ═══════════════════════════════════════════════════════

def step8_reveal_identities(script_ids, mock_data, roles):
    print_step("8", "Admin Reveals Student Identities")

    hash_iface = HashRegistryInterface()
    admin      = roles['admin']
    students   = mock_data['students']

    print(f"\n🔓 Admin linking script IDs back to students...\n")

    revealed = {}
    for i, script_id in enumerate(script_ids):
        student = students[i]
        try:
            hash_iface.reveal_student(script_id, admin)
            revealed[script_id] = student
            print(f"   ✅ {script_id} → {student['name']} ({student['student_id']})")
        except Exception as e:
            print(f"   ❌ Could not reveal {script_id}: {e}")

    print(f"\n✅ Step 8 Complete — {len(revealed)} identities revealed")
    return revealed


# ═══════════════════════════════════════════════════════
# STEP 9 — CGPA & REPORT
# ═══════════════════════════════════════════════════════

def step9_report(exam_id, script_ids, mock_data, roles, revealed, exam_index=0, enrolled_students=None):
    print_step("9", f"Grade Sheet, Audit Trail & CGPA — Exam {exam_id}")

    result_iface = ResultAuditInterface()
    students     = enrolled_students or mock_data['students']
    exam_data    = mock_data['exams'][exam_index]
    exam_marks   = mock_data['marks'][exam_index]

    # ── Grade Sheet ──────────────────────────────────────
    print(f"\n{'─'*70}")
    print(f"  📋 GRADE SHEET — {exam_data['name']}")
    print(f"{'─'*70}")
    print(f"  {'Script ID':<15} {'Student':<28} {'Marks':<10} {'Grade':<8} {'GP':<6} {'Status'}")
    print(f"  {'─'*15} {'─'*28} {'─'*10} {'─'*8} {'─'*6} {'─'*8}")

    results     = []
    all_courses = {s['student_id']: [] for s in students}

    for i, script_id in enumerate(script_ids):
        sm      = exam_marks['student_marks'][i]
        student = students[i]

        # Fetch final marks from blockchain
        try:
            bc      = result_iface.get_marks(script_id)
            marks   = bc[0]
        except Exception:
            marks = sm['final_marks']

        grade_info   = get_grade_summary(marks)
        scrutiny_flag = " *" if sm.get('scrutiny_change', 0) > 0 else ""

        print(f"  {script_id:<15} {student['name']:<28} "
              f"{marks:>3}/{sm['total_marks']:<5} "
              f"{grade_info['letter_grade']:<8} "
              f"{grade_info['grade_point']:<6.2f} "
              f"{grade_info['status']}{scrutiny_flag}")

        results.append({'student': student, 'script_id': script_id,
                        'marks': marks, 'grade_info': grade_info})
        all_courses[student['student_id']].append({
            'exam_id': exam_id,
            'course':  exam_data['course_code'],
            'marks':   marks,
            'total':   sm['total_marks'],
            'credits': exam_data.get('credits', 3),
        })

    print(f"\n  * = Marks updated after scrutiny")

    # ── Audit Trail ───────────────────────────────────────
    print(f"\n{'─'*70}")
    print(f"  📜 AUDIT TRAIL — Blockchain Immutable Records")
    print(f"{'─'*70}")

    for i, script_id in enumerate(script_ids):
        sm = exam_marks['student_marks'][i]
        print(f"\n  {script_id}:")
        try:
            trail = result_iface.get_audit_trail(script_id, roles['admin'])
            for j, entry in enumerate(trail, 1):
                # AuditEntry fields (scriptId removed):
                # [0]=oldMarks [1]=newMarks [2]=changedBy [3]=reason [4]=timestamp [5]=changeType
                ctype = entry[5]
                if ctype == "EXAMINER1":
                    print(f"   [{j}] EXAMINER 1 : {entry[1]}/50")
                    print(f"        By     : {entry[2][:20]}...")
                    print(f"        Reason : {entry[3]}")
                elif ctype == "EXAMINER2":
                    # oldMarks=ex1, newMarks=ex2 individual marks
                    combined = entry[0] + entry[1]
                    print(f"   [{j}] EXAMINER 2 : {entry[1]}/50  "
                          f"(Ex1={entry[0]}/50 + Ex2={entry[1]}/50 = {combined}/100)")
                    print(f"        By     : {entry[2][:20]}...")
                    print(f"        Reason : {entry[3]}")
                elif ctype == "SCRUTINY":
                    print(f"   [{j}] SCRUTINY   : {entry[0]} → {entry[1]}")
                    print(f"        By     : {entry[2][:20]}...")
                    print(f"        Reason : {entry[3]}")
                else:
                    print(f"   [{j}] {ctype}: {entry[0]} → {entry[1]}")
                    print(f"        Reason : {entry[3]}")
        except Exception:
            ex1 = sm.get("examiner1_marks", sm["initial_marks"] // 2)
            ex2 = sm.get("examiner2_marks", sm["initial_marks"] - sm["initial_marks"] // 2)
            print(f"   [1] EXAMINER 1 : {ex1}/50")
            print(f"   [2] EXAMINER 2 : {ex2}/50  "
                  f"(combined = {ex1+ex2}/100)")
            if sm.get('scrutiny_change', 0) != 0:
                print(f"   [3] SCRUTINY   : {sm['initial_marks']} → "
                      f"{sm['final_marks']} ({sm['scrutiny_reason']})")
            print(f"   Final: {sm['final_marks']}/100")

    # ── CGPA ──────────────────────────────────────────────
    print(f"\n{'─'*70}")
    print(f"  🎓 CGPA REPORT")
    print(f"{'─'*70}")
    print(f"\n  {'Student':<28} {'ID':<15} {'CGPA':<8} Class")
    print(f"  {'─'*28} {'─'*15} {'─'*8} {'─'*25}")

    for student in students:
        courses = all_courses.get(student['student_id'], [])
        if courses:
            cgpa = calculate_cgpa(courses)
            if   cgpa >= 3.75: cls = "First Class (Distinction)"
            elif cgpa >= 3.25: cls = "First Class"
            elif cgpa >= 3.00: cls = "Second Class"
            elif cgpa >= 2.00: cls = "Pass"
            else:              cls = "Fail"
            print(f"  {student['name']:<28} {student['student_id']:<15} {cgpa:<8.2f} {cls}")

    # ── Statistics ───────────────────────────────────────
    all_marks  = [r['marks'] for r in results]
    pass_count = sum(1 for m in all_marks if m >= 40)

    print(f"\n{'─'*70}")
    print(f"  📊 EXAM STATISTICS")
    print(f"{'─'*70}")
    print(f"  Students:       {len(all_marks)}")
    print(f"  Average Marks:  {sum(all_marks)/len(all_marks):.1f}/100")
    print(f"  Pass:           {pass_count} ({pass_count/len(all_marks)*100:.0f}%)")
    print(f"  Fail:           {len(all_marks)-pass_count} ({(len(all_marks)-pass_count)/len(all_marks)*100:.0f}%)")
    print(f"  Highest:        {max(all_marks)}/100")
    print(f"  Lowest:         {min(all_marks)}/100")
    print(f"  Scrutiny Cases: {sum(1 for r in results if exam_marks['student_marks'][results.index(r)].get('scrutiny_change',0)>0)}")

    print(f"\n✅ Step 9 Complete")
    return results


# ═══════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════

def main():
    print_section("🚀 PARIKKHCHAIN — EXAM LIFECYCLE DEMO")
    print(f"   Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Check contracts deployed and reachable
    print(f"\n🔍 Checking deployed contracts...")
    try:
        if not config.load_addresses_from_file():
            print(f"\n❌ No deployed contracts found! Run deploy_contracts.py first.")
            return
    except Exception as e:
        print(f"\n❌ Error loading addresses: {e}")
        return

    if not validate_deployment():
        print("\n  Contracts not deployed. Run deploy_contracts.py first:")
        print("  python scripts/deploy_contracts.py")
        auto = input("\n  Run deploy_contracts.py now? (yes/no): ").strip().lower()
        if auto == "yes":
            import subprocess
            subprocess.run([sys.executable,
                str(Path(__file__).parent / "deploy_contracts.py")])
            # Reload addresses after deploy
            config.load_addresses_from_file()
            if not validate_deployment():
                print("\n❌ Still not reachable after deploy. Check Remix.")
                return
        else:
            return

    input(f"\nPress Enter to begin...\n")

    try:
        mock_data  = load_mock_data()
        roles      = step1_setup_and_roles(mock_data)
        num_exams  = len(mock_data['exams'])
        exam_ids   = []

        print_section(f"Processing {num_exams} exam(s)")

        for exam_index in range(num_exams):
            print(f"\n{'█'*70}")
            print(f"  EXAM {exam_index+1}/{num_exams}: {mock_data['exams'][exam_index]['name']}")
            print(f"{'█'*70}")

            exam_id = step2_create_exam(mock_data, roles, exam_index)
            if exam_id is None:
                print(f"  ⚠️  Skipping exam {exam_index+1} — creation failed")
                continue

            exam_ids.append(exam_id)
            step2b_assign_to_exam(exam_id, roles, mock_data, exam_index=exam_index)
            enrolled = step3_enroll_students(exam_id, mock_data, roles, exam_index)
            script_ids = step4_register_scripts(exam_id, mock_data, roles, exam_index, enrolled)

            if not script_ids:
                print(f"  ⚠️  No scripts — skipping marks/scrutiny for exam {exam_id}")
                continue

            step5_submit_marks(exam_id, script_ids, mock_data, roles, exam_index=exam_index)
            step6_scrutiny(exam_id, script_ids, mock_data, roles, exam_index=exam_index)
            step7_finalize(exam_id, roles)
            revealed = step8_reveal_identities(script_ids, mock_data, roles)
            step9_report(exam_id, script_ids, mock_data, roles, revealed,
                         exam_index=exam_index, enrolled_students=enrolled)

        print_section("🎉 WORKFLOW COMPLETE!")
        print(f"\n   ✅ Step 1:  Setup & Role Assignment")
        for i, eid in enumerate(exam_ids):
            print(f"   ✅ Exam {i+1}:  {mock_data['exams'][i]['name']} (ID: {eid})")
        print(f"\n   Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    except KeyboardInterrupt:
        print(f"\n\n⚠️  Cancelled by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()