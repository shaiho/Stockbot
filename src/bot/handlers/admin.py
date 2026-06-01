from __future__ import annotations

from collections import defaultdict

from aiogram import Router
from aiogram.filters import BaseFilter, Command
from aiogram.types import Message

from src.bot.common import BotContext
from src.config import ADMIN_TELEGRAM_IDS
from src.db.models import Portfolio
from src.portfolio.calculator import PortfolioCalculator
from src.portfolio.formatter import HTML

router = Router()


class AdminFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        user = message.from_user
        return bool(user and user.id in ADMIN_TELEGRAM_IDS)


def _fmt_num(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"{value:,.0f}"
    if abs(value) >= 100:
        return f"{value:,.0f}"
    return f"{value:,.2f}"


def _format_symbol_lines(
    items: list[tuple[str, str, int]], count_label: str, empty: str
) -> str:
    if not items:
        return empty
    lines: list[str] = []
    for idx, (symbol, market, count) in enumerate(items, start=1):
        lines.append(f"{idx}. {symbol} ({market}) — {count} {count_label}")
    return "\n".join(lines)


async def _compute_platform_holdings(
    repo, calculator: PortfolioCalculator, portfolios: list[Portfolio]
) -> tuple[list[tuple[str, str, int]], float, float, float]:
    holder_counts: dict[tuple[str, str], set[int]] = defaultdict(set)
    total_ils = 0.0
    fx = await calculator.prices.get_usd_ils()

    for portfolio in portfolios:
        trades = await repo.get_trades(portfolio.id)
        holdings = await repo.get_holdings(portfolio.id, trades)
        for holding in holdings:
            holder_counts[(holding.symbol, holding.market)].add(portfolio.user_id)

        cash_ils, cash_usd = await repo.get_cash_balances(portfolio.id, trades)
        summary = await calculator.compute_summary(
            holdings,
            trades,
            cash_ils,
            cash_usd,
            portfolio.opening_cash_ils,
            portfolio.opening_cash_usd,
        )
        total_ils += summary.total_ils

    top_holdings = sorted(
        ((symbol, market, len(users)) for (symbol, market), users in holder_counts.items()),
        key=lambda item: (-item[2], item[0]),
    )[:5]
    total_usd = total_ils / fx if fx else 0.0
    return top_holdings, total_ils, total_usd, fx


def _format_admin_report(
    t: dict,
    db_stats,
    top_holdings: list[tuple[str, str, int]],
    total_ils: float,
    total_usd: float,
    fx: float,
) -> str:
    watchlist_lines = _format_symbol_lines(
        db_stats.top_watchlist, t["admin_users_label"], t["admin_no_watchlist"]
    )
    holdings_lines = _format_symbol_lines(
        top_holdings, t["admin_portfolios_label"], t["admin_no_holdings"]
    )
    traded_lines = _format_symbol_lines(
        db_stats.top_traded, t["admin_trades_label"], t["admin_no_trades"]
    )

    return t["admin_report"].format(
        total_users=db_stats.total_users,
        onboarded_users=db_stats.onboarded_users,
        users_he=db_stats.users_he,
        users_en=db_stats.users_en,
        new_users_7d=db_stats.new_users_7d,
        new_users_30d=db_stats.new_users_30d,
        total_portfolios=db_stats.total_portfolios,
        users_with_portfolio=db_stats.users_with_portfolio,
        total_trades=db_stats.total_trades,
        total_watchlist_items=db_stats.total_watchlist_items,
        users_with_watchlist=db_stats.users_with_watchlist,
        total_alerts=db_stats.total_alerts,
        enabled_alerts=db_stats.enabled_alerts,
        watchlist_top=watchlist_lines,
        holdings_top=holdings_lines,
        traded_top=traded_lines,
        total_aum_ils=_fmt_num(total_ils),
        total_aum_usd=_fmt_num(total_usd),
        fx_rate=_fmt_num(fx),
    )


@router.message(Command("admin"), AdminFilter())
async def cmd_admin(message: Message, **data) -> None:
    ctx: BotContext = data["ctx"]
    user = await ctx.repo.get_or_create_user(message.from_user.id)
    t = ctx.i18n.load(user.language)

    if not ADMIN_TELEGRAM_IDS:
        await message.answer(t["admin_not_configured"])
        return

    loading = await message.answer(t["admin_loading"])

    db_stats = await ctx.repo.get_admin_db_stats()
    portfolios = await ctx.repo.get_all_portfolios()
    top_holdings, total_ils, total_usd, fx = await _compute_platform_holdings(
        ctx.repo, ctx.calculator, portfolios
    )
    report = _format_admin_report(t, db_stats, top_holdings, total_ils, total_usd, fx)
    await loading.edit_text(report, parse_mode=HTML)
