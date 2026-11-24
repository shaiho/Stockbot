<?php
$labels = ['buy' => 'קנייה', 'sell' => 'מכירה', 'dividend' => 'דיבידנד'];
$alertLabels = [
    'pct_daily' => 'תזוזה יומית (%)', 'price_target' => 'מחיר יעד', 'premarket' => 'פרה-מרקט (%)',
    'afterhours' => 'אפטר-מרקט (%)', 'volume_spike' => 'זינוק בנפח', 'news' => 'חדשות',
    'portfolio_value_change' => 'שינוי בשווי התיק (%)', 'daily_loss_limit' => 'הפסד יומי (%)', 'pnl_milestone' => 'יעד רווח/הפסד (₪)',
];
$cur = $market === 'IL' ? 'ILS' : 'USD';
$tradeMarks = [];
foreach ($byPortfolio as $r) {
    foreach ($r['trades'] as $t) {
        if (in_array($t['action'], ['buy', 'sell'], true)) {
            $tradeMarks[] = ['ts' => $t['ts']->getTimestamp(), 'action' => $t['action'], 'price' => $t['price'], 'qty' => $t['quantity'], 'date' => local_dt($t['ts'], 'd/m/Y')];
        }
    }
}
$totQty = 0.0;
$totValue = 0.0;
$totPnl = 0.0;
$avgCost = 0.0;
$avgQty = 0.0;
foreach ($byPortfolio as $r) {
    if ($r['pnl']['quantity'] > 1e-9 && $r['pnl']['avg_cost'] > 0) {
        $avgCost += $r['pnl']['avg_cost'] * $r['pnl']['quantity'];
        $avgQty += $r['pnl']['quantity'];
    }
    $totQty += $r['pnl']['quantity'];
    if ($r['pnl']['price'] !== null) {
        $totValue += $r['pnl']['quantity'] * $r['pnl']['price'];
    }
    $totPnl += $r['pnl']['realized'] + $r['pnl']['unrealized'];
}
$avgCost = $avgQty > 1e-9 ? $avgCost / $avgQty : 0.0;
?>
<div class="head">
  <h1><?= h($symbol) ?> <small class="muted"><?= h($market) ?></small></h1>
  <a href="?p=dashboard">← כל התיקים</a>
</div>
<p>
  <button type="button" class="link" id="open-quick" data-kind="trade_add">+ עסקה</button>
  <button type="button" class="link" id="open-quick-order" data-kind="order_add">הוראה</button>
  <?php if (!$watch): ?>
  <form method="post" action="?a=watch_add" class="inline"><?= csrf_field() ?><input type="hidden" name="symbol" value="<?= h($symbol) ?>"><input type="hidden" name="market" value="<?= h($market) ?>"><input type="hidden" name="back" value="<?= h($_SERVER['REQUEST_URI']) ?>"><button class="link">+ מעקב</button></form>
  <?php endif; ?>
</p>
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
  <h2>גרף מחיר <small id="schart-legend" class="muted"></small></h2>
  <div class="filter muted">
    <button type="button" class="link chart-range" data-range="1d">יום</button>
    <button type="button" class="link chart-range" data-range="5d">5 ימים</button>
    <button type="button" class="link chart-range" data-range="1mo">חודש</button>
  </div>
  <div id="price-chart" class="lchart"></div>
</section>

<script>
(() => {
  const box = document.getElementById('price-chart');
  const sym = <?= json_encode($symbol) ?>, mkt = <?= json_encode($market) ?>;
  const trades = <?= json_encode($tradeMarks) ?>;
  const avgCost = <?= json_encode($avgCost) ?>;
  const cur = mkt === 'IL' ? '₪' : '$';
  const tz = mkt === 'IL' ? 'Asia/Jerusalem' : 'America/New_York';
  const pf = v => cur + (v >= 100 ? v.toFixed(1) : v.toFixed(2));
  let range = '1mo';
  const intra = () => range !== '1mo';
  const fmtT = ts => new Date(ts * 1000).toLocaleString('he-IL', intra()
    ? { timeZone: tz, day: 'numeric', month: 'numeric', hour: '2-digit', minute: '2-digit' }
    : { timeZone: tz, day: 'numeric', month: 'numeric', year: '2-digit' });
  const chart = mkChart(box, {
    localization: { locale: 'he-IL', timeFormatter: fmtT },
    timeScale: { timeVisible: true, secondsVisible: false, tickMarkFormatter: fmtT, borderColor: '#e5e7eb', rightOffset: 2 },
  });
  const series = chart.addAreaSeries({
    lineWidth: 2, lineColor: '#2563eb', topColor: 'rgba(37,99,235,.22)', bottomColor: 'rgba(37,99,235,0)',
    priceFormat: { type: 'custom', formatter: pf, minMove: 0.01 },
  });
  let avgLine = null;
  const legend = document.getElementById('schart-legend');
  chart.subscribeCrosshairMove(p => {
    if (!legend) return;
    const v = p.seriesData && p.seriesData.get(series);
    legend.textContent = v !== undefined && p.time !== undefined ? fmtT(p.time) + ' · ' + pf(v.value !== undefined ? v.value : v) : '';
  });
  const draw = async r => {
    range = r;
    box.style.opacity = '.4';
    let pts = [];
    try {
      pts = await (await fetch(`?p=chart&symbol=${sym}&market=${mkt}&range=${range}`)).json();
    } finally {
      box.style.opacity = '';
    }
    const data = pts.map(p => ({ time: p[0], value: p[1] })).sort((a, b) => a.time - b.time);
    series.setData(data);
    const tset = data.map(d => d.time);
    const nearest = t => tset.reduce((best, x) => Math.abs(x - t) < Math.abs(best - t) ? x : best, tset[0]);
    const groups = {};
    trades.forEach(tr => {
      if (!tset.length || tr.ts < tset[0] - 172800 || tr.ts > tset[tset.length - 1] + 172800) return;
      const k = nearest(tr.ts);
      (groups[k] = groups[k] || []).push(tr);
    });
    const markers = [];
    Object.entries(groups).forEach(([t, arr]) => {
      const buys = arr.filter(x => x.action === 'buy'), sells = arr.filter(x => x.action !== 'buy');
      if (buys.length) markers.push({ time: +t, position: 'belowBar', color: '#16a34a', shape: 'arrowUp', text: 'קניה ' + buys.length });
      if (sells.length) markers.push({ time: +t, position: 'aboveBar', color: '#dc2626', shape: 'arrowDown', text: 'מכירה ' + sells.length });
    });
    markers.sort((a, b) => a.time - b.time);
    series.setMarkers(markers);
    if (avgLine) { series.removePriceLine(avgLine); avgLine = null; }
    const ys = pts.map(p => p[1]);
    if (avgCost > Math.min(...ys) && avgCost < Math.max(...ys)) {
      avgLine = series.createPriceLine({ price: avgCost, color: '#7c3aed', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true, title: 'עלות ממוצעת' });
    }
    chart.timeScale().fitContent();
  };
  document.querySelectorAll('.chart-range').forEach(b => b.addEventListener('click', () => draw(b.dataset.range)));
  draw('1mo');
})();
</script>

<?php
$today = date('Y-m-d');
$upDiv = array_values(array_filter($events['dividends'], fn($e) => $e['date'] >= $today));
$upSplit = array_values(array_filter($events['splits'], fn($e) => $e['date'] >= $today));
$pastDiv = array_values(array_filter($events['dividends'], fn($e) => $e['date'] < $today));
$pastSplit = array_values(array_filter($events['splits'], fn($e) => $e['date'] < $today));
?>
<?php if ($upDiv || $upSplit): ?>
<section>
  <h2>אירועים קרובים</h2>
  <p>
    <?php foreach ($upDiv as $e): ?>
      <span class="chip warn">דיבידנד · <?= h($e['date']) ?> · <?= number_format($e['amount'], 4) ?></span>
    <?php endforeach; ?>
    <?php foreach ($upSplit as $e): ?>
      <span class="chip warn">פיצול <?= h((string) $e['ratio']) ?> · <?= h($e['date']) ?></span>
    <?php endforeach; ?>
  </p>
</section>
<?php endif; ?>
<?php if ($pastDiv || $pastSplit): ?>
<section>
  <h2>אירועים בשנה האחרונה</h2>
  <p>
    <?php foreach (array_reverse($pastDiv) as $e): ?>
      <span class="chip">דיבידנד · <?= h($e['date']) ?> · <?= number_format($e['amount'], 4) ?></span>
    <?php endforeach; ?>
    <?php foreach (array_reverse($pastSplit) as $e): ?>
      <span class="chip">פיצול <?= h((string) $e['ratio']) ?> · <?= h($e['date']) ?></span>
    <?php endforeach; ?>
  </p>
</section>
<?php endif; ?>

<div id="sq-overlay" class="overlay" hidden>
  <form class="card form" method="post" id="sq-form">
    <h2><span id="sq-title"></span> — <?= h($symbol) ?></h2>
    <?= csrf_field() ?>
    <input type="hidden" name="symbol" value="<?= h($symbol) ?>">
    <input type="hidden" name="market" value="<?= h($market) ?>">
    <label>תיק
      <select name="portfolio_id"><?php foreach ($portfolios as $pp): ?><option value="<?= $pp['id'] ?>"><?= h($pp['name']) ?></option><?php endforeach; ?></select>
    </label>
    <label>פעולה <select name="action_type"><option value="buy">קנייה</option><option value="sell">מכירה</option></select></label>
    <label>כמות <input name="quantity" inputmode="decimal" required></label>
    <label><span id="sq-price-label">מחיר ליחידה</span> <input name="price" inputmode="decimal" value="<?= h((string) ($quote['price'] ?? '')) ?>" required></label>
    <label id="sq-expires" hidden>בתוקף עד <input type="date" name="expires" value="<?= date('Y-m-d') ?>" min="<?= date('Y-m-d') ?>"></label>
    <button class="primary">שמור</button> <button type="button" id="sq-cancel">ביטול</button>
  </form>
</div>
<script>
(() => {
const sq = document.getElementById('sq-overlay'), sqForm = document.getElementById('sq-form');
const openSq = (kind) => {
  document.getElementById('sq-title').textContent = kind === 'order_add' ? 'הוראת לימיט' : 'עסקה מהירה';
  document.getElementById('sq-price-label').textContent = kind === 'order_add' ? 'מחיר יעד ליחידה' : 'מחיר ליחידה';
  document.getElementById('sq-expires').hidden = kind !== 'order_add';
  sqForm.action = '?a=' + kind;
  sq.hidden = false;
  sq.querySelector('[name=quantity]').focus();
};
document.getElementById('open-quick').addEventListener('click', () => openSq('trade_add'));
document.getElementById('open-quick-order').addEventListener('click', () => openSq('order_add'));
document.getElementById('sq-cancel').addEventListener('click', () => { sq.hidden = true; });
})();
</script>

<?php if (!$byPortfolio): ?>
  <p class="muted">אין עסקאות על הנייר במערכת.</p>
<?php endif; ?>

<?php foreach ($byPortfolio as $pid => $r): $pnl = $r['pnl']; $c = $pnl['currency']; ?>
<section>
  <h2><a href="?p=portfolio&id=<?= $pid ?>"><?= h($r['name']) ?></a></h2>
  <div class="scroll"><table>
    <thead><tr><th>כמות</th><th>עלות ממוצעת</th><th>שווי</th><th>שינוי יומי</th><th>שינוי מקנייה</th><th>שינוי מקנייה %</th><th>ממומש</th><th>עמלות</th><th>דיבידנדים</th></tr></thead>
    <tbody><tr>
      <td><?= qty($pnl['quantity']) ?></td>
      <td><?= $pnl['avg_cost'] > 0 ? money($pnl['avg_cost'], $c) : '—' ?></td>
      <td><?= $pnl['price'] === null ? '—' : money($pnl['quantity'] * $pnl['price'], $c) ?></td>
      <td class="<?= tone($pnl['daily']) ?>"><?= $pnl['daily'] === null ? '—' : money($pnl['daily'], $c, true) ?></td>
      <td class="<?= tone($pnl['unrealized']) ?>"><?= $pnl['price'] === null ? '—' : money($pnl['unrealized'], $c, true) ?></td>
      <td class="<?= tone($pnl['unrealized_pct']) ?>"><?= pct($pnl['unrealized_pct']) ?></td>
      <td class="<?= tone($pnl['realized']) ?>"><?= money($pnl['realized'], $c, true) ?></td>
      <td><?= money($pnl['commissions'], $c) ?></td>
      <td>
        <?php if ($pnl['div_count']): ?>
          <?= money($pnl['div_total'], $c) ?>
          <?php if ($pnl['div_yield_cost'] !== null): ?>(<?= number_format($pnl['div_yield_cost'], 1) ?>% על עלות)<?php endif; ?>
          <br><small class="muted"><?= $pnl['div_count'] ?> חלוקות<?php if ($pnl['div_last']): ?> · אחרון <?= h($pnl['div_last']['date']) ?> · <?= money($pnl['div_last']['amount'], $c) ?> על <?= qty($pnl['div_last']['qty']) ?> יח'<?php endif; ?></small>
        <?php else: ?>—<?php endif; ?>
      </td>
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
