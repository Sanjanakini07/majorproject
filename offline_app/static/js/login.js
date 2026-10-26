// Face sign-in on the laptop. Type the roll number, then:
//   first time  -> six guided photos are enrolled (like setting up Face ID)
//   every time after -> a fresh scan is compared with the enrolled face

let roll = '';
let enrolled = false;

const go = $('go');
const mascot = createRobot();
document.getElementById('art').prepend(mascot.el);
setTimeout(() => mascot.greet(), 500);

async function scan() {
  go.hidden = true;
  const ok = await FaceCam.attempt(enrolled ? 'verify' : 'enroll', '/api/login', { roll });
  mascot.emote(ok ? 'excited' : 'sad', 2500);
  if (ok) {
    FaceCam.stop();
    setTimeout(() => location.reload(), 900);
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
  $('rollForm').hidden = false;
  $('title').textContent = 'Sign in';
  $('lead').textContent = 'Enter your roll number, then look at the camera.';
}

$('rollForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  $('next').disabled = true;
  FaceCam.say('');
  try {
    const form = new FormData();
    form.append('roll', $('roll').value);
    const res = await fetch('/api/login/status', { method: 'POST', body: form });
    if (!res.ok) {
      FaceCam.say(await errorText(res), 'error');
      return;
    }
    roll = $('roll').value;
    enrolled = (await res.json()).enrolled;
  } catch (e) {
    console.error(e);
    FaceCam.say('Could not reach the laptop. Check that you are on the same Wi-Fi.', 'error');
    return;
  } finally {
    $('next').disabled = false;
  }

  $('rollForm').hidden = true;
  $('camera').hidden = false;
  $('title').textContent = enrolled ? 'Look at the camera' : 'Set up face sign-in';
  $('lead').textContent = enrolled
    ? 'A quick scan, like Face ID.'
    : 'First time here. We’ll take six quick photos so we can recognise you next time.';
  $('tips').hidden = enrolled;
  go.textContent = enrolled ? 'Scan my face' : 'Start scan';
  FaceCam.setProgress(0, enrolled ? 3 : 6);

  if (!(await FaceCam.start())) return;
  if (enrolled) {
    scan();   // starts looking as soon as the camera is on
  } else {
    FaceCam.instruct('Ready when you are');
    go.hidden = false;
  }
});

go.addEventListener('click', scan);
$('back').addEventListener('click', reset);
