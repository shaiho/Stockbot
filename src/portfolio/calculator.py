from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pytz

from src.config import TIMEZONE
from src.db.models import Holding, Trade
from src.market.prices import PriceProvider, Quote
from src.portfolio.daily_pnl import (
    _trade_date,
    calc_portfolio_daily_pnl,
    calc_symbol_daily_pnl,
    calc_symbol_daily_pnl_pct,
)


@dataclass
class StockPnL:
    symbol: str
    market: str
    currency: str
    quantity: float
    avg_cost: float
    current_price: float | None
    realized: float
    unrealized: float
    commissions_paid: float
    trade_count: int
    daily_pnl: float | None = None
    change_pct: float | None = None


@dataclass
class PortfolioSummary:
    total_ils: float
    total_usd: float
    fx_rate: float
    opening_capital_ils: float
    investments_pnl_ils: float
    total_pnl_ils: float
    total_pnl_pct: float
    daily_change_ils: float
    cash_ils: float
    cash_usd: float
    holdings: list[StockPnL]
    symbol_pnls: list[StockPnL]


@dataclass
class TaxReport:
    year: int
    gross_realized_ils: float
    commissions_ils: float
    taxable_ils: float
    tax_ils: float
    net_ils: float
    by_symbol: dict[str, float]


class PortfolioCalculator:
    def __init__(self, prices: PriceProvider) -> None:
        self.prices = prices

    async def _to_ils(self, amount: float, currency: str, fx: float) -> float:
        if currency == "ILS":
            return amount
        return amount * fx

    async def compute_symbol_pnl(
        self, trades: list[Trade], symbol: str, quote: Quote | None, *, today: str | None = None
    ) -> StockPnL:
        symbol = symbol.upper()
        qty = 0.0
        total_cost = 0.0
        realized = 0.0
        commissions = 0.0
        currency = "USD"
        market = "US"

        for trade in trades:
            if trade.symbol.upper() != symbol:
                continue
            currency = trade.currency
            market = trade.market
            commissions += trade.commission
            if trade.action == "buy":
                total_cost += trade.quantity * trade.price + trade.commission
                qty += trade.quantity
            elif trade.action == "sell" and qty > 0:
                avg = total_cost / qty
                realized += (trade.price - avg) * trade.quantity - trade.commission
                total_cost -= avg * trade.quantity
                qty -= trade.quantity
            elif trade.action == "dividend":
                realized += trade.quantity * trade.price - trade.commission

        avg_cost = total_cost / qty if qty > 0 else 0.0
        current = quote.price if quote else None
        unrealized = (current - avg_cost) * qty if current is not None and qty > 0 else 0.0

        tz = pytz.timezone(TIMEZONE)
        today = today or datetime.now(tz).date().isoformat()
        symbol_trades = [t for t in trades if t.symbol.upper() == symbol]
        daily_pnl = calc_symbol_daily_pnl(symbol_trades, quote, today=today) if quote else None
        daily_pct = (
            calc_symbol_daily_pnl_pct(daily_pnl, symbol_trades, quote, today)
            if daily_pnl is not None and quote
            else None
        )

        return StockPnL(
            symbol=symbol,
            market=market,
            currency=currency,
            quantity=qty,
            avg_cost=avg_cost,
            current_price=current,
            daily_pnl=daily_pnl,
            change_pct=daily_pct,
            realized=realized,
            unrealized=unrealized,
            commissions_paid=commissions,
            trade_count=len(symbol_trades),
        )

    def _trades_for_holding(
        self, holding: Holding, trades_by_symbol: dict[str, list[Trade]], trades: list[Trade]
    ) -> list[Trade]:
        symbol_trades = trades_by_symbol.get(holding.symbol)
        if symbol_trades:
            return symbol_trades
        return [
            t
            for t in trades
            if t.asset_type != "cash" and t.symbol.upper() == holding.symbol.upper()
        ]

    async def compute_summary(
        self,
        holdings: list[Holding],
        trades: list[Trade],
        cash_ils: float,
        cash_usd: float,
        opening_cash_ils: float = 0.0,
        opening_cash_usd: float = 0.0,
    ) -> PortfolioSummary:
        fx = await self.prices.get_usd_ils()
        stock_pnls: list[StockPnL] = []
        symbol_pnls: list[StockPnL] = []
        investments_pnl_ils = 0.0
        stock_value_usd = 0.0

        tz = pytz.timezone(TIMEZONE)
        today = datetime.now(tz).date().isoformat()

        trades_by_symbol: dict[str, list[Trade]] = {}
        for trade in trades:
            if trade.asset_type == "cash":
                continue
            trades_by_symbol.setdefault(trade.symbol.upper(), []).append(trade)

        quote_cache: dict[tuple[str, str], Quote | None] = {}

        async def get_cached_quote(symbol: str, market: str) -> Quote | None:
            key = (symbol, market)
            if key not in quote_cache:
                quote_cache[key] = await self.prices.get_quote(symbol, market)
            return quote_cache[key]

        for symbol in sorted(trades_by_symbol):
            symbol_trades = trades_by_symbol[symbol]
            market = symbol_trades[0].market
            holding = next((h for h in holdings if h.symbol.upper() == symbol), None)
            needs_quote = (holding and holding.quantity > 1e-9) or any(
                _trade_date(t) == today for t in symbol_trades if t.action in ("buy", "sell")
            )
            quote = await get_cached_quote(symbol, market) if needs_quote else None
            pnl = await self.compute_symbol_pnl(symbol_trades, symbol, quote, today=today)
            symbol_pnls.append(pnl)
            investments_pnl_ils += await self._to_ils(
                pnl.realized + pnl.unrealized, pnl.currency, fx
            )

        for holding in sorted(holdings, key=lambda h: h.symbol):
            if holding.quantity <= 1e-9:
                continue
            symbol = holding.symbol.upper()
            if any(p.symbol == symbol for p in stock_pnls):
                continue
            symbol_trades = self._trades_for_holding(holding, trades_by_symbol, trades)
            quote = await get_cached_quote(holding.symbol, holding.market)
            pnl = await self.compute_symbol_pnl(symbol_trades, holding.symbol, quote, today=today)
            if pnl.quantity <= 1e-9:
                pnl = StockPnL(
                    symbol=symbol,
                    market=holding.market,
                    currency=holding.currency,
                    quantity=holding.quantity,
                    avg_cost=holding.avg_cost,
                    current_price=pnl.current_price,
                    realized=pnl.realized,
                    unrealized=(
                        (pnl.current_price - holding.avg_cost) * holding.quantity
                        if pnl.current_price is not None
                        else 0.0
                    ),
                    commissions_paid=pnl.commissions_paid,
                    trade_count=pnl.trade_count,
                    daily_pnl=pnl.daily_pnl,
                    change_pct=pnl.change_pct,
                )
            stock_pnls.append(pnl)
            if quote:
                stock_value_usd += await self._to_usd(
                    holding.quantity * quote.price, holding.currency, fx
                )

        stock_pnls.sort(key=lambda p: p.symbol)

        daily_change_ils = await calc_portfolio_daily_pnl(
            trades,
            holdings,
            self.prices,
            opening_cash_ils=opening_cash_ils,
            opening_cash_usd=opening_cash_usd,
            cash_ils=cash_ils,
            cash_usd=cash_usd,
            fx=fx,
            today=today,
        )

        # Total portfolio value: all cash + all holdings (single conversion)
        total_ils = cash_ils + cash_usd * fx
        for holding in holdings:
            quote = await self.prices.get_quote(holding.symbol, holding.market)
            if quote:
                total_ils += await self._to_ils(
                    holding.quantity * quote.price, holding.currency, fx
                )

        net_deposits_ils = 0.0
        for trade in trades:
            if trade.asset_type != "cash":
                continue
            amount_ils = await self._to_ils(trade.quantity, trade.currency, fx)
            if trade.action == "deposit":
                net_deposits_ils += amount_ils
            elif trade.action == "withdraw":
                net_deposits_ils -= amount_ils

        opening_capital_ils = opening_cash_ils + opening_cash_usd * fx + net_deposits_ils
        total_pnl_ils = total_ils - opening_capital_ils
        total_pnl_pct = (
            (total_pnl_ils / opening_capital_ils * 100) if opening_capital_ils > 0 else 0.0
        )
        total_usd = total_ils / fx if fx else cash_usd + stock_value_usd

        return PortfolioSummary(
            total_ils=total_ils,
            total_usd=total_usd,
            fx_rate=fx,
            opening_capital_ils=opening_capital_ils,
            investments_pnl_ils=investments_pnl_ils,
            total_pnl_ils=total_pnl_ils,
            total_pnl_pct=total_pnl_pct,
            daily_change_ils=daily_change_ils,
            cash_ils=cash_ils,
            cash_usd=cash_usd,
            holdings=stock_pnls,
            symbol_pnls=symbol_pnls,
        )

    async def _to_usd(self, amount: float, currency: str, fx: float) -> float:
        if currency == "USD":
            return amount
        return amount / fx if fx else amount

    async def compute_tax_report(self, trades: list[Trade], year: int) -> TaxReport:
        fx = await self.prices.get_usd_ils()
        buckets: dict[str, dict] = {}
        total_commissions_ils = 0.0

        for trade in sorted(trades, key=lambda t: (t.timestamp, t.id)):
            if not trade.timestamp.startswith(str(year)):
                continue
            key = trade.symbol
            if key not in buckets:
                buckets[key] = {"qty": 0.0, "cost": 0.0, "realized": 0.0}
            bucket = buckets[key]
            commission_ils = await self._to_ils(trade.commission, trade.currency, fx)
            total_commissions_ils += commission_ils

            if trade.action == "buy":
                bucket["cost"] += trade.quantity * trade.price + trade.commission
                bucket["qty"] += trade.quantity
            elif trade.action == "sell" and bucket["qty"] > 0:
                avg = bucket["cost"] / bucket["qty"]
                pnl = (trade.price - avg) * trade.quantity - trade.commission
                bucket["realized"] += await self._to_ils(pnl, trade.currency, fx)
                bucket["cost"] -= avg * trade.quantity
                bucket["qty"] -= trade.quantity
            elif trade.action == "dividend":
                div = trade.quantity * trade.price - trade.commission
                bucket["realized"] += await self._to_ils(div, trade.currency, fx)

        by_symbol = {sym: data["realized"] for sym, data in buckets.items() if data["realized"] != 0}
        gross = sum(by_symbol.values())
        taxable = gross - total_commissions_ils
        tax = max(taxable, 0) * 0.25
        return TaxReport(
            year=year,
            gross_realized_ils=gross,
            commissions_ils=total_commissions_ils,
            taxable_ils=taxable,
            tax_ils=tax,
            net_ils=taxable - tax,
            by_symbol=by_symbol,
        )
