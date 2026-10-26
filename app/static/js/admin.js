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
