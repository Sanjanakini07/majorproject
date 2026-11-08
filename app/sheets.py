"""The admin's spreadsheet lists: teachers and cabins, placements, college buses.

Admins (and teachers with the "content" permission) edit them in a grid on the Admin page and save the whole list.
The assistant answers from them as exact facts (personal.build), placements also show on the Events page, and
college buses on the Bus page. Default rows come from app/data/teachers.json and placements.json (made from the
college website, CabinCompass and EMS; see scraped_data/README.md).
"""
import difflib
import re
import uuid
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import db, syllabus
from .auth import require, verified_user

router = APIRouter()

# type: text | long (wide cell) | date (YYYY-MM-DD) | time (HH:MM). need: highlighted while empty.
SHEETS = {
    "teachers": {
        "title": "Teachers & cabins",
        "hint": "Every teacher we know of. Fill the highlighted empty cells (mostly cabins) and correct anything.",
        "columns": [
            {"key": "name", "label": "Name", "type": "text", "need": True},
            {"key": "designation", "label": "Designation", "type": "text"},
            {"key": "department", "label": "Department", "type": "text", "need": True},
            {"key": "cabin", "label": "Cabin (block, floor, room)", "type": "text", "need": True},
            {"key": "directions", "label": "How to get there", "type": "long"},
            {"key": "subjects", "label": "Subjects taught", "type": "long"},
            {"key": "email", "label": "Email", "type": "text"},
        ],
        "seed": "teachers.json",
    },
    "placements": {
        "title": "Placements",
        "hint": "Campus drives and placement tests. Each row also shows on the Events page.",
        "columns": [
            {"key": "company", "label": "Company", "type": "text", "need": True},
            {"key": "date", "label": "Date", "type": "date", "need": True},
            {"key": "time", "label": "Time", "type": "time"},
            {"key": "venue", "label": "Venue", "type": "text"},
            {"key": "eligibility", "label": "Eligibility (branches, %, backlogs)", "type": "long", "need": True},
            {"key": "package", "label": "Package (CTC)", "type": "text"},
            {"key": "register_by", "label": "Register by", "type": "text"},
            {"key": "details", "label": "Other details", "type": "long"},
        ],
        "seed": "placements.json",
    },
    "college_buses": {
        "title": "College buses",
        "hint": "The college's own buses. Shown on the Bus page under College buses.",
        "columns": [
            {"key": "bus_no", "label": "Bus number", "type": "text", "need": True},
            {"key": "route", "label": "Route / starts from", "type": "text", "need": True},
            {"key": "stops", "label": "Stops in order, with times", "type": "long", "need": True},
            {"key": "morning", "label": "Reaches college at", "type": "time"},
            {"key": "evening", "label": "Leaves college at", "type": "time"},
            {"key": "contact", "label": "Driver / contact", "type": "text"},
            {"key": "notes", "label": "Notes", "type": "long"},
        ],
    },
}
MAX_ROWS = 3000
MAX_CELL = {"text": 300, "long": 3000, "date": 10, "time": 5}
UID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _sheet(name: str) -> dict:
    if name not in SHEETS:
        raise HTTPException(404, "There is no such list.")
    return SHEETS[name]


def rows(name: str) -> list[dict]:
    return db.sheet_rows(name)


@router.get("/api/sheets/{name}")
def get_sheet(name: str, user: dict = Depends(verified_user)):
    s = _sheet(name)
    return {"name": name, "title": s["title"], "hint": s["hint"], "columns": s["columns"],
            "rows": [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows(name)]}


class SheetIn(BaseModel):
    rows: list[dict[str, str | None]] = Field(max_length=MAX_ROWS)


def clean_rows(name: str, raw: list[dict]) -> list[tuple[str, dict]]:
    """Validate the grid: known columns only, sizes, dates and times; drop empty rows; give new rows a uid."""
    columns = _sheet(name)["columns"]
    out = []
    for n, row in enumerate(raw, start=1):
        data = {}
        for c in columns:
            value = " ".join((row.get(c["key"]) or "").split()) if c["type"] != "long" else (row.get(c["key"]) or "").strip()
            if len(value) > MAX_CELL[c["type"]]:
                raise HTTPException(422, f"Row {n}, {c['label']}: too long (at most {MAX_CELL[c['type']]} characters).")
            if value and c["type"] == "date":
                try:
                    date.fromisoformat(value)
                except ValueError:
                    raise HTTPException(422, f"Row {n}, {c['label']}: pick a date.")
            if value and c["type"] == "time" and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", value):
                raise HTTPException(422, f"Row {n}, {c['label']}: the time must look like 14:30.")
            data[c["key"]] = value
        if not any(data.values()):
            continue
        uid = row.get("uid") or ""
        out.append((uid if UID.match(uid) else uuid.uuid4().hex, data))
    if len({uid for uid, _ in out}) != len(out):
        raise HTTPException(422, "Two rows have the same id. Reload the page and try again.")
    return out


@router.put("/api/sheets/{name}")
def save_sheet(name: str, body: SheetIn, user: dict = Depends(require("content"))):
    return db.save_sheet(name, clean_rows(name, body.rows), user["email"])


# --- Placements on the Events page and in the assistant's calendar ------------------------

def placement_events() -> list[dict]:
    out = []
    for r in rows("placements"):
        if not r.get("date"):
            continue
        company = r.get("company") or "Placement"
        title = company if re.search(r"(?i)\b(drive|test|placement|interview|hiring)\b", company) else f"{company} campus drive"
        details = [f"Eligibility: {r['eligibility']}." if r.get("eligibility") else "",
                   f"Package: {r['package']}." if r.get("package") else "",
                   f"Register by {r['register_by']}." if r.get("register_by") else "", r.get("details") or ""]
        out.append({"id": f"placement-{r['uid']}", "kind": "placement", "title": title, "event_date": r["date"],
                    "start_time": r.get("time") or "", "venue": r.get("venue") or "",
                    "description": " ".join(d for d in details if d), "has_file": False})
    return out


def all_events() -> list[dict]:
    """Events and placement drives together, in date order."""
    events = [{**e, "kind": "event"} for e in db.list_events()] + placement_events()
    return sorted(events, key=lambda e: (e["event_date"], e["start_time"] or "", str(e["id"])))


# --- Facts for the assistant -----------------------------------------------------------

TITLES = {"dr", "mr", "ms", "mrs", "prof", "sir", "madam", "mam", "maam", "miss"}
# Words that are never a teacher's name, so "deep learning" or "where" don't pick a teacher.
NOT_NAMES = {
    "the", "and", "for", "what", "where", "when", "who", "which", "whom", "how", "his", "her", "him", "she", "cabin",
    "does", "teach", "teaches", "teaching", "teacher", "teachers", "subject", "subjects", "floor", "block", "room",
    "office", "find", "meet", "can", "get", "there", "about", "with", "from", "this", "that", "today", "class",
    "classes", "free", "available", "email", "mail", "contact", "number", "professor", "department", "dept", "head",
    "hod", "list", "all", "are", "sitting", "sits", "staff", "faculty", "lecturer", "deep", "learning", "data", "next",
    "bus", "exam", "exams", "placement", "drive", "company", "lab", "labs", "notes", "marks", "attendance", "mid",
    "sem", "semester", "event", "events", "time", "date", "day", "week", "month", "year", "you", "your", "our",
}
TEACHER_WORDS = re.compile(r"\b(sir|madam|ma'?am|mam|miss|teachers?|professors?|prof|faculty|lecturers?|cabins?|"
                           r"staff ?rooms?|hod|staff|teaches|teaching|who teaches|taught)\b")
PLACEMENT_WORDS = re.compile(r"\b(placements?|placed|drives?|recruit\w*|compan(y|ies)|packages?|ctc|lpa|salary|"
                             r"offers?|interviews?|aptitude|t ?& ?p|tnp|hiring|jobs?)\b")
COLLEGE_BUS = re.compile(r"\b(college bus(es)?|bus (no|number)|bus route|college van|institute bus)\b")


def _tokens(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z]+", text.lower()) if len(w) >= 3]


def _teacher_line(t: dict) -> str:
    who = t.get("name") or "A teacher"
    if t.get("designation"):
        who += f" ({t['designation']})"
    line = who + (f", {t['department']}." if t.get("department") else ".")
    line += f" Cabin: {t['cabin']}." if t.get("cabin") else " Cabin: not entered in the app yet."
    if t.get("directions"):
        line += f" How to get there: {t['directions'].rstrip('.')}."
    if t.get("subjects"):
        line += f" Subjects taught: {t['subjects'].rstrip('.')}."
    if t.get("email"):
        line += f" Email: {t['email']}."
    return line


def match_teachers(q: str, teachers: list[dict]) -> list[dict]:
    """Teachers the question names, allowing small mishearings ("jayson" -> Jason). Best matches only."""
    words = [w for w in _tokens(q) if w not in NOT_NAMES and w not in TITLES]
    if not words:
        return []
    scored = []
    for t in teachers:
        names = [w for w in _tokens(t.get("name") or "") if w not in TITLES]
        score = sum(1 for w in words if w in names or difflib.get_close_matches(w, names, n=1, cutoff=0.85))
        if score:
            scored.append((score, t))
    if not scored:
        return []
    top = max(s for s, _ in scored)
    return [t for s, t in scored if s == top][:6]


def _teachers_for_subject(q: str, teachers: list[dict]) -> list[dict]:
    wanted = [c["title"].lower() for _, c in syllabus.find_courses(q)]
    words = [w for w in _tokens(q) if len(w) >= 4 and w not in NOT_NAMES and w not in TITLES]
    found = []
    for t in teachers:
        subjects = (t.get("subjects") or "").lower()
        if not subjects:
            continue
        if any(title in subjects or " ".join(title.split()[:2]) in subjects for title in wanted) or any(
                re.search(rf"\b{re.escape(w)}\b", subjects) for w in words):
            found.append(t)
    return found[:8]


def facts(q: str, today: date, want_bus: bool = False) -> list[str]:
    """Exact lines from the lists for this question (already lower-cased). Empty when it isn't about them."""
    lines = []
    teachers = rows("teachers")
    named = match_teachers(q, teachers)
    if named:
        lines.append("Asked about a teacher (from the college's teacher list): "
                     + " ".join(_teacher_line(t) for t in named))
    elif TEACHER_WORDS.search(q):
        by_subject = _teachers_for_subject(q, teachers)
        if by_subject:
            lines.append("Teachers whose subjects match the question: " + " ".join(_teacher_line(t) for t in by_subject))
        else:
            dept = [t["name"] for t in teachers if (t.get("department") or "").startswith("Information Science")]
            lines.append(f"The college's teacher list has {len(teachers)} teachers. Information Science teachers: "
                         + ", ".join(dept) + ". Ask about one by name for their cabin, subjects and email.")

    if PLACEMENT_WORDS.search(q):
        drives = sorted(placement_events(), key=lambda e: (e["event_date"], e["start_time"]))
        soon = [e for e in drives if e["event_date"] >= (today - timedelta(days=1)).isoformat()]
        if soon:
            lines.append("Placement drives (from the placement list): " + " ".join(
                f"{_day(e['event_date'])}{_at(e['start_time'])}: {e['title']}"
                + (f", venue {e['venue']}" if e["venue"] else "") + (f". {e['description']}" if e["description"] else ".")
                for e in soon[:15]))
        else:
            lines.append("There are no upcoming placement drives in the placement list.")

    if want_bus or COLLEGE_BUS.search(q):
        buses = rows("college_buses")
        if buses:
            lines.append("College buses (the college's own buses): " + " ".join(
                f"Bus {b.get('bus_no') or '?'}: route {b.get('route') or 'not given'}; stops {b.get('stops') or 'not given'}"
                + (f"; reaches college at {_clock(b['morning'])}" if b.get("morning") else "")
                + (f"; leaves college at {_clock(b['evening'])}" if b.get("evening") else "")
                + (f"; contact {b['contact']}" if b.get("contact") else "")
                + (f". {b['notes']}" if b.get("notes") else ".") for b in buses))
        elif COLLEGE_BUS.search(q):
            lines.append("The college's own bus routes have not been entered in the app yet; only the public buses "
                         "are known.")
    return lines


def _clock(hhmm: str) -> str:
    return datetime.strptime(hhmm, "%H:%M").strftime("%I:%M %p").lstrip("0")


def _at(hhmm: str) -> str:
    return f" at {_clock(hhmm)}" if hhmm else ""


def _day(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d:%A} {d.day} {d:%B %Y}"
