from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from src.bot.common import get_user_lang
from src.bot.keyboards import trade_edit_fields_keyboard, trade_manage_keyboard
from src.bot.states import EditTradeStates
from src.bot.trade_helpers import trade_date_keyboard, trade_note_keyboard
from src.portfolio.formatter import fmt_date, fmt_money, format_trade_line
from src.portfolio.trade_date import parse_trade_date

router = Router()
logger = logging.getLogger(__name__)


def _trade_detail(trade, t: dict) -> str:
    action_labels = {
        "buy": t["buy"],
        "sell": t["sell"],
        "deposit": t["deposit"],
        "withdraw": t["withdraw"],
        "dividend": t["dividend"],
    }
    action = action_labels.get(trade.action, trade.action)
    lines = [
        f"#{trade.id} — {trade.symbol}",
        f"{t['choose_action']}: {action}",
        f"{t['quantity']}: {trade.quantity:g}",
        f"{t['price']}: {fmt_money(trade.price, trade.currency)}",
        f"{t['commissions']}: {fmt_money(trade.commission, trade.currency)}",
        f"📅 {fmt_date(trade.timestamp)}",
    ]
    if trade.note:
        lines.append(f"{t['trade_note']}: {trade.note}")
    return "\n".join(lines)


def _field_label(field: str, t: dict) -> str:
    labels = {
        "quantity": t["quantity"],
        "price": t["price"],
        "commission": t["commissions"],
        "date": "📅",
        "note": t["trade_note"],
    }
    return labels.get(field, field)


def _edit_prompts(t: dict) -> dict[str, str]:
    return {
        "quantity": t["quantity_prompt"],
        "price": t["price_prompt"],
        "commission": t["commission_prompt"],
        "date": t["trade_date_prompt"],
        "note": t["trade_note_prompt"],
    }


async def _apply_trade_edit(
    message: Message,
    state,
    ctx,
    user,
    t: dict,
    *,
    trade_id: int,
    field: str,
    data: dict,
) -> None:
    try:
        ok = await ctx.repo.update_trade(trade_id, user.telegram_id, **data)
    except Exception:
        logger.exception("update_trade failed trade_id=%s field=%s", trade_id, field)
        await message.answer(t["trade_update_failed"])
        return
    if not ok:
        await state.clear()
        await message.answer(t["trade_not_found"])
        return

    updated = await ctx.repo.get_trade(trade_id, user.telegram_id)
    await state.set_state(None)
    await state.update_data(trade_id=trade_id)
    field_label = _field_label(field, t)
    await message.answer(
        t["trade_updated_field"].format(field=field_label) + "\n\n" + _trade_detail(updated, t),
        reply_markup=trade_edit_fields_keyboard(trade_id, t),
    )


@router.callback_query(F.data.startswith("trade_manage:"))
async def trade_manage(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    trade_id = int(callback.data.split(":")[1])
    trade = await ctx.repo.get_trade(trade_id, user.telegram_id)
    if not trade:
        await callback.answer(t["trade_not_found"], show_alert=True)
        return
    await state.clear()
    await callback.message.answer(
        _trade_detail(trade, t),
        reply_markup=trade_manage_keyboard(trade_id, t),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("trade_del:"))
async def trade_delete_prompt(callback: CallbackQuery, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    trade_id = int(callback.data.split(":")[1])
    trade = await ctx.repo.get_trade(trade_id, user.telegram_id)
    if not trade:
        await callback.answer(t["trade_not_found"], show_alert=True)
        return
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t["confirm_delete_trade"],
                    callback_data=f"trade_del_confirm:{trade_id}",
                ),
                InlineKeyboardButton(text=t["cancel"], callback_data=f"trade_manage:{trade_id}"),
            ]
        ]
    )
    await callback.message.edit_text(
        t["delete_trade_confirm"].format(id=trade_id, line=format_trade_line(trade, t)),
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("trade_del_confirm:"))
async def trade_delete_confirm(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    trade_id = int(callback.data.split(":")[1])
    ok = await ctx.repo.delete_trade(trade_id, user.telegram_id)
    await state.clear()
    if ok:
        await callback.message.edit_text(t["trade_deleted"])
    else:
        await callback.message.edit_text(t["trade_not_found"])
    await callback.answer()


@router.callback_query(F.data.startswith("trade_edit_field:"))
async def trade_edit_field(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    parts = callback.data.split(":")
    trade_id = int(parts[1])
    field = parts[2]
    trade = await ctx.repo.get_trade(trade_id, user.telegram_id)
    if not trade:
        await callback.answer(t["trade_not_found"], show_alert=True)
        return
    prompts = _edit_prompts(t)
    await state.update_data(trade_id=trade_id, edit_field=field)
    await state.set_state(EditTradeStates.value)
    reply_markup = None
    if field == "note":
        reply_markup = trade_note_keyboard(lang)
    elif field == "date":
        reply_markup = trade_date_keyboard(lang)
    await callback.message.edit_text(prompts[field], reply_markup=reply_markup)
    await callback.answer()


@router.callback_query(F.data.regexp(r"^trade_edit:\d+$"))
async def trade_edit_start(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    trade_id = int(callback.data.split(":")[1])
    trade = await ctx.repo.get_trade(trade_id, user.telegram_id)
    if not trade:
        await callback.answer(t["trade_not_found"], show_alert=True)
        return
    await state.set_state(None)
    await state.update_data(trade_id=trade_id)
    await callback.message.edit_text(
        t["edit_trade_field"],
        reply_markup=trade_edit_fields_keyboard(trade_id, t),
    )
    await callback.answer()


@router.callback_query(EditTradeStates.value, F.data == "trade_note:skip")
async def trade_edit_note_skip(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    form = await state.get_data()
    trade_id = form.get("trade_id")
    if form.get("edit_field") != "note" or not trade_id:
        await callback.answer()
        return
    data["skip_menu_restore"] = True
    await _apply_trade_edit(
        callback.message,
        state,
        ctx,
        user,
        t,
        trade_id=trade_id,
        field="note",
        data={"note": None},
    )
    await callback.answer()


@router.callback_query(EditTradeStates.value, F.data == "trade_date:today")
async def trade_edit_date_today(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    form = await state.get_data()
    trade_id = form.get("trade_id")
    if form.get("edit_field") != "date" or not trade_id:
        await callback.answer()
        return
    data["skip_menu_restore"] = True
    await _apply_trade_edit(
        callback.message,
        state,
        ctx,
        user,
        t,
        trade_id=trade_id,
        field="date",
        data={"timestamp": parse_trade_date(None)},
    )
    await callback.answer()


@router.message(EditTradeStates.value)
async def trade_edit_value(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    form = await state.get_data()
    trade_id = form["trade_id"]
    field = form["edit_field"]
    trade = await ctx.repo.get_trade(trade_id, user.telegram_id)
    if not trade:
        await state.clear()
        await message.answer(t["trade_not_found"])
        return

    text = (message.text or "").strip()
    kwargs: dict = {}
    if field == "quantity":
        try:
            kwargs["quantity"] = float(text.replace(",", ""))
        except ValueError:
            await message.answer(t["invalid_number"])
            return
        if kwargs["quantity"] <= 0:
            await message.answer(t["invalid_number"])
            return
    elif field == "price":
        try:
            kwargs["price"] = float(text.replace(",", ""))
        except ValueError:
            await message.answer(t["invalid_number"])
            return
    elif field == "commission":
        try:
            kwargs["commission"] = float(text.replace(",", "")) if text else 0.0
        except ValueError:
            await message.answer(t["invalid_number"])
            return
    elif field == "date":
        try:
            kwargs["timestamp"] = parse_trade_date(text or "today")
        except ValueError as exc:
            if str(exc) == "future_date":
                await message.answer(t["future_date"])
            else:
                await message.answer(t["invalid_date"])
            return
    elif field == "note":
        kwargs["note"] = text or None

    data["skip_menu_restore"] = True
    await _apply_trade_edit(
        message,
        state,
        ctx,
        user,
        t,
        trade_id=trade_id,
        field=field,
        data=kwargs,
    )
