<?php $refreshUrl = '?' . http_build_query(array_merge($_GET, ['refresh' => '1'])); ?>
<div class="refresh muted">
  <span>מחירים נכון ל-<b><?= $pricedAt ? h(date('H:i:s', $pricedAt)) : '—' ?></b></span>
  <a class="btn" href="<?= h($refreshUrl) ?>">רענן עכשיו</a>
  <label class="inline"><input type="checkbox" id="auto-refresh" data-url="<?= h($refreshUrl) ?>"> רענון אוטומטי כל 30 שניות</label>
</div>
<script>
(() => {
  const box = document.getElementById('auto-refresh');
  let t;
  const arm = () => { clearTimeout(t); if (box.checked) t = setTimeout(() => { location.href = box.dataset.url; }, 30000); };
  box.checked = localStorage.getItem('autoRefresh') === '1';
  box.addEventListener('change', () => { localStorage.setItem('autoRefresh', box.checked ? '1' : '0'); arm(); });
  arm();
})();
</script>
