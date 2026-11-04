<?php
$statusLabels = ['open' => 'פתוחה', 'executed' => 'בוצעה', 'expired' => 'פקעה', 'cancelled' => 'בוטלה'];
$actLabels = ['buy' => 'קנייה', 'sell' => 'מכירה'];
?>
<div class="head"><h1>הוראות לביצוע</h1></div>

<p class="muted">ההוראות נבדקות מול המחיר החי בכל טעינת עמוד. קנייה מופעלת כשהמחיר יורד לסנט מתחת ליעד, מכירה כשהוא עולה לסנט מעל היעד — כדי למנוע הפעלה על נגיעה במחיר שלא ממלאה הוראה אמיתית.</p>

<form class="card form" method="post" action="?a=order_add">
  <h2>הוראה חדשה</h2>
  <?= csrf_field() ?>
  <label>תיק
    <select name="portfolio_id">
      <?php foreach ($portfolios as $p): ?><option value="<?= $p['id'] ?>"><?= h($p['name']) ?></option><?php endforeach; ?>
    </select>
  </label>
  <label>פעולה <select name="action_type"><option value="buy">קנייה</option><option value="sell">מכירה</option></select></label>
  <label>סימול <input name="symbol" required placeholder="AAPL / TEVA.TA"></label>
  <label>שוק <select name="market"><option value="">אוטומטי</option><option value="US">US</option><option value="IL">IL</option></select></label>
  <label>כמות <input name="quantity" inputmode="decimal" required></label>
  <label>מחיר יעד ליחידה <input name="price" inputmode="decimal" required></label>
  <label>בתוקף עד <input type="date" name="expires" value="<?= date('Y-m-d') ?>" min="<?= date('Y-m-d') ?>" required></label>
  <button class="primary">פתח הוראה</button>
</form>

<?php if ($orders): ?>
<div class="scroll"><table>
  <thead><tr><th>#</th><th>תיק</th><th>פעולה</th><th>סימול</th><th>כמות</th><th>מחיר יעד</th><th>תוקף</th><th>סטטוס</th><th></th></tr></thead>
  <tbody>
  <?php foreach ($orders as $o): ?>
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
        <?php if ($o['status'] === 'open'): ?>
          <form method="post" action="?a=order_cancel" data-confirm="לבטל את ההוראה #<?= $o['id'] ?>?"><?= csrf_field() ?><input type="hidden" name="order_id" value="<?= $o['id'] ?>"><button class="link danger">בטל</button></form>
        <?php endif; ?>
      </td>
    </tr>
  <?php endforeach; ?>
  </tbody>
</table></div>
<?php else: ?>
<p class="muted">אין הוראות.</p>
<?php endif; ?>
