from __future__ import annotations

from datetime import datetime

from app.config import Settings, TradingRules
from app.database.repository import Repository
from app.parser.parser import parse_signal
from app.trading.duplicates import (
    find_semantic_duplicates,
    message_already_executed,
    message_already_processed,
)
from app.trading.execution_controller import ExecutionController
from app.trading.loop import (
    LoopStep,
    SignalLoopRecord,
    StatusKind,
    describe_validation,
    snippet_of,
)
from app.trading.models import (
    ExecutionStatus,
    MessageStatus,
    TradeSignal,
    ValidationStatus,
)
from app.trading.validation import validate_signal
from app.utils.health import RuntimeState
from app.utils.logging import get_logger
from app.utils.telegram_ids import is_allowed_channel
from app.utils.time import utc_now

logger = get_logger("application")
parser_logger = get_logger("parser")
telegram_logger = get_logger("telegram")


class SignalProcessor:
    def __init__(
        self,
        settings: Settings,
        rules: TradingRules,
        aliases: dict[str, str],
        repository: Repository,
        state: RuntimeState,
        execution: ExecutionController,
    ) -> None:
        self._settings = settings
        self._rules = rules
        self._aliases = aliases
        self._repository = repository
        self._state = state
        self._execution = execution

    def handle_new_message(
        self,
        channel_id: int,
        message_id: int,
        raw_text: str,
        *,
        channel_name: str | None = None,
        message_date: datetime | None = None,
        is_forwarded: bool = False,
        market_price: float | None = None,
        symbol_exists: bool | None = None,
        open_positions: int | None = None,
    ) -> TradeSignal | None:
        self._state.last_telegram_event = utc_now()
        allowed = self._settings.allowed_channel_id_list()
        if not is_allowed_channel(channel_id, allowed):
            telegram_logger.info("Ignored unauthorized channel %s", channel_id)
            self._repository.save_message(
                channel_id,
                message_id,
                raw_text,
                channel_name=channel_name,
                message_date=message_date,
                is_forwarded=is_forwarded,
                status=MessageStatus.IGNORED.value,
            )
            self._record_loop(
                headline="Channel not allowed",
                snippet=raw_text,
                steps=[
                    LoopStep(
                        "Telegram",
                        "Ignored",
                        f"Channel {channel_id} is not in Allowed channel IDs.",
                        "bad",
                    ),
                    LoopStep("Parser", "Skipped", "The post was not opened.", "idle"),
                    LoopStep("Check", "Stopped", "Unauthorized source.", "bad"),
                    LoopStep("Action", "No MetaTrader order was sent.", "", "idle"),
                ],
                outcome="Not from an allowed channel. No order was sent.",
                kind="bad",
            )
            return None

        if message_already_processed(self._repository, channel_id, message_id):
            telegram_logger.info(
                "Duplicate Telegram message %s/%s ignored", channel_id, message_id
            )
            self._record_loop(
                headline="Same Telegram post",
                snippet=raw_text,
                steps=[
                    LoopStep(
                        "Telegram",
                        "Already seen",
                        f"Message {message_id} was processed before.",
                        "warn",
                    ),
                    LoopStep("Parser", "Skipped", "The same post is not parsed twice.", "idle"),
                    LoopStep("Check", "Duplicate post", "Not a new signal.", "warn"),
                    LoopStep("Action", "No MetaTrader order was sent.", "", "idle"),
                ],
                outcome="This Telegram post was already handled. No second order.",
                kind="warn",
            )
            return None

        self._repository.save_message(
            channel_id,
            message_id,
            raw_text,
            channel_name=channel_name,
            message_date=message_date,
            is_forwarded=is_forwarded,
            status=MessageStatus.RECEIVED.value,
        )
        if self._state.paused:
            self._repository.update_message(
                channel_id, message_id, status=MessageStatus.RECEIVED.value
            )
            self._record_loop(
                headline="Paused",
                snippet=raw_text,
                steps=[
                    LoopStep("Telegram", "Received", f"Message {message_id} from {channel_id}.", "ok"),
                    LoopStep("Parser", "On hold", "Processing is paused.", "warn"),
                    LoopStep("Check", "Skipped", "Press Resume to handle new posts.", "warn"),
                    LoopStep("Action", "No MetaTrader order was sent.", "", "idle"),
                ],
                outcome="App is paused. The post was saved, not traded.",
                kind="warn",
            )
            return None
        return self._parse_and_store(
            channel_id,
            message_id,
            raw_text,
            message_date=message_date,
            is_forwarded=is_forwarded,
            is_edited=False,
            market_price=market_price,
            symbol_exists=symbol_exists,
            open_positions=open_positions,
        )

    def handle_edit(
        self,
        channel_id: int,
        message_id: int,
        raw_text: str,
        *,
        message_date: datetime | None = None,
        market_price: float | None = None,
        symbol_exists: bool | None = None,
        open_positions: int | None = None,
    ) -> TradeSignal | None:
        self._state.last_telegram_event = utc_now()
        existing = self._repository.get_message(channel_id, message_id)
        if existing is None:
            return self.handle_new_message(
                channel_id,
                message_id,
                raw_text,
                message_date=message_date,
                market_price=market_price,
                symbol_exists=symbol_exists,
                open_positions=open_positions,
            )
        if message_already_executed(self._repository, channel_id, message_id):
            self._repository.update_message(
                channel_id,
                message_id,
                previous_text=existing.raw_text,
                raw_text=raw_text,
                is_edited=True,
                status=MessageStatus.EDITED_AFTER_EXECUTE.value,
            )
            self._repository.add_event(
                "Executed signal edited; manual review required.",
                level="WARNING",
                category="telegram",
                details={"channel_id": channel_id, "message_id": message_id},
            )
            self._record_loop(
                headline="Edited after a past execute flag",
                snippet=raw_text,
                steps=[
                    LoopStep("Telegram", "Edit received", f"Message {message_id} changed.", "warn"),
                    LoopStep("Parser", "Skipped", "This post was already marked executed.", "warn"),
                    LoopStep("Check", "Locked", "Edits do not open a new trade.", "warn"),
                    LoopStep("Action", "No MetaTrader order was sent.", "", "idle"),
                ],
                outcome="An already-handled trade post was edited. No new order.",
                kind="warn",
            )
            return None
        self._repository.update_message(
            channel_id,
            message_id,
            previous_text=existing.raw_text,
            raw_text=raw_text,
            is_edited=True,
            status=MessageStatus.RECEIVED.value,
        )
        return self._parse_and_store(
            channel_id,
            message_id,
            raw_text,
            message_date=message_date or existing.message_date,
            is_forwarded=existing.is_forwarded,
            is_edited=True,
            market_price=market_price,
            symbol_exists=symbol_exists,
            open_positions=open_positions,
        )

    def handle_delete(self, channel_id: int, message_id: int) -> None:
        self._state.last_telegram_event = utc_now()
        existing = self._repository.get_message(channel_id, message_id)
        if existing is None:
            return
        if message_already_executed(self._repository, channel_id, message_id):
            self._repository.update_message(
                channel_id,
                message_id,
                is_deleted=True,
                status=MessageStatus.EXECUTED.value,
            )
            self._repository.add_event(
                "Executed signal deleted in Telegram; MT5 position was not closed.",
                level="WARNING",
                category="telegram",
                details={"channel_id": channel_id, "message_id": message_id},
            )
            return
        self._repository.update_message(
            channel_id,
            message_id,
            is_deleted=True,
            status=MessageStatus.DELETED.value,
        )

    def _parse_and_store(
        self,
        channel_id: int,
        message_id: int,
        raw_text: str,
        *,
        message_date: datetime | None,
        is_forwarded: bool,
        is_edited: bool,
        market_price: float | None,
        symbol_exists: bool | None,
        open_positions: int | None,
    ) -> TradeSignal | None:
        parsed = parse_signal(raw_text, self._aliases)
        if not parsed.is_signal or parsed.signal is None:
            self._repository.update_message(
                channel_id, message_id, status=MessageStatus.IGNORED.value
            )
            self._record_loop(
                headline="Not a trade post",
                snippet=raw_text,
                steps=[
                    LoopStep(
                        "Telegram",
                        "Received",
                        f"Message {message_id} from allowed channel.",
                        "ok",
                    ),
                    LoopStep(
                        "Parser",
                        "No trade found",
                        "Missing a clear symbol/direction/entry pattern.",
                        "idle",
                    ),
                    LoopStep("Check", "Skipped", "Nothing to validate.", "idle"),
                    LoopStep("Action", "No MetaTrader order was sent.", "", "idle"),
                ],
                outcome="The post was not treated as a signal. No order was sent.",
                kind="idle",
            )
            return None

        signal = parsed.signal
        signal.telegram_channel_id = channel_id
        signal.telegram_message_id = message_id
        signal.telegram_message_date = message_date
        signal.is_forwarded = is_forwarded
        signal.is_edited = is_edited
        telegram_step = LoopStep(
            "Telegram",
            "Received",
            f"Message {message_id} from allowed channel.",
            "ok",
        )
        if parsed.rejection_reason:
            signal.validation_status = ValidationStatus.INVALID
            signal.rejection_reason = parsed.rejection_reason
            self._repository.save_signal(signal)
            self._repository.update_message(
                channel_id, message_id, status=MessageStatus.INVALID.value
            )
            self._record_loop(
                headline=self._headline(signal),
                snippet=raw_text,
                steps=[
                    telegram_step,
                    LoopStep("Parser", "Incomplete", parsed.rejection_reason, "bad"),
                    LoopStep("Check", "Not valid", describe_validation(signal.validation_status), "bad"),
                    LoopStep("Action", "No MetaTrader order was sent.", "", "idle"),
                ],
                outcome=f"Could not use this post: {parsed.rejection_reason}",
                kind="bad",
            )
            parser_logger.info("Parse rejected message %s: %s", message_id, parsed.rejection_reason)
            return signal

        if symbol_exists is None or market_price is None or open_positions is None:
            exists, price, opens = self._execution.resolve_for_signal(signal)
            if symbol_exists is None:
                symbol_exists = exists
            if market_price is None:
                market_price = price
            if open_positions is None:
                open_positions = opens
        traded_as = signal.broker_symbol or signal.normalized_symbol
        parse_detail = ", ".join(
            part
            for part in (
                traded_as,
                signal.direction.value if signal.direction else None,
                signal.order_type.value if signal.order_type else None,
                f"SL {signal.stop_loss}" if signal.stop_loss is not None else None,
                f"TP {', '.join(str(item) for item in signal.take_profits)}" if signal.take_profits else None,
            )
            if part
        )
        semantic = find_semantic_duplicates(self._repository, signal, self._rules)
        result = validate_signal(
            signal,
            self._rules,
            allowed_channel_ids=self._settings.allowed_channel_id_list(),
            mt5_connected=self._state.mt5_connected,
            symbol_exists=symbol_exists,
            market_price=market_price,
            open_positions=open_positions,
            already_executed=message_already_executed(
                self._repository, channel_id, message_id
            ),
            semantic_duplicate=bool(semantic),
        )
        signal.validation_status = result.status
        signal.rejection_reason = result.reason_text
        if result.ok:
            applied = self._execution.apply(signal)
            signal.execution_status = applied.status
            action_text = applied.detail
            order_sent = applied.order_sent
            status = _message_status(applied.status)
            check_kind: StatusKind = "ok"
            action_kind: StatusKind = "ok" if order_sent else (
                "bad" if applied.status is ExecutionStatus.FAILED else "warn"
            )
            loop_kind: StatusKind = "ok" if order_sent else (
                "bad" if applied.status is ExecutionStatus.FAILED else "warn"
            )
        elif result.status is ValidationStatus.SEMANTIC_DUPLICATE:
            signal.execution_status = ExecutionStatus.WAITING_APPROVAL
            status = MessageStatus.SEMANTIC_DUPLICATE
            check_kind = "warn"
            action_text = "Held because this trade was already recorded. No MetaTrader order was sent."
            order_sent = False
            action_kind = "warn"
            loop_kind = "warn"
        else:
            signal.execution_status = ExecutionStatus.NONE
            status = MessageStatus.REJECTED
            check_kind = "bad"
            action_text = "No MetaTrader order was sent."
            order_sent = False
            action_kind = "idle"
            loop_kind = "bad"
        self._repository.save_signal(signal)
        self._repository.update_message(channel_id, message_id, status=status.value)
        reason = signal.rejection_reason or describe_validation(result.status)
        outcome = f"{describe_validation(result.status)}. {action_text}"
        if signal.rejection_reason:
            outcome = f"{reason} {action_text}"
        self._record_loop(
            headline=self._headline(signal),
            snippet=raw_text,
            steps=[
                telegram_step,
                LoopStep("Parser", "Read the trade", parse_detail, "ok"),
                LoopStep("Check", describe_validation(result.status), reason if not result.ok else "Rules passed.", check_kind),
                LoopStep(
                    "Action",
                    "Sent" if order_sent else "No order",
                    action_text,
                    action_kind,
                ),
            ],
            outcome=outcome,
            kind=loop_kind,
            order_sent=order_sent,
        )
        parser_logger.info(
            "Processed message %s status=%s reason=%s",
            message_id,
            status.value,
            signal.rejection_reason,
        )
        return signal

    def _headline(self, signal: TradeSignal) -> str:
        symbol = signal.broker_symbol or signal.normalized_symbol or signal.symbol or "Signal"
        direction = signal.direction.value if signal.direction else ""
        return f"{symbol} {direction}".strip()

    def _record_loop(
        self,
        *,
        headline: str,
        snippet: str,
        steps: list[LoopStep],
        outcome: str,
        kind: StatusKind,
        order_sent: bool = False,
    ) -> None:
        self._state.record_loop(
            SignalLoopRecord(
                headline=headline,
                outcome=outcome,
                kind=kind,
                order_sent=order_sent,
                steps=steps,
                snippet=snippet_of(snippet),
            )
        )


def _message_status(execution: ExecutionStatus) -> MessageStatus:
    if execution is ExecutionStatus.WAITING_APPROVAL:
        return MessageStatus.WAITING_APPROVAL
    if execution is ExecutionStatus.EXECUTED:
        return MessageStatus.EXECUTED
    if execution is ExecutionStatus.FAILED:
        return MessageStatus.FAILED
    if execution is ExecutionStatus.EXECUTING:
        return MessageStatus.EXECUTING
    if execution is ExecutionStatus.REJECTED:
        return MessageStatus.REJECTED
    if execution is ExecutionStatus.APPROVED:
        return MessageStatus.APPROVED
    if execution is ExecutionStatus.NONE:
        return MessageStatus.PARSED
    if execution is ExecutionStatus.OBSERVED:
        return MessageStatus.PARSED
    if execution is ExecutionStatus.DRY_RUN:
        return MessageStatus.PARSED
    never: ExecutionStatus = execution
    raise ValueError(f"Unhandled execution status: {never}")
