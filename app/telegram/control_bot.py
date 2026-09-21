from __future__ import annotations

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from app.config import Settings
from app.database.repository import Repository
from app.services.mt5_service import Mt5Service
from app.utils.health import RuntimeState
from app.utils.logging import get_logger
from app.utils.time import format_local

logger = get_logger("telegram")

COMMANDS = (
    "/status",
    "/pause",
    "/resume",
    "/signals",
    "/errors",
    "/positions",
    "/mode",
    "/help",
    "/health",
)


class ControlBot:
    def __init__(
        self,
        settings: Settings,
        state: RuntimeState,
        repository: Repository,
        mt5_service: Mt5Service,
    ) -> None:
        self._settings = settings
        self._state = state
        self._repository = repository
        self._mt5 = mt5_service
        self._app: Application | None = None

    def credentials_ready(self) -> bool:
        return bool(self._settings.control_bot_token)

    async def start(self) -> None:
        if not self.credentials_ready():
            logger.info("Control bot token is not configured")
            return
        application = Application.builder().token(
            self._settings.control_bot_token or ""
        ).build()
        application.add_handler(CommandHandler("status", self._status))
        application.add_handler(CommandHandler("pause", self._pause))
        application.add_handler(CommandHandler("resume", self._resume))
        application.add_handler(CommandHandler("signals", self._signals))
        application.add_handler(CommandHandler("errors", self._errors))
        application.add_handler(CommandHandler("positions", self._positions))
        application.add_handler(CommandHandler("mode", self._mode))
        application.add_handler(CommandHandler("help", self._help))
        application.add_handler(CommandHandler("health", self._health))
        application.add_handler(CallbackQueryHandler(self._on_callback))
        await application.initialize()
        await application.start()
        if application.updater is None:
            raise RuntimeError("Control bot updater is unavailable.")
        await application.updater.start_polling()
        self._app = application
        self._state.control_bot_active = True
        logger.info("Control bot is running")

    async def stop(self) -> None:
        self._state.control_bot_active = False
        if self._app is None:
            return
        if self._app.updater is not None:
            await self._app.updater.stop()
        await self._app.stop()
        await self._app.shutdown()

    def _authorized(self, update: Update) -> bool:
        user = update.effective_user
        if user is None:
            return False
        return user.id in self._settings.authorized_control_user_id_list()

    async def _reject_unknown(self, update: Update) -> bool:
        if self._authorized(update):
            return False
        logger.info("Ignored unauthorized control command")
        return True

    async def _status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if await self._reject_unknown(update):
            return
        if update.message is None:
            return
        await update.message.reply_text(self._status_text())

    async def _pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if await self._reject_unknown(update):
            return
        self._state.paused = True
        self._state.processing_active = False
        if update.message is not None:
            await update.message.reply_text("Signal processing paused.")

    async def _resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if await self._reject_unknown(update):
            return
        self._state.paused = False
        self._state.processing_active = True
        if update.message is not None:
            await update.message.reply_text("Signal processing resumed.")

    async def _signals(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if await self._reject_unknown(update):
            return
        if update.message is None:
            return
        rows = self._repository.list_recent_signals(10)
        if not rows:
            await update.message.reply_text("No signals stored.")
            return
        lines = []
        for row in rows:
            lines.append(
                f"{row.signal_id[:8]} {row.normalized_symbol} {row.direction} "
                f"{row.validation_status} {row.execution_status}"
            )
        await update.message.reply_text("\n".join(lines))

    async def _errors(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if await self._reject_unknown(update):
            return
        if update.message is None:
            return
        rows = self._repository.list_recent_errors(10)
        if not rows:
            await update.message.reply_text("No recent errors.")
            return
        lines = [
            f"{format_local(row.created_at, self._settings.local_timezone)} {row.message}"
            for row in rows
        ]
        await update.message.reply_text("\n".join(lines))

    async def _positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if await self._reject_unknown(update):
            return
        if update.message is None:
            return
        if not self._state.mt5_connected:
            await update.message.reply_text("MT5 is not connected.")
            return
        try:
            positions = self._mt5.get_positions()
        except Exception as error:
            await update.message.reply_text(f"Unable to read positions: {error}")
            return
        if not positions:
            await update.message.reply_text("No open positions.")
            return
        lines = []
        for position in positions:
            symbol = getattr(position, "symbol", "?")
            volume = getattr(position, "volume", "?")
            ticket = getattr(position, "ticket", "?")
            lines.append(f"{ticket} {symbol} {volume}")
        await update.message.reply_text("\n".join(lines))

    async def _mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if await self._reject_unknown(update):
            return
        if update.message is None:
            return
        await update.message.reply_text(
            f"APP_MODE={self._settings.resolved_app_mode.value}\n"
            f"EXECUTION_MODE={self._settings.execution_mode.value}\n"
            f"DRY_RUN={self._settings.dry_run}"
        )

    async def _help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if await self._reject_unknown(update):
            return
        if update.message is None:
            return
        await update.message.reply_text("Available commands:\n" + "\n".join(COMMANDS))

    async def _health(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if await self._reject_unknown(update):
            return
        if update.message is None:
            return
        await update.message.reply_text(self._health_text())

    async def _on_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        query = update.callback_query
        if query is None:
            return
        if not self._authorized(update):
            await query.answer()
            return
        data = query.data or ""
        if data not in {"APPROVE", "REJECT"}:
            await query.answer()
            return
        await query.answer()
        await query.edit_message_text(
            "Approval actions are not enabled in Phases 1-5."
        )

    def _status_text(self) -> str:
        return "\n".join(
            [
                f"Application: running",
                f"Paused: {self._state.paused}",
                f"Telegram listener: {self._state.telegram_listener_active}",
                f"MT5: {self._state.mt5_connected}",
                f"Account type: {self._state.mt5_account_type or 'n/a'}",
                f"Balance: {self._state.mt5_balance if self._state.mt5_balance is not None else 'n/a'}",
                f"Open positions: {self._state.open_positions}",
                f"Last signal: {self._state.last_signal_summary or 'n/a'}",
                f"Last execution: {self._state.last_successful_execution or 'none'}",
                f"Uptime seconds: {int(self._state.uptime_seconds())}",
            ]
        )

    def _health_text(self) -> str:
        return "\n".join(
            [
                f"Telegram connected: {self._state.telegram_connected}",
                f"MT5 initialized: {self._state.mt5_initialized}",
                f"Database: {self._state.database_ok}",
                f"Listener active: {self._state.telegram_listener_active}",
                f"Processing active: {self._state.processing_active}",
                f"Paused: {self._state.paused}",
                f"Last Telegram event: {self._state.last_telegram_event}",
                f"Last MT5 health: {self._state.last_mt5_health}",
                f"Last exception: {self._state.last_exception or 'none'}",
            ]
        )
