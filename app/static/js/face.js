// Face check: show the webcam, send one frame to the server, which compares it
// with the photo the admin registered.

const video = $('video');
const button = $('verify');
const status = $('status');

function say(message, kind) {
  status.textContent = message;
  status.className = 'status' + (kind ? ' ' + kind : '');
}

async function startCamera() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    say('This browser cannot use the camera. Try Chrome or Edge.', 'error');
    return;
  }
  try {
    video.srcObject = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } },
      audio: false,
    });
    // Wait for the first frame, or the captured picture would be empty.
    if (video.readyState >= 2) button.disabled = false;
    else video.addEventListener('loadeddata', () => (button.disabled = false), { once: true });
  } catch (e) {
    console.error(e);
    say('Camera permission was blocked. Allow it in the address bar, then reload.', 'error');
  }
}

function captureFrame() {
  const canvas = document.createElement('canvas');
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext('2d').drawImage(video, 0, 0);
  return new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.92));
}

async function verify() {
  button.disabled = true;
  say('Checking…');
  try {
    const form = new FormData();
    form.append('file', await captureFrame(), 'face.jpg');
    const res = await fetch('/api/face/verify', { method: 'POST', body: form });
    if (res.ok) {
      say('Verified. Opening the assistant…', 'notice');
      location.href = '/';
      return;
    }
    if (res.status === 401) {
      location.href = '/'; // signed out (session expired)
      return;
    }
    say(await errorText(res), 'error');
  } catch (e) {
    console.error(e);
    say('Could not reach the server. Check your connection.', 'error');
  }
  button.disabled = false;
}

// Check the student has a registered photo before asking for the camera.
async function start() {
  try {
    const res = await fetch('/api/me');
    if (res.status === 401) {
      location.href = '/';
      return;
    }
    const me = await res.json();
    if (!me.face_enrolled) {
      say('Your face is not registered yet. Ask an admin to add your photo, then sign in again.', 'error');
      return;
    }
  } catch (e) {
    console.error(e); // the server check on Verify still applies
  }
  startCamera();
}

button.addEventListener('click', verify);
start();
