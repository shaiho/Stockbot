<div class="head"><h1>התיקים שלי</h1></div>
<?php if ($portfolios) { require __DIR__ . '/_refresh.php'; } ?>

<?php if (!$portfolios): ?>
  <p class="muted">אין עדיין תיקים. צור את הראשון למטה.</p>
<?php endif; ?>

<?php if ($portfolios):
    $tot = ['total' => 0.0, 'daily' => 0.0, 'pnl' => 0.0, 'cap' => 0.0];
    foreach ($portfolios as $p) {
        $s = $data[$p['id']]['sum'];
        $tot['total'] += $s['total_ils']; $tot['daily'] += $s['daily_change_ils'];
        $tot['pnl'] += $s['total_pnl_ils']; $tot['cap'] += $s['opening_capital_ils'];
    }
?>
<div class="stats">
  <div class="card"><span>שווי כולל — כל התיקים</span><b><?= money($tot['total']) ?></b></div>
  <div class="card"><span>שינוי יומי — כל התיקים</span><b class="<?= tone($tot['daily']) ?>"><?= money($tot['daily'], 'ILS', true) ?></b></div>
  <div class="card"><span>רווח/הפסד — כל התיקים</span><b class="<?= tone($tot['pnl']) ?>"><?= money($tot['pnl'], 'ILS', true) ?></b><small><?= $tot['cap'] > 0 ? pct($tot['pnl'] / $tot['cap'] * 100) : '' ?></small></div>
</div>
<?php if (count($snapshots) >= 2):
    $pts = array_map(fn($s) => [$s['date'], (float) $s['total_ils']], $snapshots);
    $ys = array_column($pts, 1); $y0 = min($ys); $y1 = max($ys); $n = count($pts) - 1;
    $px = fn(int $i) => 40 + $i / max($n, 1) * 850;
    $py = fn(float $v) => 250 - ($v - $y0) / max($y1 - $y0, 1e-9) * 210;
    $path = implode(' ', array_map(fn($i, $p) => ($i ? 'L' : 'M') . round($px($i), 1) . ' ' . round($py($p[1]), 1), array_keys($pts), $pts));
?>
<section>
  <h2>שווי כולל לאורך זמן</h2>
  <svg viewBox="0 0 900 260" style="width:100%;max-width:900px;height:auto;direction:ltr">
    <text x="2" y="<?= round($py($y1)) ?>" font-size="11" fill="#6b7280"><?= money($y1) ?></text>
    <text x="2" y="<?= round($py($y0)) ?>" font-size="11" fill="#6b7280"><?= money($y0) ?></text>
    <text x="40" y="258" font-size="11" fill="#6b7280"><?= h($pts[$n][0]) ?></text>
    <text x="890" y="258" font-size="11" fill="#6b7280" text-anchor="end"><?= h($pts[0][0]) ?></text>
    <path d="<?= $path ?>" fill="none" stroke="#2563eb" stroke-width="1.5"/>
  </svg>
</section>
<?php endif; ?>
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
