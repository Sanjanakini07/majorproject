// Face sign-in: type the roll number, look at the camera, and one frame goes to
// this laptop, which compares it with the college photo and the first sign-in photo.

const video = $('video');
const button = $('signin');
const status = $('status');

function say(message, kind) {
  status.textContent = message;
  status.className = 'status' + (kind ? ' ' + kind : '');
}

async function startCamera() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    say(location.protocol === 'http:' && location.hostname !== 'localhost'
      ? 'The camera needs the https address. Scan the QR code on the laptop again.'
      : 'This browser cannot use the camera. Try Chrome, Edge or Safari.', 'error');
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

$('form').addEventListener('submit', async (event) => {
  event.preventDefault();
  button.disabled = true;
  say('Checking your face…');
  try {
    const form = new FormData();
    form.append('roll', $('roll').value);
    form.append('file', await captureFrame(), 'face.jpg');
    const res = await fetch('/api/login', { method: 'POST', body: form });
    if (res.ok) {
      const result = await res.json();
      say(result.first_photo_saved
        ? 'Welcome! This first photo is now saved and will be used to recognise you next time.'
        : 'Recognised. Opening the assistant…', 'notice');
      setTimeout(() => location.reload(), result.first_photo_saved ? 2500 : 300);
      return;
    }
    say(await errorText(res), 'error');
  } catch (e) {
    console.error(e);
    say('Could not reach the laptop. Check that you are on the same Wi-Fi.', 'error');
  }
  button.disabled = false;
});

startCamera();
