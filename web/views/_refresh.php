<?php $refreshUrl = '?' . http_build_query(array_merge($_GET, ['refresh' => '1'])); ?>
<div class="refresh muted">
  <span>מחירים נכון ל-<b><?= $pricedAt ? h(date('H:i:s', $pricedAt)) : '—' ?></b></span>
  <a class="btn" id="refresh-now" href="<?= h($refreshUrl) ?>">רענן עכשיו</a>
  <label class="inline"><input type="checkbox" id="auto-refresh" data-url="<?= h($refreshUrl) ?>"> רענון אוטומטי כל 15 שניות</label>
  <span id="refresh-count"></span>
  <form method="post" action="?a=fx_set" class="inline" style="display:inline-flex;gap:.3rem;align-items:center">
    <?= csrf_field() ?><input type="hidden" name="back" value="<?= h($_SERVER['REQUEST_URI'] ?? '?p=dashboard') ?>">
    שער: <input name="fx" type="number" step="0.01" inputmode="decimal" size="6" placeholder="auto" value="<?= h((string) ($_SESSION['fx_manual'] ?? '')) ?>">
    <button class="link"><?= !empty($_SESSION['fx_manual']) ? 'בטל ידני' : 'הגדר' ?></button>
  </form>
</div>
<script>
(() => {
  const box = document.getElementById('auto-refresh');
  const count = document.getElementById('refresh-count');
  let end = 0;
  const clear = () => { if (window.__arTimer) { clearInterval(window.__arTimer); window.__arTimer = 0; } };
  let busy = false;
  const refresh = async (silent = false) => {
    if (busy) { end = Date.now() + 15000; return; }
    busy = true;
    const main = document.querySelector('main');
    count.textContent = 'מרענן…';
    if (!silent) { main && main.classList.add('refreshing'); }
    try {
      const res = await fetch(box.dataset.url);
      const doc = new DOMParser().parseFromString(await res.text(), 'text/html');
      const newMain = doc.querySelector('main');
      const oldMain = document.querySelector('main');
      if (!newMain || !oldMain) throw 0;
      clear();
      const keep = [...oldMain.querySelectorAll('[data-keep]')].map(k => [k.id, k]);
      oldMain.innerHTML = newMain.innerHTML;
      keep.forEach(([id, k]) => {
        const slot = document.getElementById(id);
        if (slot) slot.replaceWith(k);
      });
      window.lwReapply && window.lwReapply();
      oldMain.classList.remove('refreshing');
      count.textContent = '';
      oldMain.querySelectorAll('script').forEach(s => {
        const ns = document.createElement('script');
        ns.textContent = s.textContent;
        s.replaceWith(ns);
      });
      window.updateOrderBadge && window.updateOrderBadge();
    } catch (e) {
      main && main.classList.remove('refreshing');
      count.textContent = '';
      location.href = box.dataset.url;
    } finally {
      busy = false;
    }
  };
  document.getElementById('refresh-now').addEventListener('click', e => {
    e.preventDefault();
    if (!document.querySelector('.overlay:not([hidden])')) { clear(); refresh(false); }
  });
  const tick = () => {
    const s = Math.ceil((end - Date.now()) / 1000);
    if (s <= 0) {
      if (document.querySelector('.overlay:not([hidden])')) { end = Date.now() + 15000; return; }
      clear(); refresh(true); return;
    }
    count.textContent = 'רענון בעוד ' + s + ' שנ׳';
  };
  const arm = () => {
    clear();
    count.textContent = '';
    if (box.checked) { end = Date.now() + 15000; window.__arTimer = setInterval(tick, 250); tick(); }
  };
  box.checked = localStorage.getItem('autoRefresh') === '1';
  box.addEventListener('change', () => { localStorage.setItem('autoRefresh', box.checked ? '1' : '0'); arm(); });
  arm();
})();
</script>
