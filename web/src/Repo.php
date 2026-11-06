<?php
declare(strict_types=1);

/** Mirrors src/db/repository.py (Postgres branch). Every query is scoped by the owning user. */
final class Repo
{
    private const TRADE_EDITABLE = ['quantity', 'price', 'commission', 'timestamp', 'note'];

    public function __construct(private PDO $db)
    {
    }

    private function run(string $sql, array $args = []): PDOStatement
    {
        $t0 = microtime(true);
        $st = $this->db->prepare($sql);
        foreach (array_values($args) as $i => $v) {
            $st->bindValue($i + 1, $v, is_bool($v) ? PDO::PARAM_BOOL : (is_int($v) ? PDO::PARAM_INT : (is_null($v) ? PDO::PARAM_NULL : PDO::PARAM_STR)));
        }
        $st->execute();
        prof_add('db', (microtime(true) - $t0) * 1000);
        return $st;
    }

    public static function isUniqueViolation(PDOException $e): bool
    {
        return $e->getCode() === '23505';
    }

    public function user(int $id): array
    {
        $row = $this->run('SELECT * FROM users WHERE telegram_id = ?', [$id])->fetch();
        if (!$row) {
            $row = $this->run('INSERT INTO users (telegram_id) VALUES (?) RETURNING *', [$id])->fetch();
        }
        return $this->hydrateUser($row);
    }

    public function updateUser(int $id, array $u): void
    {
        $this->run(
            'UPDATE users SET language = ?, default_commission = ?, default_commission_currency = ?,
                report_morning = ?, report_evening = ?, mover_threshold_pct = ?, last_portfolio_id = ?
             WHERE telegram_id = ?',
            [$u['language'], $u['default_commission'], $u['default_commission_currency'],
             $u['report_morning'], $u['report_evening'], $u['mover_threshold_pct'], $u['last_portfolio_id'], $id]
        );
    }

    public function portfolios(int $userId): array
    {
        $rows = $this->run('SELECT * FROM portfolios WHERE user_id = ? ORDER BY id', [$userId])->fetchAll();
        return array_map([$this, 'hydratePortfolio'], $rows);
    }

    public function portfolio(int $id, int $userId): ?array
    {
        $row = $this->run('SELECT * FROM portfolios WHERE id = ? AND user_id = ?', [$id, $userId])->fetch();
        return $row ? $this->hydratePortfolio($row) : null;
    }

    /** One round trip: [list<portfolio>, map<portfolio_id, list<trade>>] for a user. */
    public function portfoliosWithTrades(int $userId): array
    {
        $row = $this->run(
            "SELECT (SELECT coalesce(json_agg(p ORDER BY id), '[]') FROM portfolios p WHERE p.user_id = ?) AS portfolios,
                    (SELECT coalesce(json_agg(t ORDER BY t.portfolio_id, t.timestamp, t.id), '[]') FROM trades t
                     JOIN portfolios p2 ON p2.id = t.portfolio_id WHERE p2.user_id = ?) AS trades",
            [$userId, $userId]
        )->fetch();
        $portfolios = array_map([$this, 'hydratePortfolio'], json_decode((string) $row['portfolios'], true) ?: []);
        $tradesBy = [];
        foreach (json_decode((string) $row['trades'], true) ?: [] as $t) {
            $tradesBy[(int) $t['portfolio_id']][] = $this->hydrateTrade($t);
        }
        return [$portfolios, $tradesBy];
    }

    /** @throws DomainException 'max_portfolios' | 'duplicate_name' */
    public function createPortfolio(int $userId, string $name, float $ils, float $usd): array
    {
        $count = (int) $this->run('SELECT COUNT(*) FROM portfolios WHERE user_id = ?', [$userId])->fetchColumn();
        if ($count >= MAX_PORTFOLIOS) {
            throw new DomainException('max_portfolios');
        }
        try {
            $row = $this->run(
                'INSERT INTO portfolios (user_id, name, opening_cash_ils, opening_cash_usd) VALUES (?, ?, ?, ?) RETURNING *',
                [$userId, trim($name), $ils, $usd]
            )->fetch();
        } catch (PDOException $e) {
            throw self::isUniqueViolation($e) ? new DomainException('duplicate_name') : $e;
        }
        return $this->hydratePortfolio($row);
    }

    public function renamePortfolio(int $id, int $userId, string $name): void
    {
        try {
            $this->run('UPDATE portfolios SET name = ? WHERE id = ? AND user_id = ?', [trim($name), $id, $userId]);
        } catch (PDOException $e) {
            throw self::isUniqueViolation($e) ? new DomainException('duplicate_name') : $e;
        }
    }

    public function updateOpeningCash(int $id, int $userId, float $ils, float $usd): void
    {
        $this->run(
            'UPDATE portfolios SET opening_cash_ils = ?, opening_cash_usd = ? WHERE id = ? AND user_id = ?',
            [$ils, $usd, $id, $userId]
        );
    }

    public function updateCommission(int $id, int $userId, float $minUsd, float $minIls, string $type, float $value): void
    {
        $this->run(
            'UPDATE portfolios SET commission_min_usd = ?, commission_min_ils = ?,
                commission_extra_type = ?, commission_extra_value = ? WHERE id = ? AND user_id = ?',
            [$minUsd, $minIls, $type, $value, $id, $userId]
        );
    }

    public function deletePortfolio(int $id, int $userId): bool
    {
        return $this->run('DELETE FROM portfolios WHERE id = ? AND user_id = ?', [$id, $userId])->rowCount() > 0;
    }

    public function deletePortfolioTrades(int $id, int $userId): int
    {
        return $this->run(
            'DELETE FROM trades WHERE portfolio_id = ? AND portfolio_id IN (SELECT id FROM portfolios WHERE user_id = ?)',
            [$id, $userId]
        )->rowCount();
    }

    /** Trades for several portfolios in one query, grouped by portfolio id. */
    public function tradesForPortfolios(array $ids): array
    {
        $byId = array_fill_keys($ids, []);
        if (!$byId) {
            return $byId;
        }
        $marks = implode(',', array_fill(0, count($ids), '?'));
        $rows = $this->run("SELECT * FROM trades WHERE portfolio_id IN ($marks) ORDER BY timestamp, id", array_values($ids))->fetchAll();
        $t0 = microtime(true);
        foreach ($rows as $r) {
            $byId[(int) $r['portfolio_id']][] = $this->hydrateTrade($r);
        }
        prof_add('hydrate', (microtime(true) - $t0) * 1000, count($rows));
        return $byId;
    }

    public function trades(int $portfolioId): array
    {
        $rows = $this->run('SELECT * FROM trades WHERE portfolio_id = ? ORDER BY timestamp, id', [$portfolioId])->fetchAll();
        $t0 = microtime(true);
        $out = array_map([$this, 'hydrateTrade'], $rows);
        prof_add('hydrate', (microtime(true) - $t0) * 1000, count($rows));
        return $out;
    }

    /** Stock trades for one symbol across all of the user's portfolios; each row gains portfolio_name. */
    public function tradesBySymbol(int $userId, string $symbol): array
    {
        $rows = $this->run(
            'SELECT t.*, p.name AS portfolio_name FROM trades t JOIN portfolios p ON p.id = t.portfolio_id
             WHERE p.user_id = ? AND t.asset_type <> ? AND UPPER(t.symbol) = ? ORDER BY t.timestamp, t.id',
            [$userId, 'cash', strtoupper($symbol)]
        )->fetchAll();
        return array_map(function (array $r): array {
            $t = $this->hydrateTrade($r);
            $t['portfolio_name'] = $r['portfolio_name'];
            return $t;
        }, $rows);
    }

    /** One round trip for the symbol page: [trades(with portfolio_name), watchlist rows, alert rules, pending orders]. */
    public function symbolData(int $userId, string $symbol): array
    {
        $row = $this->run(
            "SELECT (SELECT coalesce(json_agg(t ORDER BY t.timestamp, t.id), '[]') FROM
                     (SELECT t.*, p.name AS portfolio_name FROM trades t JOIN portfolios p ON p.id = t.portfolio_id
                      WHERE p.user_id = ? AND t.asset_type <> 'cash' AND UPPER(t.symbol) = ?) t) AS trades,
                    (SELECT coalesce(json_agg(w), '[]') FROM watchlist w WHERE w.user_id = ? AND UPPER(w.symbol) = ?) AS watch,
                    (SELECT coalesce(json_agg(r ORDER BY r.id), '[]') FROM alert_rules r WHERE r.user_id = ?) AS rules,
                    (SELECT coalesce(json_agg(o ORDER BY o.status = 'open' DESC, o.id DESC), '[]')
                     FROM pending_orders o WHERE o.user_id = ? AND UPPER(o.symbol) = ?) AS orders",
            [$userId, strtoupper($symbol), $userId, strtoupper($symbol), $userId, $userId, strtoupper($symbol)]
        )->fetch();
        $trades = array_map(function (array $r): array {
            $t = $this->hydrateTrade($r);
            $t['portfolio_name'] = $r['portfolio_name'];
            return $t;
        }, json_decode((string) $row['trades'], true) ?: []);
        $rules = array_map(function (array $r): array {
            $r['config'] = json_decode((string) $r['config'], true) ?: [];
            $r['enabled'] = (bool) $r['enabled'];
            return $r;
        }, json_decode((string) $row['rules'], true) ?: []);
        return [
            $trades,
            json_decode((string) $row['watch'], true) ?: [],
            $rules,
            array_map([$this, 'hydrateOrder'], json_decode((string) $row['orders'], true) ?: []),
        ];
    }

    public function trade(int $id, int $userId): ?array
    {
        $row = $this->run(
            'SELECT t.* FROM trades t JOIN portfolios p ON p.id = t.portfolio_id WHERE t.id = ? AND p.user_id = ?',
            [$id, $userId]
        )->fetch();
        return $row ? $this->hydrateTrade($row) : null;
    }

    public function addTrade(
        int $portfolioId,
        string $symbol,
        string $market,
        string $assetType,
        string $action,
        float $quantity,
        float $price,
        string $currency,
        float $commission,
        ?string $note,
        ?DateTimeInterface $ts = null
    ): int {
        return (int) $this->run(
            'INSERT INTO trades (portfolio_id, symbol, market, asset_type, action, quantity, price, currency, commission, note, timestamp)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?::timestamptz, NOW())) RETURNING id',
            [$portfolioId, strtoupper($symbol), $market, $assetType, $action, $quantity, $price, $currency, $commission, $note,
             $ts ? $ts->format('Y-m-d H:i:sP') : null]
        )->fetchColumn();
    }

    public function addCash(int $portfolioId, string $action, string $currency, float $amount, ?string $note, ?DateTimeInterface $ts): int
    {
        return $this->addTrade($portfolioId, 'CASH', 'CASH', 'cash', $action, $amount, 1.0, $currency, 0.0, $note ?: $action, $ts);
    }

    /** @param array<string, mixed> $fields subset of TRADE_EDITABLE; 'timestamp' as DateTimeInterface */
    public function updateTrade(int $id, int $userId, array $fields): bool
    {
        if (!$this->trade($id, $userId)) {
            return false;
        }
        $fields = array_intersect_key($fields, array_flip(self::TRADE_EDITABLE));
        if (!$fields) {
            return true;
        }
        $sets = [];
        $args = [];
        foreach ($fields as $col => $v) {
            $sets[] = $col === 'timestamp' ? 'timestamp = ?::timestamptz' : "$col = ?";
            $args[] = $v instanceof DateTimeInterface ? $v->format('Y-m-d H:i:sP') : $v;
        }
        $args[] = $id;
        return $this->run('UPDATE trades SET ' . implode(', ', $sets) . ' WHERE id = ?', $args)->rowCount() > 0;
    }

    public function deleteTrade(int $id, int $userId): bool
    {
        return $this->run(
            'DELETE FROM trades WHERE id = ? AND portfolio_id IN (SELECT id FROM portfolios WHERE user_id = ?)',
            [$id, $userId]
        )->rowCount() > 0;
    }

    public function recalculateCommissions(array $portfolio, int $userId): int
    {
        $updated = 0;
        foreach ($this->trades($portfolio['id']) as $t) {
            if ($t['asset_type'] !== 'stock' || !in_array($t['action'], ['buy', 'sell'], true)) {
                continue;
            }
            $new = Calc::commission($portfolio, $t['quantity'], $t['price'], $t['currency']);
            if (abs($new - $t['commission']) > 1e-9 && $this->updateTrade($t['id'], $userId, ['commission' => $new])) {
                $updated++;
            }
        }
        return $updated;
    }

    /** Daily value snapshots for a portfolio: list of ['date'=>Y-m-d,'total_ils'=>float]. */
    public function snapshots(int $portfolioId): array
    {
        try {
            return $this->run('SELECT date, total_ils FROM portfolio_snapshots WHERE portfolio_id = ? ORDER BY date', [$portfolioId])->fetchAll();
        } catch (PDOException) {
            return [];
        }
    }

    /** Daily total value summed across portfolios: list of ['date'=>Y-m-d,'total_ils'=>float]. */
    public function snapshotsSum(array $portfolioIds): array
    {
        if (!$portfolioIds) {
            return [];
        }
        try {
            $marks = implode(',', array_fill(0, count($portfolioIds), '?'));
            return $this->run("SELECT date, SUM(total_ils) AS total_ils FROM portfolio_snapshots WHERE portfolio_id IN ($marks) GROUP BY date ORDER BY date", array_values($portfolioIds))->fetchAll();
        } catch (PDOException) {
            return [];
        }
    }

    public function watchlist(int $userId): array
    {
        return $this->run('SELECT * FROM watchlist WHERE user_id = ? ORDER BY symbol', [$userId])->fetchAll();
    }

    /** @throws DomainException 'duplicate' */
    public function addWatchlist(int $userId, string $symbol, string $market): void
    {
        try {
            $this->run('INSERT INTO watchlist (user_id, symbol, market) VALUES (?, ?, ?)', [$userId, strtoupper($symbol), $market]);
        } catch (PDOException $e) {
            throw self::isUniqueViolation($e) ? new DomainException('duplicate') : $e;
        }
    }

    public function removeWatchlist(int $id, int $userId): void
    {
        $this->run('DELETE FROM watchlist WHERE id = ? AND user_id = ?', [$id, $userId]);
    }

    public function alertRules(int $userId): array
    {
        $rows = $this->run('SELECT * FROM alert_rules WHERE user_id = ? ORDER BY id', [$userId])->fetchAll();
        foreach ($rows as &$r) {
            $r['config'] = json_decode((string) $r['config'], true) ?: [];
            $r['enabled'] = (bool) $r['enabled'];
        }
        return $rows;
    }

    public function addAlertRule(int $userId, string $scope, string $type, array $config): void
    {
        $this->run(
            'INSERT INTO alert_rules (user_id, scope, alert_type, config, enabled) VALUES (?, ?, ?, ?::jsonb, TRUE)',
            [$userId, $scope, $type, json_encode($config)]
        );
    }

    public function deleteAlertRule(int $id, int $userId): void
    {
        $this->run('DELETE FROM alert_rules WHERE id = ? AND user_id = ?', [$id, $userId]);
    }

    public function pendingOrders(int $userId): array
    {
        $rows = $this->run(
            'SELECT o.*, p.name AS portfolio_name FROM pending_orders o JOIN portfolios p ON p.id = o.portfolio_id
             WHERE o.user_id = ? ORDER BY o.status = ? DESC, o.id DESC',
            [$userId, 'open']
        )->fetchAll();
        return array_map([$this, 'hydrateOrder'], $rows);
    }

    public function openOrders(int $userId): array
    {
        $rows = $this->run('SELECT * FROM pending_orders WHERE user_id = ? AND status = ? ORDER BY id', [$userId, 'open'])->fetchAll();
        return array_map([$this, 'hydrateOrder'], $rows);
    }

    public function addOrder(int $userId, int $portfolioId, string $symbol, string $market, string $action, float $qty, float $price, string $currency, string $expiresOn): int
    {
        return (int) $this->run(
            'INSERT INTO pending_orders (user_id, portfolio_id, symbol, market, action, quantity, limit_price, currency, expires_on)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id',
            [$userId, $portfolioId, strtoupper($symbol), $market, $action, $qty, $price, $currency, $expiresOn]
        )->fetchColumn();
    }

    public function updateOrder(int $id, int $userId, float $qty, float $price, string $expiresOn): bool
    {
        return $this->run(
            "UPDATE pending_orders SET quantity = ?, limit_price = ?, expires_on = ? WHERE id = ? AND user_id = ? AND status = 'open'",
            [$qty, $price, $expiresOn, $id, $userId]
        )->rowCount() > 0;
    }

    public function cancelOrder(int $id, int $userId): bool
    {
        return $this->run("UPDATE pending_orders SET status = 'cancelled', resolved_at = NOW() WHERE id = ? AND user_id = ? AND status = 'open'", [$id, $userId])->rowCount() > 0;
    }

    /** Marks orders whose expiry date passed. Returns count. */
    public function expireOrders(int $userId, string $today): int
    {
        return $this->run("UPDATE pending_orders SET status = 'expired', resolved_at = NOW() WHERE user_id = ? AND status = 'open' AND expires_on < ?", [$userId, $today])->rowCount();
    }

    public function resolveOrder(int $id, string $status, ?int $tradeId): void
    {
        $this->run("UPDATE pending_orders SET status = ?, resolved_at = NOW(), executed_trade_id = ? WHERE id = ? AND status = 'open'", [$status, $tradeId, $id]);
    }

    private function hydrateOrder(array $r): array
    {
        return [
            'id' => (int) $r['id'],
            'user_id' => (int) $r['user_id'],
            'portfolio_id' => (int) $r['portfolio_id'],
            'portfolio_name' => $r['portfolio_name'] ?? null,
            'symbol' => $r['symbol'],
            'market' => $r['market'],
            'action' => $r['action'],
            'quantity' => (float) $r['quantity'],
            'limit_price' => (float) $r['limit_price'],
            'currency' => $r['currency'],
            'expires_on' => (string) $r['expires_on'],
            'status' => $r['status'],
            'executed_trade_id' => $r['executed_trade_id'] === null ? null : (int) $r['executed_trade_id'],
        ];
    }

    private function hydrateUser(array $r): array
    {
        return [
            'telegram_id' => (int) $r['telegram_id'],
            'language' => $r['language'],
            'default_commission' => (float) $r['default_commission'],
            'default_commission_currency' => $r['default_commission_currency'],
            'report_morning' => $r['report_morning'],
            'report_evening' => $r['report_evening'],
            'mover_threshold_pct' => (float) $r['mover_threshold_pct'],
            'last_portfolio_id' => $r['last_portfolio_id'] === null ? null : (int) $r['last_portfolio_id'],
        ];
    }

    private function hydratePortfolio(array $r): array
    {
        return [
            'id' => (int) $r['id'],
            'user_id' => (int) $r['user_id'],
            'name' => $r['name'],
            'opening_cash_ils' => (float) $r['opening_cash_ils'],
            'opening_cash_usd' => (float) $r['opening_cash_usd'],
            'commission_min_usd' => (float) $r['commission_min_usd'],
            'commission_min_ils' => (float) $r['commission_min_ils'],
            'commission_extra_type' => $r['commission_extra_type'],
            'commission_extra_value' => (float) $r['commission_extra_value'],
        ];
    }

    private function hydrateTrade(array $r): array
    {
        return [
            'id' => (int) $r['id'],
            'portfolio_id' => (int) $r['portfolio_id'],
            'symbol' => $r['symbol'],
            'market' => $r['market'],
            'asset_type' => $r['asset_type'],
            'action' => $r['action'],
            'quantity' => (float) $r['quantity'],
            'price' => (float) $r['price'],
            'currency' => $r['currency'],
            'commission' => (float) $r['commission'],
            'ts' => new DateTimeImmutable($r['timestamp']),
            'note' => $r['note'],
        ];
    }
}
