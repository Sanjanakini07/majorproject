"""The official B.Tech. IS curriculum (2023-04 regulations), read from app/data/syllabus_is_2023.json.

That file is made from the university's syllabus PDF by scripts/import_syllabus.py. Everything about
subjects comes from here: the Notes library, the subjects in marks and attendance, the timetables,
and what the assistant knows about each course and about the regulations.
"""
import json
import re
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data" / "syllabus_is_2023.json"

# Attendance and grading, as in sections 9 and 11.7 of the regulations.
REQUIRED_ATTENDANCE = 85     # percent, in every course
CONDONABLE_TO = 75           # the principal can condone up to 10%; below 75% the student can't write the SEE ('N' grade)
GRADES = [(90, "O", 10), (80, "A+", 9), (70, "A", 8), (60, "B+", 7), (55, "B", 6), (50, "C", 5), (40, "P", 4)]
PASS_PERCENT = 40


@lru_cache(maxsize=1)
def data() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


def course(code: str) -> dict | None:
    return data()["courses"].get(code)


def semester_courses(sem: int) -> list[dict]:
    """Every course listed for an IS student in this semester: {"code", "title", "kind", "credits", "text"}."""
    out = []
    for row in data()["semesters"].get(str(sem), []):
        c = course(row["code"])
        if c:
            out.append({**c, "kind": row["kind"]})
    return out


def core_courses(sem: int) -> list[tuple[str, str]]:
    """The credit-carrying core courses of a semester, as (code, title): what marks, attendance and timetables use.

    Internships and the major project are left out (no classes, no internal tests), and so are 0-credit courses.
    """
    return [(c["code"], c["title"]) for c in semester_courses(sem)
            if c["kind"] == "Core" and (c["credits"] or 0) > 0 and not c["code"].startswith("UC")]


def is_lab(code: str) -> bool:
    return bool(re.match(r"^IS\d6\d\d", code))      # IS1601, IS3602 ...: the scheme's "PCC (Lab)" courses


def listed() -> list[tuple[int, dict]]:
    """(semester, course) for every course in the IS semester lists. A course listed twice is kept in the first."""
    seen, rows = set(), []
    for sem in range(1, 9):
        for c in semester_courses(sem):
            if c["code"] not in seen:
                seen.add(c["code"])
                rows.append((sem, c))
    return rows


def note_subjects() -> list[tuple[str, int, str]]:
    """(code, semester, name) for the Notes library."""
    return [(c["code"], sem, c["title"] if c["kind"] == "Core" else f"{c['title']} ({c['kind']})") for sem, c in listed()]


UNIT = re.compile(r"^UNIT\s*[-–]?\s*([IVX]+)\b", re.I)
TOPIC = re.compile(r"^(.{3,90}?)\s+(\d{1,2})\s*(?:Hours?|Hrs?)\.?\s*$", re.I)


def outline(code: str) -> str:
    """Units and their topic headings, short enough to list a whole semester: "Unit I: Introduction, ...; Unit II: ..."."""
    return "; ".join(f"{name}: {', '.join(topics)}" for name, topics in units(code) if topics)


def _section(text: str, start: str, stop: str) -> list[str]:
    """Numbered lines of a section ("Course Outcomes", "TEXTBOOKS") until the next heading."""
    lines, inside = [], False
    for raw in text.splitlines():
        line = raw.strip()
        if re.match(start, line, re.I):
            inside = True
            line = re.sub(start + r"[^:]*:?", "", line, flags=re.I).strip()
            if not line:
                continue
        elif inside and re.match(stop, line, re.I):
            break
        if inside and line:
            if re.match(r"^\d+[.)]\s*", line) or not lines:
                lines.append(re.sub(r"^\d+[.)]\s*", "", line))
            else:
                lines[-1] += " " + line          # a numbered item wrapped onto the next line
    return [l for l in lines if len(l) > 3 and not re.match(r"^(At the end of the course|The students? will be able)", l, re.I)]


def study_notes(code: str, sem: int) -> str:
    """A unit-by-unit study note made only from the course's own syllabus: topics, outcomes, books, and a plan."""
    c = course(code)
    if not c:
        return ""
    text = c["text"]
    parts = [f"Study notes for {c['title']} ({code}), semester {sem}. Made from the official syllabus "
             f"(2023-04 regulations); open the Syllabus note for every detail."]
    found = [(name, topics) for name, topics in units(code) if topics]
    for name, topics in found:
        parts.append(f"\n{name}\n" + "\n".join(f"- {t}" for t in topics))
    if not found:
        experiments = _section(text, r"(Suggested )?List of (Experiments|Programs|Exercises|Activities)", r"^(Course Outcomes|TEXT)")
        if experiments:
            parts.append("\nWhat you will do\n" + "\n".join(f"- {e}" for e in experiments[:12]))
        else:
            objectives = _section(text, r"Course Objectives", r"^(UNIT|Course Outcomes|Module|TEXT)")
            if objectives:
                parts.append("\nWhat this course is about\n" + "\n".join(f"- {o}" for o in objectives[:6]))
    outcomes = _section(text, r"Course Outcomes", r"^(Course Outcomes Mapping|Program Outcomes|TEXT ?BOOKS?|REFERENCE|E ?Books)")
    if outcomes:
        parts.append("\nBy the end you should be able to\n" + "\n".join(f"- {o}" for o in outcomes[:6]))
    books = _section(text, r"TEXT ?BOOKS?", r"^(REFERENCE|E ?Books|MOOC|Course Outcomes)")
    if books:
        parts.append("\nTextbooks\n" + "\n".join(f"- {b}" for b in books[:4]))
    if found:
        parts.append(f"\nHow to study it\n- Go one unit at a time: {', '.join(n for n, _ in found)}.\n"
                     f"- For each topic, make a one-page summary and solve the end-of-chapter problems in the textbook.\n"
                     f"- Before the mid-semester exams, revise the units covered so far; before the SEE, all units.")
    return "\n".join(parts)


def units(code: str) -> list[tuple[str, list[str]]]:
    """[("Unit I", [topic, ...]), ...] from the course's syllabus text."""
    c = course(code)
    if not c:
        return []
    units, current = [], None
    for raw in c["text"].splitlines():
        line = raw.strip()
        if units and re.match(r"^(Course Outcomes|TEXT ?BOOKS?|REFERENCE)", line, re.I):
            break
        u = UNIT.match(line)
        if u:
            current = [f"Unit {u.group(1).upper()}", []]
            units.append(current)
            continue
        if not current or line.startswith("(") or len(current[1]) >= 6:
            continue
        # Topic headings come as "INTRODUCTION 9 Hours", "Regression: linear ...", or a short line of their own.
        t = TOPIC.match(line)
        if t:
            heading = t.group(1)
        elif ":" in line[:70] and line.index(":") > 3:
            heading = line[:line.index(":")]
        elif len(line) < 60 and not line.endswith((".", ",")) and line[:1].isupper() and not re.search(r"\d", line):
            heading = line
        else:
            continue
        heading = heading.split(". ")[-1].strip(" :-–")      # "communication. Threads" (a wrapped line) -> "Threads"
        heading = heading.title() if heading.isupper() else heading
        if 2 < len(heading) < 70 and heading[:1].isupper() and heading not in current[1]:
            current[1].append(heading)
    return [(name, topics) for name, topics in units]


# The elective streams, as in the "List of Professional Elective Courses" table: (Group 1 codes, Group 2 codes).
STREAMS = {
    "IT Management": (["IS2201-1", "IS3201-1", "IS3202-1", "IS1201-1"], ["IS2301-1", "IS3301-1", "IS1301-1", "IS2302-1"]),
    "Software Engineering and Development": (["IS3211-1", "IS2212-1", "IS2213-1", "IS2214-1"],
                                             ["IS2311-1", "IS2312-1", "IS3313-1", "IS2314-1"]),
    "Networks and Security": (["IS4221-1", "IS4222-1", "IS4223-1", "IS4224-1"], ["IS3321-1", "IS4321-1", "IS4322-1", "IS4323-1"]),
    "Data Science and Machine Intelligence": (["IS2231-1", "IS2232-1", "IS3233-1", "IS1231-1"],
                                              ["IS3331-1", "IS3332-1", "IS3333-1", "IS3334-1"]),
    "General": (["IS3241-1", "IS3242-1", "IS3243-1", "IS3244-1"], ["IS3341-1", "IS3342-1", "IS3343-1", "IS3344-1"]),
}


def streams_text() -> str:
    name = lambda code: course(code)["title"] if course(code) else code  # noqa: E731
    return "\n".join(f"{stream} stream electives: Group 1: {', '.join(map(name, g1))}. Group 2: {', '.join(map(name, g2))}."
                     for stream, (g1, g2) in STREAMS.items())


# What students call courses. Each maps to a word that must appear in the course title.
ALIASES = {"os": "operating systems", "dbms": "database management", "db": "database", "cn": "networking",
           "dcn": "data communication", "networks": "networking", "ml": "machine learning", "ai": "artificial intelligence",
           "daa": "analysis of algorithms", "ada": "analysis of algorithms", "algorithms": "analysis of algorithms",
           "oop": "object oriented programming", "oops": "object oriented programming", "java": "object oriented programming",
           "ds": "data structures", "dsa": "data structures", "coa": "computer organization", "co": "computer organization",
           "toc": "automata", "atcd": "automata", "cd": "compiler", "compiler": "compiler", "ins": "network security",
           "iwp": "web programming", "web": "web programming", "se": "software engineering", "sepm": "software engineering",
           "maths": "math", "math": "math", "python": "python", "c": "c programming", "dld": "digital logic",
           "iot": "internet of things", "mern": "mern", "hacking": "ethical hacking", "ipr": "ipr", "evs": "environmental",
           "uhv": "universal human values", "bee": "electrical", "electronics": "electronics", "physics": "physics",
           "chemistry": "chemistry", "english": "english", "kannada": "kannada", "statistics": "statistics",
           "probability": "probability", "linear algebra": "linear algebra", "unix": "unix", "dl": "deep learning",
           "machine learning": "machine learning", "information security": "network security",
           "network security": "network security", "cyber security": "cyber security", "data science": "data science",
           "software testing": "software testing", "cloud": "cloud computing", "blockchain": "blockchain"}
_STOP = {"and", "of", "the", "to", "in", "for", "with", "its", "on", "using", "introduction", "fundamentals", "basic",
         "basics", "applied", "theory", "design", "systems", "development", "programming", "engineering", "applications",
         "foundations"}


def find_courses(q: str) -> list[tuple[int, dict]]:
    """Courses a question names: by code, by full or distinctive title words, or by a common short name (OS, DBMS)."""
    q = q.lower()
    words = set(re.findall(r"[a-z+]+", q))
    found = []
    for sem, c in listed():
        title = c["title"].lower()
        key = [w for w in re.findall(r"[a-z+]+", title) if w not in _STOP and len(w) > 2]
        if (c["code"].lower() in q or c["code"].lower().split("-")[0] in q or title in q
                or (len(key) >= 2 and all(w in words for w in key))
                or (len(key) == 1 and key[0] in words and len(key[0]) > 4)
                or any(a in words and ALIASES[a] in title for a in ALIASES if " " not in a)
                or any(a in q and ALIASES[a] in title for a in ALIASES if " " in a)):
            found.append((sem, c))
    # Prefer core courses, and don't let a vague word ("security", "web") pull in a whole semester of electives.
    found.sort(key=lambda x: x[1]["kind"] != "Core")
    return found[:3]


def course_text(c: dict, sem: int | None = None) -> str:
    """The whole syllabus of one course, with a header line the assistant can quote."""
    where = f"Semester {sem}, " if sem else ""
    kind = c.get("kind") or c.get("type") or ""
    credits = f", {c['credits']} credits" if c.get("credits") is not None else ""
    return (f"Syllabus of {c['title']} ({c['code']}). {where}{kind}{credits}. "
            f"From the B.Tech. Information Science and Engineering curriculum, 2023-04 regulations.\n{c['text']}")


def other_courses() -> list[dict]:
    """Courses in the PDF that aren't in an IS semester list (open electives from other departments, bridge courses)."""
    listed = {code for code, _, _ in note_subjects()}
    return [c for code, c in data()["courses"].items() if code not in listed]


def regulations() -> list[dict]:
    return data()["regulations"]
