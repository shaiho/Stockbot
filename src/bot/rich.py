"""Helpers for Bot API 10.3 rich messages (native tables)."""
from __future__ import annotations

from aiogram import Bot
from aiogram.methods import SendRichMessage
from aiogram.types import (
    InlineKeyboardMarkup,
    InputRichBlockSectionHeading,
    InputRichBlockTable,
    InputRichMessage,
    RichBlockTableCell,
)

def heading(text: str, size: int = 1) -> InputRichBlockSectionHeading:
    return InputRichBlockSectionHeading(text=text, size=size)


def cell(text: object, *, align: str = "left", header: bool = False) -> RichBlockTableCell:
    return RichBlockTableCell(
        text=str(text),
        align=align,
        valign="middle",
        is_header=header or None,
    )


def table(
    header: list[str] | None,
    rows: list[list[object]],
    *,
    aligns: list[str] | None = None,
    caption: str | None = None,
    compact: bool = True,
) -> InputRichBlockTable:
    ncols = len(header) if header else (len(rows[0]) if rows else 0)
    aligns = aligns or ["left"] * ncols
    cells = [[cell(h, align=a, header=True) for h, a in zip(header, aligns)]] if header else []
    for row in rows:
        cells.append([cell(v, align=a) for v, a in zip(row, aligns)])
    return InputRichBlockTable(
        cells=cells,
        is_bordered=True,
        is_striped=True,
        is_compact=compact,
        caption=caption,
    )


async def send_rich(
    bot: Bot,
    chat_id: int,
    blocks: list,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    await bot(
        SendRichMessage(
            chat_id=chat_id,
            rich_message=InputRichMessage(blocks=blocks, is_rtl=True),
            reply_markup=reply_markup,
        )
    )
