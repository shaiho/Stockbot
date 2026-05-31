from __future__ import annotations

import logging
import math
from datetime import datetime

import pytz
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.bot.i18n import I18n
from src.config import MIN_ALERT_CHECK_MINUTES, QUOTE_RATE_LIMIT_PER_MINUTE, TIMEZONE
from src.db.repository import Repository
from src.market.calendar import is_trading_day
from src.market.prices import PriceProvider
from src.portfolio.calculator import PortfolioCalculator
from src.portfolio.formatter import HTML, format_daily_report, format_monthly_report
from src.portfolio.allocation import compute_allocation
from src.portfolio.benchmark import compute_benchmark_comparison
from src.portfolio.returns import compute_period_returns
from src.portfolio.report_card import send_report_card

logger = logging.getLogger(__name__)


class BotScheduler:
    def __init__(
        self,
        bot: Bot,
        repo: Repository,
        prices: PriceProvider,
        calculator: PortfolioCalculator,
        i18n: I18n,
    ) -> None:
        self.bot = bot
        self.repo = repo
        self.prices = prices
        self.calculator = calculator
        self.i18n = i18n
        self.scheduler = AsyncIOScheduler(timezone=pytz.timezone(TIMEZONE))
        self._alert_interval_minutes = MIN_ALERT_CHECK_MINUTES

    def start(self) -> None:
        self.scheduler.add_job(self._check_report_schedule, "cron", minute="*")
        self.scheduler.add_job(
            self._check_alerts,
            "interval",
            minutes=MIN_ALERT_CHECK_MINUTES,
            id="alert_check",
            replace_existing=True,
        )
        self.scheduler.start()
        logger.info("Scheduler started")

    @staticmethod
    def _interval_for_symbols(symbol_count: int) -> int:
        if symbol_count <= 0:
            return MIN_ALERT_CHECK_MINUTES
        return max(
            MIN_ALERT_CHECK_MINUTES,
            math.ceil(symbol_count / QUOTE_RATE_LIMIT_PER_MINUTE),
        )

    def _sync_alert_schedule(self, symbol_count: int) -> None:
        interval = self._interval_for_symbols(symbol_count)
        self.prices.set_quote_cache_ttl(interval * 60)

        job = self.scheduler.get_job("alert_check")
        if job is None:
            return

        current = int(job.trigger.interval.total_seconds() // 60)
        if current != interval:
            job.reschedule(trigger=IntervalTrigger(minutes=interval))
            logger.info(
                "Alert interval %d → %d min (%d symbols, cache TTL %ds)",
                current,
                interval,
                symbol_count,
                interval * 60,
            )
        self._alert_interval_minutes = interval

    async def _collect_symbols(self, users) -> set[tuple[str, str]]:
        symbols: set[tuple[str, str]] = set()
        for user in users:
            if not user.onboarding_completed:
                continue
            portfolios = await self.repo.get_portfolios(user.telegram_id)
            for portfolio in portfolios:
                for holding in await self.repo.get_holdings(portfolio.id):
                    symbols.add((holding.symbol, holding.market))
            for item in await self.repo.get_watchlist(user.telegram_id):
                symbols.add((item.symbol, item.market))
            for rule in await self.repo.get_alert_rules(user.telegram_id):
                if not rule.enabled:
                    continue
                cfg = rule.config
                if cfg.get("symbol"):
                    symbols.add((cfg["symbol"], cfg.get("market", "US")))
        return symbols

    async def _check_report_schedule(self) -> None:
        now = datetime.now(pytz.timezone(TIMEZONE))
        current_hm = now.strftime("%H:%M")
        today = now.date().isoformat()
        users = await self.repo.get_all_users()

        report_users = []
        for user in users:
            if not user.onboarding_completed:
                continue
            if now.day == 1 and current_hm == user.report_morning:
                report_users.append(user)
                continue
            if not is_trading_day(now):
                continue
            if current_hm in (user.report_morning, user.report_evening):
                report_users.append(user)

        if report_users:
            await self.prices.warm_cache(list(await self._collect_symbols(report_users)))

        for user in users:
            if not user.onboarding_completed:
                continue
            if now.day == 1 and current_hm == user.report_morning:
                await self._send_monthly_reports(user, today)
            if not is_trading_day(now):
                continue
            if current_hm == user.report_morning:
                await self._send_user_reports(user, today, morning=True)
            if current_hm == user.report_evening:
                await self._send_user_reports(user, today, morning=False)

    async def _send_user_reports(self, user, today: str, *, morning: bool) -> None:
        t = self.i18n.load(user.language)
        portfolios = await self.repo.get_portfolios(user.telegram_id)
        kind = "morning" if morning else "evening"
        for portfolio in portfolios:
            report_key = f"report:{kind}:{portfolio.id}:{today}"
            if await self.repo.was_alert_sent_today(user.telegram_id, report_key, today):
                continue
            try:
                holdings = await self.repo.get_holdings(portfolio.id)
                trades = await self.repo.get_trades(portfolio.id)
                cash_ils, cash_usd = await self.repo.get_cash_balances(portfolio.id)
                summary = await self.calculator.compute_summary(
                    holdings,
                    trades,
                    cash_ils,
                    cash_usd,
                    portfolio.opening_cash_ils,
                    portfolio.opening_cash_usd,
                )
                benchmark = await compute_benchmark_comparison(summary, self.prices)
                text = format_daily_report(summary, portfolio.name, t, morning=morning)
                await send_report_card(
                    self.bot,
                    user.telegram_id,
                    summary,
                    portfolio.name,
                    lang=user.language,
                    t=t,
                    benchmark=benchmark,
                    morning=morning,
                )
                await self.bot.send_message(user.telegram_id, text, parse_mode=HTML)
                await self.repo.mark_alert_sent(user.telegram_id, report_key, today)
            except Exception as exc:
                logger.exception("Report failed for user %s portfolio %s: %s", user.telegram_id, portfolio.id, exc)

    async def _send_monthly_reports(self, user, today: str) -> None:
        t = self.i18n.load(user.language)
        month_key = today[:7]
        portfolios = await self.repo.get_portfolios(user.telegram_id)
        for portfolio in portfolios:
            report_key = f"monthly_report:{portfolio.id}:{month_key}"
            if await self.repo.was_alert_sent_today(user.telegram_id, report_key, today):
                continue
            try:
                holdings = await self.repo.get_holdings(portfolio.id)
                trades = await self.repo.get_trades(portfolio.id)
                cash_ils, cash_usd = await self.repo.get_cash_balances(portfolio.id)
                summary = await self.calculator.compute_summary(
                    holdings,
                    trades,
                    cash_ils,
                    cash_usd,
                    portfolio.opening_cash_ils,
                    portfolio.opening_cash_usd,
                )
                fx = summary.fx_rate

                async def to_ils(amount: float, currency: str) -> float:
                    if currency == "ILS":
                        return amount
                    return amount * fx

                period = await compute_period_returns(trades, to_ils)
                allocation = await compute_allocation(
                    holdings, cash_ils, cash_usd, self.prices
                )
                text = format_monthly_report(
                    summary,
                    portfolio.name,
                    t,
                    period=period,
                    allocation=allocation,
                    month_label=month_key,
                )
                await self.bot.send_message(user.telegram_id, text, parse_mode=HTML)
                await self.repo.mark_alert_sent(user.telegram_id, report_key, today)
            except Exception as exc:
                logger.exception(
                    "Monthly report failed for user %s portfolio %s: %s",
                    user.telegram_id,
                    portfolio.id,
                    exc,
                )

    async def _check_alerts(self) -> None:
        now = datetime.now(pytz.timezone(TIMEZONE))
        if not is_trading_day(now):
            return
        users = await self.repo.get_all_users()
        symbols = await self._collect_symbols(users)
        self._sync_alert_schedule(len(symbols))
        await self.prices.warm_cache(list(symbols))
        today = now.date().isoformat()
        for user in users:
            if not user.onboarding_completed:
                continue
            t = self.i18n.load(user.language)
            rules = await self.repo.get_alert_rules(user.telegram_id)
            for rule in rules:
                if not rule.enabled:
                    continue
                try:
                    await self._evaluate_rule(user.telegram_id, user, rule, today, t)
                except Exception as exc:
                    logger.exception("Alert check failed: %s", exc)

            portfolios = await self.repo.get_portfolios(user.telegram_id)
            seen_symbols: set[tuple[str, str]] = set()
            for portfolio in portfolios:
                holdings = await self.repo.get_holdings(portfolio.id)
                for holding in holdings:
                    key = (holding.symbol, holding.market)
                    if key in seen_symbols:
                        continue
                    seen_symbols.add(key)
                    quote = await self.prices.get_quote(holding.symbol, holding.market)
                    if not quote:
                        continue
                    if abs(quote.change_pct) >= user.mover_threshold_pct:
                        alert_key = f"mover:{holding.symbol}:{today}"
                        if await self.repo.was_alert_sent_today(user.telegram_id, alert_key, today):
                            continue
                        text = (
                            f"🔔 {t['alert_triggered']}\n"
                            f"{holding.symbol} {quote.change_pct:+.1f}% ({portfolio.name})"
                        )
                        await self.bot.send_message(user.telegram_id, text, parse_mode=HTML)
                        await self.repo.mark_alert_sent(user.telegram_id, alert_key, today)

            watchlist = await self.repo.get_watchlist(user.telegram_id)
            for item in watchlist:
                quote = await self.prices.get_quote(item.symbol, item.market)
                if quote and abs(quote.change_pct) >= user.mover_threshold_pct:
                    alert_key = f"watch_mover:{item.symbol}:{today}"
                    if await self.repo.was_alert_sent_today(user.telegram_id, alert_key, today):
                        continue
                    text = f"🔔 {t['alert_triggered']}\n👁 {item.symbol} {quote.change_pct:+.1f}%"
                    await self.bot.send_message(user.telegram_id, text, parse_mode=HTML)
                    await self.repo.mark_alert_sent(user.telegram_id, alert_key, today)

    async def _portfolio_summary(self, portfolio_id: int, user):
        portfolio = await self.repo.get_portfolio(portfolio_id, user.telegram_id)
        if not portfolio:
            return None, None
        holdings = await self.repo.get_holdings(portfolio_id)
        trades = await self.repo.get_trades(portfolio_id)
        cash_ils, cash_usd = await self.repo.get_cash_balances(portfolio_id)
        summary = await self.calculator.compute_summary(
            holdings,
            trades,
            cash_ils,
            cash_usd,
            portfolio.opening_cash_ils,
            portfolio.opening_cash_usd,
        )
        return portfolio, summary

    async def _send_once(self, chat_id, user, alert_key: str, today: str, text: str) -> None:
        if await self.repo.was_alert_sent_today(user.telegram_id, alert_key, today):
            return
        await self.bot.send_message(chat_id, text)
        await self.repo.mark_alert_sent(user.telegram_id, alert_key, today)

    async def _evaluate_rule(self, chat_id, user, rule, today, t) -> None:
        cfg = rule.config
        symbol = cfg.get("symbol")
        market = cfg.get("market", "US")
        threshold = float(cfg.get("threshold_pct", 5))

        if rule.alert_type in ("pct_daily", "premarket", "afterhours", "volume_spike") and symbol:
            quote = await self.prices.get_quote(symbol, market)
            if not quote:
                return

            if rule.alert_type == "pct_daily":
                if abs(quote.change_pct) < threshold:
                    return
                alert_key = f"pct:{symbol}:{threshold}:{today}"
                text = f"🔔 {t['alert_triggered']}\n{symbol} {quote.change_pct:+.1f}%"
                await self._send_once(chat_id, user, alert_key, today, text)
                return

            if rule.alert_type == "premarket":
                pre = quote.pre_market_price or (quote.price if quote.session == "pre" else None)
                base = quote.previous_close
                if not pre or not base or base <= 0:
                    return
                move = (pre - base) / base * 100
                if abs(move) < threshold:
                    return
                alert_key = f"pre:{symbol}:{threshold}:{today}"
                text = f"🔔 {t['pre_market']}\n{symbol} {move:+.1f}%"
                await self._send_once(chat_id, user, alert_key, today, text)
                return

            if rule.alert_type == "afterhours":
                post = quote.after_hours_price or (quote.price if quote.session == "post" else None)
                base = quote.regular_market_price or quote.previous_close
                if not post or not base or base <= 0:
                    return
                move = (post - base) / base * 100
                if abs(move) < threshold:
                    return
                alert_key = f"post:{symbol}:{threshold}:{today}"
                text = f"🔔 {t['after_hours']}\n{symbol} {move:+.1f}%"
                await self._send_once(chat_id, user, alert_key, today, text)
                return

            if rule.alert_type == "volume_spike":
                mult = float(cfg.get("multiplier", 2))
                if not quote.volume or not quote.avg_volume or quote.volume < quote.avg_volume * mult:
                    return
                alert_key = f"vol:{symbol}:{today}"
                text = f"🔔 {t['alert_triggered']}\n{symbol} volume spike"
                await self._send_once(chat_id, user, alert_key, today, text)
                return

        if rule.alert_type == "price_target" and symbol:
            target = float(cfg.get("target_price", 0))
            direction = cfg.get("direction", "above")
            quote = await self.prices.get_quote(symbol, market)
            if not quote:
                return
            hit = quote.price >= target if direction == "above" else quote.price <= target
            if not hit:
                return
            alert_key = f"target:{symbol}:{target}:{today}"
            text = f"🔔 {t['alert_triggered']}\n{symbol} → {quote.price} (target {target})"
            await self._send_once(chat_id, user, alert_key, today, text)
            return

        if rule.alert_type == "news" and symbol:
            news = await self.prices.get_company_news(symbol, market)
            if not news:
                return
            headline = news[0].get("headline", "")
            alert_key = f"news:{symbol}:{headline[:40]}:{today}"
            text = f"📰 {symbol}\n{headline}"
            await self._send_once(chat_id, user, alert_key, today, text)
            return

        if rule.scope != "portfolio":
            return

        portfolio_id = int(cfg.get("portfolio_id", 0))
        portfolio, summary = await self._portfolio_summary(portfolio_id, user)
        if not portfolio or not summary:
            return

        if rule.alert_type == "daily_loss_limit":
            if summary.opening_capital_ils <= 0:
                return
            daily_pct = summary.daily_change_ils / summary.opening_capital_ils * 100
            if daily_pct > -threshold:
                return
            alert_key = f"loss:{portfolio_id}:{today}"
            text = f"🔴 {t['alert_triggered']}\n{portfolio.name} {daily_pct:.1f}%"
            await self._send_once(chat_id, user, alert_key, today, text)
            return

        if rule.alert_type == "portfolio_value_change":
            if summary.total_ils <= 0:
                return
            daily_pct = summary.daily_change_ils / summary.total_ils * 100
            if abs(daily_pct) < threshold:
                return
            alert_key = f"value:{portfolio_id}:{threshold}:{today}"
            text = f"🔔 {t['alert_triggered']}\n{portfolio.name} {daily_pct:+.1f}%"
            await self._send_once(chat_id, user, alert_key, today, text)
            return

        if rule.alert_type == "pnl_milestone":
            milestone = float(cfg.get("threshold_ils", 0))
            pnl = summary.total_pnl_ils
            if milestone >= 0 and pnl < milestone:
                return
            if milestone < 0 and pnl > milestone:
                return
            alert_key = f"milestone:{portfolio_id}:{milestone}:{today}"
            text = f"🔔 {t['alert_triggered']}\n{portfolio.name} P&L ₪{pnl:,.0f}"
            await self._send_once(chat_id, user, alert_key, today, text)
