// Marks: students see their own; teachers and admins pick a student, and can edit if an admin allowed it.

let me = null;
let current = null;   // email being shown (null for a student's own)

function statCard(num, label) {
  return el('div', { className: 'card stat' }, el('span', { className: 'num' }, String(num)), el('span', { className: 'label' }, label));
}

function semesterChart(semesters) {
  return el('div', { className: 'card' },
    el('h2', {}, 'Semester performance'),
    el('div', { className: 'sem-bars' },
      ...semesters.map((s) => {
        const fill = el('div', { className: 'bar-fill' });
        fill.style.height = '0%';
        // Two frames, so the browser sees the empty bar first and animates up to the value.
        requestAnimationFrame(() => requestAnimationFrame(() => (fill.style.height = `${Math.max(4, s.percent * 0.85)}%`)));
        return el('div', { className: 'col' }, el('span', { className: 'pct' }, `${s.percent}%`), fill, el('span', { className: 'lbl' }, `Sem ${s.semester}`));
      })));
}

function subjectCell(s) {
  return el('td', {}, el('strong', {}, s.subject), el('br'), el('span', { className: 'muted small' }, s.code));
}

function subjectRow(sem, s, canEdit, student) {
  if (!canEdit) {
    return el('tr', {},
      subjectCell(s),
      el('td', { className: 'num' }, s.internal), el('td', { className: 'num' }, s.external),
      el('td', { className: 'num' }, el('strong', {}, s.total)), el('td', { className: 'num' }, gradeChip(s.grade)));
  }
  const internal = el('input', { type: 'number', min: 0, max: 50, value: s.internal, 'aria-label': `${s.subject} internal` });
  const external = el('input', { type: 'number', min: 0, max: 50, value: s.external, 'aria-label': `${s.subject} external` });
  const save = el('button', { className: 'btn small', onclick: async () => {
    save.disabled = true;
    try {
      await api('PUT', '/api/marks', {
        email: student, semester: sem, code: s.code, internal: Number(internal.value), external: Number(external.value),
      });
      toast('Marks saved');
      await load(current);
    } catch (e) {
      toast(e.message, 'error');
      save.disabled = false;
    }
  } }, 'Save');
  return el('tr', {},
    subjectCell(s),
    el('td', { className: 'num' }, internal), el('td', { className: 'num' }, external),
    el('td', { className: 'num' }, el('strong', {}, s.total)), el('td', { className: 'num' }, gradeChip(s.grade)),
    el('td', {}, save));
}

function semesterCard(sem, canEdit, student) {
  const head = ['Subject', 'Internal /50', 'External /50', 'Total', 'Grade', ...(canEdit ? [''] : [])];
  return el('div', { className: 'card' },
    el('div', { className: 'sem-head' },
      el('h2', {}, `Semester ${sem.semester}`),
      el('span', { className: 'pill' }, `${sem.total}/${sem.max}`, el('span', { className: 'muted small' }, `${sem.percent}%`), gradeChip(sem.grade))),
    el('div', { className: 'table-wrap' },
      el('table', {},
        el('thead', {}, el('tr', {}, ...head.map((h, i) => el('th', { className: i > 0 && i < 5 ? 'num' : '' }, h)))),
        el('tbody', {}, ...sem.subjects.map((s) => subjectRow(sem.semester, s, canEdit, student))))));
}

function render(data) {
  const box = $('content');
  if (!data.student) {
    $('sub').textContent = '';
    box.replaceChildren(el('div', { className: 'card' }, el('p', { className: 'muted' },
      me.role === 'student' ? 'Your marks will appear here after your first face sign-in.' : 'Pick a student to see their marks.')));
    return;
  }
  const canEdit = me.permissions.marks;
  const st = data.student;
  $('sub').textContent = `${(st.name || st.email).toUpperCase()} · ${st.branch || 'Branch n/a'} · now in semester ${st.semester}`;
  const best = Math.max(...data.semesters.map((s) => s.percent));
  box.replaceChildren(
    el('div', { className: 'grid cols-3' },
      statCard(`${data.overall_percent}%`, 'Overall percentage'),
      statCard(data.semesters.length, 'Semesters completed'),
      statCard(`${best}%`, 'Best semester')),
    semesterChart(data.semesters),
    ...(!canEdit && me.role !== 'student' ? [el('p', { className: 'alert info' }, 'You can view marks. An admin can switch on editing for you.')] : []),
    ...data.semesters.slice().reverse().map((s) => semesterCard(s, canEdit, st.email)));
}

async function load(email) {
  hideError();
  current = email;
  try {
    render(await api('GET', '/api/marks' + (email ? `?email=${encodeURIComponent(email)}` : '')));
  } catch (e) {
    showError(e.message);
  }
}

async function start() {
  me = await loadMe();
  renderBar('/marks', me);
  if (me.role === 'student') return load(null);
  $('picker').hidden = false;
  await studentPicker($('picker'), (email) => (email ? load(email) : render({ student: null })));
}

start();
