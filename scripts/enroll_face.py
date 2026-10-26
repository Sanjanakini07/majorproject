"""Register a face from the command line.

Use this for the first admin: the admin panel is behind the face check, so
the first admin's face has to be added this way.

    python scripts/enroll_face.py yourname@nmamit.in path/to/photo.jpg
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config, db, face  # noqa: E402


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    email, photo = sys.argv[1].strip().lower(), Path(sys.argv[2])
    if not email.endswith("@" + config.ALLOWED_DOMAIN):
        print(f"Use an @{config.ALLOWED_DOMAIN} email address.")
        return 1
    if not photo.is_file():
        print(f"No such file: {photo}")
        return 1

    db.init()
    try:
        vec = face.embedding(photo.read_bytes())
    except face.FaceError as e:
        print(f"Could not use that photo: {e}")
        return 1
    db.save_face(email, face.to_bytes(vec), "command line")
    print(f"Face registered for {email}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
