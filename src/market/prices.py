from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime

import finnhub
import pytz
import yfinance as yf

from src.config import FINNHUB_API_KEY, PRICE_CACHE_SECONDS, TIMEZONE
from src.market.calendar import us_market_session

BENCHMARKS = {
    "US": ("SPY", "US", "S&P 500 (SPY)"),
    "IL": ("TA35.TA", "IL", "TA-35"),
}

_US_EASTERN = pytz.timezone("US/Eastern")


@dataclass
class Quote:
    symbol: str
    market: str
    price: float
    change_pct: float
    currency: str
    session: str = "regular"
    previous_close: float | None = None
    regular_market_price: float | None = None
    pre_market_price: float | None = None
    pre_market_change_pct: float | None = None
    after_hours_price: float | None = None
    after_hours_change_pct: float | None = None
    regular_daily_change_pct: float | None = None
    volume: float | None = None
    avg_volume: float | None = None


class PriceProvider:
    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, Quote]] = {}
        self._fx_cache: tuple[float, float] | None = None
        self._finnhub = finnhub.Client(api_key=FINNHUB_API_KEY) if FINNHUB_API_KEY else None

    def _cache_key(self, symbol: str, market: str) -> str:
        return f"{market}:{symbol.upper()}"

    def _is_fresh(self, key: str) -> bool:
        if key not in self._cache:
            return False
        ts, _ = self._cache[key]
        return (time.time() - ts) < PRICE_CACHE_SECONDS

    def yahoo_symbol(self, symbol: str, market: str) -> str:
        symbol = symbol.upper()
        if market == "IL":
            return symbol if symbol.endswith(".TA") else f"{symbol}.TA"
        return symbol

    async def get_usd_ils(self) -> float:
        if self._fx_cache and (time.time() - self._fx_cache[0]) < PRICE_CACHE_SECONDS:
            return self._fx_cache[1]
        ticker = yf.Ticker("USDILS=X")
        hist = ticker.history(period="1d")
        if hist.empty:
            rate = 3.7
        else:
            rate = float(hist["Close"].iloc[-1])
        self._fx_cache = (time.time(), rate)
        return rate

    async def get_benchmark(self, region: str) -> tuple[str, float | None]:
        symbol, market, name = BENCHMARKS[region]
        quote = await self.get_quote(symbol, market)
        if not quote:
            return name, None
        return name, quote.change_pct

    async def get_quote(self, symbol: str, market: str) -> Quote | None:
        key = self._cache_key(symbol, market)
        if self._is_fresh(key):
            return self._cache[key][1]

        symbol = symbol.upper()
        quote: Quote | None = None
        if market == "US" and self._finnhub:
            quote = self._fetch_finnhub(symbol)
        if not quote:
            quote = self._fetch_yfinance(symbol, market)
        if quote and market == "US":
            self._apply_us_extended_hours(quote)
        if quote:
            self._cache[key] = (time.time(), quote)
        return quote

    def _fetch_finnhub(self, symbol: str) -> Quote | None:
        try:
            data = self._finnhub.quote(symbol)
            if not data or data.get("c") in (None, 0):
                return None
            live = float(data["c"])
            return Quote(
                symbol=symbol,
                market="US",
                price=live,
                change_pct=0.0,
                currency="USD",
            )
        except Exception:
            return None

    def _daily_history(self, symbol: str, market: str = "US"):
        return yf.Ticker(self.yahoo_symbol(symbol, market)).history(
            period="10d",
            interval="1d",
            prepost=False,
            auto_adjust=True,
        )

    def _bar_date_et(self, ts) -> datetime.date:
        if ts.tzinfo is not None:
            return ts.tz_convert(_US_EASTERN).date()
        return ts.date()

    def _last_regular_close(self, symbol: str, market: str = "US") -> float | None:
        """Last completed regular-session close before today."""
        try:
            if market == "IL":
                tz = pytz.timezone(TIMEZONE)
            else:
                tz = _US_EASTERN
            today = datetime.now(tz).date()
            hist = self._daily_history(symbol, market)
            if hist.empty:
                return None
            for i in range(len(hist) - 1, -1, -1):
                bar_date = hist.index[i]
                if bar_date.tzinfo is not None:
                    bar_day = bar_date.tz_convert(tz).date()
                else:
                    bar_day = bar_date.date()
                if bar_day < today:
                    return float(hist["Close"].iloc[i])
            return None
        except Exception:
            return None

    def _today_regular_close(self, symbol: str) -> float | None:
        """Today's regular-session close, when the regular session has ended."""
        try:
            info = self._yfinance_info(symbol, "US")
            regular = info.get("regularMarketPrice")
            if regular:
                return float(regular)
            today = datetime.now(_US_EASTERN).date()
            hist = self._daily_history(symbol)
            if hist.empty:
                return None
            if self._bar_date_et(hist.index[-1]) == today:
                return float(hist["Close"].iloc[-1])
            return None
        except Exception:
            return None

    def _regular_session_daily_change(self, symbol: str) -> float | None:
        """Daily % change of the last regular close vs the prior session."""
        try:
            today = datetime.now(_US_EASTERN).date()
            hist = self._daily_history(symbol)
            closes: list[float] = []
            for i in range(len(hist) - 1, -1, -1):
                if self._bar_date_et(hist.index[i]) < today:
                    closes.append(float(hist["Close"].iloc[i]))
                    if len(closes) == 2:
                        break
            if len(closes) < 2:
                return None
            latest, prior = closes[0], closes[1]
            return (latest - prior) / prior * 100
        except Exception:
            return None

    def _resolve_pre_market_price(self, quote: Quote, info: dict) -> float | None:
        if info.get("preMarketPrice"):
            return float(info["preMarketPrice"])
        current = info.get("currentPrice")
        if current and quote.previous_close:
            price = float(current)
            if abs(price - quote.previous_close) > 0.001:
                return price
        if quote.pre_market_price and quote.previous_close:
            if abs(quote.pre_market_price - quote.previous_close) > 0.001:
                return quote.pre_market_price
        if quote.previous_close and abs(quote.price - quote.previous_close) > 0.001:
            return quote.price
        return quote.pre_market_price

    def _resolve_after_hours_price(self, quote: Quote, info: dict) -> float | None:
        if info.get("postMarketPrice"):
            return float(info["postMarketPrice"])
        current = info.get("currentPrice")
        if current:
            return float(current)
        if quote.after_hours_price:
            return quote.after_hours_price
        return quote.price

    def _yfinance_info(self, symbol: str, market: str) -> dict:
        try:
            return yf.Ticker(self.yahoo_symbol(symbol, market)).info or {}
        except Exception:
            return {}

    def _read_extended_from_info(self, quote: Quote, info: dict) -> None:
        regular = info.get("regularMarketPrice")
        pre = info.get("preMarketPrice")
        post = info.get("postMarketPrice")

        if regular:
            quote.regular_market_price = float(regular)
        if pre:
            quote.pre_market_price = float(pre)
            if info.get("preMarketChangePercent") is not None:
                quote.pre_market_change_pct = float(info["preMarketChangePercent"])
        if post:
            quote.after_hours_price = float(post)
            if info.get("postMarketChangePercent") is not None:
                quote.after_hours_change_pct = float(info["postMarketChangePercent"])

    def _apply_us_extended_hours(self, quote: Quote) -> None:
        info = self._yfinance_info(quote.symbol, "US")
        quote.previous_close = self._last_regular_close(quote.symbol, "US")
        quote.regular_daily_change_pct = self._regular_session_daily_change(quote.symbol)
        self._read_extended_from_info(quote, info)

        if not quote.regular_market_price:
            quote.regular_market_price = self._today_regular_close(quote.symbol)

        session = us_market_session()
        quote.session = session
        live = quote.price

        if session == "pre":
            pre = self._resolve_pre_market_price(quote, info)
            if pre is None:
                pre = live
            quote.pre_market_price = pre
            if quote.previous_close:
                quote.pre_market_change_pct = (
                    (pre - quote.previous_close) / quote.previous_close * 100
                )
            quote.price = pre
            quote.change_pct = quote.pre_market_change_pct or 0.0
            return

        if session == "post":
            post = self._resolve_after_hours_price(quote, info)
            if post is None:
                post = live
            quote.after_hours_price = post
            base = quote.regular_market_price or quote.previous_close
            if base:
                quote.after_hours_change_pct = (post - base) / base * 100
            quote.price = post
            quote.change_pct = quote.after_hours_change_pct or 0.0
            return

        if session == "regular":
            quote.regular_market_price = live
            quote.price = live
            if quote.previous_close:
                quote.change_pct = (live - quote.previous_close) / quote.previous_close * 100
            return

        # closed — show the most recent meaningful price
        if quote.after_hours_price:
            quote.price = quote.after_hours_price
            quote.change_pct = quote.after_hours_change_pct or quote.change_pct
        elif quote.regular_market_price:
            quote.price = quote.regular_market_price
            if quote.previous_close:
                quote.change_pct = (
                    (quote.regular_market_price - quote.previous_close) / quote.previous_close * 100
                )
        elif quote.pre_market_price:
            quote.price = quote.pre_market_price
            quote.change_pct = quote.pre_market_change_pct or quote.change_pct

        if quote.pre_market_price and quote.previous_close and quote.pre_market_change_pct is None:
            quote.pre_market_change_pct = (
                (quote.pre_market_price - quote.previous_close) / quote.previous_close * 100
            )
        if quote.after_hours_price and quote.after_hours_change_pct is None:
            base = quote.regular_market_price or quote.previous_close
            if base:
                quote.after_hours_change_pct = (
                    (quote.after_hours_price - base) / base * 100
                )

    def _fetch_yfinance(self, symbol: str, market: str) -> Quote | None:
        yahoo = self.yahoo_symbol(symbol, market)
        try:
            info = self._yfinance_info(symbol, market)
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            if price is None:
                hist = yf.Ticker(yahoo).history(period="5d", prepost=False)
                if hist.empty:
                    return None
                price = float(hist["Close"].iloc[-1])
            currency = "ILS" if market == "IL" else "USD"
            avg_vol = info.get("averageVolume") or info.get("averageVolume10days")
            quote = Quote(
                symbol=symbol.replace(".TA", ""),
                market=market,
                price=float(price),
                change_pct=0.0,
                currency=currency,
                volume=float(info.get("volume") or 0) or None,
                avg_volume=float(avg_vol) if avg_vol else None,
            )
            prev = info.get("regularMarketPreviousClose") or info.get("previousClose")
            if prev:
                quote.previous_close = float(prev)
            elif market == "IL":
                quote.previous_close = self._last_regular_close(symbol, market)
            if quote.previous_close and quote.price:
                quote.change_pct = (quote.price - quote.previous_close) / quote.previous_close * 100
            if market == "US":
                self._read_extended_from_info(quote, info)
            return quote
        except Exception:
            return None

    async def get_company_news(self, symbol: str, market: str) -> list[dict]:
        if not self._finnhub or market != "US":
            return []
        try:
            from datetime import date, timedelta

            today = date.today()
            week_ago = today - timedelta(days=7)
            return self._finnhub.company_news(
                symbol.upper(),
                _from=week_ago.isoformat(),
                to=today.isoformat(),
            )[:5]
        except Exception:
            return []
