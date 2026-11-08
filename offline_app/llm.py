"""Who writes the text: Groq when there is internet, else the small local model (Ollama), else the exact facts.

1. Groq (GROQ_API_KEY set): best answers. If it fails (no internet, Groq down, rate limit), the laptop skips
   Groq for OFFLINE_RETRY_SECONDS so offline answers aren't slowed down by a failing call every time.
2. Ollama (https://ollama.com) running on this laptop.
3. The exact facts worked out by app/personal.py, read out as they are.
"""
import logging
import time

import requests

from app import config as app_config
from app import rag

from . import config

log = logging.getLogger(__name__)

NO_INFO = "I don't have any information on that yet. Please check with the college office."
OFFLINE_RETRY_SECONDS = 60
_skip_groq_until = 0.0
last_engine = ""  # who wrote the last text, for scripts/test_llm.py and the logs


def complete(system: str, user: str, max_tokens: int = 2048) -> str:
    global _skip_groq_until, last_engine
    if app_config.GROQ_API_KEY and time.monotonic() >= _skip_groq_until:
        try:
            text = rag.groq_complete(system, user, max_tokens)
            log.info("Written by Groq (%s)", app_config.GROQ_MODEL)
            last_engine = "groq"
            return text
        except Exception as e:  # no internet, timeout, rate limit, bad key: the local model takes over
            log.warning("Groq is not reachable (%s); using the local model for the next %ss",
                        type(e).__name__, OFFLINE_RETRY_SECONDS)
            _skip_groq_until = time.monotonic() + OFFLINE_RETRY_SECONDS
    text = _local(system, user, max_tokens)
    last_engine = "local"
    return text


def _local(system: str, user: str, max_tokens: int) -> str:
    try:
        res = requests.post(
            f"{config.OLLAMA_URL}/api/chat",
            json={
                "model": config.OLLAMA_MODEL,
                "stream": False,
                # Ollama's default 2048-token window cuts off the start of a long prompt, which is the rules.
                "options": {"temperature": 0.2, "num_ctx": 8192, "num_predict": max_tokens},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            },
            timeout=180,
        )
    except requests.ConnectionError:
        raise rag.AnswerError("No internet, and the local AI (Ollama) is not running. Start Ollama from the Start menu.")
    if res.status_code == 404:
        raise rag.AnswerError(f"The model {config.OLLAMA_MODEL} is not downloaded. Run: ollama pull {config.OLLAMA_MODEL}")
    res.raise_for_status()
    text = (res.json().get("message") or {}).get("content", "").strip()
    if not text:
        raise rag.AnswerError("The model returned an empty answer")
    log.info("Written by the local model (%s)", config.OLLAMA_MODEL)
    return text


def answer(question: str, hits: list[dict], personal: str = "") -> str:
    global last_engine
    if not hits and not personal:
        return NO_INFO
    try:
        return complete(rag.system_prompt(rag.build_context(hits, personal)), question)
    except rag.AnswerError:
        if personal:  # no model at all: the exact facts still answer "my attendance", "events today"...
            log.info("No model available; answering directly from the exact facts")
            last_engine = "facts"
            return personal.strip()
        raise
