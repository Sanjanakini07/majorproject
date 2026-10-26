"""Admin API: knowledge modules, staff and their permissions, enrolled faces.

Anyone on staff can read the knowledge entries, but only an admin, or a teacher
an admin has given the "content" permission, can change them. Managing staff
and faces is for admins only.

Every change to a module is written to SQLite and then immediately applied to
the vector database, so the very next question uses the new information.
"""
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from . import config, db, ingest, rag
from .auth import PERMISSIONS, admin_user, require, staff_user

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin")

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

@router.get("/modules", dependencies=[Depends(staff_user)])
def list_modules():
    return db.list_modules()


@router.post("/modules", status_code=201)
def create_module(body: ModuleIn, user: dict = Depends(require("content"))):
    title, content = _clean(body)
    source = body.source if body.source in ("manual", "image") else "manual"
    module = db.create_module(title, content, source, user["email"])
    rag.index_module(module)
    return module


@router.put("/modules/{module_id}")
def update_module(module_id: int, body: ModuleIn, user: dict = Depends(require("content"))):
    title, content = _clean(body)
    module = db.update_module(module_id, title, content, user["email"])
    if not module:
        raise HTTPException(404, "Module not found.")
    rag.index_module(module)
    return module


@router.delete("/modules/{module_id}", status_code=204, dependencies=[Depends(require("content"))])
def delete_module(module_id: int):
    if not db.delete_module(module_id):
        raise HTTPException(404, "Module not found.")
    rag.remove_module(module_id)


@router.post("/modules/import-csv", status_code=201)
async def import_csv(file: UploadFile = File(...), user: dict = Depends(require("content"))):
    data = await read_upload(file, MAX_CSV_BYTES)
    try:
        rows = ingest.parse_csv(data, file.filename or "upload.csv")
    except ingest.IngestError as e:
        raise HTTPException(400, str(e))
    for row in rows:
        rag.index_module(db.create_module(row["title"], row["content"], "csv", user["email"]))
    return {"added": len(rows)}


@router.post("/extract-text", dependencies=[Depends(require("content"))])
async def extract_text(file: UploadFile = File(...)):
    """Read the text in an image. Nothing is saved: the admin checks it first."""
    data = await read_upload(file, MAX_IMAGE_BYTES)
    try:
        text = ingest.image_to_text(data)
    except ingest.IngestError as e:
        raise HTTPException(400, str(e))
    return {"text": text}


@router.post("/reindex", dependencies=[Depends(require("content"))])
def reindex():
    count = rag.rebuild(db.list_modules())
    return {"chunks": count}


# --- Staff ------------------------------------------------------------------

class StaffIn(BaseModel):
    email: str
    name: str | None = Field(default=None, max_length=100)
    role: str = "teacher"
    content: bool = False
    attendance: bool = False
    marks: bool = False


def _staff_email(email: str) -> str:
    email = email.strip().lower()
    if email.count("@") != 1 or not email.endswith("@" + config.ALLOWED_DOMAIN):
        raise HTTPException(400, f"Use an @{config.ALLOWED_DOMAIN} email address.")
    return email


@router.get("/staff", dependencies=[Depends(admin_user)])
def list_staff():
    fixed = [
        {"email": e, "name": None, "role": "admin", "fixed": True,
         **{f"can_{p}": 1 for p in PERMISSIONS}}
        for e in sorted(config.ADMIN_EMAILS)
    ]
    saved = [{**r, "fixed": False} for r in db.list_roles() if r["email"] not in config.ADMIN_EMAILS]
    return fixed + saved


@router.post("/staff", status_code=201)
def save_staff(body: StaffIn, user: dict = Depends(admin_user)):
    email = _staff_email(body.email)
    if body.role not in ("teacher", "admin"):
        raise HTTPException(422, "Role must be teacher or admin.")
    if email in config.ADMIN_EMAILS:
        raise HTTPException(409, "This admin is set in the server settings and can't be changed here.")
    if email == user["email"] and body.role != "admin":
        raise HTTPException(409, "You can't take away your own admin access.")
    perms = {p: getattr(body, p) for p in PERMISSIONS}
    return db.save_role(email, (body.name or "").strip() or None, body.role, perms, user["email"])


@router.delete("/staff/{email}", status_code=204)
def remove_staff(email: str, user: dict = Depends(admin_user)):
    email = email.strip().lower()
    if email in config.ADMIN_EMAILS or email == user["email"]:
        raise HTTPException(409, "This account can't be removed here.")
    if not db.delete_role(email):
        raise HTTPException(404, "That person is not on the staff list.")


# --- Faces ------------------------------------------------------------------

@router.get("/faces", dependencies=[Depends(admin_user)])
def list_faces():
    return db.list_faces()


@router.delete("/faces/{email}", status_code=204, dependencies=[Depends(admin_user)])
def reset_face(email: str):
    """Forget someone's face so they enrol again at their next sign-in (new look, new phone, lost access)."""
    if not db.delete_face(email.strip().lower()):
        raise HTTPException(404, "No face is enrolled for that email.")
