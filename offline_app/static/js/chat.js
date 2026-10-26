// Tap to speak, tap again to send. The recording goes to this laptop, which turns
// it into text, finds the answer with the local AI model and reads it aloud.

const MAX_SECONDS = 30;

let recorder = null;
let stopTimer = null;
let lastAnswer = '';
const player = new Audio();
player.addEventListener('play', () => setTalking(true));
player.addEventListener('ended', () => setTalking(false));
player.addEventListener('pause', () => setTalking(false));

// ---- Screens ----------------------------------------------------------------

function show(screen) {
  for (const id of ['idle', 'processing', 'answer']) $(id).hidden = id !== screen;
  mascot.classList.toggle('thinking', screen === 'processing');
  $('typeForm').hidden = screen === 'processing';
}

function setStep(name, state) {
  document.querySelector(`.steps li[data-step="${name}"]`).className = state || '';
}

function setRecording(on) {
  $('mic').classList.toggle('on', on);
  $('mic').setAttribute('aria-label', on ? 'Tap when you are done' : 'Tap to speak');
  $('micHint').textContent = on ? 'Listening… tap when you’re done' : 'Tap to speak';
}

function fail(message) {
  show('idle');
  showError(message);
}

// ---- Recording -----------------------------------------------------------------

async function startRecording() {
  stopSpeaking();
  hideError();
  show('idle');
  if (!navigator.mediaDevices || !window.MediaRecorder) {
    showError('Voice input needs Chrome, Edge or Safari on the https address. You can type your question below.');
    return;
  }
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (e) {
    console.error(e);
    showError('Microphone permission was blocked. Allow it in the address bar and try again.');
    return;
  }
  const chunks = [];
  recorder = new MediaRecorder(stream);
  recorder.ondataavailable = (event) => event.data.size && chunks.push(event.data);
  recorder.onstop = () => {
    stream.getTracks().forEach((t) => t.stop());
    clearTimeout(stopTimer);
    setRecording(false);
    recorder = null;
    if (chunks.length) transcribe(new Blob(chunks, { type: chunks[0].type }));
  };
  recorder.start();
  setRecording(true);
  $('live').textContent = '';
  stopTimer = setTimeout(stopRecording, MAX_SECONDS * 1000);
}

function stopRecording() {
  if (recorder && recorder.state !== 'inactive') recorder.stop();
}

async function transcribe(blob) {
  show('processing');
  $('pQuestion').textContent = '';
  setStep('heard', 'active');
  setStep('searching', '');
  setStep('thinking', '');
  const form = new FormData();
  form.append('file', blob, 'speech.' + (blob.type.includes('mp4') ? 'mp4' : 'webm'));
  let res;
  try {
    res = await fetch('/api/stt', { method: 'POST', body: form });
  } catch (e) {
    console.error(e);
    return fail('Could not reach the laptop. Check that you are on the same Wi-Fi.');
  }
  if (res.status === 401 || res.status === 403) return (location.href = '/');
  if (!res.ok) return fail(await errorText(res));
  ask((await res.json()).text);
}

// ---- Speaking ------------------------------------------------------------------

async function speak(text) {
  stopSpeaking();
  try {
    const res = await fetch('/api/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) throw new Error(await errorText(res));
    player.src = URL.createObjectURL(await res.blob());
    await player.play();
  } catch (e) {
    // The laptop's voice is not available: use the browser's own voice instead.
    console.warn('Using the browser voice:', e);
    if (!('speechSynthesis' in window)) return;
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.onstart = () => setTalking(true);
    utterance.onend = utterance.onerror = () => setTalking(false);
    speechSynthesis.speak(utterance);
  }
}

function stopSpeaking() {
  player.pause();
  if ('speechSynthesis' in window) speechSynthesis.cancel();
  setTalking(false);
}

// ---- Asking ----------------------------------------------------------------------

function showAnswer(question, answer, sources, links = []) {
  lastAnswer = answer;
  $('aQuestion').textContent = `“${question}”`;
  $('aText').textContent = answer;
  $('aSources').textContent = sources && sources.length ? 'From: ' + sources.join(', ') : '';
  $('aLinks').replaceChildren(...links.map((l) =>
    el('a', { className: 'chip link', href: l.url }, icon(l.label === 'Event' ? 'events' : 'notes'), `${l.label}: ${l.title.replace(/^(Notes|Event): /, '')}`)));
  show('answer');
  speak(answer);
}

async function ask(question) {
  hideError();
  show('processing');
  $('pQuestion').textContent = `“${question}”`;
  setStep('heard', 'done');
  setStep('searching', 'active');
  setStep('thinking', '');

  let res;
  try {
    res = await fetch('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    });
  } catch (e) {
    console.error(e);
    return fail('Could not reach the laptop. Check that you are on the same Wi-Fi.');
  }
  if (res.status === 401 || res.status === 403) return (location.href = '/');
  if (!res.ok) return fail(await errorText(res));

  let finished = false;
  try {
    await readLines(res, (msg) => {
      if (msg.stage === 'thinking') {
        setStep('searching', 'done');
        setStep('thinking', 'active');
      } else if (msg.stage === 'done') {
        finished = true;
        showAnswer(question, msg.answer, msg.sources, msg.links);
      } else if (msg.stage === 'error') {
        finished = true;
        fail(msg.message);
      }
    });
  } catch (e) {
    console.error(e);
  }
  if (!finished) fail('The answer was cut off. Please try again.');
}

// ---- Sync status -----------------------------------------------------------------

const SYNC_TEXT = {
  off: 'Offline only',
  waiting: 'Sync starting…',
  syncing: 'Syncing…',
  synced: 'Synced',
  offline: 'Offline',
  error: 'Sync problem',
};

function showSync(s) {
  if (!$('sync')) return;
  const pending = s.pending && s.state !== 'off' ? ` (${s.pending} to send)` : '';
  $('sync').textContent = (SYNC_TEXT[s.state] || s.state) + pending;
  $('sync').title = s.message || (s.last_sync ? `Last synced ${new Date(s.last_sync).toLocaleString()}` : '');
}

async function refreshSync(method = 'GET') {
  try {
    const res = await fetch('/api/sync', { method });
    if (res.ok) showSync(await res.json());
  } catch (e) {
    if ($('sync')) $('sync').textContent = 'Laptop unreachable';
  }
}

// ---- Wiring -----------------------------------------------------------------------

$('mic').addEventListener('click', () => (recorder ? stopRecording() : startRecording()));
$('again').addEventListener('click', startRecording);
$('replay').addEventListener('click', () => speak(lastAnswer));
$('stop').addEventListener('click', stopSpeaking);
for (const chip of document.querySelectorAll('[data-q]')) {
  chip.addEventListener('click', () => {
    stopSpeaking();
    ask(chip.dataset.q);
  });
}
$('typeForm').addEventListener('submit', (event) => {
  event.preventDefault();
  const question = $('typeInput').value.trim();
  if (!question) return;
  $('typeInput').value = '';
  stopSpeaking();
  ask(question);
});

const mascot = robot();
$('robotSlot').append(mascot);

function setTalking(on) {
  mascot.classList.toggle('talking', on);
}

loadMe()
  .then((me) => {
    renderBar('/', me, [
      el('button', { id: 'sync', className: 'btn small', title: 'Sync with the college backend now' }, 'Sync…'),
      el('a', { className: 'btn small ghost', href: '/connect', title: 'Connect a phone' }, 'Phone'),
    ]);
    $('sync').addEventListener('click', () => refreshSync('POST'));
    refreshSync();
    $('hello').textContent = `${greeting()}, ${me.name}!`;
    if (me.role !== 'student' && me.entries === 0) {
      showError('No college information has been added yet, so the assistant can’t answer anything. Add some on the Admin page.');
    }
  })
  .catch((e) => console.error('Could not load profile', e));

setInterval(refreshSync, 15000);
