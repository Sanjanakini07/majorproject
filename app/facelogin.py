"""Enrolling a face and checking it at every sign-in. Shared by the online and offline apps.

Enrolment (first sign-in): the page takes several photos while the person turns
their head a little, and one signature per photo is stored.
Sign-in (every time): the page takes a few fresh photos and they are compared
with the enrolled signatures. Nothing is trusted from an earlier session.
"""
import logging

import numpy as np
from fastapi import HTTPException, UploadFile

from . import config, db, face
from .auth import face_lockout

log = logging.getLogger(__name__)

ENROLL_PHOTOS = db.MIN_TEMPLATES + 1   # the page takes six; the server accepts five or more
MAX_PHOTOS = 8
ENROLL_CONSISTENCY = 0.30              # every enrolment photo must resemble the average of all of them
MAX_IMAGE_BYTES = 5 * 1024 * 1024


async def read_images(files: list[UploadFile]) -> list[bytes]:
    if not files:
        raise HTTPException(400, "No photos were sent.")
    if len(files) > MAX_PHOTOS:
        raise HTTPException(400, f"Send at most {MAX_PHOTOS} photos.")
    images = []
    for f in files:
        data = await f.read(MAX_IMAGE_BYTES + 1)
        if not data or len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(400, "A photo was empty or too big.")
        images.append(data)
    return images


def check_not_locked(email: str) -> None:
    wait = face_lockout.seconds_left(email)
    if wait:
        raise HTTPException(429, f"Too many failed tries. Try again in {wait // 60 + 1} minutes.")


def enroll(email: str, images: list[bytes], by: str) -> None:
    """Store a signature for each photo. Raises HTTPException with a message the person can act on."""
    if len(images) < db.MIN_TEMPLATES:
        raise HTTPException(400, f"Take at least {db.MIN_TEMPLATES} photos.")
    vectors = []
    for i, data in enumerate(images, 1):
        try:
            vectors.append(face.embedding(data))
        except face.FaceError as e:
            raise HTTPException(400, f"Photo {i}: {e}")
    unit = np.array([v / np.linalg.norm(v) for v in vectors])
    centre = unit.mean(axis=0)
    if min(face.similarity(v, centre) for v in unit) < ENROLL_CONSISTENCY:
        raise HTTPException(400, "The photos don't all show the same person. Start again with only you in view.")
    db.save_face(email, b"".join(face.to_bytes(v) for v in vectors), by)
    log.info("Enrolled %d face photos for %s", len(vectors), email)


def verify(email: str, images: list[bytes]) -> None:
    """Pass if most of the fresh photos match an enrolled one. Raises HTTPException otherwise."""
    check_not_locked(email)
    stored = db.get_face(email)
    if stored is None:
        raise HTTPException(404, "Your face is not enrolled yet.")
    enrolled = face.templates(stored)

    scores, problem = [], None
    for data in images:
        try:
            scores.append(face.best_score(face.embedding(data), enrolled))
        except face.FaceError as e:
            problem = e
    if not scores:
        # A blurry or empty frame is not counted as a failed try.
        raise HTTPException(400, str(problem))

    matches = sum(s >= config.FACE_MATCH_THRESHOLD for s in scores)
    ok = matches * 2 > len(scores)
    log.info("Face check for %s: scores=%s match=%s", email, [round(s, 3) for s in scores], ok)
    if not ok:
        face_lockout.fail(email)
        left = face_lockout.tries_left(email)
        raise HTTPException(403, f"Face did not match. {left} {'try' if left == 1 else 'tries'} left.")
    face_lockout.reset(email)
