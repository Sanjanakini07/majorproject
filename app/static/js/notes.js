// Notes library: semesters 1-8, subjects, and files or pasted text under each subject.
// Everyone can read. Admins and teachers with the "content" permission can add and delete.

let me = null;
let subjects = [];
let semester = 1;
let subject = null;   // the selected subject object

function ago(iso) {
  return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
}

const who = (email) => (email || '').split('@')[0].toUpperCase();

// ---- Semesters and subjects ---------------------------------------------------------

function renderPills() {
  $('pills').replaceChildren(...Array.from({ length: 8 }, (_, i) => {
    const sem = i + 1;
    const count = subjects.filter((s) => s.semester === sem).reduce((n, s) => n + s.notes, 0);
    return el('button', { className: 'pill-btn' + (sem === semester ? ' active' : ''), onclick: () => pickSemester(sem) },
      el('span', {}, 'Semester'), el('b', {}, String(sem)), el('span', {}, `${count} ${count === 1 ? 'file' : 'files'}`));
  }));
}

function renderSubjects() {
  const list = subjects.filter((s) => s.semester === semester);
  $('subjects').replaceChildren(...list.map((s) =>
    el('button', { className: 'subject-pick' + (subject && s.code === subject.code ? ' active' : ''), onclick: () => pickSubject(s.code) },
      el('span', { className: 'tile' }, icon('notes')),
      el('span', {}, el('strong', {}, s.name), el('span', { className: 'muted small' }, `${s.code} · ${s.notes} ${s.notes === 1 ? 'file' : 'files'}`)))));
}

function pickSemester(sem) {
  semester = sem;
  subject = subjects.find((s) => s.semester === sem) || null;
  renderAll();
}

function pickSubject(code) {
  subject = subjects.find((s) => s.code === code);
  history.replaceState(null, '', `/notes?sem=${subject.semester}&subject=${subject.code}`);
  renderAll();
}

// ---- Files --------------------------------------------------------------------------

function noteRow(n) {
  const actions = [];
  const body = el('div', { className: 'file-main' });
  const meta = el('div', { className: 'file-meta' },
    el('span', {}, `${who(n.uploaded_by)} · ${ago(n.created_at)}`),
    n.readable
      ? el('span', { className: 'badge ok' }, 'Assistant can read this')
      : el('span', { className: 'badge warn', title: 'Scanned pictures have no text to read' }, 'Assistant can’t read this'));
  body.append(el('h3', {}, n.title), meta);

  if (n.kind === 'pdf') {
    actions.push(
      el('a', { className: 'btn small', href: `/api/notes/${n.id}/file`, target: '_blank', rel: 'noopener' }, icon('eye'), 'Open'),
      el('a', { className: 'btn small', href: `/api/notes/${n.id}/file?download=true` }, icon('download'), 'Download'));
  } else {
    const pre = el('pre', { className: 'note-text' }, n.text || '');
    pre.hidden = true;
    const toggle = el('button', { className: 'btn small', onclick: () => {
      pre.hidden = !pre.hidden;
      toggle.replaceChildren(icon('eye'), pre.hidden ? 'Read' : 'Hide');
    } }, icon('eye'), 'Read');
    actions.push(toggle);
    body.append(pre);
  }
  if (me.permissions.content) {
    actions.push(el('button', { className: 'btn small danger', onclick: () => removeNote(n) }, icon('trash'), 'Delete'));
  }
  return el('div', { className: 'file-row' },
    el('div', { className: 'ftype ' + n.kind }, icon(n.kind === 'pdf' ? 'pdf' : 'text')),
    body, el('div', { className: 'file-actions' }, ...actions));
}

async function removeNote(n) {
  if (!confirm(`Delete "${n.title}"? The assistant will stop using it too.`)) return;
  try {
    await api('DELETE', `/api/notes/${n.id}`);
    toast('Notes deleted');
    await refresh();
  } catch (e) {
    toast(e.message, 'error');
  }
}

function addForm() {
  let mode = 'pdf';
  const title = el('input', { required: '', maxlength: 200, placeholder: 'e.g. Unit 2: Process scheduling' });
  const text = el('textarea', { rows: 8, maxlength: 100000, placeholder: 'Paste the notes here…' });
  const file = el('input', { type: 'file', accept: 'application/pdf,.pdf' });
  const dropText = el('span', {}, 'Click to choose a PDF, or drop it here');
  const drop = el('label', { className: 'drop' }, icon('upload'), dropText, el('small', {}, 'PDF up to 15 MB'), file);
  const pdfBtn = el('button', { type: 'button', className: 'on' }, icon('pdf'), 'Upload PDF');
  const textBtn = el('button', { type: 'button' }, icon('text'), 'Paste text');
  const submit = el('button', { className: 'btn primary' }, icon('upload'), 'Add notes');

  const setMode = (m) => {
    mode = m;
    pdfBtn.classList.toggle('on', m === 'pdf');
    textBtn.classList.toggle('on', m === 'text');
    drop.hidden = m !== 'pdf';
    text.parentElement.hidden = m !== 'text';
  };
  pdfBtn.addEventListener('click', () => setMode('pdf'));
  textBtn.addEventListener('click', () => setMode('text'));
  file.addEventListener('change', () => {
    drop.classList.toggle('has', Boolean(file.files[0]));
    dropText.textContent = file.files[0] ? file.files[0].name : 'Click to choose a PDF, or drop it here';
  });
  for (const ev of ['dragover', 'dragenter']) drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add('over'); });
  for (const ev of ['dragleave', 'drop']) drop.addEventListener(ev, () => drop.classList.remove('over'));
  drop.addEventListener('drop', (e) => {
    e.preventDefault();
    if (e.dataTransfer.files[0]) {
      file.files = e.dataTransfer.files;
      file.dispatchEvent(new Event('change'));
    }
  });

  const form = el('form', {},
    el('label', {}, 'Title', title),
    el('div', { className: 'segmented' }, pdfBtn, textBtn),
    drop,
    el('label', {}, text),
    submit);
  text.parentElement.hidden = true;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const body = new FormData();
    body.append('subject', subject.code);
    body.append('title', title.value);
    if (mode === 'pdf') {
      if (!file.files[0]) return toast('Choose a PDF first', 'error');
      body.append('file', file.files[0]);
    } else {
      body.append('text', text.value);
    }
    submit.disabled = true;
    try {
      const res = await api('POST', '/api/notes', body);
      toast(res.readable ? 'Added. The assistant can now answer from it.' : 'Added, but this PDF has no text, so the assistant can’t read it.');
      form.reset();
      file.dispatchEvent(new Event('change'));
      await refresh();
    } catch (err) {
      toast(err.message, 'error');
    }
    submit.disabled = false;
  });
  return el('div', { className: 'card' }, el('h2', {}, `Add notes to ${subject.name}`), form);
}

function renderPanel() {
  if (!subject) {
    $('panel').replaceChildren();
    return;
  }
  const list = el('div', { className: 'card' });
  list.append(el('div', { className: 'sem-head' },
    el('h2', {}, subject.name), el('span', { className: 'badge' }, `${subject.code} · Semester ${subject.semester}`)));
  const rows = subject.items;
  if (rows === undefined) {
    list.append(el('div', { className: 'skeleton' }));
  } else if (!rows.length) {
    list.append(el('div', { className: 'empty' }, icon('notes'), el('strong', {}, 'No notes here yet'),
      el('span', {}, me.permissions.content ? 'Add the first one below.' : 'Check back soon.')));
  } else {
    list.append(...rows.map(noteRow));
  }
  $('panel').replaceChildren(el('div', { className: 'stack' }, list, ...(me.permissions.content ? [addForm()] : [])));
}

function renderAll() {
  renderPills();
  renderSubjects();
  renderPanel();
  if (subject && subject.items === undefined) loadItems();
}

async function loadItems() {
  const code = subject.code;
  try {
    const items = await api('GET', `/api/notes?subject=${encodeURIComponent(code)}`);
    const s = subjects.find((x) => x.code === code);
    s.items = items;
    s.notes = items.length;
    renderAll();
  } catch (e) {
    showError(e.message);
  }
}

async function refresh() {
  const keep = subject && subject.code;
  subjects = await api('GET', '/api/subjects');
  subject = subjects.find((s) => s.code === keep) || null;
  renderAll();
}

async function start() {
  me = await loadMe();
  renderBar('/notes', me);
  $('subjects').replaceChildren(...[1, 2, 3].map(() => el('div', { className: 'skeleton' })));
  try {
    subjects = await api('GET', '/api/subjects');
  } catch (e) {
    return showError(e.message);
  }
  const params = new URLSearchParams(location.search);
  const wanted = subjects.find((s) => s.code === params.get('subject'));
  semester = wanted ? wanted.semester : Number(params.get('sem')) || 1;
  subject = wanted || subjects.find((s) => s.semester === semester) || null;
  renderAll();
}

start();
