from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.db.models import Holding, Portfolio
from src.market.events import EVENT_DIVIDEND, EVENT_REVERSE_SPLIT, EVENT_SPLIT, MarketEvent
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
        [InlineKeyboardButton(text=skip_label, callback_data=f"ca:skip:{event.event_key[:40]}")]
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
        [InlineKeyboardButton(text=skip_label, callback_data=f"ca:skip:{event.event_key[:40]}")]
    )
    lines.append("")
    lines.append(t["event_dividend_apply_hint"])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


def is_actionable_event(event: MarketEvent) -> bool:
    return event.event_type in (EVENT_SPLIT, EVENT_REVERSE_SPLIT, EVENT_DIVIDEND)
