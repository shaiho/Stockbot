from __future__ import annotations

import logging
from datetime import date
from fractions import Fraction

import yfinance as yf

from src.db.repository import Repository

logger = logging.getLogger(__name__)

SPLIT_LOOKBACK_DAYS = 365


def yahoo_symbol(symbol: str, market: str) -> str:
    symbol = symbol.upper()
    if market == "IL":
        return symbol if symbol.endswith(".TA") else f"{symbol}.TA"
    return symbol


def ratio_to_factors(ratio: float) -> tuple[float, float]:
    if ratio <= 0:
        return 1.0, 1.0
    if abs(ratio - 1.0) < 1e-12:
        return 1.0, 1.0
    frac = Fraction(ratio).limit_denominator(1000)
    if ratio >= 1:
        return 1.0, float(frac)
    inv = Fraction(1 / ratio).limit_denominator(1000)
    return float(inv), 1.0


def split_label(from_factor: float, to_factor: float) -> str:
    ratio = to_factor / from_factor if from_factor else 1.0
    if ratio < 1:
        return f"{from_factor:g}:{to_factor:g} reverse"
    return f"{from_factor:g}:{to_factor:g}"


def split_note_markers(from_factor: float, to_factor: float) -> tuple[str, ...]:
    current = split_label(from_factor, to_factor)
    markers = (f"split {current}",)
    ratio = to_factor / from_factor if from_factor else 1.0
    if ratio < 1:
        legacy = f"split {to_factor:g}:{from_factor:g} reverse"
        if legacy not in markers:
            return (f"split {current}", legacy)
    return markers


def fetch_yfinance_splits(
    symbol: str,
    market: str,
    start: date,
    end: date,
) -> list[dict]:
    yahoo = yahoo_symbol(symbol, market)
    try:
        splits = yf.Ticker(yahoo).splits
    except Exception:
        logger.debug("yfinance splits unavailable for %s (%s)", symbol, market, exc_info=True)
        return []
    if splits is None or splits.empty:
        return []

    rows: list[dict] = []
    for ts, ratio in splits.items():
        split_day = ts.date() if hasattr(ts, "date") else ts.to_pydatetime().date()
        if split_day < start or split_day > end:
            continue
        ratio_f = float(ratio)
        from_factor, to_factor = ratio_to_factors(ratio_f)
        rows.append(
            {
                "date": split_day.isoformat(),
                "fromFactor": from_factor,
                "toFactor": to_factor,
                "ratio": ratio_f,
            }
        )
    return rows


async def split_already_applied(
    repo: Repository,
    portfolio_id: int,
    symbol: str,
    from_factor: float,
    to_factor: float,
) -> bool:
    trades = await repo.get_trades_for_symbol(portfolio_id, symbol.upper())
    markers = split_note_markers(from_factor, to_factor)
    return any(
        trade.note and any(marker in trade.note for marker in markers) for trade in trades
    )
