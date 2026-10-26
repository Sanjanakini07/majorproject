"""Download everything the app needs once, so the first real use isn't slow.

    python scripts/setup_models.py

* OpenCV face models (~40 MB) into ./models
* ChromaDB's embedding model (~80 MB) into your user cache
* RapidOCR's models ship inside the pip package, nothing to download
* The college-provided student photos (~36 MB) into ./student_photos, with
  their faces registered (see fetch_student_photos.py)
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chromadb.utils.embedding_functions import DefaultEmbeddingFunction  # noqa: E402

from app import face  # noqa: E402

print("Face models...")
face.ensure_models()
print("  ok")

print("Embedding model (first time can take a minute)...")
DefaultEmbeddingFunction()(["warm up"])
print("  ok")

print("Student photos and faces...", flush=True)
subprocess.run([sys.executable, str(Path(__file__).with_name("fetch_student_photos.py"))], check=True)

print("All set.")
