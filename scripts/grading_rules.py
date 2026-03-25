"""
ParikkhaChain - Grading Rules & CGPA Calculation
Defines university grading system for converting marks to CGPA
"""

# Grading Scale (out of 4.0)
# Based on standard Bangladeshi university grading system
GRADING_SCALE = [
    {"min_marks": 80, "max_marks": 100, "letter_grade": "A+", "grade_point": 4.00},
    {"min_marks": 75, "max_marks": 79,  "letter_grade": "A",  "grade_point": 3.75},
    {"min_marks": 70, "max_marks": 74,  "letter_grade": "A-", "grade_point": 3.50},
    {"min_marks": 65, "max_marks": 69,  "letter_grade": "B+", "grade_point": 3.25},
    {"min_marks": 60, "max_marks": 64,  "letter_grade": "B",  "grade_point": 3.00},
    {"min_marks": 55, "max_marks": 59,  "letter_grade": "B-", "grade_point": 2.75},
    {"min_marks": 50, "max_marks": 54,  "letter_grade": "C+", "grade_point": 2.50},
    {"min_marks": 45, "max_marks": 49,  "letter_grade": "C",  "grade_point": 2.25},
    {"min_marks": 40, "max_marks": 44,  "letter_grade": "D",  "grade_point": 2.00},
    {"min_marks": 0,  "max_marks": 39,  "letter_grade": "F",  "grade_point": 0.00}
]


def marks_to_letter_grade(marks):
    """
    Convert numerical marks to letter grade
    
    Args:
        marks (int/float): Marks obtained (0-100)
    
    Returns:
        str: Letter grade (A+, A, A-, B+, B, B-, C+, C, D, F)
    """
    marks = round(marks)  # Round to nearest integer
    
    for grade_rule in GRADING_SCALE:
        if grade_rule["min_marks"] <= marks <= grade_rule["max_marks"]:
            return grade_rule["letter_grade"]
    
    # Default to F if out of range
    return "F"


def marks_to_grade_point(marks):
    """
    Convert numerical marks to grade point (out of 4.0)
    
    Args:
        marks (int/float): Marks obtained (0-100)
    
    Returns:
        float: Grade point (0.0 - 4.0)
    """
    marks = round(marks)  # Round to nearest integer
    
    for grade_rule in GRADING_SCALE:
        if grade_rule["min_marks"] <= marks <= grade_rule["max_marks"]:
            return grade_rule["grade_point"]
    
    # Default to 0.0 if out of range
    return 0.0


def calculate_cgpa(courses_data):
    """
    Calculate CGPA from multiple courses
    
    Args:
        courses_data (list): List of dicts with 'marks' and 'credits'
                            Example: [
                                {'course': 'CSE6608', 'marks': 82, 'credits': 3},
                                {'course': 'CSE6601', 'marks': 75, 'credits': 3}
                            ]
    
    Returns:
        float: CGPA out of 4.0
    """
    if not courses_data:
        return 0.0
    
    total_points = 0.0
    total_credits = 0
    
    for course in courses_data:
        marks = course['marks']
        credits = course.get('credits', 3)  # Default to 3 credits
        
        grade_point = marks_to_grade_point(marks)
        total_points += grade_point * credits
        total_credits += credits
    
    if total_credits == 0:
        return 0.0
    
    cgpa = total_points / total_credits
    return round(cgpa, 2)  # Round to 2 decimal places


def calculate_semester_gpa(semester_courses):
    """
    Calculate GPA for a single semester
    Same as CGPA but for one semester only
    
    Args:
        semester_courses (list): List of courses with marks and credits
    
    Returns:
        float: GPA for the semester
    """
    return calculate_cgpa(semester_courses)  # Same calculation


def get_grade_summary(marks):
    """
    Get complete grade information for given marks
    
    Args:
        marks (int/float): Marks obtained (0-100)
    
    Returns:
        dict: Complete grade info
    """
    return {
        "marks": round(marks, 2),
        "letter_grade": marks_to_letter_grade(marks),
        "grade_point": marks_to_grade_point(marks),
        "status": "Pass" if marks >= 40 else "Fail"
    }


def display_grading_scale():
    """Display the complete grading scale"""
    print("\n" + "="*70)
    print("📊 UNIVERSITY GRADING SCALE (Out of 4.0)")
    print("="*70)
    print(f"{'Marks Range':<15} {'Letter Grade':<15} {'Grade Point':<15} {'Status':<10}")
    print("-"*70)
    
    for rule in GRADING_SCALE:
        marks_range = f"{rule['min_marks']}-{rule['max_marks']}"
        status = "Pass" if rule['min_marks'] >= 40 else "Fail"
        print(f"{marks_range:<15} {rule['letter_grade']:<15} {rule['grade_point']:<15.2f} {status:<10}")
    
    print("="*70)
    print("\n💡 Notes:")
    print("   • Minimum passing marks: 40/100")
    print("   • Minimum passing grade point: 2.00")
    print("   • Maximum CGPA: 4.00")
    print()


def example_usage():
    """Example usage of grading functions"""
    print("\n" + "="*70)
    print("📖 GRADING SYSTEM EXAMPLES")
    print("="*70)
    
    # Example 1: Single marks conversion
    print("\nExample 1: Convert marks to grade")
    test_marks = [95, 82, 75, 68, 55, 42, 35]
    
    print(f"\n{'Marks':<10} {'Letter':<10} {'Grade Point':<15} {'Status':<10}")
    print("-"*50)
    for marks in test_marks:
        grade_info = get_grade_summary(marks)
        print(f"{marks:<10} {grade_info['letter_grade']:<10} "
              f"{grade_info['grade_point']:<15.2f} {grade_info['status']:<10}")
    
    # Example 2: CGPA calculation
    print("\n" + "="*70)
    print("Example 2: Calculate CGPA")
    print("="*70)
    
    student_courses = [
        {'course': 'CSE6608', 'marks': 82, 'credits': 3},
        {'course': 'CSE6601', 'marks': 75, 'credits': 3},
        {'course': 'CSE6603', 'marks': 88, 'credits': 3},
        {'course': 'MATH301', 'marks': 70, 'credits': 3}
    ]
    
    print("\nStudent Courses:")
    print(f"{'Course':<10} {'Marks':<10} {'Credits':<10} {'Letter':<10} {'Grade Point':<12}")
    print("-"*60)
    
    for course in student_courses:
        grade_info = get_grade_summary(course['marks'])
        print(f"{course['course']:<10} {course['marks']:<10} {course['credits']:<10} "
              f"{grade_info['letter_grade']:<10} {grade_info['grade_point']:<12.2f}")
    
    cgpa = calculate_cgpa(student_courses)
    print("-"*60)
    print(f"{'CGPA:':<10} {'':<10} {'12 credits':<10} {'':<10} {cgpa:<12.2f}")
    print("="*70)


if __name__ == "__main__":
    # Display grading scale
    display_grading_scale()
    
    # Show examples
    example_usage()