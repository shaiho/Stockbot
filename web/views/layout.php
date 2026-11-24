<!doctype html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title><?= h($title ? "$title · Stockbot" : 'Stockbot') ?></title>
<link rel="stylesheet" href="style.css">
<link rel="manifest" href="manifest.json">
<meta name="theme-color" content="#2563eb">
<link rel="icon" href="icon-192.png">
<script>const th = localStorage.getItem('theme'); if (th) document.documentElement.dataset.theme = th;</script>
</head>
<body>
<?php if (!empty($_SESSION['auth'])): ?>
<header class="top">
  <a class="brand" href="?p=dashboard">Stockbot</a>
  <span id="mkt-dots" class="muted"></span>
  <nav>
    <a href="?p=dashboard">תיקים</a>
    <a href="?p=watchlist">מעקב</a>
    <a href="?p=orders">הוראות <span id="orders-badge"></span></a>
    <a href="?p=alerts">התראות</a>
    <a href="?p=settings">הגדרות</a>
  </nav>
  <form method="get" class="nav-search"><input type="hidden" name="p" value="symbol"><input name="symbol" placeholder="🔍 סימול" autocomplete="off" spellcheck="false" style="text-transform:uppercase"></form>
  <button type="button" class="link" id="theme-toggle" title="מצב כהה/בהיר">🌓</button>
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
document.addEventListener('submit', e => {
  const f = e.target.closest && e.target.closest('form[data-confirm]');
  if (f && !confirm(f.dataset.confirm)) e.preventDefault();
});
window.updateOrderBadge = () => fetch('?p=order_count').then(r => r.json()).then(d => {
  document.getElementById('orders-badge').innerHTML = d.n > 0 ? '<span class="nav-badge">' + d.n + '</span>' : '';
}).catch(() => {});
window.updateOrderBadge();
fetch('?p=mkt_status').then(r => r.json()).then(d => {
  const cls = {regular: '🟢', pre: '🟡', post: '🟡', closed: '🔴'};
  const lbl = {regular: 'מסחר', pre: 'פרה-מרקט', post: 'אפטר-מרקט', closed: 'סגור'};
  document.getElementById('mkt-dots').innerHTML =
    `US ${cls[d.us] || ''} <small>${lbl[d.us] || d.us}</small> · IL ${cls[d.il] || ''} <small>${lbl[d.il] || d.il}</small>`;
}).catch(() => {});
document.getElementById('theme-toggle')?.addEventListener('click', () => {
  const cur = document.documentElement.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  const next = cur === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  localStorage.setItem('theme', next);
});
</script>
</body>
</html>
