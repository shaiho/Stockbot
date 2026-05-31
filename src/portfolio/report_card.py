from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from pathlib import Path

from aiogram import Bot
from aiogram.types import BufferedInputFile
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


def _has_latin(text: str) -> bool:
    return any(("A" <= ch <= "Z") or ("a" <= ch <= "z") for ch in text)


def _card_label(text: str) -> str:
    """Normalize labels for Noto Sans Hebrew (no slash, no embedded Latin words)."""
    out = text.replace("/", " · ")
    out = out.replace("benchmark", "מדדים").replace("Benchmark", "מדדים")
    return out


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _draw_rtl(
    draw: ImageDraw.ImageDraw,
    x_right: int,
    y: int,
    text: str,
    font: ImageFont.ImageFont,
    fill: str,
    *,
    sanitize: bool = True,
) -> None:
    label = _card_label(text) if sanitize else text
    draw.text((x_right, y), label, font=font, fill=fill, anchor="ra", direction="rtl")


def _draw_rtl_center(
    draw: ImageDraw.ImageDraw,
    x_center: int,
    y: int,
    text: str,
    font: ImageFont.ImageFont,
    fill: str,
    *,
    sanitize: bool = True,
) -> None:
    label = _card_label(text) if sanitize else text
    draw.text((x_center, y), label, font=font, fill=fill, anchor="ma", direction="rtl")


def _draw_ltr_left(
    draw: ImageDraw.ImageDraw,
    x_left: int,
    y: int,
    text: str,
    font: ImageFont.ImageFont,
    fill: str,
) -> None:
    draw.text((x_left, y), text, font=font, fill=fill)


def _draw_ltr_right(
    draw: ImageDraw.ImageDraw,
    x_right: int,
    y: int,
    text: str,
    font: ImageFont.ImageFont,
    fill: str,
) -> None:
    width, _ = _text_size(draw, text, font)
    draw.text((x_right - width, y), text, font=font, fill=fill)


def _draw_center(
    draw: ImageDraw.ImageDraw,
    x_center: int,
    y: int,
    text: str,
    font: ImageFont.ImageFont,
    fill: str,
) -> None:
    draw.text((x_center, y), text, font=font, fill=fill, anchor="ma")


def _pick_font(
    text: str,
    lang: str,
    fonts: dict[str, ImageFont.ImageFont],
    *,
    hebrew_key: str = "hebrew_label",
    latin_key: str = "latin_label",
) -> ImageFont.ImageFont:
    if lang == "he" and _has_hebrew(text) and not _has_latin(_card_label(text)):
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

    label_font = _pick_font(label, lang, fonts)
    value_font = fonts["latin_value"]
    if lang == "he":
        if _has_hebrew(label):
            _draw_rtl(draw, x1 - 16, y + 16, label, label_font, MUTED)
        else:
            _draw_ltr_right(draw, x1 - 16, y + 16, label, label_font, MUTED)
        _draw_ltr_left(draw, x0 + 16, y + 16, value, value_font, value_color)
    else:
        _draw_ltr_left(draw, x0 + 16, y + 16, label, label_font, MUTED)
        _draw_ltr_right(draw, x1 - 16, y + 16, value, value_font, value_color)
    return y + row_h + 10


def _section_title(
    draw: ImageDraw.ImageDraw,
    y: int,
    title: str,
    lang: str,
    fonts: dict[str, ImageFont.ImageFont],
) -> int:
    font = _pick_font(title, lang, fonts, hebrew_key="hebrew_section", latin_key="latin_section")
    if lang == "he" and _has_hebrew(title):
        _draw_rtl(draw, WIDTH - PAD - 16, y, title, font, TEXT)
    else:
        _draw_ltr_left(draw, PAD + 16, y, title, font, TEXT)
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
    from PIL import features

    if data.lang == "he" and not features.check("raqm"):
        logger.warning("libraqm not available — Hebrew report card text may render incorrectly")

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
    title_font = _pick_font(
        data.portfolio_name,
        data.lang,
        fonts,
        hebrew_key="hebrew_title",
        latin_key="latin_title",
    )
    if data.lang == "he" and _has_hebrew(data.portfolio_name):
        _draw_rtl(draw, WIDTH - PAD - 24, y, data.portfolio_name, title_font, TEXT)
    elif data.lang == "he":
        _draw_ltr_right(draw, WIDTH - PAD - 24, y, data.portfolio_name, title_font, TEXT)
    else:
        _draw_ltr_left(draw, PAD + 24, y, data.portfolio_name, title_font, TEXT)
    y += 42

    subtitle_font = _pick_font(
        header,
        data.lang,
        fonts,
        hebrew_key="hebrew_subtitle",
        latin_key="latin_subtitle",
    )
    if data.lang == "he" and _has_hebrew(header):
        _draw_rtl(draw, WIDTH - PAD - 24, y, header, subtitle_font, MUTED)
    elif data.lang == "he":
        _draw_ltr_right(draw, WIDTH - PAD - 24, y, header, subtitle_font, MUTED)
    else:
        _draw_ltr_left(draw, PAD + 24, y, header, subtitle_font, MUTED)
    y += 36

    total_text = f"₪{data.total_ils:,.0f}  |  ${data.total_usd:,.2f}"
    _draw_center(draw, WIDTH // 2, y, total_text, fonts["latin_hero"], ACCENT)
    y += 58
    if data.lang == "he":
        _draw_rtl_center(
            draw,
            WIDTH // 2,
            y,
            t["total_value"],
            fonts["hebrew_small"],
            MUTED,
        )
    else:
        _draw_center(draw, WIDTH // 2, y, t["total_value"], fonts["latin_small"], MUTED)
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

    _draw_center(draw, WIDTH // 2, card_bottom - 22, "Stockbot", fonts["latin_small"], MUTED)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
