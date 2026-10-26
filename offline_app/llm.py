"""Answers from a small AI model running on this laptop through Ollama (https://ollama.com).

If Ollama is not running and GROQ_API_KEY is set, the online Groq model is used instead.
"""
import logging

import requests

from app import config as app_config
from app import rag

from . import config

log = logging.getLogger(__name__)

NO_INFO = "I don't have any information on that yet. Please check with the college office."


def answer(question: str, hits: list[dict]) -> str:
    if not hits:
        return NO_INFO
    context = "\n\n---\n\n".join(h["text"] for h in hits)
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
        if not app_config.GROQ_API_KEY:
            raise rag.AnswerError("Ollama is not running. Start it from the Start menu (Ollama).")
        log.warning("Ollama is not running; using Groq instead")
        return rag.answer(question, hits)
    if res.status_code == 404:
        raise rag.AnswerError(f"The model {config.OLLAMA_MODEL} is not downloaded. Run: ollama pull {config.OLLAMA_MODEL}")
    res.raise_for_status()
    text = (res.json().get("message") or {}).get("content", "").strip()
    if not text:
        raise rag.AnswerError("The model returned an empty answer")
    return text
