from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.bot.common import get_user_lang, show_main_menu
from src.bot.symbol_flow import prompt_ambiguous_symbol, resolve_symbol_message
from src.bot.trade_helpers import prompt_trade_date, store_trade_date, store_trade_date_today
from src.portfolio.commission import calc_trade_commission
from src.bot.keyboards import (
    currency_keyboard,
    holdings_now_keyboard,
    language_keyboard,
    yes_no_keyboard,
    zero_or_custom_keyboard,
)
from src.bot.states import OnboardingStates

router = Router()
logger = logging.getLogger(__name__)


async def _ask_cash_usd(message: Message, state: FSMContext, lang: str, t: dict, *, edit: bool = False) -> None:
    await state.set_state(OnboardingStates.opening_cash_usd)
    text = t["opening_cash_usd"]
    kb = zero_or_custom_keyboard("cash_usd", lang)
    if edit:
        await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


async def _ask_commission(message: Message, state: FSMContext, lang: str, t: dict, *, edit: bool = False) -> None:
    await state.set_state(OnboardingStates.default_commission)
    text = t["default_commission"]
    kb = zero_or_custom_keyboard("commission", lang)
    if edit:
        await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


async def _ask_commission_currency(
    message: Message, state: FSMContext, lang: str, t: dict, *, edit: bool = False
) -> None:
    await state.set_state(OnboardingStates.default_commission_currency)
    text = t["default_commission_currency"]
    kb = currency_keyboard(lang)
    if edit:
        await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


async def _create_portfolio_and_continue(
    message: Message,
    state: FSMContext,
    ctx,
    user,
    lang: str,
    t: dict,
    *,
    edit: bool = False,
) -> None:
    form = await state.get_data()
    try:
        portfolio = await ctx.repo.create_portfolio(
            user.telegram_id,
            form["portfolio_name"],
            form.get("opening_cash_ils", 0),
            form.get("opening_cash_usd", 0),
        )
    except ValueError as exc:
        target = message if not edit else message
        await target.answer(t.get(str(exc), t["duplicate_name"]))
        return

    user.last_portfolio_id = portfolio.id
    await ctx.repo.update_user(user)
    await state.update_data(portfolio_id=portfolio.id)
    await state.set_state(OnboardingStates.add_holdings_now)
    text = t["add_holdings_now"]
    kb = holdings_now_keyboard(lang)
    if edit:
        await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


async def _finish_onboarding(message: Message, state: FSMContext, ctx, user, lang: str, t: dict) -> None:
    user.onboarding_completed = True
    await ctx.repo.update_user(user)
    await state.clear()
    await show_main_menu(message, lang, t)


async def _save_onboarding_trade(
    message: Message,
    state: FSMContext,
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
        logger.exception("onboarding add_trade failed user=%s portfolio=%s", user.telegram_id, form.get("portfolio_id"))
        target = message if not edit else message
        await target.answer(t["action_failed"])
        return

    await state.set_state(OnboardingStates.add_another)
    text = t["add_another_holding"]
    kb = yes_no_keyboard(lang)
    if edit:
        await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, **data) -> None:
    ctx = data["ctx"]
    user = await ctx.repo.get_or_create_user(message.from_user.id)
    t = ctx.i18n.load(user.language)

    if not user.onboarding_completed:
        await state.set_state(OnboardingStates.language)
        await message.answer(t["welcome"])
        await message.answer(t["choose_language"], reply_markup=language_keyboard())
        return

    await state.clear()
    data["skip_menu_restore"] = True
    await show_main_menu(message, user.language, t)


@router.callback_query(OnboardingStates.language, F.data.startswith("lang:"))
async def choose_language(callback: CallbackQuery, state: FSMContext, **data) -> None:
    ctx = data["ctx"]
    lang = callback.data.split(":")[1]
    user = await ctx.repo.get_or_create_user(callback.from_user.id)
    user.language = lang
    await ctx.repo.update_user(user)
    t = ctx.i18n.load(lang)

    await state.set_state(OnboardingStates.portfolio_name)
    await callback.message.edit_text(t["portfolio_name_prompt"])
    await callback.answer()


@router.message(OnboardingStates.portfolio_name)
async def onboarding_portfolio_name(message: Message, state: FSMContext, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    name = (message.text or "").strip()
    if not name:
        await message.answer(t["portfolio_name_prompt"])
        return
    await state.update_data(portfolio_name=name, is_new_user=True)
    await state.set_state(OnboardingStates.opening_cash_ils)
    await message.answer(
        t["opening_cash_ils"],
        reply_markup=zero_or_custom_keyboard("cash_ils", lang),
    )


@router.callback_query(OnboardingStates.opening_cash_ils, F.data.startswith("ob:cash_ils:"))
async def onboarding_cash_ils_choice(callback: CallbackQuery, state: FSMContext, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    choice = callback.data.split(":")[2]

    if choice == "0":
        await state.update_data(opening_cash_ils=0.0)
        await _ask_cash_usd(callback.message, state, lang, t, edit=True)
    else:
        await state.set_state(OnboardingStates.opening_cash_ils_custom)
        await callback.message.edit_text(t["opening_cash_ils"] + "\n✏️")
    await callback.answer()


@router.message(OnboardingStates.opening_cash_ils_custom)
async def onboarding_cash_ils_custom(message: Message, state: FSMContext, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    try:
        cash = float((message.text or "0").replace(",", ""))
    except ValueError:
        await message.answer(t["invalid_number"])
        return
    await state.update_data(opening_cash_ils=cash)
    await _ask_cash_usd(message, state, lang, t)


@router.callback_query(OnboardingStates.opening_cash_usd, F.data.startswith("ob:cash_usd:"))
async def onboarding_cash_usd_choice(callback: CallbackQuery, state: FSMContext, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    choice = callback.data.split(":")[2]

    if choice == "0":
        await state.update_data(opening_cash_usd=0.0)
        await _ask_commission(callback.message, state, lang, t, edit=True)
    else:
        await state.set_state(OnboardingStates.opening_cash_usd_custom)
        await callback.message.edit_text(t["opening_cash_usd"] + "\n✏️")
    await callback.answer()


@router.message(OnboardingStates.opening_cash_usd_custom)
async def onboarding_cash_usd_custom(message: Message, state: FSMContext, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    try:
        cash = float((message.text or "0").replace(",", ""))
    except ValueError:
        await message.answer(t["invalid_number"])
        return
    await state.update_data(opening_cash_usd=cash)
    await _ask_commission(message, state, lang, t)


@router.callback_query(OnboardingStates.default_commission, F.data.startswith("ob:commission:"))
async def onboarding_commission_choice(callback: CallbackQuery, state: FSMContext, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    choice = callback.data.split(":")[2]

    if choice == "0":
        user.default_commission = 0.0
        await ctx.repo.update_user(user)
        await state.update_data(default_commission=0.0)
        await _ask_commission_currency(callback.message, state, lang, t, edit=True)
    else:
        await state.set_state(OnboardingStates.default_commission_custom)
        await callback.message.edit_text(t["default_commission"] + "\n✏️")
    await callback.answer()


@router.message(OnboardingStates.default_commission_custom)
async def onboarding_commission_custom(message: Message, state: FSMContext, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    try:
        commission = float((message.text or "0").replace(",", ""))
    except ValueError:
        await message.answer(t["invalid_number"])
        return
    user.default_commission = commission
    await ctx.repo.update_user(user)
    await state.update_data(default_commission=commission)
    await _ask_commission_currency(message, state, lang, t)


@router.callback_query(OnboardingStates.default_commission_currency, F.data.startswith("ob:currency:"))
async def onboarding_commission_currency(callback: CallbackQuery, state: FSMContext, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    currency = callback.data.split(":")[2]
    user.default_commission_currency = currency
    await ctx.repo.update_user(user)
    await _create_portfolio_and_continue(callback.message, state, ctx, user, lang, t, edit=True)
    await callback.answer()


@router.callback_query(OnboardingStates.add_holdings_now, F.data.startswith("ob:holdings:"))
async def onboarding_holdings_choice(callback: CallbackQuery, state: FSMContext, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)

    if callback.data.endswith(":no"):
        await callback.message.edit_text(t["onboarding_done"])
        await _finish_onboarding(callback.message, state, ctx, user, lang, t)
        await callback.answer()
        return

    await state.set_state(OnboardingStates.symbol)
    await callback.message.edit_text(t["add_holding_prompt"])
    await callback.answer()


@router.message(OnboardingStates.symbol)
async def onboarding_symbol(message: Message, state: FSMContext, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    raw = (message.text or "").strip()
    if not raw:
        await message.answer(t["add_holding_prompt"])
        return

    outcome = await resolve_symbol_message(message, ctx, raw)
    if outcome.kind == "resolved":
        await state.update_data(symbol=outcome.symbol, market=outcome.market)
        await state.set_state(OnboardingStates.quantity)
        await message.answer(t["quantity_prompt"])
        return
    if outcome.kind == "ambiguous":
        await prompt_ambiguous_symbol(
            message, state, OnboardingStates.market, outcome.symbol, t, lang
        )
        return
    await message.answer(t["symbol_not_found"])


@router.callback_query(OnboardingStates.market, F.data.startswith("market:"))
async def onboarding_market(callback: CallbackQuery, state: FSMContext, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    market = callback.data.split(":")[1]
    form = await state.get_data()
    quote = await ctx.prices.get_quote(form.get("symbol", ""), market)
    if not quote:
        await callback.answer(t["symbol_not_found"], show_alert=True)
        return
    await state.update_data(market=market)
    await state.set_state(OnboardingStates.quantity)
    await callback.message.edit_text(t["quantity_prompt"])
    await callback.answer()


@router.message(OnboardingStates.quantity)
async def onboarding_quantity(message: Message, state: FSMContext, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    try:
        qty = float((message.text or "").replace(",", ""))
    except ValueError:
        await message.answer(t["invalid_number"])
        return
    await state.update_data(quantity=qty)
    await state.set_state(OnboardingStates.price)
    await message.answer(t["price_prompt"])


@router.message(OnboardingStates.price)
async def onboarding_price(message: Message, state: FSMContext, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    try:
        price = float((message.text or "").replace(",", ""))
    except ValueError:
        await message.answer(t["invalid_number"])
        return

    await state.update_data(price=price)
    await prompt_trade_date(message, state, OnboardingStates.trade_date, t, lang)


@router.callback_query(OnboardingStates.trade_date, F.data == "trade_date:today")
async def onboarding_trade_date_today(callback: CallbackQuery, state: FSMContext, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    await store_trade_date_today(state)
    await _save_onboarding_trade(callback.message, state, ctx, user, lang, t, edit=True)
    await callback.answer()


@router.message(OnboardingStates.trade_date)
async def onboarding_trade_date(message: Message, state: FSMContext, **data) -> None:
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

    await _save_onboarding_trade(message, state, ctx, user, lang, t)


@router.callback_query(OnboardingStates.add_another, F.data.in_({"yes", "no"}))
async def onboarding_finish(callback: CallbackQuery, state: FSMContext, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)

    if callback.data == "yes":
        await state.set_state(OnboardingStates.symbol)
        await callback.message.edit_text(t["add_holding_prompt"])
        await callback.answer()
        return

    await callback.message.edit_text(t["onboarding_done"])
    await _finish_onboarding(callback.message, state, ctx, user, lang, t)
    await callback.answer()
