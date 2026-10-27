"""Subjects, grades and the sample marks every new student starts with.

Real results are not available to this project, so when a student enrols their
face for the first time they get random but believable marks for semesters 1-5
and attendance for the current semester. Teachers with the right permission (or
admins) can correct any number afterwards.
"""
import random
import re

from . import db, syllabus

CURRENT_SEMESTER = 6   # five semesters are finished, the sixth is running
MAX_INTERNAL = 50      # CIE
MAX_EXTERNAL = 50      # SEE

# The real courses of the 2023-04 IS curriculum (see app/syllabus.py), semester by semester.
SUBJECTS = {sem: syllabus.core_courses(sem) for sem in range(1, 9)}

GRADES = [(floor, letter) for floor, letter, _ in syllabus.GRADES]
GRADE_POINTS = {letter: points for _, letter, points in syllabus.GRADES} | {"F": 0}
PASS_PERCENT = syllabus.PASS_PERCENT


def grade(percent: float) -> str:
    return next((g for floor, g in GRADES if percent >= floor), "F")


def branch_of(email: str) -> str:
    """NNM23IS186 -> IS. Anything that doesn't look like a roll number gets a blank branch."""
    m = re.match(r"^[a-z]{3}\d{2}([a-z]{2})\d+@", email.lower())
    return m.group(1).upper() if m else ""


ROLL = re.compile(r"^[a-z]{3}\d{2}[a-z]{2}\d{3}$", re.I)


def clean_name(name: str, email: str = "") -> str:
    """College Google names look like "NNM23IS186 SRUJAN M PADMASHALI": drop the USN, and soften all capitals.

    "NNM23IS186 SRUJAN M PADMASHALI" -> "Srujan M Padmashali". A name that is only a USN stays as it is.
    """
    words = (name or "").split()
    if len(words) > 1 and ROLL.match(words[0]):
        words = words[1:]
    text = " ".join(words)
    return (text.title() if text.isupper() and not ROLL.match(text) else text) or name


def _marks(rng: random.Random) -> tuple[int, int]:
    """Internal and external marks that rise and fall together, like a real student's do."""
    ability = rng.gauss(0.72, 0.12)
    clamp = lambda x, top: max(0, min(top, round(x)))  # noqa: E731
    internal = clamp((ability + rng.gauss(0, 0.06)) * MAX_INTERNAL + 3, MAX_INTERNAL)
    external = clamp((ability + rng.gauss(0, 0.1)) * MAX_EXTERNAL, MAX_EXTERNAL)
    # Passing an exam needs 40%; keep the sample data to students who did pass.
    return max(internal, 22), max(external, 20)


def sample_codes() -> set[str]:
    """The subject codes sample records use now (older versions used made-up codes)."""
    return {code for sem in range(1, CURRENT_SEMESTER + 1) for code, _ in SUBJECTS[sem]}


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
        attended = min(total, round(total * rng.uniform(0.7, 1.0)))
        attendance.append({"email": email, "semester": CURRENT_SEMESTER, "code": code, "subject": subject,
                           "attended": attended, "total": total})
    return marks, attendance


SEEDED_BY = "demo seed"   # profiles made by app/seed.py carry a made-up name until the real student enrols


def adopt_name(email: str, name: str) -> None:
    """A sample-data student signed in for real: show their real name instead of the USN placeholder."""
    name = clean_name(name, email)
    profile = db.get_profile(email)
    # "sample data" profiles from older versions may still carry a made-up name; the signed-in person's own
    # Google name is always right for their own profile. A name a teacher or admin typed in is left alone.
    if (profile and profile["updated_by"] in (SEEDED_BY, "sample data") and name and not ROLL.match(name)
            and profile["name"] != name):
        db.rename_profile(email, name, email)


def ensure_student(email: str, name: str, by: str = "sample data") -> bool:
    """Give a student their sample records the first time. Returns True if they were created.

    A student that app/seed.py made up gets their real name when they enrol.
    """
    name = clean_name(name, email)
    existing = db.get_profile(email)
    if existing:
        if by != SEEDED_BY:
            adopt_name(email, name)
        return False
    marks, attendance = sample_records(email)
    db.save_student(
        {"email": email, "name": name, "branch": branch_of(email), "semester": CURRENT_SEMESTER},
        marks, attendance, by,
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
            "required_percent": syllabus.REQUIRED_ATTENDANCE, "condonable_percent": syllabus.CONDONABLE_TO}
