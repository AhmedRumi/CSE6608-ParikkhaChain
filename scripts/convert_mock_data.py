"""
ParikkhaChain - Mock Data Converter
Converts external JSON format into complete_mock_data.json

Input  : mock_data/external_mock_data.json
Output : mock_data/complete_mock_data.json

Each course keeps its own specific examiner pair as-is from source data.
Account layout:
  [0]       = Admin
  [1..F]    = All unique faculty (examiners + scrutinizers)
  [F+1..N]  = All students
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent))

PROJECT_ROOT  = Path(__file__).parent.parent
MOCK_DATA_DIR = PROJECT_ROOT / "mock_data"
INPUT_FILE    = MOCK_DATA_DIR / "academic_mock_data.json"
OUTPUT_FILE   = MOCK_DATA_DIR / "complete_mock_data.json"
CONFIG_FILE   = PROJECT_ROOT / "parikkhchain_config.json"

MOCK_DATA_DIR.mkdir(exist_ok=True)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def round_marks(val, cap=50):
    return min(int(round(float(val))), cap)

def get_accounts():
    """
    Fetch live Ganache accounts for informational display only.
    Addresses are NOT stored in mock data — run_workflow_demo.py
    resolves them fresh at runtime via account_index.
    """
    try:
        from blockchain_interface import BlockchainInterface
        bc = BlockchainInterface()
        accounts = bc.get_accounts()
        print(f"✅ Connected — {len(accounts)} accounts available")
        print(f"   ℹ️  Addresses are NOT stored in mock data.")
        print(f"   ℹ️  They are resolved fresh each Ganache run via account_index.")
        return accounts
    except Exception as e:
        print(f"ℹ️  Ganache not running — that's fine.")
        print(f"   Addresses will be resolved at workflow runtime.")
        return None

def load_input():
    if not INPUT_FILE.exists():
        print(f"❌ Not found: {INPUT_FILE}")
        print(f"   Save your JSON there first.")
        sys.exit(1)
    with open(INPUT_FILE) as f:
        data = json.load(f)
    print(f"✅ Loaded {INPUT_FILE.name}")
    print(f"   Courses: {len(data['courses'])}  "
          f"Students: {len(data['students'])}  "
          f"Faculty: {len(data['faculties'])}")
    return data


# ─── Build people ─────────────────────────────────────────────────────────────

def build_people(data, accounts):
    """
    Assign one Ganache account per unique faculty member and per student.

    Faculty appear in two roles across courses:
      - As 'teachers'     → EXAMINER role on blockchain
      - As 'scrutinizer'  → SCRUTINIZER role on blockchain

    A faculty member can appear as examiner in one course and
    scrutinizer in another — they get ONE account, ONE role.
    Role priority: if a faculty appears as both, EXAMINER wins.
    """
    fac_map = {f["faculty_id"]: f["name"] for f in data["faculties"]}

    # Classify each faculty by their role across all courses
    teacher_ids     = set()
    scrutinizer_ids = set()
    for course in data["courses"]:
        for tid in course["teachers"]:
            teacher_ids.add(tid)
        scrutinizer_ids.add(course["scrutinizer"])

    # Examiners first, then scrutinizers (those not also a teacher)
    examiner_fids    = sorted(teacher_ids)
    scrutinizer_fids = sorted(scrutinizer_ids - teacher_ids)

    # Assign account indices
    # [0] = admin
    # [1..len(examiners)] = examiners
    # [len(examiners)+1..] = scrutinizers
    # [len(examiners)+len(scrutinizers)+1..] = students
    fac_account_idx = {}
    idx = 1
    for fid in examiner_fids:
        fac_account_idx[fid] = idx
        idx += 1
    for fid in scrutinizer_fids:
        fac_account_idx[fid] = idx
        idx += 1

    student_base = idx
    student_account_idx = {}
    for i, s in enumerate(data["students"]):
        student_account_idx[s["student_id"]] = student_base + i

    total_needed = 1 + len(fac_account_idx) + len(data["students"])

    # Build examiner objects — address is INTENTIONALLY empty.
    # run_workflow_demo.py resolves addresses fresh from Ganache at runtime
    # using account_index, so the workflow always works on any fresh Ganache start.
    examiners = []
    for fid in examiner_fids:
        ai = fac_account_idx[fid]
        examiners.append({
            "name":          fac_map.get(fid, fid),
            "faculty_id":    fid,
            "account_index": ai,
            "address":       "",   # resolved at runtime by run_workflow_demo.py
        })

    # Build scrutinizer objects
    scrutinizers = []
    for fid in scrutinizer_fids:
        ai = fac_account_idx[fid]
        scrutinizers.append({
            "name":          fac_map.get(fid, fid),
            "faculty_id":    fid,
            "account_index": ai,
            "address":       "",   # resolved at runtime
        })

    # Build student objects
    students = []
    for s in data["students"]:
        ai = student_account_idx[s["student_id"]]
        students.append({
            "name":          s["name"],
            "student_id":    s["student_id"],
            "gender":        "Unknown",
            "account_index": ai,
            "address":       "",   # resolved at runtime
            "email":         f"{s['student_id'].lower()}@student.university.edu",
            "department":    "Computer Science & Engineering",
            "batch":         "2024",
        })

    account_layout = {
        "total_needed":        total_needed,
        "admin_index":         0,
        "examiner_indices":    [e["account_index"] for e in examiners],
        "scrutinizer_indices": [s["account_index"] for s in scrutinizers],
        "student_indices":     [s["account_index"] for s in students],
    }

    print(f"\n  People:")
    print(f"  [0] Admin")
    for e in examiners:
        print(f"  [{e['account_index']}] Examiner    — {e['name']} ({e['faculty_id']})")
    for s in scrutinizers:
        print(f"  [{s['account_index']}] Scrutinizer — {s['name']} ({s['faculty_id']})")
    for s in students[:3]:
        print(f"  [{s['account_index']}] Student     — {s['name']} ({s['student_id']})")
    if len(students) > 3:
        print(f"  ... and {len(students)-3} more students")
    print(f"\n  Total Ganache accounts needed: {total_needed}")
    if total_needed > 10:
        print(f"  ⚠️  Start Ganache with enough accounts:")
        print(f"     ganache --accounts {total_needed+2} --hardfork london")

    return (examiners, scrutinizers, students, account_layout,
            fac_account_idx, student_account_idx)


# ─── Build exams ──────────────────────────────────────────────────────────────

def build_exams(data):
    exams = []
    for i, course in enumerate(data["courses"]):
        future_date = datetime.now() + timedelta(days=30 + i * 7)
        exams.append({
            "exam_id":            i + 1,
            "name":               f"{course['course_id']} Final Examination",
            "course_code":        course["course_id"],
            "course_name":        course.get("course_name", course["course_id"]),
            "exam_type":          "Final",
            "credits":            3,
            "total_marks":        100,
            "passing_marks":      40,
            "semester":           "Spring 2026",
            "venue":              "Exam Hall A",
            "exam_date":          int(future_date.timestamp()),
            "exam_date_readable": future_date.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_minutes":   180,
        })
    print(f"\n  Exams ({len(exams)}):")
    for e in exams:
        print(f"  [{e['exam_id']}] {e['name']}")
    return exams


# ─── Build per-exam assignments ───────────────────────────────────────────────

def build_assignments(data, examiners, scrutinizers, students,
                      fac_account_idx):
    """
    Per exam:
      - exam_examiners:    the exact 2 teachers from source data
      - exam_scrutinizers: the exact scrutinizer from source data
      - exam_students:     only students enrolled in this course
    """
    fac_id_to_ex = {e["faculty_id"]: e for e in examiners}
    fac_id_to_sc = {s["faculty_id"]: s for s in scrutinizers}
    # Faculty who are examiners can also act as scrutinizers in other courses
    # combine both maps for lookup
    fac_id_to_any = {**fac_id_to_ex, **fac_id_to_sc}

    stu_id_to_obj = {s["student_id"]: s for s in students}

    exam_examiners    = {}
    exam_scrutinizers = {}
    exam_students     = {}

    for i, course in enumerate(data["courses"]):
        key = str(i)

        # Examiners: exactly the 2 teachers listed for this course
        course_examiners = []
        for fid in course["teachers"]:
            if fid in fac_id_to_any:
                course_examiners.append(fac_id_to_any[fid])
            else:
                print(f"  ⚠️  Faculty {fid} not found for course {course['course_id']}")
        exam_examiners[key] = course_examiners

        # Scrutinizer: exact faculty from source
        sc_fid = course["scrutinizer"]
        if sc_fid in fac_id_to_any:
            exam_scrutinizers[key] = [fac_id_to_any[sc_fid]]
        else:
            print(f"  ⚠️  Scrutinizer {sc_fid} not found — using first available")
            exam_scrutinizers[key] = [scrutinizers[0]] if scrutinizers else []

        # Students: only those enrolled in this course
        enrolled = []
        for enrollment in course["enrollments"]:
            sid = enrollment["student_id"]
            if sid in stu_id_to_obj:
                enrolled.append(stu_id_to_obj[sid])
        exam_students[key] = enrolled

    print(f"\n  Per-exam assignments:")
    for i, course in enumerate(data["courses"]):
        key = str(i)
        ex_names = [e["name"] for e in exam_examiners[key]]
        sc_names = [s["name"] for s in exam_scrutinizers[key]]
        print(f"  [{i+1}] {course['course_id']}")
        print(f"       Examiners   : {', '.join(ex_names)}")
        print(f"       Scrutinizer : {', '.join(sc_names)}")
        print(f"       Students    : {len(exam_students[key])}")

    return exam_examiners, exam_scrutinizers, exam_students


# ─── Build marks ──────────────────────────────────────────────────────────────

def build_marks(data, exams, exam_examiners, exam_students):
    from grading_rules import get_grade_summary

    marks_data = []

    for i, course in enumerate(data["courses"]):
        key           = str(i)
        exam          = exams[i]
        enrolled      = exam_students[key]
        course_ex     = exam_examiners[key]   # [examiner1_obj, examiner2_obj]
        stu_id_set    = {s["student_id"] for s in enrolled}

        # Map teacher fac_id → examiner object for this course
        teacher_fids  = course["teachers"]
        ex1_obj = course_ex[0] if len(course_ex) > 0 else None
        ex2_obj = course_ex[1] if len(course_ex) > 1 else None

        student_marks = []
        for enrollment in course["enrollments"]:
            sid = enrollment["student_id"]
            if sid not in stu_id_set:
                continue

            # Extract marks in teacher order from source data
            teacher_marks = enrollment["teacher_marks"]
            vals = list(teacher_marks.values())
            ex1_raw = vals[0] if len(vals) > 0 else 0
            ex2_raw = vals[1] if len(vals) > 1 else 0

            ex1_marks = round_marks(ex1_raw, 50)
            ex2_marks = round_marks(ex2_raw, 50)
            initial   = ex1_marks + ex2_marks   # combined out of 100

            sc_info   = enrollment.get("scrutinizer_mark", {})
            is_error  = sc_info.get("is_error", False)
            sc_total  = round_marks(sc_info.get("mark", initial), 100)

            if is_error:
                final           = sc_total
                scrutiny_change = final - initial
                scrutiny_reason = "Scrutinizer identified marking error and revised total"
            else:
                final           = initial
                scrutiny_change = 0
                scrutiny_reason = None

            grade_info = get_grade_summary(final)
            stu_obj    = next((s for s in enrolled if s["student_id"] == sid), {})

            student_marks.append({
                "student_name":      stu_obj.get("name", sid),
                "student_id":        sid,
                "student_address":   "",   # resolved at runtime
                "examiner1_name":    ex1_obj["name"]    if ex1_obj else "N/A",
                "examiner1_address": "",   # resolved at runtime
                "examiner1_marks":   ex1_marks,
                "examiner2_name":    ex2_obj["name"]    if ex2_obj else "N/A",
                "examiner2_address": "",   # resolved at runtime
                "examiner2_marks":   ex2_marks,
                "initial_marks":     initial,
                "final_marks":       final,
                "total_marks":       100,
                "scrutiny_change":   scrutiny_change,
                "scrutiny_reason":   scrutiny_reason,
                "is_error":          is_error,
                "letter_grade":      grade_info["letter_grade"],
                "grade_point":       grade_info["grade_point"],
                "status":            grade_info["status"],
            })

        marks_data.append({
            "exam_id":       exam["exam_id"],
            "exam_name":     exam["name"],
            "course_code":   exam["course_code"],
            "credits":       exam["credits"],
            "student_marks": student_marks,
        })

    return marks_data


# ─── Build config snapshot ────────────────────────────────────────────────────

def build_config_snapshot(examiners, scrutinizers, students,
                           account_layout, exams,
                           exam_examiners, exam_scrutinizers, exam_students):
    """
    Build parikkhchain_config.json so run_workflow_demo.py
    can read per-exam examiner/scrutinizer assignments directly.
    """
    ex_idx_map  = {e["faculty_id"]: i for i, e in enumerate(examiners)}
    sc_idx_map  = {s["faculty_id"]: i for i, s in enumerate(scrutinizers)}
    # Faculty acting as scrutinizer in some courses but examiner overall
    # need a combined lookup
    all_fac_idx = {**ex_idx_map}
    for fid, idx in sc_idx_map.items():
        all_fac_idx[fid] = idx

    stu_idx_map = {s["student_id"]: i for i, s in enumerate(students)}

    exam_examiner_map    = {}
    exam_scrutinizer_map = {}
    exam_student_map     = {}

    for key in exam_examiners:
        exam_examiner_map[key] = [
            examiners.index(e) for e in exam_examiners[key]
            if e in examiners
        ]
        # Handle case where examiner is listed in scrutinizers
        for e in exam_examiners[key]:
            if e not in examiners and e in scrutinizers:
                exam_examiner_map[key].append(
                    len(examiners) + scrutinizers.index(e)
                )

    for key in exam_scrutinizers:
        exam_scrutinizer_map[key] = []
        for s in exam_scrutinizers[key]:
            if s in scrutinizers:
                exam_scrutinizer_map[key].append(scrutinizers.index(s))
            elif s in examiners:
                # This faculty is primarily an examiner but scrutinizes here
                exam_scrutinizer_map[key].append(examiners.index(s))

    for key in exam_students:
        exam_student_map[key] = [
            students.index(s) for s in exam_students[key]
            if s in students
        ]

    cfg = {
        "examiners":            examiners,
        "scrutinizers":         scrutinizers,
        "students":             students,
        "exams":                exams,
        "account_layout":       account_layout,
        "exam_examiner_map":    exam_examiner_map,
        "exam_scrutinizer_map": exam_scrutinizer_map,
        "exam_student_map":     exam_student_map,
        "generated_at":         datetime.now().isoformat(),
    }

    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)
    print(f"\n  ✅ Saved config: {CONFIG_FILE}")
    return cfg


# ─── Print summary ────────────────────────────────────────────────────────────

def print_summary(marks_data):
    print("\n" + "=" * 65)
    print("  CONVERSION SUMMARY")
    print("=" * 65)

    for em in marks_data:
        errors  = sum(1 for s in em["student_marks"] if s.get("is_error"))
        revised = sum(1 for s in em["student_marks"] if s["scrutiny_change"] != 0)
        print(f"\n  [{em['exam_id']}] {em['exam_name']}")
        print(f"  {'─'*55}")
        print(f"  {'Student':<28} {'Ex1':>5} {'Ex2':>5} "
              f"{'Init':>5} {'Final':>5} {'Grade':<5} {'Revised'}")
        print(f"  {'─'*55}")
        for sm in em["student_marks"]:
            rev = f"+{sm['scrutiny_change']}" if sm["scrutiny_change"] > 0 \
                  else (f"{sm['scrutiny_change']}" if sm["scrutiny_change"] < 0 else "")
            print(f"  {sm['student_name']:<28} "
                  f"{sm['examiner1_marks']:>4}/50 "
                  f"{sm['examiner2_marks']:>4}/50 "
                  f"{sm['initial_marks']:>5} "
                  f"{sm['final_marks']:>5} "
                  f"[{sm['letter_grade']:<3}] "
                  f"{rev}")
        print(f"  Errors: {errors}  Revised: {revised}")

    total = sum(len(em["student_marks"]) for em in marks_data)
    errors = sum(sum(1 for s in em["student_marks"] if s.get("is_error"))
                 for em in marks_data)
    print(f"\n  Total records : {total}")
    print(f"  Total revised results  : {errors}")
    print("=" * 65)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 65)
    print("  PARIKKHCHAIN — MOCK DATA CONVERTER")
    print(f"  {INPUT_FILE.name}  →  {OUTPUT_FILE.name}")
    print("=" * 65)

    data     = load_input()
    accounts = get_accounts()

    (examiners, scrutinizers, students,
     account_layout, fac_account_idx,
     student_account_idx) = build_people(data, accounts)

    exams = build_exams(data)

    (exam_examiners,
     exam_scrutinizers,
     exam_students) = build_assignments(
        data, examiners, scrutinizers, students, fac_account_idx
    )

    marks_data = build_marks(data, exams, exam_examiners, exam_students)

    roles = {
        "admin":        "",   # resolved at runtime from accounts[0]
        "admin_index":  0,
        "examiners":    examiners,
        "scrutinizers": scrutinizers,
        "examiner":     "",   # resolved at runtime
        "scrutinizer":  "",   # resolved at runtime
        "students":     [],   # resolved at runtime
    }

    cfg_snapshot = build_config_snapshot(
        examiners, scrutinizers, students, account_layout,
        exams, exam_examiners, exam_scrutinizers, exam_students
    )

    combined = {
        "students":          students,
        "exams":             exams,
        "marks":             marks_data,
        "roles":             roles,
        "exam_examiners":    exam_examiners,
        "exam_scrutinizers": exam_scrutinizers,
        "exam_students":     exam_students,
        "config_snapshot":   cfg_snapshot,
        "generated_at":      datetime.now().isoformat(),
        "source":            "converted from external_mock_data.json",
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(combined, f, indent=2)

    print_summary(marks_data)
    print(f"\n  ✅ Saved: {OUTPUT_FILE}")
    print(f"\n  Next steps:")
    print(f"    1. python scripts/deploy_contracts.py")
    print(f"    2. python scripts/run_workflow_demo.py")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Cancelled")
    except Exception as e:
        print(f"\n❌ {e}")
        import traceback
        traceback.print_exc()