from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import Message

from src.bot.common import get_user_lang

router = Router()
logger = logging.getLogger(__name__)


@router.message(F.text)
async def unhandled_text(message: Message, state, **data) -> None:
    ctx = data["ctx"]
    user, lang = await get_user_lang(ctx.repo, message.from_user.id)
    t = ctx.i18n.load(lang)
    current = await state.get_state()

    if user.onboarding_completed and current is None:
        return

    if not user.onboarding_completed and current is None:
        logger.warning(
            "orphan onboarding message user=%s text=%r",
            user.telegram_id,
            message.text,
        )
        await message.answer(t["onboarding_stuck"])
        return

    if current is not None:
        logger.warning(
            "unhandled FSM message user=%s state=%s text=%r",
            user.telegram_id,
            current,
            message.text,
        )
        await message.answer(t["fsm_stuck"])
