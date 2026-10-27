"""Turn the official B.Tech. IS syllabus PDF (2023-04 regulations) into app/data/syllabus_is_2023.json.

    python scripts/import_syllabus.py "C:/path/14ENGR09D2_B.Tech._IS_2023-04_Regulations_Syllabus.pdf"

The JSON holds:
  semesters    the courses an IS student takes in each semester, in the order of the scheme of teaching
               (Professional Electives Group 1 are listed under semester 5, Group 2 under semester 6,
               ability enhancement courses under 5 and vocational courses under 4, where they are first offered)
  courses      every course block in the PDF (code, title, type, credits and the full syllabus text)
  regulations  the numbered sections of the regulations (attendance, evaluation, grading, ...)
The app seeds the Notes library and the assistant's knowledge from it (see app/syllabus.py).
"""
import json
import re
import sys
from pathlib import Path

from pypdf import PdfReader

OUT = Path(__file__).resolve().parent.parent / "app" / "data" / "syllabus_is_2023.json"
CODE = r"([A-Z]{2,3})\s*(\d{4})\s*[-–]\s*(\d)(?![.\d])"
ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8}
NOISE = re.compile(r"^(Regulations and curriculum for B\. ?Tech.*|Page \| ?\d+\s*|=====PAGE=====)$", re.I)
# Course outcome / programme outcome mapping tables: numbers only, not useful to read.
MAPPING = re.compile(r"^([A-Z]{2,3}\s*\d{4}\s*[-–]\s*\d\.\d|Program Outcomes|↓ Course Outcomes|1: Low|Course Outcomes Mapping)")
ACRONYMS = {"Ai": "AI", "Ml": "ML", "Ipr": "IPR", "Iot": "IoT", "Ios": "iOS", "Unix": "Unix", "Nosql": "NoSQL",
            "Mernstack": "MERN Stack", "Plc": "PLC", "Pcb": "PCB", "Matlab": "MATLAB", "It": "IT", "C++": "C++",
            "Ui": "UI", "Erp": "ERP", "And": "and", "Of": "of", "In": "in", "For": "for", "On": "on", "The": "the",
            "With": "with", "To": "to", "Its": "its", "Ii": "II", "I": "I", "Iii": "III", "Ncc": "NCC", "R": "R"}


def code_of(m: re.Match) -> str:
    return f"{m.group(1)}{m.group(2)}-{m.group(3)}"


def nice(title: str) -> str:
    """CALCULUS AND DIFFERENTIAL EQUATIONS -> Calculus and Differential Equations."""
    title = " ".join(re.sub(r"[\u2010-\u2015\u2212]", "-", title).split()).strip(" -:/")
    title = title.split(" Mandatory")[0]            # "Internship- II Mandatory Research Internship /"
    letters = [ch for ch in title if ch.isalpha()]
    if letters and sum(ch.isupper() for ch in letters) / len(letters) >= 0.8:
        words = [ACRONYMS.get(w.title(), w.title()) for w in title.split()]
        if words and words[0] not in ACRONYMS.values():
            words[0] = words[0][0].upper() + words[0][1:]
        title = " ".join(words)
    title = re.sub(r"-\s*(Iii|Ii|Iv|II|I)\b", lambda m: "-" + m.group(1).upper(), title)   # Internship-Ii -> Internship-II
    return title


def read(pdf: str) -> list[str]:
    reader = PdfReader(pdf)
    lines = []
    for page in reader.pages:
        for line in (page.extract_text() or "").splitlines():
            line = line.rstrip()
            if line.strip() and not NOISE.match(line.strip()):
                lines.append(line.strip())
    return lines


def regulations(lines: list[str], end: int) -> list[dict]:
    """Numbered top-level sections after the preamble: "9. ATTENDANCE REQUIREMENT:"."""
    start = next(i for i, l in enumerate(lines) if l.startswith("PREAMBLE"))
    heads = [i for i in range(start, end)
             if re.match(r"^\d{1,2}\.\s+[A-Z][A-Z ,/&()\-’':]{3,}$", lines[i]) and "...." not in lines[i]
             or re.match(r"^APPENDIX\s*-?\s*[A-Z]\b", lines[i])]
    heads = [start] + heads
    out = []
    for a, b in zip(heads, heads[1:] + [end]):
        title = nice(lines[a].rstrip(":"))
        text = "\n".join(lines[a + 1:b]).strip()
        if len(text) > 80:
            out.append({"title": title, "text": text})
    return out


def scheme(lines: list[str], start: int, stop: int) -> dict[int, list[str]]:
    """Course codes in each semester's scheme of teaching table."""
    sems: dict[int, list[str]] = {}
    current = None
    for line in lines[start:stop]:
        m = re.match(r"^([IVX]+) SEMESTER\s*$", line)
        if m:
            current = ROMAN[m.group(1)]
            continue
        if current is None or "Bridge" in line:
            continue
        row = re.match(rf"^\d+\.?\s+[A-Z]{{2,5}}(?:\s*\(Lab\))?\s+{CODE}", line)
        if row:
            code = code_of(re.search(CODE, line))
            if code not in sems.setdefault(current, []):
                sems[current].append(code)
    return sems


def course_blocks(lines: list[str]) -> dict[str, dict]:
    starts = []
    for i, line in enumerate(lines):
        m = re.match(rf"^Course Code\s*:?\s*{CODE}", line)
        if m:
            starts.append((i, code_of(m)))
    courses = {}
    for n, (i, code) in enumerate(starts):
        # The title is the line(s) just above "Course Code".
        title_lines, j = [], i - 1
        while j >= 0 and len(title_lines) < 2 and not re.match(rf"^Course Code|.*{CODE}.*\d{{2,3}}\s*$", lines[j]):
            if re.match(r"^\(.*\)$", lines[j]):   # "(For All except AI)"
                j -= 1
                continue
            if lines[j].isupper() or lines[j].istitle() or re.match(r"^[A-Za-z].*[A-Z]{3}", lines[j]):
                title_lines.insert(0, lines[j])
                j -= 1
                if lines[j + 1].isupper() and not lines[j].isupper():
                    break
            else:
                break
        end = starts[n + 1][0] - 1 if n + 1 < len(starts) else len(lines)
        body = lines[i:end]
        # Cut the next course's title off the end, and drop the outcome mapping tables.
        nxt_title = nice(" ".join(_title_above(lines, starts[n + 1][0]))) if n + 1 < len(starts) else ""
        while body and nxt_title and nice(body[-1]) and nice(body[-1]) in nxt_title:
            body.pop()
        body = [l for l in body if not MAPPING.match(l) and not re.match(r"^[\d\s\-–.]+$", l)]
        text = "\n".join(body)
        if text.count("SEMESTER") and "List of" in text:
            text = text.split("List of")[0]
        kind = re.search(r"Course Type\s*:?\s*([A-Z]{2,5})", text)
        credits = re.search(r"Credits\s*:?\s*0?(\d+)", text)
        title = nice(" ".join(title_lines)) or code
        if code not in courses or len(text) > len(courses[code]["text"]):
            courses[code] = {"code": code, "title": title, "type": kind.group(1) if kind else "",
                             "credits": int(credits.group(1)) if credits else None, "text": text.strip()}
    return courses


def _title_above(lines: list[str], i: int) -> list[str]:
    out, j = [], i - 1
    while j >= 0 and len(out) < 2 and (lines[j].isupper() or lines[j].istitle()):
        out.insert(0, lines[j])
        j -= 1
    return out


def table_titles(lines: list[str]) -> dict[str, str]:
    """code -> title from the one-line rows of the scheme and elective tables (nicer than the block headings)."""
    titles = {}
    for line in lines:
        parts = re.split(rf"\b{CODE}", line)
        # re.split with 3 groups: [before, g1, g2, g3, after, g1, g2, g3, after...]
        for k in range(1, len(parts) - 3, 4):
            code = f"{parts[k]}{parts[k + 1]}-{parts[k + 2]}"
            after = parts[k + 3].strip()
            after = re.split(r"\s+(?:MA|PH|CS|EC|HU|MAT|CY|EE|BT|CV|IS|ME|MG|RI|Any)\b\s*(?:Dept\.?)?\s*\d", after)[0]
            after = re.sub(r"\s*\(.*$", "", after).strip(" -–")
            if 3 < len(after) < 70 and re.match(r"^[A-Za-z]", after) and not re.search(r"\d{2}", after):
                titles.setdefault(code, nice(after))
    return titles


def main(pdf: str) -> None:
    lines = read(pdf)
    scheme_start = next(i for i, l in enumerate(lines) if "Scheme of Teaching and Examinations" in l)
    electives_at = next(i for i, l in enumerate(lines) if l.startswith("List of Professional Elective Courses"))
    sems = scheme(lines, scheme_start, electives_at)
    courses = course_blocks(lines)
    titles = table_titles(lines[scheme_start:])
    for code, c in courses.items():
        table = titles.get(code)
        if table and (c["title"] == code or c["title"].lower().endswith(" " + table.lower())):
            c["title"] = table          # "Vocational Education Courses Python Programming Fundamentals" -> the table's name
    # Phase II of the major project has no block of its own: the Major Project block covers both phases.
    for sem_codes in sems.values():
        for code in sem_codes:
            sibling = next((c for c in courses if c[:5] == code[:5] and c != code), None)
            if code not in courses and sibling and code in titles:
                courses[code] = {**courses[sibling], "code": code, "title": titles[code].split(" Student")[0]}

    # Professional electives (Group 1: x2xx, Group 2: x3xx), ability enhancement (x65x) and vocational (x55x).
    region = "\n".join(lines[electives_at - 120: electives_at + 60])
    listed = [code_of(m) for m in re.finditer(CODE, region)]
    group1 = [c for c in listed if c.startswith("IS") and c[3] == "2" and c not in sems.get(5, [])]
    group2 = [c for c in listed if c.startswith("IS") and c[3] == "3"]
    aec = [c for c in listed if re.match(r"IS\d65\d|ME1659", c)]
    vec = [c for c in listed if re.match(r"IS\d55\d", c)]
    extra = {5: [("Professional Elective, Group 1", c) for c in dict.fromkeys(group1)]
                + [("Ability Enhancement Course", c) for c in dict.fromkeys(aec)],
             6: [("Professional Elective, Group 2", c) for c in dict.fromkeys(group2)],
             4: [("Vocational Education Course", c) for c in dict.fromkeys(vec)]}

    semesters = {}
    for sem in range(1, 9):
        rows = [{"code": c, "kind": "Core"} for c in sems.get(sem, []) if c in courses]
        rows += [{"code": c, "kind": kind} for kind, c in extra.get(sem, []) if c in courses]
        semesters[str(sem)] = rows
    data = {
        "source": Path(pdf).name,
        "program": "B.Tech. Information Science and Engineering, NMAMIT (2023-04 regulations, batch 2023-27)",
        "semesters": semesters,
        "courses": courses,
        "regulations": regulations(lines, scheme_start),
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(courses)} courses, {len(data['regulations'])} regulation sections -> {OUT}")
    for sem, rows in semesters.items():
        print(f"  semester {sem}: " + "; ".join(f"{courses[r['code']]['title']} ({r['code']})" for r in rows))


if __name__ == "__main__":
    main(sys.argv[1])
