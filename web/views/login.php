<form class="card login" method="post" action="?a=login">
  <h1>Stockbot</h1>
  <?= csrf_field() ?>
  <label>סיסמה <input type="password" name="password" autofocus required></label>
  <button class="primary">כניסה</button>
</form>
