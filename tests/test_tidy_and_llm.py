"""Admin "Add information" (file reading, AI tidy-up) and who writes the answer (Groq, local model, facts)."""
from datetime import date, time

from app import personal, rag

from .conftest import login


def test_tidy_returns_title_and_clean_text(client, monkeypatch):
    seen = {}

    def fake(system, user, max_tokens=1024):
        seen.update(system=system, user=user)
        return "TITLE: Infosys campus drive\nThe Infosys campus drive is on Wednesday 18 November 2026 at 9 AM."

    monkeypatch.setattr(rag, "groq_complete", fake)
    login(client, "admin@nmamit.in")
    res = client.post("/api/admin/tidy", json={"text": "infosys drive 18 nov 9am", "category": "Placements"})
    assert res.status_code == 200
    assert res.json() == {"title": "Infosys campus drive",
                          "content": "The Infosys campus drive is on Wednesday 18 November 2026 at 9 AM."}
    assert "Placements" in seen["system"] and seen["user"] == "infosys drive 18 nov 9am"


def test_tidy_without_title_line_keeps_text_and_failure_is_explained(client, monkeypatch):
    login(client, "admin@nmamit.in")
    monkeypatch.setattr(rag, "groq_complete", lambda s, u, max_tokens=1024: "Library opens at 8:30 AM.")
    assert client.post("/api/admin/tidy", json={"text": "lib 8.30"}).json() == {"title": "", "content": "Library opens at 8:30 AM."}

    def down(*a, **k):
        raise rag.AnswerError("no model")

    monkeypatch.setattr(rag, "groq_complete", down)
    res = client.post("/api/admin/tidy", json={"text": "lib 8.30"})
    assert res.status_code == 503 and "save it as it is" in res.json()["detail"]


def test_tidy_needs_content_permission(client):
    login(client, "student@nmamit.in")
    assert client.post("/api/admin/tidy", json={"text": "x"}).status_code == 403


def test_extract_text_reads_text_files_and_refuses_word(client):
    login(client, "admin@nmamit.in")
    res = client.post("/api/admin/extract-text", files={"file": ("bus.txt", "bus 4 udupi 4.40pm".encode(), "text/plain")})
    assert res.status_code == 200 and res.json()["text"] == "bus 4 udupi 4.40pm"
    csv = "﻿date,exam\n24/11,FM\n".encode()
    assert client.post("/api/admin/extract-text", files={"file": ("mse.csv", csv, "text/csv")}).json()["text"] == "date,exam\n24/11,FM"
    res = client.post("/api/admin/extract-text", files={"file": ("x.docx", b"PK..", "application/octet-stream")})
    assert res.status_code == 400 and "PDF or CSV" in res.json()["detail"]


def test_groq_failure_switches_to_local_model_and_skips_groq_for_a_while(monkeypatch):
    from offline_app import llm

    calls = []

    def groq(system, user, max_tokens=1024):
        calls.append("groq")
        raise ConnectionError("no internet")

    def local(system, user, max_tokens):
        calls.append("local")
        return "local answer"

    monkeypatch.setattr(llm.app_config, "GROQ_API_KEY", "key")
    monkeypatch.setattr(llm.rag, "groq_complete", groq)
    monkeypatch.setattr(llm, "_local", local)
    monkeypatch.setattr(llm, "_skip_groq_until", 0.0)
    assert llm.answer("q", [{"text": "t", "title": "t"}]) == "local answer"
    assert llm.answer("q", [{"text": "t", "title": "t"}]) == "local answer"
    assert calls == ["groq", "local", "local"]  # the second question didn't wait for Groq again
    assert llm.last_engine == "local"


def test_groq_is_used_first_when_online(monkeypatch):
    from offline_app import llm

    monkeypatch.setattr(llm.app_config, "GROQ_API_KEY", "key")
    monkeypatch.setattr(llm.rag, "groq_complete", lambda s, u, max_tokens=1024: "groq answer")
    monkeypatch.setattr(llm, "_local", lambda *a: (_ for _ in ()).throw(AssertionError("local model called")))
    monkeypatch.setattr(llm, "_skip_groq_until", 0.0)
    assert llm.answer("q", [{"text": "t", "title": "t"}]) == "groq answer" and llm.last_engine == "groq"


def test_grade_for_a_score_is_exact_and_leaves_out_my_marks():
    facts = personal.build("nobody@nmamit.in", "", "What grade do I get for 85 percent?", date(2026, 11, 8), time(10))
    assert "score of 85 percent in a course: that is grade A+ (9 grade points)" in facts.text
    assert "score of 38 percent" in personal.build("x@nmamit.in", "", "I got 38 marks, did I pass?").text
    assert "grade F" in personal.build("x@nmamit.in", "", "I got 38 marks, did I pass?").text
    assert "grade O" in personal.build("x@nmamit.in", "", "what grade is 95%").text


def test_misspelt_keywords_are_corrected_but_names_and_codes_are_not():
    assert personal.fix_spelling("wat r the electiv subjcts in 6th sem") == "wat r the elective subjects in 6th sem"
    assert personal.fix_spelling("my attendence this semister") == "my attendance this semester"
    assert personal.fix_spelling("is jason sir in cabin is3101 notes") == "is jason sir in cabin is3101 notes"
    facts = personal.build("x@nmamit.in", "", "wat r the electiv subjcts in 6th sem")
    assert "lective" in facts.text


def test_rule_questions_get_one_exact_line_and_drop_regulation_search_hits():
    facts = personal.build("x@nmamit.in", "", "How are CIE marks split?")
    assert "Asked about how CIE (internal) marks are split" in facts.text and "Regulations: " in facts.covered
    hits = [{"title": "Regulations: 22. Appendix-B", "text": "diary 50:25:25"}, {"title": "Library", "text": "8:30"}]
    assert [h["title"] for h in personal.adjust_hits(hits, facts)] == ["Library"]
    see = personal.build("x@nmamit.in", "", "What is the minimum attendance needed to write the SEE?").text
    assert "the minimum to write a course's SEE is 75 percent" in see
    assert "Attendance needed: 85 percent" not in see  # the full rules list is left out


def test_group_entries_reach_the_model_even_when_search_misses_them(client):
    from app import db

    exam = db.create_module("Exam: MSE 2 timetable", "27/11 fri EH&ND 10am", "manual", "admin@nmamit.in")
    db.create_module("Placement: Wipfli", "drive 12 nov", "manual", "admin@nmamit.in")
    facts = personal.build("x@nmamit.in", "", "what time is the mse for ethical hacking")
    assert facts.groups == ("Exam: ",)
    hits = personal.adjust_hits([], facts)
    assert hits[0]["module_id"] == exam["id"] and "EH&ND" in hits[0]["text"]
    assert personal.build("x@nmamit.in", "", "where is ravi sir cabin").groups == ("Teacher: ",)
    assert "Placement: " in personal.build("x@nmamit.in", "", "whats the ctc for wipfli drive").groups


def test_a_group_entry_goes_in_whole_not_as_the_pieces_search_found(client):
    from app import db

    lines = [f"The exam for course {n} is on {n} December 2026." for n in range(1, 40)]
    exam = db.create_module("Exam: SEE timetable", "\n".join(lines), "manual", "admin@nmamit.in")
    late_piece = {"title": exam["title"], "text": "piece with only the last lines", "distance": 0.6, "module_id": exam["id"]}
    facts = personal.build("x@nmamit.in", "", "when is the FM SEE?")
    hits = personal.adjust_hits([late_piece, dict(late_piece)], facts)
    assert [h["module_id"] for h in hits].count(exam["id"]) == 1  # the pieces are replaced, not kept as well
    assert "course 1 is on 1 December" in hits[0]["text"]          # the whole entry, first
