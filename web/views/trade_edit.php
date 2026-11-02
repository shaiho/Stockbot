<?php
$labels = ['buy' => 'קנייה', 'sell' => 'מכירה', 'dividend' => 'דיבידנד', 'deposit' => 'הפקדה', 'withdraw' => 'משיכה'];
$cash = $t['asset_type'] === 'cash';
$isTrade = !$cash && $t['action'] !== 'dividend';
?>
<div class="head">
  <h1>עריכת עסקה #<?= $t['id'] ?></h1>
  <a href="?p=portfolio&id=<?= $p['id'] ?>">← <?= h($p['name']) ?></a>
</div>

<form class="card form" method="post" action="?a=trade_update">
  <?= csrf_field() ?><input type="hidden" name="trade_id" value="<?= $t['id'] ?>">
  <p><b><?= h($labels[$t['action']] ?? $t['action']) ?></b> <?= $cash ? h($t['currency']) : h($t['symbol']) . ' <small class="muted">' . h($t['market']) . '</small>' ?></p>
  <?php if ($cash || $isTrade): ?>
    <label><?= $cash ? 'סכום' : 'כמות' ?> <input name="quantity" inputmode="decimal" value="<?= h($t['quantity']) ?>" required></label>
  <?php endif; ?>
  <?php if (!$cash): ?>
    <label><?= $isTrade ? 'מחיר ליחידה' : 'סכום דיבידנד כולל' ?> <input name="price" inputmode="decimal" value="<?= h($t['price']) ?>" required></label>
  <?php endif; ?>
  <?php if ($isTrade): ?>
    <label>עמלה <input name="commission" inputmode="decimal" value="<?= h($t['commission']) ?>" required></label>
    <p class="muted">שינוי כמות או מחיר בלי לשנות את העמלה מחשב אותה מחדש לפי הגדרות התיק.</p>
  <?php endif; ?>
  <label>תאריך <input type="date" name="date" value="<?= h(local_dt($t['ts'], 'Y-m-d')) ?>" max="<?= date('Y-m-d') ?>"></label>
  <label>הערה <input name="note" maxlength="200" value="<?= h($t['note']) ?>"></label>
  <button class="primary">שמור</button>
</form>
