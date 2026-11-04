<div class="head"><h1>רשימת מעקב</h1></div>
<?php if ($items) { require __DIR__ . '/_refresh.php'; } ?>

<?php if (!$items): ?>
  <p class="muted">הרשימה ריקה.</p>
<?php else: ?>
<div class="scroll"><table>
  <thead><tr><th>סימול</th><th>שוק</th><th>מחיר</th><th>שינוי יומי</th><th></th></tr></thead>
  <tbody>
  <?php foreach ($items as $i): $q = $quotes[Prices::key($i['symbol'], $i['market'])] ?? null; $c = $i['market'] === 'IL' ? 'ILS' : 'USD'; ?>
    <tr>
      <td><b><?= h($i['symbol']) ?></b></td>
      <td><?= h($i['market']) ?></td>
      <td><?= $q ? money($q['price'], $c) . session_badge($q['session'] ?? null) : '—' ?></td>
      <td class="<?= tone($q['change_pct'] ?? null) ?>"><?= $q ? pct($q['change_pct']) : '—' ?></td>
      <td class="actions"><form method="post" action="?a=watch_remove"><?= csrf_field() ?><input type="hidden" name="id" value="<?= $i['id'] ?>"><button class="link danger">הסר</button></form></td>
    </tr>
  <?php endforeach; ?>
  </tbody>
</table></div>
<?php endif; ?>

<form class="card form" method="post" action="?a=watch_add">
  <h2>הוסף למעקב</h2>
  <?= csrf_field() ?>
  <label>סימול <input name="symbol" required placeholder="AAPL / TEVA.TA"></label>
  <label>שוק <select name="market"><option value="">אוטומטי</option><option value="US">US</option><option value="IL">IL</option></select></label>
  <button class="primary">הוסף</button>
</form>
