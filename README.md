# NMAMIT Campus Voice Assistant

A small website where an NMAMIT student signs in with their college Google account, passes a Face ID style face scan, asks a question out loud and hears the answer. Students can also see their own marks and attendance. Answers come only from the information admins and permitted teachers add in the admin panel. This approach is called RAG (retrieval-augmented generation).

**Quick tour (40 seconds, light theme):** [docs/demo-tour.mp4](docs/demo-tour.mp4). It shows sign-in, the face scan, the assistant, notes, events, marks, attendance, the robot's moods and sleep, and the admin and teacher tools. The demo used a test camera and a stand-in for the language model; search, permissions and everything on the pages are the real app.

**How offline mode works (50 seconds):** [docs/offline-mode-explained.mp4](docs/offline-mode-explained.mp4). Each laptop is its own campus server with a local database and local AI models. With internet, the cloud database is the source of truth and the laptops sync with it. Without internet, each laptop keeps working alone and catches up later. (The animation's source is [docs/offline-explainer.html](docs/offline-explainer.html).)

```
Student                        Server                                   Admin
───────                        ──────                                   ─────
Google sign-in (@nmamit.in) ─► Firebase token checked; must be a verified nmamit.in email
Webcam scan (3 fresh photos) ► OpenCV compares them with the face enrolled at first sign-in
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
| `app/main.py` | Pages, Google sign-in (Firebase), face enrol and verify endpoints, `/api/ask` |
| `app/auth.py` | Who is allowed in, roles and permissions, plus lockout and rate limits |
| `app/face.py`, `app/facelogin.py` | Face check with OpenCV (YuNet finds the face, SFace compares faces); enrolment and per-sign-in checks |
| `app/library.py` | Notes (PDF or pasted text, semesters 1-8) and events, and making them searchable by the assistant |
| `app/portal.py`, `app/academics.py` | Marks and attendance pages and APIs, the subjects, grades and sample data |
| `app/rag.py` | Splitting text into chunks, the vector database, the Groq call |
| `app/ingest.py` | Reading CSV files and text in images (RapidOCR) |
| `app/admin.py` | Admin API: knowledge entries, staff and their permissions, face resets |
| `app/db.py` | SQLite tables (knowledge, faces, roles, students, marks, attendance) |
| `app/pages/`, `app/static/` | Plain HTML, CSS and JavaScript (no framework) |
| `offline_app/`, `start_offline.bat` | The offline version: see [Offline version](#offline-version-no-internet-needed) |
| `start.bat` | One double-click: installs, checks settings, sets up once, starts the app |
| `scripts/` | Settings check, one-time model download, recording the demo video |
| `sample_data/` | Example CSVs to try the admin import |
| `tests/` | `pytest` tests |

## Quick start (Windows)

You need **Python 3.10 or newer** (tick *Add python.exe to PATH* when installing) and **Chrome or Edge**.

1. Get the four settings below and put them in a file called `.env` in this folder. If there is no `.env` yet, `start.bat` creates one and opens it in Notepad for you.
2. **Double-click `start.bat`.**

The first run installs everything and downloads the models (5-10 minutes). After that it starts in seconds and opens **http://localhost:8000**. Keep the black window open while using the app; close it to stop the app.

Then try it: sign in, set up your face (six guided photos, first time only), click **Admin**, **Import CSV** → `sample_data/sample_knowledge.csv`, go back, tap the microphone and ask "When is the library open?"

## Offline version (no internet needed)

`offline_app/` is the same assistant running entirely on one Windows laptop. Phones on the same Wi-Fi use it through their browser.

| Step | Online version | Offline version |
|---|---|---|
| Sign in | Google account + face scan | Roll number + face scan (OpenCV, on the laptop) |
| Speech to text | Browser (Google servers) | faster-whisper, on the laptop |
| Answer | Groq | Small local model through [Ollama](https://ollama.com) (`qwen2.5:1.5b`). Groq is used only if Ollama is not running and there is internet |
| Text to speech | Browser | Piper, on the laptop |
| Data | `data/app.db` | The same `data/app.db`, synced with the Turso backend whenever there is internet |

**Start it:** double-click **`start_offline.bat`**. The first run needs internet. It installs Ollama and the packages, then downloads the models (about 2 GB). This takes 10-20 minutes. After that it works with Wi-Fi off and opens **http://localhost:8100**.

**Face sign-in:** the student types their roll number and looks at the camera. The first time, the app takes six guided photos (look straight, left, right, up, down, smile) and keeps their face signatures. Every later sign-in takes fresh photos and compares them, like Face ID. There is no college photo any more. Because nothing proves who a first-time student is on the offline version, the first person to enrol a roll number owns it until an admin resets it in **Admin → Students & faces**. Students enrolled on the online version are already known and cannot be re-enrolled.

**Phones:** on the laptop, click **Connect a phone** and scan the QR code with a phone on the same Wi-Fi or hotspot. The phone warns that the connection is not private, because the laptop made its own certificate (phones only allow the camera and microphone on `https`). Tap **Advanced → Proceed**. The first time the app starts, Windows asks whether Python may use the network. Allow it on private networks.

**Sync:** set `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` in `.env`. Every change (knowledge entries, faces, staff roles, students, marks and attendance) is saved on the laptop first, then sent to Turso every minute when online. Changes from other laptops come back the same way, and the newer edit wins. The button at the top of the assistant shows the state (Synced / Offline / items still to send) and syncs now when clicked. On Turso the tables are `nva_modules`, `nva_faces`, `nva_roles`, `nva_profiles`, `nva_marks` and `nva_attendance`, so they don't touch other tables in the same database. (`nva_first_faces` from older versions is no longer used and can be dropped.)

**Tuning:** `OLLAMA_MODEL` (for example `qwen2.5:3b` for better answers, slower) and `WHISPER_MODEL` (`tiny.en`, `base.en`, `small.en`). After changing `OLLAMA_MODEL`, run `ollama pull <name>`. Run it by hand with `python -m offline_app.setup` once, then `python -m offline_app`.

## The settings (`.env`)

`start.bat` checks these every time and tells you exactly what is missing. It also creates a strong `SECRET_KEY` by itself.

| Setting | Where to get it |
|---|---|
| `FIREBASE_API_KEY`, `FIREBASE_PROJECT_ID` | Google sign-in runs through Firebase. On the [Firebase console](https://console.firebase.google.com/): **Create a project** (Analytics not needed). **Build → Authentication → Get started → Google → Enable → Save**. Then **Project settings → General → Your apps → Web (`</>`)**, register the app, and copy `apiKey` and `projectId` from the config shown. Use a *new* Firebase project: then any Google account can sign in with no extra Google Cloud setup, and `localhost` is already allowed. |
| `GROQ_API_KEY` | [console.groq.com/keys](https://console.groq.com/keys). `GROQ_MODEL` picks the model; if Groq retires it, choose a current one from [their models page](https://console.groq.com/docs/models). |
| `ADMIN_EMAILS` | Your college email. Separate several admins with commas. |

Always open the app as `http://localhost:8000`, not `127.0.0.1`: Firebase only allows sign-in from addresses on its list, and `localhost` is on it by default.

## Faces, like Face ID

- **First sign-in:** after Google sign-in (online) or the roll number (offline), the page takes **six photos** while the person follows prompts: look straight, turn left, turn right, tilt up, tilt down, smile. It keeps one 128-number signature per photo. Photos are never stored. At least five must show one clear face and all must look like the same person.
- **Every sign-in after that:** three fresh photos are taken and compared with the enrolled signatures. At least two of the three must match. The college's ID photos are no longer downloaded or used.
- **Ten tries.** A failed scan costs one try (a frame with no face doesn't count). After `FACE_MAX_FAILURES` (default **10**) failures the account is locked for `FACE_LOCK_MINUTES`.
- **New look, new account, lost access:** an admin opens **Admin → Students & faces** and presses **Reset face**. The person enrols again at their next sign-in.
- Faces enrolled by an older version (a single college photo) count as not enrolled, so those students enrol once more.

## Roles and permissions

| Role | Can see | Can change |
|---|---|---|
| **Student** (everyone by default) | Their own marks and attendance, the assistant | Nothing |
| **Teacher** | Every student's marks and attendance, the knowledge entries | Only what an admin switched on for them: **content** (knowledge, notes and events), **attendance**, **marks** |
| **Admin** | Everything | Everything, including staff and face resets |

Addresses in `ADMIN_EMAILS` are admins and can't be changed from the website. Those admins add teachers (and more admins) in **Admin → Staff & access**, and switch each teacher's three permissions on or off. A change applies on the teacher's next click. An admin has to sign in with their own face first, like everyone else, so there is no command to run for the first admin.

## Theme and the robot

- **Light / dark:** the sun and moon button in the top bar (or in the corner on the sign-in pages) switches the theme. It remembers your choice; until you choose, it follows your device's setting.
- **The robot** (`app/static/js/robot.js`) has moods: it waves on arrival, leans in with glowing ears while you speak, looks up and shows thinking dots while it finds the answer, moves its mouth while talking, looks happy, sad, surprised or confused depending on the answer, and shows hearts if you thank it. Its eyes follow your pointer, it blinks, glances around and does small things by itself. After about 40 seconds with nobody around it gets drowsy, yawns and falls asleep (Zzz); any click, key press or mouse movement wakes it. Tapping it makes it wink. With the device set to reduce motion, it keeps the expressions but stops the idle movement.

## Notes and events

- **Notes:** semesters 1 to 8, each with three sample subjects. Under a subject, an admin (or a teacher with the **content** permission) adds notes either by **uploading a PDF** (up to 15 MB) or by **pasting text**. Students can open, download and read them, never change them.
- **Events:** admins and permitted teachers publish an event with a title, date, time, venue, details and an optional PDF (poster, schedule). Students see upcoming and past events.
- **The voice assistant knows them too.** The text of every note (pasted, or read out of the PDF) and every event is saved as a knowledge entry, so questions like "Explain round robin scheduling" or "What events are coming up?" are answered from them, with a link to the note or event under the answer. Deleting a note or event removes it from the assistant as well. A scanned PDF that is only pictures has no text; it is stored and shown with an "Assistant can't read this" tag.
- Notes and events don't have a Knowledge-tab entry: they are managed on their own pages. On the offline version they are kept on that laptop; only the searchable text is synced.

## Marks and attendance

Real results aren't available to this project, so when a student enrols they get **sample data**: random marks for semesters 1 to 5 (six subjects each, internal and external out of 50) and attendance for semester 6. The numbers are random but stable per student, and are meant to be corrected by a teacher or admin. Students see percentages, grades, a semester chart and how many classes they can still miss. Teachers and admins pick a student and edit the numbers inline if they have permission.

## Manual setup (macOS, Linux, or without start.bat)

```bash
python -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/check_setup.py          # creates .env and lists what to fill in
python scripts/setup_models.py         # models (once)
uvicorn app.main:app --port 8000
```

## Using the admin panel

- **Add / edit / delete** an entry: the change is applied to the vector database at once, so the next question uses it.
- **Import CSV**: a file with `title,content` columns gives one entry per row. Any other CSV also works (for example `sample_data/sample_timetable.csv`): each row becomes an entry like "Day: Monday. Time: 9:00 AM. Subject: …".
- **Read text from image**: upload a photo of a notice or timetable. The text is copied into the form so you can correct it before saving.
- **Rebuild search index**: rebuilds the vector database from the saved entries. Use it only if search ever seems out of sync.
- **Staff & access** (admins): add teachers or admins and switch their permissions.
- **Students & faces** (admins): see who has enrolled and reset a face.
- Teachers only see the parts an admin allowed; everything else is read-only.

## Settings you may want to tune (`.env`)

| Setting | Default | Meaning |
|---|---|---|
| `FACE_MATCH_THRESHOLD` | `0.363` | How similar a live photo must be to an enrolled one (0 to 1). Higher is stricter. |
| `FACE_MAX_FAILURES` / `FACE_LOCK_MINUTES` | `10` / `10` | Failed face scans before a temporary lock |
| `TOP_K` | `4` | How many pieces of knowledge are given to the AI per question |
| `MAX_DISTANCE` | `0.7` | How close a piece must be to the question to be used (0 = same meaning) |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | Which Groq model writes the answers |

## Putting it on a server

- **Camera and microphone only work over HTTPS** (or on localhost). Put it behind HTTPS.
- Set `BASE_URL=https://your-domain`, `HTTPS_ONLY=true` and a fixed `SECRET_KEY`. In Firebase, add `your-domain` under **Authentication → Settings → Authorized domains**.
- Run **one** worker: `uvicorn app.main:app --host 0.0.0.0 --port 8000`. ChromaDB here is a local folder and the lockout counters live in memory, so several worker processes would not see each other's changes.
- Keep the `data/` folder on a disk that survives restarts. It holds the database and the vector index.

## Demo video

`scripts/record_demo.py` (not yet updated for the new face enrolment and sign-in flow, so it needs changes before it works again) records a captioned walkthrough of the whole flow into `demo_video/` (not committed). It runs its own copy of the app with a temporary data folder, so your knowledge base is not changed. See `.claude/skills/demo-video/SKILL.md` for setup, options and what the video simulates (Google sign-in and the microphone).

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
- **No liveness check.** The scan takes fresh photos but can't tell a live face from a good printed photo or a phone screen held to the camera. Online, they would still need the student's Google account. The offline version relies on the face alone, so it is weaker. A blink or head-turn check is a possible upgrade.
- **Sample marks are not real.** Don't use this as the college's record of results until they are replaced with real data.
- **Voice input runs in the browser.** Chrome sends the audio to Google's speech service to turn it into text. Firefox has no voice input; the text box always works.
- **Answers only from the knowledge base.** The AI is told to answer only from the matched entries and to say when it doesn't know. Keep the entries accurate. The sample CSV entries are made up and marked "(sample)".
- **Lockouts reset on restart.** Lockout and rate-limit counters are kept in memory.

## Troubleshooting

| Problem | Fix |
|---|---|
| The page looks old, or a script crashes right after an update | Hard refresh once with Ctrl+Shift+R. The app now tells the browser to re-check its files every time. |
| `start.bat` closes straight away or says Python is missing | Install Python 3.10+ from python.org with *Add python.exe to PATH* ticked, then run `start.bat` again. |
| `start.bat` opens Notepad | A setting in `.env` is empty. The window lists which ones; fill them in, save, run `start.bat` again. |
| "Please use your @nmamit.in college Google account" with a college account | Pick the @nmamit.in account in the Google window, not a personal one. Check `ALLOWED_DOMAIN`. |
| Google window shows `auth/unauthorized-domain` | Open the app as `http://localhost:8000`. For any other address, add it in Firebase under **Authentication → Settings → Authorized domains**. |
| Nothing happens when clicking Sign in | The browser blocked the pop-up. Allow pop-ups for this site and try again. |
| "Google sign-in is not set up on this server yet" | `FIREBASE_API_KEY` or `FIREBASE_PROJECT_ID` is empty in `.env`. |
| "Take at least 5 photos" or "Photo 3: No face found" | Sit in good light with your whole face in the circle and only you in view, then try the set-up again. |
| "The photos don't all show the same person" | Only one person should be in front of the camera during set-up. |
| "Your face is already enrolled" | Ask an admin to press **Reset face** for you in **Admin → Students & faces**. |
| Face never matches | Sit in similar light to when you enrolled. Check the scores in the server log; an admin can reset your face to enrol again, or you can lower `FACE_MATCH_THRESHOLD` slightly. |
| A teacher can't edit marks | An admin must switch on **Edit marks** for them in **Admin → Staff & access**. |
| Every answer is "Sorry, something went wrong" | Check the server log. Usually `GROQ_API_KEY` is missing or `GROQ_MODEL` was retired. |
| Mic button does nothing | Use Chrome or Edge, allow microphone access, and open the site over HTTPS or localhost. |
