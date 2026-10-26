// Face ID style camera for the sign-in pages.
//
// enroll()  first time: six photos while the person follows the on-screen prompts
// verify()  every sign-in: three quick fresh photos
// The page needs: #video, #scanner, #instruction, #status, #dots (see face.html).

const ENROLL_STEPS = [
  'Look straight at the camera',
  'Turn your head slightly left',
  'Turn your head slightly right',
  'Tilt your chin up a little',
  'Tilt your chin down a little',
  'Look straight and smile',
];
const VERIFY_FRAMES = 3;
const MAX_WIDTH = 800;   // smaller pictures upload fast and are plenty for finding a face

const FaceCam = {
  video: null,

  say(message, kind) {
    $('status').textContent = message;
    $('status').className = 'status' + (kind ? ' ' + kind : '');
  },

  instruct(text) {
    $('instruction').textContent = text;
  },

  setProgress(done, total) {
    $('scanner').style.setProperty('--p', Math.round((done / total) * 100));
    const dots = $('dots');
    dots.replaceChildren(...Array.from({ length: total }, (_, i) => el('i', { className: i < done ? 'on' : '' })));
  },

  state(name) {
    // working | bad | done | '' (idle)
    $('scanner').classList.remove('working', 'bad', 'done');
    if (name) $('scanner').classList.add(name);
  },

  async start() {
    this.video = $('video');
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      this.say(location.protocol === 'http:' && location.hostname !== 'localhost'
        ? 'The camera needs the https address. Scan the QR code on the laptop again.'
        : 'This browser cannot use the camera. Try Chrome, Edge or Safari.', 'error');
      return false;
    }
    try {
      this.video.srcObject = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
      await new Promise((resolve) => {
        if (this.video.readyState >= 2) resolve();
        else this.video.addEventListener('loadeddata', resolve, { once: true });
      });
      return true;
    } catch (e) {
      console.error(e);
      this.say('Camera permission was blocked. Allow it in the address bar, then reload.', 'error');
      return false;
    }
  },

  stop() {
    if (this.video && this.video.srcObject) this.video.srcObject.getTracks().forEach((t) => t.stop());
  },

  frame() {
    const scale = Math.min(1, MAX_WIDTH / this.video.videoWidth);
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(this.video.videoWidth * scale);
    canvas.height = Math.round(this.video.videoHeight * scale);
    canvas.getContext('2d').drawImage(this.video, 0, 0, canvas.width, canvas.height);
    return new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.9));
  },

  wait(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  },

  async enroll() {
    const photos = [];
    this.state('working');
    this.setProgress(0, ENROLL_STEPS.length);
    for (const step of ENROLL_STEPS) {
      this.instruct(step);
      this.say('Get ready…');
      await this.wait(1800);   // time to move
      photos.push(await this.frame());
      this.setProgress(photos.length, ENROLL_STEPS.length);
      this.say('Got it');
      await this.wait(350);
    }
    return photos;
  },

  async verify() {
    const photos = [];
    this.state('working');
    this.setProgress(0, VERIFY_FRAMES);
    this.instruct('Look at the camera');
    this.say('Scanning…');
    await this.wait(700);
    for (let i = 0; i < VERIFY_FRAMES; i++) {
      photos.push(await this.frame());
      this.setProgress(photos.length, VERIFY_FRAMES);
      await this.wait(350);
    }
    return photos;
  },

  // One whole attempt: take the photos, send them, show the result. Returns true on success.
  async attempt(mode, url, fields = {}) {
    const enrolling = mode === 'enroll';
    const photos = enrolling ? await this.enroll() : await this.verify();
    this.instruct('Checking…');
    this.say('');
    let res;
    try {
      res = await this.send(url, photos, fields);
    } catch (e) {
      console.error(e);
      this.state('bad');
      this.instruct('Could not reach the server');
      this.say('Check your connection and try again.', 'error');
      return false;
    }
    if (res.ok) {
      this.state('done');
      this.instruct(enrolling ? 'Face sign-in is ready' : 'Welcome back');
      this.say('');
      return true;
    }
    if (res.status === 401) {
      location.href = '/';
      return false;
    }
    this.state('bad');
    this.setProgress(0, enrolling ? ENROLL_STEPS.length : VERIFY_FRAMES);
    this.instruct(enrolling ? 'Let’s try that again' : 'That didn’t match');
    this.say(await errorText(res), 'error');
    return false;
  },

  // POST the photos as repeated "files" fields (plus any extra form fields). Returns the Response.
  send(url, photos, fields = {}) {
    const form = new FormData();
    for (const [k, v] of Object.entries(fields)) form.append(k, v);
    photos.forEach((blob, i) => form.append('files', blob, `face${i + 1}.jpg`));
    return fetch(url, { method: 'POST', body: form });
  },
};
