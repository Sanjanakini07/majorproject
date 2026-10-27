"""Bus timings around Nitte: the Bus page, its API, and exact answers for the assistant.

The timings come from the community listing "Bus Timings: Nitte" (see app/data/bus_timings.json for the
source and credit). Questions like "next bus to Karkala", "last bus to Mangalore", "buses to Udupi after
4:30" or "when does the 8 o'clock bus from the bypass reach Nitte" are worked out here, exactly.
"""
import json
import re
from datetime import datetime, time
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, Request

from .auth import verified_user
from .portal import gated_page

router = APIRouter()
DATA = Path(__file__).resolve().parent / "data" / "bus_timings.json"

BUS_WORDS = re.compile(r"\b(bus|buses|bas|busses|karkala|mangalore|mangaluru|udupi|padubidri|belman|bypass|kateel|"
                       r"mulki|manchakal|shivmogga|shimoga|kapu|travel|commute|express|transport|go home|reach nitte|"
                       r"reach college)\b")
PLACES = {"karkala": "Karkala", "mangalore": "Mangalore", "mangaluru": "Mangalore", "udupi": "Udupi",
          "padubidri": "Padubidri", "belman": "Belman", "kateel": "Kateel", "mulki": "Mulki", "manchakal": "Manchakal",
          "shivmogga": "Shivmogga", "shimoga": "Shivmogga", "kapu": "Kapu"}


@lru_cache(maxsize=1)
def data() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


@router.get("/bus", include_in_schema=False)
def bus_page(request: Request):
    return gated_page(request, "bus.html")


@router.get("/api/bus")
def bus_timings(user: dict = Depends(verified_user)):
    return data()


# --- Answers for the assistant -------------------------------------------------------------

def _t(hhmm: str) -> time:
    return datetime.strptime(hhmm, "%H:%M").time()


def _say(t: time) -> str:
    return t.strftime("%I:%M %p").lstrip("0")


def _describe(route: dict, b: dict) -> str:
    kind = " / ".join(b["type"]) or "bus"
    text = f"{_say(_t(b['time']))} {b['name']} ({kind}"
    if b.get("goes_to"):
        text += f", goes to {b['goes_to']}"
    if b.get("comes_from"):
        text += f", coming from {b['comes_from']}"
    if b.get("reaches_nitte"):
        text += f", reaches Nitte at {_say(_t(b['reaches_nitte']))}"
    return text + (", user contributed" if b.get("user_contributed") else "") + ")"


def asked_time(q: str) -> tuple[time | None, str]:
    """A time in the question and whether it means after or before it: "after 4:30", "at 5 pm", "before 9am"."""
    m = re.search(r"\b(after|from|at|around|by|before|till|until|near|about)?\s*(\d{1,2})(?:[:.](\d{2}))?\s*"
                  r"(am|pm|a\.m\.?|p\.m\.?|o'?clock)?(?=\s|$|\?|,|\.)", q)
    while m and not (m.group(1) or m.group(3) or m.group(4)):
        m = re.search(r"\b(after|from|at|around|by|before|till|until|near|about)?\s*(\d{1,2})(?:[:.](\d{2}))?\s*"
                      r"(am|pm|a\.m\.?|p\.m\.?|o'?clock)?(?=\s|$|\?|,|\.)", q[m.end():])
    if m:
        hour, minute, half = int(m.group(2)), int(m.group(3) or 0), (m.group(4) or "").replace(".", "")
        if hour <= 23 and minute < 60:
            if half.startswith("p") and hour < 12:
                hour += 12
            elif half.startswith("a") and hour == 12:
                hour = 0
            elif not half.startswith(("a", "p")) and 1 <= hour <= 6:
                hour += 12       # "the 4 o'clock bus" means 4 PM around a college
            way = "before" if m.group(1) in ("before", "till", "until", "by") else "after"
            return time(hour, minute), way
    for word, at in (("morning", time(7, 0)), ("afternoon", time(12, 0)), ("evening", time(16, 0)), ("night", time(19, 0))):
        if re.search(rf"\b{word}\b", q):
            return at, "after"
    return None, "after"


def facts(question: str, now: time | None) -> str:
    """Exact bus facts for a question: the routes it is about, the next buses, first and last, and the full lists."""
    q = question.lower()
    d = data()
    places = {PLACES[w] for w in re.findall(r"[a-z]+", q) if w in PLACES}
    to_nitte = bool(re.search(r"\b(to (nitte|college|campus)|reach (nitte|college)|from (karkala|the bypass|bypass)|"
                              r"bypass|come to college|coming to college)\b", q))
    routes = []
    for r in d["routes"]:
        if r["id"] == "bypass-to-nitte":
            if to_nitte or not places or "Karkala" in places and "from karkala" in q:
                routes.append(r)
        elif r["id"] == "to-karkala":
            if not to_nitte and (not places or "Karkala" in places):
                routes.append(r)
        elif not to_nitte and (not places or places - {"Karkala"}):
            routes.append(r)
    if not routes:
        routes = d["routes"]

    at, way = asked_time(q)
    ref = at or now
    names = {b["name"] for r in d["routes"] for b in r["buses"]}
    named = {n for n in names if re.search(rf"\b{re.escape(n.lower())}\b", q)}
    kinds = {k for k in ("express", "local", "hybrid") if re.search(rf"\b{k}\b", q)}
    lines = [f"Bus timings around Nitte, from the community listing '{d['credit']}', last updated {d['updated']}. "
             f"{d['note']} The Bus page in this app shows all of them."]
    if ref:
        lines.append(f"Time used for 'next' and 'after': {_say(ref)}" + (" (asked in the question)." if at else " (now)."))
    for r in routes:
        buses = r["buses"]
        wanted = places - {"Karkala"} if r["id"] == "to-mangalore-udupi" else set()
        if wanted:   # "to Udupi" means buses going to Udupi (including "Udupi via Kapu")
            buses = [b for b in buses if any(p.lower() in b.get("goes_to", "").lower() for p in wanted)] or buses
        if kinds:    # "express buses", "local bus"
            buses = [b for b in buses if any(k in t.lower() for t in b["type"] for k in kinds)] or buses
        if named:    # a bus by its name: every time it runs on this route
            mine = [b for b in buses if b["name"] in named]
            lines.append(f"{r['title']}, {' and '.join(sorted(named))}: " + ("; ".join(_describe(r, b) for b in mine)
                         if mine else "doesn't run on this route") + ".")
            continue
        label = r["title"]
        if wanted:
            label += f", going to {', '.join(sorted(wanted))}"
        if kinds:
            label += f", {' or '.join(sorted(kinds))} only"
        lines.append(f"{label}: {len(buses)} buses. First: {_describe(r, buses[0])}. Last: {_describe(r, buses[-1])}.")
        if ref:
            if way == "before":
                picked = [b for b in buses if _t(b["time"]) <= ref][-5:]
                lines.append(f"Buses before {_say(ref)}: " + ("; ".join(_describe(r, b) for b in picked) if picked else "none") + ".")
            else:
                picked = [b for b in buses if _t(b["time"]) >= ref][:5]
                lines.append(f"Next buses at or after {_say(ref)}: "
                             + ("; ".join(_describe(r, b) for b in picked) if picked
                                else f"none, the last one is at {_say(_t(buses[-1]['time']))}") + ".")
        if ref:   # the ones around that time, so a small offline model isn't flooded with all of them
            low, high = ref.hour * 60 + ref.minute - 120, ref.hour * 60 + ref.minute + 240
            near = [b for b in buses if low <= _t(b["time"]).hour * 60 + _t(b["time"]).minute <= high]
            if near:
                lines.append(f"All buses from {_say(_t(near[0]['time']))} to {_say(_t(near[-1]['time']))}: "
                             + "; ".join(_describe(r, b) for b in near) + ".")
        else:
            lines.append("All of them in order: " + "; ".join(_describe(r, b) for b in buses) + ".")
    return "\n".join(lines)
