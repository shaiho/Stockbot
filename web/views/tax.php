<?php $r = $report; ?>
<div class="head">
  <h1>דוח מס <?= $r['year'] ?> — <?= h($p['name']) ?></h1>
  <a href="?p=portfolio&id=<?= $p['id'] ?>">← התיק</a>
</div>

<?php if (count($years) > 1): ?>
<p class="filter muted">שנה:
  <?php foreach ($years as $y): ?>
    <a class="chip <?= $y === $r['year'] ? '' : 'muted' ?>" href="?p=tax&id=<?= $p['id'] ?>&year=<?= $y ?>"><?= $y ?></a>
  <?php endforeach; ?>
</p>
<?php endif; ?>

<div class="stats">
  <div class="card"><span>רווח ממומש ברוטו</span><b class="<?= tone($r['gross']) ?>"><?= money($r['gross'], 'ILS', true) ?></b></div>
  <div class="card"><span>עמלות</span><b><?= money($r['commissions']) ?></b></div>
  <div class="card"><span>חייב במס</span><b class="<?= tone($r['taxable']) ?>"><?= money($r['taxable'], 'ILS', true) ?></b></div>
  <div class="card"><span>מס משוער (25%)</span><b class="neg"><?= money($r['tax']) ?></b></div>
  <div class="card"><span>נטו אחרי מס</span><b class="<?= tone($r['net']) ?>"><?= money($r['net'], 'ILS', true) ?></b></div>
</div>

<p class="muted">חישוב: ממומש ממכירות + דיבידנדים בשנה (עלות ממוצעת לפי עסקאות השנה בלבד), פחות עמלות. הערכה בלבד — אינה ייעוץ מס.</p>

<?php if ($r['by_symbol']): ?>
<div class="scroll"><table class="sortable">
  <thead><tr><th>נייר</th><th>ממומש ₪</th></tr></thead>
  <tbody>
  <?php foreach ($r['by_symbol'] as $sym => $v): ?>
    <tr>
      <td><a href="?p=symbol&symbol=<?= h($sym) ?>"><b><?= h($sym) ?></b></a></td>
      <td class="<?= tone($v) ?>"><?= money($v, 'ILS', true) ?></td>
    </tr>
  <?php endforeach; ?>
  </tbody>
</table></div>
<?php else: ?>
<p class="muted">אין רווחים ממומשים בשנה זו.</p>
<?php endif; ?>
