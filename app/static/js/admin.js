// Admin panel: knowledge, staff and what they may edit, and enrolled faces.
// What shows depends on the role: teachers see only what an admin allowed.

let me = null;
let modules = [];
let editingId = null;   // id of the entry being edited, or null when adding
let nextSource = 'manual';

const notify = (message) => {
  hideError();
  toast(message);
};

// Run an action, show its error inline instead of failing silently. Resolves to whether it worked.
async function attempt(action) {
  try {
    await action();
    return true;
  } catch (e) {
    console.error(e);
    showError(e.message);
    return false;
  }
}

// ---- Tabs -----------------------------------------------------------------------

for (const tab of document.querySelectorAll('.tab')) {
  tab.addEventListener('click', () => {
    for (const t of document.querySelectorAll('.tab')) t.classList.toggle('active', t === tab);
    for (const name of ['knowledge', 'staff', 'faces']) $('tab-' + name).hidden = tab.dataset.tab !== name;
    hideError();
  });
}

// ---- Knowledge ----------------------------------------------------------------
// One form for everything: pick what it is about, paste anything (or drop a file), optionally let the AI tidy
// it, save. The kind is kept as a title prefix ("Placement: ..."), which is also how the entries are grouped.

const KINDS = [
  { id: 'general', prefix: '', label: 'General info', hint: 'rules, timings, offices, fees',
    example: 'e.g.\nlibrary open 8am-8pm weekdays, sat till 1. return books in 14 days, fine 2rs/day' },
  { id: 'placement', prefix: 'Placement: ', label: 'Placements', hint: 'drives, tests, eligibility', sheet: 'placements',
    example: 'e.g.\ninfosys drive 18 nov amphitheatre 9am. 7th sem cse ise ece, 60% no backlogs. reg on portal by 15th' },
  { id: 'exam', prefix: 'Exam: ', label: 'Exams & timetables', hint: 'MSE, SEE, lab exams',
    example: 'e.g.\nMSE 2 7th sem ISE\n24/11 mon FM 10-11.30\n25/11 tue OOMD\n26/11 SDN   room 301 & 302' },
  { id: 'teacher', prefix: 'Teacher: ', label: 'Teachers & cabins', hint: 'cabin, subjects, contact', sheet: 'teachers',
    example: 'e.g.\nDr Ravi B - APJ 5th flr, slight left from lift. teaches DAA, DBMS 7A. free after 2' },
  { id: 'bus', prefix: 'Bus: ', label: 'College buses', hint: 'bus no., route, stops', sheet: 'college_buses',
    example: 'e.g.\nbus 4 udupi route: nitte 4.40pm > belman > shirva > katapadi > udupi 5.45' },
  { id: 'event', prefix: null, label: 'Events', hint: 'fests, workshops, talks' },
];
// Groups shown above the entries; seeded entries use these prefixes too.
const GROUPS = [
  ['placement', 'Placements', 'Placement: '], ['exam', 'Exams', 'Exam: '], ['teacher', 'Teachers', 'Teacher: '],
  ['bus', 'Bus', 'Bus: '], ['timetable', 'Class timetables', 'Timetable: '], ['rules', 'Regulations', 'Regulations: '],
  ['syllabus', 'Other departments’ courses', 'Syllabus: '],
];
let kind = KINDS[0];
let group = 'all';
let beforeTidy = null;   // the text before the AI tidied it, for "Undo tidy-up"

const groupOf = (title) => (GROUPS.find(([, , prefix]) => title.startsWith(prefix)) || ['general'])[0];
const kindOf = (title) => KINDS.find((k) => k.prefix && title.startsWith(k.prefix)) || KINDS[0];

let sheet = null;   // the open spreadsheet editor, if any

// Kinds with a list open it as a spreadsheet; asText shows the free-text form instead (editing an old note,
// or pasting a notice as it is).
function pickKind(k, asText = false) {
  if (sheet && sheet.isDirty() && !confirm('You have changes in the list that are not saved. Leave without saving?')) return;
  kind = k;
  for (const b of $('kinds').children) {
    b.classList.toggle('active', b.dataset.kind === k.id);
    b.setAttribute('aria-checked', String(b.dataset.kind === k.id));
  }
  const useSheet = Boolean(k.sheet) && !asText;
  $('eventNote').hidden = k.id !== 'event';
  $('entryFields').hidden = k.id === 'event' || useSheet;
  $('mContent').required = k.id !== 'event' && !useSheet;
  if (k.example) $('mContent').placeholder = k.example;
  $('sheetBox').hidden = !useSheet;
  sheet = null;
  if (useSheet) {
    const box = el('div');
    $('sheetBox').replaceChildren(el('p', { className: 'section-label' }, `2 · ${k.label}: fill in and save`), box,
      el('p', { className: 'muted small' }, 'Have a notice or message instead? ',
        el('a', { href: '#', onclick: (e) => { e.preventDefault(); pickKind(k, true); } }, 'Write it as a free-text note')));
    sheet = sheetEditor(box, k.sheet, true);
    attempt(sheet.load);
  }
}

window.addEventListener('beforeunload', (e) => {
  if (sheet && sheet.isDirty()) e.preventDefault();
});

$('kinds').append(...KINDS.map((k) => {
  const b = el('button', { type: 'button', className: 'pill-btn', role: 'radio', onclick: () => pickKind(k) },
    el('b', {}, k.label), el('span', {}, k.hint));
  b.dataset.kind = k.id;
  return b;
}));
$('dropIcon').append(icon('upload'));

function showTidied(on) {
  $('tidyNote').hidden = !on;
  if (!on) beforeTidy = null;
}

function resetForm() {
  editingId = null;
  nextSource = 'manual';
  $('moduleForm').reset();
  $('formTitle').textContent = 'Add information';
  $('mCancel').hidden = true;
  showTidied(false);
  // stay in the free-text form if that is what was open (after saving or cancelling a note)
  pickKind(kind.id === 'event' ? KINDS[0] : kind, Boolean(kind.sheet) && $('sheetBox').hidden);
}

function startEdit(module) {
  editingId = module.id;
  const k = kindOf(module.title);
  pickKind(k, true);   // an existing entry is free text, even in a kind that also has a list
  $('mTitle').value = module.title.slice(k.prefix.length);
  $('mContent').value = module.content;
  $('formTitle').textContent = 'Edit information';
  $('mCancel').hidden = false;
  showTidied(false);
  $('mContent').focus();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// A title when none was typed: the first line, cut at a word.
function autoTitle(text) {
  const line = text.trim().split('\n')[0].trim();
  return line.length <= 60 ? line : line.slice(0, 60).replace(/\s+\S*$/, '') + '…';
}

function renderGroups() {
  const counts = { all: modules.length };
  for (const m of modules) counts[groupOf(m.title)] = (counts[groupOf(m.title)] || 0) + 1;
  const all = [['all', 'All'], ['general', 'General'], ...GROUPS];
  $('groups').replaceChildren(...all.filter(([id]) => counts[id] || id === 'all').map(([id, label]) =>
    el('button', { type: 'button', className: 'chip' + (group === id ? ' on' : ''),
      onclick: () => { group = id; renderModules(); } }, `${label} (${counts[id] || 0})`)));
}

function renderModules() {
  renderGroups();
  const filter = $('filter').value.trim().toLowerCase();
  const shown = modules.filter((m) => (group === 'all' || groupOf(m.title) === group)
    && (!filter || m.title.toLowerCase().includes(filter) || m.content.toLowerCase().includes(filter)));
  $('count').textContent = modules.length;
  const list = $('modules');
  list.replaceChildren();
  if (!shown.length) {
    list.append(el('li', { className: 'muted' }, modules.length ? 'No entries match.' : 'No entries yet.'));
    return;
  }
  for (const m of shown) {
    const preview = m.content.length > 220 ? m.content.slice(0, 220) + '…' : m.content;
    list.append(
      el('li', {},
        el('div', { className: 'item-head' },
          el('div', {},
            el('span', { className: 'item-title' }, m.title),
            el('span', { className: 'badge' }, m.source),
            el('div', { className: 'muted small' },
              `Updated ${new Date(m.updated_at).toLocaleString()}${m.updated_by ? ' by ' + m.updated_by : ''}`)
          ),
          me.permissions.content ? el('div', { className: 'row' },
            el('button', { className: 'btn small', onclick: () => startEdit(m) }, 'Edit'),
            el('button', { className: 'btn small danger', onclick: () => removeModule(m) }, 'Delete')
          ) : null
        ),
        el('p', { className: 'item-body' }, preview)
      )
    );
  }
}

async function loadModules() {
  modules = await api('GET', '/api/admin/modules');
  renderModules();
}

function removeModule(module) {
  if (!confirm(`Delete "${module.title}"? The assistant will stop using it straight away.`)) return;
  attempt(async () => {
    await api('DELETE', `/api/admin/modules/${module.id}`);
    if (editingId === module.id) resetForm();
    notify('Deleted.');
    await loadModules();
  });
}

$('moduleForm').addEventListener('submit', (event) => {
  event.preventDefault();
  const content = $('mContent').value.trim();
  if (!content) return showError('Type or paste the information first.');
  let title = $('mTitle').value.trim() || autoTitle(content);
  if (kind.prefix && !title.startsWith(kind.prefix)) title = kind.prefix + title;
  const body = { title, content, source: nextSource };
  $('mSave').disabled = true;
  attempt(async () => {
    if (editingId) await api('PUT', `/api/admin/modules/${editingId}`, body);
    else await api('POST', '/api/admin/modules', body);
    notify(editingId ? 'Saved. The assistant now uses the new version.' : 'Added. The assistant can answer from it now.');
    resetForm();
    await loadModules();
  }).finally(() => ($('mSave').disabled = false));
});

$('tidy').addEventListener('click', () => {
  const text = $('mContent').value.trim();
  if (!text) return showError('Type or paste the information first, then the AI can tidy it.');
  $('tidy').disabled = true;
  $('tidy').textContent = 'Tidying… (up to a minute)';
  attempt(async () => {
    const result = await api('POST', '/api/admin/tidy', { text: text.slice(0, 20000), category: kind.label });
    beforeTidy = { content: $('mContent').value, title: $('mTitle').value };
    $('mContent').value = result.content;
    if (result.title && !$('mTitle').value.trim()) $('mTitle').value = result.title;
    showTidied(true);
  }).finally(() => {
    $('tidy').disabled = false;
    $('tidy').textContent = 'Tidy up with AI';
  });
});

$('undoTidy').addEventListener('click', () => {
  if (beforeTidy) {
    $('mContent').value = beforeTidy.content;
    $('mTitle').value = beforeTidy.title;
  }
  showTidied(false);
});

$('mCancel').addEventListener('click', resetForm);
$('filter').addEventListener('input', renderModules);

// Any file: its text goes into the box, after what is already there.
const DROP_TEXT = 'Drop a PDF, photo, screenshot, CSV or text file here, or click to choose';

async function readFile(file) {
  const form = new FormData();
  form.append('file', file);
  $('dropText').textContent = `Reading ${file.name}…`;
  await attempt(async () => {
    const result = await api('POST', '/api/admin/extract-text', form);
    const box = $('mContent');
    box.value = box.value.trim() ? `${box.value.trim()}\n\n${result.text}` : result.text;
    if (file.type.startsWith('image/')) nextSource = 'image';
    if (!$('mTitle').value.trim()) $('mTitle').value = file.name.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ');
    notify('Text added. Check it, tidy it if you like, then save.');
  });
  $('anyFile').value = '';
  $('dropText').textContent = DROP_TEXT;
}

$('anyFile').addEventListener('change', () => $('anyFile').files[0] && readFile($('anyFile').files[0]));
for (const name of ['dragenter', 'dragover']) {
  $('drop').addEventListener(name, (e) => { e.preventDefault(); $('drop').classList.add('over'); });
}
$('drop').addEventListener('dragleave', () => $('drop').classList.remove('over'));
$('drop').addEventListener('drop', (e) => {
  e.preventDefault();
  $('drop').classList.remove('over');
  if (e.dataTransfer.files[0]) readFile(e.dataTransfer.files[0]);
});

$('csvButton').addEventListener('click', () => $('csvFile').click());
$('csvFile').addEventListener('change', () => {
  const file = $('csvFile').files[0];
  if (!file) return;
  const form = new FormData();
  form.append('file', file);
  $('csvButton').disabled = true;
  $('csvButton').textContent = 'Importing…';
  attempt(async () => {
    const result = await api('POST', '/api/admin/modules/import-csv', form);
    notify(`Imported ${result.added} entries from ${file.name}.`);
    await loadModules();
  }).finally(() => {
    $('csvFile').value = '';
    $('csvButton').disabled = false;
    $('csvButton').textContent = 'Import CSV';
  });
});

$('reindex').addEventListener('click', () => {
  $('reindex').disabled = true;
  attempt(async () => {
    const result = await api('POST', '/api/admin/reindex');
    notify(`Search index rebuilt (${result.chunks} pieces).`);
  }).finally(() => ($('reindex').disabled = false));
});

pickKind(KINDS[0]);

// ---- Staff --------------------------------------------------------------------

const PERMS = ['content', 'attendance', 'marks'];

function staffRow(p) {
  const locked = p.fixed || p.email === me.email;
  const switches = PERMS.map((perm) => {
    const box = el('input', { type: 'checkbox', 'aria-label': `${perm} for ${p.email}` });
    box.checked = Boolean(p[`can_${perm}`]);
    box.disabled = locked || p.role === 'admin';
    box.addEventListener('change', () => attempt(async () => {
      await api('POST', '/api/admin/staff', { email: p.email, name: p.name, role: p.role, ...Object.fromEntries(
        PERMS.map((x) => [x, x === perm ? box.checked : Boolean(p[`can_${x}`])])) });
      notify('Access updated.');
      await loadStaff();
    }).then((ok) => {
      if (!ok) box.checked = !box.checked;
    }));
    return el('td', { className: 'num' }, el('label', { className: 'switch' }, box, el('span')));
  });
  return el('tr', {},
    el('td', {}, el('strong', {}, p.name || p.email.split('@')[0]), el('br'), el('span', { className: 'muted small' }, p.email)),
    el('td', {}, el('span', { className: `badge ${p.role}` }, p.fixed ? 'admin · fixed' : p.role)),
    ...switches,
    el('td', {}, locked ? null : el('button', { className: 'btn small danger', onclick: () => removeStaff(p) }, 'Remove')));
}

async function loadStaff() {
  const staff = await api('GET', '/api/admin/staff');
  $('staffCount').textContent = staff.length;
  $('staff').replaceChildren(...staff.map(staffRow));
}

function removeStaff(p) {
  if (!confirm(`Remove ${p.email} from the staff? They become a normal student account.`)) return;
  attempt(async () => {
    await api('DELETE', `/api/admin/staff/${encodeURIComponent(p.email)}`);
    notify('Removed from staff.');
    await loadStaff();
  });
}

$('sRole').addEventListener('change', () => {
  $('sPerms').hidden = $('sRole').value === 'admin';
});

$('staffForm').addEventListener('submit', (event) => {
  event.preventDefault();
  const button = event.submitter;
  button.disabled = true;
  attempt(async () => {
    const admin = $('sRole').value === 'admin';
    await api('POST', '/api/admin/staff', {
      email: $('sEmail').value, name: $('sName').value, role: $('sRole').value,
      content: admin || $('pContent').checked, attendance: admin || $('pAttendance').checked, marks: admin || $('pMarks').checked,
    });
    notify(`${$('sEmail').value} added.`);
    $('staffForm').reset();
    $('sPerms').hidden = false;
    await loadStaff();
  }).finally(() => (button.disabled = false));
});

// ---- Students and faces ----------------------------------------------------------------

async function loadFaces() {
  const faces = await api('GET', '/api/admin/faces');
  $('faceCount').textContent = faces.length;
  const list = $('faces');
  list.replaceChildren();
  if (!faces.length) {
    list.append(el('li', { className: 'muted' }, 'Nobody has enrolled yet.'));
    return;
  }
  for (const f of faces) {
    list.append(
      el('li', { className: 'item-head' },
        el('div', {},
          el('div', { className: 'item-title' }, f.name || f.email.split('@')[0].toUpperCase()),
          el('div', { className: 'muted small' }, `${f.email} · enrolled ${new Date(f.updated_at).toLocaleString()}`)
        ),
        el('button', { className: 'btn small danger', onclick: () => resetFace(f.email) }, 'Reset face')
      )
    );
  }
}

function resetFace(email) {
  if (!confirm(`Reset the face for ${email}? They will enrol again at their next sign-in.`)) return;
  attempt(async () => {
    await api('DELETE', `/api/admin/faces/${encodeURIComponent(email)}`);
    notify('Face reset.');
    await loadFaces();
  });
}

async function start() {
  me = await loadMe();
  renderBar('/admin', me);
  const admin = me.role === 'admin';
  $('sub').textContent = admin
    ? 'You can manage everything: content, staff access and student faces.'
    : 'You can do what an admin has allowed for your account.';
  document.querySelector('[data-tab="staff"]').hidden = !admin;
  document.querySelector('[data-tab="faces"]').hidden = !admin;
  $('editor').hidden = !me.permissions.content;
  $('readonly').hidden = me.permissions.content;
  attempt(loadModules);
  if (admin) {
    attempt(loadStaff);
    attempt(loadFaces);
  }
}

start();
