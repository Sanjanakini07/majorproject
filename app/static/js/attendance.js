// Attendance: students see their own; teachers and admins pick a student, and can edit if an admin allowed it.

let me = null;
let current = null;

function tone(percent, required) {
  return percent >= required ? '' : percent >= required - 10 ? 'warn' : 'bad';
}

// How many classes can still be missed, or must be attended, to stay at the required percentage.
function advice(s, required) {
  const r = required / 100;
  if (s.percent >= required) {
    const spare = Math.floor(s.attended / r - s.total);
    return spare > 0
      ? `You can miss ${spare} more ${spare === 1 ? 'class' : 'classes'} and stay above ${required}%.`
      : `Right on ${required}%. Don’t miss the next class.`;
  }
  const need = Math.ceil((r * s.total - s.attended) / (1 - r));
  return `Attend the next ${need} ${need === 1 ? 'class' : 'classes'} in a row to reach ${required}%.`;
}

function subjectCard(s, required, canEdit, student) {
  const t = tone(s.percent, required);
  const ring = el('div', { className: `ring ${t}` }, el('span', {}, `${Math.round(s.percent)}%`));
  ring.style.setProperty('--v', s.percent);
  const body = [el('h3', {}, s.subject), el('span', { className: 'muted small' }, `${s.code} · ${s.attended} of ${s.total} classes`)];
  if (!canEdit) {
    body.push(el('p', { className: 'small muted' }, advice(s, required)));
  } else {
    const attended = el('input', { type: 'number', min: 0, max: 500, value: s.attended, 'aria-label': `${s.subject} attended` });
    const total = el('input', { type: 'number', min: 0, max: 500, value: s.total, 'aria-label': `${s.subject} total classes` });
    const save = el('button', { className: 'btn small', onclick: async () => {
      save.disabled = true;
      try {
        await api('PUT', '/api/attendance', {
          email: student, semester: s.semester, code: s.code, attended: Number(attended.value), total: Number(total.value),
        });
        toast('Attendance saved');
        await load(current);
      } catch (e) {
        toast(e.message, 'error');
        save.disabled = false;
      }
    } }, 'Save');
    body.push(el('div', { className: 'row' }, attended, el('span', { className: 'muted' }, 'of'), total, save));
  }
  return el('div', { className: 'card subject-card' },
    el('div', { className: 'row' }, ring, el('div', { className: 'grow' }, ...body)),
    el('div', { className: `meter ${t}` }, el('i')));
}

function render(data) {
  const box = $('content');
  if (!data.student) {
    $('sub').textContent = '';
    box.replaceChildren(el('div', { className: 'card' }, el('p', { className: 'muted' },
      me.role === 'student' ? 'Your attendance will appear here after your first face sign-in.' : 'Pick a student to see their attendance.')));
    return;
  }
  const canEdit = me.permissions.attendance;
  const st = data.student;
  const req = data.required_percent;
  $('sub').textContent = `${(st.name || st.email).toUpperCase()} · semester ${st.semester} · ${req}% needed to sit the exams`;
  const low = data.subjects.filter((s) => s.percent < req).length;
  const cards = data.subjects.map((s) => subjectCard(s, req, canEdit, st.email));
  const stat = (num, label) => el('div', { className: 'card stat' }, el('span', { className: 'num' }, String(num)), el('span', { className: 'label' }, label));
  box.replaceChildren(
    el('div', { className: 'grid cols-3' },
      stat(`${data.overall_percent}%`, 'Overall attendance'),
      stat(data.subjects.length, 'Subjects this semester'),
      stat(low, `Below ${req}%`)),
    ...(!canEdit && me.role !== 'student' ? [el('p', { className: 'alert info' }, 'You can view attendance. An admin can switch on editing for you.')] : []),
    el('div', { className: 'grid cols-2' }, ...cards));
  // Animate the meters up from empty. (Inline style attributes are blocked by the page's security policy; this is fine.)
  data.subjects.forEach((s, i) => {
    const fill = cards[i].querySelector('.meter > i');
    fill.style.width = '0%';
    requestAnimationFrame(() => requestAnimationFrame(() => (fill.style.width = `${s.percent}%`)));
  });
}

async function load(email) {
  hideError();
  current = email;
  try {
    render(await api('GET', '/api/attendance' + (email ? `?email=${encodeURIComponent(email)}` : '')));
  } catch (e) {
    showError(e.message);
  }
}

async function start() {
  me = await loadMe();
  renderBar('/attendance', me);
  if (me.role === 'student') return load(null);
  $('picker').hidden = false;
  await studentPicker($('picker'), (email) => (email ? load(email) : render({ student: null })));
}

start();
