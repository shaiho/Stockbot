<div class="head"><h1>רשימת מעקב</h1></div>
<?php if ($items) { require __DIR__ . '/_refresh.php'; } ?>

<?php if (!$items): ?>
  <p class="muted">הרשימה ריקה.</p>
<?php else: ?>
<div class="scroll"><table>
  <thead><tr><th>סימול</th><th>שוק</th><th>מחיר</th><th>שינוי יומי</th><th>5 ימים</th><th></th></tr></thead>
  <tbody>
  <?php foreach ($items as $i): $q = $quotes[Prices::key($i['symbol'], $i['market'])] ?? null; $c = $i['market'] === 'IL' ? 'ILS' : 'USD'; ?>
    <tr>
      <td><a href="?p=symbol&symbol=<?= h($i['symbol']) ?>&market=<?= h($i['market']) ?>"><b><?= h($i['symbol']) ?></b></a></td>
      <td><?= h($i['market']) ?></td>
      <td><?= $q ? money($q['price'], $c) . session_badge($q['session'] ?? null) : '—' ?></td>
      <td class="<?= tone($q['change_pct'] ?? null) ?>"><?= $q ? pct($q['change_pct']) : '—' ?></td>
      <td><span class="spark" data-symbol="<?= h($i['symbol']) ?>" data-market="<?= h($i['market']) ?>"></span></td>
      <td class="actions"><form method="post" action="?a=watch_remove"><?= csrf_field() ?><input type="hidden" name="id" value="<?= $i['id'] ?>"><button class="link danger">הסר</button></form></td>
    </tr>
  <?php endforeach; ?>
  </tbody>
</table></div>
<script>
(() => {
document.querySelectorAll('.spark').forEach(async el => {
  try {
    const pts = await (await fetch(`?p=chart&symbol=${encodeURIComponent(el.dataset.symbol)}&market=${el.dataset.market}&range=5d`)).json();
    if (pts.length < 2) return;
    const ys = pts.map(p => p[1]), y0 = Math.min(...ys), y1 = Math.max(...ys);
    const d = pts.map((p, i) => (i ? 'L' : 'M') + (i / (pts.length - 1) * 96 + 2).toFixed(1) + ' ' + (26 - (p[1] - y0) / (y1 - y0 || 1) * 22).toFixed(1)).join(' ');
    const up = ys[ys.length - 1] >= ys[0];
    el.innerHTML = `<svg viewBox="0 0 100 28" style="width:100px;height:28px;direction:ltr"><path d="${d}" fill="none" stroke="${up ? '#16a34a' : '#dc2626'}" stroke-width="1.5"/></svg>`;
  } catch (e) {}
});
})();
</script>
<?php endif; ?>

<form class="card form" method="post" action="?a=watch_add">
  <h2>הוסף למעקב</h2>
  <?= csrf_field() ?>
  <label>סימול <input name="symbol" required placeholder="AAPL / TEVA.TA"></label>
  <label>שוק <select name="market"><option value="">אוטומטי</option><option value="US">US</option><option value="IL">IL</option></select></label>
  <button class="primary">הוסף</button>
</form>
