"""Admin spreadsheet lists (app/sheets.py): teachers and cabins, placements, college buses."""
from datetime import date

from app import db, personal, seed, sheets

from .conftest import login

TEACHERS = [
    {"name": "Dr. Jason Elroy Martis", "designation": "Associate Professor", "department": "Information Science & Engineering",
     "cabin": "APJ 5th Floor", "directions": "Slight left from the lift", "subjects": "Database Management Systems; IoT",
     "email": "jason@example.edu"},
    {"name": "Dr. Deepa", "department": "Information Science & Engineering", "cabin": "", "subjects": "Data Structures"},
]


def put(client, name, rows):
    return client.put(f"/api/sheets/{name}", json={"rows": rows})


def test_reading_needs_sign_in_and_editing_needs_content_permission(client):
    assert client.get("/api/sheets/teachers").status_code == 401
    login(client, "nnm23is042@nmamit.in")
    got = client.get("/api/sheets/teachers").json()
    assert got["rows"] == [] and [c["key"] for c in got["columns"]][:3] == ["name", "designation", "department"]
    assert put(client, "teachers", TEACHERS).status_code == 403
    assert client.get("/api/sheets/nope").status_code == 404


def test_save_adds_changes_and_removes_only_what_changed(client):
    login(client, "admin@nmamit.in")
    assert put(client, "teachers", TEACHERS + [{"name": "  ", "cabin": ""}]).json() == {"added": 2, "changed": 0, "removed": 0}
    rows = client.get("/api/sheets/teachers").json()["rows"]
    assert [r["name"] for r in rows] == ["Dr. Jason Elroy Martis", "Dr. Deepa"]  # the blank row was dropped
    jason, deepa = rows
    deepa["cabin"] = "APJ 5th Floor"
    assert put(client, "teachers", [jason, deepa]).json() == {"added": 0, "changed": 1, "removed": 0}
    assert put(client, "teachers", [deepa]).json() == {"added": 0, "changed": 0, "removed": 1}
    assert [r["uid"] for r in client.get("/api/sheets/teachers").json()["rows"]] == [deepa["uid"]]


def test_bad_dates_times_and_sizes_are_refused(client):
    login(client, "admin@nmamit.in")
    assert "pick a date" in put(client, "placements", [{"company": "X", "date": "18 Nov"}]).json()["detail"]
    assert "14:30" in put(client, "placements", [{"company": "X", "date": "2026-11-18", "time": "9am"}]).json()["detail"]
    assert put(client, "placements", [{"company": "X" * 301}]).status_code == 422
    assert put(client, "placements", [{"company": "X", "uid": "a"}, {"company": "Y", "uid": "a"}]).status_code == 422


def test_placements_show_on_the_events_page_and_in_the_calendar_facts(client):
    login(client, "admin@nmamit.in")
    put(client, "placements", [{"company": "Wipfli", "date": "2026-11-12", "time": "09:30", "venue": "Sambhram",
                                "eligibility": "ISE, CSE; 65%", "package": "6.5 LPA"}])
    (ev,) = [e for e in client.get("/api/events").json() if e["kind"] == "placement"]
    assert ev["title"] == "Wipfli campus drive" and ev["event_date"] == "2026-11-12" and "6.5 LPA" in ev["description"]
    text = personal.build("x@nmamit.in", "", "any placement drives this week?", date(2026, 11, 10)).text
    assert "Thursday 12 November 2026 at 9:30 AM: Wipfli campus drive, venue Sambhram" in text
    assert "Eligibility: ISE, CSE; 65%" in text


def test_teachers_are_found_by_name_even_misheard_and_by_subject(client):
    login(client, "admin@nmamit.in")
    put(client, "teachers", TEACHERS)
    jason = personal.build("x@nmamit.in", "", "where is jayson sir's cabin").text
    assert "Dr. Jason Elroy Martis (Associate Professor)" in jason and "Cabin: APJ 5th Floor" in jason
    assert "Dr. Deepa" not in jason
    assert "Cabin: not entered in the app yet" in personal.build("x@nmamit.in", "", "where does deepa madam sit").text
    assert "Dr. Jason Elroy Martis" in personal.build("x@nmamit.in", "", "who teaches dbms").text
    assert "Dr. Deepa" not in personal.build("x@nmamit.in", "", "deep learning syllabus").text


def test_college_buses_are_empty_until_added(client):
    login(client, "admin@nmamit.in")
    assert "have not been entered" in personal.build("x@nmamit.in", "", "college bus to udupi").text
    put(client, "college_buses", [{"bus_no": "4", "route": "Udupi", "stops": "Udupi 7:10, Katapadi 7:30",
                                   "morning": "08:40"}])
    text = personal.build("x@nmamit.in", "", "college bus to udupi").text
    assert "Bus 4: route Udupi; stops Udupi 7:10, Katapadi 7:30; reaches college at 8:40 AM" in text


def test_default_lists_are_seeded_once_with_the_same_ids_everywhere(client):
    seed.seed_sheets()
    teachers = db.sheet_rows("teachers")
    assert len(teachers) > 100 and teachers[0]["uid"] == "seed-teachers-0" and teachers[0]["_by"] == "sample data"
    assert any(r["company"] == "Wipfli" for r in db.sheet_rows("placements"))
    assert db.sheet_rows("college_buses") == []
    seed.seed_sheets()  # a list that already has rows is left alone
    assert len(db.sheet_rows("teachers")) == len(teachers)


def test_saving_the_default_list_unchanged_changes_nothing(client):
    seed.seed_sheets()
    login(client, "admin@nmamit.in")
    rows = client.get("/api/sheets/teachers").json()["rows"]
    assert put(client, "teachers", rows).json() == {"added": 0, "changed": 0, "removed": 0}
    assert {r["_by"] for r in db.sheet_rows("teachers")} == {"sample data"}  # still default data: not synced
