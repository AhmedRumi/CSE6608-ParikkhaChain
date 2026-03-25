"""
ParikkhaChain - CGPA Calculator
Fetches raw marks from blockchain and calculates grades/CGPA in Python
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from blockchain_interface import BlockchainInterface, ResultAuditInterface
from grading_rules import (
    marks_to_letter_grade,
    marks_to_grade_point,
    calculate_cgpa,
    get_grade_summary,
    display_grading_scale
)
import contract_config as config
import json


def fetch_student_results_from_blockchain(student_address, exam_ids):
    """
    Fetch raw marks from blockchain for a student
    
    Args:
        student_address: Student's blockchain address
        exam_ids: List of exam IDs to fetch results for
    
    Returns:
        list: Course data with marks from blockchain
    """
    print(f"\n🔗 Fetching results from blockchain...")
    print(f"   Student: {student_address}")
    
    # Load contracts
    config.load_addresses_from_file()
    blockchain = ResultAuditInterface()
    
    courses_data = []
    
    for exam_id in exam_ids:
        try:
            # Get student's result from blockchain
            # This calls: ResultAudit.getStudentResult(examId, studentAddress)
            result = blockchain.get_contract("ResultAudit").functions.getStudentResult(
                exam_id,
                student_address
            ).call({'from': student_address})
            
            # result = (scriptId, marksObtained, totalMarks, status)
            script_id = result[0]
            marks_obtained = result[1]
            total_marks = result[2]
            status = result[3]
            
            print(f"\n   ✅ Exam {exam_id}:")
            print(f"      Script ID: {script_id}")
            print(f"      Raw Marks: {marks_obtained}/{total_marks}")
            print(f"      Status: {config.get_grade_status_name(status)}")
            
            # Add to courses (assume 3 credits each for demo)
            courses_data.append({
                'exam_id': exam_id,
                'script_id': script_id,
                'marks': marks_obtained,
                'total_marks': total_marks,
                'credits': 3  # Default, would come from exam data in production
            })
            
        except Exception as e:
            print(f"   ⚠️  Could not fetch exam {exam_id}: {e}")
    
    return courses_data


def calculate_and_display_cgpa(student_name, courses_data):
    """
    Calculate and display CGPA from blockchain marks
    
    Args:
        student_name: Student's name
        courses_data: List of courses with raw marks
    """
    print("\n" + "="*70)
    print(f"🎓 CGPA CALCULATION FOR: {student_name}")
    print("="*70)
    
    if not courses_data:
        print("⚠️  No course data available")
        return
    
    # Display each course
    print(f"\n{'Course':<15} {'Marks':<10} {'Credits':<10} {'Letter':<10} {'Grade Point':<12}")
    print("-"*70)
    
    total_points = 0.0
    total_credits = 0
    
    for course in courses_data:
        marks = course['marks']
        credits = course['credits']
        
        # Calculate grade (done in Python, NOT on blockchain)
        grade_info = get_grade_summary(marks)
        
        # Display
        course_name = f"Exam {course['exam_id']}"
        print(f"{course_name:<15} {marks:>3}/{course['total_marks']:<5} {credits:<10} "
              f"{grade_info['letter_grade']:<10} {grade_info['grade_point']:<12.2f}")
        
        total_points += grade_info['grade_point'] * credits
        total_credits += credits
    
    # Calculate CGPA
    cgpa = calculate_cgpa(courses_data)
    
    print("-"*70)
    print(f"{'TOTAL':<15} {'':<10} {total_credits:<10} {'':<10} {'':<12}")
    print("="*70)
    print(f"\n🎯 FINAL CGPA: {cgpa:.2f} / 4.00")
    print("="*70)
    
    # Classification
    if cgpa >= 3.75:
        classification = "First Class (Distinction)"
    elif cgpa >= 3.25:
        classification = "First Class"
    elif cgpa >= 3.00:
        classification = "Second Class"
    elif cgpa >= 2.00:
        classification = "Pass"
    else:
        classification = "Fail"
    
    print(f"\n🏆 Classification: {classification}")
    
    return cgpa


def demo_cgpa_calculation_from_mock_data():
    """
    Demo CGPA calculation using mock data
    (Simulates fetching from blockchain)
    """
    print("\n" + "="*70)
    print("📊 DEMO: CGPA CALCULATION FROM MOCK DATA")
    print("="*70)
    
    # Load mock data
    mock_data_file = Path(__file__).parent.parent / "mock_data" / "complete_mock_data.json"
    
    if not mock_data_file.exists():
        print("⚠️  Mock data not found. Run generate_mock_data.py first!")
        return
    
    with open(mock_data_file, 'r') as f:
        mock_data = json.load(f)
    
    students = mock_data['students']
    marks_data = mock_data['marks']
    
    # Process each student
    for student in students:
        print("\n" + "="*70)
        print(f"👤 STUDENT: {student['name']} ({student['student_id']})")
        print("="*70)
        
        # Get student's courses
        student_courses = []
        
        for exam_marks in marks_data:
            for sm in exam_marks['student_marks']:
                if sm['student_address'] == student['address']:
                    student_courses.append({
                        'exam_id': exam_marks['exam_id'],
                        'course': exam_marks['course_code'],
                        'marks': sm['final_marks'],  # Raw marks (from blockchain)
                        'total_marks': sm['total_marks'],
                        'credits': exam_marks.get('credits', 3)
                    })
        
        if student_courses:
            # Display course-wise results
            print(f"\n{'Course':<15} {'Raw Marks':<15} {'Credits':<10} {'Letter':<10} {'GP':<10}")
            print("-"*70)
            
            for course in student_courses:
                grade_info = get_grade_summary(course['marks'])
                print(f"{course['course']:<15} {course['marks']:>3}/{course['total_marks']:<10} "
                      f"{course['credits']:<10} {grade_info['letter_grade']:<10} "
                      f"{grade_info['grade_point']:<10.2f}")
            
            # Calculate CGPA
            cgpa = calculate_cgpa(student_courses)
            
            print("-"*70)
            print(f"\n🎯 CGPA: {cgpa:.2f}/4.00")
            
            # Classification
            if cgpa >= 3.75:
                classification = "First Class (Distinction)"
            elif cgpa >= 3.25:
                classification = "First Class"
            elif cgpa >= 3.00:
                classification = "Second Class"
            elif cgpa >= 2.00:
                classification = "Pass"
            else:
                classification = "Fail"
            
            print(f"🏆 Classification: {classification}")


def main():
    """Main function"""
    print("\n" + "="*70)
    print("🎓 PARIKKHCHAIN CGPA CALCULATOR")
    print("="*70)
    
    # Display grading scale
    display_grading_scale()
    
    # Demo with mock data
    demo_cgpa_calculation_from_mock_data()
    
    print("\n" + "="*70)
    print("💡 KEY POINTS:")
    print("="*70)
    print("   1. Blockchain stores: RAW MARKS only (0-100)")
    print("   2. Python calculates: Letter grades (A+, A, B+, etc.)")
    print("   3. Python calculates: Grade points (4.0, 3.75, etc.)")
    print("   4. Python calculates: CGPA out of 4.00")
    print()
    print("   This separation ensures:")
    print("   ✅ Blockchain stays simple (just numbers)")
    print("   ✅ Grading rules can be updated without changing blockchain")
    print("   ✅ Different universities can use same blockchain")
    print("="*70)
    print()


if __name__ == "__main__":
    main()