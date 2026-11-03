<?php
$labels = ['buy' => 'קנייה', 'sell' => 'מכירה', 'dividend' => 'דיבידנד', 'deposit' => 'הפקדה', 'withdraw' => 'משיכה'];
$pid = $p['id'];
?>
<div class="head">
  <h1><?= h($p['name']) ?></h1>
  <a href="?p=dashboard">← כל התיקים</a>
</div>

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
    <thead><tr><th>סימול</th><th>כמות</th><th>עלות ממוצעת</th><th>מחיר</th><th>יומי</th><th>שווי</th><th>לא ממומש</th><th>ממומש</th><th>עמלות</th></tr></thead>
    <tbody>
    <?php foreach ($sum['holdings'] as $r): $c = $r['currency']; ?>
      <tr>
        <td><b><?= h($r['symbol']) ?></b> <small class="muted"><?= h($r['market']) ?></small></td>
        <td><?= qty($r['quantity']) ?></td>
        <td><?= money($r['avg_cost'], $c) ?></td>
        <td><?= $r['price'] === null ? '<span class="neg">אין מחיר</span>' : money($r['price'], $c) ?></td>
        <td class="<?= tone($r['change_pct']) ?>"><?= pct($r['change_pct']) ?></td>
        <td><?= $r['value'] === null ? '—' : money($r['value'], $c) ?></td>
        <td class="<?= tone($r['unrealized']) ?>"><?= money($r['unrealized'], $c, true) ?> <small>(<?= pct($r['unrealized_pct']) ?>)</small></td>
        <td class="<?= tone($r['realized']) ?>"><?= money($r['realized'], $c, true) ?></td>
        <td><?= money($r['commissions'], $c) ?></td>
      </tr>
    <?php endforeach; ?>
    </tbody>
  </table></div>
  <?php endif; ?>
  <?php if ($sum['closed']): ?>
    <p class="muted">פוזיציות סגורות:
    <?php foreach ($sum['closed'] as $r): ?>
      <span class="chip <?= tone($r['realized']) ?>"><?= h($r['symbol']) ?> <?= money($r['realized'], $r['currency'], true) ?></span>
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
</section>

<section>
  <h2>היסטוריית עסקאות <small class="muted">(<?= count($trades) ?>)</small></h2>
  <div class="scroll"><table>
    <thead><tr><th>#</th><th>תאריך</th><th>פעולה</th><th>סימול</th><th>כמות</th><th>מחיר</th><th>עמלה</th><th>הערה</th><th></th></tr></thead>
    <tbody>
    <?php foreach ($trades as $t): $cash = $t['asset_type'] === 'cash'; $c = $t['currency']; ?>
      <tr>
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

<script>
const act = document.getElementById('act');
act.addEventListener('change', () => {
  const div = act.value === 'dividend';
  document.getElementById('qty-row').hidden = div;
  document.getElementById('comm-row').hidden = div;
  document.getElementById('price-label').textContent = div ? 'סכום דיבידנד כולל' : 'מחיר ליחידה';
});
</script>
