from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field

from app.utils.time import utc_now


class Direction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    BUY_LIMIT = "BUY_LIMIT"
    SELL_LIMIT = "SELL_LIMIT"
    BUY_STOP = "BUY_STOP"
    SELL_STOP = "SELL_STOP"


class ValidationStatus(str, Enum):
    PENDING = "PENDING"
    PARSED = "PARSED"
    INVALID = "INVALID"
    REJECTED = "REJECTED"
    SEMANTIC_DUPLICATE = "SEMANTIC_DUPLICATE"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class ExecutionStatus(str, Enum):
    NONE = "NONE"
    OBSERVED = "OBSERVED"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTING = "EXECUTING"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    DRY_RUN = "DRY_RUN"


class MessageStatus(str, Enum):
    RECEIVED = "RECEIVED"
    IGNORED = "IGNORED"
    PARSED = "PARSED"
    INVALID = "INVALID"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    REJECTED = "REJECTED"
    APPROVED = "APPROVED"
    EXECUTING = "EXECUTING"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    DELETED = "DELETED"
    EDITED_AFTER_EXECUTE = "EDITED_AFTER_EXECUTE"
    SEMANTIC_DUPLICATE = "SEMANTIC_DUPLICATE"


class TradeSignal(BaseModel):
    signal_id: str = Field(default_factory=lambda: uuid4().hex)
    telegram_channel_id: int | None = None
    telegram_message_id: int | None = None
    telegram_message_date: datetime | None = None
    received_at: datetime = Field(default_factory=utc_now)
    raw_message: str = ""
    symbol: str | None = None
    normalized_symbol: str | None = None
    broker_symbol: str | None = None
    direction: Direction | None = None
    order_type: OrderType | None = None
    entry_price: float | None = None
    entry_low: float | None = None
    entry_high: float | None = None
    stop_loss: float | None = None
    take_profits: list[float] = Field(default_factory=list)
    volume: float | None = None
    risk_percent: float | None = None
    comment: str | None = None
    parser_confidence: float = 0.0
    validation_status: ValidationStatus = ValidationStatus.PENDING
    rejection_reason: str | None = None
    execution_status: ExecutionStatus = ExecutionStatus.NONE
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    is_forwarded: bool = False
    is_edited: bool = False
    source_authorized: bool = True

    def has_entry_range(self) -> bool:
        return self.entry_low is not None and self.entry_high is not None

    def selected_take_profit(self, strategy: str, selected_index: int = 1) -> float | None:
        if not self.take_profits:
            return None
        if strategy == "FIRST_TP":
            return self.take_profits[0]
        if strategy == "SELECTED_TP":
            index = selected_index - 1
            if 0 <= index < len(self.take_profits):
                return self.take_profits[index]
            return None
        return self.take_profits[-1]


class ValidationResult(BaseModel):
    ok: bool
    status: ValidationStatus
    reasons: list[str] = Field(default_factory=list)
    requires_review: bool = False

    @property
    def reason_text(self) -> str | None:
        if not self.reasons:
            return None
        return "; ".join(self.reasons)
