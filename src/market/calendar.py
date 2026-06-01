from __future__ import annotations

from datetime import datetime, time

import pytz

from src.market.holidays import (
    is_exchange_holiday,
    is_trading_day as _holiday_trading_day,
    is_weekend,
)
_US_EASTERN = pytz.timezone("US/Eastern")


def is_trading_day(dt: datetime | None = None) -> bool:
    return _holiday_trading_day(dt)


def us_market_session(dt: datetime | None = None) -> str:
    """Return US session: pre, regular, post, or closed."""
    now = dt.astimezone(_US_EASTERN) if dt and dt.tzinfo else datetime.now(_US_EASTERN)
    if is_weekend(now):
        return "closed"
    if is_exchange_holiday(now.date(), "US"):
        return "closed"
    clock = now.time()
    if time(4, 0) <= clock < time(9, 30):
        return "pre"
    if time(9, 30) <= clock < time(16, 0):
        return "regular"
    if time(16, 0) <= clock < time(20, 0):
        return "post"
    return "closed"
