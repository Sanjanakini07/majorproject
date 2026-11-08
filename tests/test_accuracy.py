"""Nothing made up reaches students: invented sample content is removed, numbers are checked against the context."""
from app import academics, db, personal, rag, seed, syllabus

from .conftest import login


def test_upgrade_removes_made_up_content_but_keeps_what_people_wrote(client):
    db.add_event("Annual Sports Day", "2026-12-02", "10:00", "Ground", "made up", None, None, seed.USER)
    real_event = db.add_event("ISE farewell", "2026-11-28", "09:00", "Sambhram", "real", None, None, "admin@nmamit.in")
    made_up = [db.create_module(t, "x", "manual", seed.USER)["id"] for t in ("Library timings", "Timetable: Semester 7, Monday")]
    edited = db.create_module("Hostel", "The real hostel rules", "manual", "admin@nmamit.in")
    regulation = db.create_module("Attendance rules (2023 regulations)", "real", "manual", seed.USER)
    removed = seed.drop_invented()
    assert set(made_up) <= set(removed)
    assert [e["id"] for e in db.list_events()] == [real_event]
    assert db.get_module(edited["id"]) and db.get_module(regulation["id"])


def test_moving_up_a_semester_remakes_only_sample_records(client):
    email = "nnm23is042@nmamit.in"
    academics.ensure_student(email, "NNM23IS042", academics.SEEDED_BY)
    with db.connect() as conn:  # as an older version left it: semester 6, with a mark a teacher corrected
        conn.execute("UPDATE profiles SET semester = 6 WHERE email = ?", (email,))
        conn.execute("UPDATE marks SET internal = 49, updated_by = 'teacher@nmamit.in' WHERE email = ? AND semester = 1 "
                     "AND code = 'MA1002-1'", (email,))
    seed.move_to_semester(7)
    assert db.get_profile(email)["semester"] == 7
    marks = {(m["semester"], m["code"]): m for m in db.list_marks(email)}
    assert marks[(1, "MA1002-1")]["internal"] == 49 and marks[(1, "MA1002-1")]["updated_by"] == "teacher@nmamit.in"
    assert {m["semester"] for m in marks.values()} == set(range(1, 7))
    assert {a["semester"] for a in db.list_attendance(email)} == {7}


def test_short_course_names_are_understood():
    codes = lambda q: [c["code"] for _, c in syllabus.find_courses(q)]  # noqa: E731
    assert codes("when is the fm see") == ["MG1002-1"]
    assert codes("oomd exam") == ["IS2213-1"] and codes("eh&nd mse") == ["IS3002-1"] and codes("tqm") == ["IS1201-1"]
    assert codes("is it on monday") == [] and codes("or exam") == []   # ordinary words are not courses


def test_numbers_not_in_the_context_get_a_retry_then_the_context_itself():
    context = "Thursday 10 December 2026: MG1002-1 Financial Management. Every paper is from 1:00 PM to 4:00 PM."
    answers = iter(["FM is on 15 December.", "It is on 10 December 2026, 1 to 4 PM."])
    assert rag.grounded_answer("when is the FM SEE", context, lambda s, u: next(answers)).startswith("It is on 10 December")
    stubborn = rag.grounded_answer("when is the FM SEE", context, lambda s, u: "It is on 15 December.")
    assert "10 December 2026: MG1002-1 Financial Management" in stubborn and "15" not in stubborn
    assert rag.grounded_answer("hi", context, lambda s, u: "Thursday 10 December, 1 PM.") == "Thursday 10 December, 1 PM."
    assert rag.quote_context("who is the principal", context) == rag.NO_INFO


def test_the_real_see_timetable_answers_fm_and_says_nothing_about_mse(client):
    seed.seed_syllabus()
    db.create_module(seed.SEE_TITLE, seed.SEE_TEXT, "manual", seed.USER)
    facts = personal.build("nnm23is042@nmamit.in", "", "when is the FM SEE?")
    assert "matching lines" in facts.text and "Thursday 10 December 2026: MG1002-1 Financial Management" in facts.text
    assert "Exam: " in facts.covered and "Exam: " not in facts.groups   # just the line, not the whole timetable
    assert "mid-semester exam (MSE) dates are not part of it" in seed.SEE_TEXT


def test_sample_records_are_labelled_as_sample(client):
    academics.ensure_student("nnm23is042@nmamit.in", "NNM23IS042", academics.SEEDED_BY)
    login(client, "nnm23is042@nmamit.in")
    text = personal.build("nnm23is042@nmamit.in", "", "what is my attendance").text
    assert "sample data made by this app, not official college records" in text
