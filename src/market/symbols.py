from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

from src.market.prices import PriceProvider


@dataclass(frozen=True)
class SymbolLookupResult:
    symbol: str
    market: str | None = None
    candidate_markets: tuple[str, ...] = ()

    @property
    def resolved(self) -> bool:
        return self.market is not None

    @property
    def ambiguous(self) -> bool:
        return self.market is None and len(self.candidate_markets) > 1


def normalize_symbol(raw: str) -> str:
    symbol = raw.strip().upper()
    if symbol.endswith(".TA"):
        return symbol[:-3]
    return symbol


def infer_market_hint(raw: str) -> str | None:
    symbol = raw.strip().upper()
    if symbol.endswith(".TA"):
        return "IL"
    if re.fullmatch(r"\d+", symbol):
        return "IL"
    return None


async def lookup_symbol(
    prices: PriceProvider,
    raw: str,
    *,
    holding_markets: list[str] | None = None,
) -> SymbolLookupResult:
    symbol = normalize_symbol(raw)
    if not symbol:
        return SymbolLookupResult(symbol=symbol)

    if holding_markets:
        unique = sorted({m for m in holding_markets if m in ("US", "IL")})
        if len(unique) == 1:
            return SymbolLookupResult(symbol=symbol, market=unique[0])
        if len(unique) > 1:
            return SymbolLookupResult(symbol=symbol, candidate_markets=tuple(unique))

    hint = infer_market_hint(raw)
    if hint:
        quote = await prices.get_quote(symbol, hint)
        if quote:
            return SymbolLookupResult(symbol=symbol, market=hint)

    us_quote, il_quote = await asyncio.gather(
        prices.get_quote(symbol, "US"),
        prices.get_quote(symbol, "IL"),
    )
    us_ok = us_quote is not None
    il_ok = il_quote is not None

    if us_ok and il_ok:
        return SymbolLookupResult(symbol=symbol, candidate_markets=("US", "IL"))
    if us_ok:
        return SymbolLookupResult(symbol=symbol, market="US")
    if il_ok:
        return SymbolLookupResult(symbol=symbol, market="IL")
    return SymbolLookupResult(symbol=symbol)
