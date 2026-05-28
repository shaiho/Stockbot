from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pytz

from src.config import TIMEZONE
from src.db.models import Holding, Trade
from src.market.prices import PriceProvider, Quote

PositionKey = tuple[str, str, str]


@dataclass
class _PortfolioState:
    cash_ils: float
    cash_usd: float
    positions: dict[PositionKey, float] = field(default_factory=dict)


def _trade_date(trade: Trade) -> str:
    return trade.timestamp[:10]


def _to_ils(amount: float, currency: str, fx: float) -> float:
    if currency == "ILS":
        return amount
    return amount * fx


def _apply_trade(state: _PortfolioState, trade: Trade) -> None:
    if trade.asset_type == "cash":
        if trade.action == "deposit":
            if trade.currency == "ILS":
                state.cash_ils += trade.quantity
            else:
                state.cash_usd += trade.quantity
        elif trade.action == "withdraw":
            if trade.currency == "ILS":
                state.cash_ils -= trade.quantity
            else:
                state.cash_usd -= trade.quantity
        return

    key: PositionKey = (trade.symbol.upper(), trade.market, trade.currency)
    gross = trade.quantity * trade.price
    if trade.action == "buy":
        total = gross + trade.commission
        if trade.currency == "ILS":
            state.cash_ils -= total
        else:
            state.cash_usd -= total
        state.positions[key] = state.positions.get(key, 0.0) + trade.quantity
    elif trade.action == "sell":
        proceeds = gross - trade.commission
        if trade.currency == "ILS":
            state.cash_ils += proceeds
        else:
            state.cash_usd += proceeds
        state.positions[key] = max(state.positions.get(key, 0.0) - trade.quantity, 0.0)
        if state.positions[key] <= 1e-9:
            state.positions.pop(key, None)
    elif trade.action == "dividend":
        proceeds = gross - trade.commission
        if trade.currency == "ILS":
            state.cash_ils += proceeds
        else:
            state.cash_usd += proceeds


def _portfolio_state_at(
    trades: list[Trade],
    opening_cash_ils: float,
    opening_cash_usd: float,
    before_date: str,
) -> _PortfolioState:
    state = _PortfolioState(opening_cash_ils, opening_cash_usd)
    for trade in sorted(trades, key=lambda t: (t.timestamp, t.id)):
        if _trade_date(trade) >= before_date:
            break
        _apply_trade(state, trade)
    return state


def _external_cash_flow_ils(trades: list[Trade], today: str, fx: float) -> float:
    flow = 0.0
    for trade in trades:
        if trade.asset_type != "cash" or _trade_date(trade) != today:
            continue
        amount = _to_ils(trade.quantity, trade.currency, fx)
        if trade.action == "deposit":
            flow += amount
        elif trade.action == "withdraw":
            flow -= amount
    return flow


def _position_at_date(trades: list[Trade], before_date: str) -> tuple[float, float]:
    qty = 0.0
    cost = 0.0
    for trade in sorted(trades, key=lambda t: (t.timestamp, t.id)):
        if trade.action not in ("buy", "sell"):
            continue
        if _trade_date(trade) >= before_date:
            break
        if trade.action == "buy":
            qty += trade.quantity
            cost += trade.quantity * trade.price
        elif trade.action == "sell" and qty > 0:
            avg = cost / qty
            cost -= avg * trade.quantity
            qty -= trade.quantity
    return qty, cost


def calc_symbol_daily_pnl(
    trades: list[Trade],
    quote: Quote | None,
    *,
    today: str | None = None,
) -> float | None:
    """Position-aware daily P&L for one symbol via today's trade events."""
    if not quote or quote.previous_close is None:
        return None

    tz = pytz.timezone(TIMEZONE)
    today = today or datetime.now(tz).date().isoformat()
    prev_close = quote.previous_close
    current = quote.price

    stock_trades = [
        t
        for t in trades
        if t.action in ("buy", "sell") and _trade_date(t) <= today
    ]
    if not stock_trades:
        return None

    today_trades = [t for t in stock_trades if _trade_date(t) == today]
    qty_open, cost_open = _position_at_date(stock_trades, today)
    if not today_trades and qty_open <= 1e-9:
        return None

    qty_total = qty_open
    cost_total = cost_open
    qty_bought_today = 0.0
    cost_bought_today = 0.0
    daily_pnl = 0.0

    for trade in sorted(today_trades, key=lambda t: (t.timestamp, t.id)):
        if trade.action == "buy":
            qty_total += trade.quantity
            cost_total += trade.quantity * trade.price
            qty_bought_today += trade.quantity
            cost_bought_today += trade.quantity * trade.price
        elif trade.action == "sell" and qty_total > 0:
            sell_qty = min(trade.quantity, qty_total)
            sell_from_overnight = min(sell_qty, max(qty_total - qty_bought_today, 0.0))
            sell_from_today = sell_qty - sell_from_overnight

            daily_pnl += sell_from_overnight * (trade.price - prev_close)
            if sell_from_today > 0 and qty_bought_today > 0:
                avg_today = cost_bought_today / qty_bought_today
                daily_pnl += sell_from_today * (trade.price - avg_today)

            avg = cost_total / qty_total
            cost_total -= avg * sell_qty
            qty_total -= sell_qty
            if sell_from_today > 0 and qty_bought_today > 0:
                avg_today = cost_bought_today / qty_bought_today
                cost_bought_today -= avg_today * sell_from_today
                qty_bought_today -= sell_from_today

    qty_overnight_end = max(qty_total - qty_bought_today, 0.0)
    daily_pnl += qty_overnight_end * (current - prev_close)
    if qty_bought_today > 0:
        avg_today = cost_bought_today / qty_bought_today
        daily_pnl += qty_bought_today * (current - avg_today)

    return daily_pnl


def calc_symbol_daily_pnl_pct(
    daily_pnl: float, trades: list[Trade], quote: Quote, today: str
) -> float | None:
    if quote.previous_close is None:
        return None
    qty_open, _ = _position_at_date(trades, today)
    basis = qty_open * quote.previous_close
    for trade in sorted(trades, key=lambda t: (t.timestamp, t.id)):
        if _trade_date(trade) == today and trade.action == "buy":
            basis += trade.quantity * trade.price
    if basis <= 0:
        return None
    return daily_pnl / basis * 100


async def calc_portfolio_daily_pnl(
    trades: list[Trade],
    holdings: list[Holding],
    prices: PriceProvider,
    *,
    opening_cash_ils: float,
    opening_cash_usd: float,
    cash_ils: float,
    cash_usd: float,
    fx: float,
    today: str | None = None,
) -> float:
    """Daily P&L from start-of-day ledger state through all intraday events.

    end_value - start_value - external_cash_flows_today

    Start-of-day stocks are valued at previous close; end stocks at current price.
    Buys/sells/dividends today are captured via cash + holdings, including closed
    round-trips that leave no open position.
    """
    tz = pytz.timezone(TIMEZONE)
    today = today or datetime.now(tz).date().isoformat()

    start = _portfolio_state_at(trades, opening_cash_ils, opening_cash_usd, today)
    start_value = start.cash_ils + start.cash_usd * fx

    quote_cache: dict[tuple[str, str], Quote | None] = {}
    for (symbol, market, currency), qty in start.positions.items():
        if qty <= 1e-9:
            continue
        cache_key = (symbol, market)
        if cache_key not in quote_cache:
            quote_cache[cache_key] = await prices.get_quote(symbol, market)
        quote = quote_cache[cache_key]
        if not quote or quote.previous_close is None:
            continue
        start_value += _to_ils(qty * quote.previous_close, currency, fx)

    end_value = cash_ils + cash_usd * fx
    for holding in holdings:
        cache_key = (holding.symbol, holding.market)
        if cache_key not in quote_cache:
            quote_cache[cache_key] = await prices.get_quote(holding.symbol, holding.market)
        quote = quote_cache[cache_key]
        if not quote:
            continue
        end_value += _to_ils(holding.quantity * quote.price, holding.currency, fx)

    external_flow = _external_cash_flow_ils(trades, today, fx)
    return end_value - start_value - external_flow
