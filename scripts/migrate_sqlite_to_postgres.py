"""One-time migration from local SQLite to Supabase/Postgres.

Usage:
    python -m scripts.migrate_sqlite_to_postgres

Requires DATABASE_URL in .env (Supabase connection string).
Reads from DATABASE_PATH (default: data/stockbot.db).
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite
import asyncpg

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import DATABASE_PATH, DATABASE_URL  # noqa: E402


def parse_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
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


TABLES = [
    (
        "users",
        """
        INSERT INTO users (
            telegram_id, language, onboarding_completed, default_commission,
            default_commission_currency, report_morning, report_evening,
            mover_threshold_pct, last_portfolio_id, created_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        ON CONFLICT (telegram_id) DO NOTHING
        """,
        lambda r: (
            r["telegram_id"],
            r["language"],
            bool(r["onboarding_completed"]),
            r["default_commission"],
            r["default_commission_currency"],
            r["report_morning"],
            r["report_evening"],
            r["mover_threshold_pct"],
            r["last_portfolio_id"],
            parse_ts(r["created_at"]),
        ),
    ),
    (
        "portfolios",
        """
        INSERT INTO portfolios (
            id, user_id, name, opening_cash_ils, opening_cash_usd,
            commission_min_usd, commission_min_ils, commission_extra_type,
            commission_extra_value, opened_at, created_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        ON CONFLICT (id) DO NOTHING
        """,
        lambda r: (
            r["id"],
            r["user_id"],
            r["name"],
            r["opening_cash_ils"],
            r["opening_cash_usd"],
            r.get("commission_min_usd", 0),
            r.get("commission_min_ils", 0),
            r.get("commission_extra_type", "fixed"),
            r.get("commission_extra_value", 0),
            parse_ts(r["opened_at"]),
            parse_ts(r["created_at"]),
        ),
    ),
    (
        "trades",
        """
        INSERT INTO trades (
            id, portfolio_id, symbol, market, asset_type, action,
            quantity, price, currency, commission, timestamp, note
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        ON CONFLICT (id) DO NOTHING
        """,
        lambda r: (
            r["id"],
            r["portfolio_id"],
            r["symbol"],
            r["market"],
            r["asset_type"],
            r["action"],
            r["quantity"],
            r["price"],
            r["currency"],
            r["commission"],
            parse_ts(r["timestamp"]),
            r["note"],
        ),
    ),
    (
        "watchlist",
        """
        INSERT INTO watchlist (id, user_id, symbol, market, added_at)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (id) DO NOTHING
        """,
        lambda r: (r["id"], r["user_id"], r["symbol"], r["market"], parse_ts(r["added_at"])),
    ),
    (
        "alert_rules",
        """
        INSERT INTO alert_rules (id, user_id, scope, alert_type, config, enabled, created_at)
        VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7)
        ON CONFLICT (id) DO NOTHING
        """,
        lambda r: (
            r["id"],
            r["user_id"],
            r["scope"],
            r["alert_type"],
            r["config"],
            bool(r["enabled"]),
            parse_ts(r["created_at"]),
        ),
    ),
    (
        "alert_state",
        """
        INSERT INTO alert_state (id, user_id, alert_key, last_sent_date)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (id) DO NOTHING
        """,
        lambda r: (r["id"], r["user_id"], r["alert_key"], r["last_sent_date"]),
    ),
]

SEQUENCES = [
    "portfolios_id_seq",
    "trades_id_seq",
    "watchlist_id_seq",
    "alert_rules_id_seq",
    "alert_state_id_seq",
]


async def migrate() -> None:
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL is missing from .env")
        sys.exit(1)
    if not DATABASE_PATH.exists():
        print(f"ERROR: SQLite file not found: {DATABASE_PATH}")
        sys.exit(1)

    ssl = "require" if "supabase" in DATABASE_URL else None
    try:
        pool = await asyncpg.create_pool(DATABASE_URL, ssl=ssl)
    except OSError as exc:
        print(f"ERROR: cannot reach database ({exc})")
        if "supabase.co" in DATABASE_URL and "pooler.supabase.com" not in DATABASE_URL:
            print()
            print("Direct Supabase URL (db.*.supabase.co) is IPv6-only.")
            print("On Windows / IPv4 networks use Session pooler instead — still port 5432:")
            print("  postgresql://postgres.[project-ref]:[password]@aws-0-[region].pooler.supabase.com:5432/postgres")
            print("Copy it from Supabase → Project Settings → Database → Connection string → Session pooler.")
        print()
        print("Also check DNS: if lookups fail, set Windows DNS to 8.8.8.8 / 1.1.1.1.")
        sys.exit(1)

    async with pool.acquire() as conn:
        schema = (ROOT / "src" / "db" / "schema_postgres.sql").read_text(encoding="utf-8")
        for stmt in schema.split(";"):
            stmt = stmt.strip()
            if stmt:
                await conn.execute(stmt)

    async with aiosqlite.connect(DATABASE_PATH) as sqlite:
        sqlite.row_factory = aiosqlite.Row
        portfolio_ids = {
            int(row[0])
            for row in await (await sqlite.execute("SELECT id FROM portfolios")).fetchall()
        }
        user_ids = {
            int(row[0])
            for row in await (await sqlite.execute("SELECT telegram_id FROM users")).fetchall()
        }

        async with pool.acquire() as pg:
            for table, insert_sql, row_fn in TABLES:
                rows = await (await sqlite.execute(f"SELECT * FROM {table}")).fetchall()
                count = 0
                skipped = 0
                for row in rows:
                    data = dict(row)
                    if table == "portfolios" and int(data["user_id"]) not in user_ids:
                        skipped += 1
                        continue
                    if table == "trades" and int(data["portfolio_id"]) not in portfolio_ids:
                        skipped += 1
                        continue
                    if table == "watchlist" and int(data["user_id"]) not in user_ids:
                        skipped += 1
                        continue
                    if table in ("alert_rules", "alert_state") and int(data["user_id"]) not in user_ids:
                        skipped += 1
                        continue
                    if table == "alert_rules":
                        data["config"] = json.dumps(json.loads(data["config"]))
                    await pg.execute(insert_sql, *row_fn(data))
                    count += 1
                suffix = f" ({skipped} skipped)" if skipped else ""
                print(f"{table}: {count} rows{suffix}")

            for seq in SEQUENCES:
                table = seq.replace("_id_seq", "")
                await pg.execute(
                    f"SELECT setval('{seq}', COALESCE((SELECT MAX(id) FROM {table}), 1))"
                )

    await pool.close()
    print("Migration complete.")


if __name__ == "__main__":
    asyncio.run(migrate())
