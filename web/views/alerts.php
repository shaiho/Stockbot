<?php
$typeLabels = [
    'pct_daily' => 'תזוזה יומית (%)', 'price_target' => 'מחיר יעד', 'premarket' => 'פרה-מרקט (%)',
    'afterhours' => 'אפטר-מרקט (%)', 'volume_spike' => 'זינוק בנפח', 'news' => 'חדשות',
    'portfolio_value_change' => 'שינוי בשווי התיק (%)', 'daily_loss_limit' => 'הפסד יומי (%)', 'pnl_milestone' => 'יעד רווח/הפסד (₪)',
];
$scopeLabels = ['stock' => 'מניה', 'watchlist' => 'רשימת מעקב', 'portfolio' => 'תיק'];
$names = array_column($portfolios, 'name', 'id');

function alert_detail(array $r, array $names): string
{
    $c = $r['config'];
    $parts = [];
    if (isset($c['symbol'])) {
        $parts[] = $c['symbol'] . ' (' . ($c['market'] ?? 'US') . ')';
    }
    if (isset($c['portfolio_id'])) {
        $parts[] = 'תיק: ' . ($names[$c['portfolio_id']] ?? '#' . $c['portfolio_id']);
    }
    if (isset($c['threshold_pct'])) {
        $parts[] = $c['threshold_pct'] . '%';
    }
    if (isset($c['target_price'])) {
        $parts[] = ($c['direction'] ?? 'above') === 'below' ? 'מתחת ל-' . $c['target_price'] : 'מעל ' . $c['target_price'];
    }
    if (isset($c['threshold_ils'])) {
        $parts[] = '₪' . $c['threshold_ils'];
    }
    if (isset($c['multiplier'])) {
        $parts[] = '×' . $c['multiplier'] . ' נפח ממוצע';
    }
    return implode(' · ', $parts);
}
?>
<div class="head"><h1>התראות</h1></div>

<?php if (!$rules): ?>
  <p class="muted">אין התראות.</p>
<?php else: ?>
<div class="scroll"><table>
  <thead><tr><th>סוג</th><th>היקף</th><th>פרטים</th><th>סטטוס</th><th></th></tr></thead>
  <tbody>
  <?php foreach ($rules as $r): ?>
    <tr>
      <td><?= h($typeLabels[$r['alert_type']] ?? $r['alert_type']) ?></td>
      <td><?= h($scopeLabels[$r['scope']] ?? $r['scope']) ?></td>
      <td><?= h(alert_detail($r, $names)) ?></td>
      <td><?= $r['enabled'] ? 'פעילה' : '<span class="muted">מושבתת</span>' ?></td>
      <td class="actions"><form method="post" action="?a=alert_delete" data-confirm="למחוק את ההתראה?"><?= csrf_field() ?><input type="hidden" name="id" value="<?= $r['id'] ?>"><button class="link danger">מחק</button></form></td>
    </tr>
  <?php endforeach; ?>
  </tbody>
</table></div>
<?php endif; ?>

<form class="card form" method="post" action="?a=alert_add" id="alert-form">
  <h2>התראה חדשה</h2>
  <?= csrf_field() ?>
  <label>היקף
    <select name="scope" id="scope">
      <?php foreach ($scopeLabels as $k => $v): ?><option value="<?= $k ?>" <?= ($_GET['symbol'] ?? '') && $k === 'stock' ? 'selected' : '' ?>><?= $v ?></option><?php endforeach; ?>
    </select>
  </label>
  <label>סוג
    <select name="alert_type" id="atype">
      <?php foreach (ALERT_TYPES as $scope => $types): foreach ($types as $t): ?>
        <option value="<?= $t ?>" data-scope="<?= $scope ?>"><?= h($typeLabels[$t]) ?></option>
      <?php endforeach; endforeach; ?>
    </select>
  </label>
  <div data-for="stock watchlist">
    <label>סימול <input name="symbol" placeholder="AAPL / TEVA.TA" value="<?= h($_GET['symbol'] ?? '') ?>"></label>
    <label>שוק <select name="market"><option value="">אוטומטי</option><option value="US" <?= ($_GET['market'] ?? '') === 'US' ? 'selected' : '' ?>>US</option><option value="IL" <?= ($_GET['market'] ?? '') === 'IL' ? 'selected' : '' ?>>IL</option></select></label>
  </div>
  <label data-for="portfolio">תיק
    <select name="portfolio_id"><?php foreach ($portfolios as $p): ?><option value="<?= $p['id'] ?>"><?= h($p['name']) ?></option><?php endforeach; ?></select>
  </label>
  <label data-types="pct_daily premarket afterhours portfolio_value_change daily_loss_limit">סף (%) <input name="threshold_pct" inputmode="decimal"></label>
  <div data-types="price_target">
    <label>מחיר יעד <input name="target_price" inputmode="decimal"></label>
    <label>כיוון <select name="direction"><option value="above">מעל</option><option value="below">מתחת</option></select></label>
  </div>
  <label data-types="pnl_milestone">יעד ₪ (שלילי = הפסד) <input name="threshold_ils" inputmode="decimal"></label>
  <button class="primary">צור התראה</button>
</form>

<script>
const scope = document.getElementById('scope'), atype = document.getElementById('atype');
function syncAlertForm() {
  [...atype.options].forEach(o => { o.hidden = o.disabled = o.dataset.scope !== scope.value; });
  if (atype.selectedOptions[0].disabled) atype.value = [...atype.options].find(o => !o.disabled).value;
  document.querySelectorAll('[data-for]').forEach(el => {
    const on = el.dataset.for.split(' ').includes(scope.value);
    el.hidden = !on;
    el.querySelectorAll('input,select').forEach(i => i.disabled = !on);
  });
  document.querySelectorAll('[data-types]').forEach(el => {
    const on = el.dataset.types.split(' ').includes(atype.value);
    el.hidden = !on;
    el.querySelectorAll('input,select').forEach(i => i.disabled = !on);
  });
}
scope.addEventListener('change', syncAlertForm);
atype.addEventListener('change', syncAlertForm);
syncAlertForm();
</script>
