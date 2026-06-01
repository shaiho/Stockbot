from __future__ import annotations

import re
from dataclasses import dataclass

EVENT_MERGER = "merger"
EVENT_SPINOFF = "spinoff"
EVENT_TICKER_CHANGE = "ticker_change"
EVENT_OFFERING = "offering"
EVENT_HALT = "halt"
EVENT_CIRCUIT_BREAKER = "circuit_breaker"
EVENT_DELISTING = "delisting"
EVENT_INDEX = "index_change"

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (EVENT_HALT, re.compile(r"\b(trading halt|halted|volatility pause|ludp)\b", re.I)),
    (EVENT_CIRCUIT_BREAKER, re.compile(r"\b(circuit breaker|market.?wide halt)\b", re.I)),
    (EVENT_DELISTING, re.compile(r"\b(delisting|delisted|removed from (the )?nasdaq|removed from (the )?nyse)\b", re.I)),
    (EVENT_INDEX, re.compile(r"\b(added to (the )?s&p|removed from (the )?s&p|s&p 500 (addition|deletion|inclusion))\b", re.I)),
    (EVENT_SPINOFF, re.compile(r"\b(spin[- ]?off|spinoff|separation of)\b", re.I)),
    (EVENT_MERGER, re.compile(r"\b(merger|acquisition|to acquire|merges with|buyout)\b", re.I)),
    (EVENT_OFFERING, re.compile(r"\b(secondary offering|public offering|follow-on offering|registered direct)\b", re.I)),
    (EVENT_TICKER_CHANGE, re.compile(r"\b(ticker change|symbol change|renamed to|name change to)\b", re.I)),
]


@dataclass(frozen=True)
class ClassifiedNews:
    event_type: str
    headline: str


def classify_headline(headline: str) -> ClassifiedNews | None:
    text = (headline or "").strip()
    if not text:
        return None
    for event_type, pattern in _PATTERNS:
        if pattern.search(text):
            return ClassifiedNews(event_type=event_type, headline=text)
    return None
