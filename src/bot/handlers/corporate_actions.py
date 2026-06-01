from __future__ import annotations

import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.types import CallbackQuery

from src.bot.common import get_user_lang
from src.portfolio.corporate_actions import apply_stock_split, format_split_label

router = Router()
logger = logging.getLogger(__name__)


def _parse_float(value: str) -> float:
    return float(value.replace(",", "."))


@router.callback_query(F.data.startswith("ca:split:"))
async def apply_split_callback(callback: CallbackQuery, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    parts = callback.data.split(":")
    if len(parts) != 6:
        await callback.answer(t["action_failed"], show_alert=True)
        return

    _, _, portfolio_id_s, symbol, from_s, to_s = parts
    portfolio_id = int(portfolio_id_s)
    from_factor = _parse_float(from_s)
    to_factor = _parse_float(to_s)

    portfolio = await ctx.repo.get_portfolio(portfolio_id, user.telegram_id)
    if not portfolio:
        await callback.answer(t["no_portfolios"], show_alert=True)
        return

    applied_key = f"split_applied:{portfolio_id}:{symbol.upper()}:{from_s}x{to_s}"
    today = datetime.now().date().isoformat()
    if await ctx.repo.was_alert_sent_today(user.telegram_id, applied_key, today):
        await callback.answer(t["event_split_already_applied"], show_alert=True)
        return

    count = await apply_stock_split(
        ctx.repo, user.telegram_id, portfolio_id, symbol, from_factor, to_factor
    )
    if count <= 0:
        await callback.answer(t["event_split_no_trades"], show_alert=True)
        return

    await ctx.repo.mark_alert_sent(user.telegram_id, applied_key, today)
    label = format_split_label(from_factor, to_factor)
    await callback.message.edit_text(
        t["event_split_applied"].format(
            symbol=symbol.upper(),
            portfolio=portfolio.name,
            label=label,
            count=count,
        )
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ca:div:"))
async def record_dividend_callback(callback: CallbackQuery, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    parts = callback.data.split(":")
    if len(parts) != 6:
        await callback.answer(t["action_failed"], show_alert=True)
        return

    _, _, portfolio_id_s, symbol, amount_s, ex_date = parts
    portfolio_id = int(portfolio_id_s)
    amount_per_share = _parse_float(amount_s)

    portfolio = await ctx.repo.get_portfolio(portfolio_id, user.telegram_id)
    if not portfolio:
        await callback.answer(t["trade_not_found"], show_alert=True)
        return

    holdings = await ctx.repo.get_holdings(portfolio_id)
    holding = next((h for h in holdings if h.symbol.upper() == symbol.upper()), None)
    if not holding or holding.quantity <= 0:
        await callback.answer(t["no_holdings"], show_alert=True)
        return

    total = amount_per_share * holding.quantity
    currency = holding.currency
    applied_key = f"div_applied:{portfolio_id}:{symbol.upper()}:{ex_date}:{amount_s}"
    if await ctx.repo.was_alert_sent_today(user.telegram_id, applied_key, ex_date):
        await callback.answer(t["event_dividend_already_recorded"], show_alert=True)
        return

    await ctx.repo.add_trade(
        portfolio_id=portfolio_id,
        symbol=symbol.upper(),
        market=holding.market,
        asset_type="stock",
        action="dividend",
        quantity=1.0,
        price=total,
        currency=currency,
        commission=0.0,
        timestamp=f"{ex_date} 12:00:00",
        note=f"Auto dividend {amount_per_share} x {holding.quantity:g}",
    )
    await ctx.repo.mark_alert_sent(user.telegram_id, applied_key, ex_date)

    currency_symbol = "₪" if currency == "ILS" else "$"
    await callback.message.edit_text(
        t["event_dividend_recorded"].format(
            symbol=symbol.upper(),
            portfolio=portfolio.name,
            total=f"{currency_symbol}{total:,.2f}",
        )
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ca:skip:"))
async def skip_corporate_action(callback: CallbackQuery, **data) -> None:
    user, lang = await get_user_lang(data["ctx"].repo, callback.from_user.id)
    t = data["ctx"].i18n.load(lang)
    await callback.message.edit_text(t["event_action_skipped"])
    await callback.answer()
