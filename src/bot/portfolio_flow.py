from __future__ import annotations

from aiogram.types import Message

from src.bot.keyboards import portfolio_picker_keyboard
from src.db.models import Portfolio, User
from src.db.repository import Repository


def resolve_portfolio(user: User, portfolios: list[Portfolio]) -> Portfolio | None:
    if not portfolios:
        return None
    if len(portfolios) == 1:
        return portfolios[0]
    if user.last_portfolio_id:
        for portfolio in portfolios:
            if portfolio.id == user.last_portfolio_id:
                return portfolio
    return None


async def touch_portfolio(repo: Repository, user: User, portfolio_id: int) -> None:
    if user.last_portfolio_id != portfolio_id:
        user.last_portfolio_id = portfolio_id
        await repo.update_user(user)


async def show_portfolio_picker(
    target: Message,
    portfolios: list[Portfolio],
    lang: str,
    t: dict,
    *,
    action: str = "pick_portfolio",
    include_new: bool = False,
    prompt_key: str = "choose_portfolio",
    edit: bool = False,
) -> None:
    text = t[prompt_key]
    kb = portfolio_picker_keyboard(
        portfolios, lang, include_new=include_new, action=action
    )
    if edit:
        await target.edit_text(text, reply_markup=kb)
    else:
        await target.answer(text, reply_markup=kb)
