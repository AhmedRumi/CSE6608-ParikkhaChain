"""
ParikkhaChain - PDF Transcript Generator
Generates an official academic transcript PDF from blockchain data.
Uses the same data flow as view_result.py.
"""

import sys
from pathlib import Path
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

sys.path.insert(0, str(Path(__file__).parent))

# ── Colour palette ────────────────────────────────────────────────────────────
DARK_BLUE  = colors.HexColor("#1a3a5c")
MID_BLUE   = colors.HexColor("#2c5f8a")
LIGHT_BLUE = colors.HexColor("#e8f0f8")
ACCENT     = colors.HexColor("#c8a82a")   # gold
PASS_GREEN = colors.HexColor("#2e7d32")
FAIL_RED   = colors.HexColor("#c62828")
GREY_TEXT  = colors.HexColor("#555555")
LIGHT_GREY = colors.HexColor("#f5f5f5")
WHITE      = colors.white
BLACK      = colors.black


def grade_color(letter):
    if letter in ("A+", "A", "A-"):  return PASS_GREEN
    if letter in ("B+", "B", "B-"):  return MID_BLUE
    if letter in ("C+", "C"):        return colors.HexColor("#e65100")
    if letter == "D":                return colors.HexColor("#bf360c")
    return FAIL_RED


def build_styles():
    base = getSampleStyleSheet()
    styles = {}

    styles["uni_name"] = ParagraphStyle(
        "uni_name", fontSize=16, fontName="Helvetica-Bold",
        textColor=WHITE, alignment=TA_CENTER, spaceAfter=2)

    styles["uni_sub"] = ParagraphStyle(
        "uni_sub", fontSize=9, fontName="Helvetica",
        textColor=colors.HexColor("#cce0f5"), alignment=TA_CENTER, spaceAfter=0)

    styles["doc_title"] = ParagraphStyle(
        "doc_title", fontSize=11, fontName="Helvetica-Bold",
        textColor=ACCENT, alignment=TA_CENTER, spaceAfter=0)

    styles["section_head"] = ParagraphStyle(
        "section_head", fontSize=9, fontName="Helvetica-Bold",
        textColor=DARK_BLUE, spaceBefore=8, spaceAfter=4)

    styles["field_label"] = ParagraphStyle(
        "field_label", fontSize=8, fontName="Helvetica-Bold",
        textColor=GREY_TEXT)

    styles["field_value"] = ParagraphStyle(
        "field_value", fontSize=9, fontName="Helvetica",
        textColor=BLACK)

    styles["small"] = ParagraphStyle(
        "small", fontSize=7.5, fontName="Helvetica",
        textColor=GREY_TEXT, alignment=TA_CENTER)

    styles["footer"] = ParagraphStyle(
        "footer", fontSize=7, fontName="Helvetica",
        textColor=GREY_TEXT, alignment=TA_CENTER)

    styles["cgpa_big"] = ParagraphStyle(
        "cgpa_big", fontSize=22, fontName="Helvetica-Bold",
        textColor=DARK_BLUE, alignment=TA_CENTER)

    styles["cgpa_label"] = ParagraphStyle(
        "cgpa_label", fontSize=8, fontName="Helvetica",
        textColor=GREY_TEXT, alignment=TA_CENTER)

    styles["class_text"] = ParagraphStyle(
        "class_text", fontSize=11, fontName="Helvetica-Bold",
        textColor=ACCENT, alignment=TA_CENTER)

    return styles


def generate_transcript_pdf(student_info, courses, output_path):
    """
    Build the PDF.
    student_info: dict with name, student_id, address, wallet
    courses:      list of dicts from fetch_full_transcript()
    output_path:  Path object
    """
    from grading_rules import get_grade_summary, calculate_cgpa

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=1.8*cm, rightMargin=1.8*cm,
        topMargin=1.5*cm,  bottomMargin=1.5*cm,
    )

    W = A4[0] - 3.6*cm   # usable width
    styles = build_styles()
    story  = []

    # ── Header banner ─────────────────────────────────────────────────────
    header_data = [[
        Paragraph("PARIKKHCHAIN SYSTEM", styles["uni_name"]),
        Paragraph("OFFICIAL ACADEMIC TRANSCRIPT", styles["doc_title"]),
    ]]
    header_table = Table(header_data, colWidths=[W*0.6, W*0.4])
    header_table.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (0, 0), DARK_BLUE),
        ("BACKGROUND",  (1, 0), (1, 0), MID_BLUE),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",  (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING",(0,0), (-1, -1), 14),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING",(0, 0), (-1, -1), 12),
    ]))
    story.append(header_table)

    # Gold accent line
    story.append(HRFlowable(width="100%", thickness=3,
                            color=ACCENT, spaceAfter=10))

    # ── Student info block ────────────────────────────────────────────────
    now = datetime.now().strftime("%d %B %Y  %H:%M")

    info_rows = [
        [
            Paragraph("STUDENT NAME", styles["field_label"]),
            Paragraph(student_info.get("name", "—"), styles["field_value"]),
            Paragraph("STUDENT ID", styles["field_label"]),
            Paragraph(student_info.get("student_id", "—"), styles["field_value"]),
        ],
        [
            Paragraph("DEPARTMENT", styles["field_label"]),
            Paragraph("Computer Science & Engineering", styles["field_value"]),
            Paragraph("DATE ISSUED", styles["field_label"]),
            Paragraph(now, styles["field_value"]),
        ],
        [
            Paragraph("WALLET ADDRESS", styles["field_label"]),
            Paragraph(student_info.get("address", "—"), styles["field_value"]),
            Paragraph("VERIFIED ON", styles["field_label"]),
            Paragraph("Blockchain (Ethereum)", styles["field_value"]),
        ],
    ]
    info_table = Table(info_rows,
                       colWidths=[W*0.18, W*0.32, W*0.18, W*0.32])
    info_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), LIGHT_GREY),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("LINEBELOW",     (0, 0), (-1, -2), 0.5, colors.HexColor("#dddddd")),
        ("BOX",           (0, 0), (-1, -1), 1, MID_BLUE),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 14))

    # ── Course results table ──────────────────────────────────────────────
    story.append(Paragraph("COURSE-WISE RESULTS", styles["section_head"]))

    col_heads = ["Course Code", "Course Name", "Ex1/50", "Ex2/50",
                 "Total/100", "Grade", "GP", "Status", "Scrutiny"]
    col_widths = [W*0.10, W*0.28, W*0.07, W*0.07,
                  W*0.09, W*0.07, W*0.06, W*0.14, W*0.08]

    table_data = [col_heads]
    course_data_for_cgpa = []
    has_scrutiny_any = False

    for c in courses:
        if c["has_marks"]:
            gi = get_grade_summary(c["marks_obtained"])
            ex1 = str(c.get("examiner1_marks", "—"))
            ex2 = str(c.get("examiner2_marks", "—"))
            total = str(c["marks_obtained"])
            grade = gi["letter_grade"]
            gp    = f"{gi['grade_point']:.2f}"
            status = "Finalized" if c["finalized"] else c["status"].title()
            scrutiny = "Yes" if c["has_scrutiny"] else "No"
            if c["has_scrutiny"]:
                has_scrutiny_any = True
            course_data_for_cgpa.append({
                "course":  c["course_code"],
                "marks":   c["marks_obtained"],
                "credits": c["credits"],
            })
        else:
            ex1 = ex2 = total = grade = gp = "—"
            status  = "Pending"
            scrutiny = "—"

        table_data.append([
            c["course_code"],
            c["exam_name"][:35],
            ex1, ex2, total, grade, gp, status, scrutiny
        ])

    results_table = Table(table_data, colWidths=col_widths,
                          repeatRows=1)

    ts = TableStyle([
        # Header row
        ("BACKGROUND",    (0, 0), (-1, 0), DARK_BLUE),
        ("TEXTCOLOR",     (0, 0), (-1, 0), WHITE),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0), 8),
        ("ALIGN",         (0, 0), (-1, 0), "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, 0), 6),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        # Data rows
        ("FONTSIZE",      (0, 1), (-1, -1), 8),
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("ALIGN",         (2, 1), (-1, -1), "CENTER"),
        ("ALIGN",         (0, 1), (1,  -1), "LEFT"),
        ("TOPPADDING",    (0, 1), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, LIGHT_GREY]),
        ("GRID",          (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("BOX",           (0, 0), (-1, -1), 1, MID_BLUE),
    ])

    # Colour grade cells
    for row_idx, c in enumerate(courses, 1):
        if c["has_marks"]:
            gi = get_grade_summary(c["marks_obtained"])
            gc = grade_color(gi["letter_grade"])
            ts.add("TEXTCOLOR",  (5, row_idx), (5, row_idx), gc)
            ts.add("FONTNAME",   (5, row_idx), (5, row_idx), "Helvetica-Bold")

    results_table.setStyle(ts)
    story.append(results_table)
    story.append(Spacer(1, 14))

    # ── CGPA summary ──────────────────────────────────────────────────────
    if course_data_for_cgpa:
        cgpa = calculate_cgpa(course_data_for_cgpa)
        if   cgpa >= 3.75: cls_str = "First Class with Distinction"
        elif cgpa >= 3.25: cls_str = "First Class"
        elif cgpa >= 3.00: cls_str = "Second Class"
        elif cgpa >= 2.00: cls_str = "Pass"
        else:              cls_str = "Fail"

        # Use fixed row height so the large CGPA number centers vertically
        ROW_H = 52
        cgpa_data = [[
            Paragraph(f"{cgpa:.2f}", styles["cgpa_big"]),
            Paragraph("/ 4.00", styles["cgpa_label"]),
            Paragraph(cls_str.upper(), styles["class_text"]),
            Paragraph(
                f"Based on {len(course_data_for_cgpa)} finalized course(s)",
                styles["cgpa_label"]),
        ]]
        cgpa_table = Table(cgpa_data,
                           colWidths=[W*0.15, W*0.10, W*0.35, W*0.40],
                           rowHeights=[ROW_H])
        cgpa_table.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), LIGHT_BLUE),
            ("BOX",           (0, 0), (-1, -1), 1.5, MID_BLUE),
            ("LINEAFTER",     (0, 0), (2, 0),   0.5, MID_BLUE),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING",    (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ]))
        story.append(KeepTogether([
            Paragraph("CUMULATIVE PERFORMANCE", styles["section_head"]),
            cgpa_table,
        ]))
        story.append(Spacer(1, 14))

    # ── Blockchain verification block ─────────────────────────────────────
    ver_text = (
        "This transcript has been generated directly from immutable blockchain records. "
        "All marks, grades, and audit trails are stored on-chain and cannot be altered "
        "after finalization. Verify authenticity via ResultAudit.getFullTranscript() "
        f"using address: {student_info.get('address', '')}."
    )
    ver_style = ParagraphStyle(
        "ver", fontSize=7.5, fontName="Helvetica", textColor=DARK_BLUE,
        leading=11, leftIndent=8, rightIndent=8)

    ver_data = [[
        Paragraph("BLOCKCHAIN VERIFIED", ParagraphStyle(
            "vt", fontSize=8, fontName="Helvetica-Bold",
            textColor=WHITE, alignment=TA_CENTER)),
        Paragraph(ver_text, ver_style),
    ]]
    ver_table = Table(ver_data, colWidths=[W*0.20, W*0.80])
    ver_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, 0), DARK_BLUE),
        ("BACKGROUND",    (1, 0), (1, 0), LIGHT_BLUE),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("BOX",           (0, 0), (-1, -1), 1, MID_BLUE),
    ]))
    story.append(KeepTogether([
        Paragraph("VERIFICATION", styles["section_head"]),
        ver_table,
    ]))

    # ── Footer ────────────────────────────────────────────────────────────
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.5, color=MID_BLUE))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"Generated: {now}  |  ParikkhaChain Blockchain Examination System  |  "
        f"Chain ID: Ethereum (Local)  |  CONFIDENTIAL",
        styles["footer"]))

    doc.build(story)
    return output_path


# ── Entry point (called from view_result.py) ──────────────────────────────────

def generate_from_view_result(student_info, courses, out_dir=None):
    """
    Called by view_result.py after fetching blockchain data.
    student_info: {name, student_id, address}
    courses:      list from fetch_full_transcript()
    Returns path to generated PDF.
    """
    if out_dir is None:
        out_dir = Path(__file__).parent.parent / "transcripts"
    out_dir = Path(out_dir)
    out_dir.mkdir(exist_ok=True)

    sid  = student_info.get("student_id", "unknown").replace("/", "_")
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"transcript_{sid}_{ts}.pdf"

    generate_transcript_pdf(student_info, courses, path)
    return path


if __name__ == "__main__":
    # Quick test with dummy data
    dummy_student = {
        "name":       "Alice Johnson",
        "student_id": "STU0001",
        "address":    "0xAbCd1234...5678",
    }
    dummy_courses = [
        {"course_code": "CSE001", "exam_name": "CSE001 Final Examination",
         "marks_obtained": 49, "total_marks": 100, "credits": 3,
         "has_marks": True, "finalized": True, "has_scrutiny": False,
         "status": "FINALIZED", "examiner1_marks": 5, "examiner2_marks": 44},
        {"course_code": "CSE002", "exam_name": "CSE002 Final Examination",
         "marks_obtained": 76, "total_marks": 100, "credits": 3,
         "has_marks": True, "finalized": True, "has_scrutiny": True,
         "status": "FINALIZED", "examiner1_marks": 40, "examiner2_marks": 36},
    ]
    path = generate_from_view_result(dummy_student, dummy_courses)
    print(f"Test PDF: {path}")