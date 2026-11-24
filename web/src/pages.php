<?php
declare(strict_types=1);

/** @return array{0: array<int, array>, 1: array<string, array|null>} [per-portfolio data, quotes] */
function summaries(array $portfolios, bool $fresh = false, ?array $tradesBy = null): array
{
    $tradesBy ??= repo()->tradesForPortfolios(array_column($portfolios, 'id'));
    $pairs = [['USDILS=X', 'FX']];
    foreach ($portfolios as $p) {
        array_push($pairs, ...Calc::quotePairs($tradesBy[$p['id']] ?? []));
    }
    $quotes = prices()->quotes($pairs, $fresh);
    $fx = $quotes[Prices::key('USDILS=X', 'FX')]['price'] ?? 3.7;
    $manual = (float) ($_SESSION['fx_manual'] ?? 0);
    if ($manual > 0) {
        $fx = $manual;
        $quotes[Prices::key('USDILS=X', 'FX')] = ['price' => $manual, 'prev_close' => null, 'change_pct' => 0.0, 'ts' => time(), 'manual' => true];
    }
    $out = [];
    $t0 = microtime(true);
    foreach ($portfolios as $p) {
        $out[$p['id']] = ['trades' => $tradesBy[$p['id']] ?? [], 'sum' => Calc::summary($p, $tradesBy[$p['id']] ?? [], $quotes, $fx)];
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
    if ($page === 'order_count') {
        header('Content-Type: application/json');
        echo json_encode(['n' => count($repo->openOrders($uid))]);
        exit;
    }
    if ($page === 'mkt_status') {
        header('Content-Type: application/json');
        $us = prices()->quotes([['SPY', 'US']])[Prices::key('SPY', 'US')]['session'] ?? 'closed';
        $now = new DateTimeImmutable('now', new DateTimeZone('Asia/Jerusalem'));
        $dow = (int) $now->format('N'); $hm = (int) $now->format('Hi');
        $il = ($dow <= 4 && $hm >= 1000 && $hm < 1730) ? 'regular' : 'closed';
        echo json_encode(['us' => $us, 'il' => $il]);
        exit;
    }
    $fresh = ($_GET['refresh'] ?? '') === '1';
    process_orders($uid);

    if ($page === 'export') {
        $p = owned_portfolio((int) ($_GET['id'] ?? 0));
        $trades = $repo->trades($p['id']);
        $fname = 'trades_' . preg_replace('/[^\p{L}\p{N}_-]+/u', '_', $p['name']) . '_' . date('Y-m-d') . '.csv';
        header('Content-Type: text/csv; charset=utf-8');
        header('Content-Disposition: attachment; filename="' . $fname . '"');
        $out = fopen('php://output', 'w');
        fwrite($out, "\xEF\xBB\xBF");
        fputcsv($out, ['id', 'date', 'action', 'symbol', 'market', 'asset_type', 'quantity', 'price', 'currency', 'commission', 'note']);
        foreach ($trades as $t) {
            fputcsv($out, [$t['id'], local_dt($t['ts'], 'Y-m-d H:i'), $t['action'], $t['symbol'], $t['market'], $t['asset_type'], $t['quantity'], $t['price'], $t['currency'], $t['commission'], $t['note']]);
        }
        fclose($out);
        exit;
    }

    if ($page === 'chart') {
        $symbol = strtoupper(trim((string) ($_GET['symbol'] ?? '')));
        $market = in_array($_GET['market'] ?? '', ['US', 'IL'], true) ? $_GET['market'] : 'US';
        $range = in_array($_GET['range'] ?? '', ['1d', '5d', '1mo'], true) ? $_GET['range'] : '1mo';
        header('Content-Type: application/json');
        $ok = preg_match('/^[A-Z0-9.\-^=]{1,20}$/', $symbol);
        echo json_encode($ok ? (($_GET['ohlc'] ?? '') === '1' ? prices()->chartOhlc($symbol, $market, $range) : prices()->chart($symbol, $market, $range)) : []);
        exit;
    }

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
            render('portfolio', ['p' => $p, 'trades' => array_reverse($all['trades']), 'sum' => $all['sum'], 'snapshots' => $repo->snapshots($p['id']), 'flows' => Calc::flowMap($all['trades'], $all['sum']['fx']), 'pricedAt' => priced_at($quotes)], $p['name']);

        case 'symbol':
            $symbol = strtoupper(trim((string) ($_GET['symbol'] ?? '')));
            if (!preg_match('/^[A-Z0-9.\-^=]{1,20}$/', $symbol)) {
                fail('סימול לא תקין', '?p=dashboard');
            }
            [$symTrades, $watchRows, $rules, $orders] = $repo->symbolData($uid, $symbol);
            $watch = array_values(array_filter($watchRows, fn($w) => strtoupper($w['symbol']) === $symbol));
            $market = in_array($_GET['market'] ?? '', ['US', 'IL'], true) ? $_GET['market']
                : ($symTrades[0]['market'] ?? ($watch[0]['market'] ?? 'US'));
            $quotes = prices()->quotes([['USDILS=X', 'FX'], [$symbol, $market]], $fresh);
            $fx = $quotes[Prices::key('USDILS=X', 'FX')]['price'] ?? 3.7;
            $quote = $quotes[Prices::key($symbol, $market)];
            $alerts = array_filter(
                $rules,
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
                // Dividend stats: total received, per-share average using qty actually held on each date.
                $qty = 0.0; $divTotal = 0.0; $divCount = 0; $divLast = null;
                foreach ($r['trades'] as $t) {
                    if ($t['action'] === 'buy') { $qty += $t['quantity']; }
                    elseif ($t['action'] === 'sell') { $qty -= $t['quantity']; }
                    elseif ($t['action'] === 'dividend') {
                        $amt = $t['quantity'] * $t['price'];
                        $divTotal += $amt;
                        $divCount++;
                        $divLast = ['date' => Calc::localDate($t), 'amount' => $amt, 'qty' => max($qty, 0.0)];
                    }
                }
                $cost = $pnl['quantity'] * $pnl['avg_cost'];
                $pnl['div_total'] = $divTotal;
                $pnl['div_count'] = $divCount;
                $pnl['div_last'] = $divLast;
                $pnl['div_yield_cost'] = $cost > 0 && $divTotal > 0 ? $divTotal / $cost * 100 : null;
                $r['pnl'] = $pnl;
            }
            unset($r);
            render('symbol', [
                'symbol' => $symbol, 'market' => $market, 'quote' => $quote, 'fx' => $fx,
                'byPortfolio' => $byPortfolio, 'watch' => $watch, 'alerts' => $alerts, 'orders' => $orders,
                'portfolios' => $repo->portfolios($uid),
                'events' => prices()->events($symbol, $market),
                'pricedAt' => priced_at($quotes),
            ], $symbol);

        case 'tax':
            $p = owned_portfolio((int) ($_GET['id'] ?? 0));
            $trades = $repo->trades($p['id']);
            $years = array_values(array_unique(array_map(fn($t) => (int) substr(Calc::localDate($t), 0, 4), $trades)));
            rsort($years);
            $year = in_array((int) ($_GET['year'] ?? 0), $years, true) ? (int) $_GET['year'] : ($years[0] ?? (int) date('Y'));
            $fx = prices()->usdIls();
            render('tax', ['p' => $p, 'report' => Calc::taxReport($trades, $year, $fx), 'years' => $years], 'דוח מס');
            break;

        case 'orders':
            $orders = $repo->pendingOrders($uid);
            $open = array_values(array_filter($orders, fn($o) => $o['status'] === 'open'));
            $quotes = $open ? prices()->quotes(array_map(fn($o) => [$o['symbol'], $o['market']], $open), $fresh) : [];
            render('orders', ['orders' => $orders, 'quotes' => $quotes, 'portfolios' => $repo->portfolios($uid)], 'הוראות');

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
            $rules = $repo->alertRules($uid);
            $targets = [];
            foreach ($rules as $r) {
                if ($r['enabled'] && $r['alert_type'] === 'price_target' && !empty($r['config']['symbol'])) {
                    $targets[] = [$r['config']['symbol'], $r['config']['market'] ?? 'US'];
                }
            }
            $quotes = $targets ? prices()->quotes($targets, $fresh) : [];
            render('alerts', ['rules' => $rules, 'quotes' => $quotes, 'portfolios' => $repo->portfolios($uid)], 'התראות');

        case 'settings':
            render('settings', ['u' => $repo->user($uid)], 'הגדרות');

        case 'dashboard':
        default:
            [$portfolios, $tradesBy] = $repo->portfoliosWithTrades($uid);
            [$data, $quotes] = $portfolios ? summaries($portfolios, $fresh, $tradesBy) : [[], []];
            $bench = $portfolios ? prices()->quotes([['SPY', 'US'], ['TA35', 'IL']], $fresh) : [];
            $syms = [];
            foreach ($data as $d) {
                foreach ($d['sum']['holdings'] as $r) {
                    $syms[Prices::key($r['symbol'], $r['market'])] = [$r['symbol'], $r['market']];
                }
            }
            $upcoming = [];
            foreach (prices()->eventsFor(array_values($syms)) as $k => $ev) {
                foreach ($ev['dividends'] as $e) {
                    if ($e['date'] >= Calc::today()) {
                        $upcoming[] = ['symbol' => explode(':', $k, 2)[0], 'date' => $e['date'], 'amount' => $e['amount']];
                    }
                }
                foreach ($ev['splits'] as $e) {
                    if ($e['date'] >= Calc::today()) {
                        $upcoming[] = ['symbol' => explode(':', $k, 2)[0] . ' פיצול', 'date' => $e['date'], 'amount' => null, 'ratio' => $e['ratio']];
                    }
                }
            }
            usort($upcoming, fn($a, $b) => strcmp($a['date'], $b['date']));
            $allTrades = array_merge(...array_map('array_values', $tradesBy ?: [[]]));
            render('dashboard', [
                'portfolios' => $portfolios, 'data' => $data,
                'snapshots' => $repo->snapshotsSum(array_column($portfolios, 'id')),
                'flows' => Calc::flowMap($allTrades, prices()->usdIls()),
                'bench' => $bench, 'upcoming' => array_slice($upcoming, 0, 12),
                'pricedAt' => priced_at($quotes),
            ], 'תיקים');
    }
}
