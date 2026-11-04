<?php
declare(strict_types=1);

/** @return array{0: array<int, array>, 1: array<string, array|null>} [per-portfolio data, quotes] */
function summaries(array $portfolios, bool $fresh = false): array
{
    $repo = repo();
    $tradesBy = [];
    $pairs = [['USDILS=X', 'FX']];
    foreach ($portfolios as $p) {
        $tradesBy[$p['id']] = $repo->trades($p['id']);
        array_push($pairs, ...Calc::quotePairs($tradesBy[$p['id']]));
    }
    $quotes = prices()->quotes($pairs, $fresh);
    $fx = $quotes[Prices::key('USDILS=X', 'FX')]['price'] ?? 3.7;
    $out = [];
    foreach ($portfolios as $p) {
        $out[$p['id']] = ['trades' => $tradesBy[$p['id']], 'sum' => Calc::summary($p, $tradesBy[$p['id']], $quotes, $fx)];
    }
    return [$out, $quotes];
}

/** Timestamp of the oldest quote used, or null when there are none. */
function priced_at(array $quotes): ?int
{
    $ts = array_filter(array_map(fn($q) => $q['ts'] ?? null, $quotes));
    return $ts ? (int) min($ts) : null;
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

    switch ($page) {
        case 'portfolio':
            $p = owned_portfolio((int) ($_GET['id'] ?? 0));
            [$data, $quotes] = summaries([$p], $fresh);
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
            foreach ($symTrades as $t) {
                $byPortfolio[$t['portfolio_id']]['name'] ??= $t['portfolio_name'];
                $byPortfolio[$t['portfolio_id']]['trades'][] = $t;
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
                'byPortfolio' => $byPortfolio, 'watch' => $watch, 'alerts' => $alerts,
                'pricedAt' => priced_at($quotes),
            ], $symbol);

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
            $portfolios = $repo->portfolios($uid);
            [$data, $quotes] = $portfolios ? summaries($portfolios, $fresh) : [[], []];
            render('dashboard', ['portfolios' => $portfolios, 'data' => $data, 'pricedAt' => priced_at($quotes)], 'תיקים');
    }
}
