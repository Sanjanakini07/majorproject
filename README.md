# NMAMIT Campus Voice Assistant

A small website where an NMAMIT student signs in with their college Google account, passes a quick face check, taps a button, asks a question out loud, and hears the answer. Answers come only from the information admins add in the admin panel. This approach is called RAG (retrieval-augmented generation).

```
Student                        Server                                   Admin
───────                        ──────                                   ─────
Google sign-in (@nmamit.in) ─► Firebase token checked; must be a verified nmamit.in email
Webcam photo ────────────────► OpenCV compares it with the one registered photo
Tap, speak, tap
  browser turns speech → text
  question ──────────────────► 1. search the vector database (ChromaDB)  ◄── text / CSV / image
                               2. send the best matches + question to Groq      added in the admin panel
  ◄── answer ───────────────── 3. stream progress + answer back
  browser reads it aloud
```

## What's inside

| Folder / file | What it does |
|---|---|
| `app/main.py` | Pages, Google sign-in (Firebase), face check endpoint, `/api/ask` |
| `app/auth.py` | Who is allowed in, plus lockout and rate limits |
| `app/face.py` | Face check with OpenCV (YuNet finds the face, SFace compares faces) |
| `app/rag.py` | Splitting text into chunks, the vector database, the Groq call |
| `app/ingest.py` | Reading CSV files and text in images (RapidOCR) |
| `app/admin.py` | Admin API: knowledge entries and registered faces |
| `app/db.py` | SQLite tables (knowledge entries, face signatures) |
| `app/pages/`, `app/static/` | Plain HTML, CSS and JavaScript (no framework) |
| `offline_app/`, `start_offline.bat` | The offline version: see [Offline version](#offline-version-no-internet-needed) |
| `start.bat` | One double-click: installs, checks settings, sets up once, starts the app |
| `scripts/` | Settings check, one-time setup, downloading the student photos, registering a face by hand, recording the demo video |
| `sample_data/` | Example CSVs to try the admin import |
| `tests/` | `pytest` tests |

## Quick start (Windows)

You need **Python 3.10 or newer** (tick *Add python.exe to PATH* when installing) and **Chrome or Edge**.

1. Get the four settings below and put them in a file called `.env` in this folder. If there is no `.env` yet, `start.bat` creates one and opens it in Notepad for you.
2. **Double-click `start.bat`.**

The first run installs everything and downloads the models and student photos (5-10 minutes). After that it starts in seconds and opens **http://localhost:8000**. Keep the black window open while using the app; close it to stop the app.

Then try it: sign in, pass the face check, click **Admin**, **Import CSV** → `sample_data/sample_knowledge.csv`, go back, tap the microphone and ask "When is the library open?"

## Offline version (no internet needed)

`offline_app/` is the same assistant running entirely on one Windows laptop. Phones on the same Wi-Fi use it through their browser.

| Step | Online version | Offline version |
|---|---|---|
| Sign in | Google account + face check | Roll number + face (OpenCV, on the laptop) |
| Speech to text | Browser (Google servers) | faster-whisper, on the laptop |
| Answer | Groq | Small local model through [Ollama](https://ollama.com) (`qwen2.5:1.5b`). Groq is used only if Ollama is not running and there is internet |
| Text to speech | Browser | Piper, on the laptop |
| Data | `data/app.db` | The same `data/app.db`, synced with the Turso backend whenever there is internet |

**Start it:** double-click **`start_offline.bat`**. The first run needs internet. It installs Ollama and the packages, then downloads the models (about 2 GB) and the student photos. This takes 10-20 minutes. After that it works with Wi-Fi off and opens **http://localhost:8100**.

**Face sign-in:** the student types their roll number and looks at the camera. The first time, the photo is checked against their college ID photo. If it matches, it is saved as their sign-in photo. Later sign-ins match either the college photo or that first photo. If an admin removes the college photo, that student can't sign in.

**Phones:** on the laptop, click **Connect a phone** and scan the QR code with a phone on the same Wi-Fi or hotspot. The phone warns that the connection is not private, because the laptop made its own certificate (phones only allow the camera and microphone on `https`). Tap **Advanced → Proceed**. The first time the app starts, Windows asks whether Python may use the network. Allow it on private networks.

**Sync:** set `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` in `.env`. Every change (knowledge entries, college faces, first sign-in photos) is saved on the laptop first, then sent to Turso every minute when online. Changes from other laptops come back the same way, and the newer edit wins. The button at the top of the assistant shows the state (Synced / Offline / items still to send) and syncs now when clicked. On Turso the tables are `nva_modules`, `nva_faces` and `nva_first_faces`, so they don't touch other tables in the same database.

**Tuning:** `OLLAMA_MODEL` (for example `qwen2.5:3b` for better answers, slower) and `WHISPER_MODEL` (`tiny.en`, `base.en`, `small.en`). After changing `OLLAMA_MODEL`, run `ollama pull <name>`. Run it by hand with `python -m offline_app.setup` once, then `python -m offline_app`.

## The settings (`.env`)

`start.bat` checks these every time and tells you exactly what is missing. It also creates a strong `SECRET_KEY` by itself.

| Setting | Where to get it |
|---|---|
| `FIREBASE_API_KEY`, `FIREBASE_PROJECT_ID` | Google sign-in runs through Firebase. On the [Firebase console](https://console.firebase.google.com/): **Create a project** (Analytics not needed). **Build → Authentication → Get started → Google → Enable → Save**. Then **Project settings → General → Your apps → Web (`</>`)**, register the app, and copy `apiKey` and `projectId` from the config shown. Use a *new* Firebase project: then any Google account can sign in with no extra Google Cloud setup, and `localhost` is already allowed. |
| `GROQ_API_KEY` | [console.groq.com/keys](https://console.groq.com/keys). `GROQ_MODEL` picks the model; if Groq retires it, choose a current one from [their models page](https://console.groq.com/docs/models). |
| `ADMIN_EMAILS` | Your college email. Separate several admins with commas. |

Always open the app as `http://localhost:8000`, not `127.0.0.1`: Firebase only allows sign-in from addresses on its list, and `localhost` is on it by default.

## Student faces

The first setup downloads the college-provided student photos (NNM23IS001, NNM23IS002, …) into `student_photos/` and registers each face for its college email (`nnm23is186@nmamit.in`). The photos are not committed to git; every copy of the project downloads them. To fetch a different range or re-register: `python scripts/fetch_student_photos.py --end 250 --force`.

Anyone not in the college photos is added in **Admin → Faces**, or from the command line with one clear, front-facing photo:

```bash
python scripts/enroll_face.py yourname@nmamit.in path/to/your-photo.jpg
```

## Manual setup (macOS, Linux, or without start.bat)

```bash
python -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/check_setup.py          # creates .env and lists what to fill in
python scripts/setup_models.py         # models, student photos and faces (once)
uvicorn app.main:app --port 8000
```

## Using the admin panel

- **Add / edit / delete** an entry: the change is applied to the vector database at once, so the next question uses it.
- **Import CSV**: a file with `title,content` columns gives one entry per row. Any other CSV also works (for example `sample_data/sample_timetable.csv`): each row becomes an entry like "Day: Monday. Time: 9:00 AM. Subject: …".
- **Read text from image**: upload a photo of a notice or timetable. The text is copied into the form so you can correct it before saving.
- **Rebuild search index**: rebuilds the vector database from the saved entries. Use it only if search ever seems out of sync.
- **Faces**: register one photo per student by their college email. Only the 128-number face signature is stored, not the photo.

## Settings you may want to tune (`.env`)

| Setting | Default | Meaning |
|---|---|---|
| `FACE_MATCH_THRESHOLD` | `0.363` | How similar the live face must be to the registered one (0 to 1). Higher is stricter. |
| `FACE_MAX_FAILURES` / `FACE_LOCK_MINUTES` | `5` / `10` | Failed face checks before a temporary lock |
| `TOP_K` | `4` | How many pieces of knowledge are given to the AI per question |
| `MAX_DISTANCE` | `0.7` | How close a piece must be to the question to be used (0 = same meaning) |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | Which Groq model writes the answers |

## Putting it on a server

- **Camera and microphone only work over HTTPS** (or on localhost). Put it behind HTTPS.
- Set `BASE_URL=https://your-domain`, `HTTPS_ONLY=true` and a fixed `SECRET_KEY`. In Firebase, add `your-domain` under **Authentication → Settings → Authorized domains**.
- Run **one** worker: `uvicorn app.main:app --host 0.0.0.0 --port 8000`. ChromaDB here is a local folder and the lockout counters live in memory, so several worker processes would not see each other's changes.
- Keep the `data/` folder on a disk that survives restarts. It holds the database and the vector index.

## Demo video

`scripts/record_demo.py` records a captioned walkthrough of the whole flow into `demo_video/` (not committed). It runs its own copy of the app with a temporary data folder, so your knowledge base is not changed. See `.claude/skills/demo-video/SKILL.md` for setup, options and what the video simulates (Google sign-in and the microphone).

## Tests

```bash
pytest
```

The tests use a stand-in for the vector database and need no internet. Face tests run once the models are downloaded. To also test real matching, point the test at photos of two different people:

```bash
FACE_TEST_A=person1.jpg FACE_TEST_B=person2.jpg pytest
```

## Security notes and known limits

- **Two locks.** Google sign-in is checked first: the server verifies the Firebase sign-in token and requires a Google account with a verified `@nmamit.in` email (verified means the owner proved they can read that mailbox). The face check is a second layer on top of that.
- **One photo, no liveness check.** Someone holding up a good printed photo or a phone screen could pass the face check. They would still need the student's Google account. A blink or head-turn check is a possible upgrade.
- **Voice input runs in the browser.** Chrome sends the audio to Google's speech service to turn it into text. Firefox has no voice input; the text box always works.
- **Answers only from the knowledge base.** The AI is told to answer only from the matched entries and to say when it doesn't know. Keep the entries accurate. The sample CSV entries are made up and marked "(sample)".
- **Lockouts reset on restart.** Lockout and rate-limit counters are kept in memory.

## Troubleshooting

| Problem | Fix |
|---|---|
| `start.bat` closes straight away or says Python is missing | Install Python 3.10+ from python.org with *Add python.exe to PATH* ticked, then run `start.bat` again. |
| `start.bat` opens Notepad | A setting in `.env` is empty. The window lists which ones; fill them in, save, run `start.bat` again. |
| "Please use your @nmamit.in college Google account" with a college account | Pick the @nmamit.in account in the Google window, not a personal one. Check `ALLOWED_DOMAIN`. |
| Google window shows `auth/unauthorized-domain` | Open the app as `http://localhost:8000`. For any other address, add it in Firebase under **Authentication → Settings → Authorized domains**. |
| Nothing happens when clicking Sign in | The browser blocked the pop-up. Allow pop-ups for this site and try again. |
| "Google sign-in is not set up on this server yet" | `FIREBASE_API_KEY` or `FIREBASE_PROJECT_ID` is empty in `.env`. |
| "Your face is not registered yet" | An admin must add the photo under **Admin → Faces** (or use `scripts/enroll_face.py`). |
| Face never matches | Use a brighter, front-facing reference photo. Check the score in the server log; you can lower `FACE_MATCH_THRESHOLD` slightly. |
| Every answer is "Sorry, something went wrong" | Check the server log. Usually `GROQ_API_KEY` is missing or `GROQ_MODEL` was retired. |
| Mic button does nothing | Use Chrome or Edge, allow microphone access, and open the site over HTTPS or localhost. |
