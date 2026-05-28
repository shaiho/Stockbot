from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, TelegramObject, Update

from src.bot.common import BotContext, MENU_HOME, show_main_menu


def _resolve_message(event: TelegramObject) -> Message | None:
    if isinstance(event, Message):
        return event
    if isinstance(event, CallbackQuery):
        return event.message
    if isinstance(event, Update):
        if event.message:
            return event.message
        if event.callback_query and event.callback_query.message:
            return event.callback_query.message
        if event.edited_message:
            return event.edited_message
    return None


def _resolve_user_id(event: TelegramObject) -> int | None:
    if isinstance(event, Message) and event.from_user:
        return event.from_user.id
    if isinstance(event, CallbackQuery):
        return event.from_user.id
    if isinstance(event, Update):
        if event.message and event.message.from_user:
            return event.message.from_user.id
        if event.callback_query:
            return event.callback_query.from_user.id
        if event.edited_message and event.edited_message.from_user:
            return event.edited_message.from_user.id
    return None


class MenuRestoreMiddleware(BaseMiddleware):
    """Re-attaches the main reply keyboard when an FSM flow finishes."""

    def __init__(self, ctx: BotContext) -> None:
        self.ctx = ctx

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        state: FSMContext | None = data.get("state")
        before = await state.get_state() if state else None
        result = await handler(event, data)
        if not state or not before:
            return result
        after = await state.get_state()
        if after is not None:
            return result
        if before.startswith("OnboardingStates"):
            return result

        text = ""
        msg = _resolve_message(event)
        if msg and msg.text:
            text = msg.text
            if text.startswith("/start") or text.startswith("/menu") or text in MENU_HOME:
                return result
        if data.get("skip_menu_restore"):
            return result

        user_id = _resolve_user_id(event)
        if user_id is None:
            return result
        user = await self.ctx.repo.get_or_create_user(user_id)
        if not user.onboarding_completed:
            return result

        if not isinstance(msg, Message):
            return result
        t = self.ctx.i18n.load(user.language)
        await show_main_menu(msg, user.language, t, text=t["menu_ready"])
        return result
