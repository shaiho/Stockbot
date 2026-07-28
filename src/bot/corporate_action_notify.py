from __future__ import annotations

import asyncio
from datetime import date, timedelta

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from src.db.models import Holding, Portfolio
from src.db.repository import Repository
from src.market.events import EVENT_DIVIDEND, EVENT_REVERSE_SPLIT, EVENT_SPLIT, MarketEvent
from src.market.splits import SPLIT_LOOKBACK_DAYS, fetch_yfinance_splits, split_already_applied
from src.portfolio.corporate_actions import format_split_label


def build_split_message(
    event: MarketEvent,
    holdings: list[tuple[Portfolio, Holding]],
    t: dict,
    lang: str,
) -> tuple[str, InlineKeyboardMarkup | None]:
    from_f = float(event.meta.get("from_factor", 1))
    to_f = float(event.meta.get("to_factor", 1))
    label = format_split_label(from_f, to_f)
    kind = t["event_reverse_split"] if event.event_type == EVENT_REVERSE_SPLIT else t["event_split"]
    lines = [f"📌 {kind} · {event.symbol} ({event.market})", label, ""]
    rows: list[list[InlineKeyboardButton]] = []
    apply_label = "✅ החל" if lang == "he" else "✅ Apply"
    skip_label = "⏭ דלג" if lang == "he" else "⏭ Skip"

    for portfolio, holding in holdings:
        lines.append(
            t["event_split_portfolio_line"].format(
                portfolio=portfolio.name,
                quantity=holding.quantity,
            )
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{apply_label} · {portfolio.name}",
                    callback_data=f"ca:split:{portfolio.id}:{event.symbol}:{from_f:g}:{to_f:g}",
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text=skip_label,
                callback_data=(
                    f"ca:skip:split:{event.symbol}:{event.event_date}:{from_f:g}:{to_f:g}"
                ),
            )
        ]
    )
    lines.append("")
    lines.append(t["event_split_apply_hint"])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


def build_dividend_message(
    event: MarketEvent,
    holdings: list[tuple[Portfolio, Holding]],
    t: dict,
    lang: str,
) -> tuple[str, InlineKeyboardMarkup | None]:
    amount = event.meta.get("amount")
    ex_date = event.event_date
    if amount is None:
        return event.body, None

    amount_f = float(amount)
    lines = [
        f"📌 {t['event_dividend']} · {event.symbol} ({event.market})",
        t["event_dividend_ex_date"].format(date=ex_date, amount=amount_f),
        "",
    ]
    rows: list[list[InlineKeyboardButton]] = []
    record_label = "💵 רשום" if lang == "he" else "💵 Record"
    skip_label = "⏭ דלג" if lang == "he" else "⏭ Skip"

    for portfolio, holding in holdings:
        total = amount_f * holding.quantity
        currency = "₪" if holding.currency == "ILS" else "$"
        lines.append(
            t["event_dividend_portfolio_line"].format(
                portfolio=portfolio.name,
                shares=holding.quantity,
                total=f"{currency}{total:,.2f}",
            )
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{record_label} · {portfolio.name}",
                    callback_data=f"ca:div:{portfolio.id}:{event.symbol}:{amount_f:g}:{ex_date}",
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text=skip_label,
                callback_data=f"ca:skip:div:{event.symbol}:{ex_date}:{amount_f:g}",
            )
        ]
    )
    lines.append("")
    lines.append(t["event_dividend_apply_hint"])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


def is_actionable_event(event: MarketEvent) -> bool:
    return event.event_type in (EVENT_SPLIT, EVENT_REVERSE_SPLIT, EVENT_DIVIDEND)


def _split_event_from_row(symbol: str, market: str, row: dict) -> MarketEvent:
    from_factor = float(row.get("fromFactor") or 1)
    to_factor = float(row.get("toFactor") or 1)
    event_date = str(row.get("date", ""))[:10]
    ratio = to_factor / from_factor if from_factor else 1.0
    if ratio > 1:
        event_type = EVENT_SPLIT
        label = f"{from_factor:g}:{to_factor:g} split"
    else:
        event_type = EVENT_REVERSE_SPLIT
        label = f"{to_factor:g}:{from_factor:g} reverse split"
    return MarketEvent(
        event_type=event_type,
        symbol=symbol.upper(),
        market=market,
        event_key=f"{event_type}:{symbol.upper()}:{event_date}:{from_factor}:{to_factor}",
        title=label,
        body=label,
        event_date=event_date,
        meta={"from_factor": from_factor, "to_factor": to_factor},
    )


async def find_pending_split_events(
    repo: Repository,
    portfolio: Portfolio,
    today: date,
) -> list[tuple[MarketEvent, Holding]]:
    pending: list[tuple[MarketEvent, Holding]] = []
    start = today - timedelta(days=SPLIT_LOOKBACK_DAYS)
    holdings = await repo.get_holdings(portfolio.id)
    for holding in holdings:
        if holding.quantity <= 1e-9:
            continue
        rows = await asyncio.to_thread(
            fetch_yfinance_splits,
            holding.symbol,
            holding.market,
            start,
            today,
        )
        for row in rows:
            event = _split_event_from_row(holding.symbol, holding.market, row)
            from_f = float(event.meta.get("from_factor", 1))
            to_f = float(event.meta.get("to_factor", 1))
            if await split_already_applied(repo, portfolio.id, holding.symbol, from_f, to_f):
                continue
            pending.append((event, holding))
    return pending


async def send_pending_split_prompts(
    message: Message,
    repo: Repository,
    portfolio: Portfolio,
    t: dict,
    lang: str,
    today: date,
) -> None:
    for event, holding in await find_pending_split_events(repo, portfolio, today):
        text, keyboard = build_split_message(event, [(portfolio, holding)], t, lang)
        await message.answer(text, reply_markup=keyboard)
