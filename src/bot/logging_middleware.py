from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, TelegramObject, Update

logger = logging.getLogger(__name__)


def _describe_update(event: TelegramObject) -> tuple[int | None, str]:
    if isinstance(event, Message) and event.from_user:
        text = event.text or event.caption or f"[{event.content_type}]"
        return event.from_user.id, text[:120]
    if isinstance(event, CallbackQuery):
        data = event.data or ""
        return event.from_user.id, f"callback:{data[:120]}"
    if isinstance(event, Update):
        if event.message and event.message.from_user:
            text = event.message.text or event.message.caption or "[message]"
            return event.message.from_user.id, text[:120]
        if event.callback_query:
            data = event.callback_query.data or ""
            return event.callback_query.from_user.id, f"callback:{data[:120]}"
    return None, type(event).__name__


class UpdateLoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id, summary = _describe_update(event)
        state: FSMContext | None = data.get("state")
        state_name = await state.get_state() if state else None
        logger.info(
            "update user=%s state=%s %s",
            user_id,
            state_name or "-",
            summary,
        )
        try:
            return await handler(event, data)
        except Exception:
            logger.exception(
                "handler failed user=%s state=%s %s",
                user_id,
                state_name or "-",
                summary,
            )
            raise
