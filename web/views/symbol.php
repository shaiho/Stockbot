<?php
$labels = ['buy' => 'קנייה', 'sell' => 'מכירה', 'dividend' => 'דיבידנד'];
$alertLabels = [
    'pct_daily' => 'תזוזה יומית (%)', 'price_target' => 'מחיר יעד', 'premarket' => 'פרה-מרקט (%)',
    'afterhours' => 'אפטר-מרקט (%)', 'volume_spike' => 'זינוק בנפח', 'news' => 'חדשות',
    'portfolio_value_change' => 'שינוי בשווי התיק (%)', 'daily_loss_limit' => 'הפסד יומי (%)', 'pnl_milestone' => 'יעד רווח/הפסד (₪)',
];
$cur = $market === 'IL' ? 'ILS' : 'USD';
$totQty = 0.0;
$totValue = 0.0;
$totPnl = 0.0;
foreach ($byPortfolio as $r) {
    $totQty += $r['pnl']['quantity'];
    if ($r['pnl']['price'] !== null) {
        $totValue += $r['pnl']['quantity'] * $r['pnl']['price'];
    }
    $totPnl += $r['pnl']['realized'] + $r['pnl']['unrealized'];
}
?>
<div class="head">
  <h1><?= h($symbol) ?> <small class="muted"><?= h($market) ?></small></h1>
  <a href="?p=dashboard">← כל התיקים</a>
</div>
<?php require __DIR__ . '/_refresh.php'; ?>

<div class="stats">
  <div class="card"><span>מחיר</span><b><?= $quote ? money($quote['price'], $cur) : '—' ?></b><small><?= session_badge($quote['session'] ?? null) ? trim(strip_tags(session_badge($quote['session'] ?? null))) : ($quote ? 'מסחר רגיל' : 'אין ציטוט') ?></small></div>
  <div class="card"><span>שינוי יומי</span><b class="<?= tone($quote['change_pct'] ?? null) ?>"><?= $quote ? pct($quote['change_pct']) : '—' ?></b><small>סגירה קודמת <?= isset($quote['prev_close']) ? money($quote['prev_close'], $cur) : '—' ?></small></div>
  <div class="card"><span>כמות מוחזקת</span><b><?= qty($totQty) ?></b><small>ב-<?= count($byPortfolio) ?> תיקים</small></div>
  <div class="card"><span>שווי החזקה</span><b><?= money($totValue, $cur) ?></b><small><?= money(Calc::toIls($totValue, $cur, $fx)) ?></small></div>
  <div class="card"><span>רווח/הפסד בנייר</span><b class="<?= tone($totPnl) ?>"><?= money($totPnl, $cur, true) ?></b><small><?= money(Calc::toIls($totPnl, $cur, $fx), 'ILS', true) ?> ממומש + לא ממומש</small></div>
</div>

<?php if ($watch || $alerts || $orders): ?>
<p>
  <?php if ($watch): ?><span class="chip">ברשימת מעקב (<?= h($watch[0]['market']) ?>)</span><?php endif; ?>
  <?php foreach ($alerts as $a): ?>
    <span class="chip"><?= h($alertLabels[$a['alert_type']] ?? $a['alert_type']) ?><?= $a['enabled'] ? '' : ' · כבוי' ?></span>
  <?php endforeach; ?>
  <?php foreach ($orders as $o): ?>
    <a class="chip" href="?p=orders">הוראה #<?= $o['id'] ?> · <?= $o['action'] === 'buy' ? 'קנייה' : 'מכירה' ?> <?= qty($o['quantity']) ?> @ <?= money($o['limit_price'], $o['currency']) ?> · <?= h(['open' => 'פתוחה', 'executed' => 'בוצעה', 'expired' => 'פקעה', 'cancelled' => 'בוטלה'][$o['status']] ?? $o['status']) ?></a>
  <?php endforeach; ?>
</p>
<?php endif; ?>

<section>
  <h2>גרף מחיר</h2>
  <div class="filter muted">
    <button type="button" class="link chart-range" data-range="1d">יום</button>
    <button type="button" class="link chart-range" data-range="5d">5 ימים</button>
    <button type="button" class="link chart-range" data-range="1mo">חודש</button>
  </div>
  <div id="price-chart" style="width:100%;max-width:900px"></div>
</section>

<script>
(() => {
  const box = document.getElementById('price-chart');
  const sym = <?= json_encode($symbol) ?>, mkt = <?= json_encode($market) ?>;
  const draw = async (range) => {
    box.textContent = 'טוען…';
    const pts = await (await fetch(`?p=chart&symbol=${sym}&market=${mkt}&range=${range}`)).json();
    if (!pts.length) { box.textContent = 'אין נתונים'; return; }
    const W = 900, H = 260, pad = 40;
    const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    const px = t => pad + (t - x0) / (x1 - x0 || 1) * (W - pad - 10);
    const py = v => H - 10 - (v - y0) / (y1 - y0 || 1) * (H - pad);
    const path = pts.map((p, i) => (i ? 'L' : 'M') + px(p[0]).toFixed(1) + ' ' + py(p[1]).toFixed(1)).join(' ');
    const fmt = v => (v >= 100 ? v.toFixed(1) : v.toFixed(2));
    const color = ys[ys.length - 1] >= ys[0] ? '#16a34a' : '#dc2626';
    let grid = '';
    for (let i = 0; i <= 4; i++) {
      const v = y0 + (y1 - y0) * i / 4, y = py(v);
      grid += `<line x1="${pad}" y1="${y}" x2="${W}" y2="${y}" stroke="#e5e7eb"/><text x="2" y="${y + 4}" font-size="11" fill="#6b7280">${fmt(v)}</text>`;
    }
    const d0 = new Date(x0 * 1000), d1 = new Date(x1 * 1000);
    const fd = d => d.toLocaleDateString('he-IL', { day: 'numeric', month: 'numeric' });
    box.innerHTML = `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto;direction:ltr">` + grid +
      `<text x="${W}" y="${H - 14}" font-size="11" fill="#6b7280" text-anchor="end">${fd(d0)}</text>` +
      `<text x="${pad}" y="${H - 14}" font-size="11" fill="#6b7280">${fd(d1)}</text>` +
      `<path d="${path}" fill="none" stroke="${color}" stroke-width="1.5"/></svg>`;
  };
  document.querySelectorAll('.chart-range').forEach(b => b.addEventListener('click', () => draw(b.dataset.range)));
  draw('1mo');
})();
</script>

<?php if (!$byPortfolio): ?>
  <p class="muted">אין עסקאות על הנייר במערכת.</p>
<?php endif; ?>

<?php foreach ($byPortfolio as $pid => $r): $pnl = $r['pnl']; $c = $pnl['currency']; ?>
<section>
  <h2><a href="?p=portfolio&id=<?= $pid ?>"><?= h($r['name']) ?></a></h2>
  <div class="scroll"><table>
    <thead><tr><th>כמות</th><th>עלות ממוצעת</th><th>שווי</th><th>שינוי יומי</th><th>שינוי מקנייה</th><th>שינוי מקנייה %</th><th>ממומש</th><th>עמלות</th></tr></thead>
    <tbody><tr>
      <td><?= qty($pnl['quantity']) ?></td>
      <td><?= $pnl['avg_cost'] > 0 ? money($pnl['avg_cost'], $c) : '—' ?></td>
      <td><?= $pnl['price'] === null ? '—' : money($pnl['quantity'] * $pnl['price'], $c) ?></td>
      <td class="<?= tone($pnl['daily']) ?>"><?= $pnl['daily'] === null ? '—' : money($pnl['daily'], $c, true) ?></td>
      <td class="<?= tone($pnl['unrealized']) ?>"><?= $pnl['price'] === null ? '—' : money($pnl['unrealized'], $c, true) ?></td>
      <td class="<?= tone($pnl['unrealized_pct']) ?>"><?= pct($pnl['unrealized_pct']) ?></td>
      <td class="<?= tone($pnl['realized']) ?>"><?= money($pnl['realized'], $c, true) ?></td>
      <td><?= money($pnl['commissions'], $c) ?></td>
    </tr></tbody>
  </table></div>

  <div class="scroll"><table>
    <thead><tr><th>#</th><th>תאריך</th><th>פעולה</th><th>כמות</th><th>מחיר</th><th>עמלה</th><th>הערה</th><th></th></tr></thead>
    <tbody>
    <?php foreach (array_reverse($r['trades']) as $t): ?>
      <tr>
        <td><?= $t['id'] ?></td>
        <td><?= h(local_dt($t['ts'])) ?></td>
        <td><?= h($labels[$t['action']] ?? $t['action']) ?></td>
        <td><?= $t['action'] === 'dividend' ? '' : qty($t['quantity']) ?></td>
        <td><?= money($t['price'], $t['currency']) ?></td>
        <td><?= $t['commission'] > 0 ? money($t['commission'], $t['currency']) : '' ?></td>
        <td class="muted"><?= h($t['note']) ?></td>
        <td class="actions"><a href="?p=trade&id=<?= $t['id'] ?>">ערוך</a></td>
      </tr>
    <?php endforeach; ?>
    </tbody>
  </table></div>
</section>
<?php endforeach; ?>
