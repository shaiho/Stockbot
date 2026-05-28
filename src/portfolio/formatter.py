from __future__ import annotations

import html

from aiogram.enums import ParseMode

from src.db.models import Trade
from src.portfolio.calculator import PortfolioSummary, StockPnL, TaxReport
from src.portfolio.allocation import AllocationBreakdown
from src.portfolio.benchmark import BenchmarkComparison
from src.portfolio.returns import PeriodReturns

HTML = ParseMode.HTML


def _esc(text: str) -> str:
    return html.escape(str(text), quote=False)


def _b(text: str) -> str:
    return f"<b>{_esc(text)}</b>"


def _section(title: str) -> str:
    return f"\n{_b(title)}"


def _block(label: str, value: str) -> str:
    return f"{_b(label)}\n{value}"


def fmt_money(amount: float, currency: str, *, show_plus: bool = False) -> str:
    symbol = "₪" if currency == "ILS" else "$"
    if currency == "ILS":
        if amount < 0:
            return f"-{symbol}{abs(amount):,.0f}"
        if show_plus and amount > 0:
            return f"+{symbol}{amount:,.0f}"
        return f"{symbol}{amount:,.0f}"
    if amount < 0:
        return f"-{symbol}{abs(amount):,.2f}"
    if show_plus and amount > 0:
        return f"+{symbol}{amount:,.2f}"
    return f"{symbol}{amount:,.2f}"


def fmt_pct(amount: float) -> str:
    sign = "+" if amount > 0 else ""
    return f"{sign}{amount:.1f}%"


def fmt_dual_ils_usd(amount_ils: float, fx: float, *, show_plus: bool = False) -> str:
    amount_usd = amount_ils / fx if fx else 0.0
    ils = fmt_money(amount_ils, "ILS", show_plus=show_plus)
    usd = fmt_money(amount_usd, "USD", show_plus=show_plus)
    return f"{ils} | {usd}"


def _pct_of(part: float, total: float) -> float:
    return part / total * 100 if total > 0 else 0.0


def format_allocation_section(allocation: AllocationBreakdown, t: dict) -> list[str]:
    total = allocation.total_ils
    if total <= 0:
        return []
    market_labels = {
        "US": t["market_us_short"],
        "IL": t["market_il_short"],
        "CASH": t["cash"],
    }
    lines = [_section(t["allocation_by_market"])]
    for key in ("US", "IL", "CASH"):
        amount = allocation.by_market_ils.get(key, 0.0)
        if amount <= 0:
            continue
        pct = _pct_of(amount, total)
        lines.append(f"  {market_labels[key]}: {pct:.0f}% (₪{amount:,.0f})")
    lines.append("")
    lines.append(_b(t["allocation_by_currency"]))
    for currency in ("USD", "ILS"):
        amount = allocation.by_currency_ils.get(currency, 0.0)
        if amount <= 0:
            continue
        pct = _pct_of(amount, total)
        lines.append(f"  {currency}: {pct:.0f}% (₪{amount:,.0f})")
    return lines


def format_benchmark_section(benchmark: BenchmarkComparison, t: dict) -> list[str]:
    lines = [_section(t["benchmark_title"])]
    lines.append(f"{t['portfolio_daily']}: {fmt_pct(benchmark.portfolio_daily_pct)}")
    if benchmark.us_change_pct is not None:
        lines.append(f"{benchmark.us_name}: {fmt_pct(benchmark.us_change_pct)}")
    else:
        lines.append(f"{benchmark.us_name}: —")
    if benchmark.il_change_pct is not None:
        lines.append(f"{benchmark.il_name}: {fmt_pct(benchmark.il_change_pct)}")
    else:
        lines.append(f"{benchmark.il_name}: —")
    return lines


def format_daily_pnl_by_symbol_section(summary: PortfolioSummary, t: dict) -> list[str]:
    items = [item for item in summary.symbol_pnls if item.daily_pnl is not None]
    if not items:
        return []
    items.sort(key=lambda i: abs(i.daily_pnl or 0), reverse=True)
    lines = [_section(t["daily_pnl_by_symbol"])]
    for item in items:
        pct = f" ({fmt_pct(item.change_pct)})" if item.change_pct is not None else ""
        lines.append(
            f"• {_b(item.symbol)}: {fmt_money(item.daily_pnl, item.currency, show_plus=True)}{pct}"
        )
    return lines


def format_portfolio_summary(
    summary: PortfolioSummary,
    portfolio_name: str,
    t: dict,
    *,
    period: PeriodReturns | None = None,
    allocation: AllocationBreakdown | None = None,
    benchmark: BenchmarkComparison | None = None,
) -> str:
    fx = summary.fx_rate
    lines = [
        _b(f"📁 {portfolio_name}"),
        _b(f"📊 {t['portfolio_summary']}"),
        "",
        _block(t["total_value"], f"₪{summary.total_ils:,.0f} | ${summary.total_usd:,.2f}"),
        "",
        _block(
            t["daily_change"],
            fmt_dual_ils_usd(summary.daily_change_ils, fx, show_plus=True),
        ),
        _block(
            t["total_pnl"],
            f"{fmt_dual_ils_usd(summary.total_pnl_ils, fx, show_plus=True)} "
            f"({fmt_pct(summary.total_pnl_pct)})",
        ),
        _block(
            t["investments_pnl"],
            fmt_dual_ils_usd(summary.investments_pnl_ils, fx, show_plus=True),
        ),
    ]
    if period:
        lines.append(_section(t["realized_summary"]))
        lines.append(
            f"{t['ytd_realized']}: {fmt_dual_ils_usd(period.ytd_realized_ils, fx, show_plus=True)} "
            f"({period.ytd_trade_count} {t['trades']})"
        )
        lines.append(
            f"{t['month_realized']}: {fmt_dual_ils_usd(period.month_realized_ils, fx, show_plus=True)} "
            f"({period.month_trade_count} {t['trades']})"
        )
    lines.extend(
        [
            "",
            _block(
                t["cash"],
                f"{fmt_money(summary.cash_ils, 'ILS')} | {fmt_money(summary.cash_usd, 'USD')}",
            ),
        ]
    )
    if allocation:
        lines.extend(format_allocation_section(allocation, t))
    if benchmark:
        lines.extend(format_benchmark_section(benchmark, t))
    lines.extend(format_daily_pnl_by_symbol_section(summary, t))
    if summary.symbol_pnls:
        lines.append(_section(t["pnl_by_symbol"]))
        for item in summary.symbol_pnls:
            total = item.realized + item.unrealized
            qty_note = f"x{item.quantity:g} | " if item.quantity > 1e-9 else ""
            lines.append(
                f"• {_b(item.symbol)}: {fmt_money(total, item.currency, show_plus=True)}\n"
                f"  {qty_note}{t['realized']}: {fmt_money(item.realized, item.currency, show_plus=True)} | "
                f"{t['unrealized']}: {fmt_money(item.unrealized, item.currency, show_plus=True)}"
            )
    return "\n".join(lines)


def format_portfolio_summary_parts(
    summary: PortfolioSummary,
    portfolio_name: str,
    t: dict,
    *,
    period: PeriodReturns | None = None,
    allocation: AllocationBreakdown | None = None,
    benchmark: BenchmarkComparison | None = None,
) -> list[str]:
    return _split_message(
        format_portfolio_summary(
            summary,
            portfolio_name,
            t,
            period=period,
            allocation=allocation,
            benchmark=benchmark,
        )
    )


def format_monthly_report(
    summary: PortfolioSummary,
    portfolio_name: str,
    t: dict,
    *,
    period: PeriodReturns,
    allocation: AllocationBreakdown,
    month_label: str,
) -> str:
    fx = summary.fx_rate
    lines = [
        _b(f"📅 {t['monthly_report']} — {month_label}"),
        _b(f"📁 {portfolio_name}"),
        "",
        _block(t["total_value"], f"₪{summary.total_ils:,.0f} | ${summary.total_usd:,.2f}"),
        _block(
            t["month_realized"],
            f"{fmt_dual_ils_usd(period.month_realized_ils, fx, show_plus=True)} "
            f"({period.month_trade_count} {t['trades']})",
        ),
        _block(
            t["investments_pnl"],
            fmt_dual_ils_usd(summary.investments_pnl_ils, fx, show_plus=True),
        ),
        _block(
            t["total_pnl"],
            f"{fmt_dual_ils_usd(summary.total_pnl_ils, fx, show_plus=True)} ({fmt_pct(summary.total_pnl_pct)})",
        ),
        _block(t["ytd_realized"], fmt_dual_ils_usd(period.ytd_realized_ils, fx, show_plus=True)),
    ]
    lines.extend(format_allocation_section(allocation, t))
    if summary.holdings:
        lines.append(_section(t["holdings"]))
        for item in summary.holdings[:8]:
            total = item.realized + item.unrealized
            lines.append(
                f"• {_b(item.symbol)}: {fmt_money(total, item.currency, show_plus=True)} "
                f"({t['unrealized']}: {fmt_money(item.unrealized, item.currency, show_plus=True)})"
            )
    return "\n".join(lines)


def format_holdings(summary: PortfolioSummary, portfolio_name: str, t: dict) -> str:
    lines = [_b(f"📁 {portfolio_name}"), _b(f"📋 {t['holdings']}"), ""]
    if not summary.holdings:
        lines.append(t["no_holdings"])
        return "\n".join(lines)
    for item in summary.holdings:
        if item.current_price is None:
            lines.append(
                f"• {_b(f'{item.symbol} x{item.quantity:g}')}\n"
                f"  {t['avg_cost']}: {fmt_money(item.avg_cost, item.currency)}\n"
                f"  — {t['price_unavailable']}"
            )
            continue
        value = item.quantity * item.current_price
        lines.append(
            f"• {_b(f'{item.symbol} x{item.quantity:g}')}\n"
            f"  {t['avg_cost']}: {fmt_money(item.avg_cost, item.currency)}\n"
            f"  {t['current_price']}: {fmt_money(item.current_price, item.currency)}\n"
            f"  {t['value']}: {fmt_money(value, item.currency)}\n"
            f"  {t['realized']}: {fmt_money(item.realized, item.currency)} | "
            f"{t['unrealized']}: {fmt_money(item.unrealized, item.currency, show_plus=True)}"
        )
    return "\n".join(lines)


def format_stock_pnl(item: StockPnL, t: dict) -> str:
    total = item.realized + item.unrealized
    lines = [
        f"📈 {item.symbol} — {t['pnl_title']} ({item.trade_count} {t['trades']})",
        "",
        f"{t['realized']}: {fmt_money(item.realized, item.currency, show_plus=True)}",
        f"  {t['commissions']}: -{fmt_money(item.commissions_paid, item.currency)}",
        f"{t['unrealized']}: {fmt_money(item.unrealized, item.currency, show_plus=True)}",
        f"  {t['quantity']}: {item.quantity:g} | {t['avg_cost']}: {fmt_money(item.avg_cost, item.currency)}",
    ]
    if item.current_price is not None:
        lines.append(f"  {t['current_price']}: {fmt_money(item.current_price, item.currency)}")
    lines.extend(["", f"{t['total']}: {fmt_money(total, item.currency, show_plus=True)}"])
    return "\n".join(lines)


def format_tax_report(report: TaxReport, portfolio_name: str, t: dict) -> str:
    lines = [
        f"📋 {t['tax_report']} {report.year}",
        f"📁 {portfolio_name}",
        t["tax_disclaimer"],
        "",
        f"{t['gross_realized']}: ₪{report.gross_realized_ils:,.0f}",
        f"{t['commissions']}: -₪{report.commissions_ils:,.0f}",
        f"{t['taxable']}: ₪{report.taxable_ils:,.0f}",
        f"{t['tax_25']}: ₪{report.tax_ils:,.0f}",
        f"{t['net_after_tax']}: ₪{report.net_ils:,.0f}",
        "",
        f"── {t['by_symbol']} ──",
    ]
    for symbol, amount in sorted(report.by_symbol.items()):
        lines.append(f"{symbol}: ₪{amount:,.0f}")
    return "\n".join(lines)


def format_daily_report(
    summary: PortfolioSummary, portfolio_name: str, t: dict, *, morning: bool
) -> str:
    header = f"🌅 {t['morning_report']}" if morning else f"🌙 {t['evening_report']}"
    lines = [_b(header), "", format_portfolio_summary(summary, portfolio_name, t)]
    if summary.holdings:
        lines.append(_section(t["holdings"]))
        for item in summary.holdings:
            if item.current_price is None:
                lines.append(f"• {_b(item.symbol)}: {t['price_unavailable']}")
                continue
            total = item.realized + item.unrealized
            if item.daily_pnl is not None:
                pct = fmt_pct(item.change_pct) if item.change_pct is not None else "—"
                daily = fmt_money(item.daily_pnl, item.currency, show_plus=True)
                lines.append(
                    f"• {_b(item.symbol)} {pct}\n"
                    f"  {t['daily_change']}: {daily} | "
                    f"{t['unrealized']}: {fmt_money(item.unrealized, item.currency, show_plus=True)} | "
                    f"{t['total']}: {fmt_money(total, item.currency, show_plus=True)}"
                )
            else:
                pct = fmt_pct(item.change_pct) if item.change_pct is not None else "—"
                lines.append(
                    f"• {_b(item.symbol)} {pct}\n"
                    f"  {t['unrealized']}: {fmt_money(item.unrealized, item.currency, show_plus=True)} | "
                    f"{t['total']}: {fmt_money(total, item.currency, show_plus=True)}"
                )
    return "\n".join(lines)


def fmt_date(timestamp: str) -> str:
    if len(timestamp) >= 10 and timestamp[4] == "-":
        y, m, d = timestamp[:10].split("-")
        return f"{d}/{m}/{y}"
    return timestamp[:10]


def format_trade_line(trade: Trade, t: dict) -> str:
    action_labels = {
        "buy": t["buy"],
        "sell": t["sell"],
        "deposit": t["deposit"],
        "withdraw": t["withdraw"],
        "dividend": t["dividend"],
    }
    date = fmt_date(trade.timestamp)
    action = action_labels.get(trade.action, trade.action)
    price = fmt_money(trade.price, trade.currency)
    comm = fmt_money(trade.commission, trade.currency)
    line = (
        f"#{trade.id} | 📅 {date} | {action} | x{trade.quantity:g} @ {price} | "
        f"{t['commissions']} {comm}"
    )
    if trade.note:
        line += f" | {trade.note}"
    return line


def format_trade_history(
    trades: list[Trade], symbol: str, portfolio_name: str, t: dict
) -> list[str]:
    header = [
        f"📜 {t['trade_history']} — {symbol}",
        f"📁 {portfolio_name}",
        f"{len(trades)} {t['trades']}",
        t["trade_manage_hint"],
        "",
    ]
    lines = list(header)
    for trade in trades:
        lines.append(format_trade_line(trade, t))
    text = "\n".join(lines)
    return _split_message(text)


def _split_message(text: str, limit: int = 4000) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    chunk: list[str] = []
    size = 0
    for line in text.split("\n"):
        line_len = len(line) + 1
        if size + line_len > limit and chunk:
            parts.append("\n".join(chunk))
            chunk = [line]
            size = line_len
        else:
            chunk.append(line)
            size += line_len
    if chunk:
        parts.append("\n".join(chunk))
    return parts


def format_quote(quote, t: dict) -> str:
    lines = [f"💱 {quote.symbol} ({quote.market})"]
    if quote.market == "US":
        session_key = f"session_{quote.session}"
        if session_key in t:
            lines.append(f"🕐 {t[session_key]}")
        return "\n".join(lines + _format_us_quote_lines(quote, t))
    lines.extend(
        [
            f"{t['price']}: {fmt_money(quote.price, quote.currency)}",
            f"{t['daily_change']}: {fmt_pct(quote.change_pct)}",
        ]
    )
    return "\n".join(lines)


def _format_us_quote_lines(quote, t: dict) -> list[str]:
    lines: list[str] = []

    if quote.session == "pre" and quote.pre_market_price is not None:
        chg = quote.pre_market_change_pct if quote.pre_market_change_pct is not None else quote.change_pct
        lines.append(
            f"{t['pre_market']}: {fmt_money(quote.pre_market_price, quote.currency)} ({fmt_pct(chg)})"
        )
        if quote.previous_close:
            if quote.regular_daily_change_pct is not None:
                lines.append(
                    f"{t['previous_close']}: {fmt_money(quote.previous_close, quote.currency)} "
                    f"({fmt_pct(quote.regular_daily_change_pct)})"
                )
            else:
                lines.append(f"{t['previous_close']}: {fmt_money(quote.previous_close, quote.currency)}")
        return lines

    if quote.session == "post" and quote.after_hours_price is not None:
        chg = quote.after_hours_change_pct if quote.after_hours_change_pct is not None else quote.change_pct
        lines.append(
            f"{t['after_hours']}: {fmt_money(quote.after_hours_price, quote.currency)} ({fmt_pct(chg)})"
        )
        if quote.regular_market_price:
            lines.append(
                f"{t['regular_close']}: {fmt_money(quote.regular_market_price, quote.currency)}"
            )
        elif quote.previous_close:
            lines.append(f"{t['previous_close']}: {fmt_money(quote.previous_close, quote.currency)}")
        return lines

    lines.append(f"{t['price']}: {fmt_money(quote.price, quote.currency)}")
    lines.append(f"{t['daily_change']}: {fmt_pct(quote.change_pct)}")
    if quote.previous_close:
        lines.append(f"{t['previous_close']}: {fmt_money(quote.previous_close, quote.currency)}")
    if quote.pre_market_price is not None:
        pre_chg = quote.pre_market_change_pct
        if pre_chg is not None:
            lines.append(
                f"{t['pre_market']}: {fmt_money(quote.pre_market_price, quote.currency)} ({fmt_pct(pre_chg)})"
            )
        else:
            lines.append(f"{t['pre_market']}: {fmt_money(quote.pre_market_price, quote.currency)}")
    if quote.after_hours_price is not None:
        post_chg = quote.after_hours_change_pct
        if post_chg is not None:
            lines.append(
                f"{t['after_hours']}: {fmt_money(quote.after_hours_price, quote.currency)} ({fmt_pct(post_chg)})"
            )
        else:
            lines.append(f"{t['after_hours']}: {fmt_money(quote.after_hours_price, quote.currency)}")
    return lines
