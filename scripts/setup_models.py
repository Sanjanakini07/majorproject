"""Download everything the app needs once, so the first real use isn't slow.

    python scripts/setup_models.py

* OpenCV face models (~40 MB) into ./models
* ChromaDB's embedding model (~80 MB) into your user cache
* RapidOCR's models ship inside the pip package, nothing to download
"""
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

print("All set.")
