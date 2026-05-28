from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from src.bot.common import ALL_MENU_BUTTONS, MENU_HOME, get_user_lang, show_main_menu

router = Router()


@router.message(Command("menu"))
@router.message(F.text.in_(MENU_HOME))
async def cmd_menu(message: Message, state: FSMContext, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    if not user.onboarding_completed:
        return
    t = ctx.i18n.load(lang)
    await state.clear()
    data["skip_menu_restore"] = True
    await show_main_menu(message, lang, t)


@router.message(StateFilter(None), F.text, ~F.text.in_(ALL_MENU_BUTTONS))
async def unknown_text(message: Message, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    if not user.onboarding_completed:
        return
    t = ctx.i18n.load(lang)
    await show_main_menu(message, lang, t, text=t["menu_ready"])
