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
        $st = $this->db->prepare($sql);
        foreach (array_values($args) as $i => $v) {
            $st->bindValue($i + 1, $v, is_bool($v) ? PDO::PARAM_BOOL : (is_int($v) ? PDO::PARAM_INT : (is_null($v) ? PDO::PARAM_NULL : PDO::PARAM_STR)));
        }
        $st->execute();
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

    public function trades(int $portfolioId): array
    {
        $rows = $this->run('SELECT * FROM trades WHERE portfolio_id = ? ORDER BY timestamp, id', [$portfolioId])->fetchAll();
        return array_map([$this, 'hydrateTrade'], $rows);
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
