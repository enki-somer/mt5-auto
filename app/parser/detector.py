from __future__ import annotations

from app.parser.extractor import (
    DIRECTION_RE,
    SL_RE,
    TICKER_RE,
    TP_RE,
    extract_symbol,
    looks_like_ticker,
)
from app.parser.normalizer import uppercase_flat


def detect_signal(text: str, aliases: dict[str, str]) -> bool:
    flat = uppercase_flat(text)
    if not flat:
        return False
    has_direction = bool(DIRECTION_RE.search(flat))
    symbol = extract_symbol(flat, aliases)
    has_ticker = symbol is not None or any(
        looks_like_ticker(token) for token in TICKER_RE.findall(flat)
    )
    has_levels = bool(SL_RE.search(flat) or TP_RE.search(flat))
    return has_direction and (has_ticker or has_levels)
