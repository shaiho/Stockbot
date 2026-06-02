from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from aiogram.fsm.state import State
from aiogram.types import Message

from src.market.symbols import lookup_symbol


@dataclass(frozen=True)
class SymbolInputOutcome:
    kind: Literal["empty", "resolved", "ambiguous", "not_found"]
    symbol: str = ""
    market: str | None = None


async def resolve_symbol_message(
    message: Message,
    ctx,
    raw: str,
    *,
    holding_markets: list[str] | None = None,
) -> SymbolInputOutcome:
    text = raw.strip()
    if not text:
        return SymbolInputOutcome("empty")

    await message.bot.send_chat_action(message.chat.id, "typing")
    lookup = await lookup_symbol(ctx.prices, text, holding_markets=holding_markets)
    if lookup.resolved:
        return SymbolInputOutcome("resolved", symbol=lookup.symbol, market=lookup.market)
    if lookup.ambiguous:
        return SymbolInputOutcome("ambiguous", symbol=lookup.symbol)
    return SymbolInputOutcome("not_found", symbol=lookup.symbol)


async def prompt_ambiguous_symbol(
    message: Message,
    state,
    market_state: State,
    symbol: str,
    t: dict,
    lang: str,
) -> None:
    from src.bot.keyboards import market_keyboard

    await state.update_data(symbol=symbol)
    await state.set_state(market_state)
    await message.answer(t["symbol_ambiguous_market"], reply_markup=market_keyboard(lang))
