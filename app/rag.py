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
from functools import lru_cache

import chromadb

from . import config

log = logging.getLogger(__name__)

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
- Never invent dates, fees, names or phone numbers."""


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
        {"title": meta["title"], "text": doc, "distance": dist}
        for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0])
        if dist <= config.MAX_DISTANCE
    ]


class AnswerError(Exception):
    pass


def answer(question: str, hits: list[dict]) -> str:
    if not hits:
        return "I don't have any information on that yet. Please check with the college office."
    if not config.GROQ_API_KEY:
        raise AnswerError("GROQ_API_KEY is not set")

    from groq import Groq  # imported here so the app still starts without the key

    context = "\n\n---\n\n".join(h["text"] for h in hits)
    client = Groq(api_key=config.GROQ_API_KEY)
    resp = client.chat.completions.create(
        model=config.GROQ_MODEL,
        temperature=0.2,
        max_completion_tokens=1024,
        messages=[
            {"role": "system", "content": f"{SYSTEM_PROMPT}\n\nContext:\n{context}"},
            {"role": "user", "content": question},
        ],
    )
    text = (resp.choices[0].message.content or "").strip()
    if not text:
        raise AnswerError("The model returned an empty answer")
    return text
