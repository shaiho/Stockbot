from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from src.bot.common import get_user_lang
from src.bot.handlers.portfolio import _send_symbol_pnl
from src.bot.portfolio_flow import resolve_portfolio, show_portfolio_picker, touch_portfolio
from src.bot.states import PnlStates, QuoteStates
from src.portfolio.formatter import format_quote

router = Router()


@router.message(Command("help"))
async def cmd_help(message: Message, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    if not user.onboarding_completed:
        return
    t = ctx.i18n.load(lang)
    await message.answer(t["help_commands"])


@router.message(Command("alerts"))
async def cmd_alerts(message: Message, **data) -> None:
    from src.bot.handlers.alerts import _show_alerts

    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    if not user.onboarding_completed:
        return
    t = ctx.i18n.load(lang)
    await _show_alerts(message, ctx, user, lang, t)


@router.message(Command("pnl"))
async def cmd_pnl(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    if not user.onboarding_completed:
        return
    t = ctx.i18n.load(lang)
    parts = (message.text or "").split(maxsplit=1)
    symbol = parts[1].strip().upper() if len(parts) > 1 else None

    portfolios = await ctx.repo.get_portfolios(user.telegram_id)
    portfolio = resolve_portfolio(user, portfolios)
    if portfolio:
        await touch_portfolio(ctx.repo, user, portfolio.id)
        if symbol:
            await _send_symbol_pnl(message, ctx, user, t, portfolio.id, symbol)
        else:
            await state.update_data(portfolio_id=portfolio.id)
            await state.set_state(PnlStates.symbol)
            await message.answer(t["enter_symbol"])
        return

    if not portfolios:
        await message.answer(t["no_portfolios"])
        return

    await state.set_state(PnlStates.portfolio)
    if symbol:
        await state.update_data(pending_symbol=symbol)
    await show_portfolio_picker(message, portfolios, lang, t)


@router.message(Command("quote"))
async def cmd_quote(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    if not user.onboarding_completed:
        return
    t = ctx.i18n.load(lang)
    parts = (message.text or "").split(maxsplit=1)
    symbol = parts[1].strip().upper() if len(parts) > 1 else None

    if symbol:
        for market in ("US", "IL"):
            quote = await ctx.prices.get_quote(symbol, market)
            if quote:
                await message.answer(format_quote(quote, t))
                return
        await message.answer(t["price_unavailable"])
        return

    await state.set_state(QuoteStates.symbol)
    await message.answer(t["enter_symbol"])
