from __future__ import annotations

from app.config import ExecutionMode
from app.trading.loop import describe_action, describe_validation, format_loop_feed, visual_verdict
from app.trading.models import ExecutionStatus, ValidationStatus
from app.trading.processor import SignalProcessor
from tests.fixtures import EXAMPLE_A, EXAMPLE_C


def test_semantic_duplicate_explains_why(processor: SignalProcessor) -> None:
    processor.handle_new_message(1001, 10, EXAMPLE_C)
    second = processor.handle_new_message(1001, 11, EXAMPLE_C)
    assert second is not None
    assert second.validation_status is ValidationStatus.SEMANTIC_DUPLICATE
    assert second.rejection_reason is not None
    assert "already recorded" in second.rejection_reason
    events = processor._state.loop_events
    assert events
    latest = events[0]
    assert latest.order_sent is False
    assert "already recorded" in latest.outcome
    assert "NO ORDER" in format_loop_feed(events).upper() or "No MetaTrader order" in format_loop_feed(
        events
    )


def test_valid_signal_loop_says_no_order(processor: SignalProcessor) -> None:
    signal = processor.handle_new_message(1001, 50, EXAMPLE_A)
    assert signal is not None
    assert signal.validation_status is ValidationStatus.PARSED
    latest = processor._state.loop_events[0]
    assert latest.order_sent is False
    assert "Watch only" in latest.outcome or "No MetaTrader order" in latest.outcome
    names = [step.name for step in latest.steps]
    assert names == ["Telegram", "Parser", "Check", "Action"]


def test_unauthorized_channel_appears_in_loop(processor: SignalProcessor) -> None:
    processor.handle_new_message(9999, 1, EXAMPLE_A)
    latest = processor._state.loop_events[0]
    assert "not in Allowed" in latest.outcome or "allowed channel" in latest.outcome.lower()
    assert latest.order_sent is False


def test_describe_validation_covers_all_statuses() -> None:
    for status in ValidationStatus:
        text = describe_validation(status)
        assert text


def test_describe_action_never_claims_send_in_observe() -> None:
    text, sent = describe_action(
        ExecutionStatus.OBSERVED, mode=ExecutionMode.OBSERVE, dry_run=True
    )
    assert sent is False
    assert "No MetaTrader order" in text


def test_visual_verdict_says_did_not_trade(processor: SignalProcessor) -> None:
    processor.handle_new_message(1001, 10, EXAMPLE_C)
    processor.handle_new_message(1001, 11, EXAMPLE_C)
    title, why, kind = visual_verdict(processor._state.loop_events[0])
    assert "Did not trade" in title
    assert "already" in why.lower()
    assert kind == "warn"
