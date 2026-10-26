// Tap to speak, tap again to send. The browser turns speech into text
// (Web Speech API), the server finds the answer, and the browser reads it aloud.

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const LANG = 'en-IN';

let recognition = null;
let listening = false;
let heard = '';
let lastAnswer = '';

// ---- Screens ----------------------------------------------------------------

function show(screen) {
  for (const id of ['idle', 'processing', 'answer']) $(id).hidden = id !== screen;
  $('typeForm').hidden = screen === 'processing';
}

function setStep(name, state) {
  const item = document.querySelector(`.steps li[data-step="${name}"]`);
  item.className = state || '';
}

function setListening(on) {
  listening = on;
  $('mic').classList.toggle('on', on);
  $('mic').setAttribute('aria-label', on ? 'Tap when you are done' : 'Tap to speak');
  $('micHint').textContent = on ? 'Listening… tap when you’re done' : 'Tap to speak';
}

// ---- Speech to text -----------------------------------------------------------

function startListening() {
  stopSpeaking();
  hideError();
  show('idle');
  if (!SpeechRecognition) {
    showError('Voice input works in Chrome or Edge. You can type your question below.');
    return;
  }

  heard = '';
  let finalText = '';
  $('live').textContent = '';

  recognition = new SpeechRecognition();
  recognition.lang = LANG;
  recognition.continuous = true;      // keep listening until the second tap
  recognition.interimResults = true;  // show words as they are spoken

  recognition.onresult = (event) => {
    let interim = '';
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const result = event.results[i];
      if (result.isFinal) finalText += result[0].transcript + ' ';
      else interim += result[0].transcript;
    }
    heard = (finalText + interim).trim();
    $('live').textContent = heard;
  };

  recognition.onerror = (event) => {
    if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
      showError('Microphone permission was blocked. Allow it in the address bar and try again.');
    } else if (event.error === 'no-speech') {
      showError('I didn’t hear anything. Tap the button and try again.');
    } else if (event.error !== 'aborted') {
      showError('Voice input stopped: ' + event.error);
    }
  };

  // Fires after the second tap (or if the browser stops listening by itself).
  recognition.onend = () => {
    setListening(false);
    recognition = null;
    const question = heard.trim();
    if (question) ask(question);
  };

  recognition.start();
  setListening(true);
}

function stopListening() {
  if (recognition) recognition.stop();
}

// ---- Text to speech -----------------------------------------------------------

function speak(text) {
  if (!('speechSynthesis' in window)) return;
  speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = LANG;
  const voices = speechSynthesis.getVoices();
  const voice = voices.find((v) => v.lang === LANG) || voices.find((v) => v.lang.startsWith('en'));
  if (voice) utterance.voice = voice;
  speechSynthesis.speak(utterance);
}

function stopSpeaking() {
  if ('speechSynthesis' in window) speechSynthesis.cancel();
}

// ---- Asking the server -----------------------------------------------------------

function fail(message) {
  show('idle');
  showError(message);
}

function showAnswer(question, answer, sources) {
  lastAnswer = answer;
  $('aQuestion').textContent = `“${question}”`;
  $('aText').textContent = answer;
  $('aSources').textContent = sources && sources.length ? 'From: ' + sources.join(', ') : '';
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
    return fail('Could not reach the server. Check your connection.');
  }
  if (res.status === 401) return (location.href = '/');
  if (res.status === 403) return (location.href = '/face');
  if (!res.ok) return fail(await errorText(res));

  let finished = false;
  try {
    await readLines(res, (msg) => {
      if (msg.stage === 'thinking') {
        setStep('searching', 'done');
        setStep('thinking', 'active');
      } else if (msg.stage === 'done') {
        finished = true;
        showAnswer(question, msg.answer, msg.sources);
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

// ---- Wiring -----------------------------------------------------------------------

$('mic').addEventListener('click', () => (listening ? stopListening() : startListening()));
$('again').addEventListener('click', startListening);
$('replay').addEventListener('click', () => speak(lastAnswer));
$('stop').addEventListener('click', stopSpeaking);

$('typeForm').addEventListener('submit', (event) => {
  event.preventDefault();
  const question = $('typeInput').value.trim();
  if (!question) return;
  $('typeInput').value = '';
  stopSpeaking();
  ask(question);
});

// Some browsers load voices late; asking once makes them available for speak().
if ('speechSynthesis' in window) speechSynthesis.getVoices();

fetch('/api/me')
  .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
  .then((me) => {
    $('who').textContent = me.name;
    $('adminLink').hidden = !me.is_admin;
    if (me.is_admin && me.entries === 0) {
      showError('No college information has been added yet, so the assistant can’t answer anything. Add some on the Admin page.');
    }
  })
  .catch((e) => console.error('Could not load profile', e));
