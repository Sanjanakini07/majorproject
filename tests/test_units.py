import os
from pathlib import Path

import numpy as np
import pytest

from app import config, face, ingest
from app.rag import chunk_text


def test_chunk_text_short_text_is_one_chunk():
    assert chunk_text("hello") == ["hello"]
    assert chunk_text("   ") == []


def test_chunk_text_long_text_overlaps_and_covers_everything():
    text = " ".join(f"Sentence number {i}." for i in range(300))
    chunks = chunk_text(text, size=200, overlap=40)
    assert len(chunks) > 1
    assert all(len(c) <= 200 for c in chunks)
    assert chunks[0].startswith("Sentence number 0.")
    assert chunks[-1].endswith("Sentence number 299.")


def test_parse_csv_title_content_columns():
    rows = ingest.parse_csv(b"Title,Content\nA,first\n,skipped\nB,second\n", "x.csv")
    assert rows == [{"title": "A", "content": "first"}, {"title": "B", "content": "second"}]


def test_parse_csv_any_columns():
    rows = ingest.parse_csv("Day,Room\nMonday,LH-1\n".encode("utf-8-sig"), "timetable.csv")
    assert rows == [{"title": "timetable - row 1", "content": "Day: Monday. Room: LH-1"}]


def test_parse_csv_errors():
    with pytest.raises(ingest.IngestError):
        ingest.parse_csv(b"", "x.csv")
    with pytest.raises(ingest.IngestError):
        ingest.parse_csv("title,content\n\xe9,x\n".encode("latin-1"), "x.csv")
    with pytest.raises(ingest.IngestError):
        ingest.parse_csv(b"title,content\n,\n", "x.csv")


def test_face_similarity_math():
    a = np.array([1, 0, 0], dtype=np.float32)
    assert face.similarity(a, a) == pytest.approx(1.0)
    assert face.similarity(a, np.array([0, 1, 0], dtype=np.float32)) == pytest.approx(0.0)
    assert np.array_equal(face.from_bytes(face.to_bytes(a)), a)


def test_bad_image_is_a_friendly_error():
    with pytest.raises(face.FaceError):
        face._decode(b"not an image")


# The tests below need the OpenCV models (python scripts/setup_models.py).
models_ready = all((config.MODELS_DIR / name).exists() for name in face.MODELS)
needs_models = pytest.mark.skipif(not models_ready, reason="face models not downloaded")


@needs_models
def test_blank_image_has_no_face():
    import cv2

    ok, buf = cv2.imencode(".jpg", np.full((480, 640, 3), 200, np.uint8))
    with pytest.raises(face.FaceError, match="No face"):
        face.embedding(buf.tobytes())


@needs_models
@pytest.mark.skipif(not os.getenv("FACE_TEST_A") or not os.getenv("FACE_TEST_B"),
                    reason="set FACE_TEST_A and FACE_TEST_B to photos of two different people")
def test_same_person_matches_and_different_person_does_not():
    import cv2

    a_bytes = Path(os.environ["FACE_TEST_A"]).read_bytes()
    b_bytes = Path(os.environ["FACE_TEST_B"]).read_bytes()
    img = cv2.imdecode(np.frombuffer(a_bytes, np.uint8), cv2.IMREAD_COLOR)
    _, flipped = cv2.imencode(".jpg", cv2.flip(img, 1))  # same person, different picture

    a, a2, b = face.embedding(a_bytes), face.embedding(flipped.tobytes()), face.embedding(b_bytes)
    assert face.is_match(a, a2)[0]
    assert not face.is_match(a, b)[0]
