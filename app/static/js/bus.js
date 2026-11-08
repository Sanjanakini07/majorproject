// Bus timings: three routes from the community listing, the next few buses, and a searchable table.

let me = null;
let data = null;
let route = null;

const minutes = (hhmm) => {
  const [h, m] = hhmm.split(':').map(Number);
  return h * 60 + m;
};
const nowMinutes = () => {
  const t = new Date();
  return t.getHours() * 60 + t.getMinutes();
};
function clock(hhmm) {
  const [h, m] = hhmm.split(':').map(Number);
  return `${h % 12 || 12}:${String(m).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'}`;
}
function wait(mins) {
  if (mins < 1) return 'now';
  if (mins < 60) return `in ${mins} min`;
  return `in ${Math.floor(mins / 60)} h ${mins % 60} min`;
}

// The column that differs per route: where the bus came from, where it goes, or when it reaches Nitte.
function extra(b) {
  if (b.goes_to) return b.goes_to;
  if (b.comes_from) return b.comes_from;
  if (b.reaches_nitte) return clock(b.reaches_nitte);
  return '';
}
const EXTRA_HEAD = { 'to-karkala': 'Comes from', 'to-mangalore-udupi': 'Goes to', 'bypass-to-nitte': 'Reaches Nitte' };

function tags(b) {
  return [...b.type.map((t) => el('span', { className: 'tag' + (t === 'Express' ? ' express' : '') }, t)),
    ...(b.user_contributed ? [el('span', { className: 'tag uc', title: 'Added through the listing\'s feedback form' }, 'User contributed')] : [])];
}

function filtered() {
  const q = $('search').value.trim().toLowerCase();
  const place = $('place').value;
  return route.buses.filter((b) =>
    (!q || [b.name, b.time, clock(b.time), extra(b), ...b.type].join(' ').toLowerCase().includes(q))
    && (!place || (b.goes_to || '').includes(place)));
}

function render() {
  const now = nowMinutes();
  const buses = filtered();
  const coming = buses.filter((b) => minutes(b.time) >= now);

  $('next').replaceChildren(...(coming.length
    ? coming.slice(0, 3).map((b) => el('div', { className: 'card' },
      el('div', { className: 'when' }, clock(b.time)),
      el('div', { className: 'in' }, wait(minutes(b.time) - now)),
      el('div', {}, el('strong', {}, b.name), ' ', extra(b) ? el('span', { className: 'muted small' }, `· ${extra(b)}`) : ''),
      el('div', {}, ...tags(b))))
    : [el('div', { className: 'card' }, el('strong', {}, 'No more buses today on this route.'),
      el('div', { className: 'muted small' }, buses.length ? `First one tomorrow: ${clock(buses[0].time)} ${buses[0].name}` : ''))]));

  $('head').replaceChildren(el('tr', {}, el('th', {}, 'Time'), el('th', {}, 'Bus'), el('th', {}, EXTRA_HEAD[route.id]), el('th', {}, 'Type')));
  const shown = $('upcoming').checked ? coming : buses;
  const nextTime = coming[0] && coming[0].time;
  $('rows').replaceChildren(...(shown.length ? shown.map((b) => el('tr', {
    className: 'bus-row' + (minutes(b.time) < now ? ' gone' : '') + (b.time === nextTime ? ' next' : ''),
  }, el('td', {}, clock(b.time)), el('td', {}, b.name), el('td', {}, extra(b)), el('td', {}, ...tags(b))))
    : [el('tr', {}, el('td', { colspan: '4', className: 'muted' }, 'No buses match.'))]));
}

function pickRoute(id) {
  route = data.routes.find((r) => r.id === id) || data.routes[0];
  for (const tab of document.querySelectorAll('#routes .tab')) tab.classList.toggle('active', tab.dataset.id === route.id);
  const places = [...new Set(route.buses.map((b) => b.goes_to).filter(Boolean))].sort();
  $('place').hidden = !places.length;
  $('place').replaceChildren(el('option', { value: '' }, 'Any destination'), ...places.map((p) => el('option', { value: p }, p)));
  try { localStorage.setItem('bus-route', route.id); } catch (e) { /* storage may be off */ }
  render();
}

// ---- College buses (Admin › College buses, app/sheets.py) ---------------------------------

async function showCollege() {
  const box = $('collegeBox');
  box.replaceChildren(el('div', { className: 'skeleton' }));
  let buses = [];
  try {
    buses = (await api('GET', '/api/sheets/college_buses')).rows;
  } catch (e) {
    return showError(e.message);
  }
  if (!buses.length) {
    return box.replaceChildren(el('div', { className: 'card empty' }, icon('bus'), el('strong', {}, 'No college buses added yet'),
      el('span', {}, me.permissions.content ? 'Add each bus with its number, route and stops in Admin › College buses.'
        : 'The college bus routes will appear here once they are added.'),
      me.permissions.content ? el('a', { className: 'btn primary', href: '/admin' }, 'Open Admin') : null));
  }
  box.replaceChildren(el('div', { className: 'grid cols-2' }, ...buses.map((b) => el('div', { className: 'card' },
    el('h3', {}, `Bus ${b.bus_no || '?'}`, b.route ? el('span', { className: 'muted' }, ` · ${b.route}`) : ''),
    el('div', { className: 'meta-line' },
      b.morning ? el('span', {}, icon('clock'), `Reaches college ${clock(b.morning)}`) : null,
      b.evening ? el('span', {}, icon('clock'), `Leaves college ${clock(b.evening)}`) : null),
    b.stops ? el('p', {}, el('strong', {}, 'Stops: '), b.stops) : null,
    b.contact ? el('p', { className: 'muted small' }, `Contact: ${b.contact}`) : null,
    b.notes ? el('p', { className: 'muted small' }, b.notes) : null))));
}

function pickKind(kind) {
  for (const b of $('busKind').children) b.classList.toggle('on', b.dataset.kind === kind);
  $('localBox').hidden = kind !== 'local';
  $('collegeBox').hidden = kind !== 'college';
  try { localStorage.setItem('bus-kind', kind); } catch (e) { /* storage may be off */ }
  if (kind === 'college') showCollege();
}

async function start() {
  me = await loadMe();
  renderBar('/bus', me);
  for (const b of $('busKind').children) b.addEventListener('click', () => pickKind(b.dataset.kind));
  let kind = 'local';
  try { kind = localStorage.getItem('bus-kind') || 'local'; } catch (e) { /* storage may be off */ }
  pickKind(kind === 'college' ? 'college' : 'local');
  try {
    data = await api('GET', '/api/bus');
  } catch (e) {
    return showError(e.message);
  }
  $('routes').replaceChildren(...data.routes.map((r) => el('button', {
    className: 'tab', role: 'tab', 'data-id': r.id, onclick: () => pickRoute(r.id),
  }, r.title.replace(/ \(.*\)$/, ''))));
  const link = el('a', { href: data.source, target: '_blank', rel: 'noopener' }, 'Bus Timings: Nitte');
  $('source').replaceChildren(`Timings from the community listing `, link, `, last updated ${data.updated}. ${data.note}`);
  for (const id of ['search', 'place', 'upcoming']) $(id).addEventListener('input', render);
  let saved = null;
  try { saved = localStorage.getItem('bus-route'); } catch (e) { /* storage may be off */ }
  pickRoute(saved);
  setInterval(render, 60 * 1000);   // keep "in 5 min" current
}

start();
