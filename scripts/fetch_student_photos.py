"""Download the college-provided student photos and register their faces.

    python scripts/fetch_student_photos.py              # NNM23IS001 .. NNM23IS300
    python scripts/fetch_student_photos.py --end 250
    python scripts/fetch_student_photos.py --force      # re-register faces already registered

Photos are saved in ./student_photos (NNM23IS186.JPG ...) and each one's face
signature is stored for nnm23is186@nmamit.in. Roll numbers with no photo are
skipped. Photos already downloaded are not downloaded again.
"""
import argparse
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config, db, face  # noqa: E402

PHOTO_URL = "https://university-student-photos.s3.ap-south-1.amazonaws.com/049/student_photos%2F{roll}.JPG"
PREFIX = "NNM23IS"
PHOTOS_DIR = config.BASE_DIR / "student_photos"


def download(roll: str) -> Path | None:
    path = PHOTOS_DIR / f"{roll}.JPG"
    if path.exists() and path.stat().st_size > 0:
        return path
    try:
        with urllib.request.urlopen(PHOTO_URL.format(roll=roll), timeout=30) as resp:
            data = resp.read()
    except urllib.error.HTTPError as e:
        if e.code in (403, 404):  # no photo for this roll number
            return None
        raise
    tmp = path.with_suffix(".part")
    tmp.write_bytes(data)
    tmp.replace(path)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=300)
    parser.add_argument("--force", action="store_true", help="replace faces that are already registered")
    args = parser.parse_args()

    PHOTOS_DIR.mkdir(exist_ok=True)
    rolls = [f"{PREFIX}{n:03d}" for n in range(args.start, args.end + 1)]
    print(f"Downloading photos {rolls[0]} .. {rolls[-1]} into {PHOTOS_DIR} ...")
    with ThreadPoolExecutor(max_workers=16) as pool:
        photos = [p for p in pool.map(download, rolls) if p]
    print(f"  {len(photos)} photos")

    db.init()
    added, kept, failed = 0, 0, []
    for path in photos:
        email = f"{path.stem.lower()}@{config.ALLOWED_DOMAIN}"
        if not args.force and db.get_face(email) is not None:
            kept += 1
            continue
        try:
            vec = face.embedding(path.read_bytes())
        except face.FaceError as e:
            failed.append(f"{path.name}: {e}")
            continue
        db.save_face(email, face.to_bytes(vec), "college photos")
        added += 1

    print(f"Faces registered: {added} new, {kept} already registered, {len(failed)} could not be used.")
    for line in failed:
        print("  " + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
