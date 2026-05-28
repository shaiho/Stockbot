from __future__ import annotations

from dataclasses import dataclass

from src.db.models import Holding
from src.market.prices import PriceProvider


@dataclass
class AllocationBreakdown:
    total_ils: float
    by_market_ils: dict[str, float]
    by_currency_ils: dict[str, float]


async def compute_allocation(
    holdings: list[Holding],
    cash_ils: float,
    cash_usd: float,
    prices: PriceProvider,
) -> AllocationBreakdown:
    fx = await prices.get_usd_ils()
    cash_total_ils = cash_ils + cash_usd * fx
    by_market = {"US": 0.0, "IL": 0.0, "CASH": cash_total_ils}
    by_currency_ils = {"ILS": cash_ils, "USD": cash_usd * fx}

    for holding in holdings:
        quote = await prices.get_quote(holding.symbol, holding.market)
        if not quote:
            continue
        value_native = holding.quantity * quote.price
        if holding.currency == "ILS":
            value_ils = value_native
        else:
            value_ils = value_native * fx
        by_market[holding.market] = by_market.get(holding.market, 0.0) + value_ils
        if holding.currency == "ILS":
            by_currency_ils["ILS"] += value_ils
        else:
            by_currency_ils["USD"] += value_ils

    total_ils = sum(by_market.values())
    if total_ils <= 0:
        total_ils = sum(by_currency_ils.values())
    return AllocationBreakdown(
        total_ils=total_ils,
        by_market_ils=by_market,
        by_currency_ils=by_currency_ils,
    )
