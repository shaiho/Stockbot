from __future__ import annotations

import json
from pathlib import Path

from src.config import LOCALES_DIR


class I18n:
    def __init__(self) -> None:
        self._cache: dict[str, dict[str, str]] = {}

    def load(self, lang: str) -> dict[str, str]:
        lang = lang if lang in ("he", "en") else "he"
        if lang not in self._cache:
            path = LOCALES_DIR / f"{lang}.json"
            self._cache[lang] = json.loads(path.read_text(encoding="utf-8"))
        return self._cache[lang]

    def t(self, lang: str, key: str) -> str:
        return self.load(lang).get(key, key)


i18n = I18n()
