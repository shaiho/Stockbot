<?php
declare(strict_types=1);

const WEB_ROOT = __DIR__ . '/..';
const MAX_PORTFOLIOS = 5;

function load_env(string $path): array
{
    $vars = [];
    if (!is_file($path)) {
        return $vars;
    }
    foreach (file($path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
        $line = trim($line);
        if ($line === '' || $line[0] === '#' || !str_contains($line, '=')) {
            continue;
        }
        [$k, $v] = explode('=', $line, 2);
        $v = trim($v);
        if (strlen($v) >= 2 && ($v[0] === '"' || $v[0] === "'") && $v[-1] === $v[0]) {
            $v = substr($v, 1, -1);
        } else {
            $v = rtrim(preg_replace('/\s+#.*$/', '', $v));
        }
        $vars[trim($k)] = $v;
    }
    return $vars;
}

function env(string $key, ?string $default = null): ?string
{
    static $file = null;
    $file ??= load_env(WEB_ROOT . '/../.env');
    $v = getenv($key);
    if ($v !== false && $v !== '') {
        return $v;
    }
    $v = $file[$key] ?? '';
    return $v !== '' ? $v : $default;
}

date_default_timezone_set(env('TIMEZONE', 'Asia/Jerusalem'));

require __DIR__ . '/Db.php';
require __DIR__ . '/Repo.php';
require __DIR__ . '/Prices.php';
require __DIR__ . '/Calc.php';
require __DIR__ . '/helpers.php';
