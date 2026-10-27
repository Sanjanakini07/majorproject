"""The default sample data fills every page, once."""
from datetime import date

from app import config, db, seed

from .conftest import login


def test_seed_fills_every_page_once(client, index, monkeypatch):
    monkeypatch.setattr(config, "SEED_DEMO_DATA", True)
    with db.connect() as conn:
        conn.execute("DELETE FROM meta")
    monkeypatch.setattr(seed.threading, "Thread", lambda target, args=(), **kw: type("T", (), {"start": staticmethod(lambda: target(*args))})())
    seed.run()

    assert len(db.list_profiles(limit=1000)) == 301
    assert db.get_profile("nnm23is000@nmamit.in") and db.get_profile("nnm23is300@nmamit.in")
    from app import academics
    assert len(db.list_marks("nnm23is150@nmamit.in")) == sum(len(academics.SUBJECTS[s]) for s in range(1, 6))
    assert len(db.list_attendance("nnm23is150@nmamit.in")) == len(academics.SUBJECTS[6])
    assert all(s["notes"] == 2 for s in db.list_subjects())          # its official syllabus and study notes
    assert any(e["event_date"] >= date.today().isoformat() for e in db.list_events())
    titles = [m["title"] for m in db.list_modules()]
    assert "Timetable: Semester 6, Monday" in titles and "Library timings" in titles
    assert len(index.modules) == db.count_modules()          # everything is searchable

    # a student sees their own sample records through the normal pages
    login(client, "nnm23is150@nmamit.in")
    assert len(client.get("/api/marks").json()["semesters"]) == 5

    # second start adds nothing, even after an admin deleted something
    db.delete_event(db.list_events()[0]["id"])
    before = (db.count_modules(), len(db.list_events()))
    seed.run()
    assert (db.count_modules(), len(db.list_events())) == before


def test_assistant_gets_the_askers_own_records(client, index, monkeypatch):
    from datetime import date

    from app import personal
    monkeypatch.setattr(config, "SEED_DEMO_DATA", True)
    with db.connect() as conn:
        conn.execute("DELETE FROM meta")
    monkeypatch.setattr(seed.threading, "Thread", lambda target, args=(), **kw: type("T", (), {"start": staticmethod(lambda: target(*args))})())
    seed.run()
    me, other = "nnm23is150@nmamit.in", "nnm23is151@nmamit.in"
    monday = date(2026, 10, 26)

    ctx = personal.context_for(me, "Google Name", "what is my name", monday)
    assert db.get_profile(me)["name"] in ctx and "NNM23IS150" in ctx and "Monday 26 October 2026" in ctx
    assert "Marks" not in ctx                                    # only when asked

    marks = personal.context_for(me, "", "what are my marks last sem and first sem", monday)
    assert "Semester 5:" in marks and "Semester 1:" in marks and "Semester 6 is going on" in marks
    assert db.get_profile(other)["name"] not in marks            # nobody else's data

    att = personal.context_for(me, "", "what is my attendance", monday)
    assert "Attendance this semester" in att and "Information & Network Security" in att and "85 percent" in att

    events = personal.context_for(me, "", "what events are there today", monday)
    assert "Events on Monday 26 October 2026 (today):" in events and "Full event calendar" in events
    assert "Classes today (Monday 26 October 2026): Semester 6 timetable for Monday" in personal.context_for(me, "", "what classes do i have today", monday)

    assert personal.context_for(me, "", "zzz") == ""             # unrelated questions get nothing extra


def test_event_questions_by_date_are_answered_exactly():
    from datetime import date

    from app import personal
    today = date(2026, 10, 27)
    for q in ("is there on october 30th?", "any event 30 oct", "what is on 30/10", "anything on friday"):
        assert personal.dates_in(q, today) == [date(2026, 10, 30)], q
    assert personal.dates_in("events tomorrow", today) == [date(2026, 10, 28)]
    assert personal.dates_in("what is the capital of france", today) == []


def test_years_and_semesters_pick_the_right_notes(client, index, monkeypatch):
    from app import personal
    monkeypatch.setattr(config, "SEED_DEMO_DATA", True)
    with db.connect() as conn:
        conn.execute("DELETE FROM meta")
    monkeypatch.setattr(seed.threading, "Thread", lambda target, args=(), **kw: type("T", (), {"start": staticmethod(lambda: target(*args))})())
    seed.run()

    assert [n for n, _ in personal.semesters_in("first year subjects", 6)] == [1, 2]
    assert [n for n, _ in personal.semesters_in("my last sem marks", 6)] == [5]
    assert [n for n, _ in personal.semesters_in("3rd sem notes", 6)] == [3]

    facts = personal.build("nnm23is186@nmamit.in", "", "is on first year subjects. can i revise?")
    assert facts.note_semesters == (1, 2)
    wrong = [{"title": "Notes: Semester 8, Major Project, Quick revision points", "text": "x", "distance": 0.3, "module_id": -1}]
    hits = personal.adjust_hits(wrong, facts)
    assert hits and all(h["title"].startswith(("Notes: Semester 1,", "Notes: Semester 2,")) for h in hits)


def test_placeholder_is_the_usn_until_google_gives_the_real_name(client):
    from app import academics
    academics.ensure_student("nnm23is186@nmamit.in", "NNM23IS186", academics.SEEDED_BY)
    assert db.get_profile("nnm23is186@nmamit.in")["name"] == "NNM23IS186"
    academics.adopt_name("nnm23is186@nmamit.in", "NNM23IS186 SRUJAN M PADMASHALI")   # what Google sign-in does
    assert db.get_profile("nnm23is186@nmamit.in")["name"] == "Srujan M Padmashali"
    assert academics.clean_name("Admin Person", "admin@nmamit.in") == "Admin Person"
