<?php
$labels = ['buy' => 'קנייה', 'sell' => 'מכירה', 'dividend' => 'דיבידנד', 'deposit' => 'הפקדה', 'withdraw' => 'משיכה'];
$pid = $p['id'];
?>
<div class="head">
  <h1><?= h($p['name']) ?></h1>
  <a href="?p=dashboard">← כל התיקים</a>
</div>
<?php require __DIR__ . '/_refresh.php'; ?>

<div class="stats">
  <div class="card"><span>שווי כולל</span><b><?= money($sum['total_ils']) ?></b><small><?= money($sum['total_usd'], 'USD') ?> · $1 = ₪<?= number_format($sum['fx'], 3) ?></small></div>
  <div class="card"><span>שווי ניירות ערך</span><b><?= money($sum['securities_ils']) ?></b><small><?= money($sum['securities_usd'], 'USD') ?> · בלי מזומן</small></div>
  <div class="card"><span>רווח/הפסד כולל</span><b class="<?= tone($sum['total_pnl_ils']) ?>"><?= money($sum['total_pnl_ils'], 'ILS', true) ?></b><small><?= pct($sum['total_pnl_pct']) ?> על הון <?= money($sum['opening_capital_ils']) ?></small></div>
  <div class="card"><span>שינוי יומי</span><b class="<?= tone($sum['daily_change_ils']) ?>"><?= money($sum['daily_change_ils'], 'ILS', true) ?></b></div>
  <div class="card"><span>רווח מהשקעות</span><b class="<?= tone($sum['investments_pnl_ils']) ?>"><?= money($sum['investments_pnl_ils'], 'ILS', true) ?></b><small>ממומש + לא ממומש</small></div>
  <div class="card"><span>מזומן</span><b><?= money($sum['cash_ils']) ?></b><small><?= money($sum['cash_usd'], 'USD') ?></small></div>
</div>

<section>
  <h2>החזקות</h2>
  <?php if (!$sum['holdings']): ?>
    <p class="muted">אין החזקות פתוחות.</p>
  <?php else: ?>
  <div class="scroll"><table>
    <thead><tr><th>סימול</th><th>כמות</th><th>עלות ממוצעת</th><th>מחיר</th><th>יומי %</th><th>שינוי יומי</th><th>שווי</th><th>שינוי מקנייה</th><th>שינוי מקנייה %</th><th>ממומש</th><th>עמלות</th><th></th></tr></thead>
    <tbody>
    <?php foreach ($sum['holdings'] as $r): $c = $r['currency']; ?>
      <tr>
        <td><a href="?p=symbol&symbol=<?= h($r['symbol']) ?>&market=<?= h($r['market']) ?>"><b><?= h($r['symbol']) ?></b></a> <small class="muted"><?= h($r['market']) ?></small></td>
        <td><?= qty($r['quantity']) ?></td>
        <td><?= money($r['avg_cost'], $c) ?></td>
        <td><?= $r['price'] === null ? '<span class="neg">אין מחיר</span>' : money($r['price'], $c) . session_badge($r['session']) ?></td>
        <td class="<?= tone($r['change_pct']) ?>"><?= pct($r['change_pct']) ?></td>
        <td class="<?= tone($r['daily']) ?>"><?= $r['daily'] === null ? '—' : money($r['daily'], $c, true) ?></td>
        <td><?= $r['value'] === null ? '—' : money($r['value'], $c) ?></td>
        <td class="<?= tone($r['unrealized']) ?>"><?= $r['price'] === null ? '—' : money($r['unrealized'], $c, true) ?></td>
        <td class="<?= tone($r['unrealized_pct']) ?>"><?= pct($r['unrealized_pct']) ?></td>
        <td class="<?= tone($r['realized']) ?>"><?= money($r['realized'], $c, true) ?></td>
        <td><?= money($r['commissions'], $c) ?></td>
        <td class="actions">
          <button type="button" class="link quick-add" data-symbol="<?= h($r['symbol']) ?>" data-market="<?= h($r['market']) ?>" data-price="<?= h((string) ($r['price'] ?? '')) ?>" title="עסקה מהירה">+</button>
          <button type="button" class="link quick-order" data-symbol="<?= h($r['symbol']) ?>" data-market="<?= h($r['market']) ?>" data-price="<?= h((string) ($r['price'] ?? '')) ?>" title="הוראת לימיט">הוראה</button>
        </td>
      </tr>
    <?php endforeach; ?>
    </tbody>
  </table></div>
  <?php endif; ?>
  <?php
    $alloc = array_values(array_filter($sum['holdings'], fn($r) => $r['value'] !== null && $r['value'] > 0));
    $totAlloc = array_sum(array_map(fn($r) => $r['value'] * ($r['currency'] === 'ILS' ? 1 : $sum['fx']), $alloc));
    if ($totAlloc > 0):
      $colors = ['#2563eb', '#16a34a', '#dc2626', '#d97706', '#7c3aed', '#0891b2', '#db2777', '#65a30d'];
      $angle = -90.0; $i = 0; $seg = '';
      foreach ($alloc as $r) {
        $v = $r['value'] * ($r['currency'] === 'ILS' ? 1 : $sum['fx']);
        $pct = $v / $totAlloc;
        $a0 = deg2rad($angle); $angle += $pct * 360; $a1 = deg2rad($angle);
        $large = $pct > 0.5 ? 1 : 0;
        $x0 = 110 + 80 * cos($a0); $y0 = 110 + 80 * sin($a0);
        $x1 = 110 + 80 * cos($a1); $y1 = 110 + 80 * sin($a1);
        $xi1 = 110 + 45 * cos($a1); $yi1 = 110 + 45 * sin($a1);
        $xi0 = 110 + 45 * cos($a0); $yi0 = 110 + 45 * sin($a0);
        $seg .= sprintf('<path d="M%.1f %.1f A80 80 0 %d 1 %.1f %.1f L%.1f %.1f A45 45 0 %d 0 %.1f %.1f Z" fill="%s"/>', $x0, $y0, $large, $x1, $y1, $xi1, $yi1, $large, $xi0, $yi0, $colors[$i % count($colors)]);
        $i++;
      }
      $i = 0;
  ?>
    <h3>הקצאה</h3>
    <div style="display:flex;gap:1.5rem;align-items:center;flex-wrap:wrap">
      <svg viewBox="0 0 220 220" style="width:180px;height:180px"><?= $seg ?></svg>
      <div>
        <?php foreach ($alloc as $r): $pct = $r['value'] * ($r['currency'] === 'ILS' ? 1 : $sum['fx']) / $totAlloc * 100; ?>
          <div><span style="display:inline-block;width:.7rem;height:.7rem;background:<?= $colors[$i++ % count($colors)] ?>;border-radius:2px;margin-left:.4rem"></span><?= h($r['symbol']) ?> — <?= number_format($pct, 1) ?>%</div>
        <?php endforeach; ?>
      </div>
    </div>
  <?php endif; ?>
  <?php if ($sum['closed']): ?>
    <p class="muted">פוזיציות סגורות:
    <?php foreach ($sum['closed'] as $r): ?>
      <a class="chip <?= tone($r['realized']) ?>" href="?p=symbol&symbol=<?= h($r['symbol']) ?>"><?= h($r['symbol']) ?> <?= money($r['realized'], $r['currency'], true) ?></a>
    <?php endforeach; ?></p>
  <?php endif; ?>
</section>

<section class="two">
  <form class="card form" method="post" action="?a=trade_add" id="trade-form">
    <h2>עסקה חדשה</h2>
    <?= csrf_field() ?><input type="hidden" name="portfolio_id" value="<?= $pid ?>">
    <label>פעולה
      <select name="action_type" id="act">
        <option value="buy">קנייה</option><option value="sell">מכירה</option><option value="dividend">דיבידנד</option>
      </select>
    </label>
    <label>סימול <input name="symbol" required placeholder="AAPL / TEVA.TA / 604611"></label>
    <label>שוק
      <select name="market"><option value="">אוטומטי</option><option value="US">US</option><option value="IL">IL</option></select>
    </label>
    <label id="qty-row">כמות <input name="quantity" inputmode="decimal"></label>
    <label><span id="price-label">מחיר ליחידה</span> <input name="price" inputmode="decimal" required></label>
    <label id="comm-row">עמלה (ריק = אוטומטי) <input name="commission" inputmode="decimal"></label>
    <label>תאריך (ריק = עכשיו) <input type="date" name="date" max="<?= date('Y-m-d') ?>"></label>
    <label>הערה <input name="note" maxlength="200"></label>
    <button class="primary">שמור עסקה</button>
  </form>

  <form class="card form" method="post" action="?a=cash_add">
    <h2>מזומן</h2>
    <?= csrf_field() ?><input type="hidden" name="portfolio_id" value="<?= $pid ?>">
    <label>פעולה <select name="kind"><option value="deposit">הפקדה</option><option value="withdraw">משיכה</option></select></label>
    <label>מטבע <select name="currency"><option value="ILS">₪ ILS</option><option value="USD">$ USD</option></select></label>
    <label>סכום <input name="amount" inputmode="decimal" required></label>
    <label>תאריך (ריק = עכשיו) <input type="date" name="date" max="<?= date('Y-m-d') ?>"></label>
    <label>הערה <input name="note" maxlength="200"></label>
    <button class="primary">שמור</button>
  </form>

  <form class="card form" method="post" action="?a=order_add">
    <h2>הוראת לימיט <small class="muted">(<a href="?p=orders">כל ההוראות</a>)</small></h2>
    <?= csrf_field() ?><input type="hidden" name="portfolio_id" value="<?= $pid ?>">
    <label>פעולה <select name="action_type"><option value="buy">קנייה</option><option value="sell">מכירה</option></select></label>
    <label>סימול <input name="symbol" required placeholder="AAPL / TEVA.TA"></label>
    <label>שוק <select name="market"><option value="">אוטומטי</option><option value="US">US</option><option value="IL">IL</option></select></label>
    <label>כמות <input name="quantity" inputmode="decimal" required></label>
    <label>מחיר יעד ליחידה <input name="price" inputmode="decimal" required></label>
    <label>בתוקף עד <input type="date" name="expires" value="<?= date('Y-m-d') ?>" min="<?= date('Y-m-d') ?>" required></label>
    <button class="primary">פתח הוראה</button>
  </form>
</section>

<section>
  <h2>היסטוריית עסקאות <small class="muted">(<?= count($trades) ?>)</small> <small><a href="?p=export&id=<?= $pid ?>">ייצוא CSV</a></small></h2>
  <div class="filter muted">
    סינון: <input id="f-sym" placeholder="סימול" size="8">
    <select id="f-act">
      <option value="">כל הפעולות</option>
      <option value="buy">קנייה</option><option value="sell">מכירה</option><option value="dividend">דיבידנד</option>
      <option value="deposit">הפקדה</option><option value="withdraw">משיכה</option>
    </select>
    <input type="date" id="f-from"> – <input type="date" id="f-to">
    <button type="button" class="link" id="f-clear">נקה</button>
    <span id="f-sum"></span>
  </div>
  <div class="scroll"><table>
    <thead><tr><th>#</th><th>תאריך</th><th>פעולה</th><th>סימול</th><th>כמות</th><th>מחיר</th><th>עמלה</th><th>הערה</th><th></th></tr></thead>
    <tbody id="trades-body">
    <?php foreach ($trades as $t): $cash = $t['asset_type'] === 'cash'; $c = $t['currency']; ?>
      <tr data-act="<?= h($t['action']) ?>" data-sym="<?= h($cash ? $c : strtoupper($t['symbol'])) ?>" data-date="<?= h(local_dt($t['ts'], 'Y-m-d')) ?>" data-comm="<?= h((string) $t['commission']) ?>" data-cur="<?= h($c) ?>">
        <td><?= $t['id'] ?></td>
        <td><?= h(local_dt($t['ts'])) ?></td>
        <td><?= h($labels[$t['action']] ?? $t['action']) ?></td>
        <td><?= $cash ? '<span class="muted">' . h($c) . '</span>' : '<b>' . h($t['symbol']) . '</b>' ?></td>
        <td><?= $t['action'] === 'dividend' ? '' : qty($t['quantity']) ?></td>
        <td><?= $cash ? '' : money($t['price'], $c) ?></td>
        <td><?= $t['commission'] > 0 ? money($t['commission'], $c) : '' ?></td>
        <td class="muted"><?= h($t['note']) ?></td>
        <td class="actions">
          <a href="?p=trade&id=<?= $t['id'] ?>">ערוך</a>
          <form method="post" action="?a=trade_delete" data-confirm="למחוק את העסקה #<?= $t['id'] ?>?"><?= csrf_field() ?><input type="hidden" name="trade_id" value="<?= $t['id'] ?>"><button class="link danger">מחק</button></form>
        </td>
      </tr>
    <?php endforeach; ?>
    </tbody>
  </table></div>
</section>
<script>
(() => {
  const rows = [...document.querySelectorAll('#trades-body tr')];
  const sym = document.getElementById('f-sym'), act = document.getElementById('f-act'),
        from = document.getElementById('f-from'), to = document.getElementById('f-to'),
        sum = document.getElementById('f-sum');
  const apply = () => {
    let n = 0, comms = {};
    rows.forEach(r => {
      const ok = (!sym.value || r.dataset.sym.includes(sym.value.toUpperCase()))
        && (!act.value || r.dataset.act === act.value)
        && (!from.value || r.dataset.date >= from.value)
        && (!to.value || r.dataset.date <= to.value);
      r.hidden = !ok;
      if (ok) { n++; if (+r.dataset.comm > 0) comms[r.dataset.cur] = (comms[r.dataset.cur] || 0) + +r.dataset.comm; }
    });
    const c = Object.entries(comms).map(([k, v]) => v.toFixed(2) + ' ' + (k === 'ILS' ? '₪' : '$')).join(' + ');
    sum.textContent = (n === rows.length ? '' : n + ' שורות') + (c ? ' · עמלות ' + c : '');
  };
  [sym, act, from, to].forEach(el => el.addEventListener('input', apply));
  document.getElementById('f-clear').addEventListener('click', () => { sym.value = act.value = from.value = to.value = ''; apply(); });
})();
</script>

<section>
  <h2>הגדרות תיק</h2>
  <div class="two">
    <form class="card form" method="post" action="?a=portfolio_rename">
      <h3>שם</h3>
      <?= csrf_field() ?><input type="hidden" name="portfolio_id" value="<?= $pid ?>">
      <label>שם התיק <input name="name" value="<?= h($p['name']) ?>" maxlength="50" required></label>
      <button>שנה שם</button>
    </form>
    <form class="card form" method="post" action="?a=portfolio_cash">
      <h3>מזומן פתיחה</h3>
      <?= csrf_field() ?><input type="hidden" name="portfolio_id" value="<?= $pid ?>">
      <label>₪ <input name="cash_ils" inputmode="decimal" value="<?= h($p['opening_cash_ils']) ?>"></label>
      <label>$ <input name="cash_usd" inputmode="decimal" value="<?= h($p['opening_cash_usd']) ?>"></label>
      <button>עדכן</button>
    </form>
    <form class="card form" method="post" action="?a=portfolio_commission">
      <h3>עמלות</h3>
      <?= csrf_field() ?><input type="hidden" name="portfolio_id" value="<?= $pid ?>">
      <label>מינימום $ <input name="min_usd" inputmode="decimal" value="<?= h($p['commission_min_usd']) ?>"></label>
      <label>מינימום ₪ <input name="min_ils" inputmode="decimal" value="<?= h($p['commission_min_ils']) ?>"></label>
      <label>תוספת
        <select name="extra_type">
          <option value="fixed" <?= $p['commission_extra_type'] === 'fixed' ? 'selected' : '' ?>>קבועה</option>
          <option value="percent" <?= $p['commission_extra_type'] === 'percent' ? 'selected' : '' ?>>אחוז מהעסקה</option>
        </select>
      </label>
      <label>ערך <input name="extra_value" inputmode="decimal" value="<?= h($p['commission_extra_value']) ?>"></label>
      <button>שמור</button>
    </form>
    <div class="card form">
      <h3>פעולות</h3>
      <form method="post" action="?a=portfolio_recalc" data-confirm="לחשב מחדש את העמלות בכל העסקאות?"><?= csrf_field() ?><input type="hidden" name="portfolio_id" value="<?= $pid ?>"><button>חשב עמלות מחדש לכל העסקאות</button></form>
      <form method="post" action="?a=portfolio_clear_trades" data-confirm="למחוק את כל העסקאות בתיק? לא ניתן לשחזר."><?= csrf_field() ?><input type="hidden" name="portfolio_id" value="<?= $pid ?>"><button class="danger">מחק את כל העסקאות</button></form>
      <form method="post" action="?a=portfolio_delete" data-confirm="למחוק את התיק כולו? לא ניתן לשחזר."><?= csrf_field() ?><input type="hidden" name="portfolio_id" value="<?= $pid ?>"><button class="danger">מחק תיק</button></form>
    </div>
  </div>
</section>

<div id="qt-overlay" class="overlay" hidden>
  <form class="card form" method="post" action="?a=trade_add">
    <h2>עסקה מהירה — <span id="qt-title"></span></h2>
    <?= csrf_field() ?><input type="hidden" name="portfolio_id" value="<?= $pid ?>">
    <input type="hidden" name="symbol"><input type="hidden" name="market">
    <label>פעולה <select name="action_type"><option value="buy">קנייה</option><option value="sell">מכירה</option></select></label>
    <label>כמות <input name="quantity" inputmode="decimal" required></label>
    <label>מחיר ליחידה <input name="price" id="qt-price" inputmode="decimal" required></label>
    <label>עמלה (ריק = אוטומטי) <input name="commission" inputmode="decimal"></label>
    <label>הערה <input name="note" maxlength="200"></label>
    <button class="primary">שמור עסקה</button> <button type="button" id="qt-cancel">ביטול</button>
  </form>
</div>

<div id="qo-overlay" class="overlay" hidden>
  <form class="card form" method="post" action="?a=order_add">
    <h2>הוראת לימיט — <span id="qo-title"></span></h2>
    <?= csrf_field() ?><input type="hidden" name="portfolio_id" value="<?= $pid ?>">
    <input type="hidden" name="symbol"><input type="hidden" name="market">
    <label>פעולה <select name="action_type"><option value="buy">קנייה</option><option value="sell">מכירה</option></select></label>
    <label>כמות <input name="quantity" inputmode="decimal" required></label>
    <label>מחיר יעד ליחידה <input name="price" id="qo-price" inputmode="decimal" required></label>
    <label>בתוקף עד <input type="date" name="expires" value="<?= date('Y-m-d') ?>" min="<?= date('Y-m-d') ?>" required></label>
    <button class="primary">פתח הוראה</button> <button type="button" id="qo-cancel">ביטול</button>
  </form>
</div>

<script>
const ov = document.getElementById('qt-overlay');
document.querySelectorAll('.quick-add').forEach(b => b.addEventListener('click', () => {
  document.getElementById('qt-title').textContent = b.dataset.symbol + ' · ' + b.dataset.market;
  ov.querySelector('[name=symbol]').value = b.dataset.symbol;
  ov.querySelector('[name=market]').value = b.dataset.market;
  document.getElementById('qt-price').value = b.dataset.price;
  ov.hidden = false;
  ov.querySelector('[name=quantity]').focus();
}));
document.getElementById('qt-cancel').addEventListener('click', () => { ov.hidden = true; });
ov.addEventListener('click', e => { if (e.target === ov) ov.hidden = true; });

const qo = document.getElementById('qo-overlay');
document.querySelectorAll('.quick-order').forEach(b => b.addEventListener('click', () => {
  document.getElementById('qo-title').textContent = b.dataset.symbol + ' · ' + b.dataset.market;
  qo.querySelector('[name=symbol]').value = b.dataset.symbol;
  qo.querySelector('[name=market]').value = b.dataset.market;
  document.getElementById('qo-price').value = b.dataset.price;
  qo.hidden = false;
  qo.querySelector('[name=quantity]').focus();
}));
document.getElementById('qo-cancel').addEventListener('click', () => { qo.hidden = true; });
qo.addEventListener('click', e => { if (e.target === qo) qo.hidden = true; });

const act = document.getElementById('act');
act.addEventListener('change', () => {
  const div = act.value === 'dividend';
  document.getElementById('qty-row').hidden = div;
  document.getElementById('comm-row').hidden = div;
  document.getElementById('price-label').textContent = div ? 'סכום דיבידנד כולל' : 'מחיר ליחידה';
});
</script>
