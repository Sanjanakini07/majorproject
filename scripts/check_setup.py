"""Check the .env settings before starting, and say in plain words what is missing.

    python scripts/check_setup.py
    python scripts/check_setup.py --offline    (for start_offline.bat)

* Creates .env from .env.example if there is none.
* Fills in a strong SECRET_KEY if it is empty or too short.
* Exits with 1 (and lists what to fill in) if a required setting is empty.
start.bat runs this every time.
"""
import re
import secrets
import shutil
import sys
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent

REQUIRED = {
    "FIREBASE_API_KEY": "Firebase console > Project settings > General > Your apps > apiKey (see README)",
    "FIREBASE_PROJECT_ID": "the same place, projectId",
    "GROQ_API_KEY": "https://console.groq.com/keys",
    "ADMIN_EMAILS": "your college email, for example nnm23is186@nmamit.in",
}
# The offline app (start_offline.bat) signs in with faces and answers with a local model.
REQUIRED_OFFLINE = {"ADMIN_EMAILS": REQUIRED["ADMIN_EMAILS"]}
MIN_SECRET_LENGTH = 32


def ensure_secret_key(env_file: Path) -> bool:
    """Write a random SECRET_KEY into .env if it has none or a weak one. Returns True if it changed."""
    text = env_file.read_text(encoding="utf-8")
    current = dotenv_values(env_file).get("SECRET_KEY") or ""
    if len(current) >= MIN_SECRET_LENGTH:
        return False
    line = f"SECRET_KEY={secrets.token_urlsafe(32)}"
    if re.search(r"(?m)^SECRET_KEY=.*$", text):
        text = re.sub(r"(?m)^SECRET_KEY=.*$", line, text, count=1)
    else:
        text = text.rstrip("\n") + "\n" + line + "\n"
    env_file.write_text(text, encoding="utf-8")
    return True


def check(root: Path = ROOT, required: dict = REQUIRED) -> list[str]:
    """Return the problems that stop the app from working (empty list = all good)."""
    env_file = root / ".env"
    if not env_file.exists():
        shutil.copy(root / ".env.example", env_file)
        print("Created a new .env file from .env.example.")
    if ensure_secret_key(env_file):
        print("Generated a new SECRET_KEY in .env.")

    values = dotenv_values(env_file)
    problems = [
        f"{name} is empty. Get it from: {where}"
        for name, where in required.items()
        if not (values.get(name) or "").strip()
    ]
    domain = (values.get("ALLOWED_DOMAIN") or "nmamit.in").strip().lower()
    for email in filter(None, (e.strip().lower() for e in (values.get("ADMIN_EMAILS") or "").split(","))):
        if not email.endswith("@" + domain):
            problems.append(f"ADMIN_EMAILS has {email}, which is not an @{domain} address.")
    return problems


def main() -> int:
    problems = check(required=REQUIRED_OFFLINE if "--offline" in sys.argv else REQUIRED)
    if problems:
        print("\nPlease fill in these settings in the .env file, save it, and start again:\n")
        for p in problems:
            print("  - " + p)
        print()
        return 1
    print("Settings look good.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
