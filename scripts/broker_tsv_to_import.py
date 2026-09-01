#!/usr/bin/env python3
"""Convert broker TSV/CSV export to Stockbot portfolio import JSON."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from io import StringIO
from pathlib import Path

ACTION_MAP = {
    "קניה": "buy",
    "מכירה": "sell",
    "buy": "buy",
    "sell": "sell",
}

SYMBOL_HEADERS = ("מספר נייר/סימבול", "symbol", "סימבול")
ACTION_HEADERS = ("סוג פעולה", "action", "פעולה")
QTY_HEADERS = ("כמות מבוצעת", "כמות ביצוע", "quantity", "כמות")
PRICE_HEADERS = ("שער ביצוע", "price", "מחיר")
DATE_HEADERS = ("תאריך ביצוע", "date", "תאריך")


def _pick(row: dict[str, str], keys: tuple[str, ...]) -> str:
    for key in keys:
        if key in row and row[key].strip():
            return row[key].strip()
    raise KeyError(f"missing column, expected one of: {keys}")


def _parse_qty(raw: str) -> float:
    cleaned = raw.strip().replace(",", "").replace(" ", "")
    cleaned = cleaned.rstrip("-").lstrip("-")
    return abs(float(cleaned))


def _parse_action(raw: str) -> str:
    action = ACTION_MAP.get(raw.strip(), ACTION_MAP.get(raw.strip().lower()))
    if not action:
        raise ValueError(f"unknown action: {raw!r}")
    return action


def parse_rows(text: str) -> list[dict]:
    sample = text.lstrip("\ufeff")
    delimiter = "\t" if "\t" in sample.splitlines()[0] else ","
    reader = csv.DictReader(StringIO(sample), delimiter=delimiter)
    if not reader.fieldnames:
        raise ValueError("empty file")

    trades = []
    for line_no, row in enumerate(reader, start=2):
        if not row or not any(v and str(v).strip() for v in row.values()):
            continue
        try:
            symbol = _pick(row, SYMBOL_HEADERS).upper()
            action = _parse_action(_pick(row, ACTION_HEADERS))
            quantity = _parse_qty(_pick(row, QTY_HEADERS))
            price = float(_pick(row, PRICE_HEADERS).replace(",", ""))
            date = _pick(row, DATE_HEADERS)
        except (KeyError, ValueError) as exc:
            raise ValueError(f"line {line_no}: {exc}") from exc

        if quantity <= 0 or price < 0:
            raise ValueError(f"line {line_no}: invalid quantity/price")

        trades.append(
            {
                "symbol": symbol,
                "market": "US",
                "action": action,
                "quantity": quantity,
                "price": price,
                "currency": "USD",
                "commission": 0,
                "date": date,
                "note": "broker import",
            }
        )
    return trades


def build_import_json(
    trades: list[dict],
    *,
    opening_usd: float = 0,
    opening_ils: float = 0,
    replace: bool = True,
    commission: float = 0,
) -> dict:
    if commission:
        for trade in trades:
            if trade["action"] in ("buy", "sell"):
                trade["commission"] = commission
    return {
        "opening_cash": {"ILS": opening_ils, "USD": opening_usd},
        "replace": replace,
        "trades": trades,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Broker TSV → Stockbot import JSON")
    parser.add_argument("input", nargs="?", type=Path, help="TSV/CSV file (stdin if omitted)")
    parser.add_argument("-o", "--output", type=Path, help="output JSON path")
    parser.add_argument("--opening-usd", type=float, default=0)
    parser.add_argument("--opening-ils", type=float, default=0)
    parser.add_argument("--commission", type=float, default=0, help="per-trade commission in USD")
    parser.add_argument("--no-replace", action="store_true")
    args = parser.parse_args()

    raw = args.input.read_text(encoding="utf-8") if args.input else sys.stdin.read()
    trades = parse_rows(raw)
    payload = build_import_json(
        trades,
        opening_usd=args.opening_usd,
        opening_ils=args.opening_ils,
        replace=not args.no_replace,
        commission=args.commission,
    )
    out = json.dumps(payload, ensure_ascii=False, indent=2)

    if args.output:
        args.output.write_text(out, encoding="utf-8")
        print(f"Wrote {len(trades)} trades → {args.output}", file=sys.stderr)
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
