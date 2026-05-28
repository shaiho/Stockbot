from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from src.bot.common import MENU_ALERTS, get_user_lang
from src.bot.keyboards import (
    alert_direction_keyboard,
    alert_scope_keyboard,
    alert_type_keyboard,
    market_keyboard,
)
from src.bot.portfolio_flow import resolve_portfolio, show_portfolio_picker, touch_portfolio
from src.bot.states import AlertStates

router = Router()

STOCK_TYPES = {"pct_daily", "price_target", "premarket", "afterhours", "volume_spike"}
THRESHOLD_TYPES = {"pct_daily", "premarket", "afterhours", "portfolio_value_change", "daily_loss_limit"}
VOLUME_DEFAULT_MULT = 2.0


def _has_stock_alert(rules, symbol: str, market: str, alert_type: str = "pct_daily") -> bool:
    for rule in rules:
        if rule.alert_type != alert_type or not rule.enabled:
            continue
        cfg = rule.config
        if cfg.get("symbol") == symbol and cfg.get("market") == market:
            return True
    return False


async def _create_pct_alert(ctx, user, symbol: str, market: str, threshold: float) -> None:
    await ctx.repo.add_alert_rule(
        user.telegram_id,
        "stock",
        "pct_daily",
        {"symbol": symbol, "market": market, "threshold_pct": threshold},
    )


async def _continue_alert_portfolio(message: Message, state, form, t, *, edit: bool = False) -> None:
    alert_type = form["alert_type"]
    if alert_type == "pnl_milestone":
        await state.set_state(AlertStates.milestone)
        text = t["alert_milestone_prompt"]
    else:
        await state.set_state(AlertStates.threshold)
        text = t["alert_threshold_prompt"]
    if edit:
        await message.edit_text(text)
    else:
        await message.answer(text)


def _rule_label(rule, t: dict) -> str:
    labels = {
        "pct_daily": t["alert_type_pct_daily"],
        "price_target": t["alert_type_price_target"],
        "premarket": t["alert_type_premarket"],
        "afterhours": t["alert_type_afterhours"],
        "volume_spike": t["alert_type_volume"],
        "news": t["alert_type_news"],
        "portfolio_value_change": t["alert_type_value_change"],
        "daily_loss_limit": t["alert_type_daily_loss"],
        "pnl_milestone": t["alert_type_pnl_milestone"],
    }
    label = labels.get(rule.alert_type, rule.alert_type)
    cfg = rule.config
    if rule.scope in ("stock", "watchlist") and cfg.get("symbol"):
        return f"{label}: {cfg['symbol']}"
    if rule.scope == "portfolio" and cfg.get("portfolio_id"):
        return f"{label}: #{cfg['portfolio_id']}"
    return label


async def _show_alerts(message: Message, ctx, user, lang, t) -> None:
    rules = await ctx.repo.get_alert_rules(user.telegram_id)
    rows = [
        [InlineKeyboardButton(text=f"❌ {_rule_label(r, t)}", callback_data=f"alert_delete:{r.id}")]
        for r in rules
        if r.enabled
    ]
    rows.append([InlineKeyboardButton(text=t["add_alert"], callback_data="alert_add")])
    rows.insert(
        0,
        [InlineKeyboardButton(text=t["smart_alerts_holdings"], callback_data="alert_smart_holdings")],
    )
    text = "🔔 " + t["alerts"]
    if not rules:
        text += "\n\n" + t["alerts_empty"]
    else:
        lines = [f"• {_rule_label(r, t)}" for r in rules if r.enabled]
        text += "\n\n" + "\n".join(lines)
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.message(F.text.in_(MENU_ALERTS))
async def menu_alerts(message: Message, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    await _show_alerts(message, ctx, user, lang, t)


@router.callback_query(F.data == "alert_add")
async def alert_add_start(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    await state.set_state(AlertStates.scope)
    await callback.message.answer(
        t["choose_alert_scope"],
        reply_markup=alert_scope_keyboard(t),
    )
    await callback.answer()


@router.callback_query(AlertStates.scope, F.data.startswith("alert_scope:"))
async def alert_pick_scope(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    scope = callback.data.split(":")[1]
    await state.update_data(scope=scope)
    await state.set_state(AlertStates.alert_type)
    await callback.message.edit_text(
        t["choose_alert_type"],
        reply_markup=alert_type_keyboard(scope, t),
    )
    await callback.answer()


@router.callback_query(AlertStates.alert_type, F.data.startswith("alert_type:"))
async def alert_pick_type(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    alert_type = callback.data.split(":")[1]
    form = await state.get_data()
    scope = form["scope"]
    await state.update_data(alert_type=alert_type)

    if scope == "portfolio":
        portfolios = await ctx.repo.get_portfolios(user.telegram_id)
        if not portfolios:
            await state.clear()
            await callback.message.edit_text(t["no_portfolios"])
            await callback.answer()
            return
        only = resolve_portfolio(user, portfolios)
        if only:
            await state.update_data(portfolio_id=only.id)
            form = await state.get_data()
            await _continue_alert_portfolio(callback.message, state, form, t, edit=True)
            await callback.answer()
            return
        await state.set_state(AlertStates.portfolio)
        await show_portfolio_picker(
            callback.message, portfolios, lang, t, action="alert_portfolio", edit=True
        )
        await callback.answer()
        return

    if alert_type == "news":
        watchlist = await ctx.repo.get_watchlist(user.telegram_id)
        if not watchlist:
            await state.clear()
            await callback.message.edit_text(t["watchlist_empty"])
            await callback.answer()
            return
        rows = [
            [InlineKeyboardButton(text=item.symbol, callback_data=f"alert_symbol:{item.symbol}:{item.market}")]
            for item in watchlist
        ]
        await state.set_state(AlertStates.symbol)
        await callback.message.edit_text(t["enter_symbol"], reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
        await callback.answer()
        return

    if scope == "watchlist":
        watchlist = await ctx.repo.get_watchlist(user.telegram_id)
        if watchlist:
            rows = [
                [InlineKeyboardButton(text=item.symbol, callback_data=f"alert_symbol:{item.symbol}:{item.market}")]
                for item in watchlist
            ]
            rows.append(
                [InlineKeyboardButton(text=t["enter_symbol"], callback_data="alert_symbol:manual")]
            )
            await state.set_state(AlertStates.symbol)
            await callback.message.edit_text(
                t["enter_symbol"],
                reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            )
            await callback.answer()
            return

    await state.set_state(AlertStates.symbol)
    await callback.message.edit_text(t["enter_symbol"])
    await callback.answer()


@router.callback_query(F.data.startswith("alert_symbol:"))
async def alert_pick_symbol(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    parts = callback.data.split(":")
    if parts[1] == "manual":
        await callback.message.edit_text(t["enter_symbol"])
        await callback.answer()
        return
    symbol = parts[1]
    market = parts[2] if len(parts) > 2 else "US"
    await state.update_data(symbol=symbol, market=market)
    form = await state.get_data()
    await _continue_after_symbol(callback.message, state, ctx, user, form, t, lang)
    await callback.answer()


@router.message(AlertStates.symbol)
async def alert_symbol_text(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    symbol = (message.text or "").strip().upper()
    await state.update_data(symbol=symbol)
    form = await state.get_data()
    if form.get("scope") == "stock" and form.get("alert_type") != "news":
        await state.set_state(AlertStates.market)
        await message.answer(t["choose_market"], reply_markup=market_keyboard(lang))
        return
    await state.update_data(market="US")
    form = await state.get_data()
    await _continue_after_symbol(message, state, ctx, user, form, t, lang)


@router.callback_query(AlertStates.market, F.data.startswith("market:"))
async def alert_market(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    market = callback.data.split(":")[1]
    await state.update_data(market=market)
    form = await state.get_data()
    await _continue_after_symbol(callback.message, state, ctx, user, form, t, lang)
    await callback.answer()


@router.callback_query(AlertStates.portfolio, F.data.startswith("alert_portfolio:"))
async def alert_pick_portfolio(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    portfolio_id = int(callback.data.split(":")[1])
    await state.update_data(portfolio_id=portfolio_id)
    form = await state.get_data()
    await _continue_alert_portfolio(callback.message, state, form, t, edit=True)
    await callback.answer()


async def _save_alert(message: Message, state, ctx, user, form, t, config: dict) -> None:
    await ctx.repo.add_alert_rule(
        user_id=user.telegram_id,
        scope=form["scope"],
        alert_type=form["alert_type"],
        config=config,
    )
    await state.clear()
    await message.answer(t["alert_created"])


async def _continue_after_symbol(message: Message, state, ctx, user, form, t, lang) -> None:
    alert_type = form["alert_type"]
    if alert_type == "price_target":
        await state.set_state(AlertStates.target_price)
        await message.answer(t["alert_target_prompt"])
    elif alert_type in THRESHOLD_TYPES:
        await state.set_state(AlertStates.threshold)
        await message.answer(t["alert_threshold_prompt"])
    elif alert_type == "volume_spike":
        config = {
            "symbol": form["symbol"],
            "market": form.get("market", "US"),
            "multiplier": VOLUME_DEFAULT_MULT,
        }
        await _save_alert(message, state, ctx, user, form, t, config)
    elif alert_type == "news":
        config = {"symbol": form["symbol"], "market": form.get("market", "US")}
        await _save_alert(message, state, ctx, user, form, t, config)


@router.message(AlertStates.target_price)
async def alert_target_price(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    try:
        target = float((message.text or "").replace(",", ""))
    except ValueError:
        await message.answer(t["invalid_number"])
        return
    await state.update_data(target_price=target)
    await state.set_state(AlertStates.direction)
    await message.answer(t["alert_direction_prompt"], reply_markup=alert_direction_keyboard(t))


@router.callback_query(AlertStates.direction, F.data.startswith("alert_direction:"))
async def alert_direction(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    direction = callback.data.split(":")[1]
    form = await state.get_data()
    config = {
        "symbol": form["symbol"],
        "market": form.get("market", "US"),
        "target_price": form["target_price"],
        "direction": direction,
    }
    await _save_alert(callback.message, state, ctx, user, form, t, config)
    await callback.answer()


@router.message(AlertStates.threshold)
async def alert_threshold(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    try:
        threshold = float((message.text or "").replace(",", ""))
    except ValueError:
        await message.answer(t["invalid_number"])
        return
    form = await state.get_data()
    config: dict = {}
    alert_type = form["alert_type"]
    scope = form["scope"]

    if scope in ("stock", "watchlist"):
        config["symbol"] = form["symbol"]
        config["market"] = form.get("market", "US")
        config["threshold_pct"] = threshold
    elif scope == "portfolio":
        config["portfolio_id"] = form["portfolio_id"]
        config["threshold_pct"] = threshold

    await _save_alert(message, state, ctx, user, form, t, config)


@router.message(AlertStates.milestone)
async def alert_milestone(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    try:
        amount = float((message.text or "").replace(",", ""))
    except ValueError:
        await message.answer(t["invalid_number"])
        return
    form = await state.get_data()
    config = {"portfolio_id": form["portfolio_id"], "threshold_ils": amount}
    await _save_alert(message, state, ctx, user, form, t, config)


@router.callback_query(F.data.startswith("alert_delete:"))
async def alert_delete(callback: CallbackQuery, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    rule_id = int(callback.data.split(":")[1])
    await ctx.repo.delete_alert_rule(rule_id, user.telegram_id)
    await callback.answer(t["alert_deleted"])
    await callback.message.edit_text(t["alert_deleted"])


@router.callback_query(F.data.startswith("quick_alert:"))
async def quick_alert(callback: CallbackQuery, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    parts = callback.data.split(":")
    symbol = parts[1]
    market = parts[2]
    rules = await ctx.repo.get_alert_rules(user.telegram_id)
    if _has_stock_alert(rules, symbol, market):
        await callback.answer(t["alert_exists"], show_alert=True)
        return
    await _create_pct_alert(ctx, user, symbol, market, user.mover_threshold_pct)
    await callback.answer(t["alert_created"])


@router.callback_query(F.data == "alert_smart_holdings")
async def alert_smart_holdings(callback: CallbackQuery, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    portfolios = await ctx.repo.get_portfolios(user.telegram_id)
    portfolio = resolve_portfolio(user, portfolios)
    if not portfolio:
        await callback.answer(t["choose_portfolio"], show_alert=True)
        return
    await touch_portfolio(ctx.repo, user, portfolio.id)
    holdings = await ctx.repo.get_holdings(portfolio.id)
    if not holdings:
        await callback.answer(t["no_holdings"], show_alert=True)
        return
    rules = await ctx.repo.get_alert_rules(user.telegram_id)
    threshold = user.mover_threshold_pct
    created = 0
    for holding in holdings:
        if _has_stock_alert(rules, holding.symbol, holding.market):
            continue
        await _create_pct_alert(ctx, user, holding.symbol, holding.market, threshold)
        created += 1
    if created == 0:
        await callback.answer(t["alert_exists"], show_alert=True)
        return
    await callback.message.answer(
        t["smart_alerts_created"].format(count=created, threshold=threshold)
    )
    await callback.answer()
