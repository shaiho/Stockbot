<?php
$statusLabels = ['open' => 'פתוחה', 'executed' => 'בוצעה', 'expired' => 'פקעה', 'cancelled' => 'בוטלה'];
$actLabels = ['buy' => 'קנייה', 'sell' => 'מכירה'];
?>
<div class="head"><h1>הוראות לביצוע</h1></div>

<p class="muted">ההוראות נבדקות מול המחיר החי בכל טעינת עמוד ובכל דקה בבוט. קנייה מופעלת כשהמחיר יורד לסנט מתחת ליעד, מכירה כשהוא עולה לסנט מעל היעד — כדי למנוע הפעלה על נגיעה במחיר שלא ממלאה הוראה אמיתית. פתיחת הוראה נעשית מעמוד התיק.</p>

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
