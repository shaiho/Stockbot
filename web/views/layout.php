<!doctype html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title><?= h($title ? "$title · Stockbot" : 'Stockbot') ?></title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<?php if (!empty($_SESSION['auth'])): ?>
<header class="top">
  <a class="brand" href="?p=dashboard">Stockbot</a>
  <nav>
    <a href="?p=dashboard">תיקים</a>
    <a href="?p=watchlist">מעקב</a>
    <a href="?p=orders">הוראות <span id="orders-badge"></span></a>
    <a href="?p=alerts">התראות</a>
    <a href="?p=settings">הגדרות</a>
  </nav>
  <form method="post" action="?a=logout"><?= csrf_field() ?><button class="link">יציאה</button></form>
</header>
<?php endif; ?>
<main>
<?php foreach ($flashes as [$type, $msg]): ?>
  <div class="flash <?= h($type) ?>"><?= h($msg) ?></div>
<?php endforeach; ?>
<?= $content ?>
<?= $prof ?? '' ?>
</main>
<script>
document.querySelectorAll('form[data-confirm]').forEach(f =>
  f.addEventListener('submit', e => { if (!confirm(f.dataset.confirm)) e.preventDefault(); }));
fetch('?p=order_count').then(r => r.json()).then(d => {
  if (d.n > 0) document.getElementById('orders-badge').innerHTML = '<span class="nav-badge">' + d.n + '</span>';
}).catch(() => {});
</script>
</body>
</html>
