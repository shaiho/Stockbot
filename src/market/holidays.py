from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pytz

from src.config import FINNHUB_API_KEY, TIMEZONE

logger = logging.getLogger(__name__)

_TASE_HOLIDAYS_PATH = Path(__file__).parent / "data" / "tase_holidays.txt"
_US_HOLIDAY_CACHE: tuple[float, frozenset[str]] | None = None
_TASE_HOLIDAY_CACHE: tuple[float, frozenset[str]] | None = None
_CACHE_TTL = 86400
_TASE_EXCHANGE_CODES = ("TASE", "XTAE", "IL")


def _load_tase_holidays_file() -> frozenset[str]:
    dates: set[str] = set()
    if not _TASE_HOLIDAYS_PATH.exists():
        return frozenset()
    for line in _TASE_HOLIDAYS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        dates.add(line)
    return frozenset(dates)


def _parse_holiday_payload(payload: dict) -> frozenset[str]:
    dates: set[str] = set()
    for item in payload.get("data", []):
        at = item.get("atDate") or item.get("date")
        if not at:
            continue
        trading_hour = (item.get("tradingHour") or "").strip()
        if trading_hour:
            continue
        dates.add(str(at)[:10])
    return frozenset(dates)


def _persist_tase_holidays(dates: frozenset[str]) -> None:
    header = (
        "# TASE full-day closures — auto-synced from Finnhub.\n"
        "# Used as fallback when the API is unavailable.\n"
    )
    body = "\n".join(sorted(dates))
    _TASE_HOLIDAYS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _TASE_HOLIDAYS_PATH.write_text(f"{header}{body}\n" if body else header, encoding="utf-8")


def _fetch_finnhub_holidays(exchange: str) -> frozenset[str]:
    if not FINNHUB_API_KEY:
        return frozenset()
    import finnhub

    client = finnhub.Client(api_key=FINNHUB_API_KEY)
    payload = client.market_holiday(exchange=exchange)
    return _parse_holiday_payload(payload)


def _fetch_us_holidays(*, force: bool = False) -> frozenset[str]:
    global _US_HOLIDAY_CACHE
    now = time.time()
    if not force and _US_HOLIDAY_CACHE and now - _US_HOLIDAY_CACHE[0] < _CACHE_TTL:
        return _US_HOLIDAY_CACHE[1]
    try:
        cached = _fetch_finnhub_holidays("US")
        _US_HOLIDAY_CACHE = (now, cached)
        return cached
    except Exception:
        logger.exception("Failed to load US market holidays from Finnhub")
        return _US_HOLIDAY_CACHE[1] if _US_HOLIDAY_CACHE else frozenset()


def _fetch_tase_holidays(*, force: bool = False) -> frozenset[str]:
    global _TASE_HOLIDAY_CACHE
    now = time.time()
    if not force and _TASE_HOLIDAY_CACHE and now - _TASE_HOLIDAY_CACHE[0] < _CACHE_TTL:
        return _TASE_HOLIDAY_CACHE[1]

    file_fallback = _load_tase_holidays_file()
    if not FINNHUB_API_KEY:
        return file_fallback

    for exchange in _TASE_EXCHANGE_CODES:
        try:
            cached = _fetch_finnhub_holidays(exchange)
            if cached:
                _persist_tase_holidays(cached)
                _TASE_HOLIDAY_CACHE = (now, cached)
                logger.info("TASE holidays synced from Finnhub (%s): %d dates", exchange, len(cached))
                return cached
        except Exception:
            logger.debug("Finnhub market_holiday failed for exchange=%s", exchange, exc_info=True)

    logger.warning("Using TASE holidays file fallback (%d dates)", len(file_fallback))
    _TASE_HOLIDAY_CACHE = (now, file_fallback)
    return file_fallback


def refresh_holiday_calendars(*, force: bool = True) -> tuple[int, int]:
    """Refresh US + TASE holiday calendars. Returns (us_count, tase_count)."""
    us = _fetch_us_holidays(force=force)
    tase = _fetch_tase_holidays(force=force)
    return len(us), len(tase)


def is_weekend(dt: datetime) -> bool:
    tz = pytz.timezone(TIMEZONE)
    local = dt.astimezone(tz) if dt.tzinfo else dt.replace(tzinfo=tz)
    return local.weekday() >= 5


def is_exchange_holiday(day: date, market: str) -> bool:
    iso = day.isoformat()
    if market == "US":
        return iso in _fetch_us_holidays()
    if market == "IL":
        return iso in _fetch_tase_holidays()
    return False


def is_market_open(dt: datetime | None = None, market: str = "US") -> bool:
    tz = pytz.timezone(TIMEZONE)
    now = dt.astimezone(tz) if dt and dt.tzinfo else datetime.now(tz)
    if is_weekend(now):
        return False
    return not is_exchange_holiday(now.date(), market)


def is_trading_day(dt: datetime | None = None) -> bool:
    """True when at least one supported exchange is open (US or IL)."""
    tz = pytz.timezone(TIMEZONE)
    now = dt.astimezone(tz) if dt and dt.tzinfo else datetime.now(tz)
    if is_weekend(now):
        return False
    day = now.date()
    return not (is_exchange_holiday(day, "US") and is_exchange_holiday(day, "IL"))


def upcoming_holidays(market: str, days: int = 3) -> list[tuple[date, str]]:
    tz = pytz.timezone(TIMEZONE)
    today = datetime.now(tz).date()
    end = today + timedelta(days=days)
    holidays = _fetch_us_holidays() if market == "US" else _fetch_tase_holidays()
    result: list[tuple[date, str]] = []
    for iso in sorted(holidays):
        try:
            holiday_date = date.fromisoformat(iso)
        except ValueError:
            continue
        if today < holiday_date <= end:
            result.append((holiday_date, iso))
    return result
