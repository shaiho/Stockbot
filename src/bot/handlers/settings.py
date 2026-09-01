from __future__ import annotations

import re

from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from src.bot.common import MENU_SETTINGS, get_user_lang
from src.bot.keyboards import (
    currency_keyboard,
    language_keyboard,
    settings_menu_keyboard,
    zero_or_custom_keyboard,
)
from src.bot.portfolio_flow import resolve_portfolio, show_portfolio_picker, touch_portfolio
from src.bot.states import ExportStates, ImportStates, SettingsStates
from src.portfolio.exporter import export_portfolio_json
from src.portfolio.importer import parse_portfolio_import
from src.portfolio.trade_date import parse_trade_date

router = Router()
TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _settings_text(user, t: dict) -> str:
    return (
        f"⚙️ {t['settings']}\n\n"
        f"{t['settings_lang_label']}: {user.language}\n"
        f"{t['settings_commission_label']}: {user.default_commission} {user.default_commission_currency}\n"
        f"{t['settings_reports_label']}: {user.report_morning} / {user.report_evening}\n"
        f"{t['settings_mover_label']}: {user.mover_threshold_pct}%"
    )


@router.message(F.text.in_(MENU_SETTINGS))
async def menu_settings(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    await state.set_state(SettingsStates.menu)
    await message.answer(_settings_text(user, t), reply_markup=settings_menu_keyboard(t))


@router.callback_query(SettingsStates.menu, F.data == "settings:language")
async def settings_language(callback: CallbackQuery, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    await callback.message.edit_text(t["choose_language"], reply_markup=language_keyboard())
    await callback.answer()


@router.callback_query(SettingsStates.menu, F.data.startswith("lang:"))
async def settings_language_pick(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    new_lang = callback.data.split(":")[1]
    user.language = new_lang
    await ctx.repo.update_user(user)
    t = ctx.i18n.load(new_lang)
    await state.set_state(SettingsStates.menu)
    await callback.message.edit_text(
        t["settings_saved"] + "\n\n" + _settings_text(user, t),
        reply_markup=settings_menu_keyboard(t),
    )
    await callback.answer()


@router.callback_query(SettingsStates.menu, F.data == "settings:commission")
async def settings_commission_start(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    await state.set_state(SettingsStates.commission)
    await callback.message.edit_text(
        t["default_commission"],
        reply_markup=zero_or_custom_keyboard("commission", lang, prefix="settings"),
    )
    await callback.answer()


@router.callback_query(SettingsStates.commission, F.data.startswith("settings:commission:"))
async def settings_commission_pick(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    choice = callback.data.split(":")[2]
    if choice == "custom":
        await callback.message.edit_text(t["default_commission_custom_prompt"])
        await callback.answer()
        return
    user.default_commission = 0.0
    await ctx.repo.update_user(user)
    await state.set_state(SettingsStates.menu)
    await callback.message.edit_text(
        t["settings_saved"] + "\n\n" + _settings_text(user, t),
        reply_markup=settings_menu_keyboard(t),
    )
    await callback.answer()


@router.message(SettingsStates.commission)
async def settings_commission_value(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    try:
        commission = float((message.text or "").replace(",", ""))
    except ValueError:
        await message.answer(t["invalid_number"])
        return
    await state.update_data(commission=commission)
    await state.set_state(SettingsStates.commission_currency)
    await message.answer(t["default_commission_currency"], reply_markup=currency_keyboard(lang, prefix="settings:currency"))


@router.callback_query(SettingsStates.commission_currency, F.data.startswith("settings:currency:"))
async def settings_commission_currency(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    currency = callback.data.split(":")[2]
    form = await state.get_data()
    user.default_commission = form["commission"]
    user.default_commission_currency = currency
    await ctx.repo.update_user(user)
    await state.set_state(SettingsStates.menu)
    t = ctx.i18n.load(lang)
    await callback.message.edit_text(
        t["settings_saved"] + "\n\n" + _settings_text(user, t),
        reply_markup=settings_menu_keyboard(t),
    )
    await callback.answer()


@router.callback_query(SettingsStates.menu, F.data == "settings:reports")
async def settings_reports_start(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    await state.set_state(SettingsStates.report_morning)
    await callback.message.edit_text(t["report_morning_prompt"])
    await callback.answer()


@router.message(SettingsStates.report_morning)
async def settings_report_morning(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    value = (message.text or "").strip()
    if not TIME_RE.match(value):
        await message.answer(t["invalid_time"])
        return
    await state.update_data(report_morning=value)
    await state.set_state(SettingsStates.report_evening)
    await message.answer(t["report_evening_prompt"])


@router.message(SettingsStates.report_evening)
async def settings_report_evening(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    value = (message.text or "").strip()
    if not TIME_RE.match(value):
        await message.answer(t["invalid_time"])
        return
    form = await state.get_data()
    user.report_morning = form["report_morning"]
    user.report_evening = value
    await ctx.repo.update_user(user)
    await state.set_state(SettingsStates.menu)
    await message.answer(
        t["settings_saved"] + "\n\n" + _settings_text(user, t),
        reply_markup=settings_menu_keyboard(t),
    )


@router.callback_query(SettingsStates.menu, F.data == "settings:mover")
async def settings_mover_start(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    await state.set_state(SettingsStates.mover_threshold)
    await callback.message.edit_text(t["mover_threshold_prompt"])
    await callback.answer()


@router.message(SettingsStates.mover_threshold)
async def settings_mover_value(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    try:
        threshold = float((message.text or "").replace(",", ""))
    except ValueError:
        await message.answer(t["invalid_number"])
        return
    user.mover_threshold_pct = threshold
    await ctx.repo.update_user(user)
    await state.set_state(SettingsStates.menu)
    await message.answer(
        t["settings_saved"] + "\n\n" + _settings_text(user, t),
        reply_markup=settings_menu_keyboard(t),
    )


@router.callback_query(SettingsStates.menu, F.data == "settings:import")
async def settings_import_start(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    portfolios = await ctx.repo.get_portfolios(user.telegram_id)
    if not portfolios:
        await callback.message.edit_text(t["no_portfolios"])
        await callback.answer()
        return
    only = resolve_portfolio(user, portfolios)
    if only:
        await state.update_data(portfolio_id=only.id)
        await state.set_state(ImportStates.json_data)
        await callback.message.edit_text(t["import_send_json"])
        await callback.answer()
        return
    await state.set_state(ImportStates.portfolio)
    await show_portfolio_picker(
        callback.message,
        portfolios,
        lang,
        t,
        action="import_portfolio",
        prompt_key="import_pick_portfolio",
        edit=True,
    )
    await callback.answer()


@router.callback_query(ImportStates.portfolio, F.data.startswith("import_portfolio:"))
async def import_pick_portfolio(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    portfolio_id = int(callback.data.split(":")[1])
    await state.update_data(portfolio_id=portfolio_id)
    await state.set_state(ImportStates.json_data)
    await callback.message.edit_text(t["import_send_json"])
    await callback.answer()


@router.message(ImportStates.json_data, F.document)
async def import_json_file(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    if not message.document:
        return
    file = await message.bot.download(message.document)
    raw = file.read().decode("utf-8")
    await _process_import(message, state, ctx, user, t, raw)


@router.message(ImportStates.json_data)
async def import_json_text(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    raw = message.text or ""
    await _process_import(message, state, ctx, user, t, raw)


async def _process_import(message, state, ctx, user, t, raw: str) -> None:
    form = await state.get_data()
    portfolio_id = form["portfolio_id"]
    portfolio = await ctx.repo.get_portfolio(portfolio_id, user.telegram_id)
    if not portfolio:
        await state.clear()
        await message.answer(t["import_failed"])
        return
    try:
        parsed = parse_portfolio_import(raw)
    except Exception:
        await message.answer(t["import_failed"])
        return

    await ctx.repo.update_portfolio_opening_cash(
        portfolio_id,
        user.telegram_id,
        parsed["cash_ils"],
        parsed["cash_usd"],
    )
    count = 0
    for item in parsed["holdings"]:
        if item["quantity"] <= 0:
            continue
        timestamp = None
        if item.get("date"):
            try:
                timestamp = parse_trade_date(str(item["date"]))
            except ValueError:
                await message.answer(t["import_failed"])
                return
        await ctx.repo.add_trade(
            portfolio_id=portfolio_id,
            symbol=item["symbol"],
            market=item["market"],
            asset_type=item["asset_type"],
            action="buy",
            quantity=item["quantity"],
            price=item["avg_cost"],
            currency=item["currency"],
            commission=0.0,
            note="import",
            timestamp=timestamp,
        )
        count += 1

    await state.clear()
    await message.answer(t["import_done"].format(holdings=count))


async def _send_portfolio_export(message, ctx, user, t, portfolio_id: int) -> None:
    portfolio = await ctx.repo.get_portfolio(portfolio_id, user.telegram_id)
    if not portfolio:
        await message.answer(t["no_portfolios"])
        return
    trades = await ctx.repo.get_trades(portfolio_id)
    cash_ils, cash_usd = await ctx.repo.get_cash_balances(portfolio_id)
    content = export_portfolio_json(portfolio, trades, cash_ils, cash_usd)
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in portfolio.name)
    doc = BufferedInputFile(
        content.encode("utf-8"),
        filename=f"{safe_name or 'portfolio'}.json",
    )
    await message.answer_document(doc, caption=t["export_done"])


@router.callback_query(SettingsStates.menu, F.data == "settings:export")
async def settings_export_start(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    portfolios = await ctx.repo.get_portfolios(user.telegram_id)
    if not portfolios:
        await callback.message.edit_text(t["no_portfolios"])
        await callback.answer()
        return
    only = resolve_portfolio(user, portfolios)
    if only:
        await _send_portfolio_export(callback.message, ctx, user, t, only.id)
        await callback.answer()
        return
    await state.set_state(ExportStates.portfolio)
    await show_portfolio_picker(
        callback.message,
        portfolios,
        lang,
        t,
        action="export_portfolio",
        prompt_key="export_pick_portfolio",
        edit=True,
    )
    await callback.answer()


@router.callback_query(ExportStates.portfolio, F.data.startswith("export_portfolio:"))
async def export_pick_portfolio(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    portfolio_id = int(callback.data.split(":")[1])
    await state.clear()
    await _send_portfolio_export(callback.message, ctx, user, t, portfolio_id)
    await callback.answer()
