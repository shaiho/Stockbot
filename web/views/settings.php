<div class="head"><h1>הגדרות</h1></div>

<form class="card form" method="post" action="?a=settings_save">
  <?= csrf_field() ?>
  <label>שפת הבוט
    <select name="language">
      <option value="he" <?= $u['language'] === 'he' ? 'selected' : '' ?>>עברית</option>
      <option value="en" <?= $u['language'] === 'en' ? 'selected' : '' ?>>English</option>
    </select>
  </label>
  <label>עמלת ברירת מחדל <input name="default_commission" inputmode="decimal" value="<?= h($u['default_commission']) ?>"></label>
  <label>מטבע עמלה
    <select name="default_commission_currency">
      <option value="USD" <?= $u['default_commission_currency'] === 'USD' ? 'selected' : '' ?>>$ USD</option>
      <option value="ILS" <?= $u['default_commission_currency'] === 'ILS' ? 'selected' : '' ?>>₪ ILS</option>
    </select>
  </label>
  <label>דוח בוקר (HH:MM) <input name="report_morning" pattern="([01]\d|2[0-3]):[0-5]\d" value="<?= h($u['report_morning']) ?>" required></label>
  <label>דוח ערב (HH:MM) <input name="report_evening" pattern="([01]\d|2[0-3]):[0-5]\d" value="<?= h($u['report_evening']) ?>" required></label>
  <label>סף תנועה יומית (%) <input name="mover_threshold_pct" inputmode="decimal" value="<?= h($u['mover_threshold_pct']) ?>"></label>
  <button class="primary">שמור</button>
</form>
