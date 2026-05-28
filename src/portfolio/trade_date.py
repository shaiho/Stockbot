from __future__ import annotations

from datetime import datetime

import pytz

from src.config import TIMEZONE

DATE_FORMATS = ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d.%m.%Y")
TODAY_TOKENS = {"", "today", "היום"}


def parse_trade_date(text: str | None) -> str:
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    raw = (text or "").strip().lower()
    if raw in TODAY_TOKENS:
        return now.strftime("%Y-%m-%d %H:%M:%S")

    for fmt in DATE_FORMATS:
        try:
            dt = datetime.strptime((text or "").strip(), fmt)
        except ValueError:
            continue
        dt = tz.localize(dt.replace(hour=12, minute=0, second=0))
        if dt.date() > now.date():
            raise ValueError("future_date")
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    raise ValueError("invalid_date")
