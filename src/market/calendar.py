from __future__ import annotations

from datetime import datetime, time

import pytz

from src.config import TIMEZONE

# Saturday + Sunday (Asia/Jerusalem) — TASE and US markets are closed.
_NON_TRADING_WEEKDAYS = frozenset({5, 6})

_US_EASTERN = pytz.timezone("US/Eastern")


def is_trading_day(dt: datetime | None = None) -> bool:
    tz = pytz.timezone(TIMEZONE)
    now = dt.astimezone(tz) if dt and dt.tzinfo else datetime.now(tz)
    return now.weekday() not in _NON_TRADING_WEEKDAYS


def us_market_session(dt: datetime | None = None) -> str:
    """Return US session: pre, regular, post, or closed."""
    now = dt.astimezone(_US_EASTERN) if dt and dt.tzinfo else datetime.now(_US_EASTERN)
    if now.weekday() >= 5:
        return "closed"
    clock = now.time()
    if time(4, 0) <= clock < time(9, 30):
        return "pre"
    if time(9, 30) <= clock < time(16, 0):
        return "regular"
    if time(16, 0) <= clock < time(20, 0):
        return "post"
    return "closed"
