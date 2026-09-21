# Where to get every `.env` value

The desktop GUI edits `.env` for you: run `start.bat` or `python -m app.gui`, open **Settings**, change any value, then **Save & Restart**.

Copy `.env.example` to `.env` first:

```powershell
copy .env.example .env
```

Never commit `.env`. Never paste tokens, passwords, or API hashes into chat, git, or screenshots.

---

## 1. Telegram — user client (Mode B, default)

Used when `TELEGRAM_LISTENER_MODE=USER`. This is the mode for channels a bot cannot join.

### `TELEGRAM_API_ID` and `TELEGRAM_API_HASH`

Official source: [https://my.telegram.org/apps](https://my.telegram.org/apps)

Docs: [https://core.telegram.org/api/obtaining_api_id](https://core.telegram.org/api/obtaining_api_id)

These belong to your Telegram account, not to a bot. They appear only **after you create an application**.

#### Do not use the Test configuration

The page also shows a **Test configuration** block. It looks like this and is **not** what this app needs:

- `149.154.167.40:443` (Telegram test datacenter IP)
- `-----BEGIN RSA PUBLIC KEY-----` ... `-----END RSA PUBLIC KEY-----`

Do **not** put that IP or that RSA key in `.env`. That section is only for Telegram’s sandbox/test DCs.

#### Create the app, then scroll to App configuration

1. Open [https://my.telegram.org](https://my.telegram.org) in a browser (use a normal desktop browser, not in-app Telegram).
2. Log in with the **same phone number** you will put in `TELEGRAM_PHONE`. Telegram sends a code in the Telegram app.
3. Click **API development tools**.
4. If you only see Test configuration, you have not created an app yet. Fill the form at the **top** of that page:
  - App title: `trade-aut` (any name)
  - Short name: `tradeaut` (letters/numbers only, short)
  - Platform: `Desktop`
  - Description: `local trading signal listener` (any text)
5. Submit the form. Each phone number can have **one** `api_id`.
6. The same page then shows **App configuration** (above the test block):
  - **App api_id** → a number such as `12345678` → `TELEGRAM_API_ID`
  - **App api_hash** → a 32-character hex string such as `0123456789abcdef0123456789abcdef` → `TELEGRAM_API_HASH`

If the form is missing and you still only see IPs and an RSA key, you are on the wrong card. Go back to [https://my.telegram.org](https://my.telegram.org) and open **API development tools** again, not **Available MTProto servers** / test config.

### `TELEGRAM_PHONE`

Your Telegram account phone number in international format, no spaces or quotes.

Example: `+9647XXXXXXXX`

- Iraq country code is `+964`
- `+960` is Maldives and will be rejected if that is not your number
- Do not wrap the value in quotes in `.env`

Find it in Telegram Desktop:

**Settings → My Account** (or **Settings → Phone**)

This number is only used for the first Telethon login (SMS / in-app code). After `data/telegram.session` exists, the app can connect without asking again.

### First login (creates the session file)

After the three values above are in `.env`, run the app in a normal terminal (not background):

```powershell
.\.venv\Scripts\Activate.ps1
python -m app.main
```

Telegram will send a login code. Enter it in that terminal. If 2FA is enabled, enter the cloud password too.

Session file path (already set):

```
TELEGRAM_SESSION_PATH=data/telegram.session
```

That file is gitignored. Treat it like a password.

If you change `TELEGRAM_PHONE`, `TELEGRAM_API_ID`, or `TELEGRAM_API_HASH` in `.env`, stop the app and delete `data/telegram.session`. Then run `python -m app.main` again and enter the new login code. Changing `.env` does not switch accounts while that session file still exists.

---



## 2. Telegram — bot API (Mode A)

Use this **only if someone with admin rights** can add the bot to the channel. You do not need to own the channel, but a subscriber cannot add a bot to a private channel. If you cannot add the bot, use Mode B (`USER`) instead.

```
TELEGRAM_LISTENER_MODE=BOT
TELEGRAM_BOT_TOKEN=
ALLOWED_CHANNEL_IDS=-1004410224742
```

`TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, and `TELEGRAM_PHONE` are not used in this mode.

### Private channel steps

1. Create the bot with [@BotFather](https://t.me/BotFather) and put the token in `TELEGRAM_BOT_TOKEN`.
2. Open the private channel → **Administrators** → **Add admin** → select the bot.
3. Admin rights needed: the bot must remain an admin so it receives channel posts. Posting permission is not required.
4. Start the app. The log should say `Bot API listener is running as @your_bot`.
5. Post a test message in the channel. The log should show `Incoming Telegram chat=-100...`.
6. Put that chat id in `ALLOWED_CHANNEL_IDS` if it is not already set.

A private channel does **not** work if the bot is only a subscriber. It must be an **administrator**.

Used when `TELEGRAM_LISTENER_MODE=BOT`. The bot must be an **admin** in the target channel, or it will not see posts.

### `TELEGRAM_BOT_TOKEN`

Official source: [@BotFather](https://t.me/BotFather)

1. Open Telegram and start [https://t.me/BotFather](https://t.me/BotFather).
2. Send `/newbot`.
3. Choose a display name and a username ending in `bot`.
4. BotFather replies with a token that looks like:

```
123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

1. Put the full string in `TELEGRAM_BOT_TOKEN`.

To show an existing token later: BotFather → `/mybots` → your bot → **API Token**.

If this bot is only for **reading a channel**, add it to the channel as administrator with at least **Post messages** not required; it needs permission to see channel posts. For a public channel, add the bot as admin. For a private channel, the bot must be a member/admin.

You can use **one bot** for control and another for listening, or the same bot for both. If you use the same token in `TELEGRAM_BOT_TOKEN` and `CONTROL_BOT_TOKEN`, do not run two separate pollers; prefer Mode B (`USER`) for listening and a dedicated control bot.

### `TELEGRAM_LISTENER_MODE`

Not fetched from Telegram. Set it yourself:


| Value  | When to use                                                           |
| ------ | --------------------------------------------------------------------- |
| `USER` | Default. Your logged-in Telegram account already can see the channel. |
| `BOT`  | A bot you created can be added to the channel and receives posts.     |


---



## 3. Telegram — control bot (commands and alerts)

The control bot is a **private** interface. Only IDs in `AUTHORIZED_CONTROL_USER_IDS` may use commands.

### `CONTROL_BOT_TOKEN`

Same process as `TELEGRAM_BOT_TOKEN`: create a **second bot** with [@BotFather](https://t.me/BotFather) (recommended) and paste that token.

Suggested BotFather settings for the control bot:

1. `/mybots` → your control bot → **Bot Settings**
2. **Allow Groups?** — turn on if you will use a private group as the control chat
3. **Group Privacy** — **Turn off** if the bot must see group messages (not required for slash commands sent directly to the bot)
4. **Allow Channels?** — not required for control



### `CONTROL_CHAT_ID`

The chat where the app sends status and approval messages. Usually:

- your **Saved / private chat with the control bot**, or
- a **private group** that contains only you and the control bot

**Method A — BotFather bot + getUpdates**

1. Put `CONTROL_BOT_TOKEN` in `.env` (or keep the token ready).
2. Open Telegram and press **Start** on that bot (or send any message in the private group after adding the bot).
3. In a browser, open (replace the token):

```
https://api.telegram.org/bot<CONTROL_BOT_TOKEN>/getUpdates
```

1. In the JSON, find `"chat":{"id": ... }`.
  - Private chat with the bot: a positive number, for example `845123456`
  - Group: a negative number, for example `-1001234567890`

**Method B — ID bots**

1. Forward any message from the control chat to [@userinfobot](https://t.me/userinfobot) or [@getidsbot](https://t.me/getidsbot).
2. Copy the **Id** / **Chat ID**.

**Method C — Telegram Desktop**

1. Install [Telegram Desktop](https://desktop.telegram.org/).
2. Settings → Advanced → Experimental settings → enable **Show Peer IDs in Profile**.
3. Open the chat profile. The numeric ID is shown.

Put only the number in `.env`:

```
CONTROL_CHAT_ID=845123456
```



### `AUTHORIZED_CONTROL_USER_IDS`

Your personal Telegram **user** ID (not the bot ID, not the chat ID unless they happen to match in a private bot chat).

**Method A**

Open [@userinfobot](https://t.me/userinfobot) and send `/start`. It prints `Id: 845123456`.

**Method B**

Open [@getidsbot](https://t.me/getidsbot) and send `/start`.

**Method C**

Telegram Desktop with **Show Peer IDs in Profile** enabled → open **your own profile**.

If more than one person may control the app, comma-separate the IDs with no spaces required:

```
AUTHORIZED_CONTROL_USER_IDS=845123456,845987654
```

Empty means **nobody** can run `/status`, `/pause`, and the other commands.

### `ALLOWED_CHANNEL_IDS`

Numeric IDs of the signal channels the app may read. Empty means **no channel is authorized** (fail closed).

Channel IDs are usually `-100` plus the channel number, for example `-1001234567890`.

**Method A — forward a channel post**

1. Open the target channel.
2. Forward any post to [@userinfobot](https://t.me/userinfobot) or [@getidsbot](https://t.me/getidsbot).
3. Copy the **forwarded from** channel ID, not your own user ID.

**Method B — Telegram Desktop**

1. Enable **Show Peer IDs in Profile**.
2. Open the channel → channel info. Copy the ID.

**Method C — after Telethon is logged in**

Temporarily you can read incoming events from logs once the listener is connected, then add the printed channel ID here. Until it is listed, messages are stored as `IGNORED`.

Multiple channels:

```
ALLOWED_CHANNEL_IDS=-1001234567890,-1001987654321
```

You must already have legitimate access to that channel with the same Telegram account used for Mode B, or the bot must be a member for Mode A.

---



## 4. MetaTrader 5

All of these come from the **MT5 Desktop terminal** on this Windows PC and from your **broker demo** account. The app talks to the local terminal; it does not log into the broker website.

Install MT5 from your broker or from [https://www.metatrader5.com/en/download](https://www.metatrader5.com/en/download).

Open the terminal and log in to the **demo** account at least once by hand before starting this app.

### `MT5_LOGIN`

The account number (digits only).

Where to find it:

1. In MT5: **Navigator** (`Ctrl+N`) → **Accounts**.
2. The number next to the account, for example `12345678`.
3. Or **File → Login to Trade Account**. The **Login** field is this value.
4. Or the top of the **Toolbox → Trade** tab / account header.

```
MT5_LOGIN=12345678
```



### `MT5_PASSWORD`

The **master** (trader) password for that account, not the investor (read-only) password.

Where to find it:

- The password you chose or received when the broker opened the demo account.
- Broker email / client cabinet → demo account details.
- If you forgot it: broker cabinet → reset demo password, or create a new demo account.

MT5 does not show the current password. If login in the terminal works, use that same password here.

Investor password can read the account but is the wrong password for later order submission. Use the master password now so Phase 5 login matches what you will use later.

### `MT5_SERVER`

The broker server name, not an IP you invent.

Where to find it:

1. **File → Login to Trade Account** → **Server** dropdown.
  Example: `MetaQuotes-Demo`, `ICMarketsSC-Demo`, `XMGlobal-Demo 2`.
2. Or **Navigator → Accounts** — the server is shown under the account.
3. Or the bottom-right corner of the MT5 window (account / server line).
4. Or broker website → “How to log in to MT5” / demo server list.

Copy the name **exactly**, including spaces and `-Demo`.

```
MT5_SERVER=MetaQuotes-Demo
```



### `MT5_PATH`

Full path to `terminal64.exe` on this PC.

Typical locations:

```
C:\Program Files\MetaTrader 5\terminal64.exe
C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe
C:\Program Files\ICMarkets - MetaTrader 5\terminal64.exe
```

How to find the exact path:

1. If MT5 is running: taskbar icon → right-click → **Open file location** (or right-click the shortcut → **Open file location**).
2. Or right-click the Start-menu / desktop shortcut → **Properties** → **Target**.
3. The file must be `terminal64.exe`, not `terminal.exe` (32-bit) and not `metatester64.exe`.

If several brokers’ terminals are installed, point this at the **same** terminal that is already logged into `MT5_LOGIN` / `MT5_SERVER`.

```
MT5_PATH=C:/Program Files/MetaTrader 5/terminal64.exe
```

No quotes. Use forward slashes so `\t` in `\terminal64.exe` is not corrupted.

Open MT5 yourself and log into the demo account before starting this app. If initialize still fails, the app will retry without a path (attaches to an already-running terminal).

### Confirm it is a demo account

In MT5:

1. **Navigator → Accounts** — the account type is often labeled **demo**.
2. **Tools → Options → Server** — demo vs real.
3. Account email / cabinet from the broker.

This app accepts `APP_MODE=DEMO` only. A real account will be rejected and execution stays blocked.

---



## 5. App settings (not from Telegram or MT5)

Set these in `.env` yourself. Defaults match Phases 1–5.


| Variable                | What to put                    | Where it comes from                                                                               |
| ----------------------- | ------------------------------ | ------------------------------------------------------------------------------------------------- |
| `APP_MODE`              | `DEMO`                         | You. Any other value blocks execution.                                                            |
| `EXECUTION_MODE`        | `OBSERVE`                      | You. `APPROVAL` / `AUTO_DEMO` are recorded only; no orders are sent yet.                          |
| `DRY_RUN`               | `true`                         | You. Keep `true` until a later phase.                                                             |
| `LOCAL_TIMEZONE`        | `Asia/Baghdad`                 | [IANA timezone name](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones). Display only. |
| `DATABASE_URL`          | `sqlite:///data/automation.db` | Local file under `data/`.                                                                         |
| `TELEGRAM_SESSION_PATH` | `data/telegram.session`        | Created after the first Telethon login.                                                           |


Symbol aliases and risk rules are **not** env vars. Edit:

- `config/symbols.yaml`
- `config/trading_rules.yaml`

---



## 6. Minimal `.env` by mode



### Recommended first run (listen as your user + private control bot)

```
TELEGRAM_API_ID=
TELEGRAM_API_HASH=
TELEGRAM_PHONE=
TELEGRAM_LISTENER_MODE=USER

CONTROL_BOT_TOKEN=
CONTROL_CHAT_ID=
AUTHORIZED_CONTROL_USER_IDS=
ALLOWED_CHANNEL_IDS=

MT5_LOGIN=
MT5_PASSWORD=
MT5_SERVER=
MT5_PATH=

APP_MODE=DEMO
EXECUTION_MODE=OBSERVE
DRY_RUN=true
LOCAL_TIMEZONE=Asia/Baghdad
```

`TELEGRAM_BOT_TOKEN` can stay empty in this mode.

### Bot-only listener

```
TELEGRAM_LISTENER_MODE=BOT
TELEGRAM_BOT_TOKEN=
```

`TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, and `TELEGRAM_PHONE` can stay empty in this mode.

---



## 7. Checklist

Telegram user mode

- [ ] api_id / api_hash from [my.telegram.org/apps](https://my.telegram.org/apps)
- [ ] Phone matches that login
- [ ] Interactive `python -m app.main` created `data/telegram.session`
- [ ] Control bot token from [@BotFather](https://t.me/BotFather)
- [ ] `CONTROL_CHAT_ID` from getUpdates or [@userinfobot](https://t.me/userinfobot)
- [ ] Your user ID in `AUTHORIZED_CONTROL_USER_IDS`
- [ ] Signal channel ID in `ALLOWED_CHANNEL_IDS`

MT5

- [ ] Terminal installed and already logged into the **demo** account
- [ ] Login number, master password, exact server name
- [ ] `MT5_PATH` points at that broker’s `terminal64.exe`

Then start:

```powershell
.\start.bat
```

The startup banner should show Telegram credentials / connection and MT5 account **VERIFIED**. If a line says `NOT CONFIGURED` or `NOT CONNECTED`, that value is still missing or wrong.