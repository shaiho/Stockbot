from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from src.bot.common import MENU_TRADE, get_user_lang
from src.bot.keyboards import trade_action_keyboard
from src.bot.portfolio_flow import resolve_portfolio, show_portfolio_picker, touch_portfolio
from src.bot.states import TradeStates
from src.bot.trade_helpers import (
    prompt_trade_date,
    prompt_trade_note,
    store_trade_date,
    store_trade_date_today,
)
from src.portfolio.commission import calc_trade_commission

router = Router()


async def _save_trade(
    message: Message,
    state,
    ctx,
    user,
    form: dict,
    t: dict,
    *,
    note: str | None = None,
) -> None:
    currency = "ILS" if form.get("market") == "IL" else "USD"
    if form["action"] == "dividend":
        quantity = 1.0
        price = form["price"]
    else:
        quantity = form["quantity"]
        price = form["price"]

    if form["action"] in ("buy", "sell"):
        portfolio = await ctx.repo.get_portfolio(form["portfolio_id"], user.telegram_id)
        commission = (
            calc_trade_commission(portfolio, quantity, price, currency) if portfolio else 0.0
        )
    else:
        commission = 0.0

    await ctx.repo.add_trade(
        portfolio_id=form["portfolio_id"],
        symbol=form["symbol"],
        market=form["market"],
        asset_type="stock",
        action=form["action"],
        quantity=quantity,
        price=price,
        currency=currency,
        commission=commission,
        note=note,
        timestamp=form.get("trade_timestamp"),
    )
    await state.clear()
    action_labels = {
        "buy": t["buy"],
        "sell": t["sell"],
        "dividend": t["dividend"],
    }
    action = action_labels.get(form["action"], form["action"])
    await message.answer(
        t["trade_saved"].format(
            action=action,
            symbol=form["symbol"],
            quantity=quantity,
        )
    )


@router.message(F.text.in_(MENU_TRADE))
async def menu_trade(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    portfolios = await ctx.repo.get_portfolios(user.telegram_id)
    if not portfolios:
        await show_portfolio_picker(
            message, [], lang, t, include_new=True, action="pick_portfolio"
        )
        return

    only = resolve_portfolio(user, portfolios)
    if only:
        await touch_portfolio(ctx.repo, user, only.id)
        await state.update_data(portfolio_id=only.id)
        await state.set_state(TradeStates.action)
        await message.answer(t["choose_action"], reply_markup=trade_action_keyboard(lang))
        return

    await state.set_state(TradeStates.portfolio)
    await show_portfolio_picker(message, portfolios, lang, t, action="pick_portfolio")


@router.callback_query(TradeStates.portfolio, F.data.startswith("pick_portfolio:"))
async def trade_pick_portfolio(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    portfolio_id = int(callback.data.split(":")[1])
    await state.update_data(portfolio_id=portfolio_id)
    await state.set_state(TradeStates.action)
    await callback.message.edit_text(t["choose_action"], reply_markup=trade_action_keyboard(lang))
    await callback.answer()


@router.callback_query(TradeStates.action, F.data.startswith("trade:"))
async def trade_action(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    action = callback.data.split(":")[1]
    await state.update_data(action=action)
    await state.set_state(TradeStates.symbol)
    await callback.message.edit_text(t["enter_symbol"])
    await callback.answer()


@router.message(TradeStates.symbol)
async def trade_symbol(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    symbol = (message.text or "").strip().upper()
    await state.update_data(symbol=symbol)
    await state.set_state(TradeStates.market)
    from src.bot.keyboards import market_keyboard

    await message.answer(t["choose_market"], reply_markup=market_keyboard(lang))


@router.callback_query(TradeStates.market, F.data.startswith("market:"))
async def trade_market(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    market = callback.data.split(":")[1]
    await state.update_data(market=market)
    form = await state.get_data()
    if form.get("action") == "dividend":
        await state.set_state(TradeStates.price)
        await callback.message.edit_text(t["dividend_amount_prompt"])
    else:
        await state.set_state(TradeStates.quantity)
        await callback.message.edit_text(t["quantity_prompt"])
    await callback.answer()


@router.message(TradeStates.quantity)
async def trade_quantity(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    try:
        qty = float((message.text or "").replace(",", ""))
    except ValueError:
        await message.answer(t["invalid_number"])
        return

    form = await state.get_data()
    if form.get("action") == "sell":
        holdings = await ctx.repo.get_holdings(form["portfolio_id"])
        holding = next(
            (
                h
                for h in holdings
                if h.symbol == form["symbol"] and h.market == form.get("market")
            ),
            None,
        )
        if not holding or holding.quantity + 1e-9 < qty:
            await message.answer(t["insufficient_quantity"])
            return

    await state.update_data(quantity=qty)
    await state.set_state(TradeStates.price)
    price_key = "trade_sell_price_prompt" if form.get("action") == "sell" else "trade_buy_price_prompt"
    await message.answer(t[price_key])


@router.message(TradeStates.price)
async def trade_price(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    try:
        price = float((message.text or "").replace(",", ""))
    except ValueError:
        await message.answer(t["invalid_number"])
        return
    await state.update_data(price=price)
    await prompt_trade_date(message, state, TradeStates.trade_date, t, lang)


@router.callback_query(TradeStates.trade_date, F.data == "trade_date:today")
async def trade_date_today(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    await store_trade_date_today(state)
    await prompt_trade_note(callback.message, state, TradeStates.note, t, lang)
    await callback.answer()


@router.message(TradeStates.trade_date)
async def trade_date_input(message: Message, state, **data) -> None:
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
    await prompt_trade_note(message, state, TradeStates.note, t, lang)


@router.callback_query(TradeStates.note, F.data == "trade_note:skip")
async def trade_note_skip(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    form = await state.get_data()
    await _save_trade(callback.message, state, ctx, user, form, t, note=None)
    await callback.answer()


@router.message(TradeStates.note)
async def trade_note(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    form = await state.get_data()
    note = (message.text or "").strip() or None
    await _save_trade(message, state, ctx, user, form, t, note=note)
