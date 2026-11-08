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


def answer(question: str, hits: list[dict], personal: str = "") -> str:
    if not hits and not personal:
        return "I don't have any information on that yet. Please check with the college office."
    return groq_complete(system_prompt(build_context(hits, personal)), question)


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
