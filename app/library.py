"""Notes library and events.

Everyone signed in can read. Admins, and teachers an admin gave the "content"
permission, can add and delete. A note is a PDF or pasted text; an event can
carry a PDF too. The text of each one (pasted, or read out of the PDF) is also
saved as a knowledge entry, so the voice assistant can answer from it.
"""
import io
import logging
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from pypdf import PdfReader
from starlette.concurrency import run_in_threadpool

from . import db, rag, syllabus
from .auth import require, verified_user
from .portal import gated_page

router = APIRouter()

MAX_PDF_BYTES = 15 * 1024 * 1024
MAX_TEXT_CHARS = 100_000
MAX_PDF_TEXT_CHARS = 150_000

def seed_subjects() -> None:
    """Every course of the official IS curriculum (2023-04 regulations), under its semester."""
    db.add_subjects(syllabus.note_subjects())


def gated(request: Request, name: str):
    return gated_page(request, name)


@router.get("/notes", include_in_schema=False)
def notes_page(request: Request):
    return gated(request, "notes.html")


@router.get("/events", include_in_schema=False)
def events_page(request: Request):
    return gated(request, "events.html")


# --- Helpers ------------------------------------------------------------------------

async def read_pdf(file: UploadFile | None) -> tuple[str, bytes] | None:
    """The uploaded PDF's name and bytes, or None if nothing was chosen."""
    if file is None or not file.filename:
        return None
    data = await file.read(MAX_PDF_BYTES + 1)
    if not data:
        raise HTTPException(400, "The file is empty.")
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(413, f"The file is too big. The limit is {MAX_PDF_BYTES // (1024 * 1024)} MB.")
    if not data.startswith(b"%PDF-"):
        raise HTTPException(400, "Only PDF files can be uploaded. To add other notes, paste the text instead.")
    return file.filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1][:150], data


def pdf_text(data: bytes) -> str:
    """The text in a PDF. Empty for scanned pages that are only pictures."""
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise HTTPException(400, "This PDF is password protected. Remove the password and upload it again.")
        parts, size = [], 0
        for page in reader.pages:
            text = (page.extract_text() or "").strip()
            parts.append(text)
            size += len(text)
            if size > MAX_PDF_TEXT_CHARS:
                break
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "That PDF could not be read. It may be damaged.")
    return "\n\n".join(p for p in parts if p)[:MAX_PDF_TEXT_CHARS]


def _index(table: str, row_id: int, title: str, text: str, user: str) -> None:
    """Make the text searchable by the assistant."""
    if not text.strip():
        return
    module = db.create_module(title, text.strip(), table[:-1], user)   # source: "note" or "event"
    rag.index_module(module)
    db.set_module(table, row_id, module["id"])


def _unindex(module_id: int | None) -> None:
    if module_id and db.delete_module(module_id):
        rag.remove_module(module_id)


def pretty_date(event_date: str, start_time: str) -> str:
    try:
        text = datetime.strptime(event_date, "%Y-%m-%d").strftime("%A %d %B %Y")
    except ValueError:
        return event_date
    if start_time:
        try:
            text += ", " + datetime.strptime(start_time, "%H:%M").strftime("%I:%M %p").lstrip("0")
        except ValueError:
            pass
    return text


def _file_response(row: dict | None, download: bool) -> Response:
    if not row or not row["data"]:
        raise HTTPException(404, "There is no file here.")
    disposition = "attachment" if download else "inline"
    return Response(
        row["data"], media_type="application/pdf",
        headers={
            "Content-Disposition": f'{disposition}; filename="{(row["filename"] or "file.pdf").replace(chr(34), "")}"',
            "Cache-Control": "private, no-store",
            "Content-Security-Policy": "sandbox",   # a PDF can't run anything on this site
        },
    )


# --- Notes --------------------------------------------------------------------------

@router.get("/api/subjects")
def subjects(user: dict = Depends(verified_user)):
    return db.list_subjects()


@router.get("/api/notes")
def notes(subject: str, user: dict = Depends(verified_user)):
    if not db.get_subject(subject):
        raise HTTPException(404, "That subject was not found.")
    return db.list_notes(subject)


@router.get("/api/notes/{note_id}/file")
def note_file(note_id: int, download: bool = False, user: dict = Depends(verified_user)):
    return _file_response(db.get_note(note_id), download)


@router.post("/api/notes", status_code=201)
async def add_note(
    subject: str = Form(...), title: str = Form(..., max_length=200), text: str = Form("", max_length=MAX_TEXT_CHARS),
    file: UploadFile | None = File(None), user: dict = Depends(require("content")),
):
    sub = db.get_subject(subject)
    if not sub:
        raise HTTPException(404, "That subject was not found.")
    title, text = title.strip(), text.strip()
    pdf = await read_pdf(file)
    if not title:
        raise HTTPException(422, "Give the notes a title.")
    if not pdf and not text:
        raise HTTPException(422, "Upload a PDF or paste some text.")
    if pdf:
        filename, data = pdf
        content = await run_in_threadpool(pdf_text, data)
        note_id = db.add_note(subject, title, "pdf", content, filename, data, user["email"])
    else:
        content = text
        note_id = db.add_note(subject, title, "text", text, None, None, user["email"])
    label = f"Notes: Semester {sub['semester']}, {sub['name']}, {title}"
    await run_in_threadpool(_index, "notes", note_id, label, content, user["email"])
    return {"id": note_id, "readable": bool(content.strip())}


@router.delete("/api/notes/{note_id}", status_code=204, dependencies=[Depends(require("content"))])
def delete_note(note_id: int):
    note = db.get_note(note_id)
    if not note or not db.delete_note(note_id):
        raise HTTPException(404, "Those notes were not found.")
    _unindex(note["module_id"])


# --- Events -------------------------------------------------------------------------

@router.get("/api/events")
def events(user: dict = Depends(verified_user)):
    return db.list_events()


@router.get("/api/events/{event_id}/file")
def event_file(event_id: int, download: bool = False, user: dict = Depends(verified_user)):
    return _file_response(db.get_event(event_id), download)


@router.post("/api/events", status_code=201)
async def add_event(
    title: str = Form(..., max_length=200), event_date: str = Form(...), start_time: str = Form("", max_length=5),
    venue: str = Form("", max_length=200), description: str = Form("", max_length=MAX_TEXT_CHARS),
    file: UploadFile | None = File(None), user: dict = Depends(require("content")),
):
    title, venue, description = title.strip(), venue.strip(), description.strip()
    if not title:
        raise HTTPException(422, "Give the event a title.")
    try:
        date.fromisoformat(event_date)
    except ValueError:
        raise HTTPException(422, "Choose the event date.")
    if start_time:
        try:
            datetime.strptime(start_time, "%H:%M")
        except ValueError:
            raise HTTPException(422, "The time must look like 14:30.")
    pdf = await read_pdf(file)
    filename, data = pdf if pdf else (None, None)
    pdf_body = await run_in_threadpool(pdf_text, data) if data else ""
    event_id = db.add_event(title, event_date, start_time, venue, description, filename, data, user["email"])

    text = f"Event: {title}. Date: {pretty_date(event_date, start_time)}."
    if venue:
        text += f" Venue: {venue}."
    if description:
        text += f" Details: {description}"
    if pdf_body:
        text += f"\n{pdf_body}"
    await run_in_threadpool(_index, "events", event_id, f"Event: {title}", text, user["email"])
    return {"id": event_id}


@router.delete("/api/events/{event_id}", status_code=204, dependencies=[Depends(require("content"))])
def delete_event(event_id: int):
    event = db.get_event(event_id)
    if not event or not db.delete_event(event_id):
        raise HTTPException(404, "That event was not found.")
    _unindex(event["module_id"])


# --- Links shown under the assistant's answers -----------------------------------------

def links_for(module_ids: list) -> list[dict]:
    """Where to read the notes and events an answer came from."""
    found = db.links_for_modules([m for m in dict.fromkeys(module_ids) if m is not None])
    out = []
    for item in found:
        if item["kind"] == "event":
            out.append({"title": item["title"], "label": "Event", "url": "/events"})
        elif item["kind"] == "note" and item["semester"]:
            out.append({"title": item["title"], "label": "Notes", "url": f"/notes?sem={item['semester']}&subject={item['code']}"})
    return out[:4]
