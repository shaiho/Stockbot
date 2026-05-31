from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from pathlib import Path

from aiogram import Bot
from aiogram.types import BufferedInputFile
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont

from src.portfolio.benchmark import BenchmarkComparison
from src.portfolio.calculator import PortfolioSummary
from src.portfolio.formatter import fmt_dual_ils_usd, fmt_money, fmt_pct

FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
WIDTH = 900
PAD = 36
CARD_RADIUS = 24
BG = "#eef2f7"
CARD = "#ffffff"
TEXT = "#0f172a"
MUTED = "#64748b"
GREEN = "#15803d"
GREEN_BG = "#dcfce7"
RED = "#b91c1c"
RED_BG = "#fee2e2"
ACCENT = "#2563eb"
LINE = "#e2e8f0"

logger = logging.getLogger(__name__)


@dataclass
class ReportCardData:
    portfolio_name: str
    lang: str
    total_ils: float
    total_usd: float
    fx: float
    daily_change_ils: float
    total_pnl_ils: float
    total_pnl_pct: float
    cash_ils: float
    cash_usd: float
    benchmark: BenchmarkComparison | None
    top_movers: list[tuple[str, float, str, float | None]]
    subtitle: str | None = None
    subtitle_emoji: str | None = None
    morning: bool | None = None


def build_report_card_data(
    summary: PortfolioSummary,
    portfolio_name: str,
    *,
    lang: str,
    benchmark: BenchmarkComparison | None = None,
    morning: bool | None = None,
    subtitle: str | None = None,
    subtitle_emoji: str | None = None,
    top_n: int = 5,
) -> ReportCardData:
    movers = [item for item in summary.symbol_pnls if item.daily_pnl is not None]
    movers.sort(key=lambda item: abs(item.daily_pnl or 0), reverse=True)
    top_movers = [
        (item.symbol, item.daily_pnl or 0.0, item.currency, item.change_pct)
        for item in movers[:top_n]
    ]
    return ReportCardData(
        portfolio_name=portfolio_name,
        lang=lang,
        total_ils=summary.total_ils,
        total_usd=summary.total_usd,
        fx=summary.fx_rate,
        daily_change_ils=summary.daily_change_ils,
        total_pnl_ils=summary.total_pnl_ils,
        total_pnl_pct=summary.total_pnl_pct,
        cash_ils=summary.cash_ils,
        cash_usd=summary.cash_usd,
        benchmark=benchmark,
        top_movers=top_movers,
        subtitle=subtitle,
        subtitle_emoji=subtitle_emoji,
        morning=morning,
    )


def _has_hebrew(text: str) -> bool:
    return any("\u0590" <= ch <= "\u05ff" for ch in text)


def _hebrew_label(text: str, lang: str) -> str:
    if lang == "he" and _has_hebrew(text):
        return get_display(text)
    return text


def _pick_font(
    text: str,
    lang: str,
    fonts: dict[str, ImageFont.ImageFont],
    *,
    hebrew_key: str = "hebrew_label",
    latin_key: str = "latin_label",
) -> ImageFont.ImageFont:
    if lang == "he" and _has_hebrew(text):
        return fonts[hebrew_key]
    return fonts[latin_key]


def _load_font_file(name: str, size: int) -> ImageFont.FreeTypeFont | None:
    path = FONT_DIR / name
    if path.exists():
        return ImageFont.truetype(str(path), size=size)
    return None


def _load_fonts() -> dict[str, ImageFont.ImageFont]:
    sizes = {
        "title": 34,
        "subtitle": 22,
        "hero": 40,
        "label": 22,
        "value": 24,
        "section": 24,
        "small": 20,
    }
    fonts: dict[str, ImageFont.ImageFont] = {}
    for key, size in sizes.items():
        bold = key in {"title", "hero", "value", "section"}
        latin = _load_font_file("NotoSans-Bold.ttf" if bold else "NotoSans-Regular.ttf", size)
        hebrew = _load_font_file(
            "NotoSansHebrew-Bold.ttf" if bold else "NotoSansHebrew-Regular.ttf",
            size,
        )
        if latin is None:
            latin = hebrew or ImageFont.load_default()
        if hebrew is None:
            hebrew = latin
        fonts[f"latin_{key}"] = latin
        fonts[f"hebrew_{key}"] = hebrew
    fonts["latin"] = fonts["latin_value"]
    fonts["hebrew"] = fonts["hebrew_label"]
    return fonts


def _rounded_rect(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    radius: int,
    fill: str,
) -> None:
    draw.rounded_rectangle(xy, radius=radius, fill=fill)


def _metric_row(
    draw: ImageDraw.ImageDraw,
    y: int,
    label: str,
    value: str,
    *,
    lang: str,
    fonts: dict[str, ImageFont.ImageFont],
    value_color: str = TEXT,
    bg: str | None = None,
) -> int:
    row_h = 56
    x0 = PAD + 16
    x1 = WIDTH - PAD - 16
    if bg:
        _rounded_rect(draw, (x0, y, x1, y + row_h), 14, bg)

    label_text = _hebrew_label(label, lang)
    label_font = _pick_font(label, lang, fonts)
    value_font = fonts["latin_value"]
    if lang == "he":
        draw.text((x1 - 16, y + 16), label_text, font=label_font, fill=MUTED, anchor="ra")
        draw.text((x0 + 16, y + 16), value, font=value_font, fill=value_color, anchor="la")
    else:
        draw.text((x0 + 16, y + 16), label_text, font=label_font, fill=MUTED, anchor="la")
        draw.text((x1 - 16, y + 16), value, font=value_font, fill=value_color, anchor="ra")
    return y + row_h + 10


def _section_title(
    draw: ImageDraw.ImageDraw,
    y: int,
    title: str,
    lang: str,
    fonts: dict[str, ImageFont.ImageFont],
) -> int:
    text = _hebrew_label(title, lang)
    font = _pick_font(title, lang, fonts, hebrew_key="hebrew_section", latin_key="latin_section")
    if lang == "he":
        draw.text((WIDTH - PAD - 16, y), text, font=font, fill=TEXT, anchor="ra")
    else:
        draw.text((PAD + 16, y), text, font=font, fill=TEXT, anchor="la")
    draw.line((PAD + 16, y + 28, WIDTH - PAD - 16, y + 28), fill=LINE, width=2)
    return y + 40


async def send_report_card(
    bot: Bot,
    chat_id: int,
    summary: PortfolioSummary,
    portfolio_name: str,
    *,
    lang: str,
    t: dict,
    benchmark: BenchmarkComparison | None,
    morning: bool | None = None,
    subtitle: str | None = None,
    subtitle_emoji: str | None = None,
) -> None:
    card_data = build_report_card_data(
        summary,
        portfolio_name,
        lang=lang,
        benchmark=benchmark,
        morning=morning,
        subtitle=subtitle,
        subtitle_emoji=subtitle_emoji,
    )
    try:
        png = render_report_card(card_data, t)
        photo = BufferedInputFile(png, filename="report_card.png")
        await bot.send_photo(chat_id, photo)
    except Exception:
        logger.exception("Report card render failed for chat %s", chat_id)


def render_report_card(data: ReportCardData, t: dict) -> bytes:
    if data.subtitle:
        header = data.subtitle
    elif data.morning is not None:
        header = t["morning_report"] if data.morning else t["evening_report"]
    else:
        header = t["portfolio_summary"]

    row_count = 3
    if data.benchmark:
        row_count += 4
    if data.top_movers:
        row_count += 1 + len(data.top_movers)
    height = 320 + row_count * 66

    img = Image.new("RGB", (WIDTH, height), BG)
    draw = ImageDraw.Draw(img)
    fonts = _load_fonts()

    card_top = PAD
    card_bottom = height - PAD
    _rounded_rect(draw, (PAD, card_top, WIDTH - PAD, card_bottom), CARD_RADIUS, CARD)

    y = card_top + 28
    title_text = _hebrew_label(data.portfolio_name, data.lang)
    title_font = _pick_font(
        data.portfolio_name,
        data.lang,
        fonts,
        hebrew_key="hebrew_title",
        latin_key="latin_title",
    )
    if data.lang == "he":
        draw.text((WIDTH - PAD - 24, y), title_text, font=title_font, fill=TEXT, anchor="ra")
    else:
        draw.text((PAD + 24, y), title_text, font=title_font, fill=TEXT, anchor="la")
    y += 42

    subtitle_text = _hebrew_label(header, data.lang)
    subtitle_font = _pick_font(
        header,
        data.lang,
        fonts,
        hebrew_key="hebrew_subtitle",
        latin_key="latin_subtitle",
    )
    if data.lang == "he":
        draw.text((WIDTH - PAD - 24, y), subtitle_text, font=subtitle_font, fill=MUTED, anchor="ra")
    else:
        draw.text((PAD + 24, y), subtitle_text, font=subtitle_font, fill=MUTED, anchor="la")
    y += 36

    total_text = f"₪{data.total_ils:,.0f}  |  ${data.total_usd:,.2f}"
    draw.text((WIDTH // 2, y), total_text, font=fonts["latin_hero"], fill=ACCENT, anchor="ma")
    y += 58
    total_label = _hebrew_label(t["total_value"], data.lang)
    draw.text(
        (WIDTH // 2, y),
        total_label,
        font=fonts["hebrew_small"] if data.lang == "he" else fonts["latin_small"],
        fill=MUTED,
        anchor="ma",
    )
    y += 44

    daily_value = fmt_dual_ils_usd(data.daily_change_ils, data.fx, show_plus=True)
    daily_bg = GREEN_BG if data.daily_change_ils >= 0 else RED_BG
    daily_color = GREEN if data.daily_change_ils >= 0 else RED
    y = _metric_row(
        draw,
        y,
        t["daily_change"],
        daily_value,
        lang=data.lang,
        fonts=fonts,
        value_color=daily_color,
        bg=daily_bg,
    )

    pnl_value = (
        f"{fmt_dual_ils_usd(data.total_pnl_ils, data.fx, show_plus=True)} "
        f"({fmt_pct(data.total_pnl_pct)})"
    )
    pnl_bg = GREEN_BG if data.total_pnl_ils >= 0 else RED_BG
    pnl_color = GREEN if data.total_pnl_ils >= 0 else RED
    y = _metric_row(
        draw,
        y,
        t["total_pnl"],
        pnl_value,
        lang=data.lang,
        fonts=fonts,
        value_color=pnl_color,
        bg=pnl_bg,
    )

    cash_value = f"{fmt_money(data.cash_ils, 'ILS')}  |  {fmt_money(data.cash_usd, 'USD')}"
    y = _metric_row(draw, y, t["cash"], cash_value, lang=data.lang, fonts=fonts)
    y += 8

    if data.benchmark:
        y = _section_title(draw, y, t["benchmark_title"], data.lang, fonts)
        bench_rows = [
            (t["portfolio_daily"], fmt_pct(data.benchmark.portfolio_daily_pct)),
            (
                data.benchmark.us_name,
                fmt_pct(data.benchmark.us_change_pct)
                if data.benchmark.us_change_pct is not None
                else "—",
            ),
            (
                data.benchmark.il_name,
                fmt_pct(data.benchmark.il_change_pct)
                if data.benchmark.il_change_pct is not None
                else "—",
            ),
        ]
        for label, value in bench_rows:
            y = _metric_row(draw, y, label, value, lang=data.lang, fonts=fonts)
        y += 4

    if data.top_movers:
        y = _section_title(draw, y, t["daily_pnl_by_symbol"], data.lang, fonts)
        for symbol, daily_pnl, currency, change_pct in data.top_movers:
            pct = f" ({fmt_pct(change_pct)})" if change_pct is not None else ""
            value = f"{fmt_money(daily_pnl, currency, show_plus=True)}{pct}"
            color = GREEN if daily_pnl >= 0 else RED
            y = _metric_row(draw, y, symbol, value, lang=data.lang, fonts=fonts, value_color=color)

    draw.text(
        (WIDTH // 2, card_bottom - 22),
        "Stockbot",
        font=fonts["latin_small"],
        fill=MUTED,
        anchor="ma",
    )

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
