from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from src.bot.common import MENU_CASH, get_user_lang
from src.bot.keyboards import cash_action_keyboard, currency_keyboard
from src.bot.portfolio_flow import resolve_portfolio, show_portfolio_picker, touch_portfolio
from src.bot.states import CashStates
from src.bot.trade_helpers import prompt_trade_date, store_trade_date, store_trade_date_today

router = Router()


async def _save_cash(message: Message, state, ctx, user, form, t) -> None:
    currency = form["currency"]
    amount = form["amount"]
    cash_action = form.get("cash_action", "deposit")
    if amount <= 0:
        await message.answer(t["invalid_number"])
        return

    portfolio_id = form["portfolio_id"]
    if cash_action == "withdraw":
        cash_ils, cash_usd = await ctx.repo.get_cash_balances(portfolio_id)
        balance = cash_ils if currency == "ILS" else cash_usd
        if balance + 1e-9 < amount:
            await message.answer(t["insufficient_cash"])
            return
        await ctx.repo.add_cash_withdrawal(
            portfolio_id=portfolio_id,
            currency=currency,
            amount=amount,
            timestamp=form.get("trade_timestamp"),
        )
        symbol = "₪" if currency == "ILS" else "$"
        await state.clear()
        await message.answer(t["cash_withdrawn"].format(amount=f"{symbol}{amount:,.2f}"))
        return

    await ctx.repo.add_cash_deposit(
        portfolio_id=portfolio_id,
        currency=currency,
        amount=amount,
        timestamp=form.get("trade_timestamp"),
    )
    await state.clear()
    symbol = "₪" if currency == "ILS" else "$"
    await message.answer(t["cash_deposited"].format(amount=f"{symbol}{amount:,.2f}"))


async def _prompt_cash_action(message: Message, t: dict, lang: str) -> None:
    await message.answer(t["cash_action_prompt"], reply_markup=cash_action_keyboard(lang))


@router.message(F.text.in_(MENU_CASH))
async def menu_cash(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    portfolios = await ctx.repo.get_portfolios(user.telegram_id)
    if not portfolios:
        await message.answer(t["no_portfolios"])
        return
    only = resolve_portfolio(user, portfolios)
    if only:
        await touch_portfolio(ctx.repo, user, only.id)
        await state.update_data(portfolio_id=only.id)
        await state.set_state(CashStates.action)
        await _prompt_cash_action(message, t, lang)
        return
    await state.set_state(CashStates.portfolio)
    await show_portfolio_picker(message, portfolios, lang, t, action="cash_portfolio")


@router.callback_query(F.data.startswith("add_cash_portfolio:"))
async def manage_add_cash(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    portfolio_id = int(callback.data.split(":")[1])
    await state.update_data(portfolio_id=portfolio_id)
    await state.set_state(CashStates.action)
    await _prompt_cash_action(callback.message, t, lang)
    await callback.answer()


@router.callback_query(CashStates.portfolio, F.data.startswith("cash_portfolio:"))
async def cash_pick_portfolio(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    portfolio_id = int(callback.data.split(":")[1])
    await state.update_data(portfolio_id=portfolio_id)
    await state.set_state(CashStates.action)
    await callback.message.edit_text(t["cash_action_prompt"], reply_markup=cash_action_keyboard(lang))
    await callback.answer()


@router.callback_query(CashStates.action, F.data.startswith("cash:action:"))
async def cash_action(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    cash_action = callback.data.split(":")[2]
    await state.update_data(cash_action=cash_action)
    await state.set_state(CashStates.currency)
    await callback.message.edit_text(
        t["deposit_currency_prompt"],
        reply_markup=currency_keyboard(lang, prefix="cash:currency"),
    )
    await callback.answer()


@router.callback_query(CashStates.currency, F.data.startswith("cash:currency:"))
async def cash_currency(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    currency = callback.data.split(":")[2]
    await state.update_data(currency=currency)
    await state.set_state(CashStates.amount)
    form = await state.get_data()
    key = "withdraw_amount_prompt" if form.get("cash_action") == "withdraw" else "deposit_amount_prompt"
    await callback.message.edit_text(t[key])
    await callback.answer()


@router.message(CashStates.amount)
async def cash_amount(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    try:
        amount = float((message.text or "").replace(",", ""))
    except ValueError:
        await message.answer(t["invalid_number"])
        return
    if amount <= 0:
        await message.answer(t["invalid_number"])
        return
    await state.update_data(amount=amount)
    await prompt_trade_date(message, state, CashStates.trade_date, t, lang)


@router.callback_query(CashStates.trade_date, F.data == "trade_date:today")
async def cash_date_today(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    await store_trade_date_today(state)
    form = await state.get_data()
    await _save_cash(callback.message, state, ctx, user, form, t)
    await callback.answer()


@router.message(CashStates.trade_date)
async def cash_date_input(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    try:
        await store_trade_date(message, state, message.text)
    except ValueError as exc:
        if str(exc) == "future_date":
            await message.answer(t["future_date"])
        else:
            await message.answer(t["invalid_date"])
        return
    form = await state.get_data()
    await _save_cash(message, state, ctx, user, form, t)
