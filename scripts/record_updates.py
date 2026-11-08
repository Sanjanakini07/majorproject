"""Record a short narrated video of the client's feedback round (8 Nov 2026) working in the real desktop app.

    .venv\\Scripts\\python scripts\\record_updates.py --data C:\\path\\to\\a\\seeded\\data --out docs\\feedback-updates.mp4

--data is a data folder that has been started once (seeded and searchable); it is copied, never changed. The offline
app runs on port 8200 (so an open copy on 8100 is left alone), Playwright drives it with on-screen captions, a
Windows voice reads them, and ffmpeg joins the two. The demo student is NNM23IS042 (Asha K Rao), an admin here.
"""
import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import wave
from pathlib import Path

from itsdangerous import TimestampSigner
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PORT = 8200
BASE = f"http://localhost:{PORT}"
W, H = 1280, 720
SECRET = "record-updates-secret"
EMAIL, NAME = "nnm23is042@nmamit.in", "NNM23IS042 ASHA K RAO"
VOICE = "Microsoft Zira Desktop"
READ_MS = 4500   # how long an answer stays on screen after the narration, so it can be read

SEE_NOTICE = """SEE time table 7th sem BTech ISE - Dec 2026 (TENTATIVE) 1pm-4pm
10-12-2026 thu MG1002-1 Financial Management
12-12-2026 sat electives IS1201-1 TQM / IS2213-1 OOMD / IS4224-1 SDN
15-12-2026 tue open electives (IS2503-1 SE practices, IS2504-1 web tech ...)
17-12-2026 thu IS2302-1 UID / IS3343-1 OR / IS4321-1 IDS / IS4323-1 WSN
21-12-2026 mon IS3002-1 Ethical Hacking & Network Defence
22-12-2026 tue reserve day"""

CAPTION_JS = """
(text) => {
  let box = document.getElementById('__cap');
  if (!box) {
    box = document.createElement('div');
    box.id = '__cap';
    box.style.cssText = 'position:fixed;left:50%;bottom:22px;transform:translateX(-50%);max-width:1100px;'
      + 'background:rgba(15,20,40,.88);color:#fff;font:600 21px/1.4 "Segoe UI",sans-serif;padding:14px 22px;'
      + 'border-radius:14px;z-index:99999;pointer-events:none;box-shadow:0 8px 30px rgba(0,0,0,.35);text-align:center';
    document.body.appendChild(box);
  }
  box.innerHTML = text;
  box.style.display = text ? 'block' : 'none';
}
"""

CARD_JS = """
(html) => {
  let c = document.getElementById('__card');
  if (!c) {
    c = document.createElement('div');
    c.id = '__card';
    c.style.cssText = 'position:fixed;inset:0;z-index:100000;display:flex;align-items:center;justify-content:center;'
      + 'background:linear-gradient(135deg,#172a5c,#3a1d57 55%,#7c1632);color:#fff;font-family:"Segoe UI",sans-serif;';
    document.body.appendChild(c);
  }
  c.innerHTML = html;
  c.style.display = html ? 'flex' : 'none';
}
"""


def tts(text: str, out: Path) -> float:
    """Speak text into a WAV with a built-in Windows voice. Returns its length in seconds (0 if no voice)."""
    script = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
              "try { $s.SelectVoice($env:V) } catch {}; $s.Rate = 1;"
              "$s.SetOutputToWaveFile($env:O); $s.Speak($env:T); $s.Dispose()")
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True, capture_output=True, timeout=90,
                       env={**os.environ, "V": VOICE, "O": str(out), "T": text})
        with wave.open(str(out)) as w:
            return w.getnframes() / w.getframerate()
    except Exception as e:  # the video still works without a voice
        print("  (no voice:", e, ")")
        return 0.0


class Recorder:
    def __init__(self, page, work: Path):
        self.page, self.work, self.audio, self.caption = page, work, [], ""
        self.t0 = time.monotonic()
        self.until = self.t0

    def show(self):
        self.page.evaluate(CAPTION_JS, self.caption)

    def say(self, caption: str, speech: str | None = None):
        """Caption on screen and spoken; actions can run while it is spoken. finish() waits for the end."""
        self.finish()
        self.caption = caption
        self.show()
        clip = self.work / f"say{len(self.audio)}.wav"
        seconds = tts(speech or caption.replace("<b>", "").replace("</b>", "").replace("<br>", " "), clip)
        now = time.monotonic()
        if seconds:
            self.audio.append((now - self.t0, clip))
        self.until = now + max(seconds, 2.5) + 0.4

    def finish(self):
        left = self.until - time.monotonic()
        if left > 0:
            self.page.wait_for_timeout(left * 1000)

    def goto(self, path: str):
        self.page.goto(BASE + path, wait_until="networkidle")
        self.show()

    def ask(self, question: str) -> str:
        self.goto("/")
        self.page.fill("#typeInput", "")
        self.page.type("#typeInput", question, delay=45)
        self.page.press("#typeInput", "Enter")
        self.page.wait_for_selector("#answer:not([hidden])", timeout=180000)
        self.page.wait_for_function("document.querySelector('#aText').textContent.trim().length > 0")
        self.show()
        return self.page.inner_text("#aText")

    def kind(self, kind: str):
        self.goto("/admin")
        self.page.click(f"#kinds .pill-btn[data-kind={kind}]")
        self.page.wait_for_timeout(600)
        self.page.locator("#formTitle").scroll_into_view_if_needed()
        self.page.evaluate("window.scrollBy(0, 260)")


def walkthrough(r: Recorder):
    p = r.page
    r.goto("/")
    p.evaluate(CARD_JS, "<div style='text-align:center'><div style='font-size:20px;opacity:.8;letter-spacing:.12em'>"
               "NMAMIT CAMPUS VOICE ASSISTANT</div><div style='font-size:44px;font-weight:800;margin:14px 0'>"
               "Client feedback of 8 November</div><div style='font-size:24px;opacity:.9'>What changed, request by "
               "request, in the real app</div></div>")
    r.say("", "Here is what changed after the client's feedback of 8 November, shown request by request in the real app.")
    r.finish()
    p.evaluate(CARD_JS, "")

    # 1. Teachers
    r.kind("teacher")
    r.say("<b>1 · Teachers, cabins, subjects.</b> 140 teachers from the department site and CabinCompass, "
          "in a spreadsheet. Missing cabins are highlighted.",
          "Request one: teachers, their cabins and subjects. 140 teachers from the department website and CabinCompass "
          "are in a spreadsheet. Missing cabins are highlighted for the admin to fill.")
    p.wait_for_selector("#sheetBox tbody tr")
    p.check("#sheetBox .sheet-tools input[type=checkbox]")
    p.wait_for_timeout(1200)
    first_gap = p.locator("#sheetBox tbody tr:not([hidden]) td.pending input.cell").first
    first_gap.click()
    first_gap.type("APJ 3rd Floor, room 304", delay=60)
    p.click("#sheetBox button:has-text('Save changes')")
    r.finish()
    r.say("Students just ask, even if the name is misheard: <b>“where is jayson sir’s cabin?”</b>",
          "Students just ask. Even a misheard name like Jayson finds Doctor Jason Elroy Martis.")
    r.ask("where is jayson sir's cabin?")
    r.finish()
    p.wait_for_timeout(READ_MS)

    # 2. Exams
    r.kind("exam")
    r.say("<b>2 · Exam dates.</b> The SEE timetable is pasted as it is; the AI tidies it. "
          "MSE 2 goes in the same way once the department sends it.",
          "Request two: exam dates. The semester end exam timetable is pasted exactly as it came, and the AI tidies it. "
          "The mid semester exam two dates go in the same way once the department sends them.")
    p.fill("#mContent", SEE_NOTICE)
    p.click("#tidy")
    p.wait_for_function("!document.querySelector('#tidy').disabled", timeout=120000)
    p.locator("#mContent").scroll_into_view_if_needed()
    r.finish()
    p.wait_for_timeout(1500)
    p.click("#mSave")
    p.wait_for_function("document.querySelector('#mContent').value === ''", timeout=60000)
    r.say("<b>“When is the FM SEE?”</b>", "Now: when is the F M semester end exam?")
    r.ask("when is the FM SEE?")
    r.finish()
    p.wait_for_timeout(READ_MS)

    # 3. Spelling
    r.say("<b>3 · Unclear input.</b> Misspelt or misheard words are corrected before answering: "
          "<b>“wat r the electiv subjcts in 6th sem”</b>",
          "Request three: unclear input. Misspelt or misheard words are corrected before the answer is worked out.")
    r.ask("wat r the electiv subjcts in 6th sem")
    r.finish()
    p.wait_for_timeout(READ_MS)

    # 4. College buses
    r.goto("/bus")
    r.say("<b>4 · College buses</b> have their own tab, empty until the routes arrive.",
          "Request four: college buses get their own tab on the Bus page. It stays empty until the routes arrive.")
    p.click("#busKind button[data-kind=college]")
    r.finish()
    r.kind("bus")
    r.say("The admin adds each bus: number, route, stops with times. Rows can be pasted from Excel.",
          "The admin adds each bus with its number, route and stops, or pastes the rows straight from Excel.")
    r.finish()

    # 5 + 6. Placements and EMS
    r.kind("placement")
    r.say("<b>6 · Placements</b> have their own list. The campus drives booked on EMS are already in; "
          "add eligibility and package per drive.",
          "Request six: placements have their own list. The campus drives booked on EMS are already in. "
          "The admin adds eligibility and package for each drive.")
    p.wait_for_selector("#sheetBox tbody tr")
    r.finish()
    r.goto("/events")
    r.say("<b>5 · EMS.</b> Those drives show on the Events page, next to a link to ems.nmamit.in. "
          "A live sync of the whole EMS calendar is the next step.",
          "Request five, E M S. Those drives show on the Events page, with a link to E M S. "
          "A live sync of the whole E M S calendar is the next step.")
    r.finish()
    r.say("<b>“When is the Wipfli drive?”</b>", "And students can ask about them.")
    r.ask("when is the wipfli drive?")
    r.finish()
    p.wait_for_timeout(READ_MS)

    # Mute
    r.goto("/")
    r.say("<b>Mute.</b> Answers show on screen without being read aloud. Play again still reads one out.",
          "Finally, the mute button. Answers show on screen without being read aloud, and Play again still reads one out.")
    p.click("#mute")
    p.wait_for_timeout(1200)
    r.ask("when is the library open?")
    r.finish()
    p.wait_for_timeout(READ_MS)

    r.caption = ""
    r.show()
    p.evaluate(CARD_JS, """<div style='font-size:22px;line-height:1.9;min-width:760px'>
      <div style='font-size:34px;font-weight:800;margin-bottom:10px'>Where each request stands</div>
      <div>✔ 1 · Teachers, cabins, subjects <span style='opacity:.75'>· 25 cabins left to fill</span></div>
      <div>✔ 2 · Exam dates: SEE in <span style='opacity:.75'>· MSE 2 when the department sends it</span></div>
      <div>✔ 3 · Misspelt and misheard words <span style='opacity:.75'>· send the exact Stiram example</span></div>
      <div>✔ 4 · College buses tab <span style='opacity:.75'>· waiting for the routes</span></div>
      <div>◐ 5 · EMS drives on Events <span style='opacity:.75'>· live EMS calendar next</span></div>
      <div>✔ 6 · Placements list, on Events too</div>
      <div>✔ Mute button</div></div>""")
    r.say("", "That is where each request stands.")
    r.finish()
    p.wait_for_timeout(7000)


def ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="a seeded data folder to copy (never changed)")
    ap.add_argument("--out", default=str(ROOT / "docs" / "feedback-updates.mp4"))
    args = ap.parse_args()

    work = Path(tempfile.mkdtemp(prefix="updates-video-"))
    shutil.copytree(args.data, work / "data")
    env = {**os.environ, "DATA_DIR": str(work / "data"), "SECRET_KEY": SECRET, "ADMIN_EMAILS": EMAIL,
           "OFFLINE_HTTP_PORT": str(PORT), "TURSO_DATABASE_URL": "", "TURSO_AUTH_TOKEN": "", "PYTHONIOENCODING": "utf-8"}
    server = subprocess.Popen([sys.executable, "-m", "offline_app"], cwd=ROOT, env=env,
                              stdout=(work / "server.log").open("w"), stderr=subprocess.STDOUT)
    try:
        for _ in range(240):
            try:
                urllib.request.urlopen(BASE + "/", timeout=2)
                break
            except Exception:
                time.sleep(0.5)
        cookie = TimestampSigner(SECRET).sign(base64.b64encode(json.dumps(
            {"email": EMAIL, "name": NAME, "face_ok": True}).encode())).decode()
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="msedge")
            context = browser.new_context(viewport={"width": W, "height": H}, record_video_dir=str(work / "raw"),
                                          record_video_size={"width": W, "height": H}, color_scheme="light",
                                          bypass_csp=True)
            context.add_cookies([{"name": "nva_session", "value": cookie, "url": BASE}])
            page = context.new_page()
            page.on("dialog", lambda d: d.accept())
            recorder = Recorder(page, work)
            print("Recording (about 2 minutes)...")
            walkthrough(recorder)
            video = Path(page.video.path())
            context.close()
            browser.close()
    finally:
        server.terminate()

    print("Encoding...")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    inputs, filters, labels = ["-i", str(video)], [], []
    for n, (start, clip) in enumerate(recorder.audio, start=1):
        inputs += ["-i", str(clip)]
        filters.append(f"[{n}:a]aresample=48000,adelay={int(start * 1000)}:all=1[a{n}]")
        labels.append(f"[a{n}]")
    encode = ["-c:v", "libx264", "-preset", "slow", "-crf", "22", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    cmd = [ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *inputs]
    if labels:
        mix = ";".join(filters) + f";{''.join(labels)}amix=inputs={len(labels)}:normalize=0:duration=longest[aout]"
        cmd += ["-filter_complex", mix, "-map", "0:v", "-map", "[aout]", *encode, "-c:a", "aac", "-b:a", "128k",
                "-shortest", str(out)]
    else:
        cmd += [*encode, str(out)]
    subprocess.run(cmd, check=True)
    shutil.rmtree(work, ignore_errors=True)
    print("Saved", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
