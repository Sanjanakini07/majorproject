// Face check after Google sign-in.
// First time: enrol six photos. Every later sign-in: a fresh scan that must match.

const go = $('go');
let mode = 'verify';

async function scan() {
  go.hidden = true;
  const ok = await FaceCam.attempt(mode, mode === 'enroll' ? '/api/face/enroll' : '/api/face/verify');
  if (ok) {
    FaceCam.stop();
    setTimeout(() => (location.href = '/'), 900);
    return;
  }
  go.textContent = 'Try again';
  go.hidden = false;
}

async function start() {
  let me;
  try {
    me = await loadMe();
  } catch (e) {
    console.error(e);
    FaceCam.say('Could not reach the server. Check your connection.', 'error');
    return;
  }
  if (me.face_ok) {
    location.href = '/';
    return;
  }
  mode = me.face_enrolled ? 'verify' : 'enroll';
  const first = mode === 'enroll';
  $('title').textContent = first ? 'Set up face sign-in' : 'Face check';
  $('lead').textContent = first
    ? `Hi ${me.name.split(' ')[0]}! We'll take six quick photos so we can recognise you next time.`
    : 'Look at the camera. It only takes a moment.';
  $('tips').hidden = !first;
  go.textContent = first ? 'Start scan' : 'Scan my face';
  go.addEventListener('click', scan);

  if (!(await FaceCam.start())) return;
  if (first) {
    FaceCam.instruct('Ready when you are');
    go.hidden = false;
  } else {
    scan();   // like Face ID: it starts looking as soon as the camera is on
  }
}

start();
