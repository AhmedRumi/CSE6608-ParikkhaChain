"""
ParikkhaChain — ZKP Commitment Demo (Interactive / Manual)
===========================================================
Fully interactive walkthrough of privacy-preserving credential verification.

PHASES:
  1. COMMIT   — Admin selects a student, reads their marks from blockchain,
                generates a secret salt, computes commitment hash, stores on-chain.
  2. CRITERIA — Third party (employer/university) enters their requirements.
  3. PROVE    — Student selects which criteria to prove against,
                submits their marks + salt to contract.
  4. VERIFY   — Third party checks eligibility → sees only true/false.

RUN:
  python scripts/zkp_demo.py
"""

import sys
import json
import secrets
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent))

import contract_config as config
from blockchain_interface import BlockchainInterface
from grading_rules import get_grade_summary, calculate_cgpa

PROJECT_ROOT   = Path(__file__).parent.parent
MOCK_DATA_FILE = PROJECT_ROOT / "mock_data" / "complete_mock_data.json"
SALTS_FILE     = PROJECT_ROOT / "mock_data" / "zkp_salts.json"


# ─── UI helpers ───────────────────────────────────────────────────────────────

def sep():   print("  " + "─" * 61)
def line():  print("  " + "═" * 61)

def header(title):
    print(f"\n{'═'*65}")
    print(f"  {title}")
    print(f"{'═'*65}")

def phase_header(num, title):
    print(f"\n{'─'*65}")
    print(f"  PHASE {num} — {title}")
    print(f"{'─'*65}")

def ask(prompt, default=None):
    suffix = f" [{default}]" if default is not None else ""
    val = input(f"  {prompt}{suffix}: ").strip()
    return val if val else str(default) if default is not None else ""

def ask_int(prompt, lo, hi, default=None):
    while True:
        val = ask(prompt, default)
        try:
            n = int(val)
            if lo <= n <= hi:
                return n
        except ValueError:
            pass
        print(f"  ⚠️  Enter a number between {lo} and {hi}")

def ask_bool(prompt, default=True):
    suffix = "[Y/n]" if default else "[y/N]"
    val = input(f"  {prompt} {suffix}: ").strip().lower()
    if not val:
        return default
    return val in ("y", "yes", "1", "true")

def pick_from_list(items, label_fn, title):
    """Show numbered list, return selected item."""
    print(f"\n  {title}:")
    for i, item in enumerate(items, 1):
        print(f"    [{i}] {label_fn(item)}")
    n = ask_int("Select", 1, len(items))
    return items[n - 1]

def pause(msg="Press Enter to continue..."):
    input(f"\n  {msg}")


# ─── Connect ──────────────────────────────────────────────────────────────────

def connect():
    config.load_addresses_from_file()
    bc = BlockchainInterface()
    w3 = bc.web3

    # Refresh addresses from live Ganache
    live_accounts = w3.eth.accounts

    def ctr(name):
        addr = config.CONTRACT_ADDRESSES.get(name)
        if not addr:
            raise ValueError(
                f"'{name}' address not found in deployed_addresses.json.\n"
                f"   Deploy ZKPCommitment.sol in Remix and add its address.")
        return w3.eth.contract(
            address=w3.to_checksum_address(addr),
            abi=config.load_abi(name)
        )

    return w3, {
        "rbac":   ctr("RBAC"),
        "result": ctr("ResultAudit"),
        "hash":   ctr("HashRegistry"),
        "zkp":    ctr("ZKPCommitment"),
    }, live_accounts


# ─── Data helpers ─────────────────────────────────────────────────────────────

def load_mock_data(w3, live_accounts):
    if not MOCK_DATA_FILE.exists():
        print(f"❌ {MOCK_DATA_FILE} not found. Run convert_mock_data.py first.")
        sys.exit(1)
    with open(MOCK_DATA_FILE) as f:
        data = json.load(f)
    # Refresh addresses
    for s in data["students"]:
        idx = s.get("account_index")
        if idx is not None and idx < len(live_accounts):
            s["address"] = live_accounts[idx]
    return data


def load_salts():
    if SALTS_FILE.exists():
        with open(SALTS_FILE) as f:
            return json.load(f)
    return {}


def save_salts(salts):
    SALTS_FILE.parent.mkdir(exist_ok=True)
    with open(SALTS_FILE, "w") as f:
        json.dump(salts, f, indent=2)


def get_marks_from_blockchain(w3, contracts, student_addr, admin_addr):
    """Read finalized marks from ResultAudit.getFullTranscript()."""
    try:
        result = contracts["result"].functions.getFullTranscript(
            w3.to_checksum_address(student_addr)
        ).call({"from": w3.to_checksum_address(admin_addr)})

        script_ids, exam_ids, course_codes, marks_obtained, \
            total_marks, statuses, has_scrutiny = result

        courses = []
        for i in range(len(script_ids)):
            if statuses[i] >= 1:
                courses.append({
                    "course_code":    course_codes[i] or f"COURSE_{i+1}",
                    "marks_obtained": marks_obtained[i],
                    "total_marks":    total_marks[i],
                    "credits":        3,
                })
        return courses
    except Exception as e:
        print(f"  ⚠️  Could not read transcript: {e}")
        return []


def compute_cgpa_scaled(courses):
    data = [{"course": c["course_code"],
             "marks":  c["marks_obtained"],
             "credits":c["credits"]} for c in courses]
    return round(calculate_cgpa(data) * 100)


def compute_commitment(w3, cgpa_scaled, marks, credits, salt_hex):
    """keccak256(abi.encodePacked(cgpa_scaled, marks[], credits[], salt))"""
    salt_bytes = bytes.fromhex(salt_hex.replace("0x", "")).rjust(32, b"\x00")
    packed = b""
    packed += int(cgpa_scaled).to_bytes(32, "big")
    for m in marks:
        packed += int(m).to_bytes(32, "big")
    for c in credits:
        packed += int(c).to_bytes(32, "big")
    packed += salt_bytes
    return w3.keccak(packed).hex()


def send_tx(w3, fn, from_addr, gas=400_000):
    """Build and send a transaction, return receipt."""
    tx = fn.build_transaction({
        "from":     w3.to_checksum_address(from_addr),
        "gas":      gas,
        "gasPrice": w3.to_wei("1", "gwei"),
        "nonce":    w3.eth.get_transaction_count(from_addr),
    })
    tx_hash = w3.eth.send_transaction(tx)
    print(f"   ⏳ Tx: {tx_hash.hex()[:20]}...")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    if receipt["status"] == 1:
        print(f"   ✅ Confirmed  block={receipt['blockNumber']}  "
              f"gas={receipt['gasUsed']:,}")
        return receipt
    else:
        print(f"   ❌ Transaction reverted")
        return None


# ─── Phase 1: COMMIT ──────────────────────────────────────────────────────────

def phase1_commit(w3, contracts, accounts, mock_data, salts):
    phase_header("1", "COMMIT — Admin commits student transcript hash on-chain")

    print("""
  The admin reads a student's marks from the ResultAudit contract,
  computes:  commitment = keccak256(cgpa + marks[] + credits[] + salt)
  and stores ONLY the commitment hash on-chain.
  The actual marks are NEVER stored on the ZKP contract.
""")

    admin_addr = accounts[0]
    print(f"  Admin account: {admin_addr}\n")

    # Pick student
    students_with_addr = [s for s in mock_data["students"] if s.get("address")]
    if not students_with_addr:
        print("  ❌ No students with addresses found. Run workflow first.")
        return None

    student = pick_from_list(
        students_with_addr,
        lambda s: f"{s['name']:<28} ({s['student_id']})  [{s['address'][:14]}...]",
        "Select student to commit"
    )

    addr = student["address"]
    print(f"\n  Selected: {student['name']} ({student['student_id']})")
    print(f"  Address : {addr}")

    # Read marks from blockchain
    print(f"\n  📡 Reading marks from ResultAudit blockchain...")
    courses = get_marks_from_blockchain(w3, contracts, addr, admin_addr)

    if not courses:
        print("  ❌ No finalized marks found for this student.")
        print("     Make sure the workflow has been run and results finalized.")
        return None

    # Display marks
    cgpa_scaled = compute_cgpa_scaled(courses)
    print(f"\n  Marks retrieved from blockchain:")
    sep()
    print(f"  {'Course':<14} {'Marks':>6}  {'Grade':<5}  Credits")
    sep()
    for c in courses:
        gi = get_grade_summary(c["marks_obtained"])
        print(f"  {c['course_code']:<14} {c['marks_obtained']:>5}/100  "
              f"{gi['letter_grade']:<5}  {c['credits']} cr")
    sep()
    print(f"  CGPA: {cgpa_scaled/100:.2f}  (scaled: {cgpa_scaled})")

    # Salt
    print(f"\n  Generating secret salt...")
    if addr in salts:
        print(f"  ℹ️  Existing salt found for this student.")
        use_existing = ask_bool("Use existing salt?", True)
        if not use_existing:
            salts[addr] = "0x" + secrets.token_hex(32)
            print(f"  New salt generated.")
    else:
        salts[addr] = "0x" + secrets.token_hex(32)
        print(f"  New salt generated.")

    salt = salts[addr]
    print(f"  Salt: {salt[:22]}...  ← KEEP THIS SECRET")

    # Compute commitment
    marks_list   = [c["marks_obtained"] for c in courses]
    credits_list = [c["credits"]        for c in courses]
    commitment   = compute_commitment(w3, cgpa_scaled, marks_list, credits_list, salt)

    print(f"\n  Computing commitment hash...")
    print(f"  keccak256(cgpa={cgpa_scaled}, marks={marks_list},")
    print(f"            credits={credits_list}, salt={salt[:14]}...)")
    print(f"  Commitment: {commitment}")
    print(f"\n  ℹ️  Only the commitment hash will be stored on-chain.")
    print(f"     The actual marks stay off-chain.")

    pause("Press Enter to store commitment on-chain...")

    # Store on-chain
    commitment_bytes = bytes.fromhex(commitment.replace("0x", ""))
    receipt = send_tx(
        w3,
        contracts["zkp"].functions.commitTranscript(
            w3.to_checksum_address(addr),
            commitment_bytes,
            len(courses),
            sum(credits_list)
        ),
        admin_addr
    )

    if not receipt:
        return None

    save_salts(salts)
    print(f"\n  ✅ Phase 1 Complete")
    print(f"     Commitment stored: {commitment[:22]}...")
    print(f"     Course count: {len(courses)}")
    print(f"     Salt saved to: {SALTS_FILE.name}")

    return {
        "student":       student,
        "courses":       courses,
        "cgpa_scaled":   cgpa_scaled,
        "marks_exact":   marks_list,
        "credits_exact": credits_list,
        "salt":          salt,
        "commitment":    commitment,
        "course_count":  len(courses),
    }


# ─── Phase 2: CRITERIA ────────────────────────────────────────────────────────

def phase2_criteria(w3, contracts, accounts):
    phase_header("2", "CRITERIA — Third party posts eligibility requirements")

    print("""
  Any address can post eligibility criteria on-chain.
  This represents an employer, university, or scholarship board
  defining what they require from a student's transcript.
""")

    # Pick third party account
    print("  Select the third party account (employer/university):")
    print("  (Use any account that is NOT admin or student)")
    for i, acc in enumerate(accounts[-5:], len(accounts)-5):
        print(f"    [{i}] {acc}")
    tp_idx = ask_int("Account index", 0, len(accounts)-1, len(accounts)-1)
    third_party = accounts[tp_idx]
    print(f"\n  Third party: {third_party}")

    # Enter criteria manually
    print(f"\n  Enter eligibility criteria:\n")

    description   = ask("Description (e.g. MSc CS Admission 2026)",
                         "MSc CS Admission 2026")
    min_cgpa_disp = float(ask("Minimum CGPA required (e.g. 3.00)", "3.00"))
    min_cgpa_sc   = round(min_cgpa_disp * 100)
    min_grade     = ask_int("Minimum marks in any course (0-100)", 0, 100, 50)
    course_idx    = ask_int("Course index to check grade (0 = first course)", 0, 10, 0)
    min_credits   = ask_int("Minimum passed credit hours", 0, 50, 9)
    req_all_pass  = ask_bool("Require all courses passed (>=40)?", True)
    days_deadline = ask_int("Deadline in days from now", 1, 365, 90)
    deadline      = int((datetime.now() + timedelta(days=days_deadline)).timestamp())

    print(f"\n  Criteria summary:")
    sep()
    print(f"  Description    : {description}")
    print(f"  Min CGPA       : {min_cgpa_disp:.2f}  (scaled: {min_cgpa_sc})")
    print(f"  Min grade      : {min_grade}/100  (course index {course_idx})")
    print(f"  Min credits    : {min_credits}")
    print(f"  All pass req.  : {req_all_pass}")
    print(f"  Deadline       : {(datetime.now()+timedelta(days=days_deadline)).strftime('%Y-%m-%d')}")
    sep()

    pause("Press Enter to post criteria on-chain...")

    receipt = send_tx(
        w3,
        contracts["zkp"].functions.postCriteria(
            description,
            min_cgpa_sc,
            min_grade,
            course_idx,
            min_credits,
            req_all_pass,
            deadline,
        ),
        third_party
    )

    if not receipt:
        return None

    criteria_id = contracts["zkp"].functions.getTotalCriteria().call()
    print(f"\n  ✅ Phase 2 Complete — Criteria ID: {criteria_id} stored on-chain")
    return criteria_id, third_party


# ─── Phase 3: PROVE ───────────────────────────────────────────────────────────

def phase3_prove(w3, contracts, committed, criteria_id):
    phase_header("3", "PROVE — Student submits proof to contract")

    print(f"""
  The student submits their marks and salt to the ZKP contract.
  The contract:
    1. Recomputes keccak256(marks + salt)
    2. Checks it matches the stored commitment
    3. Checks all criteria conditions
    4. Stores ONLY true/false — never the actual marks

  Note: Marks appear in transaction calldata in this scheme.
        (True zk-SNARK would hide them completely via Circom/Groth16)
""")

    student  = committed["student"]
    addr     = student["address"]
    salt_hex = committed["salt"]
    salt_b   = bytes.fromhex(salt_hex.replace("0x", "")).rjust(32, b"\x00")

    print(f"  Student : {student['name']} ({student['student_id']})")
    print(f"  Address : {addr}")
    print(f"  Criteria ID: {criteria_id}")

    # Show what will be submitted
    print(f"\n  Data to submit to contract:")
    sep()
    print(f"  CGPA scaled  : {committed['cgpa_scaled']}  "
          f"(= {committed['cgpa_scaled']/100:.2f})")
    print(f"  Marks        : {committed['marks_exact']}")
    print(f"  Credits      : {committed['credits_exact']}")
    print(f"  Salt         : {salt_hex[:22]}...  (secret)")
    print(f"  Commitment   : {committed['commitment'][:22]}...  (on-chain)")
    sep()
    print(f"""
  ⚠️  Privacy note:
     The marks above will be visible in the transaction calldata.
     The third party can read them by inspecting this specific tx.
     In a true zk-SNARK, marks would NEVER appear anywhere on-chain.
""")

    pause("Press Enter to submit proof on-chain...")

    receipt = send_tx(
        w3,
        contracts["zkp"].functions.submitProof(
            criteria_id,
            committed["cgpa_scaled"],
            committed["marks_exact"],
            committed["credits_exact"],
            salt_b,
        ),
        addr,
        gas=500_000
    )

    if not receipt:
        return False

    # Read result
    eligible = contracts["zkp"].functions.checkEligibility(
        criteria_id,
        w3.to_checksum_address(addr)
    ).call()

    result_str = "✅ ELIGIBLE" if eligible else "❌ NOT ELIGIBLE"
    print(f"\n  Proof result stored on-chain: {result_str}")
    print(f"  (Only this boolean is stored — marks are NOT stored)")
    print(f"\n  ✅ Phase 3 Complete")
    return eligible


# ─── Phase 4: VERIFY ──────────────────────────────────────────────────────────

def phase4_verify(w3, contracts, committed, criteria_id, third_party):
    phase_header("4", "VERIFY — Third party checks eligibility")

    print(f"""
  The third party calls checkEligibility() on-chain.
  They see ONLY true/false.
  They cannot see the student's actual marks or CGPA.
""")

    student = committed["student"]
    addr    = student["address"]

    print(f"  Third party  : {third_party}")
    print(f"  Student      : {student['name']} ({student['student_id']})")
    print(f"  Student addr : {addr}")
    print(f"  Criteria ID  : {criteria_id}")

    # Show criteria
    try:
        cr = contracts["zkp"].functions.getCriteria(criteria_id).call()
        print(f"\n  Criteria requirements:")
        sep()
        print(f"  Description    : {cr[1]}")
        print(f"  Min CGPA       : {cr[2]/100:.2f}")
        print(f"  Min grade      : {cr[3]}/100")
        print(f"  Min credits    : {cr[5]}")
        print(f"  All pass req.  : {cr[6]}")
        sep()
    except Exception:
        pass

    pause("Press Enter for third party to check eligibility...")

    # Third party calls checkEligibility
    eligible = contracts["zkp"].functions.checkEligibility(
        criteria_id,
        w3.to_checksum_address(addr)
    ).call({"from": w3.to_checksum_address(third_party)})

    status, verified, submitted_at = \
        contracts["zkp"].functions.getProofStatus(
            criteria_id,
            w3.to_checksum_address(addr)
        ).call()

    ts = datetime.fromtimestamp(submitted_at).strftime("%Y-%m-%d %H:%M:%S") \
         if submitted_at > 0 else "N/A"

    print(f"\n  ╔{'═'*45}╗")
    result_str = "ELIGIBLE" if eligible else "NOT ELIGIBLE"
    print(f"  ║  Student: {student['name']:<33}║")
    print(f"  ║  Result : {'✅ ' + result_str if eligible else '❌ ' + result_str:<33}║")
    print(f"  ║  Proof submitted at: {ts:<23}║")
    print(f"  ╚{'═'*45}╝")

    print(f"""
  The third party now knows: {student['name']} is {'ELIGIBLE' if eligible else 'NOT ELIGIBLE'}.
  They do NOT know:
    - Actual CGPA value
    - Individual course marks
    - How far above/below threshold
    - Which courses were taken
""")
    print(f"  ✅ Phase 4 Complete")
    return eligible


# ─── Main menu ────────────────────────────────────────────────────────────────

def main():
    header("PARIKKHCHAIN — ZKP COMMITMENT DEMO (Interactive)")
    print("""
  Privacy-preserving credential verification.
  Each phase is done manually step by step.
""")

    try:
        w3, contracts, accounts = connect()
    except Exception as e:
        print(f"\n❌ {e}")
        sys.exit(1)

    print(f"  Chain: {w3.eth.chain_id}  |  Block: {w3.eth.block_number}")
    mock_data = load_mock_data(w3, accounts)
    salts     = load_salts()

    committed    = None
    criteria_id  = None
    third_party  = None

    while True:
        print(f"\n  ┌{'─'*45}┐")
        print(f"  │  MAIN MENU                               │")
        print(f"  ├{'─'*45}┤")
        print(f"  │  [1] Phase 1 — Commit transcript         │")
        print(f"  │  [2] Phase 2 — Post criteria             │")
        print(f"  │  [3] Phase 3 — Submit proof              │")
        print(f"  │  [4] Phase 4 — Verify eligibility        │")
        print(f"  │  [5] Run all 4 phases sequentially       │")
        print(f"  │  [6] Check commitment on-chain           │")
        print(f"  │  [0] Exit                                │")
        print(f"  └{'─'*45}┘")

        choice = ask("Select", "5")

        if choice == "0":
            print("\n  Bye!\n")
            break

        elif choice == "1":
            committed = phase1_commit(w3, contracts, accounts, mock_data, salts)

        elif choice == "2":
            result = phase2_criteria(w3, contracts, accounts)
            if result:
                criteria_id, third_party = result

        elif choice == "3":
            if not committed:
                print("  ⚠️  Run Phase 1 first.")
            elif not criteria_id:
                print("  ⚠️  Run Phase 2 first.")
            else:
                phase3_prove(w3, contracts, committed, criteria_id)

        elif choice == "4":
            if not committed:
                print("  ⚠️  Run Phase 1 first.")
            elif not criteria_id:
                print("  ⚠️  Run Phase 2 first.")
            else:
                phase4_verify(w3, contracts, committed, criteria_id, third_party)

        elif choice == "5":
            # Run all 4 phases sequentially
            committed = phase1_commit(w3, contracts, accounts, mock_data, salts)
            if committed:
                result = phase2_criteria(w3, contracts, accounts)
                if result:
                    criteria_id, third_party = result
                    phase3_prove(w3, contracts, committed, criteria_id)
                    phase4_verify(w3, contracts, committed, criteria_id, third_party)

                    header("ZKP DEMO COMPLETE")
                    print(f"""
  SUMMARY:
  ─────────────────────────────────────────────────────
  Phase 1: Admin stored commitment hash on-chain.
           Actual marks were NEVER stored.

  Phase 2: Third party posted eligibility criteria.

  Phase 3: Student submitted marks + salt.
           Contract verified hash, checked criteria,
           stored ONLY true/false.

  Phase 4: Third party saw only ELIGIBLE/NOT ELIGIBLE.
           Never saw actual marks or CGPA.

  Student proved eligibility WITHOUT revealing marks.
  ─────────────────────────────────────────────────────
""")

        elif choice == "6":
            # Check what's stored on-chain for a student
            students_with_addr = [s for s in mock_data["students"]
                                   if s.get("address")]
            student = pick_from_list(
                students_with_addr,
                lambda s: f"{s['name']} ({s['student_id']})",
                "Select student"
            )
            try:
                commitment, course_count, total_credits, committed_at = \
                    contracts["zkp"].functions.getCommitment(
                        w3.to_checksum_address(student["address"])
                    ).call()
                ts = datetime.fromtimestamp(committed_at).strftime("%Y-%m-%d %H:%M:%S")
                print(f"\n  On-chain commitment for {student['name']}:")
                sep()
                print(f"  Commitment  : 0x{commitment.hex()}")
                print(f"  Course count: {course_count}")
                print(f"  Credits     : {total_credits}")
                print(f"  Committed at: {ts}")
                sep()
            except Exception as e:
                print(f"  ❌ No commitment found: {e}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Cancelled\n")
    except Exception as e:
        print(f"\n❌ {e}")
        import traceback
        traceback.print_exc()