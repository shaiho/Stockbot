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
<p class="muted">היום:
  <?php foreach ($portfolios as $p): $s = $data[$p['id']]['sum']; ?>
    <a class="chip <?= tone($s['daily_change_ils']) ?>" href="?p=portfolio&id=<?= $p['id'] ?>"><?= h($p['name']) ?> <?= money($s['daily_change_ils'], 'ILS', true) ?></a>
  <?php endforeach; ?>
  <?php foreach ([['SPY', 'US', 'SPY'], ['TA35', 'IL', 'TA-35']] as [$bs, $bm, $bl]): $bq = $bench[Prices::key($bs, $bm)] ?? null; ?>
    <?php if ($bq && $bq['price']): ?><span class="chip <?= tone($bq['change_pct']) ?>" title="<?= h($bl) ?>"><?= h($bl) ?> <?= pct($bq['change_pct']) ?></span><?php endif; ?>
  <?php endforeach; ?>
</p>
<?php if (count($snapshots) >= 2):
    $pts = array_map(fn($s) => ['time' => $s['date'], 'value' => (float) $s['total_ils']], $snapshots);
?>
<section>
  <h2>שווי כולל לאורך זמן <small id="vchart-legend" class="muted"></small></h2>
  <div id="vchart" class="lchart"></div>
</section>
<script>
(() => {
  const data = <?= json_encode($pts) ?>;
  mkAreaChart(document.getElementById('vchart'), data, document.getElementById('vchart-legend'));
})();
</script>
<?php endif; ?>
<?php endif; ?>

<?php if (!empty($upcoming)): ?>
<p class="muted">אירועים קרובים:
  <?php foreach ($upcoming as $e): ?>
    <span class="chip warn"><?= h($e['symbol']) ?> · <?= h($e['date']) ?><?= $e['amount'] !== null ? ' · ' . number_format($e['amount'], 3) : '' ?></span>
  <?php endforeach; ?>
</p>
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
