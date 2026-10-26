"""Face check with OpenCV, like Face ID: several photos at enrolment, a fresh look at every sign-in.

Two small pretrained models from the OpenCV model zoo do all the work:
  * YuNet finds the face in a photo.
  * SFace turns that face into 128 numbers (an "embedding").
Two photos of the same person give embeddings that point in nearly the same
direction, so we compare them with cosine similarity; nothing has to be trained.
At enrolment we keep one embedding for each of several photos (different head
positions) and a sign-in matches if it is close to any of them. Photos are never
stored, only these numbers.
"""
import logging
import os
import threading
import urllib.request
from functools import lru_cache

# Hide OpenCV's harmless start-up warnings; real errors are still shown.
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

import cv2  # noqa: E402
import numpy as np

from . import config

log = logging.getLogger(__name__)

_ZOO = "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models"
MODELS = {
    "face_detection_yunet_2023mar.onnx": f"{_ZOO}/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "face_recognition_sface_2021dec.onnx": f"{_ZOO}/face_recognition_sface/face_recognition_sface_2021dec.onnx",
}

MAX_SIDE = 1280      # shrink big photos before detection
MIN_FACE_PX = 60     # faces smaller than this are too far away to trust

# OpenCV model objects are not safe to share between threads.
_lock = threading.Lock()


class FaceError(Exception):
    """A problem with the photo that the user can fix (no face, two faces, ...)."""


def ensure_models() -> None:
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    for name, url in MODELS.items():
        path = config.MODELS_DIR / name
        if path.exists() and path.stat().st_size > 0:
            continue
        log.info("Downloading %s ...", name)
        tmp = path.with_suffix(".part")
        urllib.request.urlretrieve(url, tmp)
        tmp.rename(path)


@lru_cache(maxsize=1)
def _models():
    ensure_models()
    detector = cv2.FaceDetectorYN.create(
        str(config.MODELS_DIR / "face_detection_yunet_2023mar.onnx"), "", (320, 320), 0.8
    )
    recognizer = cv2.FaceRecognizerSF.create(
        str(config.MODELS_DIR / "face_recognition_sface_2021dec.onnx"), ""
    )
    return detector, recognizer


def _decode(data: bytes) -> np.ndarray:
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise FaceError("That file is not an image we can read. Use a JPG or PNG photo.")
    h, w = img.shape[:2]
    scale = MAX_SIDE / max(h, w)
    if scale < 1:
        img = cv2.resize(img, (int(w * scale), int(h * scale)))
    return img


def embedding(image_bytes: bytes) -> np.ndarray:
    """Find exactly one face in the photo and return its 128-number embedding."""
    img = _decode(image_bytes)
    detector, recognizer = _models()
    with _lock:
        detector.setInputSize((img.shape[1], img.shape[0]))
        _, faces = detector.detect(img)
        if faces is None or len(faces) == 0:
            raise FaceError("No face found. Look at the camera in good light.")
        if len(faces) > 1:
            raise FaceError("More than one face found. Only one person should be in the photo.")
        face = faces[0]
        if min(face[2], face[3]) < MIN_FACE_PX:
            raise FaceError("Your face is too small in the picture. Move closer to the camera.")
        aligned = recognizer.alignCrop(img, face)
        feature = recognizer.feature(aligned)
    return feature.flatten().astype(np.float32)


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity: 1.0 means identical direction, around 0 means unrelated."""
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def is_match(a: np.ndarray, b: np.ndarray) -> tuple[bool, float]:
    score = similarity(a, b)
    return score >= config.FACE_MATCH_THRESHOLD, score


def to_bytes(vec: np.ndarray) -> bytes:
    return vec.astype(np.float32).tobytes()


def from_bytes(data: bytes) -> np.ndarray:
    return np.frombuffer(data, dtype=np.float32)


def templates(data: bytes) -> np.ndarray:
    """All enrolled signatures of one person as rows of a matrix."""
    return from_bytes(data).reshape(-1, 128)


def best_score(live: np.ndarray, enrolled: np.ndarray) -> float:
    """Similarity to the closest enrolled photo."""
    return max(similarity(live, row) for row in enrolled)
