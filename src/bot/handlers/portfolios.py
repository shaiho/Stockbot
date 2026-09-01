from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from src.bot.common import MENU_PORTFOLIOS, get_user_lang
from src.bot.keyboards import (
    commission_extra_type_keyboard,
    holdings_now_keyboard,
    market_keyboard,
    portfolio_manage_keyboard,
    portfolio_picker_keyboard,
    yes_no_keyboard,
    zero_or_custom_keyboard,
)
from src.portfolio.commission import calc_trade_commission, format_commission_settings
from src.bot.states import NewPortfolioStates, PortfolioManageStates
from src.bot.portfolio_flow import resolve_portfolio
from src.bot.trade_helpers import prompt_trade_date, store_trade_date, store_trade_date_today

router = Router()
logger = logging.getLogger(__name__)


async def _finish_new_portfolio(message: Message, state, ctx, user, lang: str, t: dict, portfolio_id: int) -> None:
    await state.clear()
    await _show_portfolio_manage(message, ctx, user, lang, t, portfolio_id)


async def _save_new_portfolio_trade(
    message: Message,
    state,
    ctx,
    user,
    lang: str,
    t: dict,
    *,
    edit: bool = False,
) -> None:
    form = await state.get_data()
    currency = "ILS" if form.get("market") == "IL" else "USD"
    portfolio = await ctx.repo.get_portfolio(form["portfolio_id"], user.telegram_id)
    commission = (
        calc_trade_commission(portfolio, form["quantity"], form["price"], currency) if portfolio else 0.0
    )
    try:
        await ctx.repo.add_trade(
            portfolio_id=form["portfolio_id"],
            symbol=form["symbol"],
            market=form["market"],
            asset_type="stock",
            action="buy",
            quantity=form["quantity"],
            price=form["price"],
            currency=currency,
            commission=commission,
            timestamp=form.get("trade_timestamp"),
        )
    except Exception:
        logger.exception(
            "new_portfolio add_trade failed user=%s portfolio=%s",
            user.telegram_id,
            form.get("portfolio_id"),
        )
        target = message if not edit else message
        await target.answer(t["action_failed"])
        return

    await state.set_state(NewPortfolioStates.add_another)
    text = t["add_another_holding"]
    kb = yes_no_keyboard(lang)
    if edit:
        await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


async def _create_portfolio_and_ask_holdings(
    message: Message,
    state,
    ctx,
    user,
    lang: str,
    t: dict,
    opening_cash_usd: float,
    *,
    edit: bool = False,
) -> None:
    form = await state.get_data()
    try:
        portfolio = await ctx.repo.create_portfolio(
            user.telegram_id,
            form["portfolio_name"],
            form.get("opening_cash_ils", 0),
            opening_cash_usd,
        )
    except ValueError as exc:
        text = t.get(str(exc), t["duplicate_name"])
        if edit:
            await message.edit_text(text)
        else:
            await message.answer(text)
        return

    user.last_portfolio_id = portfolio.id
    await ctx.repo.update_user(user)
    await state.update_data(portfolio_id=portfolio.id)
    await state.set_state(NewPortfolioStates.add_holdings_now)
    text = t["add_holdings_now"]
    kb = holdings_now_keyboard(lang)
    if edit:
        await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


async def _show_portfolios_list(message: Message, ctx, user, lang: str, t: dict, *, edit: bool = False) -> None:
    portfolios = await ctx.repo.get_portfolios(user.telegram_id)
    text = t["portfolios_list"]
    if portfolios:
        lines = "\n".join(f"• 📁 {p.name}" for p in portfolios)
        text = f"{text}\n\n{lines}"
    kb = portfolio_picker_keyboard(portfolios, lang, include_new=True, action="manage_portfolio")
    if edit:
        await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


async def _show_portfolio_manage(
    message: Message, ctx, user, lang: str, t: dict, portfolio_id: int, *, edit: bool = False
) -> None:
    portfolio = await ctx.repo.get_portfolio(portfolio_id, user.telegram_id)
    if not portfolio:
        await _show_portfolios_list(message, ctx, user, lang, t, edit=edit)
        return
    text = (
        f"{t['portfolio_manage']}\n"
        f"📁 {portfolio.name}\n\n"
        f"₪{portfolio.opening_cash_ils:,.0f} | ${portfolio.opening_cash_usd:,.2f}"
        f"{format_commission_settings(portfolio, t)}"
    )
    kb = portfolio_manage_keyboard(portfolio_id, t)
    if edit:
        await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


@router.message(F.text.in_(MENU_PORTFOLIOS))
async def menu_portfolios(message: Message, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    portfolios = await ctx.repo.get_portfolios(user.telegram_id)
    only = resolve_portfolio(user, portfolios)
    if only:
        await _show_portfolio_manage(message, ctx, user, lang, t, only.id)
        return
    await _show_portfolios_list(message, ctx, user, lang, t)


@router.callback_query(F.data == "portfolios_back")
async def portfolios_back(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    await state.clear()
    await _show_portfolios_list(callback.message, ctx, user, lang, t, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith("manage_portfolio:"))
async def manage_portfolio(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    portfolio_id = int(callback.data.split(":")[1])
    await state.clear()
    await _show_portfolio_manage(callback.message, ctx, user, lang, t, portfolio_id, edit=True)
    await callback.answer()


@router.callback_query(F.data == "new_portfolio")
async def new_portfolio(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    if await ctx.repo.count_portfolios(user.telegram_id) >= 5:
        await callback.answer(t["max_portfolios"], show_alert=True)
        return
    await state.set_state(NewPortfolioStates.name)
    await callback.message.answer(t["portfolio_name_prompt"])
    await callback.answer()


@router.message(NewPortfolioStates.name)
async def new_portfolio_name(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    name = (message.text or "").strip()
    if not name:
        await message.answer(t["portfolio_name_prompt"])
        return
    await state.update_data(portfolio_name=name)
    await state.set_state(NewPortfolioStates.opening_cash_ils)
    await message.answer(
        t["opening_cash_ils"],
        reply_markup=zero_or_custom_keyboard("cash_ils", lang),
    )


@router.callback_query(NewPortfolioStates.opening_cash_ils, F.data.startswith("ob:cash_ils:"))
async def new_portfolio_cash_ils_choice(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    choice = callback.data.split(":")[2]

    if choice == "0":
        await state.update_data(opening_cash_ils=0.0)
        await state.set_state(NewPortfolioStates.opening_cash_usd)
        await callback.message.edit_text(
            t["opening_cash_usd"],
            reply_markup=zero_or_custom_keyboard("cash_usd", lang),
        )
    else:
        await state.set_state(NewPortfolioStates.opening_cash_ils_custom)
        await callback.message.edit_text(t["opening_cash_ils"] + "\n✏️")
    await callback.answer()


@router.message(NewPortfolioStates.opening_cash_ils_custom)
async def new_portfolio_cash_ils_custom(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    try:
        cash = float((message.text or "0").replace(",", ""))
    except ValueError:
        await message.answer(t["invalid_number"])
        return
    await state.update_data(opening_cash_ils=cash)
    await state.set_state(NewPortfolioStates.opening_cash_usd)
    await message.answer(
        t["opening_cash_usd"],
        reply_markup=zero_or_custom_keyboard("cash_usd", lang),
    )


@router.callback_query(NewPortfolioStates.opening_cash_usd, F.data.startswith("ob:cash_usd:"))
async def new_portfolio_cash_usd_choice(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    choice = callback.data.split(":")[2]

    if choice == "custom":
        await state.set_state(NewPortfolioStates.opening_cash_usd_custom)
        await callback.message.edit_text(t["opening_cash_usd"] + "\n✏️")
        await callback.answer()
        return

    await state.update_data(opening_cash_usd=0.0)
    await _create_portfolio_and_ask_holdings(
        callback.message, state, ctx, user, lang, t, 0.0, edit=True
    )
    await callback.answer()


@router.message(NewPortfolioStates.opening_cash_usd_custom)
async def new_portfolio_cash_usd_custom(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    try:
        cash = float((message.text or "0").replace(",", ""))
    except ValueError:
        await message.answer(t["invalid_number"])
        return
    await _create_portfolio_and_ask_holdings(message, state, ctx, user, lang, t, cash)


@router.callback_query(NewPortfolioStates.add_holdings_now, F.data.startswith("ob:holdings:"))
async def new_portfolio_holdings_choice(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    form = await state.get_data()

    if callback.data.endswith(":no"):
        await callback.message.edit_text(t["onboarding_done"])
        await _finish_new_portfolio(callback.message, state, ctx, user, lang, t, form["portfolio_id"])
        await callback.answer()
        return

    await state.set_state(NewPortfolioStates.symbol)
    await callback.message.edit_text(t["add_holding_prompt"])
    await callback.answer()


@router.message(NewPortfolioStates.symbol)
async def new_portfolio_symbol(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    symbol = (message.text or "").strip().upper()
    if not symbol:
        await message.answer(t["add_holding_prompt"])
        return
    await state.update_data(symbol=symbol)
    await state.set_state(NewPortfolioStates.market)
    await message.answer(t["choose_market"], reply_markup=market_keyboard(lang))


@router.callback_query(NewPortfolioStates.market, F.data.startswith("market:"))
async def new_portfolio_market(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    market = callback.data.split(":")[1]
    await state.update_data(market=market)
    await state.set_state(NewPortfolioStates.quantity)
    await callback.message.edit_text(t["quantity_prompt"])
    await callback.answer()


@router.message(NewPortfolioStates.quantity)
async def new_portfolio_quantity(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    try:
        qty = float((message.text or "").replace(",", ""))
    except ValueError:
        await message.answer(t["invalid_number"])
        return
    await state.update_data(quantity=qty)
    await state.set_state(NewPortfolioStates.price)
    await message.answer(t["price_prompt"])


@router.message(NewPortfolioStates.price)
async def new_portfolio_price(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    try:
        price = float((message.text or "").replace(",", ""))
    except ValueError:
        await message.answer(t["invalid_number"])
        return

    await state.update_data(price=price)
    await prompt_trade_date(message, state, NewPortfolioStates.trade_date, t, lang)


@router.callback_query(NewPortfolioStates.trade_date, F.data == "trade_date:today")
async def new_portfolio_trade_date_today(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    await store_trade_date_today(state)
    await _save_new_portfolio_trade(callback.message, state, ctx, user, lang, t, edit=True)
    await callback.answer()


@router.message(NewPortfolioStates.trade_date)
async def new_portfolio_trade_date(message: Message, state, **data) -> None:
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

    await _save_new_portfolio_trade(message, state, ctx, user, lang, t)


@router.callback_query(NewPortfolioStates.add_another, F.data.in_({"yes", "no"}))
async def new_portfolio_add_another(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    form = await state.get_data()

    if callback.data == "yes":
        await state.set_state(NewPortfolioStates.symbol)
        await callback.message.edit_text(t["add_holding_prompt"])
        await callback.answer()
        return

    await callback.message.edit_text(t["onboarding_done"])
    await _finish_new_portfolio(callback.message, state, ctx, user, lang, t, form["portfolio_id"])
    await callback.answer()


@router.callback_query(F.data.startswith("rename_portfolio:"))
async def rename_portfolio_start(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    portfolio_id = int(callback.data.split(":")[1])
    await state.update_data(portfolio_id=portfolio_id)
    await state.set_state(PortfolioManageStates.rename)
    await callback.message.answer(t["portfolio_name_prompt"])
    await callback.answer()


@router.message(PortfolioManageStates.rename)
async def rename_portfolio_finish(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    form = await state.get_data()
    name = (message.text or "").strip()
    if not name:
        await message.answer(t["portfolio_name_prompt"])
        return
    try:
        await ctx.repo.rename_portfolio(form["portfolio_id"], user.telegram_id, name)
    except ValueError:
        await message.answer(t["duplicate_name"])
        return
    await state.clear()
    await message.answer(t["renamed"].format(name=name))
    await _show_portfolio_manage(message, ctx, user, lang, t, form["portfolio_id"])


@router.callback_query(F.data.startswith("edit_cash_portfolio:"))
async def edit_cash_start(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    portfolio_id = int(callback.data.split(":")[1])
    portfolio = await ctx.repo.get_portfolio(portfolio_id, user.telegram_id)
    if not portfolio:
        await callback.answer()
        return
    await state.update_data(
        portfolio_id=portfolio_id,
        opening_cash_ils=portfolio.opening_cash_ils,
        opening_cash_usd=portfolio.opening_cash_usd,
    )
    await state.set_state(PortfolioManageStates.edit_cash_ils)
    await callback.message.answer(
        t["opening_cash_ils"],
        reply_markup=zero_or_custom_keyboard("cash_ils", lang, prefix="mgmt"),
    )
    await callback.answer()


@router.callback_query(PortfolioManageStates.edit_cash_ils, F.data.startswith("mgmt:cash_ils:"))
async def edit_cash_ils_choice(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    choice = callback.data.split(":")[2]
    form = await state.get_data()

    if choice == "0":
        await state.update_data(opening_cash_ils=0.0)
    else:
        await state.set_state(PortfolioManageStates.edit_cash_ils_custom)
        await callback.message.edit_text(t["opening_cash_ils"] + "\n✏️")
        await callback.answer()
        return

    await state.set_state(PortfolioManageStates.edit_cash_usd)
    await callback.message.edit_text(
        t["opening_cash_usd"],
        reply_markup=zero_or_custom_keyboard("cash_usd", lang, prefix="mgmt"),
    )
    await callback.answer()


@router.message(PortfolioManageStates.edit_cash_ils_custom)
async def edit_cash_ils_custom(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    try:
        cash = float((message.text or "0").replace(",", ""))
    except ValueError:
        await message.answer(t["invalid_number"])
        return
    await state.update_data(opening_cash_ils=cash)
    await state.set_state(PortfolioManageStates.edit_cash_usd)
    await message.answer(
        t["opening_cash_usd"],
        reply_markup=zero_or_custom_keyboard("cash_usd", lang, prefix="mgmt"),
    )


@router.callback_query(PortfolioManageStates.edit_cash_usd, F.data.startswith("mgmt:cash_usd:"))
async def edit_cash_usd_choice(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    choice = callback.data.split(":")[2]
    form = await state.get_data()

    if choice == "custom":
        await state.set_state(PortfolioManageStates.edit_cash_usd_custom)
        await callback.message.edit_text(t["opening_cash_usd"] + "\n✏️")
        await callback.answer()
        return

    await state.update_data(opening_cash_usd=0.0)
    await ctx.repo.update_portfolio_opening_cash(
        form["portfolio_id"],
        user.telegram_id,
        form.get("opening_cash_ils", 0),
        0.0,
    )
    portfolio_id = form["portfolio_id"]
    await state.clear()
    await callback.message.edit_text(t["opening_cash_updated"])
    await _show_portfolio_manage(callback.message, ctx, user, lang, t, portfolio_id)
    await callback.answer()


@router.message(PortfolioManageStates.edit_cash_usd_custom)
async def edit_cash_usd_custom(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    try:
        cash = float((message.text or "0").replace(",", ""))
    except ValueError:
        await message.answer(t["invalid_number"])
        return
    form = await state.get_data()
    await ctx.repo.update_portfolio_opening_cash(
        form["portfolio_id"],
        user.telegram_id,
        form.get("opening_cash_ils", 0),
        cash,
    )
    portfolio_id = form["portfolio_id"]
    await state.clear()
    await message.answer(t["opening_cash_updated"])
    await _show_portfolio_manage(message, ctx, user, lang, t, portfolio_id)


@router.callback_query(F.data.startswith("edit_commission:"))
async def edit_commission_start(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    portfolio_id = int(callback.data.split(":")[1])
    portfolio = await ctx.repo.get_portfolio(portfolio_id, user.telegram_id)
    if not portfolio:
        await callback.answer()
        return
    await state.update_data(portfolio_id=portfolio_id)
    await state.set_state(PortfolioManageStates.commission_min_usd)
    await callback.message.answer(t["ask_commission_min_usd"])
    await callback.answer()


@router.message(PortfolioManageStates.commission_min_usd)
async def edit_commission_min_usd(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    try:
        value = float(message.text.replace(",", "").strip())
        if value < 0:
            raise ValueError
    except ValueError:
        await message.answer(t["invalid_number"])
        return
    await state.update_data(commission_min_usd=value)
    await state.set_state(PortfolioManageStates.commission_min_ils)
    await message.answer(t["ask_commission_min_ils"])


@router.message(PortfolioManageStates.commission_min_ils)
async def edit_commission_min_ils(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    try:
        value = float(message.text.replace(",", "").strip())
        if value < 0:
            raise ValueError
    except ValueError:
        await message.answer(t["invalid_number"])
        return
    await state.update_data(commission_min_ils=value)
    await state.set_state(PortfolioManageStates.commission_extra_type)
    await message.answer(t["ask_commission_extra_type"], reply_markup=commission_extra_type_keyboard(t))


@router.callback_query(PortfolioManageStates.commission_extra_type, F.data.startswith("comm_extra:"))
async def edit_commission_extra_type(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    extra_type = callback.data.split(":")[1]
    if extra_type not in {"fixed", "percent"}:
        await callback.answer()
        return
    await state.update_data(commission_extra_type=extra_type)
    await state.set_state(PortfolioManageStates.commission_extra_value)
    prompt = t["ask_commission_extra_fixed"] if extra_type == "fixed" else t["ask_commission_extra_percent"]
    await callback.message.edit_text(prompt)
    await callback.answer()


@router.message(PortfolioManageStates.commission_extra_value)
async def edit_commission_extra_value(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    form = await state.get_data()
    extra_type = form.get("commission_extra_type", "fixed")
    try:
        value = float(message.text.replace(",", "").strip().replace("%", ""))
        if value < 0:
            raise ValueError
        if extra_type == "percent" and value > 100:
            raise ValueError
    except ValueError:
        await message.answer(t["invalid_number"])
        return
    portfolio_id = form["portfolio_id"]
    await ctx.repo.update_portfolio_commission(
        portfolio_id=portfolio_id,
        user_id=user.telegram_id,
        commission_min_usd=form["commission_min_usd"],
        commission_min_ils=form["commission_min_ils"],
        commission_extra_type=extra_type,
        commission_extra_value=value,
    )
    await state.clear()
    await message.answer(t["commission_updated"])
    await _show_portfolio_manage(message, ctx, user, lang, t, portfolio_id)


@router.callback_query(F.data.startswith("recalc_commissions:"))
async def recalc_commissions(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    portfolio_id = int(callback.data.split(":")[1])
    portfolio = await ctx.repo.get_portfolio(portfolio_id, user.telegram_id)
    if not portfolio:
        await callback.answer()
        return
    count = await ctx.repo.recalculate_portfolio_commissions(portfolio_id, user.telegram_id)
    await callback.message.answer(t["commissions_recalculated"].format(count=count))
    await callback.answer()


@router.callback_query(F.data.startswith("delete_portfolio:"))
async def delete_portfolio_start(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    portfolio_id = int(callback.data.split(":")[1])
    portfolio = await ctx.repo.get_portfolio(portfolio_id, user.telegram_id)
    if not portfolio:
        await callback.answer()
        return
    await state.update_data(portfolio_id=portfolio_id, portfolio_name=portfolio.name)
    await state.set_state(PortfolioManageStates.confirm_delete)
    await callback.message.answer(
        t["confirm_delete"].format(name=portfolio.name),
        reply_markup=yes_no_keyboard(lang),
    )
    await callback.answer()


@router.callback_query(PortfolioManageStates.confirm_delete, F.data.in_({"yes", "no"}))
async def delete_portfolio_finish(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    if callback.data == "no":
        await state.clear()
        await callback.message.edit_text(t["cancel"])
        await callback.answer()
        return
    form = await state.get_data()
    deleted_id = form["portfolio_id"]
    await ctx.repo.delete_portfolio(deleted_id, user.telegram_id)
    if user.last_portfolio_id == deleted_id:
        user.last_portfolio_id = None
        remaining = await ctx.repo.get_portfolios(user.telegram_id)
        if remaining:
            user.last_portfolio_id = remaining[0].id
        await ctx.repo.update_user(user)
    await state.clear()
    await callback.message.edit_text(t["deleted"])
    await _show_portfolios_list(callback.message, ctx, user, lang, t)
    await callback.answer()
