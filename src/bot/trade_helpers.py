from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from src.portfolio.trade_date import parse_trade_date


def trade_date_keyboard(lang: str) -> InlineKeyboardMarkup:
    label = "📅 היום" if lang == "he" else "📅 Today"
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=label, callback_data="trade_date:today")]]
    )


def trade_note_keyboard(lang: str) -> InlineKeyboardMarkup:
    skip = "⏭ דילוג" if lang == "he" else "⏭ Skip"
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=skip, callback_data="trade_note:skip")]]
    )


def trade_commission_keyboard(lang: str) -> InlineKeyboardMarkup:
    label = "🔄 חישוב אוטומטי" if lang == "he" else "🔄 Auto calculate"
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=label, callback_data="trade_commission:auto")]]
    )


async def prompt_trade_note(message: Message, state, next_state, t: dict, lang: str) -> None:
    await state.set_state(next_state)
    await message.answer(t["trade_note_prompt"], reply_markup=trade_note_keyboard(lang))


async def prompt_trade_date(message: Message, state, next_state, t: dict, lang: str) -> None:
    await state.set_state(next_state)
    await message.answer(t["trade_date_prompt"], reply_markup=trade_date_keyboard(lang))


async def store_trade_date(message: Message, state, text: str | None) -> str:
    timestamp = parse_trade_date(text)
    await state.update_data(trade_timestamp=timestamp)
    return timestamp


async def store_trade_date_today(state) -> str:
    timestamp = parse_trade_date(None)
    await state.update_data(trade_timestamp=timestamp)
    return timestamp
