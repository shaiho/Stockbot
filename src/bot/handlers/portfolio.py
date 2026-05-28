from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from src.bot.common import (
    MENU_HISTORY,
    MENU_HOLDINGS,
    MENU_MONTHLY,
    MENU_PORTFOLIO,
    MENU_PNL,
    MENU_QUOTE,
    MENU_TAX,
    get_user_lang,
)
from src.bot.keyboards import (
    holdings_shortcuts_keyboard,
    portfolio_picker_keyboard,
    trade_history_manage_keyboard,
    year_keyboard,
)
from src.bot.portfolio_flow import resolve_portfolio, show_portfolio_picker, touch_portfolio
from src.bot.states import HistoryStates, MonthlyStates, PnlStates, QuoteStates, TaxStates, TradeStates
from src.portfolio.allocation import compute_allocation
from src.portfolio.benchmark import compute_benchmark_comparison
from src.portfolio.formatter import (
    HTML,
    format_holdings,
    format_monthly_report,
    format_portfolio_summary,
    format_portfolio_summary_parts,
    format_quote,
    format_stock_pnl,
    format_tax_report,
    format_trade_history,
)
from src.portfolio.returns import compute_period_returns

router = Router()


def _pnl_actions_keyboard(
    t: dict, portfolio_id: int, symbol: str, market: str
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t["trade_history"],
                    callback_data=f"history:{portfolio_id}:{symbol}",
                ),
                InlineKeyboardButton(
                    text=t["quick_alert"],
                    callback_data=f"quick_alert:{symbol}:{market}",
                ),
            ]
        ]
    )


async def _send_symbol_pnl(message, ctx, user, t, portfolio_id: int, symbol: str) -> None:
    await touch_portfolio(ctx.repo, user, portfolio_id)
    trades = await ctx.repo.get_trades_for_symbol(portfolio_id, symbol)
    if not trades:
        await message.answer(t["no_trades"])
        return
    market = trades[0].market
    quote = await ctx.prices.get_quote(symbol, market)
    pnl = await ctx.calculator.compute_symbol_pnl(trades, symbol, quote)
    await message.answer(
        format_stock_pnl(pnl, t),
        reply_markup=_pnl_actions_keyboard(t, portfolio_id, symbol, market),
    )


async def _send_trade_history(message: Message, ctx, user, lang, t, portfolio_id: int, symbol: str) -> None:
    portfolio = await ctx.repo.get_portfolio(portfolio_id, user.telegram_id)
    if not portfolio:
        return
    trades = await ctx.repo.get_trades_for_symbol(portfolio_id, symbol)
    if not trades:
        await message.answer(t["no_trades"])
        return
    parts = format_trade_history(trades, symbol, portfolio.name, t)
    for i, part in enumerate(parts):
        kb = trade_history_manage_keyboard(trades, t) if i == len(parts) - 1 else None
        await message.answer(part, reply_markup=kb)


async def _require_portfolios(message: Message, ctx, user, lang, t):
    portfolios = await ctx.repo.get_portfolios(user.telegram_id)
    if not portfolios:
        await message.answer(t["choose_portfolio"], reply_markup=portfolio_picker_keyboard([], lang, include_new=True))
        return None
    if len(portfolios) == 1:
        return portfolios[0]
    await message.answer(
        t["choose_portfolio"],
        reply_markup=portfolio_picker_keyboard(portfolios, lang),
    )
    return None


@router.message(F.text.in_(MENU_PORTFOLIO))
async def menu_portfolio(message: Message, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    portfolios = await ctx.repo.get_portfolios(user.telegram_id)
    only = resolve_portfolio(user, portfolios)
    if only:
        await touch_portfolio(ctx.repo, user, only.id)
        await _send_summary(message, ctx, user, lang, t, only.id)
        return
    if not portfolios:
        await show_portfolio_picker(
            message, [], lang, t, action="portfolio_summary", include_new=True
        )
        return
    await show_portfolio_picker(message, portfolios, lang, t, action="portfolio_summary")


@router.callback_query(StateFilter(None), F.data.startswith("portfolio_summary:"))
async def pick_portfolio(callback: CallbackQuery, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    portfolio_id = int(callback.data.split(":")[1])
    await touch_portfolio(ctx.repo, user, portfolio_id)

    # Determine intent from FSM or default to summary
    await _send_summary(callback.message, ctx, user, lang, t, portfolio_id, edit=True)
    await callback.answer()


async def _send_summary(message, ctx, user, lang, t, portfolio_id, edit=False):
    portfolio = await ctx.repo.get_portfolio(portfolio_id, user.telegram_id)
    if not portfolio:
        return
    holdings = await ctx.repo.get_holdings(portfolio_id)
    trades = await ctx.repo.get_trades(portfolio_id)
    cash_ils, cash_usd = await ctx.repo.get_cash_balances(portfolio_id)
    summary = await ctx.calculator.compute_summary(
        holdings,
        trades,
        cash_ils,
        cash_usd,
        portfolio.opening_cash_ils,
        portfolio.opening_cash_usd,
    )
    fx = summary.fx_rate

    async def to_ils(amount: float, currency: str) -> float:
        if currency == "ILS":
            return amount
        return amount * fx

    period = await compute_period_returns(trades, to_ils)
    allocation = await compute_allocation(holdings, cash_ils, cash_usd, ctx.prices)
    benchmark = await compute_benchmark_comparison(summary, ctx.prices)
    text_parts = format_portfolio_summary_parts(
        summary,
        portfolio.name,
        t,
        period=period,
        allocation=allocation,
        benchmark=benchmark,
    )
    if edit:
        await message.edit_text(text_parts[0], parse_mode=HTML)
        for part in text_parts[1:]:
            await message.answer(part, parse_mode=HTML)
    else:
        for part in text_parts:
            await message.answer(part, parse_mode=HTML)


async def _send_monthly_report(message, ctx, user, lang, t, portfolio_id: int) -> None:
    from datetime import datetime

    portfolio = await ctx.repo.get_portfolio(portfolio_id, user.telegram_id)
    if not portfolio:
        return
    holdings = await ctx.repo.get_holdings(portfolio_id)
    trades = await ctx.repo.get_trades(portfolio_id)
    cash_ils, cash_usd = await ctx.repo.get_cash_balances(portfolio_id)
    summary = await ctx.calculator.compute_summary(
        holdings,
        trades,
        cash_ils,
        cash_usd,
        portfolio.opening_cash_ils,
        portfolio.opening_cash_usd,
    )
    fx = summary.fx_rate

    async def to_ils(amount: float, currency: str) -> float:
        if currency == "ILS":
            return amount
        return amount * fx

    period = await compute_period_returns(trades, to_ils)
    allocation = await compute_allocation(holdings, cash_ils, cash_usd, ctx.prices)
    month_label = datetime.now().strftime("%m/%Y")
    text = format_monthly_report(
        summary,
        portfolio.name,
        t,
        period=period,
        allocation=allocation,
        month_label=month_label,
    )
    await message.answer(text, parse_mode=HTML)


@router.message(F.text.in_(MENU_MONTHLY))
async def menu_monthly(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    portfolios = await ctx.repo.get_portfolios(user.telegram_id)
    only = resolve_portfolio(user, portfolios)
    if only:
        await touch_portfolio(ctx.repo, user, only.id)
        await state.clear()
        await _send_monthly_report(message, ctx, user, lang, t, only.id)
        return
    if not portfolios:
        await show_portfolio_picker(message, [], lang, t, include_new=True)
        return
    await state.set_state(MonthlyStates.portfolio)
    await show_portfolio_picker(message, portfolios, lang, t, action="monthly_portfolio")


@router.callback_query(MonthlyStates.portfolio, F.data.startswith("monthly_portfolio:"))
async def monthly_pick_portfolio(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    portfolio_id = int(callback.data.split(":")[1])
    await state.clear()
    await _send_monthly_report(callback.message, ctx, user, lang, t, portfolio_id)
    await callback.answer()


@router.message(F.text.in_(MENU_HOLDINGS))
async def menu_holdings(message: Message, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    portfolios = await ctx.repo.get_portfolios(user.telegram_id)
    only = resolve_portfolio(user, portfolios)
    if only:
        await touch_portfolio(ctx.repo, user, only.id)
        await _send_holdings(message, ctx, user, lang, t, only.id)
        return
    if not portfolios:
        await show_portfolio_picker(
            message, [], lang, t, action="portfolio_holdings", include_new=True
        )
        return
    await show_portfolio_picker(message, portfolios, lang, t, action="portfolio_holdings")


@router.callback_query(StateFilter(None), F.data.startswith("portfolio_holdings:"))
async def pick_holdings(callback: CallbackQuery, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    portfolio_id = int(callback.data.split(":")[1])
    await callback.message.edit_text(t["holdings"])
    await _send_holdings(callback.message, ctx, user, lang, t, portfolio_id)
    await callback.answer()


async def _send_holdings(message, ctx, user, lang, t, portfolio_id):
    portfolio = await ctx.repo.get_portfolio(portfolio_id, user.telegram_id)
    if not portfolio:
        return
    holdings = await ctx.repo.get_holdings(portfolio_id)
    trades = await ctx.repo.get_trades(portfolio_id)
    cash_ils, cash_usd = await ctx.repo.get_cash_balances(portfolio_id)
    summary = await ctx.calculator.compute_summary(
        holdings,
        trades,
        cash_ils,
        cash_usd,
        portfolio.opening_cash_ils,
        portfolio.opening_cash_usd,
    )
    kb = holdings_shortcuts_keyboard(portfolio_id, summary.holdings, t) if summary.holdings else None
    await message.answer(format_holdings(summary, portfolio.name, t), reply_markup=kb, parse_mode=HTML)


@router.callback_query(F.data.startswith("hold:pnl:"))
async def hold_pnl(callback: CallbackQuery, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    parts = callback.data.split(":")
    portfolio_id = int(parts[2])
    symbol = parts[3]
    trades = await ctx.repo.get_trades_for_symbol(portfolio_id, symbol)
    if not trades:
        await callback.answer(t["no_trades"], show_alert=True)
        return
    market = trades[0].market
    quote = await ctx.prices.get_quote(symbol, market)
    pnl = await ctx.calculator.compute_symbol_pnl(trades, symbol, quote)
    await callback.message.answer(
        format_stock_pnl(pnl, t),
        reply_markup=_pnl_actions_keyboard(t, portfolio_id, symbol, market),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("hold:hist:"))
async def hold_history(callback: CallbackQuery, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    parts = callback.data.split(":")
    portfolio_id = int(parts[2])
    symbol = parts[3]
    await _send_trade_history(callback.message, ctx, user, lang, t, portfolio_id, symbol)
    await callback.answer()


@router.callback_query(F.data.startswith("hold:quote:"))
async def hold_quote(callback: CallbackQuery, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    parts = callback.data.split(":")
    portfolio_id = int(parts[2])
    symbol = parts[3]
    market = parts[4]
    quote = await ctx.prices.get_quote(symbol, market)
    if not quote:
        await callback.answer(t["price_unavailable"], show_alert=True)
        return
    await callback.message.answer(format_quote(quote, t))
    await callback.answer()


@router.callback_query(F.data.startswith("hold:sell:"))
async def hold_sell(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    parts = callback.data.split(":")
    portfolio_id = int(parts[2])
    symbol = parts[3]
    market = parts[4]
    portfolio = await ctx.repo.get_portfolio(portfolio_id, user.telegram_id)
    if not portfolio:
        await callback.answer(t["no_portfolios"], show_alert=True)
        return
    await state.update_data(
        portfolio_id=portfolio_id,
        symbol=symbol,
        market=market,
        action="sell",
    )
    await state.set_state(TradeStates.quantity)
    await callback.message.answer(t["shortcut_sell_prompt"].format(symbol=symbol))
    await callback.answer()


@router.callback_query(F.data.startswith("hold:noop:"))
async def hold_noop(callback: CallbackQuery, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    await callback.answer(t["holdings_shortcuts_hint"], show_alert=True)


@router.message(F.text.in_(MENU_QUOTE))
async def menu_quote(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    await state.set_state(QuoteStates.symbol)
    await message.answer(t["enter_symbol"])


@router.message(QuoteStates.symbol)
async def quote_symbol(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    symbol = (message.text or "").strip().upper()
    await state.update_data(symbol=symbol)
    await state.set_state(QuoteStates.market)
    from src.bot.keyboards import market_keyboard

    await message.answer(t["choose_market"], reply_markup=market_keyboard(lang))


@router.callback_query(QuoteStates.market, F.data.startswith("market:"))
async def quote_market(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    form = await state.get_data()
    market = callback.data.split(":")[1]
    quote = await ctx.prices.get_quote(form["symbol"], market)
    await state.clear()
    if not quote:
        await callback.message.edit_text(t["price_unavailable"])
    else:
        await callback.message.edit_text(format_quote(quote, t))
    await callback.answer()


@router.message(F.text.in_(MENU_PNL))
async def menu_pnl(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    portfolios = await ctx.repo.get_portfolios(user.telegram_id)
    only = resolve_portfolio(user, portfolios)
    if only:
        await touch_portfolio(ctx.repo, user, only.id)
        await state.update_data(portfolio_id=only.id)
        await state.set_state(PnlStates.symbol)
        await message.answer(t["enter_symbol"])
        return
    if not portfolios:
        await show_portfolio_picker(message, [], lang, t, include_new=True)
        return
    await state.set_state(PnlStates.portfolio)
    await show_portfolio_picker(message, portfolios, lang, t)


@router.callback_query(PnlStates.portfolio, F.data.startswith("pick_portfolio:"))
async def pnl_pick_portfolio(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    portfolio_id = int(callback.data.split(":")[1])
    await touch_portfolio(ctx.repo, user, portfolio_id)
    form = await state.get_data()
    pending = form.get("pending_symbol")
    if pending:
        await state.clear()
        await _send_symbol_pnl(callback.message, ctx, user, t, portfolio_id, pending.upper())
    else:
        await state.update_data(portfolio_id=portfolio_id)
        await state.set_state(PnlStates.symbol)
        await callback.message.edit_text(t["enter_symbol"])
    await callback.answer()


@router.message(PnlStates.symbol)
async def pnl_symbol(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    form = await state.get_data()
    portfolio_id = form["portfolio_id"]
    symbol = (message.text or "").strip().upper()
    await state.clear()
    await _send_symbol_pnl(message, ctx, user, t, portfolio_id, symbol)


@router.message(F.text.in_(MENU_HISTORY))
async def menu_history(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    portfolios = await ctx.repo.get_portfolios(user.telegram_id)
    only = resolve_portfolio(user, portfolios)
    if only:
        await touch_portfolio(ctx.repo, user, only.id)
        await state.update_data(portfolio_id=only.id)
        await state.set_state(HistoryStates.symbol)
        await message.answer(t["history_enter_symbol"])
        return
    if not portfolios:
        await show_portfolio_picker(message, [], lang, t, include_new=True)
        return
    await state.set_state(HistoryStates.portfolio)
    await show_portfolio_picker(message, portfolios, lang, t, action="history_portfolio")


@router.callback_query(HistoryStates.portfolio, F.data.startswith("history_portfolio:"))
async def history_pick_portfolio(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    portfolio_id = int(callback.data.split(":")[1])
    await state.update_data(portfolio_id=portfolio_id)
    await state.set_state(HistoryStates.symbol)
    await callback.message.edit_text(t["history_enter_symbol"])
    await callback.answer()


@router.message(HistoryStates.symbol)
async def history_symbol(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    form = await state.get_data()
    symbol = (message.text or "").strip().upper()
    await state.clear()
    await _send_trade_history(message, ctx, user, lang, t, form["portfolio_id"], symbol)


@router.callback_query(F.data.startswith("history:"))
async def history_callback(callback: CallbackQuery, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    parts = callback.data.split(":")
    portfolio_id = int(parts[1])
    symbol = parts[2]
    await _send_trade_history(callback.message, ctx, user, lang, t, portfolio_id, symbol)
    await callback.answer()


@router.message(F.text.in_(MENU_TAX))
async def menu_tax(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    portfolios = await ctx.repo.get_portfolios(user.telegram_id)
    only = resolve_portfolio(user, portfolios)
    if only:
        await touch_portfolio(ctx.repo, user, only.id)
        await state.update_data(portfolio_id=only.id)
        await state.set_state(TaxStates.year)
        from datetime import datetime

        years = list(range(datetime.now().year, datetime.now().year - 5, -1))
        await message.answer(t["choose_year"], reply_markup=year_keyboard(years))
        return
    if not portfolios:
        await show_portfolio_picker(message, [], lang, t, include_new=True)
        return
    await state.set_state(TaxStates.portfolio)
    await show_portfolio_picker(message, portfolios, lang, t)


@router.callback_query(TaxStates.portfolio, F.data.startswith("pick_portfolio:"))
async def tax_pick_portfolio(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    portfolio_id = int(callback.data.split(":")[1])
    await state.update_data(portfolio_id=portfolio_id)
    await state.set_state(TaxStates.year)
    from datetime import datetime

    years = list(range(datetime.now().year, datetime.now().year - 5, -1))
    await callback.message.edit_text(t["choose_year"], reply_markup=year_keyboard(years))
    await callback.answer()


@router.callback_query(TaxStates.year, F.data.startswith("tax_year:"))
async def tax_year(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    form = await state.get_data()
    year = int(callback.data.split(":")[1])
    portfolio = await ctx.repo.get_portfolio(form["portfolio_id"], user.telegram_id)
    trades = await ctx.repo.get_trades(form["portfolio_id"])
    report = await ctx.calculator.compute_tax_report(trades, year)
    await state.clear()
    await callback.message.edit_text(format_tax_report(report, portfolio.name, t))
    await callback.answer()
