// Click-to-sort for <table class="sortable"> — numeric-aware, re-run safe.
(() => {
  const num = s => {
    const m = s.replace(/[^\d.\-+]/g, '');
    return m !== '' && !isNaN(+m) ? +m : null;
  };
  const bind = table => {
    if (table.__sorted) return;
    table.__sorted = true;
    const heads = table.tHead && table.tHead.rows[0] ? [...table.tHead.rows[0].cells] : [];
    heads.forEach((th, col) => {
      th.style.cursor = 'pointer';
      th.title = 'מיון';
      th.addEventListener('click', () => {
        const body = table.tBodies[0];
        if (!body) return;
        const rows = [...body.rows];
        const numeric = rows.some(r => num(r.cells[col]?.textContent || '') !== null);
        const dir = th.__dir === 'asc' ? -1 : 1;
        th.__dir = dir === 1 ? 'asc' : 'desc';
        heads.forEach(h => h.classList.remove('sort-asc', 'sort-desc'));
        th.classList.add(dir === 1 ? 'sort-asc' : 'sort-desc');
        rows.sort((a, b) => {
          const x = a.cells[col]?.textContent.trim() || '', y = b.cells[col]?.textContent.trim() || '';
          if (numeric) return ((num(x) ?? -Infinity) - (num(y) ?? -Infinity)) * dir;
          return x.localeCompare(y, 'he') * dir;
        });
        rows.forEach(r => body.appendChild(r));
      });
    });
  };
  const init = () => document.querySelectorAll('table.sortable').forEach(bind);
  init();
  new MutationObserver(init).observe(document.body, { childList: true, subtree: true });
})();
