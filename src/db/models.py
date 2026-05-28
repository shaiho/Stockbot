from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class User:
    telegram_id: int
    language: str = "he"
    onboarding_completed: bool = False
    default_commission: float = 0.0
    default_commission_currency: str = "USD"
    report_morning: str = "09:00"
    report_evening: str = "23:00"
    mover_threshold_pct: float = 5.0
    last_portfolio_id: int | None = None


@dataclass
class Portfolio:
    id: int
    user_id: int
    name: str
    opening_cash_ils: float = 0.0
    opening_cash_usd: float = 0.0
    commission_min_usd: float = 0.0
    commission_min_ils: float = 0.0
    commission_extra_type: str = "fixed"
    commission_extra_value: float = 0.0
    opened_at: str = ""


@dataclass
class Trade:
    id: int
    portfolio_id: int
    symbol: str
    market: str
    asset_type: str
    action: str
    quantity: float
    price: float
    currency: str
    commission: float
    timestamp: str
    note: str | None = None


@dataclass
class Holding:
    symbol: str
    market: str
    asset_type: str
    quantity: float
    avg_cost: float
    currency: str
    trade_count: int


@dataclass
class WatchlistItem:
    id: int
    user_id: int
    symbol: str
    market: str
    added_at: str


@dataclass
class AlertRule:
    id: int
    user_id: int
    scope: str
    alert_type: str
    config: dict[str, Any]
    enabled: bool = True
