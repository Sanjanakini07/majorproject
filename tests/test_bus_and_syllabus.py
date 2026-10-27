"""Bus timings and the official syllabus: the data, the pages, and the exact facts the assistant gets."""
from datetime import time

from app import bus, personal, syllabus

from .conftest import login


def test_bus_page_and_api_need_sign_in(client):
    assert client.get("/api/bus").status_code == 401
    login(client, "nnm23is186@nmamit.in")
    data = client.get("/api/bus").json()
    assert [len(r["buses"]) for r in data["routes"]] == [88, 90, 18]
    assert client.get("/bus").status_code == 200


def test_times_in_bus_questions():
    assert bus.asked_time("next bus to karkala after 4:30") == (time(16, 30), "after")
    assert bus.asked_time("bus to udupi at 9 am") == (time(9, 0), "after")
    assert bus.asked_time("any bus before 7pm") == (time(19, 0), "before")
    assert bus.asked_time("buses to mangalore in the evening") == (time(16, 0), "after")
    assert bus.asked_time("bus to karkala")[0] is None
    assert bus.asked_time("is there a bus on 30/10")[0] is None          # a date is not a time


def test_bus_facts_pick_the_route_and_the_next_buses():
    text = bus.facts("when is the next bus to karkala", time(16, 0))
    assert "From Nitte to Karkala" in text and "Belman" not in text
    assert "Next buses at or after 4:00 PM" in text
    udupi = bus.facts("last bus to udupi", None)
    assert "going to Udupi" in udupi and "Last:" in udupi and "Karkala:" not in udupi
    morning = bus.facts("bus from karkala bypass to college at 8", None)
    assert "Karkala Bypass to Nitte" in morning and "reaches Nitte at" in morning


def test_bus_questions_reach_the_assistant(client):
    facts = personal.build("nnm23is186@nmamit.in", "", "next bus to mangalore after 5 pm")
    assert "going to Mangalore" in facts.text and "Next buses at or after 5:00 PM" in facts.text
    assert "Events today" not in facts.text            # a bus question is not an events question


def test_courses_are_found_by_short_names():
    find = lambda q: [c["code"] for _, c in syllabus.find_courses(q)]  # noqa: E731
    assert find("where can i find os notes") == ["IS3101-1"]
    assert find("dbms syllabus") == ["CS2102-1"]
    assert find("what is in unit 2 of machine learning") == ["IS2002-1"]
    assert find("syllabus for compiler design") == ["IS3102-1"]
    assert find("when is the library open") == []


def test_syllabus_outline_and_named_course_facts(client):
    assert "Unit I" in syllabus.outline("IS3102-1") and "Turing Machines" in syllabus.outline("IS3102-1")
    facts = personal.build("nnm23is186@nmamit.in", "", "what is in the operating systems syllabus?")
    assert facts.courses == ("IS3101-1",)
    assert "semester 5 core course" in facts.text and "Notes page under Semester 5" in facts.text
    whole = personal.build("nnm23is186@nmamit.in", "", "what subjects do i have this sem")
    assert whole.note_semesters == (6,) and "Automata Theory and Compiler Design" in whole.text


def test_regulation_numbers_used_by_the_app():
    assert syllabus.REQUIRED_ATTENDANCE == 85 and syllabus.CONDONABLE_TO == 75
    assert [g for _, g, _ in syllabus.GRADES] == ["O", "A+", "A", "B+", "B", "C", "P"]
    assert any("Attendance" in r["title"] for r in syllabus.regulations())
