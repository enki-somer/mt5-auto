from __future__ import annotations

import re

from app.parser.normalizer import uppercase_flat
from app.trading.models import Direction, OrderType

TICKER_RE = re.compile(r"\b[A-Z]{3,12}\b")
RESERVED_WORDS = {
    "BUY",
    "SELL",
    "NOW",
    "MARKET",
    "LIMIT",
    "STOP",
    "ENTRY",
    "ENTER",
    "SL",
    "TP",
    "TP1",
    "TP2",
    "TP3",
    "TP4",
    "TP5",
    "LOSS",
    "PROFIT",
    "TAKE",
    "LOT",
    "LOTS",
    "VOLUME",
    "SIZE",
    "LONG",
    "SHORT",
}

DIRECTION_RE = re.compile(r"\b(BUY|SELL)\b")
SL_RE = re.compile(
    r"(?:STOP\s*LOSS|S\s*\.?\s*L\s*\.?|\bSL\b)\s*[:\-]?\s*(\d+(?:\.\d+)?)(?!\.)",
)
TP_INDEXED_RE = re.compile(r"\bTP([1-9])\s*[:\-]?\s*(\d+(?:\.\d+)?)(?!\.)")
TP_PLAIN_RE = re.compile(
    r"(?:TAKE\s*PROFIT|\bTP\b)\s*[:\-]?\s*(\d+(?:\.\d+)?)(?!\.)"
)
TP_RE = re.compile(
    r"(?:TAKE\s*PROFIT|\bTP\b)\s*[:\-]?\s*(\d+(?:\.\d+)?)(?!\.)"
)
ENTRY_RE = re.compile(
    r"\b(?:ENTRY|ENTER)\b\s*[:\-]?\s*(\d+(?:\.\d+)?)(?!\.)(?:\s*(?:[-–]|TO)\s*(\d+(?:\.\d+)?)(?!\.))?",
)
ENTRY_TOKEN_RE = re.compile(
    r"^(\d+(?:\.\d+)?)(?:[-–](\d+(?:\.\d+)?))?$"
)
RANGE_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)(?![\w.])")
VOLUME_RE = re.compile(
    r"(?:VOLUME|SIZE|LOTS?)\s*[:\-]?\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*LOTS?\b",
)
ENTRY_KEYWORD_RE = re.compile(r"\b(ENTRY|ENTER)\b")
SL_KEYWORD_RE = re.compile(r"\b(SL|STOP\s*LOSS)\b")
TP_KEYWORD_RE = re.compile(r"\b(TP|TAKE\s*PROFIT)\b")


def looks_like_ticker(token: str) -> bool:
    return bool(TICKER_RE.fullmatch(token)) and token not in RESERVED_WORDS


def extract_symbol(text: str, aliases: dict[str, str]) -> str | None:
    flat = uppercase_flat(text)
    ordered = sorted(aliases.keys(), key=len, reverse=True)
    for alias in ordered:
        pattern = re.compile(rf"\b{re.escape(alias)}\b")
        if pattern.search(flat):
            return alias
    for token in TICKER_RE.findall(flat):
        if looks_like_ticker(token):
            return token
    return None


def extract_direction(text: str) -> tuple[Direction | None, str | None]:
    flat = uppercase_flat(text)
    found = DIRECTION_RE.findall(flat)
    unique = set(found)
    if "BUY" in unique and "SELL" in unique:
        return None, "Direction detected as both BUY and SELL."
    if "BUY" in unique:
        return Direction.BUY, None
    if "SELL" in unique:
        return Direction.SELL, None
    return None, "Direction not found."


def extract_order_type(text: str, direction: Direction | None) -> OrderType:
    flat = uppercase_flat(text)
    if "BUY LIMIT" in flat:
        return OrderType.BUY_LIMIT
    if "SELL LIMIT" in flat:
        return OrderType.SELL_LIMIT
    if "BUY STOP" in flat:
        return OrderType.BUY_STOP
    if "SELL STOP" in flat:
        return OrderType.SELL_STOP
    if re.search(r"\bLIMIT\b", flat) and direction is not None:
        return (
            OrderType.BUY_LIMIT if direction is Direction.BUY else OrderType.SELL_LIMIT
        )
    if re.search(r"\bSTOP\b", flat) and not re.search(r"STOP\s*LOSS", flat):
        if direction is Direction.BUY:
            return OrderType.BUY_STOP
        if direction is Direction.SELL:
            return OrderType.SELL_STOP
    return OrderType.MARKET


def extract_entry(text: str) -> tuple[float | None, float | None, float | None, str | None]:
    flat = uppercase_flat(text)
    keyword = ENTRY_KEYWORD_RE.search(flat)
    if keyword:
        remainder = flat[keyword.end() :].strip().lstrip(":-").strip()
        token = remainder.split()[0] if remainder else ""
        parsed = ENTRY_TOKEN_RE.fullmatch(token)
        if parsed is None:
            return None, None, None, "Malformed entry price."
        first = float(parsed.group(1))
        second = parsed.group(2)
        if second:
            return None, first, float(second), None
        return first, None, None, None
    labeled = ENTRY_RE.search(flat)
    if labeled:
        first = float(labeled.group(1))
        second = labeled.group(2)
        if second:
            return None, first, float(second), None
        return first, None, None, None
    range_match = RANGE_RE.search(flat)
    if range_match:
        return None, float(range_match.group(1)), float(range_match.group(2)), None
    return None, None, None, None


def extract_stop_loss(text: str) -> tuple[float | None, str | None]:
    flat = uppercase_flat(text)
    match = SL_RE.search(flat)
    if match:
        return float(match.group(1)), None
    if SL_KEYWORD_RE.search(flat):
        return None, "Malformed stop loss."
    return None, None


def extract_take_profits(text: str) -> tuple[list[float], str | None]:
    flat = uppercase_flat(text)
    indexed = TP_INDEXED_RE.findall(flat)
    if indexed:
        return [float(price) for _index, price in indexed], None
    plains = TP_PLAIN_RE.findall(flat)
    if plains:
        return [float(price) for price in plains], None
    if TP_KEYWORD_RE.search(flat):
        return [], "Malformed take profit."
    return [], None


def extract_volume(text: str) -> float | None:
    flat = uppercase_flat(text)
    match = VOLUME_RE.search(flat)
    if not match:
        return None
    raw = match.group(1) or match.group(2)
    return float(raw)
