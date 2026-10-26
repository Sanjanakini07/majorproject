// Google sign-in through Firebase: Google's sign-in window opens, then the
// server checks the result and starts the app's own session.
import { initializeApp } from 'https://www.gstatic.com/firebasejs/12.4.0/firebase-app.js';
import {
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  signOut,
} from 'https://www.gstatic.com/firebasejs/12.4.0/firebase-auth.js';

const button = document.getElementById('signin');
const box = document.getElementById('error');

let auth = null;
let provider = null;

function showError(message) {
  box.textContent = message;
  box.hidden = false;
}

async function setup() {
  const res = await fetch('/api/firebase-config');
  if (!res.ok) {
    showError('Google sign-in is not set up on this server yet. See the README.');
    return;
  }
  const cfg = await res.json();
  auth = getAuth(initializeApp({ apiKey: cfg.apiKey, authDomain: cfg.authDomain, projectId: cfg.projectId }));
  provider = new GoogleAuthProvider();
  // Let Google show the account picker; the server still enforces the @nmamit.in-only policy.
  // Hard-forcing hd=... can randomly fail when the browser has no matching local account available.
  provider.setCustomParameters({ prompt: 'select_account' });
  button.disabled = false;
}

async function signIn() {
  box.hidden = true;
  button.disabled = true;
  try {
    const result = await signInWithPopup(auth, provider);
    const idToken = await result.user.getIdToken();
    const res = await fetch('/auth/session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id_token: idToken }),
    });
    await signOut(auth); // from here on the app's own session is used
    if (res.ok) {
      location.href = (await res.json()).next;
      return;
    }
    const body = await res.json().catch(() => ({}));
    showError(body.detail || 'Sign-in failed. Please try again.');
  } catch (e) {
    console.error(e);
    if (e.code === 'auth/popup-blocked') {
      showError('The browser blocked the Google window. Allow pop-ups for this site and try again.');
    } else if (e.code !== 'auth/popup-closed-by-user' && e.code !== 'auth/cancelled-popup-request') {
      showError('Google sign-in did not complete. Please try again.');
    }
  }
  button.disabled = false;
}

const mascot = createRobot();
document.getElementById('art').prepend(mascot.el);
setTimeout(() => mascot.greet(), 500);
button.addEventListener('click', signIn);
setup().catch((e) => {
  console.error(e);
  showError('Could not load Google sign-in. Check the internet connection and reload.');
});
