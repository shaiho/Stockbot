<?php
declare(strict_types=1);

const ALERT_TYPES = [
    'stock' => ['pct_daily', 'price_target', 'premarket', 'afterhours', 'volume_spike'],
    'watchlist' => ['pct_daily', 'price_target', 'premarket', 'afterhours', 'volume_spike', 'news'],
    'portfolio' => ['portfolio_value_change', 'daily_loss_limit', 'pnl_milestone'],
];

/** Redirect back with an error flash. */
function fail(string $msg, string $to): never
{
    flash('err', $msg);
    redirect($to);
}

function owned_portfolio(int $id): array
{
    $p = repo()->portfolio($id, current_user_id());
    if (!$p) {
        fail('התיק לא נמצא', '?p=dashboard');
    }
    return $p;
}

/** @return array{0:string,1:string} [SYMBOL, market] */
function parse_symbol(string $raw, string $marketChoice, array $heldMarkets = []): array
{
    $raw = strtoupper(trim($raw));
    $symbol = str_ends_with($raw, '.TA') ? substr($raw, 0, -3) : $raw;
    if (!preg_match('/^[A-Z0-9.\-^=]{1,20}$/', $symbol)) {
        throw new DomainException('סימול לא תקין');
    }
    if (in_array($marketChoice, ['US', 'IL'], true)) {
        return [$symbol, $marketChoice];
    }
    if (str_ends_with($raw, '.TA') || ctype_digit($symbol)) {
        return [$symbol, 'IL'];
    }
    $held = array_values(array_unique($heldMarkets));
    if (count($held) > 1) {
        throw new DomainException('הסימול מוחזק בשני שווקים — בחר שוק');
    }
    return [$symbol, $held[0] ?? 'US'];
}

function quote_exists(string $symbol, string $market): bool
{
    return (prices()->quotes([[$symbol, $market]])[Prices::key($symbol, $market)] ?? null) !== null;
}

function handle_action(string $a): never
{
    if ($a === 'login') {
        if (login_blocked()) {
            fail('יותר מדי ניסיונות. נסה שוב בעוד 15 דקות.', '?p=login');
        }
        if (!password_ok((string) ($_POST['password'] ?? ''))) {
            login_blocked(true);
            fail('סיסמה שגויה', '?p=login');
        }
        session_regenerate_id(true);
        $_SESSION['auth'] = true;
        redirect('?p=dashboard');
    }
    if ($a === 'logout') {
        session_destroy();
        redirect('?p=login');
    }
    if (empty($_SESSION['auth'])) {
        redirect('?p=login');
    }

    $uid = current_user_id();
    $repo = repo();
    $repo->user($uid);
    $back = fn(int $pid) => '?p=portfolio&id=' . $pid;

    switch ($a) {
        case 'portfolio_create':
            $name = trim((string) ($_POST['name'] ?? ''));
            $ils = num($_POST['cash_ils'] ?? '0') ?? -1;
            $usd = num($_POST['cash_usd'] ?? '0') ?? -1;
            if ($name === '' || mb_strlen($name) > 50 || $ils < 0 || $usd < 0) {
                fail('שם או מזומן פתיחה לא תקינים', '?p=dashboard');
            }
            try {
                $p = $repo->createPortfolio($uid, $name, $ils, $usd);
            } catch (DomainException $e) {
                fail($e->getMessage() === 'max_portfolios' ? 'ניתן ליצור עד ' . MAX_PORTFOLIOS . ' תיקים' : 'כבר קיים תיק בשם הזה', '?p=dashboard');
            }
            flash('ok', 'התיק נוצר');
            redirect($back($p['id']));

        case 'portfolio_rename':
            $p = owned_portfolio((int) ($_POST['portfolio_id'] ?? 0));
            $name = trim((string) ($_POST['name'] ?? ''));
            if ($name === '' || mb_strlen($name) > 50) {
                fail('שם לא תקין', $back($p['id']));
            }
            try {
                $repo->renamePortfolio($p['id'], $uid, $name);
            } catch (DomainException) {
                fail('כבר קיים תיק בשם הזה', $back($p['id']));
            }
            flash('ok', 'השם עודכן');
            redirect($back($p['id']));

        case 'portfolio_cash':
            $p = owned_portfolio((int) ($_POST['portfolio_id'] ?? 0));
            $ils = num($_POST['cash_ils'] ?? '');
            $usd = num($_POST['cash_usd'] ?? '');
            if ($ils === null || $usd === null || $ils < 0 || $usd < 0) {
                fail('מזומן פתיחה לא תקין', $back($p['id']));
            }
            $repo->updateOpeningCash($p['id'], $uid, $ils, $usd);
            flash('ok', 'מזומן הפתיחה עודכן');
            redirect($back($p['id']));

        case 'portfolio_commission':
            $p = owned_portfolio((int) ($_POST['portfolio_id'] ?? 0));
            $minUsd = num($_POST['min_usd'] ?? '');
            $minIls = num($_POST['min_ils'] ?? '');
            $val = num($_POST['extra_value'] ?? '');
            $type = $_POST['extra_type'] ?? '';
            if (in_array(null, [$minUsd, $minIls, $val], true) || min($minUsd, $minIls, $val) < 0 || !in_array($type, ['fixed', 'percent'], true)) {
                fail('הגדרות עמלה לא תקינות', $back($p['id']));
            }
            $repo->updateCommission($p['id'], $uid, $minUsd, $minIls, $type, $val);
            flash('ok', 'הגדרות העמלה נשמרו');
            redirect($back($p['id']));

        case 'portfolio_recalc':
            $p = owned_portfolio((int) ($_POST['portfolio_id'] ?? 0));
            $n = $repo->recalculateCommissions($p, $uid);
            flash('ok', "עמלות חושבו מחדש ל-$n עסקאות");
            redirect($back($p['id']));

        case 'portfolio_clear_trades':
            $p = owned_portfolio((int) ($_POST['portfolio_id'] ?? 0));
            $n = $repo->deletePortfolioTrades($p['id'], $uid);
            flash('ok', "נמחקו $n עסקאות");
            redirect($back($p['id']));

        case 'portfolio_delete':
            $p = owned_portfolio((int) ($_POST['portfolio_id'] ?? 0));
            $repo->deletePortfolio($p['id'], $uid);
            $user = $repo->user($uid);
            if ($user['last_portfolio_id'] === $p['id']) {
                $left = $repo->portfolios($uid);
                $user['last_portfolio_id'] = $left ? $left[0]['id'] : null;
                $repo->updateUser($uid, $user);
            }
            flash('ok', 'התיק נמחק');
            redirect('?p=dashboard');

        case 'trade_add':
            $p = owned_portfolio((int) ($_POST['portfolio_id'] ?? 0));
            $to = $back($p['id']);
            $action = $_POST['action_type'] ?? '';
            if (!in_array($action, ['buy', 'sell', 'dividend'], true)) {
                fail('פעולה לא תקינה', $to);
            }
            $trades = $repo->trades($p['id']);
            $holdings = Calc::holdings($trades);
            $sym = strtoupper(trim((string) ($_POST['symbol'] ?? '')));
            $sym = str_ends_with($sym, '.TA') ? substr($sym, 0, -3) : $sym;
            $heldMarkets = array_column(array_filter($holdings, fn($h) => strtoupper($h['symbol']) === $sym), 'market');
            try {
                [$symbol, $market] = parse_symbol((string) ($_POST['symbol'] ?? ''), (string) ($_POST['market'] ?? ''), $action === 'sell' ? $heldMarkets : []);
                $ts = parse_trade_ts((string) ($_POST['date'] ?? ''));
            } catch (DomainException $e) {
                fail(['invalid_date' => 'תאריך לא תקין', 'future_date' => 'תאריך עתידי אינו מותר'][$e->getMessage()] ?? $e->getMessage(), $to);
            }
            $quantity = $action === 'dividend' ? 1.0 : num($_POST['quantity'] ?? '');
            $price = num($_POST['price'] ?? '');
            if ($quantity === null || $quantity <= 0 || $price === null || $price <= 0) {
                fail('כמות/מחיר לא תקינים', $to);
            }
            $currency = $market === 'IL' ? 'ILS' : 'USD';

            if ($action === 'sell') {
                $held = array_values(array_filter($holdings, fn($h) => $h['symbol'] === $symbol && $h['market'] === $market));
                if (!$held || $held[0]['quantity'] + 1e-9 < $quantity) {
                    fail('אין מספיק יחידות למכירה', $to);
                }
            } else {
                $known = array_filter($trades, fn($t) => $t['symbol'] === $symbol && $t['market'] === $market);
                if (!$known && !quote_exists($symbol, $market)) {
                    fail('הסימול לא נמצא בשוק ' . $market, $to);
                }
            }

            $commission = 0.0;
            if ($action !== 'dividend') {
                $raw = trim((string) ($_POST['commission'] ?? ''));
                $commission = $raw === '' ? Calc::commission($p, $quantity, $price, $currency) : num($raw);
                if ($commission === null || $commission < 0) {
                    fail('עמלה לא תקינה', $to);
                }
            }
            $note = trim((string) ($_POST['note'] ?? '')) ?: null;
            $repo->addTrade($p['id'], $symbol, $market, 'stock', $action, $quantity, $price, $currency, $commission, $note, $ts);
            flash('ok', 'העסקה נשמרה');
            redirect($to);

        case 'cash_add':
            $p = owned_portfolio((int) ($_POST['portfolio_id'] ?? 0));
            $to = $back($p['id']);
            $kind = $_POST['kind'] ?? '';
            $currency = $_POST['currency'] ?? '';
            $amount = num($_POST['amount'] ?? '');
            if (!in_array($kind, ['deposit', 'withdraw'], true) || !in_array($currency, ['ILS', 'USD'], true) || $amount === null || $amount <= 0) {
                fail('פרטי מזומן לא תקינים', $to);
            }
            try {
                $ts = parse_trade_ts((string) ($_POST['date'] ?? ''));
            } catch (DomainException $e) {
                fail($e->getMessage() === 'future_date' ? 'תאריך עתידי אינו מותר' : 'תאריך לא תקין', $to);
            }
            if ($kind === 'withdraw') {
                [$ils, $usd] = Calc::cashBalances($p, $repo->trades($p['id']));
                if (($currency === 'ILS' ? $ils : $usd) + 1e-9 < $amount) {
                    fail('אין מספיק מזומן למשיכה', $to);
                }
            }
            $repo->addCash($p['id'], $kind, $currency, $amount, trim((string) ($_POST['note'] ?? '')) ?: null, $ts);
            flash('ok', $kind === 'deposit' ? 'ההפקדה נשמרה' : 'המשיכה נשמרה');
            redirect($to);

        case 'order_add':
            $p = owned_portfolio((int) ($_POST['portfolio_id'] ?? 0));
            $action = $_POST['action_type'] ?? '';
            if (!in_array($action, ['buy', 'sell'], true)) {
                fail('פעולה לא תקינה', '?p=orders');
            }
            $trades = $repo->trades($p['id']);
            $holdings = Calc::holdings($trades);
            $sym = strtoupper(trim((string) ($_POST['symbol'] ?? '')));
            $sym = str_ends_with($sym, '.TA') ? substr($sym, 0, -3) : $sym;
            $heldMarkets = array_column(array_filter($holdings, fn($h) => strtoupper($h['symbol']) === $sym), 'market');
            try {
                [$symbol, $market] = parse_symbol((string) ($_POST['symbol'] ?? ''), (string) ($_POST['market'] ?? ''), $action === 'sell' ? $heldMarkets : []);
            } catch (DomainException $e) {
                fail($e->getMessage(), '?p=orders');
            }
            $quantity = num($_POST['quantity'] ?? '');
            $price = num($_POST['price'] ?? '');
            $expires = trim((string) ($_POST['expires'] ?? ''));
            if ($quantity === null || $quantity <= 0 || $price === null || $price <= 0) {
                fail('כמות/מחיר לא תקינים', '?p=orders');
            }
            if (!preg_match('/^\d{4}-\d{2}-\d{2}$/', $expires) || !strtotime($expires) || $expires < Calc::today()) {
                fail('תאריך פקיעה לא תקין (חייב להיות היום או בעתיד)', '?p=orders');
            }
            if ($action === 'sell') {
                $held = array_values(array_filter($holdings, fn($h) => $h['symbol'] === $symbol && $h['market'] === $market));
                if (!$held || $held[0]['quantity'] + 1e-9 < $quantity) {
                    fail('אין מספיק יחידות למכירה', '?p=orders');
                }
            } else {
                $known = array_filter($trades, fn($t) => $t['symbol'] === $symbol && $t['market'] === $market);
                if (!$known && !quote_exists($symbol, $market)) {
                    fail('הסימול לא נמצא בשוק ' . $market, '?p=orders');
                }
            }
            $id = $repo->addOrder($uid, $p['id'], $symbol, $market, $action, $quantity, $price, $market === 'IL' ? 'ILS' : 'USD', $expires);
            flash('ok', sprintf('הוראה #%d נפתחה: %s %s %s במחיר %s, בתוקף עד %s', $id, $action === 'buy' ? 'קניית' : 'מכירת', qty($quantity), $symbol, $price, $expires));
            redirect('?p=orders');

        case 'fx_set':
            $v = num($_POST['fx'] ?? '');
            if ($v !== null && $v > 0) {
                $_SESSION['fx_manual'] = $v;
                flash('ok', 'שער ידני הוגדר: ' . $v);
            } else {
                unset($_SESSION['fx_manual']);
                flash('ok', 'שער ידני בוטל — חוזרים לשער החי');
            }
            redirect((string) ($_POST['back'] ?? '?p=dashboard'));

        case 'order_edit':
            $quantity = num($_POST['quantity'] ?? '');
            $price = num($_POST['price'] ?? '');
            $expires = trim((string) ($_POST['expires'] ?? ''));
            if ($quantity === null || $quantity <= 0 || $price === null || $price <= 0) {
                fail('כמות/מחיר לא תקינים', '?p=orders');
            }
            if (!preg_match('/^\d{4}-\d{2}-\d{2}$/', $expires) || !strtotime($expires) || $expires < Calc::today()) {
                fail('תאריך פקיעה לא תקין', '?p=orders');
            }
            if ($repo->updateOrder((int) ($_POST['order_id'] ?? 0), $uid, $quantity, $price, $expires)) {
                flash('ok', 'ההוראה עודכנה');
            } else {
                fail('ההוראה לא נמצאה או שאינה פתוחה', '?p=orders');
            }
            redirect('?p=orders');

        case 'order_cancel':
            if ($repo->cancelOrder((int) ($_POST['order_id'] ?? 0), $uid)) {
                flash('ok', 'ההוראה בוטלה');
            }
            redirect('?p=orders');

        case 'trade_update':
            $trade = $repo->trade((int) ($_POST['trade_id'] ?? 0), $uid);
            if (!$trade) {
                fail('העסקה לא נמצאה', '?p=dashboard');
            }
            $p = owned_portfolio($trade['portfolio_id']);
            $to = $back($p['id']);
            $self = '?p=trade&id=' . $trade['id'];
            $fields = [];
            $isCash = $trade['asset_type'] === 'cash';
            $isDividend = $trade['action'] === 'dividend';
            $isTrade = !$isCash && !$isDividend;

            if ($isCash || $isTrade) {
                $q = num($_POST['quantity'] ?? '');
                if ($q === null || $q <= 0) {
                    fail('כמות לא תקינה', $self);
                }
                if (abs($q - $trade['quantity']) > 1e-12) {
                    $fields['quantity'] = $q;
                }
            }
            if (!$isCash) {
                $price = num($_POST['price'] ?? '');
                if ($price === null || $price <= 0) {
                    fail('מחיר לא תקין', $self);
                }
                if (abs($price - $trade['price']) > 1e-12) {
                    $fields['price'] = $price;
                }
            }
            if ($isTrade) {
                $c = num($_POST['commission'] ?? '');
                if ($c === null || $c < 0) {
                    fail('עמלה לא תקינה', $self);
                }
                if (abs($c - $trade['commission']) > 1e-12) {
                    $fields['commission'] = $c;
                } elseif (isset($fields['quantity']) || isset($fields['price'])) {
                    $fields['commission'] = Calc::commission($p, $fields['quantity'] ?? $trade['quantity'], $fields['price'] ?? $trade['price'], $trade['currency']);
                }
            }
            $date = trim((string) ($_POST['date'] ?? ''));
            if ($date !== '' && $date !== local_dt($trade['ts'], 'Y-m-d')) {
                try {
                    $fields['timestamp'] = parse_trade_ts($date);
                } catch (DomainException $e) {
                    fail($e->getMessage() === 'future_date' ? 'תאריך עתידי אינו מותר' : 'תאריך לא תקין', $self);
                }
            }
            $fields['note'] = trim((string) ($_POST['note'] ?? '')) ?: null;
            $repo->updateTrade($trade['id'], $uid, $fields);
            flash('ok', 'העסקה עודכנה');
            redirect($to);

        case 'trade_delete':
            $trade = $repo->trade((int) ($_POST['trade_id'] ?? 0), $uid);
            if (!$trade) {
                fail('העסקה לא נמצאה', '?p=dashboard');
            }
            $repo->deleteTrade($trade['id'], $uid);
            flash('ok', 'העסקה נמחקה');
            redirect($back($trade['portfolio_id']));

        case 'watch_add':
            try {
                [$symbol, $market] = parse_symbol((string) ($_POST['symbol'] ?? ''), (string) ($_POST['market'] ?? ''));
            } catch (DomainException $e) {
                fail($e->getMessage(), '?p=watchlist');
            }
            if (!quote_exists($symbol, $market)) {
                fail('הסימול לא נמצא בשוק ' . $market, '?p=watchlist');
            }
            try {
                $repo->addWatchlist($uid, $symbol, $market);
            } catch (DomainException) {
                fail('הסימול כבר ברשימת המעקב', '?p=watchlist');
            }
            flash('ok', 'נוסף לרשימת המעקב');
            redirect('?p=watchlist');

        case 'watch_remove':
            $repo->removeWatchlist((int) ($_POST['id'] ?? 0), $uid);
            redirect('?p=watchlist');

        case 'alert_add':
            $scope = $_POST['scope'] ?? '';
            $type = $_POST['alert_type'] ?? '';
            if (!isset(ALERT_TYPES[$scope]) || !in_array($type, ALERT_TYPES[$scope], true)) {
                fail('סוג התראה לא תקין', '?p=alerts');
            }
            $config = [];
            if ($scope === 'portfolio') {
                $p = owned_portfolio((int) ($_POST['portfolio_id'] ?? 0));
                $config['portfolio_id'] = $p['id'];
                if ($type === 'pnl_milestone') {
                    $v = num($_POST['threshold_ils'] ?? '');
                    if ($v === null) {
                        fail('סכום לא תקין', '?p=alerts');
                    }
                    $config['threshold_ils'] = $v;
                } else {
                    $v = num($_POST['threshold_pct'] ?? '');
                    if ($v === null || $v <= 0) {
                        fail('אחוז לא תקין', '?p=alerts');
                    }
                    $config['threshold_pct'] = $v;
                }
            } else {
                try {
                    [$symbol, $market] = parse_symbol((string) ($_POST['symbol'] ?? ''), (string) ($_POST['market'] ?? ''));
                } catch (DomainException $e) {
                    fail($e->getMessage(), '?p=alerts');
                }
                if (!quote_exists($symbol, $market)) {
                    fail('הסימול לא נמצא בשוק ' . $market, '?p=alerts');
                }
                $config = ['symbol' => $symbol, 'market' => $market];
                if ($type === 'price_target') {
                    $v = num($_POST['target_price'] ?? '');
                    $dir = $_POST['direction'] ?? '';
                    if ($v === null || $v <= 0 || !in_array($dir, ['above', 'below'], true)) {
                        fail('מחיר יעד לא תקין', '?p=alerts');
                    }
                    $config += ['target_price' => $v, 'direction' => $dir];
                } elseif (in_array($type, ['pct_daily', 'premarket', 'afterhours'], true)) {
                    $v = num($_POST['threshold_pct'] ?? '');
                    if ($v === null || $v <= 0) {
                        fail('אחוז לא תקין', '?p=alerts');
                    }
                    $config['threshold_pct'] = $v;
                } elseif ($type === 'volume_spike') {
                    $config['multiplier'] = 2.0;
                }
            }
            $repo->addAlertRule($uid, $scope, $type, $config);
            flash('ok', 'ההתראה נוצרה');
            redirect('?p=alerts');

        case 'alert_delete':
            $repo->deleteAlertRule((int) ($_POST['id'] ?? 0), $uid);
            redirect('?p=alerts');

        case 'settings_save':
            $user = $repo->user($uid);
            $comm = num($_POST['default_commission'] ?? '');
            $thr = num($_POST['mover_threshold_pct'] ?? '');
            $re = '/^([01]\d|2[0-3]):([0-5]\d)$/';
            $m = trim((string) ($_POST['report_morning'] ?? ''));
            $e = trim((string) ($_POST['report_evening'] ?? ''));
            if (
                !in_array($_POST['language'] ?? '', ['he', 'en'], true)
                || !in_array($_POST['default_commission_currency'] ?? '', ['ILS', 'USD'], true)
                || $comm === null || $comm < 0 || $thr === null || $thr <= 0
                || !preg_match($re, $m) || !preg_match($re, $e)
            ) {
                fail('אחד הערכים לא תקין (שעות בפורמט HH:MM)', '?p=settings');
            }
            $repo->updateUser($uid, [
                'language' => $_POST['language'],
                'default_commission' => $comm,
                'default_commission_currency' => $_POST['default_commission_currency'],
                'report_morning' => $m,
                'report_evening' => $e,
                'mover_threshold_pct' => $thr,
                'last_portfolio_id' => $user['last_portfolio_id'],
            ]);
            flash('ok', 'ההגדרות נשמרו');
            redirect('?p=settings');
    }
    fail('פעולה לא מוכרת', '?p=dashboard');
}
