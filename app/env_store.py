from __future__ import annotations

import os
from pathlib import Path

from app.paths import user_dir


def env_path() -> Path:
    return user_dir() / ".env"


def example_path() -> Path:
    return user_dir() / ".env.example"


ENV_PATH = env_path()
EXAMPLE_PATH = example_path()

ENV_GROUPS: list[tuple[str, list[dict[str, object]]]] = [
    (
        "Telegram",
        [
            {
                "key": "TELEGRAM_LISTENER_MODE",
                "label": "How do you read the channel?",
                "kind": "choice",
                "choices": ["USER", "BOT"],
                "hint": "Use your own account if you cannot add a bot to the channel.",
            },
            {
                "key": "TELEGRAM_API_ID",
                "label": "API ID",
                "kind": "text",
                "hint": "From my.telegram.org",
                "modes": ["USER"],
            },
            {
                "key": "TELEGRAM_API_HASH",
                "label": "API hash",
                "kind": "secret",
                "hint": "From my.telegram.org",
                "modes": ["USER"],
            },
            {
                "key": "TELEGRAM_PHONE",
                "label": "Phone number",
                "kind": "text",
                "hint": "International format, for example +9647XXXXXXXX",
                "placeholder": "+9647XXXXXXXX",
                "modes": ["USER"],
            },
            {
                "key": "TELEGRAM_BOT_TOKEN",
                "label": "Bot token",
                "kind": "secret",
                "hint": "From @BotFather. The bot must be an admin in the channel.",
                "modes": ["BOT"],
            },
            {
                "key": "ALLOWED_CHANNEL_IDS",
                "label": "Channel IDs",
                "kind": "text",
                "hint": "Only these channels are read. Example: -1004410224742",
                "placeholder": "-1004410224742",
            },
        ],
    ),
    (
        "Control bot",
        [
            {"key": "CONTROL_BOT_TOKEN", "label": "Control bot token", "kind": "secret", "advanced": True},
            {"key": "CONTROL_CHAT_ID", "label": "Control chat ID", "kind": "text", "advanced": True},
            {
                "key": "AUTHORIZED_CONTROL_USER_IDS",
                "label": "Allowed control users",
                "kind": "text",
                "advanced": True,
            },
        ],
    ),
    (
        "MetaTrader 5",
        [
            {"key": "MT5_LOGIN", "label": "Account number", "kind": "text"},
            {"key": "MT5_PASSWORD", "label": "Password", "kind": "secret"},
            {
                "key": "MT5_SERVER",
                "label": "Server name",
                "kind": "text",
                "hint": "Copy this exactly from MetaTrader: File → Login to Trade Account.",
            },
            {
                "key": "MT5_PATH",
                "label": "MetaTrader program",
                "kind": "path",
                "hint": "Select terminal64.exe. Leave empty to auto-detect.",
            },
        ],
    ),
    (
        "App",
        [
            {"key": "APP_MODE", "label": "App mode", "kind": "choice", "choices": ["DEMO"], "advanced": True},
            {
                "key": "EXECUTION_MODE",
                "label": "When a signal arrives",
                "kind": "choice",
                "choices": ["OBSERVE", "APPROVAL", "AUTO_DEMO"],
                "hint": "Watch only never sends. Wait for approval holds. Auto on demo sends to MT5 when Keep orders off is turned off.",
            },
            {
                "key": "DRY_RUN",
                "label": "Safe mode",
                "kind": "choice",
                "choices": ["true", "false"],
                "hint": "On = no orders. Off = Auto on demo may send to the demo account.",
            },
            {"key": "LOCAL_TIMEZONE", "label": "Timezone", "kind": "text", "advanced": True},
            {"key": "DATABASE_URL", "label": "Database", "kind": "text", "advanced": True},
            {"key": "TELEGRAM_SESSION_PATH", "label": "Telegram session file", "kind": "text", "advanced": True},
        ],
    ),
]


def known_keys() -> list[str]:
    keys: list[str] = []
    for _group, fields in ENV_GROUPS:
        for field in fields:
            keys.append(str(field["key"]))
    return keys


def read_env(path: Path | None = None) -> dict[str, str]:
    target = path or env_path()
    values: dict[str, str] = {key: "" for key in known_keys()}
    if not target.exists() and example_path().exists():
        target = example_path()
    if not target.exists():
        return values
    for raw_line in target.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def write_env(values: dict[str, str], path: Path | None = None) -> Path:
    target = path or env_path()
    existing: dict[str, str] = {}
    existing_order: list[str] = []
    if target.exists():
        for raw_line in target.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key not in existing:
                existing_order.append(key)
            existing[key] = value.strip().strip('"').strip("'")
    merged = dict(existing)
    merged.update(values)
    ordered: list[str] = []
    for key in known_keys():
        if key in merged and key not in ordered:
            ordered.append(key)
    for key in existing_order:
        if key not in ordered:
            ordered.append(key)
    for key in values:
        if key not in ordered:
            ordered.append(key)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(f"{key}={merged.get(key, '')}" for key in ordered) + "\n", encoding="utf-8")
    return target


def apply_to_process(values: dict[str, str]) -> None:
    for key, value in values.items():
        if value:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)
