from __future__ import annotations

from dataclasses import dataclass

from app.parser.detector import detect_signal
from app.parser.extractor import (
    extract_direction,
    extract_entry,
    extract_order_type,
    extract_stop_loss,
    extract_symbol,
    extract_take_profits,
    extract_volume,
)
from app.parser.normalizer import normalize_text
from app.trading.models import TradeSignal, ValidationStatus


@dataclass
class ParseResult:
    is_signal: bool
    signal: TradeSignal | None
    rejection_reason: str | None
    confidence: float


def normalize_symbol(symbol: str | None, aliases: dict[str, str]) -> str | None:
    if symbol is None:
        return None
    return aliases.get(symbol.upper(), symbol.upper())


def _confidence(signal: TradeSignal) -> float:
    score = 0.0
    if signal.normalized_symbol:
        score += 0.2
    if signal.direction:
        score += 0.2
    if signal.stop_loss is not None:
        score += 0.2
    if signal.take_profits:
        score += 0.2
    if signal.entry_price is not None or signal.order_type and signal.order_type.value == "MARKET":
        score += 0.2
    return round(score, 2)


def parse_signal(raw_message: str, aliases: dict[str, str]) -> ParseResult:
    normalized = normalize_text(raw_message)
    if not detect_signal(normalized, aliases):
        return ParseResult(False, None, None, 0.0)

    reasons: list[str] = []
    symbol = extract_symbol(normalized, aliases)
    direction, direction_error = extract_direction(normalized)
    if direction_error:
        reasons.append(direction_error)
    order_type = extract_order_type(normalized, direction)
    entry, entry_low, entry_high, entry_error = extract_entry(normalized)
    if entry_error:
        reasons.append(entry_error)
    stop_loss, sl_error = extract_stop_loss(normalized)
    if sl_error:
        reasons.append(sl_error)
    take_profits, tp_error = extract_take_profits(normalized)
    if tp_error:
        reasons.append(tp_error)
    volume = extract_volume(normalized)
    mapped = normalize_symbol(symbol, aliases)
    signal = TradeSignal(
        raw_message=raw_message,
        symbol=symbol,
        normalized_symbol=mapped,
        direction=direction,
        order_type=order_type,
        entry_price=entry,
        entry_low=entry_low,
        entry_high=entry_high,
        stop_loss=stop_loss,
        take_profits=take_profits,
        volume=volume,
        validation_status=ValidationStatus.INVALID if reasons else ValidationStatus.PARSED,
        rejection_reason="; ".join(reasons) if reasons else None,
    )
    signal.parser_confidence = _confidence(signal)
    if reasons:
        return ParseResult(True, signal, signal.rejection_reason, signal.parser_confidence)
    return ParseResult(True, signal, None, signal.parser_confidence)
