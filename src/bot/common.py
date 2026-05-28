from __future__ import annotations

from dataclasses import dataclass

from aiogram.types import Message

from src.bot.i18n import I18n
from src.bot.keyboards import main_menu_keyboard
from src.db.repository import Repository
from src.market.prices import PriceProvider
from src.portfolio.calculator import PortfolioCalculator


@dataclass
class BotContext:
    repo: Repository
    prices: PriceProvider
    calculator: PortfolioCalculator
    i18n: I18n


MENU_PORTFOLIO = {"📊 התיק שלי", "📊 Portfolio"}
MENU_HOLDINGS = {"📋 החזקות", "📋 Holdings"}
MENU_QUOTE = {"💱 מחיר", "💱 Quote"}
MENU_TRADE = {"➕ עסקה", "➕ Trade"}
MENU_CASH = {"💵 הפקדה", "💵 Deposit"}
MENU_PNL = {"📈 רווח/הפסד", "📈 P&L"}
MENU_HISTORY = {"📜 היסטוריה", "📜 History"}
MENU_TAX = {"📋 דוח מס", "📋 Tax report"}
MENU_MONTHLY = {"📅 דוח חודשי", "📅 Monthly report"}
MENU_WATCHLIST = {"👁 מעקב", "👁 Watchlist"}
MENU_ALERTS = {"🔔 התראות", "🔔 Alerts"}
MENU_PORTFOLIOS = {"📁 תיקים", "📁 Portfolios"}
MENU_SETTINGS = {"⚙️ הגדרות", "⚙️ Settings"}
MENU_HOME = {"🏠 תפריט ראשי", "🏠 Main menu"}

ALL_MENU_BUTTONS = (
    MENU_PORTFOLIO
    | MENU_HOLDINGS
    | MENU_QUOTE
    | MENU_TRADE
    | MENU_CASH
    | MENU_PNL
    | MENU_HISTORY
    | MENU_TAX
    | MENU_MONTHLY
    | MENU_WATCHLIST
    | MENU_ALERTS
    | MENU_PORTFOLIOS
    | MENU_SETTINGS
    | MENU_HOME
)


def get_ctx(data: dict) -> BotContext:
    return data["ctx"]


async def get_user_lang(repo: Repository, telegram_id: int) -> tuple:
    user = await repo.get_or_create_user(telegram_id)
    return user, user.language


async def show_main_menu(message: Message, lang: str, t: dict, *, text: str | None = None) -> None:
    await message.answer(text or t["main_menu"], reply_markup=main_menu_keyboard(lang))
