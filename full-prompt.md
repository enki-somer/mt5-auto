You are a senior Python automation engineer.

Build a production-quality Windows application that monitors a Telegram channel for trading signals, parses those signals according to configurable rules, validates them, and interacts with MetaTrader 5 running locally on the same Windows laptop.

The application will initially be used with an MT5 DEMO account.

Do not make assumptions silently. Where behavior can vary, expose it through configuration.

==================================================

1. ENVIRONMENT
   ==================================================

Target operating system:

Windows 10/11

Runtime:

Python 3.12+ preferred.

MetaTrader:

MetaTrader 5 Desktop installed locally on Windows.

MT5 may be minimized but will normally remain running.

The laptop will remain powered on and connected to the internet while the automation is operating.

Do NOT design this around clicking the Telegram GUI or clicking buttons inside MetaTrader.

Use APIs/programmatic integrations.

The intended architecture is:

Telegram
↓
Telegram Listener
↓
Signal Parser
↓
Validation / Risk Engine
↓
Execution Controller
↓
MetaTrader 5
↓
Broker

The application should also send status and execution notifications back to a private Telegram control bot/chat.

==================================================
2. PROJECT OBJECTIVE
====================

The software must continuously monitor one or more authorized Telegram channels.

When a new message arrives:

1. Receive the Telegram message.
2. Verify that it came from an allowed channel.
3. Store the raw message.
4. Determine whether the message contains a trading signal.
5. Parse the signal.
6. Normalize the instrument name.
7. Validate all required fields.
8. Apply configured risk rules.
9. Detect duplicates.
10. Determine whether the signal is still fresh enough to execute.
11. Produce a structured TradeSignal object.
12. In DEMO mode, submit the intended trade to the configured MT5 demo account.
13. Record the MT5 response.
14. Store the result permanently.
15. Send a Telegram notification describing what happened.

The system must fail closed.

If information is ambiguous, malformed, contradictory, stale, or incomplete, DO NOT GUESS.

Reject the signal and explain the rejection reason.

==================================================
3. TELEGRAM CONNECTION
======================

Support two Telegram modes.

MODE A:

Telegram Bot API.

Use this if a Telegram bot can legitimately receive the messages from the target channel.

MODE B:

Authenticated Telegram user client using Telethon or another appropriate maintained MTProto library.

Use this when monitoring a Telegram channel that the authenticated Telegram account already has legitimate access to but where a bot cannot be added.

Do NOT scrape the Telegram desktop UI.

Credentials must come from environment variables or an .env file.

Never hardcode:

API IDs
API hashes
bot tokens
phone numbers
session secrets
MT5 passwords
broker passwords

Example environment variables:

TELEGRAM_API_ID=
TELEGRAM_API_HASH=
TELEGRAM_PHONE=
TELEGRAM_BOT_TOKEN=
CONTROL_CHAT_ID=

ALLOWED_CHANNEL_IDS=

MT5_LOGIN=
MT5_PASSWORD=
MT5_SERVER=
MT5_PATH=

APP_MODE=DEMO
EXECUTION_MODE=APPROVAL

==================================================
4. TELEGRAM CONTROL BOT
=======================

Create a private Telegram control interface.

Only explicitly authorized Telegram user IDs may use commands.

Configuration:

AUTHORIZED_CONTROL_USER_IDS=

Commands should include:

/status

Return:

application state
Telegram listener state
MT5 connection state
account type
account balance if available
number of open positions
last signal received
last successful execution
uptime

/pause

Pause processing of new trading signals.

/resume

Resume signal processing.

/signals

Show the latest signals and statuses.

/errors

Show recent application errors.

/positions

Show current MT5 positions.

/mode

Show current execution mode.

/help

Show available commands.

Optional:

/health

Return detailed service health information.

Do NOT expose credentials through Telegram commands.

==================================================
5. EXECUTION MODES
==================

Implement these modes.

MODE 1:

OBSERVE

Receive and parse signals only.

Never submit anything to MT5.

MODE 2:

APPROVAL

Receive signal.

Parse signal.

Validate signal.

Send the normalized trade to my private Telegram control chat.

Example:

NEW TRADE SIGNAL

Symbol: XAUUSD
Direction: BUY
Entry: MARKET
SL: 3625
TP: 3675
Volume: 0.02

Source:
Channel Name

Message ID:
82911

Received:
18:32:14

Buttons:

APPROVE
REJECT

Only an authorized Telegram control user can approve.

After approval:

revalidate the signal
check its age again
check MT5 connection again
check current price if applicable
then submit on DEMO MT5.

MODE 3:

AUTO_DEMO

Automatically execute validated signals against the MT5 demo account.

The code architecture may support a future LIVE mode, but do not automatically enable live-money trading.

LIVE must never become active merely because an environment variable was mistyped.

Use explicit defensive checks.

==================================================
6. TRADING SIGNAL DATA MODEL
============================

Create a clear data model such as:

TradeSignal

Fields:

signal_id
telegram_channel_id
telegram_message_id
telegram_message_date
received_at
raw_message

symbol
normalized_symbol

direction

BUY
SELL

order_type

MARKET
BUY_LIMIT
SELL_LIMIT
BUY_STOP
SELL_STOP

entry_price

stop_loss

take_profits

volume

risk_percent

comment

parser_confidence

validation_status

rejection_reason

execution_status

created_at
updated_at

A signal may contain multiple take-profit levels.

Example:

TP1
TP2
TP3

Do not assume that every signal has only one TP.

==================================================
7. SIGNAL EXAMPLES
==================

The parser should be modular enough to handle messages resembling:

Example A:

GOLD BUY NOW

ENTRY 3642

SL 3628

TP1 3650
TP2 3660
TP3 3680

Example B:

XAUUSD BUY

3640-3643

SL: 3625

TP: 3655
TP: 3670

Example C:

SELL GOLD

Market

Stop Loss 3685

Take Profit 3650

Example D:

EURUSD SELL LIMIT

Entry 1.18250

SL 1.18500

TP1 1.18000
TP2 1.17750

The parser must support configurable aliases.

Example:

GOLD
XAU
XAUUSD

may map to the broker symbol:

XAUUSD

But symbol aliases MUST be configurable.

For example:

config/symbols.yaml

GOLD: XAUUSD
XAU: XAUUSD
XAUUSD: XAUUSD
NAS100: USTEC
US100: USTEC

Do not assume broker symbol names.

==================================================
8. PARSER ARCHITECTURE
======================

Do NOT create one giant regex.

Create a modular parser.

Suggested stages:

normalize_text()

detect_signal()

extract_symbol()

extract_direction()

extract_order_type()

extract_entry()

extract_stop_loss()

extract_take_profits()

extract_volume_if_present()

normalize_signal()

validate_signal()

The parser should preserve the raw Telegram message.

Parsing errors should be understandable.

Example rejection:

SIGNAL REJECTED

Reason:
Direction detected as BUY, but Stop Loss is above entry price.

Message:
82918

Do not silently fix suspicious values.

==================================================
9. CONFIGURABLE SIGNAL RULES
============================

Create:

config/trading_rules.yaml

Allow rules such as:

require_stop_loss: true

require_take_profit: true

minimum_take_profits: 1

maximum_signal_age_seconds: 120

default_volume: 0.01

maximum_volume: 0.05

maximum_open_positions: 3

allow_market_orders: true

allow_pending_orders: true

allowed_symbols:

* XAUUSD
* EURUSD

allowed_directions:

* BUY
* SELL

duplicate_window_hours: 24

Require configuration rather than hardcoded values wherever possible.

==================================================
10. VALIDATION ENGINE
=====================

Validation must happen before any MT5 action.

Validate:

signal source is authorized

message ID has not already been executed

symbol is allowed

symbol exists in MT5

direction exists

order type is valid

entry exists when required

SL exists if required

TP exists if required

volume is within limits

signal is not stale

MT5 is connected

market is available where relevant

maximum open position limit not exceeded

price relationships make logical sense

For BUY:

normally:
SL < entry
TP > entry

For SELL:

normally:
SL > entry
TP < entry

For market orders, use current market price during final validation.

Do not assume a parsed signal is valid merely because parsing succeeded.

==================================================
11. DUPLICATE PROTECTION
========================

This is mandatory.

Telegram messages must have unique processing protection.

Primary identity:

telegram_channel_id
+
telegram_message_id

Store every received message.

Statuses could include:

RECEIVED
IGNORED
PARSED
INVALID
WAITING_APPROVAL
REJECTED
APPROVED
EXECUTING
EXECUTED
FAILED

If the application restarts, it must know whether a Telegram signal has already been processed.

Never execute the same Telegram message twice.

Also implement optional semantic duplicate detection.

For example:

same symbol
same direction
same entry
same SL
same TP

within a short time window.

Semantic duplicates should normally require review rather than automatic execution.

==================================================
12. DATABASE
============

Use SQLite initially.

Use SQLAlchemy.

Design the database so moving to PostgreSQL later is easy.

Suggested tables:

telegram_messages

trade_signals

trade_attempts

executed_trades

application_events

configuration_history if useful

Required information should include:

raw message
parsed fields
validation result
approval information
MT5 request
MT5 response
ticket/order number
timestamps
errors

==================================================
13. MT5 INTEGRATION
===================

Create an isolated MT5 service module.

Example:

services/mt5_service.py

Responsibilities:

initialize MT5

login

verify account

verify that this is the expected account

retrieve symbol information

enable/select symbol if necessary

retrieve bid/ask

retrieve account information

retrieve positions

prepare order

submit DEMO order

interpret MT5 result codes

shutdown safely

The rest of the application must not call MetaTrader5 directly.

Only the MT5 service layer should communicate with MT5.

==================================================
14. ACCOUNT SAFETY
==================

At startup display:

MT5 ACCOUNT

Login:
Server:
Account type:
Balance:
Mode:

If APP_MODE=DEMO:

verify the configured account is intended for demo testing.

If there is any uncertainty about the account environment:

STOP EXECUTION.

The application can still run in OBSERVE mode.

Never silently fall back to another MT5 account.

==================================================
15. ORDER EXECUTION
===================

Create a normalized OrderRequest before interacting with MT5.

Example:

OrderRequest(
symbol="XAUUSD",
direction="BUY",
order_type="MARKET",
volume=0.02,
entry=None,
stop_loss=3625,
take_profit=3670,
source_signal_id=123
)

The application should preserve both:

requested price

actual execution price

Store:

requested volume

executed volume

spread at execution

broker return code

ticket/order ID

position ID where available

timestamp

raw broker response

==================================================
16. MULTIPLE TAKE PROFITS
=========================

Design the system so it can eventually support:

TP1
TP2
TP3

Do not hardcode only one TP.

Initially implement one of these configurable strategies:

FIRST_TP
LAST_TP
SELECTED_TP

For example:

take_profit_strategy: LAST_TP

Architecture should allow future partial-position execution.

==================================================
17. LOGGING
===========

Implement structured logging.

Use Python logging.

Prefer rotating log files.

Example directory:

logs/

application.log
telegram.log
parser.log
mt5.log
trades.log
errors.log

Log:

startup
shutdown
Telegram connectivity
new messages
parsing
validation
approvals
MT5 connectivity
execution attempts
execution results
exceptions

Never log passwords, API secrets, tokens, or Telegram session secrets.

==================================================
18. WINDOWS STARTUP
===================

The application should be easy to start on Windows.

Provide:

start.bat

Example intended behavior:

activate virtual environment

start application

write logs

Keep the console readable.

Also document how to optionally configure the project later using:

Windows Task Scheduler

or

NSSM

for automatic startup.

Do not automatically make system-level changes.

==================================================
19. APPLICATION HEALTH
======================

Implement health status.

Health checks:

Telegram connected

MT5 initialized

database available

listener active

signal processing active

paused state

last Telegram event time

last MT5 health check

last exception

If MT5 disconnects:

DO NOT lose Telegram signals.

Store incoming signals.

Mark them appropriately.

Do not blindly execute old queued signals when MT5 reconnects.

Recheck:

signal age

current market conditions

validation

approval state

before doing anything.

==================================================
20. ERROR HANDLING
==================

The application should never crash because one Telegram message is malformed.

Use exception boundaries around:

Telegram

parser

database

MT5

control bot

execution

Errors must be logged.

Critical failures should trigger a Telegram alert.

Example:

SYSTEM WARNING

MT5 connection lost.

Automatic execution has been paused.

Time:
18:52:11

==================================================
21. TELEGRAM NOTIFICATIONS
==========================

Send notifications for:

system started

system stopped

MT5 connected

MT5 disconnected

signal received

signal rejected

signal waiting approval

trade approved

trade rejected

demo trade submitted

trade failed

duplicate signal detected

unexpected system error

Avoid excessive spam.

==================================================
22. PROJECT STRUCTURE
=====================

Use a maintainable project structure approximately like:

telegram_mt5_automation/

```
app/
    __init__.py
    main.py

    config.py

    telegram/
        listener.py
        control_bot.py

    parser/
        detector.py
        parser.py
        normalizer.py
        validators.py

    trading/
        models.py
        risk.py
        execution_controller.py

    services/
        mt5_service.py

    database/
        models.py
        repository.py
        session.py

    notifications/
        telegram_notifier.py

    utils/
        logging.py
        time.py

config/
    symbols.yaml
    trading_rules.yaml

data/

logs/

tests/

    test_parser.py
    test_validation.py
    test_duplicates.py
    test_signal_age.py
    test_symbol_mapping.py

.env.example

.gitignore

requirements.txt

start.bat

README.md
```

==================================================
23. TESTING
===========

Write real tests.

Especially parser tests.

Create at least 20 sample Telegram messages.

Include:

normal signals

different whitespace

emoji

Arabic text mixed with English signal syntax

uppercase

lowercase

missing SL

missing TP

multiple TP

price range

malformed number

duplicate message

contradictory BUY/SELL

unsupported symbol

stale message

edited Telegram message

forwarded signal

non-trading conversation

The parser should reject messages rather than hallucinate missing values.

==================================================
24. DRY RUN
===========

Implement:

DRY_RUN=true

When active:

Telegram should work.

Parsing should work.

Validation should work.

Database should work.

Notifications should work.

MT5 connection may work.

But no MT5 order should be submitted.

Instead log:

WOULD EXECUTE:

XAUUSD
BUY
0.02
Market
SL 3625
TP 3670

This will be the first mode used during development.

==================================================
25. EDITED TELEGRAM MESSAGES
============================

Handle edited Telegram messages safely.

If a signal has NOT been executed:

update stored content

reparse

revalidate

If a signal has already been executed:

NEVER automatically execute another trade because the Telegram message was edited.

Instead notify:

EXECUTED SIGNAL EDITED

Original message:
...

Updated message:
...

Manual review required.

==================================================
26. DELETED TELEGRAM MESSAGES
=============================

If Telegram exposes message deletion events and a previously detected signal gets deleted:

record the event.

If not yet executed:

cancel pending approval where possible.

If already executed:

send an alert.

Do not automatically close an MT5 position simply because the Telegram message was deleted.

==================================================
27. SECURITY
============

Use:

.env

.gitignore

Never commit:

.env
*.session
Telegram session files
passwords
API keys
MT5 credentials
database credentials

Restrict Telegram control commands by Telegram user ID.

Ignore unauthorized callbacks.

Validate callback data.

Do not allow arbitrary shell command execution through Telegram.

==================================================
28. TIME HANDLING
=================

Store timestamps internally in UTC.

Display local timestamps using configurable timezone.

Default:

Asia/Baghdad

Configuration:

LOCAL_TIMEZONE=Asia/Baghdad

Telegram message age must be calculated correctly using timezone-aware datetimes.

==================================================
29. CONFIGURATION
=================

Create a single understandable settings system.

Use environment variables for secrets and machine-specific configuration.

Use YAML for trading/parser behavior.

Example:

.env

TELEGRAM_API_ID=
TELEGRAM_API_HASH=
TELEGRAM_PHONE=

CONTROL_BOT_TOKEN=
CONTROL_CHAT_ID=

AUTHORIZED_CONTROL_USER_IDS=

MT5_LOGIN=
MT5_PASSWORD=
MT5_SERVER=
MT5_PATH=

APP_MODE=DEMO
EXECUTION_MODE=APPROVAL

DRY_RUN=true

LOCAL_TIMEZONE=Asia/Baghdad

==================================================
30. README
==========

Create a detailed README explaining:

requirements

Python installation

virtual environment creation

dependency installation

Telegram API setup

Telegram authentication

control bot setup

channel ID discovery

MT5 installation

MT5 account setup

environment configuration

symbol mapping

starting the application

stopping the application

DRY_RUN

OBSERVE mode

APPROVAL mode

AUTO_DEMO mode

reading logs

database location

common errors

Telegram session authentication

MT5 connection troubleshooting

==================================================
31. INSTALLATION EXPERIENCE
===========================

I want installation to be easy.

Target setup:

git clone / project folder

python -m venv .venv

.venv\Scripts\activate

pip install -r requirements.txt

copy .env.example .env

edit .env

python -m app.main

Also provide:

start.bat

==================================================
32. FIRST-RUN DIAGNOSTIC
========================

When the application starts, show something like:

========================================
Telegram → MT5 Automation
=========================

Mode: DEMO
Execution: APPROVAL
Dry Run: TRUE

Database ............. OK
Telegram credentials . OK
Telegram connection .. OK
Control bot .......... OK
MT5 installation ..... FOUND
MT5 connection ....... OK
MT5 account .......... VERIFIED
Symbol mapping ....... OK

Listening to:

Channel:
Channel ID:

========================================
SYSTEM READY
============

If anything important fails:

clearly show the reason.

==================================================
33. CODING QUALITY
==================

Use:

type hints

dataclasses or Pydantic models where appropriate

small functions

dependency separation

clear interfaces

structured exceptions

asyncio where useful for Telegram

do not create unnecessary complexity

do not create giant files

do not put all logic in main.py

Do not leave major sections as pseudo-code.

Implement working code.

==================================================
34. DEVELOPMENT ORDER
=====================

Build incrementally.

PHASE 1

Create project structure.

Create configuration system.

Create database.

Create logging.

PHASE 2

Connect Telegram.

Print incoming authorized channel messages.

Persist incoming messages.

PHASE 3

Implement parser.

Implement parser tests.

PHASE 4

Implement validation.

Implement duplicate protection.

Implement stale-message protection.

PHASE 5

Implement MT5 connectivity.

Retrieve account information.

Retrieve symbols.

Retrieve market prices.

NO ORDER SUBMISSION YET.

PHASE 6

Implement DRY_RUN execution simulation.

PHASE 7

Implement Telegram approval workflow.

PHASE 8

Implement MT5 DEMO execution.

PHASE 9

Implement control commands and health monitoring.

PHASE 10

Run end-to-end test suite.

==================================================
35. CRITICAL DEVELOPMENT RULE
=============================

DO NOT jump directly to order submission.

I want each stage verified.

Before implementing actual DEMO order submission, demonstrate that:

Telegram listener works

channel filtering works

database persistence works

parser works

validation works

duplicate protection works

stale-signal protection works

MT5 connection works

symbol discovery works

bid/ask retrieval works

DRY_RUN works

Only then implement DEMO order submission.

==================================================
36. OUTPUT EXPECTED FROM YOU
============================

You have access to the local machine and project directory.

Actually create the project.

Do not merely explain what code I should write.

Create all required directories and files.

Install dependencies if permitted.

Create the virtual environment if appropriate.

Create .env.example.

Do NOT put secrets into source files.

Run tests.

Run syntax checks.

Fix errors you encounter.

At the end provide:

1. Project directory location.
2. Files created.
3. Dependencies installed.
4. Tests performed.
5. Test results.
6. Anything that still requires my credentials.
7. Exact next command I should run.
8. Exact information you need from me before Telegram authentication.
9. Exact information you need from me before connecting MT5.

Do not invent credentials.

==================================================
37. INFORMATION THAT WILL BE PROVIDED LATER
===========================================

I will later provide:

Telegram channel name

Telegram channel ID if known

whether I own the Telegram channel

real examples of signals

symbol mappings

my preferred TP strategy

default volume/risk rules

maximum permitted open positions

signal expiry duration

MetaTrader broker/server information

Do not hardcode assumptions about those values.

Until real examples are supplied, create fixtures/sample signals for development.

==================================================
38. FINAL DESIGN PRINCIPLE
==========================

Reliability is more important than immediately placing a trade.

The priority order is:

1. Never execute the same signal twice.
2. Never guess missing trade information.
3. Never execute stale signals.
4. Never execute malformed signals.
5. Never use an unexpected MT5 account.
6. Preserve every relevant event in logs/database.
7. Make failures visible.
8. Keep the system simple enough to maintain.
9. Start in DRY_RUN.
10. Use DEMO before anything involving real funds.

Begin by inspecting the current local environment and create the project architecture.

Then implement PHASE 1 through PHASE 5 first.

Do not request trading credentials until the relevant stage requires them.
