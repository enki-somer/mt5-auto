from __future__ import annotations

from app.config import TradingRules
from app.parser.parser import normalize_symbol, parse_signal
from app.trading.validation import validate_signal
from app.utils.time import utc_now
from tests.fixtures import EXAMPLE_A, NAS100_SIGNAL


def test_gold_aliases(aliases: dict[str, str]) -> None:
    assert normalize_symbol("GOLD", aliases) == "XAUUSD"
    assert normalize_symbol("XAU", aliases) == "XAUUSD"
    assert normalize_symbol("XAUUSD", aliases) == "XAUUSD"


def test_index_aliases(aliases: dict[str, str]) -> None:
    assert normalize_symbol("NAS100", aliases) == "USTEC"
    assert normalize_symbol("US100", aliases) == "USTEC"


def test_parsed_gold_normalizes(aliases: dict[str, str]) -> None:
    result = parse_signal(EXAMPLE_A, aliases)
    assert result.signal is not None
    assert result.signal.symbol == "GOLD"
    assert result.signal.normalized_symbol == "XAUUSD"


def test_mapped_but_not_allowed(
    aliases: dict[str, str], rules: TradingRules
) -> None:
    result = parse_signal(NAS100_SIGNAL, aliases)
    assert result.signal is not None
    assert result.signal.normalized_symbol == "USTEC"
    result.signal.telegram_message_date = utc_now()
    validation = validate_signal(result.signal, rules)
    assert validation.ok is False
    assert any("USTEC" in item for item in validation.reasons)
