# Telegram to MT5 Automation

Windows application that monitors authorized Telegram channels for trading signals, parses and validates them, and (in later phases) executes them on a local MetaTrader 5 demo account.

This milestone implements Phases 1-5: foundation, Telegram ingest, parser, validation, and MT5 connectivity. **No orders are submitted.**

## Requirements

- Windows 10/11
- Python 3.11 (project `.venv` is already created)
- MetaTrader 5 Desktop for connectivity checks
- Telegram API credentials when you are ready to listen to channels

## Python and virtual environment

The repository includes `.venv`. Activate it, then install dependencies:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If you ever need to recreate the environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Configuration

```powershell
copy .env.example .env
```

Edit `.env`. Secrets stay in `.env` only.

### Environment variables

| Variable | Purpose |
| --- | --- |
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` | my.telegram.org user-client credentials (Mode B) |
| `TELEGRAM_PHONE` | Phone for first-time Telethon login |
| `TELEGRAM_BOT_TOKEN` | Bot API listener (Mode A) |
| `TELEGRAM_LISTENER_MODE` | `USER` (default) or `BOT` |
| `CONTROL_BOT_TOKEN` / `CONTROL_CHAT_ID` | Private control notifications and commands |
| `AUTHORIZED_CONTROL_USER_IDS` | Comma-separated Telegram user IDs |
| `ALLOWED_CHANNEL_IDS` | Comma-separated channel IDs. Empty means no channel is authorized. |
| `MT5_LOGIN` / `MT5_PASSWORD` / `MT5_SERVER` / `MT5_PATH` | Local MT5 demo login |
| `APP_MODE` | Must be `DEMO`. Any other value blocks execution. |
| `EXECUTION_MODE` | `OBSERVE` (default), `APPROVAL`, or `AUTO_DEMO` |
| `DRY_RUN` | Default `true` |
| `LOCAL_TIMEZONE` | Default `Asia/Baghdad` |

`LIVE` cannot be enabled by a typo. Order submission is not implemented in this milestone.

### YAML files

- `config/symbols.yaml` — alias to broker symbol
- `config/trading_rules.yaml` — SL/TP requirements, age, volume, allowed symbols, duplicate window, TP strategy

## Telegram setup

1. Create an application at https://my.telegram.org for Mode B.
2. Create a control bot with BotFather. Disable group privacy if it must see channel posts in Mode A.
3. Add the control bot to your private control chat.
4. Discover a channel ID by forwarding a channel post to `@userinfobot` or by logging an incoming event after the listener is authorized.
5. Put that ID in `ALLOWED_CHANNEL_IDS`.

### Telegram authentication (Mode B)

First run must be interactive so Telethon can send a login code:

```powershell
.\.venv\Scripts\Activate.ps1
python -m app.main
```

The session file is stored at `data/telegram.session` and is gitignored.

### Control bot commands

`/status` `/pause` `/resume` `/signals` `/errors` `/positions` `/mode` `/help` `/health`

Unauthorized users are ignored. Credentials are never returned.

## MetaTrader 5

1. Install MT5 Desktop.
2. Log into a **demo** account once in the terminal.
3. Set `MT5_PATH` to `terminal64.exe` if auto-detect fails.
4. This milestone only initializes, logs in, verifies the account, lists symbols, and reads bid/ask.

If the account environment is uncertain, execution stays blocked. Observe/listen can continue.

## Start and stop

GUI (credentials editor + live logs):

```powershell
.\start.bat
```

or `python -m app.gui`

Console only:

```powershell
.\start-console.bat
```

In the GUI, open **Settings**, edit any `.env` value, then **Save & Restart**. Values are not frozen to the first run.

## Copy to a PC that has no Python

On this PC:

```powershell
.\build-exe.bat
```

Copy the whole folder `dist\TelegramMT5` to the other Windows computer. Run `TelegramMT5.exe`. Python is not required there.

That other PC still needs **MetaTrader 5 Desktop** if you want MT5. Telegram works without MT5. First launch creates `.env` next to the exe — edit credentials in the GUI Settings tab.

Optional later: Windows Task Scheduler or NSSM. This project does not change system startup for you.

## Modes

- `DRY_RUN=true` — default; no orders
- `OBSERVE` — parse, validate, store
- `APPROVAL` — recorded as waiting; approval buttons are not live yet
- `AUTO_DEMO` — architecture only; no order send in this milestone

## Logs and database

- Logs: `logs/application.log`, `telegram.log`, `parser.log`, `mt5.log`, `trades.log`, `errors.log`
- SQLite: `data/automation.db` (from `DATABASE_URL`)

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

## Common errors

| Symptom | Check |
| --- | --- |
| Telegram credentials NOT CONFIGURED | `.env` values and listener mode |
| Session not authorized | Interactive first login with `TELEGRAM_PHONE` |
| Channel ignored | `ALLOWED_CHANNEL_IDS` must contain that channel |
| MT5 initialize failed | Terminal installed, path correct, terminal not locked |
| Account mismatch | `MT5_LOGIN` / `MT5_SERVER` must match the open terminal |
| Real account rejected | Use a demo account while `APP_MODE=DEMO` |
| Parser rejects | Missing SL/TP, range entry, contradictory direction, stale message |

## Project layout

See `app/`, `config/`, `tests/`. All MT5 calls go through `app/services/mt5_service.py`.
