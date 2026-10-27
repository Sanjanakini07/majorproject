// Offline Face sign-in and registration.
//
// 1. Sign In (registered users):
//    Enter roll number -> instant camera scan (3 frames) -> verified against SQLite 'faces' table -> logged in.
//
// 2. Register (first time):
//    Enter roll number + full name -> 6 guided photos (looking center, left, right, up, down)
//    -> saved into SQLite 'faces' table & profile updated -> logged in.

let roll = '';
let studentName = '';
let enrolled = false;
let mode = 'signin'; // 'signin' | 'register'

const go = $('go');
const mascot = createRobot();
document.getElementById('art').prepend(mascot.el);
setTimeout(() => mascot.greet(), 400);

function setMode(newMode) {
  mode = newMode;
  $('tabSignin').classList.toggle('active', mode === 'signin');
  $('tabSignin').setAttribute('aria-selected', mode === 'signin');
  $('tabRegister').classList.toggle('active', mode === 'register');
  $('tabRegister').setAttribute('aria-selected', mode === 'register');

  $('nameWrap').hidden = mode !== 'register';
  $('title').textContent = mode === 'register' ? 'Register New User' : 'Sign in';
  $('lead').textContent = mode === 'register'
    ? 'First time here? Enter your details to scan and save your face offline.'
    : 'Enter your roll number, then verify with your face.';
  $('next').textContent = mode === 'register' ? 'Set up Face Scan' : 'Continue';
  $('modeHint').textContent = mode === 'register'
    ? 'Already registered? Click Sign In above.'
    : 'New student or staff? Click Register above to enrol your face.';
  FaceCam.say('');
}

$('tabSignin').addEventListener('click', () => setMode('signin'));
$('tabRegister').addEventListener('click', () => setMode('register'));

async function scan() {
  go.hidden = true;
  const isEnrolling = mode === 'register' || !enrolled;
  const fields = { roll };
  if (isEnrolling && $('name').value.trim()) {
    fields.name = $('name').value.trim();
  }

  const ok = await FaceCam.attempt(isEnrolling ? 'enroll' : 'verify', '/api/login', fields);
  mascot.emote(ok ? 'excited' : 'sad', 2500);
  if (ok) {
    FaceCam.stop();
    setTimeout(() => { location.href = '/'; }, 850);
    return;
  }
  go.textContent = 'Try again';
  go.hidden = false;
}

function reset() {
  FaceCam.stop();
  FaceCam.state('');
  FaceCam.say('');
  FaceCam.instruct('');
  $('camera').hidden = true;
  $('authForm').hidden = false;
  $('authTabs').hidden = false;
  setMode(mode);
}

$('authForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  $('next').disabled = true;
  FaceCam.say('');

  roll = $('roll').value.trim();
  studentName = $('name').value.trim();

  if (!roll) {
    FaceCam.say('Please enter your roll number or USN.', 'error');
    $('next').disabled = false;
    return;
  }

  try {
    const form = new FormData();
    form.append('roll', roll);
    const res = await fetch('/api/login/status', { method: 'POST', body: form });
    if (!res.ok) {
      FaceCam.say(await errorText(res), 'error');
      return;
    }
    const data = await res.json();
    enrolled = Boolean(data.enrolled);

    if (mode === 'signin' && !enrolled) {
      // Intelligently switch to registration if not enrolled
      setMode('register');
      FaceCam.say('No face registered yet for this roll number. Please enter your name and register your face.', 'error');
      return;
    }

    if (mode === 'register' && enrolled) {
      // If already enrolled, switch to sign in
      setMode('signin');
      FaceCam.say(`Face already enrolled for ${data.name || roll}. Verifying your face...`);
    }
  } catch (e) {
    console.error(e);
    FaceCam.say('Could not reach the local assistant service.', 'error');
    return;
  } finally {
    $('next').disabled = false;
  }

  // Show camera scanner
  $('authTabs').hidden = true;
  $('authForm').hidden = true;
  $('camera').hidden = false;

  const isEnrolling = mode === 'register' || !enrolled;
  $('title').textContent = isEnrolling ? 'Set up face sign-in' : 'Look at the camera';
  $('lead').textContent = isEnrolling
    ? 'We’ll take six quick photos from slight angles to save your offline face signature.'
    : 'A quick scan, like Face ID.';
  $('tips').hidden = !isEnrolling;
  go.textContent = isEnrolling ? 'Start face registration' : 'Scan my face';
  FaceCam.setProgress(0, isEnrolling ? 6 : 3);

  if (!(await FaceCam.start())) return;

  if (!isEnrolling) {
    scan(); // Auto-start verification once camera is running
  } else {
    FaceCam.instruct('Ready when you are');
    go.hidden = false;
  }
});

go.addEventListener('click', scan);
$('back').addEventListener('click', reset);

// Initial mode setup
setMode('signin');
