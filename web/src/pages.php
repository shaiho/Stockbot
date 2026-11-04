<?php
declare(strict_types=1);

/** @return array{0: array<int, array>, 1: array<string, array|null>} [per-portfolio data, quotes] */
function summaries(array $portfolios, bool $fresh = false, ?array $tradesBy = null): array
{
    $tradesBy ??= repo()->tradesForPortfolios(array_column($portfolios, 'id'));
    $pairs = [['USDILS=X', 'FX']];
    foreach ($portfolios as $p) {
        array_push($pairs, ...Calc::quotePairs($tradesBy[$p['id']]));
    }
    $quotes = prices()->quotes($pairs, $fresh);
    $fx = $quotes[Prices::key('USDILS=X', 'FX')]['price'] ?? 3.7;
    $out = [];
    $t0 = microtime(true);
    foreach ($portfolios as $p) {
        $out[$p['id']] = ['trades' => $tradesBy[$p['id']], 'sum' => Calc::summary($p, $tradesBy[$p['id']], $quotes, $fx)];
    }
    prof_add('calc', (microtime(true) - $t0) * 1000, count($portfolios));
    return [$out, $quotes];
}

/** Timestamp of the oldest quote used, or null when there are none. */
function priced_at(array $quotes): ?int
{
    $ts = array_filter(array_map(fn($q) => $q['ts'] ?? null, $quotes));
    return $ts ? (int) min($ts) : null;
}

/** Expire stale limit orders and execute triggered ones against fresh quotes. Runs on every page load. */
function process_orders(int $uid): void
{
    // The bot sweeps every minute too; skip a fresh sweep if this session ran one <30s ago.
    if (($_SESSION['orders_checked'] ?? 0) > time() - 30) {
        return;
    }
    $_SESSION['orders_checked'] = time();
    $repo = repo();
    $today = Calc::today();
    $t0 = microtime(true);
    $repo->expireOrders($uid, $today);
    $open = $repo->openOrders($uid);
    if (!$open) {
        return;
    }
    $quotes = prices()->quotes(array_map(fn($o) => [$o['symbol'], $o['market']], $open), true);
    foreach ($open as $o) {
        $q = $quotes[Prices::key($o['symbol'], $o['market'])] ?? null;
        if (!$q) {
            continue;
        }
        $px = $q['price'];
        $hit = $o['action'] === 'buy' ? $px <= $o['limit_price'] - 0.01 : $px >= $o['limit_price'] + 0.01;
        if (!$hit) {
            continue;
        }
        if ($o['action'] === 'sell') {
            $held = array_values(array_filter(
                Calc::holdings($repo->trades($o['portfolio_id'])),
                fn($h) => strtoupper($h['symbol']) === strtoupper($o['symbol']) && $h['market'] === $o['market']
            ));
            if (!$held || $held[0]['quantity'] + 1e-9 < $o['quantity']) {
                continue;
            }
        }
        $p = $repo->portfolio($o['portfolio_id'], $uid);
        if (!$p) {
            continue;
        }
        $commission = Calc::commission($p, $o['quantity'], $o['limit_price'], $o['currency']);
        $note = sprintf('הוראת לימיט #%d (ציטוט %s בעת ההפעלה)', $o['id'], rtrim(rtrim(number_format($px, 4, '.', ''), '0'), '.'));
        $tid = $repo->addTrade($o['portfolio_id'], $o['symbol'], $o['market'], 'stock', $o['action'], $o['quantity'], $o['limit_price'], $o['currency'], $commission, $note, null);
        $repo->resolveOrder($o['id'], 'executed', $tid);
        flash('ok', sprintf('הוראה #%d בוצעה: %s %s %s במחיר %s', $o['id'], $o['action'] === 'buy' ? 'קניית' : 'מכירת', qty($o['quantity']), $o['symbol'], money($o['limit_price'], $o['currency'])));
    }
    prof_add('orders', (microtime(true) - $t0) * 1000);
}

function handle_page(string $page): never
{
    if ($page === 'login') {
        render('login', [], 'כניסה');
    }
    if (empty($_SESSION['auth'])) {
        redirect('?p=login');
    }

    $uid = current_user_id();
    $repo = repo();
    $fresh = ($_GET['refresh'] ?? '') === '1';
    process_orders($uid);

    switch ($page) {
        case 'portfolio':
            [$ports, $tradesBy] = $repo->portfoliosWithTrades($uid);
            $id = (int) ($_GET['id'] ?? 0);
            $p = array_values(array_filter($ports, fn($x) => $x['id'] === $id))[0] ?? null;
            if (!$p) {
                fail('התיק לא נמצא', '?p=dashboard');
            }
            [$data, $quotes] = summaries([$p], $fresh, $tradesBy);
            $all = $data[$p['id']];
            render('portfolio', ['p' => $p, 'trades' => array_reverse($all['trades']), 'sum' => $all['sum'], 'pricedAt' => priced_at($quotes)], $p['name']);

        case 'symbol':
            $symbol = strtoupper(trim((string) ($_GET['symbol'] ?? '')));
            if (!preg_match('/^[A-Z0-9.\-^=]{1,20}$/', $symbol)) {
                fail('סימול לא תקין', '?p=dashboard');
            }
            $symTrades = $repo->tradesBySymbol($uid, $symbol);
            $watch = array_values(array_filter($repo->watchlist($uid), fn($w) => strtoupper($w['symbol']) === $symbol));
            $market = in_array($_GET['market'] ?? '', ['US', 'IL'], true) ? $_GET['market']
                : ($symTrades[0]['market'] ?? ($watch[0]['market'] ?? 'US'));
            $quotes = prices()->quotes([['USDILS=X', 'FX'], [$symbol, $market]], $fresh);
            $fx = $quotes[Prices::key('USDILS=X', 'FX')]['price'] ?? 3.7;
            $quote = $quotes[Prices::key($symbol, $market)];
            $alerts = array_filter(
                $repo->alertRules($uid),
                fn($r) => in_array($symbol, array_map(fn($v) => strtoupper((string) $v), $r['config']), true)
            );

            $byPortfolio = [];
            $orders = [];
            foreach ($symTrades as $t) {
                $byPortfolio[$t['portfolio_id']]['name'] ??= $t['portfolio_name'];
                $byPortfolio[$t['portfolio_id']]['trades'][] = $t;
            }
            foreach ($repo->pendingOrders($uid) as $o) {
                if (strtoupper($o['symbol']) === $symbol) {
                    $orders[] = $o;
                }
            }
            foreach ($byPortfolio as &$r) {
                $pnl = Calc::symbolPnl($r['trades'], $symbol, $quote);
                $daily = Calc::symbolDaily($r['trades'], $quote, Calc::today());
                $pnl['daily'] = $daily[0] ?? null;
                if ($daily && $daily[1] !== null) {
                    $pnl['change_pct'] = $daily[1];
                }
                $pnl['unrealized_pct'] = $quote && $pnl['avg_cost'] > 0 ? ($quote['price'] - $pnl['avg_cost']) / $pnl['avg_cost'] * 100 : null;
                $r['pnl'] = $pnl;
            }
            unset($r);
            render('symbol', [
                'symbol' => $symbol, 'market' => $market, 'quote' => $quote, 'fx' => $fx,
                'byPortfolio' => $byPortfolio, 'watch' => $watch, 'alerts' => $alerts, 'orders' => $orders,
                'pricedAt' => priced_at($quotes),
            ], $symbol);

        case 'orders':
            render('orders', ['orders' => $repo->pendingOrders($uid), 'portfolios' => $repo->portfolios($uid)], 'הוראות');

        case 'trade':
            $trade = $repo->trade((int) ($_GET['id'] ?? 0), $uid);
            if (!$trade) {
                fail('העסקה לא נמצאה', '?p=dashboard');
            }
            render('trade_edit', ['t' => $trade, 'p' => owned_portfolio($trade['portfolio_id'])], 'עריכת עסקה');

        case 'watchlist':
            $items = $repo->watchlist($uid);
            $quotes = prices()->quotes(array_map(fn($i) => [$i['symbol'], $i['market']], $items), $fresh);
            render('watchlist', ['items' => $items, 'quotes' => $quotes, 'pricedAt' => priced_at($quotes)], 'מעקב');

        case 'alerts':
            render('alerts', ['rules' => $repo->alertRules($uid), 'portfolios' => $repo->portfolios($uid)], 'התראות');

        case 'settings':
            render('settings', ['u' => $repo->user($uid)], 'הגדרות');

        case 'dashboard':
        default:
            [$portfolios, $tradesBy] = $repo->portfoliosWithTrades($uid);
            [$data, $quotes] = $portfolios ? summaries($portfolios, $fresh, $tradesBy) : [[], []];
            render('dashboard', ['portfolios' => $portfolios, 'data' => $data, 'pricedAt' => priced_at($quotes)], 'תיקים');
    }
}
