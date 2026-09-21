from __future__ import annotations

from typing import Any, Literal

import customtkinter as ctk

StatusKind = Literal["idle", "ok", "warn", "bad"]

BG = "#12121C"
SURFACE = "#1A1A2E"
CARD = "#22223B"
CARD_ALT = "#1C1C30"
BORDER = "#2E3150"
TEXT = "#F5F5F5"
MUTED = "#94A3B8"
TEAL = "#21918C"
TEAL_HOVER = "#1A7A76"
YELLOW = "#FDE725"
YELLOW_HOVER = "#E6D21F"
YELLOW_TEXT = "#0F172A"
RED = "#C45C5C"
RED_HOVER = "#A84C4C"
GREEN = "#34D399"
AMBER = "#FBBF24"
LISTENER_LABELS = {
    "USER": "My Telegram account",
    "BOT": "A channel bot",
}
LISTENER_VALUES = {label: value for value, label in LISTENER_LABELS.items()}

EXECUTION_LABELS = {
    "OBSERVE": "Watch only",
    "APPROVAL": "Wait for approval",
    "AUTO_DEMO": "Auto on demo",
}
EXECUTION_VALUES = {label: value for value, label in EXECUTION_LABELS.items()}


def font(size: int, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family="Segoe UI", size=size, weight=weight)


def apply_system_font(widget: Any, size: int | None = None, weight: str | None = None) -> None:
    font_obj = getattr(widget, "_font", None)
    resolved_size = 13
    resolved_weight = "normal"
    if isinstance(font_obj, ctk.CTkFont):
        resolved_size = abs(int(font_obj.cget("size")))
        resolved_weight = str(font_obj.cget("weight") or "normal")
    if size is not None:
        resolved_size = size
    if weight is not None:
        resolved_weight = weight
    if resolved_weight not in {"normal", "bold"}:
        resolved_weight = "bold" if "bold" in resolved_weight else "normal"
    for attr in ("_label", "_text_label"):
        inner = getattr(widget, attr, None)
        if inner is not None:
            inner.configure(font=("Segoe UI", resolved_size, resolved_weight))


def retune_fonts(widget: Any) -> None:
    apply_system_font(widget)
    for child in widget.winfo_children():
        retune_fonts(child)


def status_color(kind: StatusKind) -> str:
    if kind == "ok":
        return GREEN
    if kind == "warn":
        return AMBER
    if kind == "bad":
        return "#F87171"
    if kind == "idle":
        return MUTED
    never: StatusKind = kind
    raise ValueError(f"Unhandled status kind: {never}")
