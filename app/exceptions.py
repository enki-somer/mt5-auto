class AppError(Exception):
    """Base application error."""


class ConfigurationError(AppError):
    """Invalid or incomplete configuration."""


class LiveModeDisabledError(AppError):
    """LIVE trading is not allowed."""


class SignalRejectedError(AppError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class DuplicateSignalError(AppError):
    """Telegram message has already been processed."""


class StaleSignalError(AppError):
    """Signal is older than the configured maximum age."""


class Mt5ServiceError(AppError):
    """MetaTrader 5 service failure."""


class Mt5AccountMismatchError(AppError):
    """Connected MT5 account does not match the configured account."""


class TelegramAuthError(AppError):
    """Telegram authentication or authorization failure."""
