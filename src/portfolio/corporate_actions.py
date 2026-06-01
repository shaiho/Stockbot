from __future__ import annotations

import logging

from src.db.models import Holding, Portfolio
from src.db.repository import Repository

logger = logging.getLogger(__name__)


def split_ratio(from_factor: float, to_factor: float) -> float:
    if from_factor <= 0:
        return 1.0
    return to_factor / from_factor


def format_split_label(from_factor: float, to_factor: float) -> str:
    ratio = split_ratio(from_factor, to_factor)
    if ratio >= 1:
        return f"{from_factor:g}:{to_factor:g}"
    return f"{to_factor:g}:{from_factor:g} reverse"


async def find_active_holdings(
    repo: Repository, user_id: int, symbol: str, market: str
) -> list[tuple[Portfolio, Holding]]:
    symbol = symbol.upper()
    matches: list[tuple[Portfolio, Holding]] = []
    for portfolio in await repo.get_portfolios(user_id):
        for holding in await repo.get_holdings(portfolio.id):
            if (
                holding.symbol.upper() == symbol
                and holding.market == market
                and holding.quantity > 1e-9
            ):
                matches.append((portfolio, holding))
    return matches


async def apply_stock_split(
    repo: Repository,
    user_id: int,
    portfolio_id: int,
    symbol: str,
    from_factor: float,
    to_factor: float,
) -> int:
    ratio = split_ratio(from_factor, to_factor)
    if abs(ratio - 1.0) < 1e-12:
        return 0

    trades = await repo.get_trades_for_symbol(portfolio_id, symbol.upper())
    label = format_split_label(from_factor, to_factor)
    updated = 0
    for trade in trades:
        if trade.asset_type != "stock" or trade.action not in ("buy", "sell"):
            continue
        new_qty = trade.quantity * ratio
        new_price = trade.price / ratio if trade.price else trade.price
        note = trade.note or ""
        if label not in note:
            note = f"{note} | split {label}".strip(" |")
        ok = await repo.update_trade(
            trade.id,
            user_id,
            quantity=new_qty,
            price=new_price,
            note=note,
        )
        if ok:
            updated += 1
    logger.info(
        "Applied split %s to %s in portfolio %s (%d trades)",
        label,
        symbol,
        portfolio_id,
        updated,
    )
    return updated
