<?php $refreshUrl = '?' . http_build_query(array_merge($_GET, ['refresh' => '1'])); ?>
<div class="refresh muted">
  <span>מחירים נכון ל-<b><?= $pricedAt ? h(date('H:i:s', $pricedAt)) : '—' ?></b></span>
  <a class="btn" href="<?= h($refreshUrl) ?>">רענן עכשיו</a>
  <label class="inline"><input type="checkbox" id="auto-refresh" data-url="<?= h($refreshUrl) ?>"> רענון אוטומטי כל 30 שניות</label>
  <span id="refresh-count"></span>
</div>
<script>
(() => {
  const box = document.getElementById('auto-refresh');
  const count = document.getElementById('refresh-count');
  let end = 0, timer;
  const tick = () => {
    const s = Math.ceil((end - Date.now()) / 1000);
    if (s <= 0) { location.href = box.dataset.url; return; }
    count.textContent = 'רענון בעוד ' + s + ' שנ׳';
  };
  const arm = () => {
    clearInterval(timer);
    count.textContent = '';
    if (box.checked) { end = Date.now() + 30000; timer = setInterval(tick, 250); tick(); }
  };
  box.checked = localStorage.getItem('autoRefresh') === '1';
  box.addEventListener('change', () => { localStorage.setItem('autoRefresh', box.checked ? '1' : '0'); arm(); });
  arm();
})();
</script>
