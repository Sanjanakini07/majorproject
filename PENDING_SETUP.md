# Offline app: what's left to do

Status on 2026-10-19. Delete this file once everything below is ticked.

## Already done and tested on this laptop

- `offline_app/` is written: face sign-in, offline voice, local AI through Ollama, sync with Turso, phone QR page. `start_offline.bat` starts it.
- Speech-to-text and voice models are downloaded into `models/` (faster-whisper `base.en`, Piper `en_US-lessac-medium`).
- `.env` has `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN`. The first sync worked. Faces, roles, students, marks and attendance now sync too (tables `nva_modules`, `nva_faces`, `nva_roles`, `nva_profiles`, `nva_marks`, `nva_attendance`). The old college-photo faces on Turso are ignored: those students enrol again.
- Over HTTPS, the way a phone connects, these all work:
  - sign-in: the face is enrolled with six photos at first sign-in, then recognised from fresh photos each time, and a wrong face is rejected
  - voice in and voice out
  - asking a question (answered by Groq for now, because Ollama is missing)
  - sync status
- Tests pass (`.venv\Scripts\python -m pytest -q`).

## Still to do (at home, with good internet)

1. **Install Ollama.** Either:
   - double-click `start_offline.bat`, which installs it with winget, or
   - download it from https://ollama.com/download (1.5 GB) and install it.

   The download here kept failing because the connection reset partway.
2. **Double-click `start_offline.bat`.** It downloads the AI model `qwen2.5:1.5b` (about 1 GB) and skips everything already downloaded. Then it opens http://localhost:8100.
3. **Check a real offline answer.** Turn Wi-Fi off, sign in with your face (roll number NNM23IS186; the first time you enrol six photos) and ask a question. Note how many seconds the answer takes. If it's too slow, set `OLLAMA_MODEL=qwen2.5:0.5b` in `.env`. If the answers are weak, try `qwen2.5:3b`. After changing it, run `ollama pull <name>`.
4. **Test a phone.** Put the phone on the same Wi-Fi or hotspot. On the laptop, click **Connect a phone**, scan the QR code and tap **Advanced → Proceed**. Then check the camera sign-in and the microphone. If Windows asks about the firewall, allow Python on private networks.
5. **Rotate the Turso token.** It was pasted into a chat. In the Turso dashboard, create a new token and put it in `.env` as `TURSO_AUTH_TOKEN`.

## To continue with Claude in a new session, paste this

> Read PENDING_SETUP.md and README.md ("Offline version"). Help me finish the steps that are left: check Ollama is installed and the model is pulled, run start_offline.bat, test a local answer and tell me how long it takes, then commit the offline app.

## If something goes wrong

- **"Ollama is not running":** open Ollama from the Start menu, or run `"%LOCALAPPDATA%\Programs\Ollama\ollama.exe" serve`.
- **"model ... is not downloaded":** run `ollama pull qwen2.5:1.5b`.
- **Setup stopped halfway:** delete `data\offline-setup-done` if it exists, then double-click `start_offline.bat` again.
- **The phone can't open the page:** the laptop and phone must be on the same network. The QR code shows the laptop's Wi-Fi address. Restart the app after changing networks.
