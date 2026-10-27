"""Default data, so no page opens empty.

On the first start this fills in: students NNM23IS000 to NNM23IS300 (named by USN until they sign in, with
sample marks and attendance), timetables, college information for the assistant and upcoming events.
The Notes library and the assistant's knowledge of every course and of the regulations come from the
official IS syllabus (app/syllabus.py), so they are real, not made up.
Each step runs once (a marker is saved in the database), so anything an admin later edits or deletes stays
that way. Turn it off with SEED_DEMO_DATA=0 in .env.
"""
import logging
import threading
from datetime import date, timedelta

from . import academics, config, db, library, rag, syllabus

log = logging.getLogger(__name__)

MARKER = "demo_data_v1"
SYLLABUS_MARKER = "syllabus_2023_04_v1"
STUDY_MARKER = "study_notes_v1"
USER = "sample data"
FIRST_ROLL, LAST_ROLL = 0, 300


# --- Timetable -----------------------------------------------------------------------

SLOTS = ["9:00 AM to 10:00 AM", "10:00 AM to 11:00 AM", "11:15 AM to 12:15 PM", "12:15 PM to 1:15 PM",
         "2:00 PM to 3:00 PM", "3:00 PM to 4:00 PM"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def timetable_entries() -> list[tuple[str, str]]:
    """One knowledge entry per semester and weekday, with that semester's real courses, read-out friendly."""
    out = []
    for sem in range(1, 9):
        subjects = academics.SUBJECTS.get(sem) or [("UC3002-1", "Major Project Phase II (project work)")]
        if sem == 8:
            subjects = [("UC3002-1", "Major Project Phase II (project work)"), ("UC2001-1", "Internship-II reviews")]
        for d, day in enumerate(DAYS):
            lines = []
            for offset, slot in enumerate(SLOTS):
                code, name = subjects[(d + offset) % len(subjects)]
                room = f"LH-{sem}{(d + offset) % 4 + 1:02d}"
                lab = " (lab)" if syllabus.is_lab(code) else ""
                lines.append(f"{slot}: {name}{lab}, {code}, room {room}")
            note = " Saturday classes end at 1:15 PM, with no afternoon session." if day == "Saturday" else ""
            body = (f"Semester {sem} timetable for {day}. " + ". ".join(lines[:4 if day == "Saturday" else 6])
                    + f". Tea break 11:00 AM to 11:15 AM, lunch 1:15 PM to 2:00 PM.{note}")
            out.append((f"Timetable: Semester {sem}, {day}", body))
    return out


# --- College information ------------------------------------------------------------------

INFO = [
    ("Library timings", "The central library is open from 8:30 AM to 8:00 PM on weekdays and from 9:00 AM to 1:00 PM on Saturdays. It is closed on Sundays and public holidays. Students can borrow up to four books for 14 days. A late fee of 2 rupees per book per day applies."),
    ("Lost ID card", "If you lose your college ID card, report it at the administrative office and fill in the duplicate ID card form. A replacement is usually issued within a week. A fee of 100 rupees is charged."),
    ("Fee payment", "Tuition and other fees are paid at the accounts section on the ground floor of the administrative block, from 10:00 AM to 3:00 PM on working days. Online payment is also open through the college portal. Late payment after the due date carries a fine of 50 rupees per day."),
    ("Hostel", "Separate hostels are available for boys and girls. The mess serves breakfast from 7:30 to 9:00 AM, lunch from 12:30 to 2:00 PM, snacks from 4:30 to 5:30 PM and dinner from 7:30 to 9:00 PM. Hostel gates close at 9:30 PM. Apply for a room at the hostel office at the start of the academic year."),
    ("Canteen", "The main canteen is open from 8:00 AM to 5:30 PM on working days. It serves breakfast, a South Indian lunch, snacks and juices. A smaller coffee counter near the library stays open until 6:30 PM."),
    ("Placement cell", "The training and placement cell runs aptitude, coding and interview practice sessions from the fifth semester. Companies visit from August to February. Students need at least 60 percent marks and no active backlogs to sit for placements. Register on the placement portal with your resume."),
    ("Sports and clubs", "The college has cricket, football, volleyball, basketball and badminton teams, and a gym. Technical clubs include coding, robotics, AI and cyber security. Cultural clubs cover music, dance, drama and photography. Join through the student activities office or the club's stall during the orientation week."),
    ("Wi-Fi and computer labs", "Campus Wi-Fi is free for students. Use your roll number as the user name. Computer labs are open until 5:00 PM on working days, and the department lab stays open until 6:00 PM during project work. Report problems at the IT help desk."),
    ("Scholarships", "Merit and government scholarships are handled by the scholarship section in the administrative block. Applications open in August on the state scholarship portal. Bring your income certificate, caste certificate if applicable, marks cards and bank passbook."),
    ("Department of Information Science", "The Information Science and Engineering department is on the second floor of the academic block. The head of department's office is open from 9:30 AM to 4:30 PM. Major Project Phase I is in the seventh semester and Phase II in the eighth, as in the 2023-04 curriculum."),
    # These three follow the 2023-04 regulations (sections 9 and 11); the full sections are in the knowledge base too.
    ("Attendance rules (2023 regulations)", "Every course needs at least 85 percent attendance. The principal can condone up to 10 percent for reasons such as medical grounds or taking part in university sports, cultural activities, seminars, workshops and paper presentations. A student with less than 75 percent in a course can't write that course's semester end exam (SEE) and gets an N grade, and has to repeat the course when it is offered next. Attendance is told to students in the first week of every month."),
    ("Evaluation and grading rules (2023 regulations)", "Each course has 50 marks of continuous internal evaluation (CIE) and 50 marks of semester end examination (SEE). CIE has two mid-semester examinations (40 marks) and quizzes, tutorials and assignments (10 marks); for project based and integrated lab courses the PBL or lab work counts too. To pass, a student needs 40 percent of the course total (CIE plus SEE). Grades are absolute: O for 90 percent and above (10 points), A+ for 80 to 89 (9), A for 70 to 79 (8), B+ for 60 to 69 (7), B for 55 to 59 (6), C for 50 to 54 (5), P for 40 to 49 (4) and F below 40 (0). A CGPA of 7 or more is first class with distinction, 6 to 6.99 first class and 5 to 5.99 second class. Below a CGPA of 5 a student is on academic probation."),
    ("Academic calendar (2023 regulations)", "There are two main semesters a year: the odd semester from August to December and the even semester from January to May, each of about 20 weeks. An optional summer semester runs in the vacation after the even semester, mainly to help students clear courses they failed."),
]
# Older versions added these made-up rules; the syllabus versions above replace them.
REPLACED = {"Attendance rules", "Exam and grading rules", "Internal assessment schedule", "Academic calendar",
            "Mini project and major project", "Department of Information Science", "College bus"}


# --- Events -----------------------------------------------------------------------------

# (days from today, time, title, venue, description)
EVENTS = [
    (3, "10:00", "Mid-semester examination 2 begins", "Respective classrooms", "The second mid-semester (CIE) examinations for all semesters run for one week. Carry your ID card and a calculator where allowed."),
    (5, "14:00", "Guest lecture: Careers in Machine Learning", "Seminar Hall, Academic Block", "An alumnus working at a product company talks about learning paths, projects and interviews for ML roles."),
    (8, "09:30", "Placement drive: Infosys", "Placement Cell, Admin Block", "Open to final year students with 60 percent and no backlogs. Carry two copies of your resume and your ID card."),
    (12, "09:00", "Hackathon: Code for Campus", "Computer Science Labs", "A 24 hour hackathon in teams of up to four. Build something that makes campus life easier. Prizes for the top three teams."),
    (15, "11:00", "Workshop: Web development with FastAPI", "IS Department Lab 2", "A hands-on workshop on building and deploying a web API. Bring your laptop. Seats are limited to 60."),
    (19, "16:00", "Cultural evening: Rhythm 2026", "Open Air Auditorium", "Music, dance and drama performances by students. Entry is free for NMAMIT students with ID cards."),
    (24, "10:00", "Annual Sports Day", "College Ground", "Track and field events, relay races and team games. Register with your class representative by the previous Friday."),
    (30, "09:30", "Alumni meet", "Main Auditorium", "Alumni from the last ten batches return to meet students, share advice and visit their old classrooms."),
    (36, "10:00", "Technical fest: Nitte Tech Expo", "Entire Campus", "Project exhibition, robotics contest, coding rounds and a quiz. Open to students from other colleges too."),
    (45, "09:00", "Semester end exams begin", "Examination Hall", "The semester end exam timetable is on the notice board. Hall tickets can be collected from the department a week before."),
    (-4, "15:00", "Orientation for new club members", "Seminar Hall, Academic Block", "Introduction to all technical and cultural clubs. This event has already happened."),
]


# --- Putting it together ----------------------------------------------------------------

def seed_students() -> int:
    created = 0
    for n in range(FIRST_ROLL, LAST_ROLL + 1):
        email = f"nnm23is{n:03d}@{config.ALLOWED_DOMAIN}"
        # The name is just the USN until the student signs in with Google and their real name replaces it.
        created += academics.ensure_student(email, email.split("@")[0].upper(), academics.SEEDED_BY)
    return created


def seed_events() -> None:
    for days, start, title, venue, description in EVENTS:
        when = (date.today() + timedelta(days=days)).isoformat()
        event_id = db.add_event(title, when, start, venue, description, None, None, USER)
        text = f"Event: {title}. Date: {library.pretty_date(when, start)}. Venue: {venue}. Details: {description}"
        module = db.create_module(f"Event: {title}", text, "event", USER)
        db.set_module("events", event_id, module["id"])


def _drop_old_samples() -> list[int]:
    """Remove what older versions made up: sample notes and subjects, timetables, rules and marks with fake codes.

    Only rows the sample data wrote are touched; anything a person added or edited stays. Returns removed module ids.
    """
    removed = []
    with db.connect() as conn:
        rows = conn.execute("SELECT id, module_id FROM notes WHERE uploaded_by = ?", (USER,)).fetchall()
        conn.execute("DELETE FROM notes WHERE uploaded_by = ?", (USER,))
        removed += [r["module_id"] for r in rows if r["module_id"]]
        old = conn.execute(
            f"SELECT id FROM modules WHERE updated_by = ? AND (title LIKE 'Timetable: %' OR source = 'syllabus' "
            f"OR title IN ({','.join('?' * len(REPLACED))}))", (USER, *REPLACED)).fetchall()
        removed += [r["id"] for r in old]
        new_codes = {code for code, _, _ in syllabus.note_subjects()}
        for s in conn.execute("SELECT code FROM subjects").fetchall():
            if s["code"] not in new_codes and not conn.execute("SELECT 1 FROM notes WHERE code = ?", (s["code"],)).fetchone():
                conn.execute("DELETE FROM subjects WHERE code = ?", (s["code"],))
        # Sample marks and attendance with the old made-up subject codes get the real subjects.
        codes = academics.sample_codes()
        stale = conn.execute("SELECT DISTINCT email FROM marks WHERE updated_by IN (?, ?) UNION "
                             "SELECT DISTINCT email FROM attendance WHERE updated_by IN (?, ?)",
                             (academics.SEEDED_BY, USER, academics.SEEDED_BY, USER)).fetchall()
        for table in ("marks", "attendance"):
            for row in conn.execute(f"SELECT id, code FROM {table} WHERE updated_by IN (?, ?)",
                                    (academics.SEEDED_BY, USER)).fetchall():
                if row["code"] not in codes:
                    conn.execute(f"DELETE FROM {table} WHERE id = ?", (row["id"],))
        if removed:
            conn.execute(f"DELETE FROM modules WHERE id IN ({','.join('?' * len(removed))})", removed)
    for r in stale:
        marks, attendance = academics.sample_records(r["email"])
        db.save_student({"email": r["email"], "name": None, "branch": "", "semester": academics.CURRENT_SEMESTER},
                        marks, attendance, academics.SEEDED_BY)   # profile exists already, so only the records are added
    return removed


def seed_syllabus() -> None:
    """Notes for every course (its full syllabus), the regulations, and the other courses, for the assistant."""
    library.seed_subjects()
    have = {m["title"] for m in db.list_modules()}
    for title, content in INFO + timetable_entries():
        if title not in have:
            db.create_module(title, content, "manual", USER)
    for sem, c in syllabus.listed():
        text = syllabus.course_text({**c, "kind": "Core course" if c["kind"] == "Core" else c["kind"]}, sem)
        _add_note(sem, c, "Syllabus (2023-04 regulations)", "Syllabus", text)
    for section in syllabus.regulations():
        db.create_module(f"Regulations: {section['title']}", f"B.Tech. regulations 2023, {section['title']}.\n{section['text']}",
                         "syllabus", USER)
    for c in syllabus.other_courses():
        db.create_module(f"Syllabus: {c['title']} ({c['code']})", syllabus.course_text(c), "syllabus", USER)


def _add_note(sem: int, c: dict, title: str, label: str, body: str) -> None:
    note_id = db.add_note(c["code"], title, "text", body, None, None, USER)
    module = db.create_module(f"Notes: Semester {sem}, {c['title']}, {label}", body, "note", USER)
    db.set_module("notes", note_id, module["id"])


def seed_study_notes() -> None:
    """A unit-wise study note for every subject that doesn't have one, made from its syllabus (shown above it)."""
    with db.connect() as conn:
        done = {r["code"] for r in conn.execute("SELECT code FROM notes WHERE title = 'Unit-wise study notes'")}
    for sem, c in syllabus.listed():
        body = syllabus.study_notes(c["code"], sem)
        if body and c["code"] not in done:
            _add_note(sem, c, "Unit-wise study notes", "Study notes", body)


def _index(removed: list[int], after: int) -> None:
    """Take removed entries out of the search index and add the new ones (ids above `after`)."""
    try:
        for module_id in removed:
            rag.remove_module(module_id)
        for module in db.list_modules():   # add, never wipe: existing entries stay searchable meanwhile
            if module["id"] > after:
                rag.index_module(module)
        log.info("Default data is searchable by the assistant.")
    except Exception:
        log.exception("Default data was saved, but it could not be added to the search index. "
                      "Use the Rebuild search index button in the admin panel.")


def run() -> None:
    """Fill the empty database with the default data, once; bring older sample data up to the syllabus, once."""
    if not config.SEED_DEMO_DATA:
        return
    db.unname_seeded_profiles()   # older versions gave made-up names; show the USN until the real name is known
    newest = max((m["id"] for m in db.list_modules()), default=0)
    changed, removed = False, []
    if not db.get_meta(MARKER):
        log.info("First start: filling in the default data (students, timetables, events)...")
        db.init()
        seed_students()
        seed_events()
        db.set_meta(MARKER, db.now())
        newest, changed = 0, True       # a new database: index everything
    if not db.get_meta(SYLLABUS_MARKER):
        log.info("Adding the official IS syllabus to the notes and the assistant...")
        removed = _drop_old_samples()   # this also removes earlier study notes, so they are made again below
        seed_syllabus()
        db.set_meta(SYLLABUS_MARKER, db.now())
        with db.connect() as conn:
            conn.execute("DELETE FROM meta WHERE k = ?", (STUDY_MARKER,))
        changed = True
    if not db.get_meta(STUDY_MARKER):
        seed_study_notes()
        db.set_meta(STUDY_MARKER, db.now())
        changed = True
    if changed:
        # Indexing takes a few minutes on a slow computer, so it runs in the background: the pages have their
        # data straight away and the assistant can answer from it once this finishes.
        threading.Thread(target=_index, args=(removed, newest), name="seed-index", daemon=True).start()
        log.info("Default data is ready.")
