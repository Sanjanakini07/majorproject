"""Record a captioned walkthrough video of the whole app, for clients and reviews.

    python scripts/record_demo.py
    python scripts/record_demo.py --email nnm23is186@nmamit.in --name "Srujan"

Needs (once):  pip install playwright imageio-ffmpeg && python -m playwright install chromium

What it does:
* Starts a second copy of the app on port 8765 with its own data folder, so
  the real knowledge base is never touched (registered faces are copied in).
* Drives Chromium through every step: sign-in page, face check (the webcam is
  fed the account's registered photo), admin panel (typed entry, CSV import,
  text from an image, faces), questions by voice and by typing.
* Shows a plain caption at the bottom of each step and a visible cursor.
* Windows only: the student's question and the spoken answer are voiced with
  the built-in Windows voices and mixed into the video.

Recording notes, so nobody is misled by the video:
* Google sign-in can't be automated. The video shows the sign-in button and
  explains it, then continues with a signed-in session for the demo account.
* Browser speech recognition doesn't run under automation. The microphone is
  replaced by a stand-in that "hears" the scripted question; everything after
  that (search, AI answer, display) is the real app.

Output: demo_video/nmamit-assistant-walkthrough.mp4
"""
import argparse
import base64
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import imageio_ffmpeg  # noqa: E402
from itsdangerous import TimestampSigner  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from app import config  # noqa: E402

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
PORT = 8765
URL = f"http://localhost:{PORT}"
W, H = 1280, 720      # video size
ZOOM = 1.25           # the page is shown at 125% so text is easy to read
OUT_DIR = ROOT / "demo_video"
ACCENT = "#9b1c2c"

STUDENT_VOICE = "Microsoft David Desktop"
ASSISTANT_VOICE = "Microsoft Zira Desktop"

# --- Runs inside every page: caption bar, visible cursor, stand-in microphone --------

PAGE_SCRIPT = r"""
(() => {
  const store = {
    get(k) { try { return sessionStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { sessionStorage.setItem(k, v); } catch (e) {} },
  };

  function captionBox() {
    let box = document.getElementById('__demo_caption');
    if (!box && document.body) {
      box = document.createElement('div');
      box.id = '__demo_caption';
      Object.assign(box.style, {
        position: 'fixed', left: '50%', bottom: '20px', transform: 'translateX(-50%)',
        maxWidth: '84%', padding: '12px 24px 14px', borderRadius: '10px',
        background: 'rgba(18,18,18,0.88)', color: '#fff', textAlign: 'center',
        font: '500 20px/1.45 "Segoe UI", system-ui, sans-serif',
        zIndex: '2147483646', pointerEvents: 'none', boxShadow: '0 6px 24px rgba(0,0,0,0.28)',
      });
      document.documentElement.appendChild(box);  // outside <body>, so it isn't zoomed
    }
    return box;
  }

  function renderCaption() {
    const box = captionBox();
    if (!box) return;
    const cap = JSON.parse(store.get('__demo_cap') || 'null');
    box.replaceChildren();
    box.style.display = cap ? 'block' : 'none';
    if (!cap) return;
    if (cap.step) {
      const step = document.createElement('div');
      step.textContent = cap.step;
      Object.assign(step.style, { font: '600 12px/1.6 "Segoe UI", system-ui, sans-serif',
        letterSpacing: '0.08em', textTransform: 'uppercase', color: '#f3a3ad' });
      box.appendChild(step);
    }
    box.appendChild(document.createTextNode(cap.text));
  }

  window.__demoCaption = (step, text) => {
    store.set('__demo_cap', JSON.stringify(text ? { step, text } : null));
    renderCaption();
  };

  function cursor() {
    let c = document.getElementById('__demo_cursor');
    if (!c && document.body) {
      c = document.createElement('div');
      c.id = '__demo_cursor';
      c.innerHTML = '<svg width="26" height="26" viewBox="0 0 24 24"><path d="M4 2l15 11-6.5 1.2L16 21l-3 1.4-3.4-6.9L4 20z" fill="#111" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
      Object.assign(c.style, { position: 'fixed', left: '0', top: '0', zIndex: '2147483647',
        pointerEvents: 'none', transition: 'transform 0.12s', transformOrigin: '4px 2px' });
      document.documentElement.appendChild(c);
      const pos = JSON.parse(store.get('__demo_pos') || '[640,360]');
      c.style.left = pos[0] - 4 + 'px'; c.style.top = pos[1] - 2 + 'px';
    }
    return c;
  }

  document.addEventListener('mousemove', (e) => {
    const c = cursor();
    if (c) { c.style.left = e.clientX - 4 + 'px'; c.style.top = e.clientY - 2 + 'px'; }
    store.set('__demo_pos', JSON.stringify([e.clientX, e.clientY]));
  }, true);
  document.addEventListener('mousedown', () => { const c = cursor(); if (c) c.style.transform = 'scale(0.8)'; }, true);
  document.addEventListener('mouseup', () => { const c = cursor(); if (c) c.style.transform = ''; }, true);

  function setup() {
    if (location.protocol.startsWith('http')) {  // the app's pages, not the title cards
      document.body.style.zoom = '__ZOOM__';
      document.body.style.minHeight = 'calc(100vh / __ZOOM__)';
    }
    renderCaption();
    cursor();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', setup);
  else setup();

  // Stand-in for the browser's speech recognition: "hears" window.__demoSpeech word by word.
  class StandInRecognition {
    start() {
      const s = window.__demoSpeech || { text: '', wordMs: 300 };
      const words = s.text.split(' ');
      this._text = s.text;
      let i = 0;
      this._timer = setInterval(() => {
        i += 1;
        this._emit(words.slice(0, i).join(' '), false);
        if (i >= words.length) clearInterval(this._timer);
      }, s.wordMs);
    }
    _emit(text, isFinal) {
      const result = [{ transcript: text }];
      result.isFinal = isFinal;
      if (this.onresult) this.onresult({ resultIndex: 0, results: [result] });
    }
    stop() {
      clearInterval(this._timer);
      this._emit(this._text, true);
      setTimeout(() => this.onend && this.onend(), 50);
    }
    abort() { this.stop(); }
  }
  window.SpeechRecognition = StandInRecognition;
  window.webkitSpeechRecognition = StandInRecognition;
  // The video gets its own voice track, so the browser stays quiet.
  if (window.speechSynthesis) window.speechSynthesis.speak = () => {};
})();
"""


def title_card(title: str, subtitle: str = "", lines: list[str] | None = None) -> str:
    items = "".join(f"<li>{line}</li>" for line in lines or [])
    return f"""<!doctype html><html><head><style>
      html,body{{margin:0;height:100%;background:#f6f6f4;color:#1c1c1c;font-family:"Segoe UI",system-ui,sans-serif}}
      body{{display:flex;flex-direction:column;justify-content:center;padding:0 140px}}
      .bar{{width:64px;height:6px;background:{ACCENT};border-radius:3px;margin-bottom:28px}}
      h1{{font-size:54px;margin:0 0 14px;font-weight:650;letter-spacing:-0.01em}}
      p{{font-size:25px;margin:0;color:#55554f;line-height:1.5}}
      ul{{margin:30px 0 0;padding:0;list-style:none}}
      li{{font-size:22px;line-height:1.5;margin:10px 0;padding-left:26px;position:relative;color:#33332f}}
      li::before{{content:"";position:absolute;left:0;top:14px;width:10px;height:10px;border-radius:50%;background:{ACCENT}}}
    </style></head><body><div class="bar"></div><h1>{title}</h1><p>{subtitle}</p><ul>{items}</ul></body></html>"""


NOTICE_HTML = f"""<!doctype html><html><head><style>
  body{{margin:0;background:#fff;font-family:Georgia,serif;color:#111}}
  .n{{width:760px;padding:46px 54px;border:3px double #333}}
  h2{{text-align:center;margin:0 0 6px;font-size:30px}} h3{{text-align:center;margin:0 0 28px;font-size:22px;font-weight:normal}}
  p{{font-size:23px;line-height:1.6;margin:0 0 18px}} .s{{text-align:right;margin-top:36px}}
</style></head><body><div class="n">
  <h2>NMAM INSTITUTE OF TECHNOLOGY</h2><h3>NOTICE (sample)</h3>
  <p>The Central Library will remain closed on Saturday, 7 November 2026 for annual stock verification.</p>
  <p>Books due on that day may be returned on Monday, 9 November 2026 without a fine.</p>
  <p class="s">Chief Librarian</p></div></body></html>"""


# --- Helpers --------------------------------------------------------------------------

def run_ffmpeg(*args: str) -> None:
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def tts(text: str, voice: str, out: Path) -> float | None:
    """Write text as speech to a WAV file with a built-in Windows voice. Returns seconds."""
    if os.name != "nt":
        return None
    script = (
        "Add-Type -AssemblyName System.Speech;"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        "try { $s.SelectVoice($env:DEMO_VOICE) } catch {};"
        "$s.SetOutputToWaveFile($env:DEMO_OUT); $s.Speak($env:DEMO_TEXT); $s.Dispose()"
    )
    env = {**os.environ, "DEMO_VOICE": voice, "DEMO_OUT": str(out),
           "DEMO_TEXT": text.replace(" ", " ").replace("‑", "-")}
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", script], env=env, check=True,
                       capture_output=True, timeout=60)
        with wave.open(str(out)) as w:
            return w.getnframes() / w.getframerate()
    except Exception as e:  # voices are a nice-to-have; the video works without them
        print(f"  (no voice: {e})")
        return None


def session_cookie(email: str, name: str) -> str:
    data = base64.b64encode(json.dumps({"email": email, "name": name, "face_ok": False}).encode())
    return TimestampSigner(config.SECRET_KEY).sign(data).decode()


def start_server(data_dir: Path, log: Path) -> subprocess.Popen:
    env = {**os.environ, "DATA_DIR": str(data_dir), "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)],
        cwd=ROOT, env=env, stdout=log.open("w"), stderr=subprocess.STDOUT,
    )
    for _ in range(120):
        try:
            urllib.request.urlopen(URL, timeout=2)
            return proc
        except Exception:
            if proc.poll() is not None:
                raise SystemExit(f"Demo server stopped. See {log}")
            time.sleep(0.5)
    proc.terminate()
    raise SystemExit(f"Demo server did not start. See {log}")


class Recorder:
    """Wraps the page with timed captions, visible mouse moves and an audio timeline."""

    def __init__(self, page, work: Path):
        self.page = page
        self.work = work
        self.t0 = time.time()
        self.audio: list[tuple[float, Path]] = []

    def now(self) -> float:
        return time.time() - self.t0

    def wait(self, seconds: float) -> None:
        self.page.wait_for_timeout(int(seconds * 1000))

    def caption(self, step: str, text: str, hold: float | None = None) -> None:
        self.page.evaluate("([s, t]) => window.__demoCaption && window.__demoCaption(s, t)", [step, text])
        self.wait(hold if hold is not None else max(2.6, len(text) / 15))

    def card(self, title: str, subtitle: str = "", lines: list[str] | None = None, hold: float = 3.5) -> None:
        # Clear the caption first, so it doesn't flash up again on the next app page.
        self.page.evaluate("() => window.__demoCaption && window.__demoCaption('', '')")
        self.page.goto("about:blank")
        self.page.set_content(title_card(title, subtitle, lines))
        self.wait(hold)

    def goto(self, path: str) -> None:
        self.page.goto(URL + path)
        self.page.wait_for_load_state("networkidle")

    def point(self, selector: str) -> None:
        box = self.page.locator(selector).first.bounding_box()
        view_h = self.page.viewport_size["height"]
        if box["y"] < 50 or box["y"] + box["height"] > view_h - 140:  # keep it clear of the caption bar
            self.page.locator(selector).first.evaluate("el => el.scrollIntoView({behavior: 'smooth', block: 'center'})")
            self.wait(0.9)
            box = self.page.locator(selector).first.bounding_box()
        self.page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=28)
        self.wait(0.35)

    def click(self, selector: str) -> None:
        self.point(selector)
        self.page.locator(selector).first.click()

    def type(self, selector: str, text: str, delay: int = 28) -> None:
        self.click(selector)
        self.page.locator(selector).first.press_sequentially(text, delay=delay)

    def choose_file(self, button: str, path: Path) -> None:
        self.point(button)
        with self.page.expect_file_chooser() as chooser:
            self.page.locator(button).click()
        self.wait(0.6)
        chooser.value.set_files(str(path))

    def scroll_to(self, selector: str) -> None:
        self.page.locator(selector).first.evaluate("el => el.scrollIntoView({behavior: 'smooth', block: 'start'})")
        self.wait(1.2)

    def voice(self, text: str, voice: str, lead: float = 0.0) -> float:
        """Queue a voice clip starting now (+lead). Returns its length (0 if no voice)."""
        start = self.now() + lead
        out = self.work / f"voice{len(self.audio)}.wav"
        seconds = tts(text, voice, out)
        if not seconds:
            return 0.0
        self.audio.append((start, out))
        return seconds

    def ask_by_voice(self, question: str, step: str, start: str = "#mic", hint: str = "") -> None:
        self.caption(step, hint or "Tap the microphone and ask the question out loud.", hold=2.4)
        clip = self.work / "q.wav"
        seconds = tts(question, STUDENT_VOICE, clip) or len(question.split()) * 0.35
        word_ms = int(seconds * 1000 / max(1, len(question.split())))
        self.page.evaluate("s => { window.__demoSpeech = s; }", {"text": question, "wordMs": word_ms})
        self.click(start)
        if clip.exists():
            final = self.work / f"voice{len(self.audio)}.wav"
            shutil.move(clip, final)
            self.audio.append((self.now(), final))
        self.caption(step, "The words appear as they are heard. Tap again when done.", hold=seconds + 0.8)
        self.click("#mic")
        self.show_answer(step)

    def ask_by_typing(self, question: str, step: str) -> None:
        self.type("#typeInput", question, delay=45)
        self.wait(0.4)
        self.click("#typeForm button")
        self.show_answer(step)

    def show_answer(self, step: str) -> None:
        self.caption(step, "The question is matched against the college information, then the AI writes "
                           "a short answer using only what it found.", hold=0.3)
        self.page.wait_for_selector("#answer:not([hidden])", timeout=60000)
        answer = self.page.inner_text("#aText")
        start = self.now()
        seconds = self.voice(answer, ASSISTANT_VOICE, lead=0.5)
        if self.page.inner_text("#aSources").strip():
            self.caption(step, "The answer appears on screen and is read aloud, with the entries it came from.", hold=0)
        else:
            self.caption(step, "Nothing in the college information matches, so the assistant says so "
                               "instead of guessing.", hold=0)
        remaining = start + 0.5 + max(seconds, 4.5) + 1.2 - self.now()
        self.wait(max(remaining, 1.0))


# --- The walkthrough -------------------------------------------------------------------

def walkthrough(r: Recorder, email: str, name: str, notice: Path) -> None:
    p = r.page
    r.card("NMAMIT Campus Voice Assistant",
           "A walkthrough of the complete flow: signing in, the face check, asking by voice, and the admin panel.",
           hold=5)

    # 1. Sign in
    r.card("1 · Sign in", "Only college Google accounts can get in.", hold=3)
    step = "Step 1 · Sign in"
    r.goto("/")
    r.caption(step, "Students open the website and sign in with their college Google account.")
    r.point("#signin")
    r.caption(step, "The button opens Google's own sign-in window, which offers only @nmamit.in accounts.")
    r.caption(step, "The server then checks the account has a verified @nmamit.in email. Personal Gmail "
                    "accounts are turned away.")

    # Continue as a signed-in student (Google sign-in itself can't be automated).
    p.context.add_cookies([{"name": "nva_session", "value": session_cookie(email, name), "url": URL}])

    # 2. Face check
    r.card("2 · Face check", "A second lock on top of Google sign-in.", hold=3)
    step = "Step 2 · Face check"
    r.goto("/face")
    p.wait_for_selector("#verify:not([disabled])", timeout=20000)
    r.caption(step, "After signing in, the student looks at the camera.")
    r.caption(step, "The live picture is compared with the photo the college registered for this student.")
    r.click("#verify")
    p.wait_for_url(URL + "/", timeout=30000)
    p.wait_for_load_state("networkidle")
    r.caption(step, "Matched, so the assistant opens. Five wrong tries lock the account for 10 minutes.")
    r.caption(step, "Only a 128-number face signature is stored, never the photo itself.")

    # 3. Admin panel
    r.card("3 · Admin panel", "Admins decide what the assistant knows.", hold=3)
    step = "Step 3 · Admin panel"
    r.goto("/")
    r.caption(step, "Admins see an Admin link at the top.", hold=2.2)
    r.click("#adminLink")
    p.wait_for_load_state("networkidle")
    r.caption(step, "The assistant answers only from what admins add here. Entries can be typed in.")
    r.type("#mTitle", "Hostel office hours (sample)")
    r.type("#mContent", "The hostel office is open from 9:00 AM to 5:00 PM, Monday to Saturday. "
                        "Room change requests are accepted only in the first week of each month.", delay=14)
    r.wait(0.6)
    r.click("#mSave")
    p.wait_for_selector("#notice:not([hidden])")
    r.caption(step, "Saved. The very next question can use it, with no restart.")

    r.caption(step, "Many entries at once: import a spreadsheet (CSV file).", hold=2.4)
    r.choose_file("#csvButton", ROOT / "sample_data" / "sample_knowledge.csv")
    p.wait_for_selector("#notice:has-text('Imported')")
    r.caption(step, "Each row becomes an entry. Timetables and staff lists work too.")

    r.caption(step, "Printed notices: upload a photo and the text is read from the picture.", hold=2.6)
    r.choose_file("#imgButton", notice)
    p.wait_for_function("document.querySelector('#mContent').value.length > 20", timeout=60000)
    r.caption(step, "The text is put in the form so the admin can check it before saving.", hold=4)
    r.click("#mSave")
    p.wait_for_selector("#notice:has-text('Added')")
    r.scroll_to("#modules")
    r.caption(step, "All entries can be searched, edited or deleted here.")
    p.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
    r.wait(0.8)

    r.click(".tab[data-tab='faces']")
    r.wait(0.8)
    r.scroll_to("#tab-faces .card:nth-of-type(2)")
    r.caption(step, "Faces: one photo per student, registered by email. The whole batch is already registered.", hold=4.2)
    p.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
    r.wait(0.8)
    r.click(".tab[data-tab='knowledge']")
    r.wait(0.5)

    # 4. Asking
    r.card("4 · Ask a question", "Tap, speak, and hear the answer. Typing works too.", hold=3)
    step = "Step 4 · Asking questions"
    r.goto("/")
    r.ask_by_voice("When is the library open on Saturdays?", step)
    r.ask_by_voice("Is the library open on the 7th of November?", step, start="#again",
                   hint="Ask another starts listening again straight away.")
    r.caption(step, "That answer came from the notice photo uploaded a minute ago.", hold=3.4)

    r.caption(step, "Questions can also be typed.", hold=2)
    r.ask_by_typing("Who won the cricket world cup?", step)
    r.caption("", "")

    r.card("How it works", "", [
        "Sign-in: Google accounts on the nmamit.in college domain only",
        "Face check: OpenCV face models compare the live picture with the registered photo",
        "Answers: a vector search finds the matching college information, the Groq AI phrases the reply",
        "Voice: the browser turns speech into text and reads the answer aloud",
        "Admin panel: typed entries, CSV imports, text read from photos, face registration",
    ], hold=9)
    r.card("Thank you", "NMAMIT Campus Voice Assistant", hold=3)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", help="demo account (default: the first admin in .env)")
    parser.add_argument("--name", default="Student", help="name shown in the top bar")
    parser.add_argument("--photo", help="photo for the webcam (default: student_photos/<ROLL>.JPG)")
    parser.add_argument("--out", default=str(OUT_DIR / "nmamit-assistant-walkthrough.mp4"))
    args = parser.parse_args()

    email = (args.email or (sorted(config.ADMIN_EMAILS) or [""])[0]).lower()
    if not email or email not in config.ADMIN_EMAILS:
        raise SystemExit("The demo account must be listed in ADMIN_EMAILS (the video shows the admin panel).")
    photo = Path(args.photo) if args.photo else ROOT / "student_photos" / f"{email.split('@')[0].upper()}.JPG"
    if not photo.is_file():
        raise SystemExit(f"No photo at {photo}. Run scripts/setup_models.py or pass --photo.")
    if not (config.DATA_DIR / "app.db").is_file():
        raise SystemExit("No data/app.db yet. Run scripts/setup_models.py first.")

    work = Path(tempfile.mkdtemp(prefix="demo_"))
    data = work / "data"
    data.mkdir()
    # Faces from the real database, no knowledge entries: the video adds its own.
    shutil.copy(config.DATA_DIR / "app.db", data / "app.db")
    with sqlite3.connect(data / "app.db") as conn:
        conn.execute("DELETE FROM modules")

    print("Preparing the webcam picture...")
    camera = work / "camera.y4m"
    run_ffmpeg("-loop", "1", "-i", str(photo), "-t", "1", "-r", "10",
               "-vf", "scale=-2:560,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=0x3a3a38,format=yuv420p",
               str(camera))

    print("Starting a demo copy of the app...")
    server = start_server(data, work / "server.log")
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=[
                "--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream",
                f"--use-file-for-fake-video-capture={camera}",
                "--autoplay-policy=no-user-gesture-required",
            ])
            notice = work / "Library closure notice.png"
            helper = browser.new_page(viewport={"width": 900, "height": 700})
            helper.set_content(NOTICE_HTML)
            helper.locator(".n").screenshot(path=str(notice))
            helper.close()

            context = browser.new_context(
                viewport={"width": W, "height": H}, record_video_dir=str(work / "raw"),
                record_video_size={"width": W, "height": H}, color_scheme="light",
                bypass_csp=True, permissions=["camera", "microphone"], locale="en-IN",
            )
            context.add_init_script(PAGE_SCRIPT.replace("__ZOOM__", str(ZOOM)))
            page = context.new_page()
            recorder = Recorder(page, work)
            print("Recording the walkthrough (about 3 minutes)...")
            walkthrough(recorder, email, args.name, notice)
            video = Path(page.video.path())
            context.close()
            browser.close()
    finally:
        server.terminate()

    print("Encoding the final video...")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    inputs, filters, labels = ["-i", str(video)], [], []
    for n, (start, clip) in enumerate(recorder.audio, start=1):
        inputs += ["-i", str(clip)]
        ms = int(max(start, 0) * 1000)
        filters.append(f"[{n}:a]aresample=48000,adelay={ms}:all=1[a{n}]")
        labels.append(f"[a{n}]")
    encode = ["-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    if labels:
        mix = ";".join(filters) + f";{''.join(labels)}amix=inputs={len(labels)}:normalize=0:duration=longest[aout]"
        run_ffmpeg(*inputs, "-filter_complex", mix, "-map", "0:v", "-map", "[aout]",
                   *encode, "-c:a", "aac", "-b:a", "160k", str(out))
    else:
        run_ffmpeg(*inputs, *encode, str(out))
    shutil.rmtree(work, ignore_errors=True)
    print(f"Done: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
