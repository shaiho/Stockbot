from __future__ import annotations

import json
from typing import Any

VALID_TRADE_ACTIONS = frozenset({"buy", "sell", "dividend"})


def _parse_market(raw: str | None) -> str:
    market = str(raw or "US").upper()
    return market if market in ("US", "IL") else "US"


def parse_portfolio_import(raw: str) -> dict[str, Any]:
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("invalid_root")

    cash = data.get("cash") or {}
    opening = data.get("opening_cash") or {}
    holdings = data.get("holdings") or []
    trades = data.get("trades") or []
    if not isinstance(cash, dict) or not isinstance(holdings, list) or not isinstance(trades, list):
        raise ValueError("invalid_structure")

    parsed_holdings = []
    for item in holdings:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol", "")).upper().strip()
        if not symbol:
            continue
        market = _parse_market(item.get("market"))
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

    parsed_trades = []
    for item in trades:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol", "")).upper().strip()
        if not symbol:
            continue
        action = str(item.get("action", "buy")).lower().strip()
        if action not in VALID_TRADE_ACTIONS:
            raise ValueError("invalid_action")
        market = _parse_market(item.get("market"))
        quantity = float(item.get("quantity", 0))
        price = float(item.get("price", 0))
        if action in ("buy", "sell") and quantity <= 0:
            raise ValueError("invalid_quantity")
        if action == "dividend":
            quantity = 1.0
        parsed_trades.append(
            {
                "symbol": symbol,
                "market": market,
                "asset_type": item.get("type", "stock"),
                "action": action,
                "quantity": quantity,
                "price": price,
                "currency": item.get("currency") or ("ILS" if market == "IL" else "USD"),
                "commission": float(item.get("commission", 0)),
                "date": item.get("date"),
                "note": item.get("note") or "import",
            }
        )

    has_opening = isinstance(opening, dict) and ("ILS" in opening or "USD" in opening)
    return {
        "cash_ils": float(cash.get("ILS", 0)),
        "cash_usd": float(cash.get("USD", 0)),
        "opening_cash_ils": float(opening.get("ILS", 0)) if has_opening else None,
        "opening_cash_usd": float(opening.get("USD", 0)) if has_opening else None,
        "holdings": parsed_holdings,
        "trades": parsed_trades,
        "replace": bool(data.get("replace", False)),
    }
