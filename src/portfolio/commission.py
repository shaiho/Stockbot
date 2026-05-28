from __future__ import annotations

from src.db.models import Portfolio


def calc_trade_commission(
    portfolio: Portfolio,
    quantity: float,
    price: float,
    currency: str,
) -> float:
    trade_value = quantity * price
    minimum = (
        portfolio.commission_min_ils if currency == "ILS" else portfolio.commission_min_usd
    )
    if portfolio.commission_extra_type == "percent":
        extra = trade_value * (portfolio.commission_extra_value / 100)
    else:
        extra = portfolio.commission_extra_value
    return max(minimum, extra)


def format_commission_settings(portfolio: Portfolio, t: dict) -> str:
    extra = portfolio.commission_extra_value
    if portfolio.commission_extra_type == "percent":
        extra_label = f"{extra:g}%"
    else:
        extra_label = f"${extra:g} / ₪{extra:g}"
    return (
        f"\n{t['portfolio_commission_title']}\n"
        f"{t['commission_min_usd']}: ${portfolio.commission_min_usd:g}\n"
        f"{t['commission_min_ils']}: ₪{portfolio.commission_min_ils:g}\n"
        f"{t['commission_extra']}: {extra_label}"
    )
