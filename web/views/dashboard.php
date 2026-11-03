<div class="head"><h1>התיקים שלי</h1></div>
<?php if ($portfolios) { require __DIR__ . '/_refresh.php'; } ?>

<?php if (!$portfolios): ?>
  <p class="muted">אין עדיין תיקים. צור את הראשון למטה.</p>
<?php endif; ?>

<div class="grid">
<?php foreach ($portfolios as $p): $s = $data[$p['id']]['sum']; ?>
  <a class="card tile" href="?p=portfolio&id=<?= $p['id'] ?>">
    <h2><?= h($p['name']) ?></h2>
    <div class="big"><?= money($s['total_ils']) ?></div>
    <div class="muted">≈ <?= money($s['total_usd'], 'USD') ?></div>
    <dl>
      <dt>רווח/הפסד כולל</dt><dd class="<?= tone($s['total_pnl_ils']) ?>"><?= money($s['total_pnl_ils'], 'ILS', true) ?> (<?= pct($s['total_pnl_pct']) ?>)</dd>
      <dt>שינוי יומי</dt><dd class="<?= tone($s['daily_change_ils']) ?>"><?= money($s['daily_change_ils'], 'ILS', true) ?></dd>
      <dt>מזומן</dt><dd><?= money($s['cash_ils']) ?> · <?= money($s['cash_usd'], 'USD') ?></dd>
      <dt>החזקות</dt><dd><?= count($s['holdings']) ?></dd>
    </dl>
  </a>
<?php endforeach; ?>
</div>

<?php if (count($portfolios) < MAX_PORTFOLIOS): ?>
<form class="card form" method="post" action="?a=portfolio_create">
  <h2>תיק חדש</h2>
  <?= csrf_field() ?>
  <label>שם <input name="name" maxlength="50" required></label>
  <label>מזומן פתיחה ₪ <input name="cash_ils" inputmode="decimal" value="0"></label>
  <label>מזומן פתיחה $ <input name="cash_usd" inputmode="decimal" value="0"></label>
  <button class="primary">צור תיק</button>
</form>
<?php endif; ?>
