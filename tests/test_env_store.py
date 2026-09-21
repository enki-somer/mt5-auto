from __future__ import annotations

import os
from pathlib import Path

from app.env_store import apply_to_process, read_env, write_env


def test_write_and_read_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    write_env(
        {
            "TELEGRAM_LISTENER_MODE": "BOT",
            "ALLOWED_CHANNEL_IDS": "-1001",
            "MT5_PATH": "C:/Program Files/MetaTrader 5/terminal64.exe",
            "APP_MODE": "DEMO",
        },
        path=path,
    )
    loaded = read_env(path)
    assert loaded["TELEGRAM_LISTENER_MODE"] == "BOT"
    assert loaded["ALLOWED_CHANNEL_IDS"] == "-1001"
    assert "terminal64.exe" in loaded["MT5_PATH"]
    write_env({"TELEGRAM_LISTENER_MODE": "USER", "ALLOWED_CHANNEL_IDS": "-1001"}, path=path)
    reopened = read_env(path)
    assert reopened["TELEGRAM_LISTENER_MODE"] == "USER"
    assert reopened["ALLOWED_CHANNEL_IDS"] == "-1001"
    assert "terminal64.exe" in reopened["MT5_PATH"]
    assert reopened["APP_MODE"] == "DEMO"


def test_apply_to_process_sets_and_clears() -> None:
    apply_to_process({"TELEGRAM_LISTENER_MODE": "USER"})
    assert os.environ["TELEGRAM_LISTENER_MODE"] == "USER"
    apply_to_process({"TELEGRAM_LISTENER_MODE": ""})
    assert "TELEGRAM_LISTENER_MODE" not in os.environ
