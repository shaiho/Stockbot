<?php
declare(strict_types=1);

function h(mixed $v): string
{
    return htmlspecialchars((string) $v, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

function num(?string $s): ?float
{
    $s = str_replace(',', '', trim((string) $s));
    return is_numeric($s) ? (float) $s : null;
}

function money(float $v, string $currency = 'ILS', bool $sign = false): string
{
    $sym = $currency === 'ILS' ? '₪' : '$';
    $s = number_format(abs($v), 2);
    $prefix = $v < -0.004 ? '-' : ($sign && $v > 0.004 ? '+' : '');
    return $prefix . $sym . $s;
}

function qty(float $v): string
{
    return rtrim(rtrim(number_format($v, 6, '.', ','), '0'), '.');
}

function pct(?float $v): string
{
    return $v === null ? '—' : sprintf('%+.2f%%', $v);
}

function session_badge(?string $session): string
{
    $label = ['pre' => 'פרה-מרקט', 'post' => 'אפטר-מרקט', 'closed' => 'סגור'][$session] ?? null;
    return $label ? ' <small class="badge">' . $label . '</small>' : '';
}

function tone(?float $v): string
{
    return $v === null || abs($v) < 0.005 ? '' : ($v > 0 ? 'pos' : 'neg');
}

function local_dt(DateTimeInterface $d, string $fmt = 'd/m/Y H:i'): string
{
    return DateTimeImmutable::createFromInterface($d)->setTimezone(new DateTimeZone(date_default_timezone_get()))->format($fmt);
}

/** @throws DomainException 'invalid_date' | 'future_date' */
function parse_trade_ts(string $raw): DateTimeImmutable
{
    $now = new DateTimeImmutable('now');
    $raw = trim($raw);
    if ($raw === '') {
        return $now;
    }
    foreach (['Y-m-d', 'd/m/Y', 'd-m-Y', 'd.m.Y'] as $fmt) {
        $d = DateTimeImmutable::createFromFormat('!' . $fmt, $raw);
        if ($d && $d->format($fmt) === $raw) {
            if ($d->format('Y-m-d') > $now->format('Y-m-d')) {
                throw new DomainException('future_date');
            }
            return $d->format('Y-m-d') === $now->format('Y-m-d') ? $now : $d->setTime(12, 0);
        }
    }
    throw new DomainException('invalid_date');
}

function redirect(string $url): never
{
    header('Location: ' . $url);
    exit;
}

function flash(string $type, string $msg): void
{
    $_SESSION['flash'][] = [$type, $msg];
}

function take_flash(): array
{
    $f = $_SESSION['flash'] ?? [];
    unset($_SESSION['flash']);
    return $f;
}

function csrf_token(): string
{
    return $_SESSION['csrf'] ??= bin2hex(random_bytes(32));
}

function csrf_field(): string
{
    return '<input type="hidden" name="csrf" value="' . h(csrf_token()) . '">';
}

function csrf_check(): void
{
    if (!hash_equals(csrf_token(), (string) ($_POST['csrf'] ?? ''))) {
        http_response_code(400);
        exit('Bad CSRF token');
    }
}

function session_boot(): void
{
    $https = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') || ($_SERVER['HTTP_X_FORWARDED_PROTO'] ?? '') === 'https';
    session_name('stockbot_web');
    session_set_cookie_params(['lifetime' => 0, 'path' => '/', 'httponly' => true, 'secure' => $https, 'samesite' => 'Lax']);
    session_start();
}

function password_ok(string $given): bool
{
    $want = (string) env('WEB_PASSWORD', '');
    if ($want === '' || $given === '') {
        return false;
    }
    return str_starts_with($want, '$2y$') || str_starts_with($want, '$argon2')
        ? password_verify($given, $want)
        : hash_equals($want, $given);
}

/** Max 5 failed logins / 15 min per IP (file based, survives cookie resets). */
function login_blocked(bool $recordFailure = false): bool
{
    $dir = WEB_ROOT . '/cache';
    is_dir($dir) || @mkdir($dir, 0775, true);
    $file = $dir . '/login_attempts.json';
    $ip = $_SERVER['REMOTE_ADDR'] ?? '?';
    $fh = fopen($file, 'c+');
    if (!$fh) {
        return false;
    }
    flock($fh, LOCK_EX);
    $all = json_decode((string) stream_get_contents($fh), true) ?: [];
    $cut = time() - 900;
    $all = array_filter(array_map(fn($ts) => array_values(array_filter($ts, fn($t) => $t > $cut)), $all));
    if ($recordFailure) {
        $all[$ip][] = time();
    }
    ftruncate($fh, 0);
    rewind($fh);
    fwrite($fh, json_encode($all));
    flock($fh, LOCK_UN);
    fclose($fh);
    return count($all[$ip] ?? []) >= 5;
}

function prices(): Prices
{
    static $p = null;
    return $p ??= new Prices(WEB_ROOT . '/cache', (int) env('PRICE_CACHE_SECONDS', '300'), env('FINNHUB_API_KEY'));
}

function repo(): Repo
{
    static $r = null;
    return $r ??= new Repo(Db::pdo());
}

function current_user_id(): int
{
    $id = env('WEB_TELEGRAM_ID');
    if (!$id || !ctype_digit($id)) {
        throw new RuntimeException('WEB_TELEGRAM_ID must be set in .env (the Telegram user whose accounts the site manages).');
    }
    return (int) $id;
}

/** Request-scoped profiler: prof_add('db', $ms) accumulates; prof_report() renders a footer line when WEB_DEBUG=1. */
function prof_add(string $key, float $ms, int $count = 1): void
{
    $GLOBALS['prof'][$key][0] = ($GLOBALS['prof'][$key][0] ?? 0) + $ms;
    $GLOBALS['prof'][$key][1] = ($GLOBALS['prof'][$key][1] ?? 0) + $count;
}

function prof_report(): string
{
    if (!filter_var(env('WEB_DEBUG'), FILTER_VALIDATE_BOOLEAN)) {
        return '';
    }
    $total = (microtime(true) - ($_SERVER['REQUEST_TIME_FLOAT'] ?? microtime(true))) * 1000;
    $parts = ['total ' . round($total) . 'ms'];
    foreach ($GLOBALS['prof'] ?? [] as $k => [$ms, $n]) {
        $parts[] = "$k " . round($ms) . "ms" . ($n > 1 ? " ×$n" : '');
    }
    return '<footer class="muted" style="margin-top:2rem">' . h(implode(' · ', $parts)) . '</footer>';
}

function render(string $view, array $vars = [], string $title = ''): never
{
    extract($vars);
    $flashes = take_flash();
    ob_start();
    require WEB_ROOT . '/views/' . $view . '.php';
    $content = ob_get_clean();
    $prof = prof_report();
    require WEB_ROOT . '/views/layout.php';
    exit;
}
