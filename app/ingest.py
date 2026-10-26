"""Turning uploaded files into knowledge modules: CSV rows and text in images."""
import csv
import io
import threading
from functools import lru_cache

MAX_CSV_ROWS = 2000


class IngestError(Exception):
    pass


def parse_csv(data: bytes, filename: str) -> list[dict]:
    """Return a list of {"title", "content"} from a CSV file.

    * If the CSV has `title` and `content` columns, each row becomes one module.
    * Any other CSV (a timetable, a staff list...) also works: each row becomes
      "Column: value. Column: value." titled with the file name and row number.
    """
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise IngestError("The CSV must be saved as UTF-8 (in Excel: Save As > CSV UTF-8).")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise IngestError("The CSV is empty.")
    columns = {(c or "").strip().lower(): c for c in reader.fieldnames}
    simple = "title" in columns and "content" in columns
    base = filename.rsplit(".", 1)[0] or "CSV"

    modules = []
    for n, row in enumerate(reader, start=1):
        if n > MAX_CSV_ROWS:
            raise IngestError(f"Too many rows. The limit is {MAX_CSV_ROWS} per file.")
        if simple:
            title = (row.get(columns["title"]) or "").strip()
            content = (row.get(columns["content"]) or "").strip()
        else:
            parts = [
                f"{(col or '').strip()}: {(val or '').strip()}"
                for col, val in row.items()
                if col and val and val.strip()
            ]
            title, content = f"{base} - row {n}", ". ".join(parts)
        if title and content:
            modules.append({"title": title[:200], "content": content})

    if not modules:
        raise IngestError("No usable rows found in the CSV.")
    return modules


_ocr_lock = threading.Lock()


@lru_cache(maxsize=1)
def _ocr():
    from rapidocr import RapidOCR  # loads its models once, on first use
    return RapidOCR()


def image_to_text(data: bytes) -> str:
    """Read the text printed in an image (notice, timetable, poster)."""
    import cv2
    import numpy as np

    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise IngestError("That file is not an image we can read. Use a JPG or PNG.")
    with _ocr_lock:
        result = _ocr()(img)
    lines = [t.strip() for t in (result.txts or ()) if t and t.strip()]
    if not lines:
        raise IngestError("No text was found in that image.")
    return "\n".join(lines)
