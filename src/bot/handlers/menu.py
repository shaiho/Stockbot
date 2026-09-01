from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.bot.common import ALL_MENU_BUTTONS, MENU_HOME, get_user_lang, show_main_menu
from src.bot.handlers import alerts, cash, misc, portfolio, portfolios, settings, trades

router = Router()

MenuHandler = Callable[..., Awaitable[Any]]

_MENU_CALLBACKS: dict[str, MenuHandler] = {
    "portfolio": portfolio.menu_portfolio,
    "holdings": portfolio.menu_holdings,
    "quote": portfolio.menu_quote,
    "trade": trades.menu_trade,
    "cash": cash.menu_cash,
    "pnl": portfolio.menu_pnl,
    "history": portfolio.menu_history,
    "tax": portfolio.menu_tax,
    "monthly": portfolio.menu_monthly,
    "watchlist": misc.menu_watchlist,
    "alerts": alerts.menu_alerts,
    "portfolios": portfolios.menu_portfolios,
    "settings": settings.menu_settings,
}


async def _invoke_menu_handler(
    handler: MenuHandler,
    message: Message,
    state: FSMContext,
    data: dict[str, Any],
) -> None:
    params = inspect.signature(handler).parameters
    if "state" in params:
        await handler(message, state, **data)
    else:
        await handler(message, **data)


@router.message(Command("menu"))
@router.message(F.text.in_(MENU_HOME))
async def cmd_menu(message: Message, state: FSMContext, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    if not user.onboarding_completed:
        await message.answer(t["onboarding_in_progress"])
        return
    await state.clear()
    data["skip_menu_restore"] = True
    await show_main_menu(message, lang, t)


@router.callback_query(F.data.startswith("menu:"))
async def menu_inline(callback: CallbackQuery, state: FSMContext, **data) -> None:
    if not callback.message or not callback.from_user:
        await callback.answer()
        return
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    if not user.onboarding_completed:
        await callback.answer(t["onboarding_in_progress"], show_alert=True)
        return

    action = callback.data.split(":", 1)[1]
    handler = _MENU_CALLBACKS.get(action)
    if not handler:
        await callback.answer()
        return

    await callback.answer()
    data["skip_menu_restore"] = True
    message = callback.message.model_copy(update={"from_user": callback.from_user})
    await _invoke_menu_handler(handler, message, state, data)


@router.message(StateFilter(None), F.text, ~F.text.in_(ALL_MENU_BUTTONS))
async def unknown_text(message: Message, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    if not user.onboarding_completed:
        return
    t = ctx.i18n.load(lang)
    await show_main_menu(message, lang, t, text=t["menu_ready"])
