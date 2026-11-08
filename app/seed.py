"""Default data, so no page opens empty.

On the first start this fills in: students NNM23IS000 to NNM23IS300 (named by USN until they sign in, with
sample marks and attendance), timetables, college information for the assistant and upcoming events.
The Notes library and the assistant's knowledge of every course and of the regulations come from the
official IS syllabus (app/syllabus.py), so they are real, not made up.
Each step runs once (a marker is saved in the database), so anything an admin later edits or deletes stays
that way. Turn it off with SEED_DEMO_DATA=0 in .env.
"""
import json
import logging
import threading

from . import academics, config, db, library, rag, sheets, syllabus

log = logging.getLogger(__name__)

MARKER = "demo_data_v1"
SYLLABUS_MARKER = "syllabus_2023_04_v1"
STUDY_MARKER = "study_notes_v1"
SHEETS_MARKER = "sheets_v1"   # teacher list and placement drives (app/data)
ACCURACY_MARKER = "accuracy_v1"   # made-up content removed, real SEE timetable, semester 7
USER = "sample data"
FIRST_ROLL, LAST_ROLL = 0, 300


# --- College information ------------------------------------------------------------------

INFO = [
    # These three follow the 2023-04 regulations (sections 9 and 11); the full sections are in the knowledge base too.
    ("Attendance rules (2023 regulations)", "Every course needs at least 85 percent attendance. The principal can condone up to 10 percent for reasons such as medical grounds or taking part in university sports, cultural activities, seminars, workshops and paper presentations. A student with less than 75 percent in a course can't write that course's semester end exam (SEE) and gets an N grade, and has to repeat the course when it is offered next. Attendance is told to students in the first week of every month."),
    ("Evaluation and grading rules (2023 regulations)", "Each course has 50 marks of continuous internal evaluation (CIE) and 50 marks of semester end examination (SEE). CIE has two mid-semester examinations (40 marks) and quizzes, tutorials and assignments (10 marks); for project based and integrated lab courses the PBL or lab work counts too. To pass, a student needs 40 percent of the course total (CIE plus SEE). Grades are absolute: O for 90 percent and above (10 points), A+ for 80 to 89 (9), A for 70 to 79 (8), B+ for 60 to 69 (7), B for 55 to 59 (6), C for 50 to 54 (5), P for 40 to 49 (4) and F below 40 (0). A CGPA of 7 or more is first class with distinction, 6 to 6.99 first class and 5 to 5.99 second class. Below a CGPA of 5 a student is on academic probation."),
    ("Academic calendar (2023 regulations)", "There are two main semesters a year: the odd semester from August to December and the even semester from January to May, each of about 20 weeks. An optional summer semester runs in the vacation after the even semester, mainly to help students clear courses they failed."),
]
# Real: the 7th semester B.Tech SEE theory timetable, December 2026 (Controller of Examinations, NDU Off-campus
# Centre, Nitte; marked TENTATIVE). Only the ISE papers and the open electives are listed.
SEE_TITLE = "Exam: SEE timetable, 7th semester ISE, December 2026 (tentative)"
SEE_TEXT = """Semester end examination (SEE) theory timetable for 7th semester B.Tech Information Science and Engineering (ISE), December 2026. It is marked TENTATIVE by the Controller of Examinations, NDU Off-campus Centre, Nitte. Every paper is from 1:00 PM to 4:00 PM.
Thursday 10 December 2026: MG1002-1 Financial Management (FM).
Saturday 12 December 2026: professional electives IS1201-1 Total Quality Management for Sustainable Growth (TQM), IS2213-1 Object Oriented Modeling and Design (OOMD) and IS4224-1 Software Defined Networks (SDN).
Tuesday 15 December 2026: open electives, including IS2503-1 Software Engineering Practices, IS2504-1 Web Technologies, AM1501-1 Intel Driven Empowering with AIML, BT1501-1 Biofuel Engineering, CS2502-1 Introduction to Data Structures, CV2501-1 Disaster Management, CV2503-1 Environmental Impact Assessment, CV2504-1 Introduction to Geoinformatics, CV2505-1 Sustainability Engineering, CV2506-1 Traditional Vastu Shastra and Modern Building Design, EC2501-1 Consumer Electronics, EC2503-1 Space Technology and Applications, EE2503-1 Electric Vehicle Technology, EE2506-1 Non-Conventional Energy Sources, HU1501-1 Elements of Yoga, HU1503-1 Introduction to German Language, HU1504-1 Introduction to Japanese Language, HU1506-1 Overview of Indian Culture, HU1508-1 Principles of Physical Education, HU2502-1 Linguistic and Language Technology, MA1502-1 Number Theory, ME1502-1 Industrial Pollution Control, ME1503-1 Sustainable Development Goals, ME1504-1 Technological Innovation, ME1506-1 Quantitative Techniques in Management, MG1501-1 Human Resource Management, PH2501-1 Nanotechnology and RI2504-1 Micro Aerial Vehicles.
Thursday 17 December 2026: professional electives IS2302-1 User Interface Design (UID), IS3343-1 Operations Research (OR), IS4321-1 Intrusion Detection System (IDS) and IS4323-1 Wireless Sensor Networks (WSN).
Friday 18 December 2026: no ISE paper.
Monday 21 December 2026: IS3002-1 Ethical Hacking and Network Defence (EH&ND).
Tuesday 22 December 2026: reserve day. If an exam is postponed for unforeseen reasons, it is held on this day.
Courses not listed here have no theory paper in this timetable. The mid-semester exam (MSE) dates are not part of it."""

# Made up by older versions and stated by the assistant as fact: campus details, class timetables and events.
INVENTED_TITLES = {"Library timings", "Lost ID card", "Fee payment", "Hostel", "Canteen", "Placement cell",
                   "Sports and clubs", "Wi-Fi and computer labs", "Scholarships", "Department of Information Science"}
# Older versions added these made-up rules; the syllabus versions above replace them.
REPLACED = {"Attendance rules", "Exam and grading rules", "Internal assessment schedule", "Academic calendar",
            "Mini project and major project", "Department of Information Science", "College bus"}


# --- Putting it together ----------------------------------------------------------------

def seed_students() -> int:
    created = 0
    for n in range(FIRST_ROLL, LAST_ROLL + 1):
        email = f"nnm23is{n:03d}@{config.ALLOWED_DOMAIN}"
        # The name is just the USN until the student signs in with Google and their real name replaces it.
        created += academics.ensure_student(email, email.split("@")[0].upper(), academics.SEEDED_BY)
    return created


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
    for title, content in INFO:
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


def drop_invented() -> list[int]:
    """Remove what older versions made up and the assistant stated as fact: sample events, class timetables and
    campus details. Only rows the sample data wrote are touched. Returns the removed knowledge entry ids."""
    with db.connect() as conn:
        events = conn.execute("SELECT id, module_id FROM events WHERE created_by = ?", (USER,)).fetchall()
        conn.execute("DELETE FROM events WHERE created_by = ?", (USER,))
        marks = ",".join("?" * len(INVENTED_TITLES))
        rows = conn.execute(f"SELECT id FROM modules WHERE updated_by = ? AND (title LIKE 'Timetable: %' "
                            f"OR source = 'event' OR title IN ({marks}))", (USER, *INVENTED_TITLES)).fetchall()
        removed = sorted({r["id"] for r in rows} | {e["module_id"] for e in events if e["module_id"]})
        if removed:
            conn.execute(f"DELETE FROM modules WHERE id IN ({','.join('?' * len(removed))})", removed)
    return removed


def move_to_semester(semester: int) -> None:
    """The batch moved up a semester: students still in the previous one move up, and sample records made for
    the old semester are made again (a teacher's or admin's own entries stay)."""
    with db.connect() as conn:
        emails = [r["email"] for r in conn.execute("SELECT email FROM profiles WHERE semester = ?", (semester - 1,))]
        conn.execute("UPDATE profiles SET semester = ? WHERE semester = ?", (semester, semester - 1))
        for email in emails:
            for table in ("marks", "attendance"):
                conn.execute(f"DELETE FROM {table} WHERE email = ? AND updated_by IN (?, ?)",
                             (email, academics.SEEDED_BY, USER))
    for email in emails:
        marks, attendance = academics.sample_records(email)
        db.save_student({"email": email, "name": None, "branch": "", "semester": semester},
                        marks, attendance, academics.SEEDED_BY)   # profile exists already: only the records are added


def seed_sheets() -> None:
    """The teacher list and the placement drives (app/data/*.json), into empty lists only. The uids are the same on
    every laptop, so an admin's edit to one of these rows syncs to the same row everywhere."""
    for name, sheet in sheets.SHEETS.items():
        if not sheet.get("seed") or db.sheet_rows(name):
            continue
        rows = json.loads((config.BASE_DIR / "app" / "data" / sheet["seed"]).read_text(encoding="utf-8"))
        # cleaned the way a save from the grid cleans them, so saving the grid unchanged changes nothing
        db.save_sheet(name, sheets.clean_rows(name, [{**r, "uid": f"seed-{name}-{i}"} for i, r in enumerate(rows)]), USER)


def run() -> threading.Thread | None:
    """Fill the empty database with the default data, once; bring older sample data up to the syllabus, once.

    Returns the background indexing thread (if one was started) so a one-off script can wait for it."""
    if not config.SEED_DEMO_DATA:
        return None
    db.unname_seeded_profiles()   # older versions gave made-up names; show the USN until the real name is known
    newest = max((m["id"] for m in db.list_modules()), default=0)
    changed, removed = False, []
    if not db.get_meta(MARKER):
        log.info("First start: filling in the default data (students, timetables, events)...")
        db.init()
        seed_students()
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
    if not db.get_meta(SHEETS_MARKER):
        seed_sheets()
        db.set_meta(SHEETS_MARKER, db.now())
    if not db.get_meta(ACCURACY_MARKER):
        log.info("Removing made-up sample content, adding the SEE timetable, moving to semester %s...",
                 academics.CURRENT_SEMESTER)
        removed = [*removed, *drop_invented()]
        if not db.get_module_by_title(SEE_TITLE):
            db.create_module(SEE_TITLE, SEE_TEXT, "manual", USER)
        move_to_semester(academics.CURRENT_SEMESTER)
        db.set_meta(ACCURACY_MARKER, db.now())
        changed = True
    if changed:
        # Indexing takes a few minutes on a slow computer, so it runs in the background: the pages have their
        # data straight away and the assistant can answer from it once this finishes.
        indexer = threading.Thread(target=_index, args=(removed, newest), name="seed-index", daemon=True)
        indexer.start()
        log.info("Default data is ready.")
        return indexer
    return None
