"""Facts about the signed-in person and the calendar, worked out exactly and handed to the assistant.

Text search (rag.py) is good at "when is the library open", but it can't do arithmetic, dates or "my".
So questions like "what is my name", "my marks last sem", "my CGPA", "how many classes can I miss",
"is there an event on October 30th", "events next week" or "what class do I have now" are answered
from here. Only the asker's own records are ever included.
"""
import re
from datetime import date, datetime, time, timedelta
from typing import NamedTuple

from . import academics, bus, db, syllabus

GRADE_POINTS = academics.GRADE_POINTS

MARKS_WORDS = re.compile(r"\b(marks?|grades?|scores?|scored|results?|sgpa|cgpa|gpa|cpi|percent\w*|pass(ed)?|fail(ed)?|"
                         r"backlogs?|internals?|externals?|topper|best|worst|lowest|highest|semesters?|sems?)\b")
ATTENDANCE_WORDS = re.compile(r"\b(attendance|attend\w*|present|absent|bunk\w*|miss(ed)?|skip\w*|leave|shortage|"
                              r"detained|condon\w*|75)\b")
EVENT_WORDS = re.compile(r"\b(events?|fests?|happening|going on|programs?|programmes?|activit\w+|upcoming|"
                         r"workshops?|hackathons?|seminars?|placements?|drives?|competitions?|sports|cultural|"
                         r"meet|exams?|tests?|holidays?|scheduled|plans?)\b")
CLASS_WORDS = re.compile(r"\b(timetable|time table|class(es)?|lectures?|periods?|"
                         r"room|free|break|lunch|college today|first hour|next hour)\b")
STUDY_WORDS = re.compile(r"\b(notes?|revis\w*|study|studies|studying|syllabus|subjects?|units?|topics?|prepar\w*|"
                         r"learn\w*|read|materials?|important questions|question papers?|courses?|papers?)\b")
ME_WORDS = re.compile(r"\b(my|me|myself|mine|i|name|who am i|roll|usn|branch|date|day|time|"
                      r"today|todays|tonight|tomorrow|yesterday|now|week|weekend|month)\b")

MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"]
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
SHORT_DAYS = {"mon": 0, "tue": 1, "tues": 1, "wed": 2, "thu": 3, "thurs": 3, "fri": 4, "sat": 5}
_MONTH = "|".join(sorted({*MONTHS, *(m[:3] for m in MONTHS), "sept"}, key=len, reverse=True))
_DAY_FIRST = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s*(?:of\s+)?({_MONTH})\b")
_MONTH_FIRST = re.compile(rf"\b({_MONTH})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b")
_NUMERIC = re.compile(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b")
_MONTH_ONLY = re.compile(rf"\b(in|during|of|for|this|next|whole|entire)?\s*({_MONTH})\b")

ORDINALS = {"first": 1, "1st": 1, "one": 1, "second": 2, "2nd": 2, "two": 2, "third": 3, "3rd": 3, "three": 3,
            "fourth": 4, "4th": 4, "four": 4, "fifth": 5, "5th": 5, "five": 5, "sixth": 6, "6th": 6, "six": 6,
            "seventh": 7, "7th": 7, "seven": 7, "eighth": 8, "8th": 8, "eight": 8}
_ORD = "|".join(sorted(ORDINALS, key=len, reverse=True))
_SEM = r"(?:sem|semester|semesters|sems)"


# --- Reading the question ----------------------------------------------------------------

def _month_number(word: str) -> int:
    return next(i for i, m in enumerate(MONTHS, 1) if m.startswith(word[:3]))


def _day(d: date) -> str:
    return f"{d:%A} {d.day} {d:%B %Y}"


def _clock(t: time) -> str:
    return t.strftime("%I:%M %p").lstrip("0")


def dates_in(q: str, today: date) -> list[date]:
    """The calendar days a question talks about: "october 30th", "30 oct", "30/10", "tomorrow", "next friday"."""
    found = []

    def add(day: int, month: int, year: int | None = None):
        try:
            d = date(year or today.year, month, day)
        except ValueError:
            return
        if year is None and d < today - timedelta(days=180):
            d = date(d.year + 1, month, day)     # "january 5" asked in december means next year
        found.append(d)

    for m in _DAY_FIRST.finditer(q):
        add(int(m.group(1)), _month_number(m.group(2)))
    for m in _MONTH_FIRST.finditer(q):
        add(int(m.group(2)), _month_number(m.group(1)))
    for m in _NUMERIC.finditer(q):
        year = int(m.group(3)) + (2000 if len(m.group(3)) == 2 else 0) if m.group(3) else None
        add(int(m.group(1)), int(m.group(2)), year)      # day/month, the Indian way
    if "day after tomorrow" in q:
        found.append(today + timedelta(days=2))
    elif re.search(r"\b(tomorrow|tmrw|tmr|tomorow|tommorow)\b", q):
        found.append(today + timedelta(days=1))
    if re.search(r"\byesterday\b", q):
        found.append(today - timedelta(days=1))
    if re.search(r"\b(today|todays|tonight|now)\b", q):
        found.append(today)
    names = {**{n: i for i, n in enumerate(WEEKDAYS)}, **SHORT_DAYS}
    for name, i in names.items():
        if re.search(rf"\b{name}s?\b", q):
            ahead = (i - today.weekday()) % 7
            if ahead == 0 and re.search(rf"\b(next|coming)\s+{name}", q):
                ahead = 7
            if re.search(rf"\blast\s+{name}", q):
                ahead -= 7
            found.append(today + timedelta(days=ahead))
    return list(dict.fromkeys(found))


def ranges_in(q: str, today: date) -> list[tuple[str, date, date]]:
    """Spans of days: this week, next week, the weekend, this month, next month, "in november"."""
    out = []
    monday = today - timedelta(days=today.weekday())
    if re.search(r"\b(this|the|rest of the) week\b", q):
        out.append(("this week", today, monday + timedelta(days=6)))
    if re.search(r"\b(next|coming|upcoming) week\b", q):
        out.append(("next week", monday + timedelta(days=7), monday + timedelta(days=13)))
    if re.search(r"\bweekend\b", q):
        saturday = monday + timedelta(days=5)
        out.append(("this weekend", max(today, saturday), saturday + timedelta(days=1)))
    first = today.replace(day=1)
    following = (first + timedelta(days=32)).replace(day=1)
    if re.search(r"\bthis month\b", q):
        out.append(("this month", first, following - timedelta(days=1)))
    if re.search(r"\bnext month\b", q):
        out.append(("next month", following, (following + timedelta(days=32)).replace(day=1) - timedelta(days=1)))
    day_months = {m.group(2) for m in _DAY_FIRST.finditer(q)} | {m.group(1) for m in _MONTH_FIRST.finditer(q)}
    for m in _MONTH_ONLY.finditer(q):
        word = m.group(2)
        if word in day_months or (word == "may" and not m.group(1)):
            continue          # "october 30" is a day, not the month; "may i know" is not about May
        n = _month_number(word)
        year = today.year + (1 if n < today.month - 6 else 0)
        start = date(year, n, 1)
        end = (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        out.append((f"in {MONTHS[n - 1].title()} {year}", start, end))
    return list(dict.fromkeys(out))


YEARS = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4, "final": 4}
_YEAR = "|".join(sorted(YEARS, key=len, reverse=True))


def semesters_in(q: str, current: int) -> list[tuple[int, str]]:
    """Which semesters a question means: "this sem", "last sem", "first sem", "sem 3", "first year", "this year"."""
    found = []
    for m in re.finditer(rf"\b({_YEAR})[\s-]+years?\b|\byear\s*-?\s*([1-4])\b", q):
        y = YEARS[m.group(1)] if m.group(1) else int(m.group(2))
        found += [(2 * y - 1, f"year {y}, semester {2 * y - 1}"), (2 * y, f"year {y}, semester {2 * y}")]
    if re.search(r"\b(this|current) year\b", q):
        y = (current + 1) // 2
        found += [(2 * y - 1, f"this year, semester {2 * y - 1}"), (2 * y, f"this year, semester {2 * y}")]
    if re.search(r"\bfreshers?\b", q):
        found += [(1, "year 1, semester 1"), (2, "year 1, semester 2")]
    if re.search(rf"\b(this|current|present|ongoing|running)\s+{_SEM}\b", q):
        found.append((current, "the current semester"))
    if re.search(rf"\b(last|previous|prev|past|latest|recent)\s+{_SEM}\b", q):
        found.append((current - 1, "last semester"))
    for m in re.finditer(rf"\b({_ORD})\s+{_SEM}\b|\b{_SEM}\s*-?\s*({_ORD}|\d)\b", q):
        word = m.group(1) or m.group(2)
        n = int(word) if word.isdigit() else ORDINALS[word]
        if 1 <= n <= 8:
            found.append((n, f"semester {n}"))
    return list(dict.fromkeys(found))


# --- The facts --------------------------------------------------------------------------

def _gpa(grades: list[str]) -> float:
    """Every subject carries the same weight here, so the SGPA is the average grade point."""
    return round(sum(GRADE_POINTS[g] for g in grades) / len(grades), 2) if grades else 0.0


def _marks(email: str, current: int, asked: list[tuple[int, str]]) -> str:
    report = academics.marks_report(email)
    if not report["semesters"]:
        return "No marks are recorded for this person yet."
    by_sem = {s["semester"]: s for s in report["semesters"]}
    lines = [f"Marks: every subject is out of 100 (internal out of 50 plus external out of 50). Semester {current} is "
             f"going on now, so it has no marks yet; they come after its semester end exams. "
             f"Last semester means semester {current - 1}."]
    for n, label in asked:
        s = by_sem.get(n)
        if s:
            lines.append(f"Asked about {label} (semester {n}): total {s['total']} out of {s['max']}, {s['percent']} "
                         f"percent, grade {s['grade']}, SGPA {_gpa([x['grade'] for x in s['subjects']])}.")
        elif n == current:
            lines.append(f"Asked about {label} (semester {n}): it is still going on, so there are no marks yet.")
        else:
            lines.append(f"Asked about {label} (semester {n}): no marks are recorded for it.")
    every = []
    for s in report["semesters"]:
        every += s["subjects"]
        subjects = "; ".join(f"{x['subject']} {x['total']} (internal {x['internal']}, external {x['external']}, "
                             f"grade {x['grade']})" for x in s["subjects"])
        lines.append(f"Semester {s['semester']}: total {s['total']} out of {s['max']}, {s['percent']} percent, grade "
                     f"{s['grade']}, SGPA {_gpa([x['grade'] for x in s['subjects']])}. Subjects: {subjects}.")
    best = max(every, key=lambda x: x["total"])
    worst = min(every, key=lambda x: x["total"])
    failed = [x["subject"] for x in every if not x["passed"]]
    lines.append(f"Overall: {report['overall_percent']} percent, CGPA {_gpa([x['grade'] for x in every])} out of 10. "
                 f"Best subject: {best['subject']} ({best['total']}). Lowest: {worst['subject']} ({worst['total']}). "
                 f"Backlogs: {', '.join(failed) if failed else 'none'}.")
    return "\n".join(lines)


def _attendance(email: str) -> str:
    report = academics.attendance_report(email)
    if not report["subjects"]:
        return "No attendance is recorded for this person yet."
    need, floor = report["required_percent"], report["condonable_percent"]

    def can_miss(s: dict, limit: int) -> int:        # classes that can be missed and still be at the limit
        return max(0, int((s["attended"] - limit / 100 * s["total"]) / (limit / 100)))

    def to_reach(s: dict, limit: int) -> int:        # classes in a row needed to get back to the limit
        return max(0, -int(-(limit / 100 * s["total"] - s["attended"]) // (1 - limit / 100)))

    parts = []
    for s in report["subjects"]:
        if s["percent"] >= need:
            note = (f"fine; can miss {can_miss(s, need)} more classes and stay at {need} percent, "
                    f"or {can_miss(s, floor)} before falling under {floor} percent")
        elif s["percent"] >= floor:
            note = (f"below {need} percent, so it needs condonation by the principal; attend the next "
                    f"{to_reach(s, need)} classes in a row to reach {need} percent; missing more than "
                    f"{can_miss(s, floor)} classes would take it under {floor} percent")
        else:
            note = (f"under {floor} percent: not allowed to write this course's SEE (N grade) unless it gets back to "
                    f"{floor} percent, which needs the next {to_reach(s, floor)} classes in a row")
        parts.append(f"{s['subject']}: {s['percent']} percent ({s['attended']} of {s['total']} classes), {note}")
    short = [s["subject"] for s in report["subjects"] if s["percent"] < need]
    barred = [s["subject"] for s in report["subjects"] if s["percent"] < floor]
    return (f"Attendance this semester: overall {report['overall_percent']} percent. The regulations need {need} percent "
            f"in every course; up to 10 percent can be condoned, and under {floor} percent the student can't write that "
            f"course's SEE. " + ". ".join(parts) + ". "
            + (f"Below {need} percent: {', '.join(short)}. " if short else f"Every subject is at {need} percent or more. ")
            + (f"Under {floor} percent: {', '.join(barred)}." if barred else f"No subject is under {floor} percent."))


def _show(e: dict, details: bool = False) -> str:
    when = f" at {_clock(datetime.strptime(e['start_time'], '%H:%M').time())}" if e["start_time"] else ""
    text = f"{e['title']}{when}" + (f", venue {e['venue']}" if e["venue"] else "")
    return text + (f". {e['description']}" if details and e["description"] else "")


def _events(today: date, days: list[date], spans: list[tuple[str, date, date]]) -> str:
    """Exact answers first (the days and spans asked about), then the whole calendar, so nothing is missed."""
    events = db.list_events()
    on = lambda d: [e for e in events if e["event_date"] == d.isoformat()]  # noqa: E731
    lines = []
    for d in days:
        found = on(d)
        lines.append(f"Events on {_day(d)}{' (today)' if d == today else ''}: "
                     + ("; ".join(_show(e, True) for e in found) if found else "none, nothing is scheduled that day") + ".")
    for label, start, end in spans:
        found = [e for e in events if start.isoformat() <= e["event_date"] <= end.isoformat()]
        lines.append(f"Events {label} ({_day(start)} to {_day(end)}): "
                     + ("; ".join(f"{_day(date.fromisoformat(e['event_date']))}: {_show(e)}" for e in found)
                        if found else "none") + ".")
    if today not in days:
        found = on(today)
        lines.append("Events today: " + ("; ".join(_show(e, True) for e in found) if found else "none") + ".")
    upcoming = [e for e in events if e["event_date"] > today.isoformat()]
    if upcoming:
        nxt = upcoming[0]
        gap = (date.fromisoformat(nxt["event_date"]) - today).days
        lines.append(f"Next event: {_day(date.fromisoformat(nxt['event_date']))}, in {gap} day{'' if gap == 1 else 's'}: "
                     f"{_show(nxt, True)}.")
    recent = [e for e in events if e["event_date"] >= (today - timedelta(days=14)).isoformat()][:25]
    if recent:
        lines.append("Full event calendar in date order: " + "; ".join(
            f"{_day(date.fromisoformat(e['event_date']))}: {_show(e)}"
            + (" (already over)" if e["event_date"] < today.isoformat() else "") for e in recent) + ".")
    else:
        lines.append("There are no events in the calendar.")
    return "\n".join(lines)


SLOT = re.compile(r"(\d{1,2}:\d{2}\s*[AP]M)\s+to\s+(\d{1,2}:\d{2}\s*[AP]M):\s*([^.]+)")


def _parse_clock(text: str) -> time:
    return datetime.strptime(text.replace(" ", ""), "%I:%M%p").time()


def _timetable(semester: int, days: list[date], today: date, now: time | None) -> str:
    lines = []
    for d in days:
        label = "today" if d == today else "tomorrow" if d == today + timedelta(days=1) else "on that day"
        if d.weekday() == 6:
            lines.append(f"Classes {label} ({_day(d)}): none, it is a Sunday.")
            if d == today:
                lines.append(_next_day_first_class(semester, today))
            continue
        module = db.get_module_by_title(f"Timetable: Semester {semester}, {d:%A}")
        if not module:
            lines.append(f"Classes {label} ({_day(d)}): no timetable has been added for semester {semester} on {d:%A}s.")
            continue
        lines.append(f"Classes {label} ({_day(d)}): {module['content']}")
        if d == today and now:
            slots = [(_parse_clock(a), _parse_clock(b), what.strip()) for a, b, what in SLOT.findall(module["content"])]
            current = next((w for a, b, w in slots if a <= now < b), None)
            later = [(a, w) for a, b, w in slots if a > now]
            if current:
                lines.append(f"Class going on right now: {current}.")
            elif slots and now < slots[0][0]:
                lines.append("Classes have not started yet today.")
            if later:
                lines.append(f"Next class today: {later[0][1]} at {_clock(later[0][0])}.")
            elif slots:
                lines.append("No more classes today; today's classes are over.")
                lines.append(_next_day_first_class(semester, today))
    return "\n".join(lines)


def _next_day_first_class(semester: int, today: date) -> str:
    """When today's classes are over (or it's Sunday): the first class on the next working day."""
    for ahead in range(1, 8):
        d = today + timedelta(days=ahead)
        module = db.get_module_by_title(f"Timetable: Semester {semester}, {d:%A}")
        slot = SLOT.search(module["content"]) if module and d.weekday() != 6 else None
        if slot:
            when = "tomorrow" if ahead == 1 else f"on {_day(d)}"
            return f"Next class: {when}, {slot.group(3).strip()} at {_clock(_parse_clock(slot.group(1)))}."
    return ""


def _subjects(semesters: list[int]) -> str:
    """The official courses of these semesters with their units, and the electives by name."""
    lines = []
    for sem in semesters:
        courses = syllabus.semester_courses(sem)
        if not courses:
            lines.append(f"Semester {sem}: no courses are listed in the syllabus.")
            continue
        core = [c for c in courses if c["kind"] == "Core"]
        lines.append(f"Semester {sem} courses in the official IS syllabus (2023-04 regulations): "
                     + "; ".join(f"{c['title']} ({c['code']}, {c['credits']} credits)" for c in core) + ".")
        for c in core:
            if syllabus.outline(c["code"]):
                lines.append(f"{c['title']} units: {syllabus.outline(c['code'])}.")
        for kind in dict.fromkeys(c["kind"] for c in courses if c["kind"] != "Core"):
            lines.append(f"Semester {sem} {kind} choices: " + "; ".join(c["title"] for c in courses if c["kind"] == kind) + ".")
        lines.append(f"The full syllabus of each course is a note on the Notes page under Semester {sem}.")
    return "\n".join(lines)


ELECTIVE_WORDS = re.compile(r"\b(electives?|streams?|pec|oec|open elective|ability enhancement|aec|vocational|vec|"
                            r"group ?(1|2|i|ii|one|two))\b")
RULE_WORDS = re.compile(r"\b(pass(ing)?|fail(ed|ing)?|grades?|grading|cgpa|sgpa|distinction|first class|second class|"
                        r"probation|condon\w*|minimum attendance|attendance (rule|requirement)s?|cie|see|n grade|"
                        r"mid ?sem\w*|internals?|rules?|regulations?|eligib\w*|detained|re-?register\w*|backlogs?)\b")


def _electives() -> str:
    """Every elective an IS student can choose, by group, from the syllabus."""
    groups: dict[str, list[str]] = {}
    for sem, c in syllabus.listed():
        if c["kind"] != "Core":
            groups.setdefault(f"{c['kind']} (listed under semester {sem})", []).append(f"{c['title']} ({c['code']})")
    lines = [f"{kind}: " + "; ".join(names) + "." for kind, names in groups.items()]
    lines.append(syllabus.streams_text())
    lines.append("Professional Elective I is taken in semester 5, II and III in semester 6, and IV and V in semester 7. "
                 "Electives I, II and IV come from Group 1; III and V from Group 2. Open Electives I and II (semesters 6 "
                 "and 7) are courses offered by other departments.")
    return "\n".join(lines)


def _rules() -> str:
    """The numbers from the 2023-04 regulations, said plainly."""
    bands = ", ".join(f"{letter} for {floor} percent and above ({points} points)" for floor, letter, points in syllabus.GRADES)
    return (f"Rules from the 2023-04 regulations: each course has 50 marks of CIE (continuous internal evaluation: two "
            f"mid-semester exams for 40 marks plus quizzes and assignments for 10) and 50 marks of SEE (semester end "
            f"exam). To pass a course you need {syllabus.PASS_PERCENT} percent of the total, that is 40 out of 100 marks "
            f"(CIE plus SEE). Grades: {bands}, and F below {syllabus.PASS_PERCENT} percent (0 points). Students with less "
            f"than 40 percent in CIE or less than {syllabus.CONDONABLE_TO} percent attendance can't write the SEE and get "
            f"an N grade. Attendance needed: {syllabus.REQUIRED_ATTENDANCE} percent in every course; the principal can "
            f"condone up to 10 percent. CGPA of 7 or more is first class with distinction, 6 to 6.99 first class, 5 to "
            f"5.99 second class, and below 5 means academic probation.")


def _named_courses(courses: list[tuple[int, dict]]) -> str:
    lines = []
    for sem, c in courses:
        kind = "core course" if c["kind"] == "Core" else c["kind"]
        lines.append(f"{c['title']} ({c['code']}) is a semester {sem} {kind}, {c['credits']} credits. Its full syllabus "
                     f"is a note on the Notes page under Semester {sem}, {c['title']}."
                     + (f" Units: {syllabus.outline(c['code'])}." if syllabus.outline(c["code"]) else ""))
    return "\n".join(lines)


class Facts(NamedTuple):
    text: str = ""                       # what the model is told
    covered: tuple[str, ...] = ()        # knowledge-entry title prefixes the facts replace (e.g. "Event: ")
    note_semesters: tuple[int, ...] = ()  # semesters whose notes should be used, and no others
    timetable_semesters: tuple[int, ...] = ()  # the only semesters whose timetables are relevant to this person
    courses: tuple[str, ...] = ()        # course codes the question names ("OS notes", "syllabus of DBMS")


def adjust_hits(hits: list[dict], facts: Facts) -> list[dict]:
    """Drop search results the exact facts replace or that are from the wrong semester; add the courses asked about."""
    def wrong_semester(title: str) -> bool:
        m = re.match(r"Notes: Semester (\d+),", title)
        if facts.note_semesters and m and int(m.group(1)) not in facts.note_semesters:
            return True
        m = re.match(r"Timetable: Semester (\d+),", title)   # another semester's timetable is never about you
        return bool(facts.timetable_semesters and m and int(m.group(1)) not in facts.timetable_semesters)

    kept = [h for h in hits if not h["title"].startswith(facts.covered) and not wrong_semester(h["title"])]
    have = {h.get("module_id") for h in kept}
    # The full syllabus of a course the question names (search may miss it behind a short name like "OS").
    for module in db.note_modules_for(list(facts.courses))[:2]:
        if module["id"] not in have:
            kept.insert(0, {"title": module["title"], "text": f"{module['title']}\n{module['content'][:6000]}",
                            "distance": 0.0, "module_id": module["id"]})
            have.add(module["id"])
    # For a whole semester the facts list the courses and units; these entries only give the links on screen.
    if facts.note_semesters:
        core = {c["code"] for sem in facts.note_semesters for c in syllabus.semester_courses(sem) if c["kind"] == "Core"}
        for module in db.note_modules(list(facts.note_semesters)):
            if module["id"] not in have and module["note_code"] in core:
                kept.append({"title": module["title"], "text": module["title"], "distance": 0.0, "module_id": module["id"]})
    return kept


def build(email: str, session_name: str, question: str, today: date | None = None,
          now: time | None = None) -> Facts:
    """The exact facts for this question. Empty when it is not about the person, their studies or the calendar."""
    if today is None:
        stamp = datetime.now()
        today, now = stamp.date(), now or stamp.time()
    q = " ".join(question.lower().replace("’", "'").split())
    days, spans = dates_in(q, today), ranges_in(q, today)
    want_marks = bool(MARKS_WORDS.search(q))
    want_attendance = bool(ATTENDANCE_WORDS.search(q))
    want_bus = bool(bus.BUS_WORDS.search(q))
    # A date in a bus question ("bus tomorrow at 8") is about the bus, not the events or classes that day.
    want_events = bool(EVENT_WORDS.search(q) or ((days or spans) and not want_bus))
    want_classes = bool(CLASS_WORDS.search(q) or (days and not EVENT_WORDS.search(q) and not want_bus))
    named = syllabus.find_courses(q)
    want_notes = bool(STUDY_WORDS.search(q) or named)
    want_electives = bool(ELECTIVE_WORDS.search(q))
    want_rules = bool(RULE_WORDS.search(q))
    profile = db.get_profile(email)
    if not (want_marks or want_attendance or want_events or want_classes or want_notes or want_bus or want_electives
            or want_rules or ME_WORDS.search(q)):
        return Facts(timetable_semesters=(profile["semester"],) if profile else ())

    name = academics.clean_name((profile or {}).get("name") or session_name or "", email) or email
    lines = [f"Name: {name}. Roll number: {email.split('@')[0].upper()}. College email: {email}."]
    if profile:
        lines.append(f"Branch: {profile['branch'] or 'not known'}. Current semester: {profile['semester']}.")
    lines.append(f"Right now it is {_day(today)}" + (f", {_clock(now)}" if now else "") + ".")
    covered = []
    current = profile["semester"] if profile else 6
    asked_semesters = semesters_in(q, current)
    if profile and (want_marks or (asked_semesters and not want_notes and not want_classes)):
        lines.append(_marks(email, profile["semester"], asked_semesters))
    note_semesters = ()
    if named:
        lines.append(_named_courses(named))
    elif want_notes and (asked_semesters or re.search(r"\b(subjects?|courses?|syllabus)\b", q)):
        # "what subjects do I have" without a semester means the current one
        note_semesters = tuple(dict.fromkeys(n for n, _ in asked_semesters)) or (current,)
        lines.append(_subjects(list(note_semesters)))
    if want_electives:
        lines.append(_electives())
    if want_rules or want_attendance:
        lines.append(_rules())
    if want_bus:
        lines.append(bus.facts(q, now))
    if profile and want_attendance:
        lines.append(_attendance(email))
    if want_events:
        lines.append(_events(today, days, spans))
        covered.append("Event: ")
    if profile and want_classes:
        lines.append(_timetable(profile["semester"], days or [today], today, now))
        covered.append("Timetable: ")
    timetable_semesters = tuple(dict.fromkeys([current, *(n for n, _ in asked_semesters)])) if profile else ()
    return Facts("\n".join(line for line in lines if line), tuple(covered), note_semesters, timetable_semesters,
                 tuple(c["code"] for _, c in named))


def context_for(email: str, session_name: str, question: str, today: date | None = None,
                now: time | None = None) -> str:
    return build(email, session_name, question, today, now).text
