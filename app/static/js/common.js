// Small helpers shared by every page.

const $ = (id) => document.getElementById(id);

function showError(message) {
  const box = $('error');
  box.textContent = message;
  box.hidden = false;
}

function hideError() {
  $('error').hidden = true;
}

// Turn a failed response into a readable message.
// FastAPI sends {"detail": "text"} or, for invalid input, {"detail": [{"msg": ...}]}.
async function errorText(res) {
  try {
    const body = await res.json();
    if (typeof body.detail === 'string') return body.detail;
    if (Array.isArray(body.detail) && body.detail[0]) return body.detail[0].msg;
  } catch (e) {
    console.error(e);
  }
  return `Something went wrong (error ${res.status}).`;
}

// Read a response that sends one JSON object per line, calling onMessage for each.
async function readLines(res, onMessage) {
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let newline;
    while ((newline = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, newline).trim();
      buffer = buffer.slice(newline + 1);
      if (line) onMessage(JSON.parse(line));
    }
  }
}

// Build an element safely: text always goes in as text, never as HTML.
function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else if (key === 'className') node.className = value;
    else node.setAttribute(key, value);
  }
  for (const child of children) {
    if (child != null) node.append(child);
  }
  return node;
}

// ---- Signed-in pages: top bar, profile, messages -------------------------------------

const LINKS = [
  { href: '/', label: 'Assistant' },
  { href: '/marks', label: 'Marks' },
  { href: '/attendance', label: 'Attendance' },
  { href: '/admin', label: 'Admin', staff: true },
];

async function loadMe() {
  const res = await fetch('/api/me');
  if (res.status === 401) {
    location.href = '/';
    return new Promise(() => {});
  }
  return res.json();
}

// Fill <header id="bar"> with the logo, links for this person's role, and sign out.
// `extra` is a list of nodes (for example the offline sync button) shown before the name.
function renderBar(active, me, extra = []) {
  const bar = $('bar');
  const initials = me.name.split(/[\s@._-]+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase();
  bar.replaceChildren(
    el('a', { className: 'brand', href: '/' }, el('span', { className: 'brand-mark' }, 'N'), 'NMAMIT Assistant'),
    el('nav', { className: 'nav' },
      ...LINKS.filter((l) => !l.staff || me.role !== 'student')
        .map((l) => el('a', { href: l.href, className: l.href === active ? 'active' : '' }, l.label))),
    el('div', { className: 'bar-right' },
      ...extra,
      el('span', { className: 'who' },
        el('span', { className: 'avatar' }, initials || '?'),
        el('span', { className: 'name' }, me.name),
        el('span', { className: `badge ${me.role}` }, me.role)),
      el('a', { className: 'btn small ghost', href: '/logout' }, 'Sign out')),
  );
}

let toastTimer = null;
function toast(message, kind = '') {
  document.querySelectorAll('.toast').forEach((t) => t.remove());
  const node = el('div', { className: 'toast ' + kind, role: 'status' }, message);
  document.body.append(node);
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.remove(), 3200);
}

// JSON request that throws an Error with a readable message on failure.
async function api(method, url, body) {
  const options = { method };
  if (body instanceof FormData) options.body = body;
  else if (body !== undefined) {
    options.headers = { 'Content-Type': 'application/json' };
    options.body = JSON.stringify(body);
  }
  const res = await fetch(url, options);
  if (res.status === 401) location.href = '/';
  if (!res.ok) throw new Error(await errorText(res));
  return res.status === 204 ? null : res.json();
}

// ---- Student picker (teachers and admins choose whose records to see) ---------------

async function studentPicker(box, onPick) {
  const students = await api('GET', '/api/students');
  const select = el('select', { 'aria-label': 'Student' });
  const search = el('input', { type: 'search', placeholder: 'Search roll number or name', 'aria-label': 'Search students' });
  const fill = () => {
    const q = search.value.trim().toLowerCase();
    const shown = students.filter((s) => s.email.includes(q) || (s.name || '').toLowerCase().includes(q));
    select.replaceChildren(...shown.map((s) => el('option', { value: s.email }, `${(s.name || s.email.split('@')[0]).toUpperCase()}  ·  ${s.email}`)));
    if (shown.length) onPick(select.value);
    else onPick(null);
  };
  search.addEventListener('input', fill);
  select.addEventListener('change', () => onPick(select.value));
  box.replaceChildren(el('div', { className: 'picker' }, search, select));
  if (!students.length) box.append(el('p', { className: 'muted small' }, 'No students yet. They appear here after their first face sign-in.'));
  fill();
}

function gradeChip(grade) {
  const kind = grade === 'F' ? 'F' : ['C', 'B'].includes(grade) ? 'mid' : '';
  return el('span', { className: 'grade ' + kind }, grade);
}

// ---- The robot ----------------------------------------------------------------------

const ROBOT_SVG = `
<svg class="robot" viewBox="0 0 200 210" role="img" aria-label="Friendly robot assistant">
  <defs>
    <linearGradient id="rb-head" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#cfd6ec"/></linearGradient>
    <linearGradient id="rb-screen" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1a2552"/><stop offset="1" stop-color="#0c1230"/></linearGradient>
  </defs>
  <ellipse cx="100" cy="200" rx="52" ry="7" fill="rgba(0,0,0,.22)"/>
  <line x1="100" y1="34" x2="100" y2="52" stroke="#cfd6ec" stroke-width="5" stroke-linecap="round"/>
  <circle class="antenna-ball" cx="100" cy="28" r="9" fill="#f2b134"/>
  <rect x="14" y="98" width="16" height="42" rx="8" fill="#b01f3a"/>
  <rect x="170" y="98" width="16" height="42" rx="8" fill="#b01f3a"/>
  <rect x="28" y="50" width="144" height="124" rx="40" fill="url(#rb-head)"/>
  <rect x="42" y="64" width="116" height="94" rx="28" fill="url(#rb-screen)"/>
  <g class="pupils">
    <rect class="eye" x="64" y="88" width="22" height="30" rx="11" fill="#7ee0ff"/>
    <rect class="eye" x="114" y="88" width="22" height="30" rx="11" fill="#7ee0ff"/>
  </g>
  <circle cx="58" cy="132" r="7" fill="#f0627c" opacity=".55"/>
  <circle cx="142" cy="132" r="7" fill="#f0627c" opacity=".55"/>
  <path class="smile" d="M80 134 Q100 150 120 134" fill="none" stroke="#7ee0ff" stroke-width="6" stroke-linecap="round"/>
  <ellipse class="talk" cx="100" cy="140" rx="13" ry="9" fill="#7ee0ff"/>
</svg>`;

// Returns the robot as an element. Its eyes follow the pointer a little.
// robot.classList 'talking' moves the mouth, 'thinking' makes the eyes look around.
function robot() {
  const wrap = document.createElement('div');
  wrap.innerHTML = ROBOT_SVG;
  const svg = wrap.firstElementChild;
  const pupils = svg.querySelector('.pupils');
  document.addEventListener('pointermove', (e) => {
    const box = svg.getBoundingClientRect();
    const dx = (e.clientX - (box.left + box.width / 2)) / window.innerWidth;
    const dy = (e.clientY - (box.top + box.height / 2)) / window.innerHeight;
    pupils.style.transform = `translate(${(dx * 9).toFixed(1)}px, ${(dy * 7).toFixed(1)}px)`;
  });
  return svg;
}

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening';
}
