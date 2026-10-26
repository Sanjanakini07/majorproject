// Events: everyone can read. Admins and teachers with the "content" permission can add and delete.
// Details can be typed in or come from a PDF (its text is read by the voice assistant too).

let me = null;
let events = [];

const MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

function parts(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  return { y, m: m - 1, d, dow: new Date(y, m - 1, d).getDay() };
}

function clock(hhmm) {
  if (!hhmm) return '';
  const [h, m] = hhmm.split(':').map(Number);
  return `${h % 12 || 12}:${String(m).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'}`;
}

const todayIso = () => {
  const t = new Date();
  return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`;
};

function eventCard(ev, past) {
  const p = parts(ev.event_date);
  const meta = [];
  if (ev.start_time) meta.push(el('span', {}, icon('clock'), clock(ev.start_time)));
  if (ev.venue) meta.push(el('span', {}, icon('pin'), ev.venue));
  const actions = [];
  if (ev.has_file) {
    actions.push(
      el('a', { className: 'btn small', href: `/api/events/${ev.id}/file`, target: '_blank', rel: 'noopener' }, icon('pdf'), 'Open PDF'),
      el('a', { className: 'btn small', href: `/api/events/${ev.id}/file?download=true` }, icon('download'), 'Download'));
  }
  if (me.permissions.content) {
    actions.push(el('button', { className: 'btn small danger', onclick: () => remove(ev) }, icon('trash'), 'Delete'));
  }
  return el('div', { className: 'card event' + (past ? ' past' : '') },
    el('div', { className: 'datebox' },
      el('div', { className: 'm' }, MONTHS[p.m]), el('div', { className: 'd' }, String(p.d)), el('div', { className: 'w' }, DAYS[p.dow])),
    el('div', { className: 'grow' },
      el('h3', {}, ev.title),
      el('div', { className: 'meta-line' }, ...meta),
      ev.description ? el('p', { className: 'desc' }, ev.description) : null,
      actions.length ? el('div', { className: 'row', }, ...actions) : null));
}

function render() {
  const today = todayIso();
  const upcoming = events.filter((e) => e.event_date >= today);
  const past = events.filter((e) => e.event_date < today).reverse();
  const nodes = [];
  if (!events.length) {
    nodes.push(el('div', { className: 'card empty' }, icon('events'), el('strong', {}, 'No events yet'),
      el('span', {}, me.permissions.content ? 'Add the first one with the button above.' : 'Check back soon.')));
  }
  if (upcoming.length) nodes.push(el('div', { className: 'section-label' }, 'Upcoming'), el('div', { className: 'stack' }, ...upcoming.map((e) => eventCard(e, false))));
  if (past.length) nodes.push(el('div', { className: 'section-label' }, 'Past'), el('div', { className: 'stack' }, ...past.map((e) => eventCard(e, true))));
  $('list').replaceChildren(...nodes);
}

async function remove(ev) {
  if (!confirm(`Delete "${ev.title}"? The assistant will stop using it too.`)) return;
  try {
    await api('DELETE', `/api/events/${ev.id}`);
    toast('Event deleted');
    await load();
  } catch (e) {
    toast(e.message, 'error');
  }
}

function addForm() {
  const title = el('input', { required: '', maxlength: 200, placeholder: 'e.g. Tech Fest 2026' });
  const date = el('input', { type: 'date', required: '', min: todayIso() });
  const time = el('input', { type: 'time' });
  const venue = el('input', { maxlength: 200, placeholder: 'e.g. Main auditorium' });
  const desc = el('textarea', { rows: 5, maxlength: 100000, placeholder: 'What is it about? Who can join? Anything to bring?' });
  const file = el('input', { type: 'file', accept: 'application/pdf,.pdf' });
  const fileText = el('span', {}, 'Optional: attach a PDF (poster, schedule, rules)');
  const drop = el('label', { className: 'drop' }, icon('upload'), fileText, file);
  file.addEventListener('change', () => {
    drop.classList.toggle('has', Boolean(file.files[0]));
    fileText.textContent = file.files[0] ? file.files[0].name : 'Optional: attach a PDF (poster, schedule, rules)';
  });
  const submit = el('button', { className: 'btn primary' }, icon('events'), 'Publish event');
  const form = el('form', {},
    el('label', {}, 'Event title', title),
    el('div', { className: 'grid cols-3' }, el('label', {}, 'Date', date), el('label', {}, 'Start time', time), el('label', {}, 'Venue', venue)),
    el('label', {}, 'Details', desc),
    drop, submit);
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const body = new FormData();
    body.append('title', title.value);
    body.append('event_date', date.value);
    body.append('start_time', time.value);
    body.append('venue', venue.value);
    body.append('description', desc.value);
    if (file.files[0]) body.append('file', file.files[0]);
    submit.disabled = true;
    try {
      await api('POST', '/api/events', body);
      toast('Event published. The assistant knows about it now.');
      form.reset();
      file.dispatchEvent(new Event('change'));
      setForm(false);
      await load();
    } catch (err) {
      toast(err.message, 'error');
    }
    submit.disabled = false;
  });
  return el('div', { className: 'card' }, el('h2', {}, 'New event'), form);
}

function setForm(open) {
  $('formBox').replaceChildren(...(open ? [addForm()] : []));
  $('toggleForm').textContent = open ? 'Close' : 'Add an event';
  $('toggleForm').dataset.open = open ? '1' : '';
}

async function load() {
  try {
    events = await api('GET', '/api/events');
    render();
  } catch (e) {
    showError(e.message);
  }
}

async function start() {
  me = await loadMe();
  renderBar('/events', me);
  if (me.permissions.content) {
    $('toggleForm').hidden = false;
    $('toggleForm').addEventListener('click', () => setForm(!$('toggleForm').dataset.open));
    setForm(false);
  }
  $('list').replaceChildren(el('div', { className: 'skeleton' }));
  await load();
}

start();
