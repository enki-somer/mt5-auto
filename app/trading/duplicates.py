from __future__ import annotations

from app.config import TradingRules
from app.database.models import TelegramMessage, TradeSignalRecord
from app.database.repository import Repository
from app.trading.models import TradeSignal


def existing_message(
    repository: Repository, channel_id: int, message_id: int
) -> TelegramMessage | None:
    return repository.get_message(channel_id, message_id)


def message_already_processed(
    repository: Repository, channel_id: int, message_id: int
) -> bool:
    return existing_message(repository, channel_id, message_id) is not None


def message_already_executed(
    repository: Repository, channel_id: int, message_id: int
) -> bool:
    return repository.latest_executed_for_message(channel_id, message_id) is not None


def find_semantic_duplicates(
    repository: Repository,
    signal: TradeSignal,
    rules: TradingRules,
) -> list[TradeSignalRecord]:
    if not signal.normalized_symbol or not signal.direction:
        return []
    return repository.find_semantic_duplicates(
        symbol=signal.normalized_symbol,
        direction=signal.direction.value,
        entry_price=signal.entry_price,
        stop_loss=signal.stop_loss,
        take_profits=signal.take_profits,
        window_hours=rules.duplicate_window_hours,
        exclude_signal_id=signal.signal_id,
    )
