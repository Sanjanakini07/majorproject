"""Pages and APIs both apps share: who am I, marks, attendance, and the admin page.

Students see only their own marks and attendance. Teachers can see every
student's, and change them only if an admin switched that permission on.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field

from . import academics, config, db
from .auth import permissions_of, require, role_of, signed_in_user, staff_user, verified_user

router = APIRouter()
PAGES = config.BASE_DIR / "app" / "pages"


def page(name: str) -> FileResponse:
    return FileResponse(PAGES / name, headers={"Cache-Control": "no-store"})


def gated_page(request: Request, name: str, staff_only: bool = False):
    session = request.session
    if not session.get("email") or not session.get("face_ok"):
        return RedirectResponse("/")
    if staff_only and role_of(session["email"]) == "student":
        return RedirectResponse("/")
    return page(name)


@router.get("/marks", include_in_schema=False)
def marks_page(request: Request):
    return gated_page(request, "marks.html")


@router.get("/attendance", include_in_schema=False)
def attendance_page(request: Request):
    return gated_page(request, "attendance.html")


@router.get("/admin", include_in_schema=False)
def admin_page(request: Request):
    return gated_page(request, "admin.html", staff_only=True)


@router.get("/api/me")
def me(user: dict = Depends(signed_in_user)):
    email = user["email"]
    role = role_of(email)
    return {
        "email": email,
        "name": user["name"],
        "role": role,
        "permissions": permissions_of(email),
        "is_admin": role == "admin",
        "face_ok": bool(user.get("face_ok")),
        "face_enrolled": db.get_face(email) is not None,
        "entries": db.count_modules(),
    }


# --- Students -----------------------------------------------------------------

def _target(user: dict, email: str | None) -> str:
    """Whose records to show: students only ever see their own."""
    own = user["email"]
    if not email or email.strip().lower() == own:
        return own
    if role_of(own) == "student":
        raise HTTPException(403, "You can only see your own records.")
    return email.strip().lower()


def _student(email: str) -> dict | None:
    profile = db.get_profile(email)
    return {k: profile[k] for k in ("email", "name", "branch", "semester")} if profile else None


@router.get("/api/students")
def students(q: str = "", user: dict = Depends(staff_user)):
    return db.list_profiles(q)


@router.get("/api/marks")
def marks(email: str | None = None, user: dict = Depends(verified_user)):
    target = _target(user, email)
    return {"student": _student(target), **academics.marks_report(target)}


@router.get("/api/attendance")
def attendance(email: str | None = None, user: dict = Depends(verified_user)):
    target = _target(user, email)
    return {"student": _student(target), **academics.attendance_report(target)}


class MarkIn(BaseModel):
    email: str
    semester: int = Field(ge=1, le=8)
    code: str = Field(min_length=1, max_length=20)
    internal: int = Field(ge=0, le=academics.MAX_INTERNAL)
    external: int = Field(ge=0, le=academics.MAX_EXTERNAL)


@router.put("/api/marks")
def update_marks(body: MarkIn, user: dict = Depends(require("marks"))):
    if not db.update_mark(body.email.strip().lower(), body.semester, body.code, body.internal, body.external, user["email"]):
        raise HTTPException(404, "That student or subject was not found.")
    return {"ok": True}


class AttendanceIn(BaseModel):
    email: str
    semester: int = Field(ge=1, le=8)
    code: str = Field(min_length=1, max_length=20)
    attended: int = Field(ge=0, le=500)
    total: int = Field(ge=0, le=500)


@router.put("/api/attendance")
def update_attendance(body: AttendanceIn, user: dict = Depends(require("attendance"))):
    if body.attended > body.total:
        raise HTTPException(422, "Classes attended can't be more than classes held.")
    if not db.update_attendance(body.email.strip().lower(), body.semester, body.code, body.attended, body.total, user["email"]):
        raise HTTPException(404, "That student or subject was not found.")
    return {"ok": True}
