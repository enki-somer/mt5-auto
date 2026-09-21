from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.database.models import (
    ApplicationEvent,
    ExecutedTrade,
    TelegramMessage,
    TradeAttempt,
    TradeSignalRecord,
)
from app.trading.models import MessageStatus, TradeSignal
from app.utils.time import utc_now


class Repository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def save_message(
        self,
        channel_id: int,
        message_id: int,
        raw_text: str,
        *,
        channel_name: str | None = None,
        message_date: datetime | None = None,
        is_forwarded: bool = False,
        status: str = MessageStatus.RECEIVED.value,
    ) -> TelegramMessage:
        with self._session_factory() as session:
            record = TelegramMessage(
                telegram_channel_id=channel_id,
                telegram_message_id=message_id,
                channel_name=channel_name,
                raw_text=raw_text,
                message_date=message_date,
                received_at=utc_now(),
                updated_at=utc_now(),
                is_forwarded=is_forwarded,
                status=status,
            )
            session.add(record)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = self.get_message(channel_id, message_id)
                if existing is None:
                    raise
                return existing
            session.refresh(record)
            return record

    def get_message(self, channel_id: int, message_id: int) -> TelegramMessage | None:
        with self._session_factory() as session:
            statement: Select[tuple[TelegramMessage]] = select(TelegramMessage).where(
                TelegramMessage.telegram_channel_id == channel_id,
                TelegramMessage.telegram_message_id == message_id,
            )
            return session.scalars(statement).first()

    def update_message(
        self,
        channel_id: int,
        message_id: int,
        **changes: object,
    ) -> TelegramMessage | None:
        with self._session_factory() as session:
            statement = select(TelegramMessage).where(
                TelegramMessage.telegram_channel_id == channel_id,
                TelegramMessage.telegram_message_id == message_id,
            )
            record = session.scalars(statement).first()
            if record is None:
                return None
            for key, value in changes.items():
                setattr(record, key, value)
            record.updated_at = utc_now()
            session.commit()
            session.refresh(record)
            return record

    def save_signal(self, signal: TradeSignal) -> TradeSignalRecord:
        with self._session_factory() as session:
            record = TradeSignalRecord(
                signal_id=signal.signal_id,
                telegram_channel_id=signal.telegram_channel_id,
                telegram_message_id=signal.telegram_message_id,
                telegram_message_date=signal.telegram_message_date,
                received_at=signal.received_at,
                raw_message=signal.raw_message,
                symbol=signal.symbol,
                normalized_symbol=signal.normalized_symbol,
                direction=signal.direction.value if signal.direction else None,
                order_type=signal.order_type.value if signal.order_type else None,
                entry_price=signal.entry_price,
                entry_low=signal.entry_low,
                entry_high=signal.entry_high,
                stop_loss=signal.stop_loss,
                take_profits_json=json.dumps(signal.take_profits),
                volume=signal.volume,
                risk_percent=signal.risk_percent,
                comment=signal.comment,
                parser_confidence=signal.parser_confidence,
                validation_status=signal.validation_status.value,
                rejection_reason=signal.rejection_reason,
                execution_status=signal.execution_status.value,
                created_at=signal.created_at,
                updated_at=signal.updated_at,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def get_signal_by_message(
        self, channel_id: int, message_id: int
    ) -> TradeSignalRecord | None:
        with self._session_factory() as session:
            statement = (
                select(TradeSignalRecord)
                .where(
                    TradeSignalRecord.telegram_channel_id == channel_id,
                    TradeSignalRecord.telegram_message_id == message_id,
                )
                .order_by(TradeSignalRecord.id.desc())
            )
            return session.scalars(statement).first()

    def latest_executed_for_message(
        self, channel_id: int, message_id: int
    ) -> TradeSignalRecord | None:
        with self._session_factory() as session:
            statement = select(TradeSignalRecord).where(
                TradeSignalRecord.telegram_channel_id == channel_id,
                TradeSignalRecord.telegram_message_id == message_id,
                TradeSignalRecord.execution_status == "EXECUTED",
            )
            return session.scalars(statement).first()

    def find_semantic_duplicates(
        self,
        symbol: str,
        direction: str,
        entry_price: float | None,
        stop_loss: float | None,
        take_profits: list[float],
        window_hours: int,
        exclude_signal_id: str | None = None,
    ) -> list[TradeSignalRecord]:
        cutoff = utc_now() - timedelta(hours=window_hours)
        with self._session_factory() as session:
            statement = select(TradeSignalRecord).where(
                TradeSignalRecord.normalized_symbol == symbol,
                TradeSignalRecord.direction == direction,
                TradeSignalRecord.created_at >= cutoff,
            )
            rows = list(session.scalars(statement))
        matches: list[TradeSignalRecord] = []
        for row in rows:
            if exclude_signal_id and row.signal_id == exclude_signal_id:
                continue
            if row.validation_status in {"REJECTED", "INVALID"}:
                continue
            if row.entry_price != entry_price:
                continue
            if row.stop_loss != stop_loss:
                continue
            stored_tps = json.loads(row.take_profits_json or "[]")
            if stored_tps != take_profits:
                continue
            matches.append(row)
        return matches

    def list_recent_signals(self, limit: int = 10) -> list[TradeSignalRecord]:
        with self._session_factory() as session:
            statement = select(TradeSignalRecord).order_by(
                TradeSignalRecord.id.desc()
            ).limit(limit)
            return list(session.scalars(statement))

    def list_recent_errors(self, limit: int = 10) -> list[ApplicationEvent]:
        with self._session_factory() as session:
            statement = (
                select(ApplicationEvent)
                .where(ApplicationEvent.level.in_(("ERROR", "CRITICAL")))
                .order_by(ApplicationEvent.id.desc())
                .limit(limit)
            )
            return list(session.scalars(statement))

    def add_event(
        self,
        message: str,
        *,
        level: str = "INFO",
        category: str = "app",
        details: dict[str, object] | None = None,
    ) -> ApplicationEvent:
        with self._session_factory() as session:
            event = ApplicationEvent(
                created_at=utc_now(),
                level=level,
                category=category,
                message=message,
                details_json=json.dumps(details) if details else None,
            )
            session.add(event)
            session.commit()
            session.refresh(event)
            return event

    def save_attempt(
        self,
        signal: TradeSignal,
        *,
        request: dict[str, object] | None = None,
        response: dict[str, object] | None = None,
        retcode: int | None = None,
        status: str,
        error_text: str | None = None,
    ) -> TradeAttempt:
        with self._session_factory() as session:
            record = TradeAttempt(
                signal_id=signal.signal_id,
                requested_symbol=signal.broker_symbol
                or signal.normalized_symbol
                or signal.symbol,
                requested_direction=signal.direction.value if signal.direction else None,
                requested_order_type=signal.order_type.value if signal.order_type else None,
                requested_volume=signal.volume,
                requested_price=signal.entry_price,
                requested_stop_loss=signal.stop_loss,
                requested_take_profit=signal.take_profits[0] if signal.take_profits else None,
                mt5_request_json=json.dumps(request) if request else None,
                mt5_response_json=json.dumps(response) if response else None,
                broker_retcode=retcode,
                status=status,
                error_text=error_text,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def save_executed(
        self,
        signal: TradeSignal,
        *,
        ticket: int | None,
        order_id: int | None,
        position_id: int | None,
        requested_price: float | None,
        actual_price: float | None,
        requested_volume: float | None,
        executed_volume: float | None,
        spread: float | None,
        retcode: int | None,
        raw: dict[str, object] | None,
    ) -> ExecutedTrade:
        with self._session_factory() as session:
            record = ExecutedTrade(
                signal_id=signal.signal_id,
                ticket=ticket,
                order_id=order_id,
                position_id=position_id,
                requested_price=requested_price,
                actual_price=actual_price,
                requested_volume=requested_volume,
                executed_volume=executed_volume,
                spread=spread,
                broker_retcode=retcode,
                raw_broker_response=json.dumps(raw) if raw else None,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def count_open_attempts(self) -> int:
        with self._session_factory() as session:
            statement = select(TradeAttempt).where(TradeAttempt.status == "OPEN")
            return len(list(session.scalars(statement)))

    def list_executed(self, limit: int = 10) -> list[ExecutedTrade]:
        with self._session_factory() as session:
            statement = select(ExecutedTrade).order_by(ExecutedTrade.id.desc()).limit(limit)
            return list(session.scalars(statement))
