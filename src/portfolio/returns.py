from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pytz

from src.config import TIMEZONE
from src.db.models import Trade


@dataclass
class PeriodReturns:
    ytd_realized_ils: float
    month_realized_ils: float
    ytd_trade_count: int
    month_trade_count: int


async def compute_period_returns(trades: list[Trade], to_ils) -> PeriodReturns:
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    year_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    ytd_realized = 0.0
    month_realized = 0.0
    ytd_count = 0
    month_count = 0

    buckets: dict[str, dict] = {}
    for trade in sorted(trades, key=lambda t: (t.timestamp, t.id)):
        if trade.asset_type == "cash":
            continue
        key = trade.symbol
        if key not in buckets:
            buckets[key] = {"qty": 0.0, "cost": 0.0}
        bucket = buckets[key]
        ts = _parse_ts(trade.timestamp, tz)

        if trade.action == "buy":
            bucket["cost"] += trade.quantity * trade.price + trade.commission
            bucket["qty"] += trade.quantity
            if ts >= year_start:
                ytd_count += 1
            if ts >= month_start:
                month_count += 1
        elif trade.action == "sell" and bucket["qty"] > 0:
            avg = bucket["cost"] / bucket["qty"]
            pnl = (trade.price - avg) * trade.quantity - trade.commission
            pnl_ils = await to_ils(pnl, trade.currency)
            if ts >= year_start:
                ytd_realized += pnl_ils
                ytd_count += 1
            if ts >= month_start:
                month_realized += pnl_ils
                month_count += 1
            bucket["cost"] -= avg * trade.quantity
            bucket["qty"] -= trade.quantity
        elif trade.action == "dividend":
            div = trade.quantity * trade.price - trade.commission
            div_ils = await to_ils(div, trade.currency)
            if ts >= year_start:
                ytd_realized += div_ils
                ytd_count += 1
            if ts >= month_start:
                month_realized += div_ils
                month_count += 1

    return PeriodReturns(
        ytd_realized_ils=ytd_realized,
        month_realized_ils=month_realized,
        ytd_trade_count=ytd_count,
        month_trade_count=month_count,
    )


def _parse_ts(timestamp: str, tz) -> datetime:
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = tz.localize(dt)
        return dt.astimezone(tz)
    except ValueError:
        return datetime.min.replace(tzinfo=tz)
