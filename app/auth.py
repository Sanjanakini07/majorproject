"""Who is allowed in: Google sign-in, then the face check, then (for admins) the admin list."""
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from . import config

_google = google_requests.Request()


def verify_firebase_token(token: str) -> dict:
    """Check a Firebase sign-in token (signature, expiry, our project). Raises ValueError if it is not valid."""
    if not config.FIREBASE_PROJECT_ID:
        raise ValueError("FIREBASE_PROJECT_ID is not set")
    claims = id_token.verify_firebase_token(token, _google, audience=config.FIREBASE_PROJECT_ID)
    if claims.get("iss") != f"https://securetoken.google.com/{config.FIREBASE_PROJECT_ID}":
        raise ValueError("Token was issued for another project")
    return claims


def is_allowed_google_user(claims: dict) -> bool:
    """Only Google accounts with a verified college email address.

    An address is only "verified" when its owner has proved they can read
    mail sent to it, so a personal account can't pass with a made-up
    @nmamit.in address.
    """
    email = (claims.get("email") or "").lower()
    return (
        (claims.get("firebase") or {}).get("sign_in_provider") == "google.com"
        and bool(claims.get("email_verified"))
        and email.count("@") == 1
        and email.endswith("@" + config.ALLOWED_DOMAIN)
    )


def is_admin(email: str) -> bool:
    return email.lower() in config.ADMIN_EMAILS


# --- FastAPI dependencies -----------------------------------------------------

def signed_in_user(request: Request) -> dict:
    if not request.session.get("email"):
        raise HTTPException(401, "Please sign in.")
    return request.session


def verified_user(request: Request) -> dict:
    user = signed_in_user(request)
    if not user.get("face_ok"):
        raise HTTPException(403, "Face check required.")
    return user


def admin_user(request: Request) -> dict:
    user = verified_user(request)
    if not is_admin(user["email"]):
        raise HTTPException(403, "Admins only.")
    return user


# --- Simple in-memory limits ------------------------------------------------------
# Kept on the server (not in the session cookie) so they can't be reset by
# replaying an old cookie. They reset when the server restarts, which is fine
# for a single-server project.

class FaceLockout:
    def __init__(self, max_failures: int, lock_seconds: int):
        self.max_failures = max_failures
        self.lock_seconds = lock_seconds
        self._fails: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def _recent(self, email: str) -> list[float]:
        cutoff = time.time() - self.lock_seconds
        fails = [t for t in self._fails[email] if t > cutoff]
        self._fails[email] = fails
        return fails

    def seconds_left(self, email: str) -> int:
        with self._lock:
            fails = self._recent(email)
            if len(fails) < self.max_failures:
                return 0
            return int(fails[-self.max_failures] + self.lock_seconds - time.time()) + 1

    def tries_left(self, email: str) -> int:
        with self._lock:
            return max(0, self.max_failures - len(self._recent(email)))

    def fail(self, email: str) -> None:
        with self._lock:
            self._fails[email].append(time.time())

    def reset(self, email: str) -> None:
        with self._lock:
            self._fails.pop(email, None)


class RateLimit:
    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] < now - 60:
                hits.popleft()
            if len(hits) >= self.per_minute:
                return False
            hits.append(now)
            return True


face_lockout = FaceLockout(config.FACE_MAX_FAILURES, config.FACE_LOCK_MINUTES * 60)
ask_limit = RateLimit(config.ASKS_PER_MINUTE)
