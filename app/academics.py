"""Subjects, grades and the sample marks every new student starts with.

Real results are not available to this project, so when a student enrols their
face for the first time they get random but believable marks for semesters 1-5
and attendance for the current semester. Teachers with the right permission (or
admins) can correct any number afterwards.
"""
import random
import re

from . import db

CURRENT_SEMESTER = 6   # five semesters are finished, the sixth is running
MAX_INTERNAL = 50
MAX_EXTERNAL = 50

SUBJECTS = {
    1: [("21MA101", "Calculus and Linear Algebra"), ("21PH102", "Engineering Physics"),
        ("21CS103", "Problem Solving with C"), ("21EE104", "Basic Electrical Engineering"),
        ("21ME105", "Engineering Graphics"), ("21HS106", "Communication Skills")],
    2: [("21MA201", "Differential Equations"), ("21CH202", "Engineering Chemistry"),
        ("21CS203", "Data Structures"), ("21EC204", "Basic Electronics"),
        ("21CS205", "Python Programming"), ("21HS206", "Environmental Studies")],
    3: [("21MA301", "Discrete Mathematics"), ("21IS302", "Digital Logic Design"),
        ("21IS303", "Object Oriented Programming"), ("21IS304", "Computer Organisation"),
        ("21IS305", "Analysis of Algorithms"), ("21HS306", "Universal Human Values")],
    4: [("21MA401", "Probability and Statistics"), ("21IS402", "Operating Systems"),
        ("21IS403", "Database Management Systems"), ("21IS404", "Computer Networks"),
        ("21IS405", "Software Engineering"), ("21IS406", "Microprocessors")],
    5: [("21IS501", "Theory of Computation"), ("21IS502", "Web Technologies"),
        ("21IS503", "Artificial Intelligence"), ("21IS504", "Information Security"),
        ("21IS505", "Cloud Computing"), ("21IS506", "Data Analytics Lab")],
    6: [("21IS601", "Machine Learning"), ("21IS602", "Compiler Design"),
        ("21IS603", "Big Data Technologies"), ("21IS604", "Mobile Application Development"),
        ("21IS605", "Professional Elective"), ("21IS606", "Mini Project")],
}

GRADES = [(90, "O"), (80, "A+"), (70, "A"), (60, "B+"), (50, "B"), (40, "C")]
PASS_PERCENT = 40


def grade(percent: float) -> str:
    return next((g for floor, g in GRADES if percent >= floor), "F")


def branch_of(email: str) -> str:
    """NNM23IS186 -> IS. Anything that doesn't look like a roll number gets a blank branch."""
    m = re.match(r"^[a-z]{3}\d{2}([a-z]{2})\d+@", email.lower())
    return m.group(1).upper() if m else ""


def _marks(rng: random.Random) -> tuple[int, int]:
    """Internal and external marks that rise and fall together, like a real student's do."""
    ability = rng.gauss(0.72, 0.12)
    clamp = lambda x, top: max(0, min(top, round(x)))  # noqa: E731
    internal = clamp((ability + rng.gauss(0, 0.06)) * MAX_INTERNAL + 3, MAX_INTERNAL)
    external = clamp((ability + rng.gauss(0, 0.1)) * MAX_EXTERNAL, MAX_EXTERNAL)
    # Passing an exam needs 40%; keep the sample data to students who did pass.
    return max(internal, 22), max(external, 20)


def sample_records(email: str) -> tuple[list[dict], list[dict]]:
    """Random marks (semesters 1-5) and attendance (current semester) for one student.

    Seeded by the email, so the same student always gets the same numbers.
    """
    rng = random.Random(email)
    marks = []
    for sem in range(1, CURRENT_SEMESTER):
        for code, subject in SUBJECTS[sem]:
            internal, external = _marks(rng)
            marks.append({"email": email, "semester": sem, "code": code, "subject": subject,
                          "internal": internal, "external": external})
    attendance = []
    for code, subject in SUBJECTS[CURRENT_SEMESTER]:
        total = rng.randint(34, 48)
        attended = min(total, round(total * rng.uniform(0.68, 1.0)))
        attendance.append({"email": email, "semester": CURRENT_SEMESTER, "code": code, "subject": subject,
                           "attended": attended, "total": total})
    return marks, attendance


def ensure_student(email: str, name: str) -> bool:
    """Give a student their sample records the first time. Returns True if they were created."""
    if db.get_profile(email):
        return False
    marks, attendance = sample_records(email)
    db.save_student(
        {"email": email, "name": name, "branch": branch_of(email), "semester": CURRENT_SEMESTER},
        marks, attendance, "sample data",
    )
    return True


# --- What the pages show -----------------------------------------------------------

def marks_report(email: str) -> dict:
    semesters: dict[int, list[dict]] = {}
    for row in db.list_marks(email):
        total = row["internal"] + row["external"]
        percent = total / (MAX_INTERNAL + MAX_EXTERNAL) * 100
        semesters.setdefault(row["semester"], []).append({
            "code": row["code"], "subject": row["subject"], "internal": row["internal"],
            "external": row["external"], "total": total, "grade": grade(percent),
            "passed": percent >= PASS_PERCENT,
        })
    out = []
    for sem, subjects in sorted(semesters.items()):
        total = sum(s["total"] for s in subjects)
        top = len(subjects) * (MAX_INTERNAL + MAX_EXTERNAL)
        percent = round(total / top * 100, 1)
        out.append({"semester": sem, "subjects": subjects, "total": total, "max": top,
                    "percent": percent, "grade": grade(percent)})
    overall = round(sum(s["total"] for s in out) / max(1, sum(s["max"] for s in out)) * 100, 1) if out else 0
    return {"semesters": out, "overall_percent": overall}


def attendance_report(email: str) -> dict:
    subjects = []
    for row in db.list_attendance(email):
        percent = round(row["attended"] / row["total"] * 100, 1) if row["total"] else 0
        subjects.append({**{k: row[k] for k in ("semester", "code", "subject", "attended", "total")},
                         "percent": percent})
    attended = sum(s["attended"] for s in subjects)
    total = sum(s["total"] for s in subjects)
    return {"subjects": subjects, "overall_percent": round(attended / total * 100, 1) if total else 0,
            "required_percent": 75}
