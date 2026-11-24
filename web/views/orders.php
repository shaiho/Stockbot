<?php
$statusLabels = ['open' => 'פתוחה', 'executed' => 'בוצעה', 'expired' => 'פקעה', 'cancelled' => 'בוטלה'];
$actLabels = ['buy' => 'קנייה', 'sell' => 'מכירה'];
$open = array_values(array_filter($orders, fn($o) => $o['status'] === 'open'));
$closed = array_values(array_filter($orders, fn($o) => $o['status'] !== 'open'));
?>
<div class="head"><h1>הוראות לביצוע</h1></div>

<p class="muted">ההוראות נבדקות מול המחיר החי בכל טעינת עמוד ובכל דקה בבוט. קנייה מופעלת כשהמחיר יורד לסנט מתחת ליעד, מכירה כשהוא עולה לסנט מעל היעד — כדי למנוע הפעלה על נגיעה במחיר שלא ממלאה הוראה אמיתית. פתיחת הוראה נעשית מעמוד התיק.</p>

<h2>הוראות פתוחות <small class="muted">(<?= count($open) ?>)</small></h2>
<?php if ($open): ?>
<form method="post" action="?a=order_cancel_bulk" id="bulk-form">
<?= csrf_field() ?>
<div class="scroll"><table class="sortable">
  <thead><tr><th><input type="checkbox" id="sel-all"></th><th>#</th><th>תיק</th><th>פעולה</th><th>סימול</th><th>כמות</th><th>מחיר יעד</th><th>מחיר חי</th><th>תוקף</th><th></th></tr></thead>
  <tbody>
  <?php foreach ($open as $o): ?>
    <tr>
      <td><input type="checkbox" name="order_ids[]" value="<?= $o['id'] ?>" class="sel-order"></td>
      <td><?= $o['id'] ?></td>
      <td><a href="?p=portfolio&id=<?= $o['portfolio_id'] ?>"><?= h($o['portfolio_name']) ?></a></td>
      <td><?= h($actLabels[$o['action']] ?? $o['action']) ?></td>
      <td><a href="?p=symbol&symbol=<?= h($o['symbol']) ?>&market=<?= h($o['market']) ?>"><b><?= h($o['symbol']) ?></b></a> <small class="muted"><?= h($o['market']) ?></small></td>
      <td><?= qty($o['quantity']) ?></td>
      <td><?= money($o['limit_price'], $o['currency']) ?></td>
      <td>
        <?php $q = $quotes[Prices::key($o['symbol'], $o['market'])] ?? null; ?>
        <?php if ($q && $q['price']): $diff = ($q['price'] - $o['limit_price']) / $o['limit_price'] * 100;
          $near = $o['action'] === 'buy' ? $diff > 0 && $diff < 3 : $diff < 0 && $diff > -3; ?>
          <b><?= money($q['price'], $o['currency']) ?></b>
          <small class="<?= $near ? 'warn' : 'muted' ?>"><?= ($diff > 0 ? '+' : '') . number_format($diff, 1) ?>%</small>
        <?php else: ?>—<?php endif; ?>
      </td>
      <td><?= h($o['expires_on']) ?></td>
      <td class="actions">
        <button type="button" class="link edit-order" data-id="<?= $o['id'] ?>" data-symbol="<?= h($o['symbol']) ?>" data-qty="<?= h((string) $o['quantity']) ?>" data-price="<?= h((string) $o['limit_price']) ?>" data-expires="<?= h($o['expires_on']) ?>">ערוך</button>
        <form method="post" action="?a=order_execute" class="exec-order"><?= csrf_field() ?><input type="hidden" name="order_id" value="<?= $o['id'] ?>"><input type="hidden" name="fill_price" value="<?= h((string) $o['limit_price']) ?>"><button class="link">בוצע</button></form>
        <form method="post" action="?a=order_cancel" data-confirm="לבטל את ההוראה #<?= $o['id'] ?>?"><?= csrf_field() ?><input type="hidden" name="order_id" value="<?= $o['id'] ?>"><button class="link danger">בטל</button></form>
      </td>
    </tr>
  <?php endforeach; ?>
  </tbody>
</table></div>
<button class="danger" id="bulk-cancel" data-confirm disabled data-confirm-text="לבטל את ההוראות שנבחרו?">בטל נבחרות</button>
</form>
<?php else: ?>
<p class="muted">אין הוראות פתוחות.</p>
<?php endif; ?>

<?php if ($closed): ?>
<details>
  <summary><h2 style="display:inline">היסטוריה <small class="muted">(<?= count($closed) ?>)</small></h2></summary>
<div class="scroll"><table class="sortable">
  <thead><tr><th>#</th><th>תיק</th><th>פעולה</th><th>סימול</th><th>כמות</th><th>מחיר יעד</th><th>תוקף</th><th>סטטוס</th><th></th></tr></thead>
  <tbody>
  <?php foreach ($closed as $o): ?>
    <tr>
      <td><?= $o['id'] ?></td>
      <td><a href="?p=portfolio&id=<?= $o['portfolio_id'] ?>"><?= h($o['portfolio_name']) ?></a></td>
      <td><?= h($actLabels[$o['action']] ?? $o['action']) ?></td>
      <td><a href="?p=symbol&symbol=<?= h($o['symbol']) ?>&market=<?= h($o['market']) ?>"><b><?= h($o['symbol']) ?></b></a> <small class="muted"><?= h($o['market']) ?></small></td>
      <td><?= qty($o['quantity']) ?></td>
      <td><?= money($o['limit_price'], $o['currency']) ?></td>
      <td><?= h($o['expires_on']) ?></td>
      <td>
        <?= h($statusLabels[$o['status']] ?? $o['status']) ?>
        <?php if ($o['status'] === 'executed' && $o['executed_trade_id']): ?>
          <a href="?p=trade&id=<?= $o['executed_trade_id'] ?>">עסקה #<?= $o['executed_trade_id'] ?></a>
        <?php endif; ?>
      </td>
      <td class="actions">
        <button type="button" class="link dup-order" data-pid="<?= $o['portfolio_id'] ?>" data-symbol="<?= h($o['symbol']) ?>" data-market="<?= h($o['market']) ?>" data-action="<?= h($o['action']) ?>" data-qty="<?= h((string) $o['quantity']) ?>" data-price="<?= h((string) $o['limit_price']) ?>">שכפל</button>
      </td>
    </tr>
  <?php endforeach; ?>
  </tbody>
</table></div>
</details>
<?php endif; ?>

<div id="od-overlay" class="overlay" hidden>
  <form class="card form" method="post" action="?a=order_add">
    <h2>הוראה חדשה — <span id="od-title"></span></h2>
    <?= csrf_field() ?>
    <input type="hidden" name="portfolio_id"><input type="hidden" name="symbol"><input type="hidden" name="market"><input type="hidden" name="action_type">
    <label>כמות <input name="quantity" inputmode="decimal" required></label>
    <label>מחיר יעד ליחידה <input name="price" inputmode="decimal" required></label>
    <label>בתוקף עד <input type="date" name="expires" min="<?= date('Y-m-d') ?>" value="<?= date('Y-m-d') ?>" required></label>
    <button class="primary">פתח הוראה</button> <button type="button" id="od-cancel">ביטול</button>
  </form>
</div>

<div id="oe-overlay" class="overlay" hidden>
  <form class="card form" method="post" action="?a=order_edit">
    <h2>עריכת הוראה #<span id="oe-title"></span></h2>
    <?= csrf_field() ?><input type="hidden" name="order_id">
    <label>כמות <input name="quantity" inputmode="decimal" required></label>
    <label>מחיר יעד ליחידה <input name="price" inputmode="decimal" required></label>
    <label>בתוקף עד <input type="date" name="expires" min="<?= date('Y-m-d') ?>" required></label>
    <button class="primary">שמור</button> <button type="button" id="oe-cancel">ביטול</button>
  </form>
</div>
<script>
(() => {
const oe = document.getElementById('oe-overlay');
document.querySelectorAll('.edit-order').forEach(b => b.addEventListener('click', () => {
  document.getElementById('oe-title').textContent = b.dataset.id + ' · ' + b.dataset.symbol;
  oe.querySelector('[name=order_id]').value = b.dataset.id;
  oe.querySelector('[name=quantity]').value = b.dataset.qty;
  oe.querySelector('[name=price]').value = b.dataset.price;
  oe.querySelector('[name=expires]').value = b.dataset.expires;
  oe.hidden = false;
}));
document.getElementById('oe-cancel').addEventListener('click', () => { oe.hidden = true; });
const od = document.getElementById('od-overlay');
document.querySelectorAll('.dup-order').forEach(b => b.addEventListener('click', () => {
  document.getElementById('od-title').textContent = (b.dataset.action === 'buy' ? 'קניית ' : 'מכירת ') + b.dataset.symbol;
  od.querySelector('[name=portfolio_id]').value = b.dataset.pid;
  od.querySelector('[name=symbol]').value = b.dataset.symbol;
  od.querySelector('[name=market]').value = b.dataset.market;
  od.querySelector('[name=action_type]').value = b.dataset.action;
  od.querySelector('[name=quantity]').value = b.dataset.qty;
  od.querySelector('[name=price]').value = b.dataset.price;
  od.hidden = false;
  od.querySelector('[name=quantity]').focus();
}));
document.getElementById('od-cancel').addEventListener('click', () => { od.hidden = true; });
document.querySelectorAll('form.exec-order').forEach(f => f.addEventListener('submit', e => {
  const inp = f.querySelector('[name=fill_price]');
  const v = prompt('מחיר ביצוע בפועל ליחידה:', inp.value);
  if (v === null) { e.preventDefault(); return; }
  inp.value = v;
}));
const selAll = document.getElementById('sel-all'), bulkBtn = document.getElementById('bulk-cancel');
const syncSel = () => { bulkBtn.disabled = !document.querySelector('.sel-order:checked'); };
selAll.addEventListener('change', () => { document.querySelectorAll('.sel-order').forEach(c => c.checked = selAll.checked); syncSel(); });
document.querySelectorAll('.sel-order').forEach(c => c.addEventListener('change', syncSel));
bulkBtn.addEventListener('click', e => { if (!confirm(bulkBtn.dataset.confirmText)) e.preventDefault(); });
})();
</script>
