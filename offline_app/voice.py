"""Speech to text (faster-whisper) and text to speech (Piper), both running on this laptop.

The models are downloaded once by `python -m offline_app.setup` into ./models.
"""
import io
import threading
import urllib.request
import wave
from functools import lru_cache

from . import config

PIPER_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium"

_stt_lock = threading.Lock()
_tts_lock = threading.Lock()


class VoiceError(Exception):
    pass


def download_models() -> None:
    from faster_whisper import download_model

    if not config.WHISPER_DIR.exists():
        download_model(config.WHISPER_MODEL, output_dir=str(config.WHISPER_DIR))
    config.PIPER_PATH.parent.mkdir(parents=True, exist_ok=True)
    for path in (config.PIPER_PATH, config.PIPER_PATH.with_suffix(".onnx.json")):
        if not path.exists():
            tmp = path.with_suffix(".part")
            urllib.request.urlretrieve(f"{PIPER_BASE}/{path.name}", tmp)
            tmp.replace(path)


@lru_cache(maxsize=1)
def _whisper():
    from faster_whisper import WhisperModel

    if not config.WHISPER_DIR.exists():
        raise VoiceError("The speech model is not downloaded. Run start_offline.bat once with internet.")
    return WhisperModel(str(config.WHISPER_DIR), device="cpu", compute_type="int8")


@lru_cache(maxsize=1)
def _piper():
    from piper import PiperVoice

    if not config.PIPER_PATH.exists():
        raise VoiceError("The voice model is not downloaded. Run start_offline.bat once with internet.")
    return PiperVoice.load(str(config.PIPER_PATH))


def transcribe(audio: bytes) -> str:
    """Turn a recording from the browser (webm, ogg, mp4 or wav) into text."""
    import av

    with _stt_lock:
        try:
            segments, _ = _whisper().transcribe(io.BytesIO(audio), language="en", beam_size=1, vad_filter=True)
            return " ".join(s.text.strip() for s in segments).strip()
        except av.FFmpegError as e:  # the upload is not audio
            raise VoiceError("That recording could not be read. Please try again.") from e


def speak(text: str) -> bytes:
    """Return the text read aloud as a WAV file."""
    buf = io.BytesIO()
    with _tts_lock, wave.open(buf, "wb") as wav:
        _piper().synthesize_wav(text, wav)
    return buf.getvalue()
