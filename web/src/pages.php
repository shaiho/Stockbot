<?php
declare(strict_types=1);

function summaries(array $portfolios): array
{
    $repo = repo();
    $tradesBy = [];
    $pairs = [['USDILS=X', 'FX']];
    foreach ($portfolios as $p) {
        $tradesBy[$p['id']] = $repo->trades($p['id']);
        array_push($pairs, ...Calc::quotePairs($tradesBy[$p['id']]));
    }
    $quotes = prices()->quotes($pairs);
    $fx = $quotes[Prices::key('USDILS=X', 'FX')]['price'] ?? 3.7;
    $out = [];
    foreach ($portfolios as $p) {
        $out[$p['id']] = ['trades' => $tradesBy[$p['id']], 'sum' => Calc::summary($p, $tradesBy[$p['id']], $quotes, $fx)];
    }
    return $out;
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

    switch ($page) {
        case 'portfolio':
            $p = owned_portfolio((int) ($_GET['id'] ?? 0));
            $all = summaries([$p])[$p['id']];
            render('portfolio', ['p' => $p, 'trades' => array_reverse($all['trades']), 'sum' => $all['sum']], $p['name']);

        case 'trade':
            $trade = $repo->trade((int) ($_GET['id'] ?? 0), $uid);
            if (!$trade) {
                fail('העסקה לא נמצאה', '?p=dashboard');
            }
            render('trade_edit', ['t' => $trade, 'p' => owned_portfolio($trade['portfolio_id'])], 'עריכת עסקה');

        case 'watchlist':
            $items = $repo->watchlist($uid);
            $quotes = prices()->quotes(array_map(fn($i) => [$i['symbol'], $i['market']], $items));
            render('watchlist', ['items' => $items, 'quotes' => $quotes], 'מעקב');

        case 'alerts':
            render('alerts', ['rules' => $repo->alertRules($uid), 'portfolios' => $repo->portfolios($uid)], 'התראות');

        case 'settings':
            render('settings', ['u' => $repo->user($uid)], 'הגדרות');

        case 'dashboard':
        default:
            $portfolios = $repo->portfolios($uid);
            render('dashboard', ['portfolios' => $portfolios, 'data' => $portfolios ? summaries($portfolios) : []], 'תיקים');
    }
}
