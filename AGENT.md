# AGENT.md: working notes for this project

Read this before changing anything. It records what the app does now, why it is built this way, and the traps
already hit. The README is for people running the app; this file is for whoever (human or agent) works on it next.

## What it is

NMAMIT Campus Voice Assistant (FastAPI + plain HTML/JS, no framework). Students sign in with their college Google
account, pass a face scan, then ask questions by voice. Pages: Assistant, Notes, Events, Bus, Admin (staff), and
Marks / Attendance behind the arrow (▾) at the end of the nav bar (the client said those two are not the focus now).
An offline version (`offline_app/`) runs on one laptop with local models and syncs with Turso.

Run: `start.bat` (online, port 8000, **no auto-reload**: restart it after code changes) or `start_offline.bat`.
Tests: `.venv\Scripts\python -m pytest -q` (85 pass, 1 skipped).

## How an answer is made (`/api/ask` in `app/main.py`, same in `offline_app/main.py`)

1. `personal.build(email, name, question)` works out **exact facts** for the question (see below) and returns
   `Facts(text, covered, note_semesters, timetable_semesters, courses)`.
2. `rag.search(question)` finds knowledge entries (ChromaDB, cosine, `MAX_DISTANCE` 0.7).
3. `personal.adjust_hits(hits, facts)` drops hits the facts replace (events, timetables), drops notes/timetables of
   the wrong semester, and puts the syllabus of a course the question names at the top.
4. `rag.answer(question, hits, facts.text)` (or `offline_app/llm.answer`) sends both to the model. The system prompt
   in `rag.py` says the "About the person asking" block is exact and wins over everything else.

**Rule that came out of user testing: never trust text search for dates, numbers, "my", or short course names.**
Every wrong answer the client reported (an event on "October 30th" missed, "first year subjects" returning
semester 8 notes, wrong name, "what's my next class" at night) was fixed by computing the answer in
`app/personal.py` and handing it to the model as a fact. Add new question types the same way.

`personal.py` handles: name / USN / branch / semester; dates ("october 30th", "30/10", "tomorrow", "next friday"),
week / weekend / month ranges; events on those days, next event, full calendar; today's / tomorrow's classes,
class now, next class (rolls to the next working day); marks per semester ("this sem", "last sem", "first year",
"3rd sem"), SGPA / CGPA (equal weight per subject), best / worst, backlogs; attendance with "can miss N" and
"attend next N" against 85% and 75%; regulation numbers; electives by group and stream; courses named by code,
title or short name (OS, DBMS, CN, ML, DAA...) with their units; buses (via `app/bus.py`).

Check real answers with the scratchpad-style harness: build facts, search, call Groq for ~30 questions, read every
answer. The key is in `.env` (`GROQ_API_KEY`, model `openai/gpt-oss-120b`). Point `DATA_DIR` at a copy of
`data/` when doing this so the real database is never touched.

## Data and where it comes from

| What | Source | Code |
|---|---|---|
| Subjects, notes, course syllabi, regulations | University PDF `14ENGR09D2_B.Tech._IS_2023-04_Regulations_Syllabus.pdf` (383 pages, not in the repo) → `app/data/syllabus_is_2023.json` via `scripts/import_syllabus.py <pdf>` | `app/syllabus.py` |
| Bus timings (196 entries, 3 routes) | Community Notion page "Bus Timings: Nitte" (bhvsh.notion.site), read through Notion's public `queryCollection` API (needs a browser User-Agent) → `app/data/bus_timings.json` | `app/bus.py` |
| Students NNM23IS000-300, sample marks / attendance, events, timetables, campus info | Made up on first start | `app/seed.py`, `app/academics.py` |

Client instructions to keep: **"strictly follow the PDF"** for syllabus and notes; seed students **named by their
USN** until they sign in, then use the real Google name; the Google name looks like `NNM23IS186 SRUJAN M PADMASHALI`
(the first word is the USN) and is shown as "Srujan M Padmashali" (`academics.clean_name`).

Syllabus facts used by the app (`syllabus.py`): attendance 85% per course, condonable to 75%, below 75% no SEE
(N grade); CIE 50 (two mid-sems 40 + quizzes 10) + SEE 50; pass 40% of total; grades O ≥90 (10), A+ 80 (9), A 70 (8),
B+ 60 (7), B 55 (6), C 50 (5), P 40 (4), F; CGPA ≥7 distinction, 6-6.99 first, 5-5.99 second, <5 probation.
Notes page: each semester's scheme courses; Professional Electives Group 1 listed under sem 5, Group 2 under sem 6,
AEC under 5, VEC under 4 (where first offered). Marks/attendance/timetables use `syllabus.core_courses(sem)`.
Each subject has two notes: "Syllabus (2023-04 regulations)" (the PDF text) and "Unit-wise study notes"
(`syllabus.study_notes`, built only from that course's syllabus: unit topics, outcomes, textbooks, a study plan).

Bus data: the listing writes afternoon times **without PM** ("01:03" = 1:03 PM). The JSON is converted to 24-hour
(hours 1-6 → PM). Get this wrong and the bot says the last bus is at 12:52 PM.

## Seeding and upgrades (`app/seed.py`)

Runs at start-up in both apps (`SEED_DEMO_DATA=0` turns it off; tests set it off). Each step has a marker in the
`meta` table and runs once, so admin edits and deletions stick:

- `demo_data_v1`: students (USN names, `updated_by = 'demo seed'`), events.
- `syllabus_2023_04_v1`: `_drop_old_samples()` removes what older versions made up (sample notes, fake subjects,
  timetables, replaced rule entries, syllabus entries, sample marks with fake codes, regenerated with real codes),
  then `seed_syllabus()` adds subjects, syllabus notes, regulations, other departments' courses, campus info,
  timetables. It clears the study-notes marker so they are made again.
- `study_notes_v1`: adds "Unit-wise study notes" to every subject that lacks one.

Only new knowledge entries (ids above the newest before seeding) are indexed, in a background thread: about
36 s for the study notes, about 5 minutes for a full fresh database (≈1,600 chunks on this CPU). Pages work at once;
the assistant knows the new text when indexing finishes.

Names: `db.unname_seeded_profiles()` resets made-up names of unclaimed seeded profiles to the USN at every start;
`academics.adopt_name()` runs at Google sign-in and on every `/api/me`, replacing a `demo seed` / `sample data`
name with the person's own Google name. A name a teacher or admin typed is never overwritten.

## Access rules (`app/portal.py`, `app/auth.py`)

Students see only their own marks and attendance. Seeing another student's needs the `marks` / `attendance`
permission (admins have all). `/api/students` needs either. The pages only show the student picker to people with
the permission. Bus, notes, events: any verified (face-checked) user.

## Traps already hit

- **Shell heredocs eat `\b`.** Writing Python with regexes through `bash <<EOF` turned `\b` into a backspace
  character twice, silently breaking word matching. Write code with the editor/Write tool, or build backslashes with
  `chr(92)`. Check with `grep -c $'\x08' app/*.py`.
- **The running server keeps old code.** `start.bat` has no `--reload`; the client restarted it in the middle of my
  edits once and it upgraded the database with half-finished code. Migrations must therefore be steps with their own
  markers that can complete an earlier, partial upgrade.
- **Patching `threading.Thread` globally in a script breaks ChromaDB.** Patch `seed.threading` only.
- `.gitignore` used `data/`, which also ignored `app/data/`; it is `/data/` now.
- Windows console is cp1252: run scripts that print answers with `PYTHONIOENCODING=utf-8`.
- Notion pages are rendered by JavaScript; WebFetch returns nothing. Use the `api/v3` endpoints.
- Small offline model (Ollama `qwen2.5:1.5b`) has a short context: keep fact blocks compact (bus lists are cut to a
  window around the asked time; semester questions get unit outlines, not full syllabi).

## Open items

- Events are dated relative to the first start, so they go stale; old databases still have the earlier
  "Internal Assessment 2 begins" event (new ones say "Mid-semester examination 2").
- Open electives from other departments are in the assistant's knowledge but not on the Notes page.
- `scripts/record_demo.py` predates face enrolment and the new pages.
- Timetables, campus information (library, hostel, canteen...) and events are still invented sample data.
