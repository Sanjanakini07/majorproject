"""Record an HTML explainer animation (docs/*-explainer.html) as an MP4.

    pip install playwright imageio-ffmpeg
    python scripts/record_explainer.py docs/whats-new-explainer.html docs/whats-new.mp4

Uses the Microsoft Edge that comes with Windows (no browser download). The page must set window.TOTAL (ms).
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import imageio_ffmpeg
from playwright.sync_api import sync_playwright


def main(page_path: str, out: str) -> None:
    page_url = Path(page_path).resolve().as_uri()
    work = Path(tempfile.mkdtemp(prefix="explainer-"))
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge")
        context = browser.new_context(viewport={"width": 1280, "height": 720}, record_video_dir=str(work),
                                      record_video_size={"width": 1280, "height": 720})
        page = context.new_page()
        page.goto(page_url)
        total = page.evaluate("window.TOTAL")
        page.wait_for_timeout(total + 1500)
        context.close()
        browser.close()
    raw = next(work.glob("*.webm"))
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(raw), "-ss", "0.4",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "24", "-movflags", "+faststart", out], check=True)
    shutil.rmtree(work, ignore_errors=True)
    print("saved", out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
