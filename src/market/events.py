from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

import finnhub.exceptions
import pytz

from src.config import TIMEZONE
from src.market.event_classifier import classify_headline
from src.market.holidays import is_exchange_holiday, upcoming_holidays
from src.market.prices import PriceProvider

logger = logging.getLogger(__name__)

EVENT_SPLIT = "split"
EVENT_REVERSE_SPLIT = "reverse_split"
EVENT_DIVIDEND = "dividend"
EVENT_EARNINGS = "earnings"
EVENT_EARNINGS_SURPRISE = "earnings_surprise"
EVENT_ANALYST = "analyst_rating"
EVENT_IPO = "ipo"
EVENT_INDEX = "index_change"
EVENT_MERGER = "merger"
EVENT_SPINOFF = "spinoff"
EVENT_TICKER_CHANGE = "ticker_change"
EVENT_OFFERING = "offering"
EVENT_HALT = "halt"
EVENT_CIRCUIT_BREAKER = "circuit_breaker"
EVENT_DELISTING = "delisting"
EVENT_MARKET_HOLIDAY = "market_holiday"

LOOKAHEAD_DAYS = 7
LOOKBACK_DAYS = 2


@dataclass(frozen=True)
class MarketEvent:
    event_type: str
    symbol: str
    market: str
    event_key: str
    title: str
    body: str
    event_date: str
    meta: dict[str, Any] = field(default_factory=dict)


class MarketEventsProvider:
    def __init__(self, prices: PriceProvider) -> None:
        self._prices = prices
        self._finnhub_denied: set[str] = set()

    @property
    def available(self) -> bool:
        return self._prices._finnhub is not None

    async def _call(self, fn, *args, **kwargs):
        name = getattr(fn, "__name__", "finnhub")
        if name in self._finnhub_denied:
            return None
        await self._prices._rate_limiter.acquire()
        try:
            return await asyncio.to_thread(fn, *args, **kwargs)
        except finnhub.exceptions.FinnhubAPIException as exc:
            if exc.status_code == 403:
                self._finnhub_denied.add(name)
                logger.warning(
                    "Finnhub denied %s (403) — not available on current plan; skipping",
                    name,
                )
                return None
            logger.warning("Finnhub %s failed: %s", name, exc)
            return None
        except Exception:
            logger.exception("Finnhub %s failed", name)
            return None

    async def scan_symbol(self, symbol: str, market: str, today: date) -> list[MarketEvent]:
        if market != "US" or not self.available:
            return await self._scan_il_symbol(symbol, today)
        events: list[MarketEvent] = []
        sym = symbol.upper()
        events.extend(await self._scan_splits(sym, market, today))
        events.extend(await self._scan_dividends(sym, market, today))
        events.extend(await self._scan_earnings(sym, market, today))
        events.extend(await self._scan_analyst(sym, market, today))
        events.extend(await self._scan_news_events(sym, market, today))
        return events

    async def _scan_il_symbol(self, symbol: str, today: date) -> list[MarketEvent]:
        events: list[MarketEvent] = []
        headlines: list[str] = []
        try:
            import yfinance as yf

            yahoo = f"{symbol.upper()}.TA" if not symbol.upper().endswith(".TA") else symbol.upper()
            for item in (yf.Ticker(yahoo).news or [])[:8]:
                title = item.get("title") or item.get("headline") or ""
                if title:
                    headlines.append(title)
        except Exception:
            logger.debug("IL news unavailable for %s", symbol, exc_info=True)
        for headline in headlines:
            classified = classify_headline(headline)
            if not classified:
                continue
            ts = today.isoformat()
            events.append(
                MarketEvent(
                    event_type=classified.event_type,
                    symbol=symbol.upper(),
                    market="IL",
                    event_key=f"news:{classified.event_type}:{symbol.upper()}:{headline[:48]}:{ts}",
                    title=headline,
                    body=headline,
                    event_date=ts,
                )
            )
        return events

    async def _scan_splits(self, symbol: str, market: str, today: date) -> list[MarketEvent]:
        client = self._prices._finnhub
        assert client is not None
        start = (today - timedelta(days=LOOKBACK_DAYS)).isoformat()
        end = (today + timedelta(days=LOOKAHEAD_DAYS)).isoformat()
        rows = await self._call(client.stock_splits, symbol, _from=start, to=end)
        events: list[MarketEvent] = []
        for row in rows or []:
            event_date = str(row.get("date", today.isoformat()))[:10]
            from_factor = float(row.get("fromFactor") or 1)
            to_factor = float(row.get("toFactor") or 1)
            if from_factor <= 0 or to_factor <= 0:
                continue
            ratio = to_factor / from_factor
            if ratio > 1:
                event_type = EVENT_SPLIT
                label = f"{from_factor:g}:{to_factor:g} split"
            else:
                event_type = EVENT_REVERSE_SPLIT
                label = f"{to_factor:g}:{from_factor:g} reverse split"
            events.append(
                MarketEvent(
                    event_type=event_type,
                    symbol=symbol,
                    market=market,
                    event_key=f"{event_type}:{symbol}:{event_date}:{from_factor}:{to_factor}",
                    title=label,
                    body=label,
                    event_date=event_date,
                    meta={"from_factor": from_factor, "to_factor": to_factor},
                )
            )
        return events

    async def _scan_dividends(self, symbol: str, market: str, today: date) -> list[MarketEvent]:
        client = self._prices._finnhub
        assert client is not None
        start = (today - timedelta(days=1)).isoformat()
        end = (today + timedelta(days=LOOKAHEAD_DAYS)).isoformat()
        rows = await self._call(client.stock_dividends, symbol, _from=start, to=end)
        events: list[MarketEvent] = []
        for row in rows or []:
            ex_date = str(row.get("exDate") or row.get("date") or "")[:10]
            if not ex_date:
                continue
            amount = row.get("amount")
            pay_date = str(row.get("payDate") or "")[:10]
            body = f"ex-date {ex_date}"
            if amount is not None:
                body += f", ${float(amount):.4f}"
            if pay_date:
                body += f", pay {pay_date}"
            events.append(
                MarketEvent(
                    event_type=EVENT_DIVIDEND,
                    symbol=symbol,
                    market=market,
                    event_key=f"div:{symbol}:{ex_date}:{amount}",
                    title=f"Dividend ex-date {ex_date}",
                    body=body,
                    event_date=ex_date,
                    meta={"amount": amount, "pay_date": pay_date},
                )
            )
        return events

    async def _scan_earnings(self, symbol: str, market: str, today: date) -> list[MarketEvent]:
        client = self._prices._finnhub
        assert client is not None
        events: list[MarketEvent] = []
        start = today.isoformat()
        end = (today + timedelta(days=LOOKAHEAD_DAYS)).isoformat()
        cal = await self._call(
            client.earnings_calendar,
            _from=start,
            to=end,
            symbol=symbol,
            international=False,
        )
        for row in (cal or {}).get("earningsCalendar", []) or []:
            event_date = str(row.get("date", ""))[:10]
            hour = row.get("hour") or ""
            eps_est = row.get("epsEstimate")
            body = f"Earnings {event_date}"
            if hour:
                body += f" ({hour})"
            if eps_est is not None:
                body += f", est EPS {eps_est}"
            events.append(
                MarketEvent(
                    event_type=EVENT_EARNINGS,
                    symbol=symbol,
                    market=market,
                    event_key=f"earn:{symbol}:{event_date}:{hour}",
                    title=f"Earnings {event_date}",
                    body=body,
                    event_date=event_date,
                    meta={"hour": hour, "eps_estimate": eps_est},
                )
            )

        surprises = await self._call(client.company_earnings, symbol, limit=1)
        for row in surprises or []:
            period = str(row.get("period", ""))[:10]
            if not period:
                continue
            try:
                period_date = datetime.strptime(period, "%Y-%m-%d").date()
            except ValueError:
                continue
            if (today - period_date).days > 45:
                continue
            actual = row.get("actual")
            estimate = row.get("estimate")
            surprise_pct = row.get("surprisePercent")
            if actual is None or estimate is None:
                continue
            body = f"EPS actual {actual} vs est {estimate}"
            if surprise_pct is not None:
                body += f" ({float(surprise_pct):+.1f}%)"
            events.append(
                MarketEvent(
                    event_type=EVENT_EARNINGS_SURPRISE,
                    symbol=symbol,
                    market=market,
                    event_key=f"surprise:{symbol}:{period}:{actual}:{estimate}",
                    title=f"Earnings surprise {period}",
                    body=body,
                    event_date=today.isoformat(),
                    meta={"actual": actual, "estimate": estimate, "surprise_pct": surprise_pct},
                )
            )
        return events

    async def _scan_analyst(self, symbol: str, market: str, today: date) -> list[MarketEvent]:
        client = self._prices._finnhub
        assert client is not None
        start = (today - timedelta(days=LOOKBACK_DAYS)).isoformat()
        end = today.isoformat()
        events: list[MarketEvent] = []
        rows = await self._call(client.upgrade_downgrade, symbol=symbol, _from=start, to=end)
        for row in rows or []:
            action = row.get("action") or row.get("grade") or "update"
            firm = row.get("company") or row.get("firm") or ""
            grade_from = row.get("fromGrade") or ""
            grade_to = row.get("toGrade") or ""
            event_date = str(row.get("date") or today.isoformat())[:10]
            body = f"{action}: {grade_from} → {grade_to}".strip(" :→")
            if firm:
                body = f"{firm}: {body}"
            events.append(
                MarketEvent(
                    event_type=EVENT_ANALYST,
                    symbol=symbol,
                    market=market,
                    event_key=f"analyst:{symbol}:{event_date}:{action}:{grade_to}:{firm}",
                    title=f"Analyst {action}",
                    body=body,
                    event_date=event_date,
                )
            )
        return events

    async def _scan_news_events(self, symbol: str, market: str, today: date) -> list[MarketEvent]:
        events: list[MarketEvent] = []
        news = await self._prices.get_company_news(symbol, market)
        for item in news[:8]:
            headline = item.get("headline", "")
            classified = classify_headline(headline)
            if not classified:
                continue
            ts = str(item.get("datetime", ""))[:10] or today.isoformat()
            events.append(
                MarketEvent(
                    event_type=classified.event_type,
                    symbol=symbol,
                    market=market,
                    event_key=f"news:{classified.event_type}:{symbol}:{headline[:48]}:{ts}",
                    title=headline,
                    body=headline,
                    event_date=ts,
                )
            )
        return events

    async def scan_ipo_calendar(self, symbols: set[str], today: date) -> list[MarketEvent]:
        if not self.available or not symbols:
            return []
        client = self._prices._finnhub
        assert client is not None
        start = today.isoformat()
        end = (today + timedelta(days=LOOKAHEAD_DAYS)).isoformat()
        cal = await self._call(client.ipo_calendar, _from=start, to=end)
        if not cal:
            return []
        events: list[MarketEvent] = []
        for row in cal.get("ipoCalendar", []) or []:
            sym = str(row.get("symbol") or "").upper()
            if sym not in symbols:
                continue
            event_date = str(row.get("date") or today.isoformat())[:10]
            name = row.get("name") or sym
            price = row.get("price")
            body = name
            if price:
                body += f" @ {price}"
            events.append(
                MarketEvent(
                    event_type=EVENT_IPO,
                    symbol=sym,
                    market="US",
                    event_key=f"ipo:{sym}:{event_date}",
                    title=f"IPO {event_date}",
                    body=body,
                    event_date=event_date,
                )
            )
        return events

    async def scan_index_history(self, symbols: set[str], today: date) -> list[MarketEvent]:
        if not self.available or not symbols:
            return []
        client = self._prices._finnhub
        assert client is not None
        start = (today - timedelta(days=LOOKBACK_DAYS)).isoformat()
        end = today.isoformat()
        events: list[MarketEvent] = []
        data = await self._call(client.indices_hist_const, symbol="^GSPC", _from=start, to=end)
        if not data:
            return []
        for row in data.get("data", []) or []:
            action = str(row.get("action") or "").lower()
            sym = str(row.get("symbol") or "").upper()
            if sym not in symbols or action not in {"added", "removed", "add", "remove"}:
                continue
            event_date = str(row.get("date") or today.isoformat())[:10]
            if action in {"added", "add"}:
                title = "Added to S&P 500"
            else:
                title = "Removed from S&P 500"
            events.append(
                MarketEvent(
                    event_type=EVENT_INDEX,
                    symbol=sym,
                    market="US",
                    event_key=f"index:{action}:{sym}:{event_date}",
                    title=title,
                    body=title,
                    event_date=event_date,
                )
            )
        return events

    def scan_holiday_reminders(self, market: str, today: date) -> list[MarketEvent]:
        events: list[MarketEvent] = []
        for holiday_date, iso in upcoming_holidays(market, days=1):
            if holiday_date <= today:
                continue
            label = "US market" if market == "US" else "TASE"
            events.append(
                MarketEvent(
                    event_type=EVENT_MARKET_HOLIDAY,
                    symbol="",
                    market=market,
                    event_key=f"holiday:{market}:{iso}",
                    title=f"{label} closed {iso}",
                    body=f"{label} holiday on {iso}",
                    event_date=iso,
                )
            )
        return events

    def format_event(self, event: MarketEvent, t: dict) -> str:
        labels = {
            EVENT_SPLIT: t.get("event_split", "Split"),
            EVENT_REVERSE_SPLIT: t.get("event_reverse_split", "Reverse split"),
            EVENT_DIVIDEND: t.get("event_dividend", "Dividend"),
            EVENT_EARNINGS: t.get("event_earnings", "Earnings"),
            EVENT_EARNINGS_SURPRISE: t.get("event_earnings_surprise", "Earnings surprise"),
            EVENT_ANALYST: t.get("event_analyst", "Analyst rating"),
            EVENT_IPO: t.get("event_ipo", "IPO"),
            EVENT_INDEX: t.get("event_index", "Index change"),
            EVENT_MERGER: t.get("event_merger", "M&A"),
            EVENT_SPINOFF: t.get("event_spinoff", "Spin-off"),
            EVENT_TICKER_CHANGE: t.get("event_ticker_change", "Ticker change"),
            EVENT_OFFERING: t.get("event_offering", "Offering"),
            EVENT_HALT: t.get("event_halt", "Trading halt"),
            EVENT_CIRCUIT_BREAKER: t.get("event_circuit_breaker", "Circuit breaker"),
            EVENT_DELISTING: t.get("event_delisting", "Delisting"),
            EVENT_MARKET_HOLIDAY: t.get("event_market_holiday", "Market holiday"),
        }
        kind = labels.get(event.event_type, event.event_type)
        prefix = f"📌 {kind}"
        if event.symbol:
            prefix += f" · {event.symbol}"
        if event.market:
            prefix += f" ({event.market})"
        return f"{prefix}\n{event.body}"
