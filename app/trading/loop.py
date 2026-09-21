from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import uuid4

from app.config import ExecutionMode
from app.trading.models import ExecutionStatus, ValidationStatus
from app.utils.time import utc_now

StatusKind = Literal["idle", "ok", "warn", "bad"]


@dataclass
class LoopStep:
    name: str
    result: str
    detail: str
    kind: StatusKind = "idle"


@dataclass
class SignalLoopRecord:
    headline: str
    outcome: str
    kind: StatusKind
    order_sent: bool
    steps: list[LoopStep] = field(default_factory=list)
    snippet: str = ""
    record_id: str = field(default_factory=lambda: uuid4().hex)
    at: datetime = field(default_factory=utc_now)

    def fingerprint(self) -> str:
        return f"{self.record_id}:{self.outcome}"


def snippet_of(raw_text: str, limit: int = 90) -> str:
    compact = " ".join(raw_text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"


def describe_validation(status: ValidationStatus) -> str:
    if status is ValidationStatus.PENDING:
        return "Still checking"
    if status is ValidationStatus.PARSED:
        return "Valid signal"
    if status is ValidationStatus.INVALID:
        return "Could not read as a complete trade"
    if status is ValidationStatus.REJECTED:
        return "Blocked by trading rules"
    if status is ValidationStatus.SEMANTIC_DUPLICATE:
        return "Same trade already seen"
    if status is ValidationStatus.NEEDS_REVIEW:
        return "Needs a human look"
    never: ValidationStatus = status
    raise ValueError(f"Unhandled validation status: {never}")


def describe_action(
    execution: ExecutionStatus,
    *,
    mode: ExecutionMode,
    dry_run: bool,
) -> tuple[str, bool]:
    if execution is ExecutionStatus.NONE:
        text = "No MetaTrader order was sent."
        sent = False
    elif execution is ExecutionStatus.OBSERVED:
        text = (
            f"Stored only. Mode is {mode_label(mode)}. No MetaTrader order was sent."
        )
        sent = False
    elif execution is ExecutionStatus.WAITING_APPROVAL:
        text = "Held for review. No MetaTrader order was sent."
        sent = False
    elif execution is ExecutionStatus.APPROVED:
        text = "Approved in the log. No MetaTrader order was sent."
        sent = False
    elif execution is ExecutionStatus.REJECTED:
        text = "Not sent to MetaTrader."
        sent = False
    elif execution is ExecutionStatus.EXECUTING:
        text = "Sending to MetaTrader."
        sent = False
    elif execution is ExecutionStatus.EXECUTED:
        text = "MetaTrader order was sent."
        sent = True
    elif execution is ExecutionStatus.FAILED:
        text = "MetaTrader order failed. Nothing stays open from this app."
        sent = False
    elif execution is ExecutionStatus.DRY_RUN:
        text = "Dry run. No MetaTrader order was sent."
        sent = False
    else:
        never: ExecutionStatus = execution
        raise ValueError(f"Unhandled execution status: {never}")
    if dry_run:
        sent = False
        if execution is ExecutionStatus.EXECUTED:
            text = "Dry run blocked the send. No MetaTrader order was sent."
    return text, sent


def mode_label(mode: ExecutionMode) -> str:
    if mode is ExecutionMode.OBSERVE:
        return "Watch only"
    if mode is ExecutionMode.APPROVAL:
        return "Wait for approval"
    if mode is ExecutionMode.AUTO_DEMO:
        return "Auto on demo"
    never: ExecutionMode = mode
    raise ValueError(f"Unhandled execution mode: {never}")


def visual_verdict(record: SignalLoopRecord) -> tuple[str, str, StatusKind]:
    if record.order_sent:
        return "Trade sent to MetaTrader", record.outcome, "ok"
    text = f"{record.headline} {record.outcome}".lower()
    if record.kind == "bad":
        return "Did not trade", record.outcome, "bad"
    if "already" in text or "duplicate" in text:
        return "Did not trade — already seen", record.outcome, "warn"
    if "keep orders off" in text or "dry run" in text:
        return "Did not trade — Keep orders off", record.outcome, "warn"
    if "watch only" in text or "stored only" in text:
        return "Did not trade — watching only", record.outcome, "warn"
    if record.kind == "idle":
        return "Ignored — not a trade", record.outcome, "idle"
    return "Did not trade", record.outcome, "warn"


EMPTY_STEPS = [
    LoopStep("Telegram", "Waiting", "A post arrives from your allowed channel.", "idle"),
    LoopStep("Parser", "Waiting", "The app reads buy/sell, symbol, SL and TP.", "idle"),
    LoopStep("Check", "Waiting", "It checks if the trade is new, valid, or a copy.", "idle"),
    LoopStep(
        "Action",
        "Waiting",
        "Watch only never sends. Auto on demo sends after you turn Keep orders off.",
        "idle",
    ),
]


STEP_TITLES = {
    "Telegram": "1. Heard",
    "Parser": "2. Read",
    "Check": "3. Decide",
    "Action": "4. Action",
}


def step_title(name: str) -> str:
    return STEP_TITLES.get(name, name)


def format_loop_feed(records: list[SignalLoopRecord]) -> str:
    if not records:
        return (
            "Waiting for the next channel post.\n"
            "When a message arrives you will see: Heard → Read → Decide → Action.\n"
            "Watch only never sends. Auto on demo sends after you turn Keep orders off."
        )
    blocks: list[str] = []
    for record in records:
        stamp = record.at.strftime("%H:%M:%S")
        title, _, _ = visual_verdict(record)
        lines = [
            f"{stamp}  {record.headline}  ·  {title}",
        ]
        if record.snippet:
            lines.append(f"    Post: {record.snippet}")
        for index, step in enumerate(record.steps, start=1):
            extra = f" — {step.detail}" if step.detail else ""
            lines.append(f"    {index}. {step_title(step.name)}: {step.result}{extra}")
        lines.append(f"    Result: {record.outcome}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
