"""Retrieval-Augmented Generation.

1. Index:  every knowledge module is split into chunks; each chunk is turned
           into an embedding and stored in ChromaDB (the vector database).
2. Search: the question is embedded the same way and ChromaDB returns the
           chunks whose meaning is closest to it.
3. Answer: those chunks are given to the Groq model as context, with an
           instruction to answer only from them.

ChromaDB's built-in embedding model (all-MiniLM-L6-v2) runs locally and is
free. It is downloaded (~80 MB) the first time it is used.
"""
import logging
import re
import threading
from datetime import date
from functools import lru_cache

import chromadb
from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2

from . import config, syllabus

log = logging.getLogger(__name__)

# Keep the search model with the other models (not in ~/.cache), so the installed desktop app ships it
# and can search with no internet from the first question.
ONNXMiniLM_L6_V2.DOWNLOAD_PATH = config.MODELS_DIR / ONNXMiniLM_L6_V2.MODEL_NAME

COLLECTION = "knowledge"
CHUNK_SIZE = 800      # characters per chunk
CHUNK_OVERLAP = 120   # repeated between neighbouring chunks so nothing is cut in half

# Serialises index changes so a rebuild can't interleave with an edit.
_write_lock = threading.Lock()

SYSTEM_PROMPT = """You are the NMAMIT campus voice assistant. Students ask you questions out loud and your reply is read aloud to them.

Rules:
- Answer ONLY from the context below. If the context does not contain the answer, say you don't have that information yet and suggest checking with the college office.
- Keep it short: at most 4 sentences.
- Plain spoken English. No markdown, bullet points, tables, emojis or URLs.
- Never invent dates, fees, names or phone numbers.
- Much of the context was typed by college staff and can be messy: shorthand, abbreviations, typos, copied messages, tables squashed into one line, dates like 15/12 or "mon 10am". Work out what it means, the way a sensible senior student would (FM = Financial Management, MSE = mid-semester exam, SEE = semester end exam, T&P = training and placement, "drive" = campus placement drive), and answer in clear sentences. Use only what it says; if it is truly unclear, say what the notice says and suggest confirming with the department.
- Students speak their questions, so names and words may be misheard or misspelt (for example "Jayson sir" for Jason, "data base" for database). Match them to the closest name or subject in the context.
- Some context comes from subject notes or events. Say which subject or event it is from, for example "From the Operating Systems notes". The screen shows a link, so don't read out any address.
- Notes are kept on the Notes page of this app, sorted by semester and subject. When asked where to find notes, say they are on the Notes page under that semester and subject, say what they cover, and mention the link on screen.
- The part of the context under "About the person asking" was worked out exactly by the college system for the person talking to you, and it is always correct. Use it for "my name", "my marks", "my CGPA", "my attendance", "how many classes can I miss", "today's date", "events on a date" and "my classes". Prefer it over anything else in the context.
- Lines that start with "Asked about", "Events on", "Events this week" (and similar), "Next event", "Next class" or "Class going on right now" are the exact answer to that part of the question. If such a line lists an event, never say there is none; if it says none, say nothing is scheduled.
- For "upcoming", "next" or "this week" questions use "Right now it is" as today, and don't call a past event upcoming.
- Say numbers plainly. Read grades as words, for example A+ as "A plus". If the question asks for more than you can say in 4 sentences, give the totals first and offer to go into subjects.
- Never share one person's records as anyone else's, and never guess a number that is not in the context.
- Subjects, units, textbooks and rules come from the official B.Tech. Information Science syllabus and regulations (2023-04). Answer syllabus questions from that text, and name the course, for example "In the Operating Systems Fundamentals syllabus, unit 2 covers ...".
- For buses, use the bus lines in the context. Give the time and the bus name, say whether it is express or local, and remind that times can vary by a few minutes when it matters."""


def build_context(hits: list[dict], personal: str = "") -> str:
    parts = [f"About the person asking:\n{personal}"] if personal else []
    parts.extend(h["text"] for h in hits)
    return "\n\n---\n\n".join(parts)


def system_prompt(context: str) -> str:
    return f"{SYSTEM_PROMPT}\n\nToday is {date.today():%A %d %B %Y}.\n\nContext:\n{context}"


@lru_cache(maxsize=1)
def _collection():
    client = chromadb.PersistentClient(
        path=str(config.DATA_DIR / "chroma"),
        settings=chromadb.config.Settings(anonymized_telemetry=False),
    )
    return client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping pieces, preferring to cut at a line or sentence end."""
    text = text.strip()
    if len(text) <= size:
        return [text] if text else []
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            cut = max(text.rfind("\n", start, end), text.rfind(". ", start, end))
            if cut > start + size // 2:
                end = cut + 1
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = end - overlap
    return [c for c in chunks if c]


def _add(module: dict) -> None:
    pieces = chunk_text(module["content"])
    if not pieces:
        return
    _collection().add(
        ids=[f"{module['id']}-{i}" for i in range(len(pieces))],
        # The title goes into every chunk so a search for the topic finds it.
        documents=[f"{module['title']}\n{p}" for p in pieces],
        metadatas=[{"module_id": module["id"], "title": module["title"]} for _ in pieces],
    )


def index_module(module: dict) -> None:
    """Add or replace one module in the vector database."""
    with _write_lock:
        _collection().delete(where={"module_id": module["id"]})
        _add(module)


def remove_module(module_id: int) -> None:
    with _write_lock:
        _collection().delete(where={"module_id": module_id})


def rebuild(modules: list[dict]) -> int:
    """Throw the index away and rebuild it from the modules table."""
    with _write_lock:
        col = _collection()
        existing = col.get(include=[])["ids"]
        if existing:
            col.delete(ids=existing)
        for m in modules:
            _add(m)
        return col.count()


def search(question: str, k: int = config.TOP_K) -> list[dict]:
    col = _collection()
    if col.count() == 0:
        return []
    res = col.query(query_texts=[question], n_results=min(k, col.count()))
    return [
        {"title": meta["title"], "text": doc, "distance": dist, "module_id": meta["module_id"]}
        for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0])
        if dist <= config.MAX_DISTANCE
    ]


class AnswerError(Exception):
    pass


def groq_complete(system: str, user: str, max_tokens: int = 2048) -> str:
    if not config.GROQ_API_KEY:
        raise AnswerError("GROQ_API_KEY is not set")

    from groq import Groq  # imported here so the app still starts without the key

    # Fail fast without internet so the offline app can switch to the local model quickly.
    client = Groq(api_key=config.GROQ_API_KEY, timeout=30, max_retries=1)
    resp = client.chat.completions.create(
        model=config.GROQ_MODEL,
        temperature=0.2,
        max_completion_tokens=max_tokens,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    text = (resp.choices[0].message.content or "").strip()
    if not text:
        raise AnswerError("The model returned an empty answer")
    return text


NO_INFO = "I don't have any information on that yet. Please check with the college office."


def answer(question: str, hits: list[dict], personal: str = "") -> str:
    if not hits and not personal:
        return NO_INFO
    return grounded_answer(question, build_context(hits, personal), groq_complete)


# --- Keeping answers to what the context says ----------------------------------------
# Models, the small offline one most of all, sometimes state a date, time, mark or percentage that isn't in the
# context. Every number in an answer must appear in the context or the question; if not, the model gets one more
# try with the invented numbers named, and after that the reply is the context's own most relevant sentences.

_NUMBER = re.compile(r"\d+(?:[.:]\d+)?")
_WORD = re.compile(r"[a-z0-9]+")
_COMMON = {"the", "and", "for", "what", "when", "where", "which", "who", "how", "is", "are", "was", "will", "can",
           "does", "do", "my", "me", "i", "a", "an", "of", "to", "in", "on", "at", "it", "this", "that", "there",
           "tell", "about", "please", "college", "nmamit", "any", "get", "have", "has", "be"}


def _numbers(text: str, answer_side: bool = False) -> set[str]:
    out = set()
    for n in _NUMBER.findall(text):
        if ":" in n:
            hour, minute = n.split(":")
            hour = hour.lstrip("0") or "0"
            if minute == "00":
                out.add(hour)              # "1:00 PM" and "1 PM" are the same time
                if not answer_side:
                    out.add(f"{hour}:00")
            else:
                out.add(f"{hour}:{minute}")
        elif "." in n:
            out.add(n)
        else:
            out.add(n.lstrip("0") or "0")          # "09" December is 9
    return out


def unsupported_numbers(text: str, context: str, question: str = "") -> list[str]:
    """Numbers in an answer that neither the context nor the question contains."""
    have = _numbers(context) | _numbers(question)
    return sorted(n for n in _numbers(text, answer_side=True) if n not in have)


def quote_context(question: str, context: str, limit: int = 2) -> str:
    """The context's sentences that share the most words with the question, word for word."""
    wanted = {w for w in _WORD.findall(question.lower()) if w not in _COMMON and len(w) > 1}
    wanted |= {w for _, c in syllabus.find_courses(question) for w in _WORD.findall(c["title"].lower()) if len(w) > 3}
    sentences = [s.strip() for line in context.splitlines() for s in re.split(r"(?<=[.!?])\s+", line) if s.strip()]
    scored = sorted(((len(wanted & set(_WORD.findall(s.lower()))), -i, s) for i, s in enumerate(sentences)
                     if not s.startswith(("About the person asking", "---"))), reverse=True)
    best = [s for score, _, s in scored[:limit] if score > 0]
    if not best:
        return NO_INFO
    return "Here is what the college information says: " + " ".join(s[:400] for s in best)


# Words that don't name what a question is about, so they can't show that the context covers it.
_NOT_TOPIC = _COMMON | {
    "open", "opens", "opening", "close", "closes", "closing", "timing", "timings", "time", "times", "today",
    "tomorrow", "now", "right", "there", "available", "much", "many", "long", "need", "give", "know", "show",
    "list", "say", "find", "want", "like", "should", "could", "would", "also", "some", "next", "last", "first",
    "best", "good", "still", "yet", "going", "happen", "happening", "held", "start", "starts", "end", "ends",
    "your", "you", "they", "them", "their", "our", "we", "us", "am", "im", "whats", "when's", "hey", "hello", "hi",
    "sir", "madam", "mam", "ok", "okay", "thanks", "thank", "any", "all", "with", "from", "into", "if", "or", "not",
    "did", "does", "doing", "done", "go", "goes", "make", "take", "put", "use", "used", "much", "more", "less",
}
_SAME_TOPIC = {"hod": "head", "fees": "fee", "teachers": "teacher", "classes": "class"}


def on_topic(question: str, context: str) -> bool:
    """False when no word that says what the question is about appears in the context: there is nothing to answer
    from, and a small model would otherwise make the answer up ("When is the library open?" with no library info)."""
    ctx = context.lower()
    words = [w for w in _WORD.findall(question.lower()) if len(w) > 2 and w not in _NOT_TOPIC and not w.isdigit()]
    if not words:
        return True
    words += [w for _, c in syllabus.find_courses(question) for w in _WORD.findall(c["title"].lower())]
    return any(w in ctx or _SAME_TOPIC.get(w, w) in ctx or w.rstrip("s") in ctx for w in words)


SAMPLE_MARK = "sample data made by this app"


def grounded_answer(question: str, context: str, write) -> str:
    """write(system, user) -> text: Groq, or the offline app's Groq-then-local chain."""
    if not on_topic(question, context):
        log.info("Nothing in the context is about this question; not asking the model")
        return NO_INFO
    final = _checked(question, context, write)
    # Sample marks and attendance must be called that, even when the model leaves it out.
    if SAMPLE_MARK in context and "sample" not in final.lower() and final != NO_INFO:
        final += " (These records are sample data made by the app, not official college records.)"
    return final


def _checked(question: str, context: str, write) -> str:
    system = system_prompt(context)
    text = write(system, question)
    bad = unsupported_numbers(text, context, question)
    if not bad:
        return text
    log.warning("Answer had numbers that aren't in the context (%s); asking again", ", ".join(bad))
    retry = write(system + "\n\nYour last answer used numbers that are NOT in the context: " + ", ".join(bad)
                  + ". Answer again using only numbers, dates and times that appear in the context. If the context "
                  "doesn't have the answer, say you don't have that information yet.", question)
    if not unsupported_numbers(retry, context, question):
        return retry
    log.warning("Still not supported by the context; answering with the context's own words")
    return quote_context(question, context)


TIDY_PROMPT = """You clean up information that college staff typed or pasted into the NMAMIT campus assistant, so the assistant can answer students from it.

The input can be messy: shorthand, abbreviations, typos, WhatsApp messages, broken tables, lists in any order, half sentences, mixed Kannada/Hindi/English words.

Rewrite it as clean, complete information:
- One fact per line, each line understandable on its own (repeat the subject, e.g. "The Infosys campus drive is on ...", not "It is on ...").
- Keep EVERY detail: names, dates, days, times, venues, rooms, course codes, numbers, eligibility, links, phone numbers.
- Expand abbreviations when they are clear (FM = Financial Management, MSE = mid-semester exam, SEE = semester end exam, HOD = head of department, CSE/ISE/ECE branches, T&P = training and placement). Keep the short form in brackets the first time.
- Write dates in full, for example "Monday 15 December 2026". Today is {today}; use it to work out a missing year or a weekday.
- Course names and codes in this college's IS syllabus, to expand short forms (e.g. EH&ND, OOMD, SDN, UID, OR, IDS, WSN): {courses}
- Fix spelling, but never change a name, number or code you are unsure about.
- Never add anything that is not in the input. If a part is unclear, keep it as written and add "(unclear in the original)".
- Plain text only. No markdown, no bullets, no tables.

The staff member said this is about: {category}.

Reply in exactly this form:
TITLE: <what exactly this is, at most 8 words, e.g. "MSE 2 timetable, 7th semester ISE" or "Dr. Ravi B, cabin and subjects"; never just the topic>
<the cleaned information, one fact per line>"""


@lru_cache(maxsize=1)
def _course_names() -> str:
    return "; ".join(f"{c['code']} {c['title']}" for _, c in syllabus.listed())


def tidy(raw: str, category: str = "general information") -> dict:
    """Messy staff input -> {"title", "content"} in clear sentences, nothing added. Groq only: in testing the small
    local model looped or dropped facts, while it answers well from the raw text, so offline the admin saves it as is."""
    prompt = TIDY_PROMPT.format(today=f"{date.today():%A %d %B %Y}", category=category, courses=_course_names())
    out = groq_complete(prompt, raw.strip(), max_tokens=6000)
    out = "\n".join(line.strip() for line in out.strip().splitlines())
    first, _, rest = out.partition("\n")
    if first.upper().startswith("TITLE:"):
        title, content = first[6:].strip(" *#\"'"), rest.strip()
    else:
        title, content = "", out
    return {"title": title[:200], "content": content or raw.strip()}
