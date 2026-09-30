// Dropdown mit Suche, im Stil der TreuFlow-Combobox (Panel, Suchfeld, Häkchen,
// Tastatur). Das Original-<select> bleibt als Wertspeicher im DOM: aller
// bestehende Code liest und setzt weiterhin select.value und hört auf
// «change». Wer den Wert per Code setzt, löst danach «change» aus, dann zieht
// die Anzeige nach.
//
//   Combobox.enhance(select, { search: true, placeholder: 'Kasse suchen…',
//                              keywords: value => 'zusätzliche Suchbegriffe' })
(function () {
  const norm = s => (s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  const CHEV = '<svg class="cbx-chev" viewBox="0 0 12 12" aria-hidden="true"><path d="M3 4.5l3 3 3-3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  const SEARCH = '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="7" cy="7" r="4.5" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M10.5 10.5L14 14" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>';
  const CHECK = '<svg class="cbx-check" viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 8.5l3 3 6-7" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  let openCombo = null;

  function enhance(select, opts) {
    if (!select || select._combo) return select && select._combo;
    opts = opts || {};
    const wrap = document.createElement('div');
    wrap.className = 'cbx';
    select.parentNode.insertBefore(wrap, select);
    wrap.appendChild(select);
    select.style.display = 'none';

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'cbx-trigger';
    btn.id = select.id + '-cbx';
    btn.setAttribute('aria-haspopup', 'listbox');
    btn.setAttribute('aria-expanded', 'false');
    btn.innerHTML = '<span class="cbx-value"></span>' + CHEV;
    wrap.appendChild(btn);
    const lbl = select.id && document.querySelector('label[for="' + select.id + '"]');
    if (lbl) lbl.htmlFor = btn.id;

    let panel = null, list = null, input = null, rows = [], active = -1;

    function sync() {
      const o = select.selectedOptions[0];
      const v = btn.querySelector('.cbx-value');
      v.textContent = o ? o.textContent : '';
      v.classList.toggle('cbx-placeholder', !select.value);
    }

    function split(text) {
      const m = text.match(/^(.*?)\s*\((.*)\)\s*$/);
      return m ? [m[1], m[2]] : [text, ''];
    }

    function render(q) {
      const nq = norm(q);
      list.innerHTML = '';
      rows = [];
      // Treffer am Wortanfang zuerst: «swi» soll Swica vor Wädenswil zeigen
      const rank = o => {
        if (!nq) return 0;
        const hay = norm(o.textContent + ' ' + (opts.keywords ? opts.keywords(o.value) : ''));
        if (!hay.includes(nq)) return -1;
        if (hay.startsWith(nq)) return 0;
        return hay.split(/[\s(\-\/]+/).some(w => w.startsWith(nq)) ? 1 : 2;
      };
      const matches = [...select.options].map(o => [o, rank(o)]).filter(([, r]) => r >= 0)
        .sort((a, b) => a[1] - b[1]).map(([o]) => o);
      matches.forEach(o => {
        const [main, sub] = split(o.textContent);
        const row = document.createElement('button');
        row.type = 'button';
        row.className = 'cbx-row' + (o.value === select.value ? ' selected' : '');
        row.setAttribute('role', 'option');
        row.innerHTML = '<span class="cbx-text"><span class="cbx-main"></span>' + (sub ? '<span class="cbx-sub"></span>' : '') + '</span>' + (o.value === select.value ? CHECK : '');
        row.querySelector('.cbx-main').textContent = main;
        if (sub) row.querySelector('.cbx-sub').textContent = sub;
        row.addEventListener('mousedown', e => e.preventDefault());
        row.addEventListener('click', () => choose(o.value));
        list.appendChild(row);
        rows.push({ row, value: o.value });
      });
      if (!rows.length) list.innerHTML = '<div class="cbx-empty">Nichts gefunden</div>';
      active = rows.findIndex(r => r.value === select.value);
      if (active < 0 && rows.length) active = 0;
      highlight();
    }

    function highlight() {
      rows.forEach((r, i) => r.row.classList.toggle('active', i === active));
      if (rows[active]) rows[active].row.scrollIntoView({ block: 'nearest' });
    }

    function place() {
      const r = btn.getBoundingClientRect();
      const w = Math.min(Math.max(r.width, 230), window.innerWidth - 16);
      let left = Math.min(r.left, window.innerWidth - w - 8);
      panel.style.width = w + 'px';
      panel.style.left = Math.max(8, left) + 'px';
      const below = window.innerHeight - r.bottom;
      const h = panel.offsetHeight;
      panel.style.top = (below < h + 12 && r.top > h + 12 ? r.top - h - 6 : r.bottom + 6) + 'px';
    }

    function open() {
      if (openCombo && openCombo !== api) openCombo.close();
      panel = document.createElement('div');
      panel.className = 'cbx-panel';
      panel.setAttribute('role', 'listbox');
      if (opts.search) {
        panel.innerHTML = '<label class="cbx-search">' + SEARCH + '<input type="text" autocomplete="off"></label>';
        input = panel.querySelector('input');
        input.placeholder = opts.placeholder || 'Suchen…';
        input.addEventListener('input', () => render(input.value));
        input.addEventListener('keydown', keys);
      }
      list = document.createElement('div');
      list.className = 'cbx-list';
      panel.appendChild(list);
      document.body.appendChild(panel);
      render('');
      place();
      btn.setAttribute('aria-expanded', 'true');
      openCombo = api;
      (input || btn).focus();
      setTimeout(() => document.addEventListener('mousedown', outside), 0);
      window.addEventListener('resize', close);
      window.addEventListener('scroll', onScroll, true);
    }

    function close() {
      if (!panel) return;
      panel.remove();
      panel = list = input = null;
      btn.setAttribute('aria-expanded', 'false');
      document.removeEventListener('mousedown', outside);
      window.removeEventListener('resize', close);
      window.removeEventListener('scroll', onScroll, true);
      if (openCombo === api) openCombo = null;
    }

    function onScroll(e) { if (panel && !panel.contains(e.target)) place(); }
    function outside(e) { if (panel && !panel.contains(e.target) && !wrap.contains(e.target)) close(); }

    function choose(v) {
      const changed = select.value !== v;
      select.value = v;
      sync();
      close();
      btn.focus();
      if (changed) select.dispatchEvent(new Event('change', { bubbles: true }));
    }

    function keys(e) {
      if (e.key === 'ArrowDown') { e.preventDefault(); active = Math.min(rows.length - 1, active + 1); highlight(); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); active = Math.max(0, active - 1); highlight(); }
      else if (e.key === 'Enter') { e.preventDefault(); if (rows[active]) choose(rows[active].value); }
      else if (e.key === 'Escape') { e.preventDefault(); close(); btn.focus(); }
      else if (e.key === 'Tab') close();
    }

    btn.addEventListener('click', () => (panel ? close() : open()));
    btn.addEventListener('keydown', e => {
      if (!panel && ['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(e.key)) { e.preventDefault(); open(); }
      else if (panel) keys(e);
    });
    select.addEventListener('change', sync);
    sync();

    const api = { sync, close, open };
    select._combo = api;
    return api;
  }

  window.Combobox = { enhance };
})();
