from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite

from src.config import DATABASE_PATH, DATABASE_URL, MAX_PORTFOLIOS_PER_USER
from src.db.models import AdminDbStats, AlertRule, Holding, Portfolio, Trade, User, WatchlistItem

try:
    import asyncpg
except ImportError:  # pragma: no cover
    asyncpg = None  # type: ignore[assignment]

_UNSET = object()


class Repository:
    def __init__(self, db_path: Path | None = None, database_url: str | None = None) -> None:
        self.db_path = db_path or DATABASE_PATH
        self.database_url = database_url if database_url is not None else DATABASE_URL
        self._pool: asyncpg.Pool | None = None

    @property
    def _postgres(self) -> bool:
        return bool(self.database_url)

    async def init(self) -> None:
        if self._postgres:
            if asyncpg is None:
                raise RuntimeError("asyncpg is required when DATABASE_URL is set")
            ssl = "require" if "supabase" in self.database_url else None
            self._pool = await asyncpg.create_pool(
                self.database_url,
                min_size=1,
                max_size=10,
                ssl=ssl,
            )
            schema = (Path(__file__).parent / "schema_postgres.sql").read_text(encoding="utf-8")
            async with self._pool.acquire() as conn:
                for stmt in schema.split(";"):
                    stmt = stmt.strip()
                    if stmt:
                        await conn.execute(stmt)
            return

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        schema = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(schema)
            await self._migrate(db)
            await db.commit()

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def _migrate(self, db: aiosqlite.Connection) -> None:
        rows = await (await db.execute("PRAGMA table_info(portfolios)")).fetchall()
        cols = {row[1] for row in rows}
        additions = {
            "commission_min_usd": "REAL NOT NULL DEFAULT 0",
            "commission_min_ils": "REAL NOT NULL DEFAULT 0",
            "commission_extra_type": "TEXT NOT NULL DEFAULT 'fixed'",
            "commission_extra_value": "REAL NOT NULL DEFAULT 0",
        }
        for name, ddl in additions.items():
            if name not in cols:
                await db.execute(f"ALTER TABLE portfolios ADD COLUMN {name} {ddl}")

    @staticmethod
    def _sql(query: str, postgres: bool) -> str:
        if not postgres:
            return query
        idx = 1
        parts: list[str] = []
        for ch in query:
            if ch == "?":
                parts.append(f"${idx}")
                idx += 1
            else:
                parts.append(ch)
        return "".join(parts)

    @staticmethod
    def _text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, datetime):
            return value.isoformat(sep=" ", timespec="seconds")
        return str(value)

    @staticmethod
    def _coerce_timestamp(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        text = str(value).strip()
        for fmt in (
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
        ):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        return datetime.fromisoformat(text.replace("Z", "+00:00"))

    async def get_or_create_user(self, telegram_id: int) -> User:
        if self._postgres:
            assert self._pool is not None
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM users WHERE telegram_id = $1",
                    telegram_id,
                )
                if row:
                    return self._row_to_user(row)
                row = await conn.fetchrow(
                    """
                    INSERT INTO users (telegram_id)
                    VALUES ($1)
                    RETURNING *
                    """,
                    telegram_id,
                )
                return self._row_to_user(row)

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            row = await (
                await db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
            ).fetchone()
            if row:
                return self._row_to_user(row)
            await db.execute("INSERT INTO users (telegram_id) VALUES (?)", (telegram_id,))
            await db.commit()
            row = await (
                await db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
            ).fetchone()
            return self._row_to_user(row)

    async def update_user(self, user: User) -> None:
        query = """
            UPDATE users SET
                language = ?, onboarding_completed = ?,
                default_commission = ?, default_commission_currency = ?,
                report_morning = ?, report_evening = ?,
                mover_threshold_pct = ?, last_portfolio_id = ?
            WHERE telegram_id = ?
        """
        args = (
            user.language,
            bool(user.onboarding_completed),
            user.default_commission,
            user.default_commission_currency,
            user.report_morning,
            user.report_evening,
            user.mover_threshold_pct,
            user.last_portfolio_id,
            user.telegram_id,
        )
        if self._postgres:
            assert self._pool is not None
            async with self._pool.acquire() as conn:
                await conn.execute(self._sql(query, True), *args)
            return

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(self._sql(query, False), args)
            await db.commit()

    async def count_portfolios(self, user_id: int) -> int:
        query = "SELECT COUNT(*) AS cnt FROM portfolios WHERE user_id = ?"
        if self._postgres:
            assert self._pool is not None
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(self._sql(query, True), user_id)
                return int(row["cnt"])

        async with aiosqlite.connect(self.db_path) as db:
            row = await (
                await db.execute(self._sql(query, False), (user_id,))
            ).fetchone()
            return int(row[0])

    async def create_portfolio(
        self,
        user_id: int,
        name: str,
        opening_cash_ils: float = 0.0,
        opening_cash_usd: float = 0.0,
    ) -> Portfolio:
        count = await self.count_portfolios(user_id)
        if count >= MAX_PORTFOLIOS_PER_USER:
            raise ValueError("max_portfolios")
        args = (user_id, name.strip(), opening_cash_ils, opening_cash_usd)
        if self._postgres:
            assert self._pool is not None
            async with self._pool.acquire() as conn:
                try:
                    row = await conn.fetchrow(
                        """
                        INSERT INTO portfolios (user_id, name, opening_cash_ils, opening_cash_usd)
                        VALUES ($1, $2, $3, $4)
                        RETURNING *
                        """,
                        *args,
                    )
                except asyncpg.UniqueViolationError as exc:
                    raise ValueError("duplicate_name") from exc
                return self._row_to_portfolio(row)

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            try:
                cursor = await db.execute(
                    """
                    INSERT INTO portfolios (user_id, name, opening_cash_ils, opening_cash_usd)
                    VALUES (?, ?, ?, ?)
                    """,
                    args,
                )
                await db.commit()
            except aiosqlite.IntegrityError as exc:
                raise ValueError("duplicate_name") from exc
            row = await (
                await db.execute("SELECT * FROM portfolios WHERE id = ?", (cursor.lastrowid,))
            ).fetchone()
            return self._row_to_portfolio(row)

    async def get_portfolios(self, user_id: int) -> list[Portfolio]:
        query = "SELECT * FROM portfolios WHERE user_id = ? ORDER BY id"
        if self._postgres:
            assert self._pool is not None
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(self._sql(query, True), user_id)
                return [self._row_to_portfolio(r) for r in rows]

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await (
                await db.execute(self._sql(query, False), (user_id,))
            ).fetchall()
            return [self._row_to_portfolio(r) for r in rows]

    async def get_portfolio(self, portfolio_id: int, user_id: int) -> Portfolio | None:
        query = "SELECT * FROM portfolios WHERE id = ? AND user_id = ?"
        args = (portfolio_id, user_id)
        if self._postgres:
            assert self._pool is not None
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(self._sql(query, True), *args)
                return self._row_to_portfolio(row) if row else None

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            row = await (
                await db.execute(self._sql(query, False), args)
            ).fetchone()
            return self._row_to_portfolio(row) if row else None

    async def rename_portfolio(self, portfolio_id: int, user_id: int, name: str) -> None:
        query = "UPDATE portfolios SET name = ? WHERE id = ? AND user_id = ?"
        args = (name.strip(), portfolio_id, user_id)
        if self._postgres:
            assert self._pool is not None
            async with self._pool.acquire() as conn:
                try:
                    await conn.execute(self._sql(query, True), *args)
                except asyncpg.UniqueViolationError as exc:
                    raise ValueError("duplicate_name") from exc
            return

        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute(self._sql(query, False), args)
                await db.commit()
            except aiosqlite.IntegrityError as exc:
                raise ValueError("duplicate_name") from exc

    async def update_portfolio_opening_cash(
        self,
        portfolio_id: int,
        user_id: int,
        opening_cash_ils: float,
        opening_cash_usd: float,
    ) -> bool:
        query = """
            UPDATE portfolios
            SET opening_cash_ils = ?, opening_cash_usd = ?
            WHERE id = ? AND user_id = ?
        """
        args = (opening_cash_ils, opening_cash_usd, portfolio_id, user_id)
        if self._postgres:
            assert self._pool is not None
            async with self._pool.acquire() as conn:
                result = await conn.execute(self._sql(query, True), *args)
                return result.endswith("1")

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(self._sql(query, False), args)
            await db.commit()
            return cursor.rowcount > 0

    async def delete_portfolio(self, portfolio_id: int, user_id: int) -> bool:
        query = "DELETE FROM portfolios WHERE id = ? AND user_id = ?"
        args = (portfolio_id, user_id)
        if self._postgres:
            assert self._pool is not None
            async with self._pool.acquire() as conn:
                result = await conn.execute(self._sql(query, True), *args)
                return result.endswith("1")

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(self._sql(query, False), args)
            await db.commit()
            return cursor.rowcount > 0

    async def update_portfolio_commission(
        self,
        portfolio_id: int,
        user_id: int,
        *,
        commission_min_usd: float,
        commission_min_ils: float,
        commission_extra_type: str,
        commission_extra_value: float,
    ) -> bool:
        query = """
            UPDATE portfolios SET
                commission_min_usd = ?,
                commission_min_ils = ?,
                commission_extra_type = ?,
                commission_extra_value = ?
            WHERE id = ? AND user_id = ?
        """
        args = (
            commission_min_usd,
            commission_min_ils,
            commission_extra_type,
            commission_extra_value,
            portfolio_id,
            user_id,
        )
        if self._postgres:
            assert self._pool is not None
            async with self._pool.acquire() as conn:
                result = await conn.execute(self._sql(query, True), *args)
                return result.endswith("1")

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(self._sql(query, False), args)
            await db.commit()
            return cursor.rowcount > 0

    async def recalculate_portfolio_commissions(self, portfolio_id: int, user_id: int) -> int:
        from src.portfolio.commission import calc_trade_commission

        portfolio = await self.get_portfolio(portfolio_id, user_id)
        if not portfolio:
            return 0
        trades = await self.get_trades(portfolio_id)
        updated = 0
        for trade in trades:
            if trade.asset_type != "stock" or trade.action not in ("buy", "sell"):
                continue
            new_commission = calc_trade_commission(
                portfolio, trade.quantity, trade.price, trade.currency
            )
            if abs(new_commission - trade.commission) > 1e-9:
                ok = await self.update_trade(
                    trade.id, user_id, commission=new_commission
                )
                if ok:
                    updated += 1
        return updated

    async def add_trade(
        self,
        portfolio_id: int,
        symbol: str,
        market: str,
        asset_type: str,
        action: str,
        quantity: float,
        price: float,
        currency: str,
        commission: float,
        note: str | None = None,
        timestamp: str | None = None,
    ) -> Trade:
        base_args = (
            portfolio_id,
            symbol.upper(),
            market,
            asset_type,
            action,
            quantity,
            price,
            currency,
            commission,
            note,
        )
        if self._postgres:
            assert self._pool is not None
            async with self._pool.acquire() as conn:
                if timestamp:
                    row = await conn.fetchrow(
                        """
                        INSERT INTO trades
                        (portfolio_id, symbol, market, asset_type, action, quantity, price, currency, commission, note, timestamp)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                        RETURNING *
                        """,
                        *base_args,
                        self._coerce_timestamp(timestamp),
                    )
                else:
                    row = await conn.fetchrow(
                        """
                        INSERT INTO trades
                        (portfolio_id, symbol, market, asset_type, action, quantity, price, currency, commission, note)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                        RETURNING *
                        """,
                        *base_args,
                    )
                return self._row_to_trade(row)

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if timestamp:
                cursor = await db.execute(
                    """
                    INSERT INTO trades
                    (portfolio_id, symbol, market, asset_type, action, quantity, price, currency, commission, note, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (*base_args, timestamp),
                )
            else:
                cursor = await db.execute(
                    """
                    INSERT INTO trades
                    (portfolio_id, symbol, market, asset_type, action, quantity, price, currency, commission, note)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    base_args,
                )
            await db.commit()
            row = await (
                await db.execute("SELECT * FROM trades WHERE id = ?", (cursor.lastrowid,))
            ).fetchone()
            return self._row_to_trade(row)

    async def add_cash_deposit(
        self,
        portfolio_id: int,
        currency: str,
        amount: float,
        timestamp: str | None = None,
        note: str | None = None,
    ) -> Trade:
        return await self.add_trade(
            portfolio_id=portfolio_id,
            symbol="CASH",
            market="CASH",
            asset_type="cash",
            action="deposit",
            quantity=amount,
            price=1.0,
            currency=currency,
            commission=0.0,
            note=note or "deposit",
            timestamp=timestamp,
        )

    async def add_cash_withdrawal(
        self,
        portfolio_id: int,
        currency: str,
        amount: float,
        timestamp: str | None = None,
        note: str | None = None,
    ) -> Trade:
        return await self.add_trade(
            portfolio_id=portfolio_id,
            symbol="CASH",
            market="CASH",
            asset_type="cash",
            action="withdraw",
            quantity=amount,
            price=1.0,
            currency=currency,
            commission=0.0,
            note=note or "withdraw",
            timestamp=timestamp,
        )

    async def get_trade(self, trade_id: int, user_id: int) -> Trade | None:
        query = """
            SELECT t.* FROM trades t
            JOIN portfolios p ON p.id = t.portfolio_id
            WHERE t.id = ? AND p.user_id = ?
        """
        args = (trade_id, user_id)
        if self._postgres:
            assert self._pool is not None
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(self._sql(query, True), *args)
                return self._row_to_trade(row) if row else None

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            row = await (
                await db.execute(self._sql(query, False), args)
            ).fetchone()
            return self._row_to_trade(row) if row else None

    async def delete_trade(self, trade_id: int, user_id: int) -> bool:
        query = """
            DELETE FROM trades
            WHERE id = ? AND portfolio_id IN (
                SELECT id FROM portfolios WHERE user_id = ?
            )
        """
        args = (trade_id, user_id)
        if self._postgres:
            assert self._pool is not None
            async with self._pool.acquire() as conn:
                result = await conn.execute(self._sql(query, True), *args)
                return result.endswith("1")

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(self._sql(query, False), args)
            await db.commit()
            return cursor.rowcount > 0

    async def update_trade(
        self,
        trade_id: int,
        user_id: int,
        *,
        quantity: float | None = None,
        price: float | None = None,
        commission: float | None = None,
        timestamp: str | None = None,
        note: Any = _UNSET,
    ) -> bool:
        trade = await self.get_trade(trade_id, user_id)
        if not trade:
            return False

        updates: dict[str, Any] = {}
        if quantity is not None:
            updates["quantity"] = quantity
        if price is not None:
            updates["price"] = price
        if commission is not None:
            updates["commission"] = commission
        if timestamp is not None:
            updates["timestamp"] = (
                self._coerce_timestamp(timestamp) if self._postgres else timestamp
            )
        if note is not _UNSET:
            updates["note"] = note
        if not updates:
            return True

        set_clause = ", ".join(f"{column} = ?" for column in updates)
        query = f"UPDATE trades SET {set_clause} WHERE id = ?"
        args = (*updates.values(), trade_id)
        if self._postgres:
            assert self._pool is not None
            async with self._pool.acquire() as conn:
                result = await conn.execute(self._sql(query, True), *args)
                return result.endswith("1")

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(self._sql(query, False), args)
            await db.commit()
            return cursor.rowcount > 0

    async def get_trades(self, portfolio_id: int) -> list[Trade]:
        query = "SELECT * FROM trades WHERE portfolio_id = ? ORDER BY timestamp, id"
        if self._postgres:
            assert self._pool is not None
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(self._sql(query, True), portfolio_id)
                return [self._row_to_trade(r) for r in rows]

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await (
                await db.execute(self._sql(query, False), (portfolio_id,))
            ).fetchall()
            return [self._row_to_trade(r) for r in rows]

    async def get_trades_for_symbol(self, portfolio_id: int, symbol: str) -> list[Trade]:
        query = """
            SELECT * FROM trades
            WHERE portfolio_id = ? AND symbol = ?
            ORDER BY timestamp, id
        """
        args = (portfolio_id, symbol.upper())
        if self._postgres:
            assert self._pool is not None
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(self._sql(query, True), *args)
                return [self._row_to_trade(r) for r in rows]

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await (
                await db.execute(self._sql(query, False), args)
            ).fetchall()
            return [self._row_to_trade(r) for r in rows]

    async def get_holdings(
        self, portfolio_id: int, trades: list[Trade] | None = None
    ) -> list[Holding]:
        if trades is None:
            trades = await self.get_trades(portfolio_id)
        buckets: dict[tuple[str, str, str, str], dict] = {}
        for trade in trades:
            if trade.asset_type == "cash":
                continue
            key = (trade.symbol, trade.market, trade.asset_type, trade.currency)
            if key not in buckets:
                buckets[key] = {
                    "quantity": 0.0,
                    "total_cost": 0.0,
                    "trade_count": 0,
                }
            bucket = buckets[key]
            bucket["trade_count"] += 1
            if trade.action == "buy":
                bucket["total_cost"] += trade.quantity * trade.price + trade.commission
                bucket["quantity"] += trade.quantity
            elif trade.action == "sell":
                if bucket["quantity"] <= 0:
                    continue
                avg = bucket["total_cost"] / bucket["quantity"]
                bucket["quantity"] -= trade.quantity
                bucket["total_cost"] -= avg * trade.quantity
        holdings: list[Holding] = []
        for (symbol, market, asset_type, currency), bucket in buckets.items():
            qty = bucket["quantity"]
            if qty <= 1e-9:
                continue
            holdings.append(
                Holding(
                    symbol=symbol,
                    market=market,
                    asset_type=asset_type,
                    quantity=qty,
                    avg_cost=bucket["total_cost"] / qty,
                    currency=currency,
                    trade_count=bucket["trade_count"],
                )
            )
        return holdings

    async def get_cash_balances(
        self, portfolio_id: int, trades: list[Trade] | None = None
    ) -> tuple[float, float]:
        portfolio = await self._get_portfolio_raw(portfolio_id)
        if not portfolio:
            return 0.0, 0.0
        ils = float(portfolio["opening_cash_ils"])
        usd = float(portfolio["opening_cash_usd"])
        if trades is None:
            trades = await self.get_trades(portfolio_id)
        for trade in trades:
            if trade.asset_type == "cash":
                if trade.action == "deposit":
                    if trade.currency == "ILS":
                        ils += trade.quantity
                    else:
                        usd += trade.quantity
                elif trade.action == "withdraw":
                    if trade.currency == "ILS":
                        ils -= trade.quantity
                    else:
                        usd -= trade.quantity
                continue
            gross = trade.quantity * trade.price
            total = gross + trade.commission
            if trade.action == "buy":
                if trade.currency == "ILS":
                    ils -= total
                else:
                    usd -= total
            elif trade.action == "sell":
                proceeds = gross - trade.commission
                if trade.currency == "ILS":
                    ils += proceeds
                else:
                    usd += proceeds
            elif trade.action == "dividend":
                proceeds = gross - trade.commission
                if trade.currency == "ILS":
                    ils += proceeds
                else:
                    usd += proceeds
        return ils, usd

    async def get_all_users(self) -> list[User]:
        if self._postgres:
            assert self._pool is not None
            async with self._pool.acquire() as conn:
                rows = await conn.fetch("SELECT * FROM users")
                return [self._row_to_user(r) for r in rows]

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await (await db.execute("SELECT * FROM users")).fetchall()
            return [self._row_to_user(r) for r in rows]

    async def get_all_portfolios(self) -> list[Portfolio]:
        query = "SELECT * FROM portfolios ORDER BY user_id, id"
        if self._postgres:
            assert self._pool is not None
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(query)
                return [self._row_to_portfolio(r) for r in rows]

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await (await db.execute(query)).fetchall()
            return [self._row_to_portfolio(r) for r in rows]

    async def get_admin_db_stats(self) -> AdminDbStats:
        if self._postgres:
            assert self._pool is not None
            async with self._pool.acquire() as conn:
                return await self._fetch_admin_db_stats_postgres(conn)

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            return await self._fetch_admin_db_stats_sqlite(db)

    async def _fetch_admin_db_stats_postgres(self, conn: asyncpg.Connection) -> AdminDbStats:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS total_users,
                COUNT(*) FILTER (WHERE onboarding_completed) AS onboarded_users,
                COUNT(*) FILTER (WHERE language = 'he') AS users_he,
                COUNT(*) FILTER (WHERE language = 'en') AS users_en,
                COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '7 days') AS new_users_7d,
                COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '30 days') AS new_users_30d
            FROM users
            """
        )
        pf = await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS total_portfolios,
                COUNT(DISTINCT user_id) AS users_with_portfolio
            FROM portfolios
            """
        )
        tr = await conn.fetchrow("SELECT COUNT(*) AS total_trades FROM trades")
        wl = await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS total_watchlist_items,
                COUNT(DISTINCT user_id) AS users_with_watchlist
            FROM watchlist
            """
        )
        al = await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS total_alerts,
                COUNT(*) FILTER (WHERE enabled) AS enabled_alerts
            FROM alert_rules
            """
        )
        watch_rows = await conn.fetch(
            """
            SELECT symbol, market, COUNT(DISTINCT user_id) AS user_count
            FROM watchlist
            GROUP BY symbol, market
            ORDER BY user_count DESC, symbol
            LIMIT 5
            """
        )
        trade_rows = await conn.fetch(
            """
            SELECT symbol, market, COUNT(*) AS trade_count
            FROM trades
            WHERE asset_type != 'cash'
            GROUP BY symbol, market
            ORDER BY trade_count DESC, symbol
            LIMIT 5
            """
        )
        return AdminDbStats(
            total_users=row["total_users"],
            onboarded_users=row["onboarded_users"],
            users_he=row["users_he"],
            users_en=row["users_en"],
            new_users_7d=row["new_users_7d"],
            new_users_30d=row["new_users_30d"],
            total_portfolios=pf["total_portfolios"],
            users_with_portfolio=pf["users_with_portfolio"],
            total_trades=tr["total_trades"],
            total_watchlist_items=wl["total_watchlist_items"],
            users_with_watchlist=wl["users_with_watchlist"],
            total_alerts=al["total_alerts"],
            enabled_alerts=al["enabled_alerts"],
            top_watchlist=[(r["symbol"], r["market"], r["user_count"]) for r in watch_rows],
            top_traded=[(r["symbol"], r["market"], r["trade_count"]) for r in trade_rows],
        )

    async def _fetch_admin_db_stats_sqlite(self, db: aiosqlite.Connection) -> AdminDbStats:
        row = await (
            await db.execute(
                """
                SELECT
                    COUNT(*) AS total_users,
                    SUM(CASE WHEN onboarding_completed = 1 THEN 1 ELSE 0 END) AS onboarded_users,
                    SUM(CASE WHEN language = 'he' THEN 1 ELSE 0 END) AS users_he,
                    SUM(CASE WHEN language = 'en' THEN 1 ELSE 0 END) AS users_en,
                    SUM(CASE WHEN created_at >= datetime('now', '-7 days') THEN 1 ELSE 0 END) AS new_users_7d,
                    SUM(CASE WHEN created_at >= datetime('now', '-30 days') THEN 1 ELSE 0 END) AS new_users_30d
                FROM users
                """
            )
        ).fetchone()
        pf = await (
            await db.execute(
                """
                SELECT
                    COUNT(*) AS total_portfolios,
                    COUNT(DISTINCT user_id) AS users_with_portfolio
                FROM portfolios
                """
            )
        ).fetchone()
        tr = await (await db.execute("SELECT COUNT(*) AS total_trades FROM trades")).fetchone()
        wl = await (
            await db.execute(
                """
                SELECT
                    COUNT(*) AS total_watchlist_items,
                    COUNT(DISTINCT user_id) AS users_with_watchlist
                FROM watchlist
                """
            )
        ).fetchone()
        al = await (
            await db.execute(
                """
                SELECT
                    COUNT(*) AS total_alerts,
                    SUM(CASE WHEN enabled = 1 THEN 1 ELSE 0 END) AS enabled_alerts
                FROM alert_rules
                """
            )
        ).fetchone()
        watch_rows = await (
            await db.execute(
                """
                SELECT symbol, market, COUNT(DISTINCT user_id) AS user_count
                FROM watchlist
                GROUP BY symbol, market
                ORDER BY user_count DESC, symbol
                LIMIT 5
                """
            )
        ).fetchall()
        trade_rows = await (
            await db.execute(
                """
                SELECT symbol, market, COUNT(*) AS trade_count
                FROM trades
                WHERE asset_type != 'cash'
                GROUP BY symbol, market
                ORDER BY trade_count DESC, symbol
                LIMIT 5
                """
            )
        ).fetchall()
        return AdminDbStats(
            total_users=row["total_users"],
            onboarded_users=row["onboarded_users"],
            users_he=row["users_he"],
            users_en=row["users_en"],
            new_users_7d=row["new_users_7d"],
            new_users_30d=row["new_users_30d"],
            total_portfolios=pf["total_portfolios"],
            users_with_portfolio=pf["users_with_portfolio"],
            total_trades=tr["total_trades"],
            total_watchlist_items=wl["total_watchlist_items"],
            users_with_watchlist=wl["users_with_watchlist"],
            total_alerts=al["total_alerts"],
            enabled_alerts=al["enabled_alerts"],
            top_watchlist=[(r["symbol"], r["market"], r["user_count"]) for r in watch_rows],
            top_traded=[(r["symbol"], r["market"], r["trade_count"]) for r in trade_rows],
        )

    async def add_watchlist_item(self, user_id: int, symbol: str, market: str) -> WatchlistItem:
        args = (user_id, symbol.upper(), market)
        if self._postgres:
            assert self._pool is not None
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO watchlist (user_id, symbol, market)
                    VALUES ($1, $2, $3)
                    RETURNING *
                    """,
                    *args,
                )
                return WatchlistItem(
                    id=row["id"],
                    user_id=row["user_id"],
                    symbol=row["symbol"],
                    market=row["market"],
                    added_at=self._text(row["added_at"]),
                )

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "INSERT INTO watchlist (user_id, symbol, market) VALUES (?, ?, ?)",
                args,
            )
            await db.commit()
            row = await (
                await db.execute("SELECT * FROM watchlist WHERE id = ?", (cursor.lastrowid,))
            ).fetchone()
            return WatchlistItem(
                id=row["id"],
                user_id=row["user_id"],
                symbol=row["symbol"],
                market=row["market"],
                added_at=row["added_at"],
            )

    async def get_watchlist(self, user_id: int) -> list[WatchlistItem]:
        query = "SELECT * FROM watchlist WHERE user_id = ? ORDER BY symbol"
        if self._postgres:
            assert self._pool is not None
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(self._sql(query, True), user_id)
                return [
                    WatchlistItem(
                        id=r["id"],
                        user_id=r["user_id"],
                        symbol=r["symbol"],
                        market=r["market"],
                        added_at=self._text(r["added_at"]),
                    )
                    for r in rows
                ]

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await (
                await db.execute(self._sql(query, False), (user_id,))
            ).fetchall()
            return [
                WatchlistItem(
                    id=r["id"],
                    user_id=r["user_id"],
                    symbol=r["symbol"],
                    market=r["market"],
                    added_at=r["added_at"],
                )
                for r in rows
            ]

    async def remove_watchlist_item(self, item_id: int, user_id: int) -> bool:
        query = "DELETE FROM watchlist WHERE id = ? AND user_id = ?"
        args = (item_id, user_id)
        if self._postgres:
            assert self._pool is not None
            async with self._pool.acquire() as conn:
                result = await conn.execute(self._sql(query, True), *args)
                return result.endswith("1")

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(self._sql(query, False), args)
            await db.commit()
            return cursor.rowcount > 0

    async def add_alert_rule(
        self,
        user_id: int,
        scope: str,
        alert_type: str,
        config: dict,
        enabled: bool = True,
    ) -> AlertRule:
        if self._postgres:
            assert self._pool is not None
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO alert_rules (user_id, scope, alert_type, config, enabled)
                    VALUES ($1, $2, $3, $4::jsonb, $5)
                    RETURNING *
                    """,
                    user_id,
                    scope,
                    alert_type,
                    json.dumps(config),
                    enabled,
                )
                return self._row_to_alert_rule(row)

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                INSERT INTO alert_rules (user_id, scope, alert_type, config, enabled)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, scope, alert_type, json.dumps(config), int(enabled)),
            )
            await db.commit()
            row = await (
                await db.execute("SELECT * FROM alert_rules WHERE id = ?", (cursor.lastrowid,))
            ).fetchone()
            return self._row_to_alert_rule(row)

    async def get_alert_rules(self, user_id: int) -> list[AlertRule]:
        query = "SELECT * FROM alert_rules WHERE user_id = ? ORDER BY id"
        if self._postgres:
            assert self._pool is not None
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(self._sql(query, True), user_id)
                return [self._row_to_alert_rule(r) for r in rows]

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await (
                await db.execute(self._sql(query, False), (user_id,))
            ).fetchall()
            return [self._row_to_alert_rule(r) for r in rows]

    async def delete_alert_rule(self, rule_id: int, user_id: int) -> bool:
        query = "DELETE FROM alert_rules WHERE id = ? AND user_id = ?"
        args = (rule_id, user_id)
        if self._postgres:
            assert self._pool is not None
            async with self._pool.acquire() as conn:
                result = await conn.execute(self._sql(query, True), *args)
                return result.endswith("1")

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(self._sql(query, False), args)
            await db.commit()
            return cursor.rowcount > 0

    async def was_alert_sent_today(self, user_id: int, alert_key: str, today: str) -> bool:
        query = "SELECT last_sent_date FROM alert_state WHERE user_id = ? AND alert_key = ?"
        args = (user_id, alert_key)
        if self._postgres:
            assert self._pool is not None
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(self._sql(query, True), *args)
                return bool(row and row["last_sent_date"] == today)

        async with aiosqlite.connect(self.db_path) as db:
            row = await (
                await db.execute(self._sql(query, False), args)
            ).fetchone()
            return bool(row and row[0] == today)

    async def mark_alert_sent(self, user_id: int, alert_key: str, today: str) -> None:
        query = """
            INSERT INTO alert_state (user_id, alert_key, last_sent_date)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, alert_key) DO UPDATE SET last_sent_date = excluded.last_sent_date
        """
        args = (user_id, alert_key, today)
        if self._postgres:
            assert self._pool is not None
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO alert_state (user_id, alert_key, last_sent_date)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (user_id, alert_key)
                    DO UPDATE SET last_sent_date = EXCLUDED.last_sent_date
                    """,
                    *args,
                )
            return

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(self._sql(query, False), args)
            await db.commit()

    async def _get_portfolio_raw(self, portfolio_id: int) -> Mapping[str, Any] | None:
        query = "SELECT * FROM portfolios WHERE id = ?"
        if self._postgres:
            assert self._pool is not None
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(self._sql(query, True), portfolio_id)
                return row

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            return await (
                await db.execute(self._sql(query, False), (portfolio_id,))
            ).fetchone()

    @staticmethod
    def _row_to_user(row: Mapping[str, Any]) -> User:
        return User(
            telegram_id=row["telegram_id"],
            language=row["language"],
            onboarding_completed=bool(row["onboarding_completed"]),
            default_commission=row["default_commission"],
            default_commission_currency=row["default_commission_currency"],
            report_morning=row["report_morning"],
            report_evening=row["report_evening"],
            mover_threshold_pct=row["mover_threshold_pct"],
            last_portfolio_id=row["last_portfolio_id"],
        )

    @staticmethod
    def _row_to_portfolio(row: Mapping[str, Any]) -> Portfolio:
        return Portfolio(
            id=row["id"],
            user_id=row["user_id"],
            name=row["name"],
            opening_cash_ils=row["opening_cash_ils"],
            opening_cash_usd=row["opening_cash_usd"],
            commission_min_usd=row["commission_min_usd"],
            commission_min_ils=row["commission_min_ils"],
            commission_extra_type=row["commission_extra_type"],
            commission_extra_value=row["commission_extra_value"],
            opened_at=Repository._text(row["opened_at"]),
        )

    @staticmethod
    def _row_to_trade(row: Mapping[str, Any]) -> Trade:
        return Trade(
            id=row["id"],
            portfolio_id=row["portfolio_id"],
            symbol=row["symbol"],
            market=row["market"],
            asset_type=row["asset_type"],
            action=row["action"],
            quantity=row["quantity"],
            price=row["price"],
            currency=row["currency"],
            commission=row["commission"],
            timestamp=Repository._text(row["timestamp"]),
            note=row["note"],
        )

    @staticmethod
    def _row_to_alert_rule(row: Mapping[str, Any]) -> AlertRule:
        config = row["config"]
        if isinstance(config, str):
            config = json.loads(config)
        return AlertRule(
            id=row["id"],
            user_id=row["user_id"],
            scope=row["scope"],
            alert_type=row["alert_type"],
            config=config,
            enabled=bool(row["enabled"]),
        )
