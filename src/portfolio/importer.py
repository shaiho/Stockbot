from __future__ import annotations

import json
from typing import Any


def parse_portfolio_import(raw: str) -> dict[str, Any]:
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("invalid_root")

    cash = data.get("cash") or {}
    holdings = data.get("holdings") or []
    if not isinstance(cash, dict) or not isinstance(holdings, list):
        raise ValueError("invalid_structure")

    parsed_holdings = []
    for item in holdings:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol", "")).upper().strip()
        if not symbol:
            continue
        market = str(item.get("market", "US")).upper()
        if market not in ("US", "IL"):
            market = "US"
        parsed_holdings.append(
            {
                "symbol": symbol,
                "market": market,
                "asset_type": item.get("type", "stock"),
                "quantity": float(item.get("quantity", 0)),
                "avg_cost": float(item.get("avg_cost", item.get("price", 0))),
                "currency": item.get("currency") or ("ILS" if market == "IL" else "USD"),
                "date": item.get("date"),
            }
        )

    return {
        "cash_ils": float(cash.get("ILS", 0)),
        "cash_usd": float(cash.get("USD", 0)),
        "holdings": parsed_holdings,
    }
