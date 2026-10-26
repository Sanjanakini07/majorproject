// Admin panel: manage the knowledge the assistant answers from, and registered faces.

let modules = [];
let editingId = null;   // id of the entry being edited, or null when adding
let nextSource = 'manual';

function notify(message) {
  hideError();
  $('notice').textContent = message;
  $('notice').hidden = false;
  setTimeout(() => ($('notice').hidden = true), 4000);
}

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

// Run an action, show its error inline instead of failing silently.
async function attempt(action) {
  try {
    await action();
  } catch (e) {
    console.error(e);
    showError(e.message);
  }
}

// ---- Tabs -----------------------------------------------------------------------

for (const tab of document.querySelectorAll('.tab')) {
  tab.addEventListener('click', () => {
    for (const t of document.querySelectorAll('.tab')) t.classList.toggle('active', t === tab);
    $('tab-knowledge').hidden = tab.dataset.tab !== 'knowledge';
    $('tab-faces').hidden = tab.dataset.tab !== 'faces';
    hideError();
  });
}

// ---- Knowledge ----------------------------------------------------------------

function resetForm() {
  editingId = null;
  nextSource = 'manual';
  $('moduleForm').reset();
  $('formTitle').textContent = 'Add knowledge';
  $('mCancel').hidden = true;
}

function startEdit(module) {
  editingId = module.id;
  $('mTitle').value = module.title;
  $('mContent').value = module.content;
  $('formTitle').textContent = 'Edit knowledge';
  $('mCancel').hidden = false;
  $('mTitle').focus();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function renderModules() {
  const filter = $('filter').value.trim().toLowerCase();
  const shown = modules.filter(
    (m) => !filter || m.title.toLowerCase().includes(filter) || m.content.toLowerCase().includes(filter)
  );
  $('count').textContent = modules.length;
  const list = $('modules');
  list.replaceChildren();
  if (!shown.length) {
    list.append(el('li', { className: 'muted' }, modules.length ? 'No entries match.' : 'No entries yet. Add one above.'));
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
          el('div', { className: 'row' },
            el('button', { className: 'btn small', onclick: () => startEdit(m) }, 'Edit'),
            el('button', { className: 'btn small danger', onclick: () => removeModule(m) }, 'Delete')
          )
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
  const body = { title: $('mTitle').value, content: $('mContent').value, source: nextSource };
  $('mSave').disabled = true;
  attempt(async () => {
    if (editingId) await api('PUT', `/api/admin/modules/${editingId}`, body);
    else await api('POST', '/api/admin/modules', body);
    notify(editingId ? 'Saved. The assistant now uses the new version.' : 'Added. The assistant can now answer from it.');
    resetForm();
    await loadModules();
  }).finally(() => ($('mSave').disabled = false));
});

$('mCancel').addEventListener('click', resetForm);
$('filter').addEventListener('input', renderModules);

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

$('imgButton').addEventListener('click', () => $('imgFile').click());
$('imgFile').addEventListener('change', () => {
  const file = $('imgFile').files[0];
  if (!file) return;
  const form = new FormData();
  form.append('file', file);
  $('imgButton').disabled = true;
  $('imgButton').textContent = 'Reading image…';
  attempt(async () => {
    const result = await api('POST', '/api/admin/extract-text', form);
    resetForm();
    nextSource = 'image';
    $('mTitle').value = file.name.replace(/\.[^.]+$/, '');
    $('mContent').value = result.text;
    $('formTitle').textContent = 'Check the text from the image, then Save';
    $('mCancel').hidden = false;
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }).finally(() => {
    $('imgFile').value = '';
    $('imgButton').disabled = false;
    $('imgButton').textContent = 'Read text from image';
  });
});

$('reindex').addEventListener('click', () => {
  $('reindex').disabled = true;
  attempt(async () => {
    const result = await api('POST', '/api/admin/reindex');
    notify(`Search index rebuilt (${result.chunks} pieces).`);
  }).finally(() => ($('reindex').disabled = false));
});

// ---- Faces --------------------------------------------------------------------

async function loadFaces() {
  const faces = await api('GET', '/api/admin/faces');
  $('faceCount').textContent = faces.length;
  const list = $('faces');
  list.replaceChildren();
  if (!faces.length) {
    list.append(el('li', { className: 'muted' }, 'No faces registered yet.'));
    return;
  }
  for (const f of faces) {
    list.append(
      el('li', { className: 'item-head' },
        el('div', {},
          el('div', { className: 'item-title' }, f.email),
          el('div', { className: 'muted small' }, `Registered ${new Date(f.updated_at).toLocaleString()}`)
        ),
        el('button', { className: 'btn small danger', onclick: () => removeFace(f.email) }, 'Remove')
      )
    );
  }
}

function removeFace(email) {
  if (!confirm(`Remove the face for ${email}? They won't be able to pass the face check until it is registered again.`)) return;
  attempt(async () => {
    await api('DELETE', `/api/admin/faces/${encodeURIComponent(email)}`);
    notify('Face removed.');
    await loadFaces();
  });
}

$('faceForm').addEventListener('submit', (event) => {
  event.preventDefault();
  const form = new FormData();
  form.append('email', $('fEmail').value);
  form.append('file', $('fFile').files[0]);
  const button = event.submitter;
  button.disabled = true;
  attempt(async () => {
    const result = await api('POST', '/api/admin/faces', form);
    notify(`Face saved for ${result.email}.`);
    $('faceForm').reset();
    await loadFaces();
  }).finally(() => (button.disabled = false));
});

attempt(loadModules);
attempt(loadFaces);
