from __future__ import annotations

import json
from typing import Any

from src.db.models import Portfolio, Trade


def export_portfolio_json(
    portfolio: Portfolio,
    trades: list[Trade],
    cash_ils: float,
    cash_usd: float,
) -> str:
    stock_trades = [t for t in trades if t.asset_type != "cash"]
    data: dict[str, Any] = {
        "portfolio": portfolio.name,
        "cash": {"ILS": cash_ils, "USD": cash_usd},
        "opening_cash": {
            "ILS": portfolio.opening_cash_ils,
            "USD": portfolio.opening_cash_usd,
        },
        "trades": [
            {
                "symbol": t.symbol,
                "market": t.market,
                "action": t.action,
                "quantity": t.quantity,
                "price": t.price,
                "currency": t.currency,
                "commission": t.commission,
                "date": t.timestamp[:10] if t.timestamp else None,
                "note": t.note,
            }
            for t in stock_trades
        ],
    }
    return json.dumps(data, ensure_ascii=False, indent=2)
