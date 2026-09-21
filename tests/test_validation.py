from __future__ import annotations

from datetime import timedelta

from app.config import TradingRules
from app.parser.parser import parse_signal
from app.trading.models import ValidationStatus
from app.trading.validation import validate_signal
from app.utils.time import utc_now
from tests.fixtures import (
    BUY_SL_ABOVE_ENTRY,
    EXAMPLE_A,
    EXAMPLE_B,
    EXAMPLE_C,
    EXAMPLE_D,
    MISSING_SL,
    MISSING_TP,
    UNSUPPORTED_SYMBOL,
)


def _parsed(body: str, aliases: dict[str, str]):
    result = parse_signal(body, aliases)
    assert result.signal is not None
    return result.signal


def test_valid_examples(aliases: dict[str, str], rules: TradingRules) -> None:
    now = utc_now()
    for body in (EXAMPLE_A, EXAMPLE_C, EXAMPLE_D):
        signal = _parsed(body, aliases)
        signal.telegram_message_date = now
        result = validate_signal(signal, rules, now=now)
        assert result.ok, result.reasons


def test_range_entry_rejected(aliases: dict[str, str], rules: TradingRules) -> None:
    signal = _parsed(EXAMPLE_B, aliases)
    signal.telegram_message_date = utc_now()
    result = validate_signal(signal, rules)
    assert result.ok is False
    assert any("range" in item.lower() for item in result.reasons)


def test_missing_sl_and_tp(aliases: dict[str, str], rules: TradingRules) -> None:
    sl = _parsed(MISSING_SL, aliases)
    sl.telegram_message_date = utc_now()
    sl_result = validate_signal(sl, rules)
    assert sl_result.ok is False
    assert any("Stop loss" in item for item in sl_result.reasons)

    tp = _parsed(MISSING_TP, aliases)
    tp.telegram_message_date = utc_now()
    tp_result = validate_signal(tp, rules)
    assert tp_result.ok is False
    assert any("Take profit" in item for item in tp_result.reasons)


def test_unsupported_symbol(aliases: dict[str, str], rules: TradingRules) -> None:
    signal = _parsed(UNSUPPORTED_SYMBOL, aliases)
    signal.telegram_message_date = utc_now()
    result = validate_signal(signal, rules)
    assert result.ok is False
    assert any("not allowed" in item for item in result.reasons)


def test_buy_sl_above_entry(aliases: dict[str, str], rules: TradingRules) -> None:
    signal = _parsed(BUY_SL_ABOVE_ENTRY, aliases)
    signal.telegram_message_date = utc_now()
    result = validate_signal(signal, rules)
    assert result.ok is False
    assert result.status is ValidationStatus.REJECTED
    assert any("Stop Loss is above entry" in item for item in result.reasons)


def test_volume_cap(aliases: dict[str, str], rules: TradingRules) -> None:
    signal = _parsed(EXAMPLE_A, aliases)
    signal.telegram_message_date = utc_now()
    signal.volume = 1.0
    result = validate_signal(signal, rules)
    assert result.ok is False
    assert any("exceeds maximum" in item for item in result.reasons)


def test_already_executed(aliases: dict[str, str], rules: TradingRules) -> None:
    signal = _parsed(EXAMPLE_A, aliases)
    signal.telegram_message_date = utc_now()
    result = validate_signal(signal, rules, already_executed=True)
    assert result.ok is False
    assert "already been executed" in (result.reason_text or "")


def test_mt5_symbol_and_positions(aliases: dict[str, str], rules: TradingRules) -> None:
    signal = _parsed(EXAMPLE_A, aliases)
    signal.telegram_message_date = utc_now()
    missing = validate_signal(signal, rules, mt5_connected=True, symbol_exists=False)
    assert missing.ok is False
    crowded = validate_signal(
        signal,
        rules,
        mt5_connected=True,
        symbol_exists=True,
        open_positions=rules.maximum_open_positions,
    )
    assert crowded.ok is False


def test_unauthorized_channel(aliases: dict[str, str], rules: TradingRules) -> None:
    signal = _parsed(EXAMPLE_A, aliases)
    signal.telegram_channel_id = 9
    signal.telegram_message_date = utc_now()
    result = validate_signal(signal, rules, allowed_channel_ids=[1001])
    assert result.ok is False
    assert any("not authorized" in item for item in result.reasons)


def test_default_volume_applied(aliases: dict[str, str], rules: TradingRules) -> None:
    signal = _parsed(EXAMPLE_A, aliases)
    signal.telegram_message_date = utc_now()
    signal.volume = None
    result = validate_signal(signal, rules)
    assert result.ok
    assert signal.volume == rules.default_volume


def test_stale_not_used_here_but_fresh_passes(
    aliases: dict[str, str], rules: TradingRules
) -> None:
    signal = _parsed(EXAMPLE_A, aliases)
    signal.telegram_message_date = utc_now() - timedelta(seconds=1)
    result = validate_signal(signal, rules)
    assert result.ok
