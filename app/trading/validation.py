from __future__ import annotations

from datetime import datetime

from app.config import TradingRules
from app.trading.models import (
    Direction,
    OrderType,
    TradeSignal,
    ValidationResult,
    ValidationStatus,
)
from app.trading.risk import resolve_volume
from app.trading.symbol_resolver import symbol_allowed
from app.utils.telegram_ids import is_allowed_channel
from app.utils.time import age_seconds, utc_now

DUPLICATE_REASON = (
    "Same symbol, direction, entry, stop, and take-profits were already "
    "recorded in the last 24 hours."
)

PENDING_TYPES = {
    OrderType.BUY_LIMIT,
    OrderType.SELL_LIMIT,
    OrderType.BUY_STOP,
    OrderType.SELL_STOP,
}


def validate_signal_age(
    message_time: datetime,
    rules: TradingRules,
    now: datetime | None = None,
) -> ValidationResult:
    age = age_seconds(message_time, now)
    if age > rules.maximum_signal_age_seconds:
        return ValidationResult(
            ok=False,
            status=ValidationStatus.REJECTED,
            reasons=[
                f"Signal is stale ({int(age)}s old; limit {rules.maximum_signal_age_seconds}s)."
            ],
        )
    return ValidationResult(ok=True, status=ValidationStatus.PARSED)


def _price_reference(signal: TradeSignal, market_price: float | None) -> float | None:
    if signal.entry_price is not None:
        return signal.entry_price
    if signal.order_type is OrderType.MARKET:
        return market_price
    return None


def _direction_price_errors(
    signal: TradeSignal, reference: float | None
) -> list[str]:
    if signal.direction is None or reference is None:
        return []
    errors: list[str] = []
    if signal.direction is Direction.BUY:
        if signal.stop_loss is not None and signal.stop_loss >= reference:
            errors.append(
                "Direction detected as BUY, but Stop Loss is above entry price."
            )
        for take_profit in signal.take_profits:
            if take_profit <= reference:
                errors.append(
                    "Direction detected as BUY, but Take Profit is below entry price."
                )
                break
        return errors
    if signal.direction is Direction.SELL:
        if signal.stop_loss is not None and signal.stop_loss <= reference:
            errors.append(
                "Direction detected as SELL, but Stop Loss is below entry price."
            )
        for take_profit in signal.take_profits:
            if take_profit >= reference:
                errors.append(
                    "Direction detected as SELL, but Take Profit is above entry price."
                )
                break
        return errors
    never: Direction = signal.direction
    raise ValueError(f"Unhandled direction: {never}")


def validate_signal(
    signal: TradeSignal,
    rules: TradingRules,
    *,
    allowed_channel_ids: list[int] | None = None,
    now: datetime | None = None,
    mt5_connected: bool = False,
    symbol_exists: bool | None = None,
    market_price: float | None = None,
    open_positions: int | None = None,
    already_executed: bool = False,
    semantic_duplicate: bool = False,
) -> ValidationResult:
    reasons: list[str] = []
    requires_review = False

    if already_executed:
        return ValidationResult(
            ok=False,
            status=ValidationStatus.REJECTED,
            reasons=["Message ID has already been executed."],
        )

    if allowed_channel_ids is not None and signal.telegram_channel_id is not None:
        if not is_allowed_channel(signal.telegram_channel_id, allowed_channel_ids):
            reasons.append("Signal source is not authorized.")

    if signal.direction is None:
        reasons.append("Direction is missing.")
    elif signal.direction.value not in rules.allowed_directions:
        reasons.append(f"Direction {signal.direction.value} is not allowed.")

    if signal.order_type is None:
        reasons.append("Order type is missing.")
    else:
        if signal.order_type is OrderType.MARKET and not rules.allow_market_orders:
            reasons.append("Market orders are not allowed.")
        if signal.order_type in PENDING_TYPES and not rules.allow_pending_orders:
            reasons.append("Pending orders are not allowed.")

    if not signal.normalized_symbol:
        reasons.append("Symbol is missing.")
    elif not symbol_allowed(
        signal.normalized_symbol, signal.broker_symbol, rules.allowed_symbols
    ):
        reasons.append(f"Symbol {signal.normalized_symbol} is not allowed.")

    if signal.has_entry_range():
        reasons.append("Entry is a price range; a single entry price is required.")

    if signal.order_type in PENDING_TYPES and signal.entry_price is None:
        reasons.append("Entry price is required for pending orders.")

    if rules.require_stop_loss and signal.stop_loss is None:
        reasons.append("Stop loss is required.")

    if rules.require_take_profit and not signal.take_profits:
        reasons.append("Take profit is required.")
    elif len(signal.take_profits) < rules.minimum_take_profits:
        reasons.append(
            f"At least {rules.minimum_take_profits} take-profit level(s) required."
        )

    volume = resolve_volume(signal, rules)
    if volume <= 0:
        reasons.append("Volume must be greater than zero.")
    if volume > rules.maximum_volume:
        reasons.append(
            f"Volume {volume} exceeds maximum {rules.maximum_volume}."
        )
    signal.volume = volume

    if signal.telegram_message_date is not None:
        age_result = validate_signal_age(
            signal.telegram_message_date, rules, now or utc_now()
        )
        if not age_result.ok:
            reasons.extend(age_result.reasons)

    reference = _price_reference(signal, market_price)
    reasons.extend(_direction_price_errors(signal, reference))

    if mt5_connected:
        if symbol_exists is False:
            label = signal.symbol or signal.normalized_symbol or "this"
            reasons.append(f"No tradable {label} symbol on this MetaTrader account.")
        if (
            open_positions is not None
            and open_positions >= rules.maximum_open_positions
        ):
            reasons.append("Maximum open position limit exceeded.")
    if semantic_duplicate:
        requires_review = True
        reasons.append(DUPLICATE_REASON)

    other_reasons = [item for item in reasons if item != DUPLICATE_REASON]
    if semantic_duplicate and not other_reasons:
        return ValidationResult(
            ok=False,
            status=ValidationStatus.SEMANTIC_DUPLICATE,
            reasons=reasons,
            requires_review=True,
        )
    if semantic_duplicate:
        return ValidationResult(
            ok=False,
            status=ValidationStatus.REJECTED,
            reasons=reasons,
            requires_review=True,
        )
    if reasons:
        return ValidationResult(
            ok=False,
            status=ValidationStatus.REJECTED,
            reasons=reasons,
            requires_review=requires_review,
        )
    return ValidationResult(ok=True, status=ValidationStatus.PARSED)
