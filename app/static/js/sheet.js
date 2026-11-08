// A spreadsheet-style editor for the Admin lists (app/sheets.py): one row of input boxes per line, like Excel.
// Type in any cell, Tab to the next, Enter to the cell below, paste rows straight from Excel or Google Sheets,
// add and delete rows, then Save once. Empty cells that matter are highlighted, so missing data is easy to see.

function sheetEditor(box, name, editable) {
  let cols = [];
  let rows = [];
  let dirty = false;

  const status = el('span', { className: 'muted small' });
  const search = el('input', { type: 'search', placeholder: 'Find in this list', 'aria-label': 'Find in this list' });
  const onlyGaps = el('input', { type: 'checkbox' });
  const save = el('button', { type: 'button', className: 'btn primary' }, 'Save changes');
  const undo = el('button', { type: 'button', className: 'btn' }, 'Undo changes');
  const add = el('button', { type: 'button', className: 'btn' }, '+ Add row');
  const hint = el('p', { className: 'muted small' });
  const table = el('table', { className: 'sheet' });
  const wrap = el('div', { className: 'sheet-wrap' }, table);

  const empty = (row, c) => c.need && !String(row[c.key] || '').trim();
  const gaps = (row) => cols.some((c) => empty(row, c));

  function setDirty(on) {
    dirty = on;
    save.disabled = !on;
    undo.disabled = !on;
    save.textContent = on ? 'Save changes' : 'Saved';
  }

  function updateStatus() {
    const missing = rows.reduce((n, r) => n + cols.filter((c) => empty(r, c)).length, 0);
    status.textContent = `${rows.length} rows` + (missing ? ` · ${missing} highlighted cells to fill` : ' · nothing missing');
  }

  function cell(row, c, r, i) {
    const value = row[c.key] || '';
    let input;
    if (c.type === 'long') {
      input = el('textarea', { rows: 1 });
      input.value = value;
    } else {
      input = el('input', { type: c.type === 'date' || c.type === 'time' ? c.type : 'text', value });
    }
    input.className = 'cell';
    input.setAttribute('aria-label', `${c.label}, row ${r + 1}`);
    input.dataset.r = r;
    input.dataset.i = i;
    if (!editable) input.readOnly = true;
    const td = el('td', { className: 'c-' + c.type + (empty(row, c) ? ' pending' : '') }, input);
    input.addEventListener('input', () => {
      row[c.key] = input.value;
      td.classList.toggle('pending', empty(row, c));
      setDirty(true);
      updateStatus();
    });
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !(c.type === 'long' && e.shiftKey)) {   // Enter: the cell below; Shift+Enter: new line
        e.preventDefault();
        focusCell(r + 1, i);
      }
    });
    input.addEventListener('paste', (e) => {
      const text = (e.clipboardData || window.clipboardData).getData('text');
      if (!editable || !/[\t\n]/.test(text.trim())) return;   // one value: let the browser paste it
      e.preventDefault();
      pasteGrid(text, r, i);
    });
    return td;
  }

  // Rows and columns copied from a spreadsheet arrive as lines of tab-separated values.
  function pasteGrid(text, r0, i0) {
    const lines = text.replace(/\r/g, '').replace(/\n$/, '').split('\n');
    lines.forEach((line, dr) => {
      while (rows.length <= r0 + dr) rows.push({});
      line.split('\t').forEach((value, di) => {
        const c = cols[i0 + di];
        if (c) rows[r0 + dr][c.key] = value.trim();
      });
    });
    setDirty(true);
    render();
    toast(`Pasted ${lines.length} row${lines.length === 1 ? '' : 's'}. Check them, then Save.`);
  }

  function focusCell(r, i) {
    const next = table.querySelector(`.cell[data-r="${r}"][data-i="${i}"]`);
    if (next) next.focus();
    else if (editable && r === rows.length) {
      rows.push({});
      setDirty(true);
      render();
      focusCell(r, i);
    }
  }

  function render() {
    const q = search.value.trim().toLowerCase();
    table.replaceChildren(
      el('thead', {}, el('tr', {}, el('th', { className: 'rn' }, '#'),
        ...cols.map((c) => el('th', { className: 'c-' + c.type }, c.label, c.need ? el('span', { className: 'need', title: 'Needed' }, ' *') : '')),
        editable ? el('th', { className: 'del' }, '') : null)),
      el('tbody', {}, ...rows.map((row, r) => {
        const show = (!q || cols.some((c) => String(row[c.key] || '').toLowerCase().includes(q))) && (!onlyGaps.checked || gaps(row));
        const tr = el('tr', {}, el('td', { className: 'rn' }, String(r + 1)), ...cols.map((c, i) => cell(row, c, r, i)),
          editable ? el('td', { className: 'del' }, el('button', {
            type: 'button', className: 'icon-btn', title: `Delete row ${r + 1}`, 'aria-label': `Delete row ${r + 1}`,
            onclick: () => {
              rows.splice(r, 1);
              setDirty(true);
              render();
            },
          }, '×')) : null);
        tr.hidden = !show;
        return tr;
      })));
    if (!rows.length) {
      table.append(el('tbody', {}, el('tr', {}, el('td', { colspan: String(cols.length + 2), className: 'muted' },
        editable ? 'Nothing here yet. Click "+ Add row", or copy rows from Excel and paste them into a cell.' : 'Nothing here yet.'))));
    }
    updateStatus();
  }

  async function load() {
    const s = await api('GET', `/api/sheets/${name}`);
    cols = s.columns;
    rows = s.rows;
    hint.textContent = s.hint + (editable ? ' Tip: copy rows from Excel and paste them into a cell; Enter goes to the cell below.' : '');
    setDirty(false);
    render();
  }

  save.addEventListener('click', async () => {
    save.disabled = true;
    save.textContent = 'Saving…';
    try {
      const body = { rows: rows.map((r) => Object.fromEntries([['uid', r.uid || ''], ...cols.map((c) => [c.key, r[c.key] || ''])])) };
      const done = await api('PUT', `/api/sheets/${name}`, body);
      toast(`Saved: ${done.added} added, ${done.changed} changed, ${done.removed} removed. The assistant uses it now.`);
      await load();
    } catch (e) {
      showError(e.message);
      setDirty(true);
    }
  });
  undo.addEventListener('click', () => confirm('Throw away the changes you haven\'t saved?') && load());
  add.addEventListener('click', () => {
    rows.push({});
    setDirty(true);
    search.value = '';
    onlyGaps.checked = false;
    render();
    focusCell(rows.length - 1, 0);
    wrap.scrollTop = wrap.scrollHeight;
  });
  search.addEventListener('input', render);
  onlyGaps.addEventListener('change', render);

  box.replaceChildren(hint,
    el('div', { className: 'sheet-tools' }, search,
      el('label', { className: 'muted small' }, onlyGaps, ' Only rows with missing data'), status),
    wrap,
    editable ? el('div', { className: 'row sheet-actions' }, add, el('span', { className: 'grow' }), undo, save) : null);
  return { load, isDirty: () => dirty };
}
