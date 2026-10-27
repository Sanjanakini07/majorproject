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

const ICONS = {
  chat: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
  marks: '<path d="M18 20V10M12 20V4M6 20v-6"/>',
  attendance: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18M9 16l2 2 4-4"/>',
  notes: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V2H6.5A2.5 2.5 0 0 0 4 4.5z"/><path d="M20 17v5H6.5A2.5 2.5 0 0 1 4 19.5"/>',
  events: '<path d="M12 2l2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 16.8 6.1 20l1.2-6.5L2.5 8.9 9.1 8z"/>',
  admin: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
  pdf: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>',
  text: '<path d="M4 6h16M4 12h16M4 18h10"/>',
  pin: '<path d="M21 10c0 7-9 13-9 13S3 17 3 10a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>',
  clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
  upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>',
  trash: '<path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/>',
  eye: '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>',
  bus: '<rect x="4" y="3" width="16" height="15" rx="2"/><path d="M4 11h16M8 21v-3M16 21v-3"/><circle cx="8" cy="14.5" r="0.8"/><circle cx="16" cy="14.5" r="0.8"/>',
  chevron: '<path d="M6 9l6 6 6-6"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
};

// An inline icon (a fixed string from ICONS above, never user text).
function icon(name) {
  const wrap = document.createElement('span');
  wrap.className = 'icon';
  wrap.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name]}</svg>`;
  return wrap;
}

const LINKS = [
  { href: '/', label: 'Assistant', icon: 'chat' },
  { href: '/notes', label: 'Notes', icon: 'notes' },
  { href: '/events', label: 'Events', icon: 'events' },
  { href: '/bus', label: 'Bus', icon: 'bus' },
  { href: '/admin', label: 'Admin', icon: 'admin', staff: true },
];
// Tucked away behind the arrow at the end of the bar.
const MORE_LINKS = [
  { href: '/marks', label: 'Marks', icon: 'marks' },
  { href: '/attendance', label: 'Attendance', icon: 'attendance' },
];

// The arrow button and its little menu. The menu is fixed-positioned so the scrolling nav can't clip it.
function moreMenu(active) {
  const menu = el('div', { className: 'nav-menu', role: 'menu', hidden: '' },
    ...MORE_LINKS.map((l) => el('a', { href: l.href, role: 'menuitem', className: l.href === active ? 'active' : '' },
      icon(l.icon), el('span', {}, l.label))));
  const button = el('button', {
    type: 'button', className: 'nav-more' + (MORE_LINKS.some((l) => l.href === active) ? ' active' : ''),
    'aria-label': 'More: marks and attendance', 'aria-haspopup': 'menu', 'aria-expanded': 'false',
  }, icon('chevron'));
  const close = () => {
    menu.hidden = true;
    button.setAttribute('aria-expanded', 'false');
  };
  button.addEventListener('click', (event) => {
    event.stopPropagation();
    if (!menu.hidden) return close();
    menu.hidden = false;
    button.setAttribute('aria-expanded', 'true');
    const r = button.getBoundingClientRect();
    const bottomBar = r.top > innerHeight / 2;          // on phones the nav sits at the bottom: open upwards
    menu.style.left = `${Math.max(8, Math.min(r.right - menu.offsetWidth, innerWidth - menu.offsetWidth - 8))}px`;
    menu.style.top = bottomBar ? `${r.top - menu.offsetHeight - 8}px` : `${r.bottom + 8}px`;
  });
  document.addEventListener('click', (event) => { if (!menu.contains(event.target)) close(); });
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape') close(); });
  addEventListener('resize', close);
  document.body.append(menu);
  return button;
}

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
        .map((l) => el('a', { href: l.href, className: l.href === active ? 'active' : '' }, icon(l.icon), el('span', { className: 'label' }, l.label))),
      moreMenu(active)),
    el('div', { className: 'bar-right' },
      ...extra,
      el('span', { className: 'who' },
        el('span', { className: 'avatar' }, initials || '?'),
        el('span', { className: 'name' }, me.name),
        el('span', { className: `badge ${me.role}` }, me.role)),
      Theme.button(),
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

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening';
}
