<?php
declare(strict_types=1);

/** Ports of src/portfolio/{commission,calculator,daily_pnl}.py and Repository.get_holdings/get_cash_balances. */
final class Calc
{
    private const EPS = 1e-9;

    public static function commission(array $p, float $qty, float $price, string $currency): float
    {
        $min = $currency === 'ILS' ? $p['commission_min_ils'] : $p['commission_min_usd'];
        $extra = $p['commission_extra_type'] === 'percent'
            ? $qty * $price * ($p['commission_extra_value'] / 100)
            : $p['commission_extra_value'];
        return max($min, $extra);
    }

    public static function toIls(float $amount, string $currency, float $fx): float
    {
        return $currency === 'ILS' ? $amount : $amount * $fx;
    }

    public static function localDate(array $trade): string
    {
        return $trade['ts']->setTimezone(new DateTimeZone(date_default_timezone_get()))->format('Y-m-d');
    }

    public static function today(): string
    {
        return (new DateTimeImmutable('now'))->format('Y-m-d');
    }

    /** @return list<array{symbol:string,market:string,asset_type:string,quantity:float,avg_cost:float,currency:string,trade_count:int}> */
    public static function holdings(array $trades): array
    {
        $b = [];
        foreach ($trades as $t) {
            if ($t['asset_type'] === 'cash') {
                continue;
            }
            $k = implode('|', [$t['symbol'], $t['market'], $t['asset_type'], $t['currency']]);
            $b[$k] ??= ['symbol' => $t['symbol'], 'market' => $t['market'], 'asset_type' => $t['asset_type'],
                'currency' => $t['currency'], 'qty' => 0.0, 'cost' => 0.0, 'n' => 0];
            $x = &$b[$k];
            $x['n']++;
            if ($t['action'] === 'buy') {
                $x['cost'] += $t['quantity'] * $t['price'] + $t['commission'];
                $x['qty'] += $t['quantity'];
            } elseif ($t['action'] === 'sell') {
                if ($x['qty'] <= 0) {
                    unset($x);
                    continue;
                }
                $avg = $x['cost'] / $x['qty'];
                $x['qty'] -= $t['quantity'];
                $x['cost'] -= $avg * $t['quantity'];
            }
            unset($x);
        }
        $out = [];
        foreach ($b as $x) {
            if ($x['qty'] <= self::EPS) {
                continue;
            }
            $out[] = ['symbol' => $x['symbol'], 'market' => $x['market'], 'asset_type' => $x['asset_type'],
                'quantity' => $x['qty'], 'avg_cost' => $x['cost'] / $x['qty'], 'currency' => $x['currency'], 'trade_count' => $x['n']];
        }
        return $out;
    }

    /** @return array{0:float,1:float} [ILS, USD] */
    public static function cashBalances(array $p, array $trades): array
    {
        $c = ['ILS' => $p['opening_cash_ils'], 'USD' => $p['opening_cash_usd']];
        foreach ($trades as $t) {
            $cur = $t['currency'] === 'ILS' ? 'ILS' : 'USD';
            if ($t['asset_type'] === 'cash') {
                $c[$cur] += match ($t['action']) { 'deposit' => $t['quantity'], 'withdraw' => -$t['quantity'], default => 0.0 };
                continue;
            }
            $gross = $t['quantity'] * $t['price'];
            $c[$cur] += match ($t['action']) {
                'buy' => -($gross + $t['commission']),
                'sell', 'dividend' => $gross - $t['commission'],
                default => 0.0,
            };
        }
        return [$c['ILS'], $c['USD']];
    }

    /** Quote keys needed to price a portfolio: open holdings + symbols traded today. */
    public static function quotePairs(array $trades): array
    {
        $today = self::today();
        $pairs = [];
        foreach (self::holdings($trades) as $h) {
            $pairs[] = [$h['symbol'], $h['market']];
        }
        foreach ($trades as $t) {
            if ($t['asset_type'] !== 'cash' && in_array($t['action'], ['buy', 'sell'], true) && self::localDate($t) === $today) {
                $pairs[] = [$t['symbol'], $t['market']];
            }
        }
        return $pairs;
    }

    public static function symbolPnl(array $trades, string $symbol, ?array $quote): array
    {
        $symbol = strtoupper($symbol);
        $qty = $cost = $realized = $commissions = 0.0;
        $currency = 'USD';
        $market = 'US';
        foreach ($trades as $t) {
            if (strtoupper($t['symbol']) !== $symbol || $t['asset_type'] === 'cash') {
                continue;
            }
            $currency = $t['currency'];
            $market = $t['market'];
            $commissions += $t['commission'];
            if ($t['action'] === 'buy') {
                $cost += $t['quantity'] * $t['price'] + $t['commission'];
                $qty += $t['quantity'];
            } elseif ($t['action'] === 'sell' && $qty > 0) {
                $avg = $cost / $qty;
                $realized += ($t['price'] - $avg) * $t['quantity'] - $t['commission'];
                $cost -= $avg * $t['quantity'];
                $qty -= $t['quantity'];
            } elseif ($t['action'] === 'dividend') {
                $realized += $t['quantity'] * $t['price'] - $t['commission'];
            }
        }
        $avg = $qty > 0 ? $cost / $qty : 0.0;
        $price = $quote['price'] ?? null;
        return [
            'symbol' => $symbol, 'market' => $market, 'currency' => $currency, 'quantity' => $qty, 'avg_cost' => $avg,
            'price' => $price, 'realized' => $realized, 'commissions' => $commissions,
            'unrealized' => $price !== null && $qty > 0 ? ($price - $avg) * $qty : 0.0,
            'change_pct' => $quote['change_pct'] ?? null,
        ];
    }

    /** @return array{0:float,1:float} [qty, cost] from buys/sells dated before $before (port of _position_at_date) */
    private static function positionBefore(array $trades, string $before): array
    {
        $qty = $cost = 0.0;
        foreach ($trades as $t) {
            if (!in_array($t['action'], ['buy', 'sell'], true) || self::localDate($t) >= $before) {
                continue;
            }
            if ($t['action'] === 'buy') {
                $qty += $t['quantity'];
                $cost += $t['quantity'] * $t['price'];
            } elseif ($qty > 0) {
                $cost -= $cost / $qty * $t['quantity'];
                $qty -= $t['quantity'];
            }
        }
        return [$qty, $cost];
    }

    /**
     * Port of calc_symbol_daily_pnl + calc_symbol_daily_pnl_pct: position-aware, so same-day buys use
     * their own cost and same-day sells use the previous close.
     * @param array $trades one symbol's trades, oldest first
     * @return array{0:float,1:?float}|null [amount, pct]
     */
    public static function symbolDaily(array $trades, ?array $quote, string $today): ?array
    {
        $prev = $quote['prev_close'] ?? null;
        if ($prev === null) {
            return null;
        }
        $price = $quote['price'];
        $stock = array_values(array_filter($trades, fn($t) => in_array($t['action'], ['buy', 'sell'], true) && self::localDate($t) <= $today));
        if (!$stock) {
            return null;
        }
        $todayTrades = array_values(array_filter($stock, fn($t) => self::localDate($t) === $today));
        [$qtyOpen, $costOpen] = self::positionBefore($stock, $today);
        if (!$todayTrades && $qtyOpen <= self::EPS) {
            return null;
        }

        $qtyTotal = $qtyOpen;
        $costTotal = $costOpen;
        $boughtQty = $boughtCost = $daily = 0.0;
        foreach ($todayTrades as $t) {
            if ($t['action'] === 'buy') {
                $qtyTotal += $t['quantity'];
                $costTotal += $t['quantity'] * $t['price'];
                $boughtQty += $t['quantity'];
                $boughtCost += $t['quantity'] * $t['price'];
            } elseif ($qtyTotal > 0) {
                $sell = min($t['quantity'], $qtyTotal);
                $fromOvernight = min($sell, max($qtyTotal - $boughtQty, 0.0));
                $fromToday = $sell - $fromOvernight;
                $daily += $fromOvernight * ($t['price'] - $prev);
                $avgToday = $boughtQty > 0 ? $boughtCost / $boughtQty : 0.0;
                if ($fromToday > 0 && $boughtQty > 0) {
                    $daily += $fromToday * ($t['price'] - $avgToday);
                }
                $costTotal -= $costTotal / $qtyTotal * $sell;
                $qtyTotal -= $sell;
                if ($fromToday > 0 && $boughtQty > 0) {
                    $boughtCost -= $avgToday * $fromToday;
                    $boughtQty -= $fromToday;
                }
            }
        }
        $overnightEnd = max($qtyTotal - $boughtQty, 0.0);
        $daily += $overnightEnd * ($price - $prev);
        if ($boughtQty > 0) {
            $daily += $boughtQty * ($price - $boughtCost / $boughtQty);
        }

        $basis = $qtyOpen * $prev;
        foreach ($todayTrades as $t) {
            if ($t['action'] === 'buy') {
                $basis += $t['quantity'] * $t['price'];
            }
        }
        return [$daily, $basis > 0 ? $daily / $basis * 100 : null];
    }

    /**
     * @param array<string, array|null> $quotes keyed by Prices::key()
     */
    public static function summary(array $p, array $trades, array $quotes, float $fx): array
    {
        $holdings = self::holdings($trades);
        [$cashIls, $cashUsd] = self::cashBalances($p, $trades);

        $symbols = [];
        foreach ($trades as $t) {
            if ($t['asset_type'] !== 'cash') {
                $symbols[strtoupper($t['symbol'])] = true;
            }
        }
        $symbols = array_map('strval', array_keys($symbols));
        sort($symbols, SORT_STRING);

        $investments = 0.0;
        $pnls = [];
        foreach ($symbols as $sym) {
            $row = self::symbolPnl($trades, $sym, null);
            if ($row['quantity'] > self::EPS && ($q = $quotes[Prices::key($sym, $row['market'])] ?? null)) {
                $row = self::symbolPnl($trades, $sym, $q);
            }
            $pnls[$sym] = $row;
            $investments += self::toIls($row['realized'] + $row['unrealized'], $row['currency'], $fx);
        }

        $rows = [];
        $securities = 0.0;
        usort($holdings, fn($a, $b) => strcmp($a['symbol'], $b['symbol']));
        foreach ($holdings as $h) {
            $sym = strtoupper($h['symbol']);
            $q = $quotes[Prices::key($h['symbol'], $h['market'])] ?? null;
            if ($q) {
                $securities += self::toIls($h['quantity'] * $q['price'], $h['currency'], $fx);
            }
            if (isset($rows[$sym])) {
                continue;
            }
            $pnl = self::symbolPnl($trades, $sym, $q);
            if ($pnl['quantity'] <= self::EPS) {
                $pnl['quantity'] = $h['quantity'];
                $pnl['avg_cost'] = $h['avg_cost'];
                $pnl['currency'] = $h['currency'];
                $pnl['unrealized'] = $q ? ($q['price'] - $h['avg_cost']) * $h['quantity'] : 0.0;
            }
            $symTrades = array_values(array_filter($trades, fn($t) => $t['asset_type'] !== 'cash' && strtoupper($t['symbol']) === $sym));
            $daily = self::symbolDaily($symTrades, $q, self::today());
            $pnl['daily'] = $daily[0] ?? null;
            if ($daily && $daily[1] !== null) {
                $pnl['change_pct'] = $daily[1];
            }
            $pnl['market'] = $h['market'];
            $pnl['session'] = $q['session'] ?? null;
            $pnl['value'] = $q ? $pnl['quantity'] * $q['price'] : null;
            $pnl['unrealized_pct'] = $q && $pnl['avg_cost'] > 0 ? ($q['price'] - $pnl['avg_cost']) / $pnl['avg_cost'] * 100 : null;
            $rows[$sym] = $pnl;
        }

        $netDeposits = 0.0;
        foreach ($trades as $t) {
            if ($t['asset_type'] === 'cash') {
                $amt = self::toIls($t['quantity'], $t['currency'], $fx);
                $netDeposits += $t['action'] === 'deposit' ? $amt : ($t['action'] === 'withdraw' ? -$amt : 0.0);
            }
        }
        $total = $cashIls + $cashUsd * $fx + $securities;
        $opening = $p['opening_cash_ils'] + $p['opening_cash_usd'] * $fx + $netDeposits;
        $totalPnl = $total - $opening;

        return [
            'fx' => $fx,
            'cash_ils' => $cashIls,
            'cash_usd' => $cashUsd,
            'securities_ils' => $securities,
            'securities_usd' => $fx ? $securities / $fx : 0.0,
            'total_ils' => $total,
            'total_usd' => $fx ? $total / $fx : 0.0,
            'opening_capital_ils' => $opening,
            'investments_pnl_ils' => $investments,
            'total_pnl_ils' => $totalPnl,
            'total_pnl_pct' => $opening > 0 ? $totalPnl / $opening * 100 : 0.0,
            'daily_change_ils' => self::dailyChange($p, $trades, $holdings, $quotes, $fx, $cashIls, $cashUsd),
            'holdings' => array_values($rows),
            'closed' => array_values(array_filter($pnls, fn($r) => !isset($rows[$r['symbol']]) && abs($r['realized']) > self::EPS)),
        ];
    }

    private static function dailyChange(array $p, array $trades, array $holdings, array $quotes, float $fx, float $cashIls, float $cashUsd): float
    {
        $today = self::today();
        $ils = $p['opening_cash_ils'];
        $usd = $p['opening_cash_usd'];
        $pos = [];
        $flow = 0.0;
        foreach ($trades as $t) {
            $date = self::localDate($t);
            if ($date === $today && $t['asset_type'] === 'cash') {
                $amt = self::toIls($t['quantity'], $t['currency'], $fx);
                $flow += $t['action'] === 'deposit' ? $amt : ($t['action'] === 'withdraw' ? -$amt : 0.0);
            }
            if ($date >= $today) {
                continue;
            }
            $cur = $t['currency'] === 'ILS' ? 'ILS' : 'USD';
            $gross = $t['quantity'] * $t['price'];
            $delta = 0.0;
            if ($t['asset_type'] === 'cash') {
                $delta = $t['action'] === 'deposit' ? $t['quantity'] : ($t['action'] === 'withdraw' ? -$t['quantity'] : 0.0);
            } else {
                $key = implode('|', [strtoupper($t['symbol']), $t['market'], $t['currency']]);
                if ($t['action'] === 'buy') {
                    $delta = -($gross + $t['commission']);
                    $pos[$key] = ($pos[$key] ?? 0.0) + $t['quantity'];
                } elseif ($t['action'] === 'sell') {
                    $delta = $gross - $t['commission'];
                    $pos[$key] = max(($pos[$key] ?? 0.0) - $t['quantity'], 0.0);
                } elseif ($t['action'] === 'dividend') {
                    $delta = $gross - $t['commission'];
                }
            }
            $cur === 'ILS' ? $ils += $delta : $usd += $delta;
        }

        $start = $ils + $usd * $fx;
        foreach ($pos as $key => $qty) {
            if ($qty <= self::EPS) {
                continue;
            }
            [$sym, $market, $cur] = explode('|', $key);
            $prev = $quotes[Prices::key($sym, $market)]['prev_close'] ?? null;
            if ($prev !== null) {
                $start += self::toIls($qty * $prev, $cur, $fx);
            }
        }

        $end = $cashIls + $cashUsd * $fx;
        foreach ($holdings as $h) {
            $q = $quotes[Prices::key($h['symbol'], $h['market'])] ?? null;
            if ($q) {
                $end += self::toIls($h['quantity'] * $q['price'], $h['currency'], $fx);
            }
        }
        return $end - $start - $flow;
    }
}
