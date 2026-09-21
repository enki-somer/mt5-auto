from __future__ import annotations

import os
import queue
from pathlib import Path
from queue import Queue
from tkinter import filedialog, messagebox
from typing import Any

import customtkinter as ctk
from customtkinter.windows.widgets.theme import ThemeManager

from app.config import PROJECT_ROOT
from app.env_store import ENV_GROUPS, apply_to_process, read_env, write_env
from app.gui.theme import (
    AMBER,
    BG,
    BORDER,
    CARD,
    EXECUTION_LABELS,
    EXECUTION_VALUES,
    GREEN,
    LISTENER_LABELS,
    LISTENER_VALUES,
    MUTED,
    RED,
    RED_HOVER,
    SURFACE,
    TEAL,
    TEAL_HOVER,
    TEXT,
    YELLOW,
    YELLOW_HOVER,
    YELLOW_TEXT,
    StatusKind,
    font,
    retune_fonts,
    status_color,
)
from app.paths import ensure_runtime_files, is_frozen
from app.runtime import AutomationRuntime
from app.trading.loop import SignalLoopRecord, step_title, visual_verdict
from app.updater import UpdateWatcher, relaunch, repo_root
from app.utils.health import RuntimeState
from app.utils.logging import setup_logging

ctk.deactivate_automatic_dpi_awareness()
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")
ThemeManager.theme["CTkFont"]["family"] = "Segoe UI"

LEVEL_COLORS = {
    "DEBUG": MUTED,
    "INFO": TEXT,
    "WARNING": AMBER,
    "ERROR": "#F87171",
    "CRITICAL": "#FB7185",
}

NAV_PAGES = ("home", "setup", "activity")
NAV_LABELS = {"home": "Home", "setup": "Setup", "activity": "Activity"}


def _field_map() -> dict[str, dict[str, object]]:
    mapping: dict[str, dict[str, object]] = {}
    for _group, fields in ENV_GROUPS:
        for field in fields:
            mapping[str(field["key"])] = field
    return mapping


class PromptDialog(ctk.CTkToplevel):
    def __init__(self, master: ctk.CTk, title: str, message: str, secret: bool) -> None:
        super().__init__(master)
        self.title(title)
        self.geometry("440x220")
        self.resizable(False, False)
        self.result = ""
        self.configure(fg_color=BG)
        self.transient(master)
        self.grab_set()
        card = ctk.CTkFrame(self, fg_color=CARD, corner_radius=16, border_color=BORDER, border_width=1)
        card.pack(fill="both", expand=True, padx=16, pady=16)
        ctk.CTkLabel(card, text=title, font=font(18, "bold"), text_color=TEXT).pack(
            anchor="w", padx=20, pady=(18, 4)
        )
        ctk.CTkLabel(card, text=message, wraplength=380, text_color=MUTED, font=font(13)).pack(
            anchor="w", padx=20, pady=(0, 10)
        )
        self._entry = ctk.CTkEntry(
            card,
            height=40,
            border_color=BORDER,
            fg_color=SURFACE,
            show="*" if secret else "",
        )
        self._entry.pack(fill="x", padx=20)
        self._entry.focus_set()
        self._entry.bind("<Return>", lambda _event: self._ok())
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=16)
        ctk.CTkButton(
            row,
            text="Continue",
            height=36,
            fg_color=TEAL,
            hover_color=TEAL_HOVER,
            command=self._ok,
        ).pack(side="right")
        ctk.CTkButton(
            row,
            text="Cancel",
            height=36,
            fg_color=SURFACE,
            hover_color=BORDER,
            text_color=TEXT,
            command=self._cancel,
        ).pack(side="right", padx=(0, 8))
        retune_fonts(self)

    def _ok(self) -> None:
        self.result = self._entry.get().strip()
        self.destroy()

    def _cancel(self) -> None:
        self.result = ""
        self.destroy()


class AppWindow(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Telegram → MT5")
        self.geometry("1100x780")
        self.minsize(900, 640)
        self.configure(fg_color=BG)
        ensure_runtime_files()
        self.log_queue: Queue[dict[str, Any]] = Queue()
        setup_logging(self.log_queue)
        self.runtime = AutomationRuntime(
            log_queue=self.log_queue,
            code_callback=self._ask_code,
            password_callback=self._ask_password,
        )
        self._fields: dict[str, Any] = {}
        self._field_rows: dict[str, ctk.CTkFrame] = {}
        self._field_defs = _field_map()
        self._pages: dict[str, ctk.CTkFrame] = {}
        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        self._page = "home"
        self._dirty = False
        self._advanced_open = False
        self._loop_seen = ""
        self._loop_events: list[SignalLoopRecord] = []
        self._wrap_labels: list[ctk.CTkLabel] = []
        self._resize_job: str | None = None
        self._build()
        retune_fonts(self)
        self._load_settings_into_form()
        self._show_page("home")
        self._closing = False
        self._updater = UpdateWatcher(on_restart=self._schedule_update_restart)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(200, self._pump)
        self._updater.start()

    def _build(self) -> None:
        self._build_header()
        self._build_nav()
        stage = ctk.CTkFrame(self, fg_color=BG)
        stage.pack(fill="both", expand=True)
        for name in NAV_PAGES:
            page = ctk.CTkFrame(stage, fg_color=BG)
            self._pages[name] = page
        self._build_home(self._pages["home"])
        self._build_setup(self._pages["setup"])
        self._build_activity(self._pages["activity"])

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=0, height=72)
        header.pack(fill="x")
        header.pack_propagate(False)
        left = ctk.CTkFrame(header, fg_color="transparent")
        left.pack(side="left", padx=24, pady=14)
        ctk.CTkLabel(left, text="Telegram → MT5", font=font(20, "bold"), text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(
            left,
            text="Read channel signals. Send demo orders only when Auto on demo is on.",
            font=font(12),
            text_color=MUTED,
        ).pack(anchor="w")
        pill = ctk.CTkFrame(header, fg_color=CARD, corner_radius=14)
        pill.pack(side="right", padx=24, pady=20)
        self._status_pill = ctk.CTkLabel(
            pill,
            text="Stopped",
            font=font(13, "bold"),
            text_color=MUTED,
            width=90,
        )
        self._status_pill.pack(padx=12, pady=6)

    def _build_nav(self) -> None:
        nav = ctk.CTkFrame(self, fg_color=BG)
        nav.pack(fill="x", padx=24, pady=(16, 8))
        for name in NAV_PAGES:
            button = ctk.CTkButton(
                nav,
                text=NAV_LABELS[name],
                width=110,
                height=36,
                corner_radius=10,
                font=font(13, "bold"),
                command=lambda page=name: self._show_page(page),
            )
            button.pack(side="left", padx=(0, 8))
            self._nav_buttons[name] = button

    def _show_page(self, name: str) -> None:
        if name not in NAV_PAGES:
            never = name
            raise ValueError(f"Unhandled page: {never}")
        self._page = name
        for key, page in self._pages.items():
            page.pack_forget()
            selected = key == name
            self._nav_buttons[key].configure(
                fg_color=TEAL if selected else CARD,
                hover_color=TEAL_HOVER if selected else BORDER,
                text_color=TEXT,
            )
        self._pages[name].pack(fill="both", expand=True, padx=24, pady=(0, 20))

    def _card(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        return ctk.CTkFrame(
            parent,
            fg_color=CARD,
            corner_radius=16,
            border_color=BORDER,
            border_width=1,
        )

    def _build_home(self, parent: ctk.CTkFrame) -> None:
        scroll = ctk.CTkScrollableFrame(parent, fg_color=BG, scrollbar_button_color=BORDER)
        scroll.pack(fill="both", expand=True)
        self._home_scroll = scroll
        scroll.bind("<Configure>", self._on_home_configure)

        hero = self._card(scroll)
        hero.pack(fill="x", pady=(0, 12))
        self._hero = hero
        self._hero_title = ctk.CTkLabel(hero, text="Ready when you are", font=font(24, "bold"), text_color=TEXT)
        self._hero_title.pack(anchor="w", padx=22, pady=(18, 4))
        self._hero_copy = ctk.CTkLabel(
            hero,
            text="Open Setup if this is the first time, then press Start.",
            font=font(13),
            text_color=MUTED,
        )
        self._hero_copy.pack(anchor="w", padx=22)
        actions = ctk.CTkFrame(hero, fg_color="transparent")
        actions.pack(anchor="w", padx=22, pady=16)
        self._start_btn = ctk.CTkButton(
            actions,
            text="Start",
            width=140,
            height=40,
            font=font(15, "bold"),
            fg_color=YELLOW,
            hover_color=YELLOW_HOVER,
            text_color=YELLOW_TEXT,
            command=self._start,
        )
        self._start_btn.pack(side="left")
        self._stop_btn = ctk.CTkButton(
            actions,
            text="Stop",
            width=110,
            height=40,
            font=font(14, "bold"),
            fg_color=RED,
            hover_color=RED_HOVER,
            command=self._stop,
        )
        self._stop_btn.pack(side="left", padx=8)
        self._pause_btn = ctk.CTkButton(
            actions,
            text="Pause",
            width=110,
            height=40,
            font=font(14, "bold"),
            fg_color=SURFACE,
            hover_color=BORDER,
            text_color=TEXT,
            command=self._toggle_pause,
        )
        self._pause_btn.pack(side="left")
        self._setup_link = ctk.CTkButton(
            actions,
            text="Open Setup",
            width=120,
            height=40,
            font=font(14),
            fg_color="transparent",
            hover_color=SURFACE,
            text_color=TEAL,
            command=lambda: self._show_page("setup"),
        )
        self._setup_link.pack(side="left", padx=(12, 0))

        self._alert = ctk.CTkLabel(
            scroll, text="", font=font(13), text_color="#F87171", anchor="w", justify="left"
        )

        status = ctk.CTkFrame(scroll, fg_color="transparent")
        status.pack(fill="x", pady=(0, 12))
        self._status_row = status
        status.grid_columnconfigure((0, 1), weight=1)
        self._tg_frame, self._tg_card = self._status_card(status, "Telegram", 0, 0)
        self._mt5_frame, self._mt5_card = self._status_card(status, "MetaTrader", 0, 1)

        loop = self._card(scroll)
        loop.pack(fill="x", pady=(0, 20))
        self._loop_panel = loop
        head = ctk.CTkFrame(loop, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(16, 8))
        ctk.CTkLabel(head, text="Signal loop", font=font(16, "bold"), text_color=TEXT).pack(anchor="w")
        self._order_banner = ctk.CTkLabel(
            head,
            text="Watch only — no MetaTrader order",
            font=font(13),
            text_color=AMBER,
            wraplength=860,
            justify="left",
            anchor="w",
        )
        self._order_banner.pack(anchor="w", pady=(4, 0))
        self._wrap_labels.append(self._order_banner)
        self._loop_list = ctk.CTkFrame(loop, fg_color="transparent")
        self._loop_list.pack(fill="x", padx=16, pady=(4, 16))
        self._paint_history([])

    def _status_card(
        self, parent: ctk.CTkFrame, title: str, row: int, column: int
    ) -> tuple[ctk.CTkFrame, dict[str, ctk.CTkLabel]]:
        card = self._card(parent)
        pad = (0, 8) if column == 0 else (8, 0)
        card.grid(row=row, column=column, sticky="nsew", padx=pad)
        ctk.CTkLabel(card, text=title, font=font(12), text_color=MUTED).pack(anchor="w", padx=18, pady=(14, 0))
        value = ctk.CTkLabel(card, text="—", font=font(18, "bold"), text_color=TEXT, anchor="w")
        value.pack(anchor="w", padx=18, pady=(2, 0))
        detail = ctk.CTkLabel(
            card, text="", font=font(13), text_color=MUTED, wraplength=380, justify="left", anchor="w"
        )
        detail.pack(anchor="w", fill="x", padx=18, pady=(4, 14))
        self._wrap_labels.append(detail)
        return card, {"value": value, "detail": detail}

    def _kind_fill(self, kind: StatusKind) -> str:
        if kind == "ok":
            return "#17352C"
        if kind == "warn":
            return "#3A2F14"
        if kind == "bad":
            return "#3A1A1A"
        if kind == "idle":
            return SURFACE
        never: StatusKind = kind
        raise ValueError(f"Unhandled status kind: {never}")

    def _loop_wrap(self) -> int:
        try:
            width = int(self._home_scroll.winfo_width())
        except (TypeError, ValueError):
            width = 900
        return max(420, width - 80)

    def _remember_wrap(self, label: ctk.CTkLabel) -> ctk.CTkLabel:
        self._wrap_labels.append(label)
        return label

    def _on_home_configure(self, _event: object) -> None:
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(80, self._apply_wrap)

    def _apply_wrap(self) -> None:
        wrap = self._loop_wrap()
        half = max(280, (wrap // 2) - 20)
        for label in list(self._wrap_labels):
            if not label.winfo_exists():
                self._wrap_labels.remove(label)
                continue
            width = half if label in {self._tg_card["detail"], self._mt5_card["detail"]} else wrap
            label.configure(wraplength=width)

    def _add_text(
        self,
        parent: ctk.CTkFrame,
        text: str,
        *,
        size: int = 13,
        weight: str = "normal",
        color: str = TEXT,
        pad: tuple[int, int] = (0, 0),
    ) -> ctk.CTkLabel:
        label = ctk.CTkLabel(
            parent,
            text=text,
            font=font(size, weight),
            text_color=color,
            wraplength=self._loop_wrap(),
            justify="left",
            anchor="w",
        )
        label.pack(fill="x", padx=16, pady=pad)
        self._remember_wrap(label)
        return label

    def _paint_history(self, records: list[SignalLoopRecord]) -> None:
        for child in self._loop_list.winfo_children():
            child.destroy()
        self._wrap_labels = [
            self._order_banner,
            self._tg_card["detail"],
            self._mt5_card["detail"],
        ]
        if not records:
            empty = ctk.CTkFrame(self._loop_list, fg_color=SURFACE, corner_radius=12)
            empty.pack(fill="x")
            self._add_text(
                empty,
                "Waiting for a channel post. Each signal will show Heard, Read, Decide, and Action in a card you can scroll.",
                color=MUTED,
                pad=(14, 14),
            )
            return
        for index, record in enumerate(records):
            title, why, kind = visual_verdict(record)
            card = ctk.CTkFrame(
                self._loop_list,
                fg_color=self._kind_fill(kind),
                corner_radius=12,
                border_color=status_color(kind),
                border_width=1,
            )
            card.pack(fill="x", pady=(0, 10))
            top = ctk.CTkFrame(card, fg_color="transparent")
            top.pack(fill="x", padx=16, pady=(12, 0))
            stamp = record.at.strftime("%H:%M:%S")
            badge = "Latest" if index == 0 else stamp
            ctk.CTkLabel(top, text=badge, font=font(12, "bold"), text_color=MUTED).pack(side="left")
            if index == 0:
                ctk.CTkLabel(top, text=stamp, font=font(12), text_color=MUTED).pack(side="left", padx=(10, 0))
            ctk.CTkLabel(
                top, text=title, font=font(13, "bold"), text_color=status_color(kind)
            ).pack(side="right")
            self._add_text(card, record.headline, size=18, weight="bold", pad=(6, 0))
            self._add_text(card, why, color=status_color(kind), pad=(2, 0))
            if record.snippet:
                self._add_text(card, f"Post: {record.snippet}", color=MUTED, pad=(6, 0))
            for step_index, step in enumerate(record.steps, start=1):
                self._add_text(
                    card,
                    f"{step_index}. {step_title(step.name)} — {step.result}",
                    weight="bold",
                    color=status_color(step.kind),
                    pad=(8 if step_index == 1 else 2, 0),
                )
                if step.detail:
                    self._add_text(card, step.detail, color=MUTED, pad=(0, 0))
            spacer = ctk.CTkFrame(card, fg_color="transparent", height=12)
            spacer.pack(fill="x")
            retune_fonts(card)

    def _build_setup(self, parent: ctk.CTkFrame) -> None:
        footer = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=14)
        footer.pack(side="bottom", fill="x", pady=(8, 0))
        self._save_note = ctk.CTkLabel(footer, text="Changes are kept after you save.", text_color=MUTED, font=font(12))
        self._save_note.pack(side="left", padx=16, pady=12)
        ctk.CTkButton(
            footer,
            text="Save",
            width=120,
            height=36,
            font=font(13, "bold"),
            fg_color=YELLOW,
            hover_color=YELLOW_HOVER,
            text_color=YELLOW_TEXT,
            command=self._save_settings,
        ).pack(side="right", padx=16, pady=10)
        ctk.CTkButton(
            footer,
            text="Save and start",
            width=140,
            height=36,
            font=font(13, "bold"),
            fg_color=TEAL,
            hover_color=TEAL_HOVER,
            command=self._save_and_restart,
        ).pack(side="right")

        scroll = ctk.CTkScrollableFrame(parent, fg_color=BG, scrollbar_button_color=BORDER)
        scroll.pack(fill="both", expand=True)

        telegram = self._section(scroll, "Telegram", "Sign in once. The login stays saved on this computer.")
        self._add_listener_mode(telegram)
        self._telegram_fields = ctk.CTkFrame(telegram, fg_color="transparent")
        self._telegram_fields.pack(fill="x")
        for key in (
            "TELEGRAM_API_ID",
            "TELEGRAM_API_HASH",
            "TELEGRAM_PHONE",
            "TELEGRAM_BOT_TOKEN",
            "ALLOWED_CHANNEL_IDS",
        ):
            self._add_field(self._telegram_fields, key)
        ctk.CTkButton(
            telegram,
            text="Forget Telegram login",
            width=180,
            height=32,
            fg_color="transparent",
            hover_color=SURFACE,
            text_color=MUTED,
            anchor="w",
            command=self._clear_session,
        ).pack(anchor="w", padx=20, pady=(4, 16))

        mt5 = self._section(scroll, "MetaTrader 5", "Use a demo account. Open MetaTrader on this PC first.")
        for key in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_PATH"):
            self._add_field(mt5, key)

        handling = self._section(scroll, "Signals", "This version records signals. It does not place orders.")
        self._add_execution_mode(handling)
        self._add_safe_mode(handling)

        self._advanced_btn = ctk.CTkButton(
            scroll,
            text="More options",
            width=140,
            height=32,
            fg_color=CARD,
            hover_color=BORDER,
            text_color=TEXT,
            command=self._toggle_advanced,
        )
        self._advanced_btn.pack(anchor="w", pady=(8, 8))
        self._advanced = ctk.CTkFrame(scroll, fg_color=CARD, corner_radius=16, border_color=BORDER, border_width=1)
        self._advanced_spacer = ctk.CTkFrame(scroll, fg_color=BG, height=12)
        self._advanced_spacer.pack(fill="x")
        for key in (
            "CONTROL_BOT_TOKEN",
            "CONTROL_CHAT_ID",
            "AUTHORIZED_CONTROL_USER_IDS",
            "LOCAL_TIMEZONE",
            "DATABASE_URL",
            "TELEGRAM_SESSION_PATH",
        ):
            self._add_field(self._advanced, key)
        hidden = ctk.CTkFrame(self, fg_color=BG)
        self._add_hidden_choice(hidden, "APP_MODE", ["DEMO"])

    def _section(self, parent: ctk.CTkFrame, title: str, subtitle: str) -> ctk.CTkFrame:
        card = self._card(parent)
        card.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(card, text=title, font=font(16, "bold"), text_color=TEXT).pack(anchor="w", padx=20, pady=(16, 0))
        ctk.CTkLabel(card, text=subtitle, font=font(12), text_color=MUTED).pack(anchor="w", padx=20, pady=(2, 10))
        return card

    def _add_listener_mode(self, parent: ctk.CTkFrame) -> None:
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.pack(fill="x", padx=20, pady=(0, 10))
        ctk.CTkLabel(wrap, text="How do you read the channel?", font=font(13, "bold"), text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(
            wrap,
            text="Choose your account if you cannot add a bot as admin.",
            font=font(12),
            text_color=MUTED,
        ).pack(anchor="w", pady=(0, 6))
        widget = ctk.CTkSegmentedButton(
            wrap,
            values=list(LISTENER_LABELS.values()),
            command=self._on_listener_mode,
            selected_color=TEAL,
            selected_hover_color=TEAL_HOVER,
            unselected_color=SURFACE,
            unselected_hover_color=BORDER,
            font=font(13),
        )
        widget.set(LISTENER_LABELS["USER"])
        widget.pack(anchor="w")
        self._fields["TELEGRAM_LISTENER_MODE"] = widget

    def _add_execution_mode(self, parent: ctk.CTkFrame) -> None:
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.pack(fill="x", padx=20, pady=(0, 10))
        ctk.CTkLabel(wrap, text="When a signal arrives", font=font(13, "bold"), text_color=TEXT).pack(anchor="w")
        widget = ctk.CTkSegmentedButton(
            wrap,
            values=list(EXECUTION_LABELS.values()),
            command=lambda _value: self._on_execution_mode(),
            selected_color=TEAL,
            selected_hover_color=TEAL_HOVER,
            unselected_color=SURFACE,
            unselected_hover_color=BORDER,
            font=font(13),
        )
        widget.set(EXECUTION_LABELS["OBSERVE"])
        widget.pack(anchor="w", pady=(6, 4))
        self._execution_hint = ctk.CTkLabel(
            wrap,
            text="Watch only records the signal and never sends an order.",
            font=font(12),
            text_color=MUTED,
            wraplength=640,
            justify="left",
            anchor="w",
        )
        self._execution_hint.pack(anchor="w", pady=(0, 12))
        self._fields["EXECUTION_MODE"] = widget

    def _add_safe_mode(self, parent: ctk.CTkFrame) -> None:
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.pack(fill="x", padx=20, pady=(0, 16))
        widget = ctk.CTkSwitch(
            wrap,
            text="Keep orders off",
            font=font(13),
            text_color=TEXT,
            progress_color=TEAL,
            command=self._on_safe_mode,
        )
        widget.select()
        widget.pack(anchor="w")
        self._dry_hint = ctk.CTkLabel(
            wrap,
            text="On = no order is sent, even if Auto on demo is selected.",
            font=font(12),
            text_color=MUTED,
            wraplength=640,
            justify="left",
            anchor="w",
        )
        self._dry_hint.pack(anchor="w", pady=(4, 16))
        self._fields["DRY_RUN"] = widget

    def _add_hidden_choice(self, parent: ctk.CTkFrame, key: str, choices: list[str]) -> None:
        widget = ctk.CTkComboBox(parent, values=choices, width=80)
        widget.set(choices[0])
        self._fields[key] = widget

    def _add_field(self, parent: ctk.CTkFrame, key: str) -> None:
        field = self._field_defs[key]
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.pack(fill="x", padx=20, pady=6)
        ctk.CTkLabel(wrap, text=str(field["label"]), font=font(13, "bold"), text_color=TEXT).pack(anchor="w")
        kind = str(field.get("kind", "text"))
        controls = ctk.CTkFrame(wrap, fg_color="transparent")
        controls.pack(fill="x", pady=(4, 0))
        if kind == "choice":
            widget: Any = ctk.CTkComboBox(
                controls,
                values=[str(item) for item in field.get("choices", [])],
                height=38,
                command=lambda _value: self._mark_dirty(),
            )
            widget.set("")
            widget.pack(fill="x")
        else:
            widget = ctk.CTkEntry(
                controls,
                height=38,
                border_color=BORDER,
                fg_color=SURFACE,
                show="*" if kind == "secret" else "",
                placeholder_text=str(field.get("placeholder") or ""),
            )
            widget.pack(side="left", fill="x", expand=True)
            widget.bind("<KeyRelease>", lambda _event: self._mark_dirty())
            if kind == "secret":
                reveal = ctk.CTkButton(
                    controls,
                    text="Show",
                    width=64,
                    height=38,
                    fg_color=SURFACE,
                    hover_color=BORDER,
                )
                reveal.configure(command=lambda target=widget, button=reveal: self._toggle_secret(target, button))
                reveal.pack(side="left", padx=(8, 0))
            if kind == "path":
                ctk.CTkButton(
                    controls,
                    text="Browse",
                    width=90,
                    height=38,
                    fg_color=TEAL,
                    hover_color=TEAL_HOVER,
                    command=lambda target=widget: self._browse(target),
                ).pack(side="left", padx=(8, 0))
        hint = str(field.get("hint") or field.get("help") or "")
        if hint:
            ctk.CTkLabel(wrap, text=hint, font=font(12), text_color=MUTED).pack(anchor="w", pady=(4, 0))
        self._fields[key] = widget
        self._field_rows[key] = wrap

    def _toggle_secret(self, widget: ctk.CTkEntry, button: ctk.CTkButton) -> None:
        hidden = widget.cget("show") == "*"
        widget.configure(show="" if hidden else "*")
        button.configure(text="Hide" if hidden else "Show")

    def _toggle_advanced(self) -> None:
        self._advanced_open = not self._advanced_open
        if self._advanced_open:
            self._advanced.pack(fill="x", pady=(0, 12), before=self._advanced_spacer)
            self._advanced_btn.configure(text="Hide extra options")
            return
        self._advanced.pack_forget()
        self._advanced_btn.configure(text="More options")

    def _on_listener_mode(self, _value: str = "") -> None:
        self._apply_listener_visibility()
        self._mark_dirty()

    def _on_execution_mode(self, _value: str = "") -> None:
        self._refresh_execution_hint()
        self._mark_dirty()

    def _on_safe_mode(self) -> None:
        self._refresh_execution_hint()
        self._mark_dirty()

    def _refresh_execution_hint(self) -> None:
        mode = EXECUTION_VALUES.get(self._fields["EXECUTION_MODE"].get(), "OBSERVE")
        dry = bool(self._fields["DRY_RUN"].get())
        if mode == "OBSERVE":
            self._execution_hint.configure(
                text="Watch only records the signal and never sends an order."
            )
        elif mode == "APPROVAL":
            self._execution_hint.configure(
                text="Wait for approval holds a valid signal. This screen does not send after approval yet."
            )
        elif mode == "AUTO_DEMO" and dry:
            self._execution_hint.configure(
                text="Auto on demo will send to the MT5 demo account after you turn Keep orders off, then Save and Start."
            )
        elif mode == "AUTO_DEMO":
            self._execution_hint.configure(
                text="Auto on demo sends the next valid signal to the connected MT5 demo account. Save and Start to apply."
            )
        else:
            never = mode
            raise ValueError(f"Unhandled execution mode: {never}")
        if dry:
            self._dry_hint.configure(text="On = no order is sent, even if Auto on demo is selected.")
        else:
            self._dry_hint.configure(
                text="Off = Auto on demo may send a demo order. Watch only and Wait for approval still do not send."
            )

    def _order_banner_state(self) -> tuple[str, str]:
        values = self._form_values()
        mode = values.get("EXECUTION_MODE", "OBSERVE")
        dry = values.get("DRY_RUN", "true") == "true"
        if mode == "AUTO_DEMO" and not dry:
            return "Auto on demo — next valid signal is sent to MetaTrader", GREEN
        if mode == "AUTO_DEMO" and dry:
            return "Auto on demo selected — turn off Keep orders off to send", AMBER
        if mode == "APPROVAL":
            return "Wait for approval — holds the trade, no order yet", AMBER
        if mode == "OBSERVE":
            return "Watch only — no MetaTrader order", AMBER
        never = mode
        raise ValueError(f"Unhandled execution mode: {never}")

    def _apply_listener_visibility(self) -> None:
        mode = LISTENER_VALUES.get(self._fields["TELEGRAM_LISTENER_MODE"].get(), "USER")
        order = (
            "TELEGRAM_API_ID",
            "TELEGRAM_API_HASH",
            "TELEGRAM_PHONE",
            "TELEGRAM_BOT_TOKEN",
            "ALLOWED_CHANNEL_IDS",
        )
        for key in order:
            row = self._field_rows[key]
            row.pack_forget()
            modes = self._field_defs[key].get("modes")
            allowed = {str(item) for item in modes} if modes else set()
            if not allowed or mode in allowed:
                row.pack(fill="x", padx=20, pady=6)

    def _build_activity(self, parent: ctk.CTkFrame) -> None:
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(bar, text="What the app is doing", font=font(16, "bold"), text_color=TEXT).pack(side="left")
        self._log_filter = ctk.CTkSegmentedButton(
            bar,
            values=["All", "Problems"],
            selected_color=TEAL,
            selected_hover_color=TEAL_HOVER,
            unselected_color=CARD,
            unselected_hover_color=BORDER,
            font=font(13),
        )
        self._log_filter.set("All")
        self._log_filter.pack(side="right")
        ctk.CTkButton(
            bar,
            text="Clear",
            width=80,
            height=32,
            fg_color=CARD,
            hover_color=BORDER,
            command=self._clear_logs,
        ).pack(side="right", padx=8)
        box = self._card(parent)
        box.pack(fill="both", expand=True)
        self._log_box = ctk.CTkTextbox(
            box,
            font=ctk.CTkFont(family="Consolas", size=13),
            fg_color=CARD,
            text_color=TEXT,
            wrap="word",
        )
        self._log_box.pack(fill="both", expand=True, padx=8, pady=8)
        for level, color in LEVEL_COLORS.items():
            self._log_box._textbox.tag_config(level, foreground=color)

    def _browse(self, widget: ctk.CTkEntry) -> None:
        path = filedialog.askopenfilename(
            title="Select MetaTrader",
            filetypes=[("MetaTrader", "terminal64.exe"), ("Programs", "*.exe"), ("All files", "*.*")],
        )
        if path:
            widget.delete(0, "end")
            widget.insert(0, path.replace("\\", "/"))
            self._mark_dirty()

    def _mark_dirty(self) -> None:
        self._dirty = True
        self._save_note.configure(text="Unsaved changes", text_color=AMBER)

    def _form_values(self) -> dict[str, str]:
        values: dict[str, str] = {}
        for key, widget in self._fields.items():
            if key == "TELEGRAM_LISTENER_MODE":
                values[key] = LISTENER_VALUES.get(widget.get(), "USER")
                continue
            if key == "EXECUTION_MODE":
                values[key] = EXECUTION_VALUES.get(widget.get(), "OBSERVE")
                continue
            if key == "DRY_RUN":
                values[key] = "true" if widget.get() else "false"
                continue
            if isinstance(widget, ctk.CTkComboBox):
                values[key] = widget.get().strip()
            else:
                values[key] = widget.get().strip()
        values["APP_MODE"] = "DEMO"
        return values

    def _load_settings_into_form(self) -> None:
        values = read_env()
        for key, widget in self._fields.items():
            current = values.get(key, "")
            if key == "TELEGRAM_LISTENER_MODE":
                widget.set(LISTENER_LABELS.get(current, LISTENER_LABELS["USER"]))
                continue
            if key == "EXECUTION_MODE":
                widget.set(EXECUTION_LABELS.get(current, EXECUTION_LABELS["OBSERVE"]))
                continue
            if key == "DRY_RUN":
                if current.lower() in {"", "true", "1", "yes"}:
                    widget.select()
                else:
                    widget.deselect()
                continue
            if isinstance(widget, ctk.CTkComboBox):
                options = [str(item) for item in widget.cget("values")]
                widget.set(current if current in options else (options[0] if options else ""))
                continue
            widget.delete(0, "end")
            widget.insert(0, current)
        self._apply_listener_visibility()
        self._refresh_execution_hint()
        self._dirty = False
        self._save_note.configure(text="Changes are kept after you save.", text_color=MUTED)

    def _save_settings(self) -> None:
        values = self._form_values()
        write_env(values)
        apply_to_process(values)
        self._dirty = False
        self._save_note.configure(text="Saved on this computer.", text_color=GREEN)

    def _save_and_restart(self) -> None:
        self._save_settings()
        if self.runtime.running:
            self.runtime.stop()
        self.runtime.start()
        self._append_log("INFO", "application", "Saved settings and started")
        self._show_page("home")

    def _clear_session(self) -> None:
        if not messagebox.askyesno(
            "Telegram",
            "Forget the saved Telegram login on this computer?\nThe next Start will ask for a code.",
        ):
            return
        relative = self._form_values().get("TELEGRAM_SESSION_PATH") or "data/telegram.session"
        session = (PROJECT_ROOT / relative).resolve()
        for extra in (session, Path(str(session) + "-journal")):
            if extra.exists():
                extra.unlink()
        self._save_note.configure(text="Telegram login forgotten.", text_color=AMBER)

    def _start(self) -> None:
        apply_to_process(self._form_values())
        self.runtime.start()
        self._show_page("home")

    def _stop(self) -> None:
        self.runtime.stop()

    def _toggle_pause(self) -> None:
        if self.runtime.state.paused:
            self.runtime.resume()
            return
        self.runtime.pause()

    def _ask_code(self) -> str:
        return self._ask("Telegram code", "Enter the code Telegram just sent you.", False)

    def _ask_password(self) -> str:
        return self._ask("Telegram password", "Enter your Telegram two-step password.", True)

    def _ask(self, title: str, message: str, secret: bool) -> str:
        box: queue.Queue[str] = queue.Queue()

        def show() -> None:
            dialog = PromptDialog(self, title, message, secret)
            self.wait_window(dialog)
            box.put(dialog.result)

        self.after(0, show)
        try:
            return box.get(timeout=300)
        except queue.Empty:
            return ""

    def _clear_logs(self) -> None:
        self._log_box.delete("1.0", "end")

    def _append_log(self, level: str, name: str, message: str) -> None:
        selected = self._log_filter.get()
        if selected == "Problems" and level not in {"WARNING", "ERROR", "CRITICAL"}:
            return
        display = message
        if "  " in message:
            parts = message.split("  ", 3)
            if len(parts) == 4:
                display = f"{parts[1]}  {parts[3]}"
        self._log_box.insert("end", display + "\n", level if level in LEVEL_COLORS else "INFO")
        self._log_box.see("end")

    def _refresh_loop(self, state: RuntimeState) -> None:
        seen = state.loop_events[0].fingerprint() if state.loop_events else "empty"
        if seen == self._loop_seen:
            return
        self._loop_seen = seen
        self._loop_events = list(state.loop_events)
        self._paint_history(self._loop_events)

    def _set_card(self, card: dict[str, ctk.CTkLabel], value: str, detail: str, kind: StatusKind) -> None:
        card["value"].configure(text=value, text_color=status_color(kind))
        card["detail"].configure(text=detail)

    def _refresh_status(self) -> None:
        state: RuntimeState = self.runtime.state
        running = self.runtime.running
        paused = running and state.paused
        if paused:
            pill = "Paused"
            pill_color = AMBER
            title = "Paused"
            copy = "Signals are on hold. Press Resume to continue."
        elif running:
            pill = "Running"
            pill_color = GREEN
            title = "Listening"
            copy = "The app is watching your allowed channels."
        else:
            pill = "Stopped"
            pill_color = MUTED
            title = "Ready when you are"
            copy = "Open Setup if this is the first time, then press Start."
        values = self._form_values()
        if not running and not (values.get("TELEGRAM_API_ID") or values.get("TELEGRAM_BOT_TOKEN")):
            copy = "Add Telegram details in Setup, then press Start."
        self._status_pill.configure(text=pill, text_color=pill_color)
        self._hero_title.configure(text=title)
        self._hero_copy.configure(text=copy)
        self._start_btn.configure(state="disabled" if running else "normal")
        self._stop_btn.configure(state="normal" if running else "disabled")
        self._pause_btn.configure(
            text="Resume" if paused else "Pause",
            state="normal" if running else "disabled",
        )

        if running and state.telegram_connected:
            channels = ", ".join(state.listening_channels) or "Waiting for allowed channels"
            self._set_card(self._tg_card, "Connected", channels, "ok")
        elif running:
            self._set_card(self._tg_card, "Not connected", "Check Setup, then Start again.", "bad")
        else:
            self._set_card(self._tg_card, "Off", "Starts with the app.", "idle")

        if state.mt5_account_verified:
            account = f"{state.mt5_login or ''} · {state.mt5_server or 'Demo'}".strip(" ·")
            extra = ""
            if state.mt5_balance is not None:
                extra = f" · {state.mt5_balance:.2f} · {state.open_positions} open"
            self._set_card(self._mt5_card, "Connected", account + extra, "ok")
        elif running and state.mt5_installation == "NOT FOUND":
            self._set_card(self._mt5_card, "Not found", "Install MetaTrader 5 Desktop on this PC.", "bad")
        elif running:
            self._set_card(self._mt5_card, "Not connected", "Open MetaTrader and check the account in Setup.", "warn")
        else:
            self._set_card(self._mt5_card, "Off", "Starts with the app.", "idle")

        banner, banner_color = self._order_banner_state()
        self._order_banner.configure(text=banner, text_color=banner_color)
        self._refresh_loop(state)

        if state.last_exception:
            self._alert.configure(text=f"Something needs attention: {state.last_exception}")
            if not self._alert.winfo_ismapped():
                self._alert.pack(fill="x", pady=(0, 12), before=self._status_row)
        else:
            self._alert.configure(text="")
            self._alert.pack_forget()

    def _pump(self) -> None:
        while True:
            try:
                item = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self._append_log(item["level"], item["name"], item["message"])
        self._refresh_status()
        self.after(250, self._pump)

    def _schedule_update_restart(self) -> None:
        self.after(0, self._restart_for_update)

    def _restart_for_update(self) -> None:
        if self._closing:
            return
        self._updater.stop()
        self._status_pill.configure(text="Updating", text_color=AMBER)
        self.update_idletasks()
        if self.runtime.running:
            self.runtime.stop()
        if not self._updater.launch_pending_apply():
            root = repo_root()
            if root is not None and not is_frozen():
                relaunch("app.gui", root)
        self.destroy()
        os._exit(0)

    def _on_close(self) -> None:
        self._closing = True
        self._updater.stop()
        if self.runtime.running:
            self.runtime.stop()
        self.destroy()


def run_gui() -> None:
    ensure_runtime_files()
    AppWindow().mainloop()
