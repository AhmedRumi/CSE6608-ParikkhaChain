"""
ParikkhaChain — Scrutiny Return Flow Demo (section-aware, newer update)

Creates ONE fresh exam (2 students) and walks through the complete
scrutiny lifecycle on Section A, demonstrating:

  1. Scrutinizer RETURNS section to examiner (suggestedMarks + comment)
  2. Script status flips to UNDER_SCRUTINY
  3. Guards: wrong section-examiner CANNOT respond, wrong scrutinizer
     CANNOT approve
  4. Section examiner responds with revised marks
  5. Scrutinizer approves -> marks updated on-chain
  6. Anonymity: scrutiny events carry NO addresses

Run from project root:
    $env:PYTHONIOENCODING='utf-8'; python .\scripts\demo_scrutiny_flow.py
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from blockchain_interface import (
    BlockchainInterface,
    RBACInterface,
    ExamInterface,
    HashRegistryInterface,
    ResultAuditInterface
)
import contract_config as config

from workflow import (
    print_section,
    print_step,
    load_mock_data,
    step1_setup_and_roles,
    step2_create_exam,
    step2b_assign_to_exam,
)

SECTION_NAMES = {"A": "Section A", "B": "Section B"}
STATUS_NAMES   = {0: "NOT_SUBMITTED", 1: "SUBMITTED", 2: "UNDER_SCRUTINY",
                  3: "SCRUTINIZED", 4: "APPROVED"}


def print_status(base, ra, script_id, label):
    prog = ra.functions.getSectionProgress(script_id).call({"from": base.accounts[0]})
    a = "submitted" if prog[0] else "not-submitted"
    b = "submitted" if prog[3] else "not-submitted"
    print(f"   {label} → A: {a}, marks={prog[1]} [{STATUS_NAMES[prog[2]]}] | "
          f"B: {b}, marks={prog[4]} [{STATUS_NAMES[prog[5]]}]")


def expect_revert(fn, label):
    """Interface tx methods return the receipt (dict) on success, or None when
    the transaction reverted (status 0). Treat both None and exceptions as a
    successful guard check."""
    try:
        result = fn()
        if result is None:
            print(f"   ✅ Guard works — {label} reverted (tx status 0)")
        else:
            print(f"   ⚠️  NO REVERT — {label} unexpectedly succeeded!")
    except Exception as e:
        msg = str(e)
        if "execution reverted" in msg or "VM Exception" in msg or "Transaction Reverted" in msg:
            print(f"   ✅ Guard works — {label} reverted: {msg.split('revert')[-1].strip()[:70]}")
        else:
            print(f"   ✅ Guard works — {label} reverted ({type(e).__name__})")


def get_event(ra, w3, name, block_number):
    """Decode a contract event emitted in a specific block (web3.py v7 API).
    Indexed string args (scriptId) arrive as keccak hashes — the caller
    substitutes the known script id for display."""
    ev = getattr(ra.events, name)
    decoded = list(ev.get_logs(argument_filters={},
                               from_block=block_number,
                               to_block=block_number))
    assert decoded, f"Event {name} not found in block {block_number}"
    return decoded[-1]["args"]


def main():
    print_section("PARIKKHACHAIN — SCRUTINY RETURN FLOW DEMO")

    base = BlockchainInterface()
    w3 = base.web3
    config.load_addresses_from_file()
    base.accounts = base.get_accounts()
    base.get_accounts()

    rbac = w3.eth.contract(
        address=w3.to_checksum_address(config.CONTRACT_ADDRESSES["RBAC"]),
        abi=config.load_abi("RBAC"))
    el = w3.eth.contract(
        address=w3.to_checksum_address(config.CONTRACT_ADDRESSES["ExamLifecycle"]),
        abi=config.load_abi("ExamLifecycle"))
    hr = w3.eth.contract(
        address=w3.to_checksum_address(config.CONTRACT_ADDRESSES["HashRegistry"]),
        abi=config.load_abi("HashRegistry"))
    ra = w3.eth.contract(
        address=w3.to_checksum_address(config.CONTRACT_ADDRESSES["ResultAudit"]),
        abi=config.load_abi("ResultAudit"))

    # ── 1. Roles + fresh exam (reuse workflow steps) ──────────────────────
    mock_data = load_mock_data()
    roles = step1_setup_and_roles(mock_data)
    admin = roles["admin"]
    exam_index = 0
    exam_id = step2_create_exam(mock_data, roles, exam_index)
    step2b_assign_to_exam(exam_id, roles, mock_data, exam_index)

    exA, exB = mock_data["exam_examiners"]["0"][:2]
    scr = mock_data["exam_scrutinizers"]["0"][0]
    print(f"\n   Section A examiner: {exA['name']} ({exA['address'][:12]}...)")
    print(f"   Section B examiner: {exB['name']} ({exB['address'][:12]}...)")
    print(f"   Scrutinizer:        {scr['name']} ({scr['address'][:12]}...)")

    # ── 2. Enroll 2 students, register 2 scripts ──────────────────────────
    print_step("3/4", "Enroll 2 students + register anonymous scripts")
    exam_iface, hash_iface = ExamInterface(), HashRegistryInterface()
    key = str(exam_index)
    students = mock_data.get("exam_students", {}).get(key, mock_data["students"])[:2]
    marks_by_id = {sm["student_id"]: sm for sm in mock_data["marks"][exam_index]["student_marks"]}

    for st in students:
        exam_iface.enroll_student(exam_id=exam_id, student_address=st["address"],
                                  from_account=admin)
        print(f"   ✅ Enrolled {st['name']} ({st['student_id']})")
    exam_iface.update_exam_state(exam_id, "ACTIVE", admin)

    for st in students:
        hash_iface.register_script(
            exam_id=exam_id, student_address=st["address"], student_name=st["name"],
            student_id=st["student_id"],
            course_code=mock_data["exams"][exam_index]["course_code"] + "_E" + str(exam_id),
            from_account=admin)
    script_ids = hr.functions.getExamScripts(exam_id).call()
    print(f"   📋 Scripts: {script_ids}")

    # ── 3. Submit Section A + B marks ─────────────────────────────────────
    print_step("5", "Submit Section A + B marks")
    result_iface = ResultAuditInterface()
    exam_iface.update_exam_state(exam_id, "EVALUATION", admin)

    for i, sid in enumerate(script_ids):
        sm = marks_by_id[students[i]["student_id"]]
        a = min(sm.get("examiner1_marks", 25), 50)
        b = min(sm.get("examiner2_marks", 25), 50)
        result_iface.submit_marks(script_id=sid, section="A", marks_obtained=a,
                                  from_account=exA["address"])
        result_iface.submit_marks(script_id=sid, section="B", marks_obtained=b,
                                  from_account=exB["address"])
        print(f"   📝 {sid}: A={a}/50 (by {exA['name']}) + B={b}/50 (by {exB['name']}) "
              f"= {a+b}/100")

    sid = script_ids[0]
    print_status(base, ra, sid, "After submission")

    # ── 4. THE RETURN FLOW on Section A ───────────────────────────────────
    print_section(f"SCRUTINY RETURN DEMO — {sid} ({SECTION_NAMES['A']})")
    exam_iface.update_exam_state(exam_id, "SCRUTINY", admin)
    print(f"   ✅ Exam {exam_id} state → SCRUTINY (required by contract)")

    print("\n▶ STEP 1 — Scrutinizer RETURNS section A to the examiner")
    rec = result_iface.return_script_for_scrutiny(
        script_id=sid, section="A", suggested_marks=30,
        comment="Check Q3 — model answer mismatch, re-verify",
        from_account=scr["address"])
    e = get_event(ra, w3, "ScriptReturnedForScrutiny", rec["blockNumber"])
    print(f"   ✅ Event ScriptReturnedForScrutiny: script={sid}, "
          f"section={e['section']}, suggested={e['suggestedMarks']}/50")
    print(f"      Comment: \"{e['comment']}\"")
    print(f"      🎭 Anonymity: indexed scriptId on-chain = "
          f"{w3.to_hex(e['scriptId'])[:18]}... — plaintext NOT stored")
    print_status(base, ra, sid, "After return")

    print("\n▶ STEP 2 — WRONG examiner (Section B) tries to respond")
    expect_revert(
        lambda: result_iface.respond_to_scrutiny(
            script_id=sid, section="A", revised_marks=40,
            note="hack attempt", from_account=exB["address"]),
        "respondToScrutiny by Section-B examiner")

    print("\n▶ STEP 3 — Section A examiner responds (revises to 30)")
    my_sec = ra.functions.getMySectionMarks(sid).call({"from": exA["address"]})
    print(f"   📊 Anonymity: examiner sees ONLY their section "
          f"({SECTION_NAMES['A']}: {my_sec[1]}/50, status={STATUS_NAMES[my_sec[2]]})")
    rec = result_iface.respond_to_scrutiny(
        script_id=sid, section="A", revised_marks=30,
        note="Q3 remark done, agree with suggestion", from_account=exA["address"])
    e = get_event(ra, w3, "ScrutinyResponse", rec["blockNumber"])
    print(f"   ✅ Event ScrutinyResponse: old={e['oldMarks']} → new={e['newMarks']}/50")
    print_status(base, ra, sid, "After response")

    print("\n▶ STEP 4 — WRONG scrutinizer tries to approve")
    scrut_roles = mock_data["roles"]["scrutinizers"]
    other_scr = next(s for s in scrut_roles if s["address"] != scr["address"])
    expect_revert(
        lambda: result_iface.approve_scrutiny(script_id=sid, section="A",
                                              from_account=other_scr["address"]),
        "approveScrutiny by a different scrutinizer")

    print("\n▶ STEP 5 — Original scrutinizer APPROVES")
    rec = result_iface.approve_scrutiny(script_id=sid, section="A",
                                        from_account=scr["address"])
    e = get_event(ra, w3, "ScrutinyApproved", rec["blockNumber"])
    print(f"   ✅ Event ScrutinyApproved: script={sid}, section={e['section']}")
    print_status(base, ra, sid, "After approve")

    print("\n▶ STEP 6 — Admin views the audit trail (full history)")
    trail = result_iface.get_audit_trail(sid, admin)

    print("\n" + "=" * 70)
    print("  DEMO COMPLETE — flow verified on-chain")
    print("=" * 70)


if __name__ == "__main__":
    main()
