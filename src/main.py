from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import TelegramObject
from typing import Any, Awaitable, Callable

from src.bot.common import BotContext
from src.bot.handlers import alerts, cash, commands, menu, misc, onboarding, portfolio, portfolios, settings, trade_manage, trades
from src.bot.i18n import i18n
from src.bot.middleware import MenuRestoreMiddleware
from src.config import TELEGRAM_BOT_TOKEN
from src.db.repository import Repository
from src.market.prices import PriceProvider
from src.portfolio.calculator import PortfolioCalculator
from src.scheduler.jobs import BotScheduler

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)


class ContextMiddleware:
    def __init__(self, ctx: BotContext) -> None:
        self.ctx = ctx

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["ctx"] = self.ctx
        return await handler(event, data)


async def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is missing. Copy .env.example to .env and set your token.")
        sys.exit(1)

    repo = Repository()
    await repo.init()
    prices = PriceProvider()
    calculator = PortfolioCalculator(prices)
    ctx = BotContext(repo=repo, prices=prices, calculator=calculator, i18n=i18n)

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.middleware(ContextMiddleware(ctx))
    dp.message.middleware(MenuRestoreMiddleware(ctx))
    dp.callback_query.middleware(MenuRestoreMiddleware(ctx))

    dp.include_router(onboarding.router)
    dp.include_router(commands.router)
    dp.include_router(portfolio.router)
    dp.include_router(trades.router)
    dp.include_router(trade_manage.router)
    dp.include_router(cash.router)
    dp.include_router(portfolios.router)
    dp.include_router(alerts.router)
    dp.include_router(settings.router)
    dp.include_router(misc.router)
    dp.include_router(menu.router)

    scheduler = BotScheduler(bot, repo, prices, calculator, i18n)
    scheduler.start()

    logger.info("Stockbot starting...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
