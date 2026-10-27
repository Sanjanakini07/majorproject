"""Answers from a small AI model running on this laptop through Ollama (https://ollama.com).

If Ollama is not running and GROQ_API_KEY is set, the Groq model is used.
If offline and facts were computed, the exact facts are returned directly.
"""
import logging

import requests

from app import config as app_config
from app import rag

from . import config

log = logging.getLogger(__name__)

NO_INFO = "I don't have any information on that yet. Please check with the college office."


def answer(question: str, hits: list[dict], personal: str = "") -> str:
    if not hits and not personal:
        return NO_INFO
    context = rag.build_context(hits, personal)
    try:
        res = requests.post(
            f"{config.OLLAMA_URL}/api/chat",
            json={
                "model": config.OLLAMA_MODEL,
                "stream": False,
                "options": {"temperature": 0.2},
                "messages": [
                    {"role": "system", "content": rag.system_prompt(context)},
                    {"role": "user", "content": question},
                ],
            },
            timeout=180,
        )
    except requests.ConnectionError:
        if app_config.GROQ_API_KEY:
            log.warning("Ollama is not running; using Groq instead")
            return rag.answer(question, hits, personal)
        if personal:
            log.info("Ollama is not running; answering directly from exact personal facts")
            return personal.strip()
        raise rag.AnswerError("Ollama is not running. Start it from the Start menu (Ollama) or set GROQ_API_KEY in .env.")
    if res.status_code == 404:
        if app_config.GROQ_API_KEY:
            return rag.answer(question, hits, personal)
        if personal:
            return personal.strip()
        raise rag.AnswerError(f"The model {config.OLLAMA_MODEL} is not downloaded. Run: ollama pull {config.OLLAMA_MODEL}")
    res.raise_for_status()
    text = (res.json().get("message") or {}).get("content", "").strip()
    if not text:
        if personal:
            return personal.strip()
        raise rag.AnswerError("The model returned an empty answer")
    return text
