"""Admin API: manage knowledge modules and enrolled faces.

Every change to a module is written to SQLite and then immediately applied to
the vector database, so the very next question uses the new information.
"""
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from . import config, db, face, ingest, rag
from .auth import admin_user

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", dependencies=[Depends(admin_user)])

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_CSV_BYTES = 2 * 1024 * 1024


class ModuleIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=20000)
    source: str = "manual"


async def read_upload(file: UploadFile, limit: int) -> bytes:
    data = await file.read(limit + 1)
    if not data:
        raise HTTPException(400, "The file is empty.")
    if len(data) > limit:
        raise HTTPException(413, f"The file is too big. The limit is {limit // (1024 * 1024)} MB.")
    return data


def _clean(body: ModuleIn) -> tuple[str, str]:
    title, content = body.title.strip(), body.content.strip()
    if not title or not content:
        raise HTTPException(422, "Title and content can't be blank.")
    return title, content


# --- Knowledge modules ------------------------------------------------------------

@router.get("/modules")
def list_modules():
    return db.list_modules()


@router.post("/modules", status_code=201)
def create_module(body: ModuleIn, user: dict = Depends(admin_user)):
    title, content = _clean(body)
    source = body.source if body.source in ("manual", "image") else "manual"
    module = db.create_module(title, content, source, user["email"])
    rag.index_module(module)
    return module


@router.put("/modules/{module_id}")
def update_module(module_id: int, body: ModuleIn, user: dict = Depends(admin_user)):
    title, content = _clean(body)
    module = db.update_module(module_id, title, content, user["email"])
    if not module:
        raise HTTPException(404, "Module not found.")
    rag.index_module(module)
    return module


@router.delete("/modules/{module_id}", status_code=204)
def delete_module(module_id: int):
    if not db.delete_module(module_id):
        raise HTTPException(404, "Module not found.")
    rag.remove_module(module_id)


@router.post("/modules/import-csv", status_code=201)
async def import_csv(file: UploadFile = File(...), user: dict = Depends(admin_user)):
    data = await read_upload(file, MAX_CSV_BYTES)
    try:
        rows = ingest.parse_csv(data, file.filename or "upload.csv")
    except ingest.IngestError as e:
        raise HTTPException(400, str(e))
    for row in rows:
        rag.index_module(db.create_module(row["title"], row["content"], "csv", user["email"]))
    return {"added": len(rows)}


@router.post("/extract-text")
async def extract_text(file: UploadFile = File(...)):
    """Read the text in an image. Nothing is saved: the admin checks it first."""
    data = await read_upload(file, MAX_IMAGE_BYTES)
    try:
        text = ingest.image_to_text(data)
    except ingest.IngestError as e:
        raise HTTPException(400, str(e))
    return {"text": text}


@router.post("/reindex")
def reindex():
    count = rag.rebuild(db.list_modules())
    return {"chunks": count}


# --- Faces ------------------------------------------------------------------

@router.get("/faces")
def list_faces():
    return db.list_faces()


@router.post("/faces", status_code=201)
async def enroll_face(
    email: str = Form(...), file: UploadFile = File(...), user: dict = Depends(admin_user)
):
    email = email.strip().lower()
    if not email.endswith("@" + config.ALLOWED_DOMAIN) or email.count("@") != 1:
        raise HTTPException(400, f"Use the student's @{config.ALLOWED_DOMAIN} email address.")
    data = await read_upload(file, MAX_IMAGE_BYTES)
    try:
        vec = face.embedding(data)
    except face.FaceError as e:
        raise HTTPException(400, str(e))
    db.save_face(email, face.to_bytes(vec), user["email"])
    return {"email": email}


@router.delete("/faces/{email}", status_code=204)
def remove_face(email: str):
    if not db.delete_face(email.strip().lower()):
        raise HTTPException(404, "No face registered for that email.")
