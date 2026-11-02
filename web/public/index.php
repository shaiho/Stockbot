<?php
declare(strict_types=1);

require __DIR__ . '/../src/bootstrap.php';
require __DIR__ . '/../src/actions.php';
require __DIR__ . '/../src/pages.php';

session_boot();
header('X-Frame-Options: DENY');
header('X-Content-Type-Options: nosniff');
header('Referrer-Policy: same-origin');

try {
    if ($_SERVER['REQUEST_METHOD'] === 'POST') {
        csrf_check();
        handle_action((string) ($_GET['a'] ?? ''));
    }
    handle_page((string) ($_GET['p'] ?? 'dashboard'));
} catch (Throwable $e) {
    error_log((string) $e);
    http_response_code(500);
    $detail = filter_var(env('WEB_DEBUG'), FILTER_VALIDATE_BOOLEAN) ? $e->getMessage() : 'שגיאה פנימית. פרטים ביומן השרת.';
    echo '<!doctype html><meta charset="utf-8"><body dir="rtl" style="font-family:sans-serif;padding:2rem"><h2>שגיאה</h2><p>' . h($detail) . '</p>';
}
