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

/** Market-closure / short-session notes for the header strip (US + IL). */
function market_notes(?array $usq, ?array $ilq): array
{
    $ilTz = new DateTimeZone('Asia/Jerusalem');
    $usTz = new DateTimeZone('America/New_York');
    $ilNow = new DateTimeImmutable('now', $ilTz);
    $usNow = new DateTimeImmutable('now', $usTz);

    // NYSE full-day closures (observed dates).
    static $usHolidays = [
        '2025-01-01' => 'ראש השנה', '2025-01-20' => 'יום מרטין לותר קינג',
        '2025-02-17' => 'יום הנשיאים', '2025-04-18' => 'יום השישי הטוב',
        '2025-05-26' => 'יום הזיכרון', '2025-06-19' => 'יום האמנציפציה',
        '2025-07-04' => 'יום העצמאות', '2025-09-01' => 'יום העבודה',
        '2025-11-27' => 'חג ההודיה', '2025-12-25' => 'חג המולד',
        '2026-01-01' => 'ראש השנה', '2026-01-19' => 'יום מרטין לותר קינג',
        '2026-02-16' => 'יום הנשיאים', '2026-04-03' => 'יום השישי הטוב',
        '2026-05-25' => 'יום הזיכרון', '2026-06-19' => 'יום האמנציפציה',
        '2026-07-03' => 'יום העצמאות', '2026-09-07' => 'יום העבודה',
        '2026-11-26' => 'חג ההודיה', '2026-12-25' => 'חג המולד',
    ];
    // NYSE early closes (13:00 ET).
    static $usEarly = ['2025-07-03', '2025-11-28', '2025-12-24', '2026-11-27', '2026-12-24'];

    $notes = [];
    $mk = function (string $flag, ?array $q, DateTimeImmutable $now, DateTimeZone $tz, callable $isDay, int $normalEnd, array $holidayNames, array $earlyDates) use ($ilTz, &$notes) {
        $today = $now->format('Y-m-d');
        $tomorrow = $now->modify('+1 day')->format('Y-m-d');
        $td = $q['trade_date'] ?? null;
        $end = isset($q['session_end']) ? (new DateTimeImmutable('@' . $q['session_end']))->setTimezone($tz) : null;
        $endIl = $end ? $end->setTimezone($ilTz)->format('H:i') : null;
        $earlyEnd = $end && (int) $end->format('Hi') < $normalEnd;

        if (isset($holidayNames[$today]) || ($isDay($now) && $td && $td > $today)) {
            $nm = $holidayNames[$today] ?? null;
            $back = $td ? ' — מסחר חוזר ב-' . (new DateTimeImmutable($td))->setTimezone($ilTz)->format('d/m') : '';
            $notes[] = "$flag היום סגור" . ($nm ? " — $nm" : $back);
        } elseif (in_array($today, $earlyDates, true) || ($td === $today && $earlyEnd)) {
            $notes[] = "$flag היום מסחר מקוצר" . ($endIl ? " — סגירה $endIl" : '');
        }
        if (isset($holidayNames[$tomorrow]) || ($isDay($now->modify('+1 day')) && $td && $td > $tomorrow)) {
            $nm = $holidayNames[$tomorrow] ?? null;
            $back = $td ? ' — מסחר חוזר ב-' . (new DateTimeImmutable($td))->setTimezone($ilTz)->format('d/m') : '';
            $notes[] = "$flag מחר סגור" . ($nm ? " — $nm" : $back);
        } elseif (in_array($tomorrow, $earlyDates, true) || ($td === $tomorrow && $earlyEnd)) {
            $notes[] = "$flag מחר מסחר מקוצר" . ($endIl ? " — סגירה $endIl" : '');
        }
    };
    $usDay = fn(DateTimeImmutable $d) => (int) $d->format('N') <= 5;
    $ilDay = fn(DateTimeImmutable $d) => (int) $d->format('N') === 7 || (int) $d->format('N') <= 4;
    $mk('🇺🇸', $usq, $usNow, $usTz, $usDay, 1600, $usHolidays, $usEarly);
    $mk('🇮🇱', $ilq, $ilNow, $ilTz, $ilDay, 1700, [], []);
    return $notes;
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
    $t0 = microtime(true);
    ob_start();
    require WEB_ROOT . '/views/' . $view . '.php';
    $content = ob_get_clean();
    prof_add('render', (microtime(true) - $t0) * 1000);
    $prof = prof_report();
    require WEB_ROOT . '/views/layout.php';
    exit;
}
