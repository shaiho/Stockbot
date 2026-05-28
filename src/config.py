from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
LOCALES_DIR = BASE_DIR / "locales"
DATA_DIR = BASE_DIR / "data"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", str(DATA_DIR / "stockbot.db")))
TIMEZONE = os.getenv("TIMEZONE", "Asia/Jerusalem")

MAX_PORTFOLIOS_PER_USER = 5
PRICE_CACHE_SECONDS = 300
ALERT_CHECK_MINUTES = 15
QUOTE_RATE_LIMIT_PER_MINUTE = int(os.getenv("QUOTE_RATE_LIMIT_PER_MINUTE", "55"))
NEWS_CACHE_SECONDS = int(os.getenv("NEWS_CACHE_SECONDS", "3600"))
TAX_RATE = 0.25
