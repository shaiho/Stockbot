from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from src.bot.common import MENU_WATCHLIST, get_user_lang
from src.bot.states import WatchlistStates

router = Router()


@router.message(F.text.in_(MENU_WATCHLIST))
async def menu_watchlist(message: Message, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    items = await ctx.repo.get_watchlist(user.telegram_id)
    if not items:
        add_label = t["add_to_watchlist"]
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=add_label, callback_data="watchlist_add")]]
        )
        await message.answer(t["watchlist_empty"], reply_markup=kb)
        return
    lines = [f"• {item.symbol} ({item.market})" for item in items]
    rows = [
        [
            InlineKeyboardButton(text=f"📰 {item.symbol}", callback_data=f"watchlist_news:{item.id}"),
            InlineKeyboardButton(text="❌", callback_data=f"watchlist_remove:{item.id}"),
        ]
        for item in items
    ]
    rows.append([InlineKeyboardButton(text=t["add_to_watchlist"], callback_data="watchlist_add")])
    await message.answer("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("watchlist_news:"))
async def watchlist_news(callback: CallbackQuery, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    item_id = int(callback.data.split(":")[1])
    items = await ctx.repo.get_watchlist(user.telegram_id)
    item = next((i for i in items if i.id == item_id), None)
    if not item:
        await callback.answer()
        return
    news = await ctx.prices.get_company_news(item.symbol, item.market)
    if not news:
        await callback.message.answer(f"{item.symbol}: {t['no_news']}")
        await callback.answer()
        return
    lines = [f"📰 {item.symbol}", ""]
    for article in news[:5]:
        headline = article.get("headline", "")
        if headline:
            lines.append(f"• {headline}")
    await callback.message.answer("\n".join(lines))
    await callback.answer()


@router.callback_query(F.data == "watchlist_add")
async def watchlist_add_start(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    await state.set_state(WatchlistStates.symbol)
    await callback.message.answer(t["enter_symbol"])
    await callback.answer()


@router.message(WatchlistStates.symbol)
async def watchlist_symbol(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    symbol = (message.text or "").strip().upper()
    await state.update_data(symbol=symbol)
    await state.set_state(WatchlistStates.market)
    from src.bot.keyboards import market_keyboard

    await message.answer(t["choose_market"], reply_markup=market_keyboard(lang))


@router.callback_query(WatchlistStates.market, F.data.startswith("market:"))
async def watchlist_market(callback: CallbackQuery, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, callback.from_user.id)
    t = ctx.i18n.load(lang)
    form = await state.get_data()
    market = callback.data.split(":")[1]
    try:
        await ctx.repo.add_watchlist_item(user.telegram_id, form["symbol"], market)
    except Exception:
        pass
    await state.clear()
    await callback.message.edit_text(t["watchlist_added"])
    await callback.answer()


@router.callback_query(F.data.startswith("watchlist_remove:"))
async def watchlist_remove(callback: CallbackQuery, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    item_id = int(callback.data.split(":")[1])
    await ctx.repo.remove_watchlist_item(item_id, user.telegram_id)
    await callback.answer(t["watchlist_removed"])
