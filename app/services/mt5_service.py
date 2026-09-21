from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import Settings, TradingRules
from app.exceptions import LiveModeDisabledError, Mt5AccountMismatchError, Mt5ServiceError
from app.trading.models import Direction, OrderType, TradeSignal
from app.trading.symbol_resolver import BrokerSymbol
from app.trading.risk import resolve_volume, select_take_profit
from app.utils.logging import get_logger

try:
    import MetaTrader5 as mt5
except ImportError:  # pragma: no cover - optional at test time
    mt5 = None

logger = get_logger("mt5")

ACCOUNT_TRADE_MODE_DEMO = 0
ACCOUNT_TRADE_MODE_CONTEST = 1
ACCOUNT_TRADE_MODE_REAL = 2
DEFAULT_TERMINAL = Path(r"C:\Program Files\MetaTrader 5\terminal64.exe")
INIT_TIMEOUT_MS = 120_000
NOT_READY_CODES = {-10003, -10001, -10000, -2}
TRADE_ACTION_DEAL = 1
TRADE_ACTION_PENDING = 5
ORDER_TYPE_BUY = 0
ORDER_TYPE_SELL = 1
ORDER_TYPE_BUY_LIMIT = 2
ORDER_TYPE_SELL_LIMIT = 3
ORDER_TYPE_BUY_STOP = 4
ORDER_TYPE_SELL_STOP = 5
ORDER_TIME_GTC = 0
ORDER_FILLING_FOK = 0
ORDER_FILLING_IOC = 1
ORDER_FILLING_RETURN = 2
SYMBOL_FILLING_FOK = 1
SYMBOL_FILLING_IOC = 2
SYMBOL_FILLING_RETURN = 4
TRADE_RETCODE_PLACED = 10008
TRADE_RETCODE_DONE = 10009
TRADE_RETCODE_DONE_PARTIAL = 10010
ORDER_SUCCESS_CODES = {TRADE_RETCODE_PLACED, TRADE_RETCODE_DONE, TRADE_RETCODE_DONE_PARTIAL}
DEFAULT_DEVIATION = 20
DEFAULT_MAGIC = 260921
MAX_ORDER_COMMENT = 29


def _normalize_terminal_path(raw: str) -> Path:
    cleaned = raw.strip().strip('"').strip("'").replace("/", "\\")
    cleaned = cleaned.replace("\terminal64.exe", r"\terminal64.exe")
    if "\t" in cleaned and "terminal64" not in cleaned.lower():
        cleaned = cleaned.replace("\t", "\\t")
    return Path(cleaned)


def _terminal_running() -> bool:
    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq terminal64.exe"],
        capture_output=True,
        text=True,
        check=False,
    )
    return "terminal64.exe" in (result.stdout or "")


def resolve_terminal_path(raw: str | None) -> Path | None:
    candidates: list[Path] = []
    if raw:
        candidates.append(_normalize_terminal_path(raw))
    candidates.append(DEFAULT_TERMINAL)
    for path in candidates:
        if path.is_file():
            return path
    return None


def auth_kwargs(settings: Settings) -> dict[str, object]:
    if not settings.has_mt5_credentials():
        return {}
    return {
        "login": int(settings.mt5_login or 0),
        "password": settings.mt5_password or "",
        "server": (settings.mt5_server or "").strip(),
    }


def describe_initialize_kwargs(kwargs: dict[str, object]) -> str:
    path = kwargs.get("path", "auto")
    if "login" in kwargs:
        return f"path={path} login={kwargs['login']} server={kwargs.get('server')}"
    return f"path={path} without account"


def build_initialize_attempts(
    exe: Path | None,
    settings: Settings,
    prefer_existing: bool = False,
) -> list[dict[str, object]]:
    auth = auth_kwargs(settings)
    timeout = INIT_TIMEOUT_MS
    with_auth_path: dict[str, object] | None = None
    path_only: dict[str, object] | None = None
    with_auth: dict[str, object] | None = None
    auto = {"timeout": timeout}
    if exe is not None and auth:
        with_auth_path = {"path": str(exe), "timeout": timeout, **auth}
    if exe is not None:
        path_only = {"path": str(exe), "timeout": timeout}
    if auth:
        with_auth = {"timeout": timeout, **auth}
    if prefer_existing:
        ordered = (path_only, auto, with_auth_path, with_auth)
    else:
        ordered = (with_auth_path, with_auth, path_only, auto)
    return [item for item in ordered if item is not None]


def _authorization_help(settings: Settings) -> str:
    login = settings.mt5_login
    server = (settings.mt5_server or "").strip() or "(empty)"
    return (
        f" MT5 rejected login {login} on server {server}. "
        "Open MetaTrader 5 Desktop → File → Login to Trade Account, "
        "then copy the Login and Server exactly. "
        "MetaQuotes-Demo only works for a demo opened in this official MetaQuotes terminal. "
        "A broker demo (Exness, XM, IC Markets, and similar) needs that broker's MT5 and server name."
    )


@dataclass
class AccountSnapshot:
    login: int
    server: str
    name: str
    balance: float
    equity: float
    trade_mode: int
    trade_mode_label: str
    currency: str


@dataclass
class Quote:
    symbol: str
    bid: float
    ask: float
    spread: float


@dataclass
class OrderResult:
    ok: bool
    retcode: int | None
    comment: str
    ticket: int | None
    order: int | None
    deal: int | None
    volume: float | None
    price: float | None
    request: dict[str, object]
    response: dict[str, object]
    error_text: str | None = None


def filling_type(filling_mode: int) -> int:
    mode = int(filling_mode or 0)
    if mode & SYMBOL_FILLING_IOC:
        return ORDER_FILLING_IOC
    if mode & SYMBOL_FILLING_FOK:
        return ORDER_FILLING_FOK
    if mode & SYMBOL_FILLING_RETURN:
        return ORDER_FILLING_RETURN
    return ORDER_FILLING_IOC


def order_action_and_type(order_type: OrderType, direction: Direction) -> tuple[int, int]:
    if order_type is OrderType.MARKET:
        if direction is Direction.BUY:
            return TRADE_ACTION_DEAL, ORDER_TYPE_BUY
        if direction is Direction.SELL:
            return TRADE_ACTION_DEAL, ORDER_TYPE_SELL
        never: Direction = direction
        raise ValueError(f"Unhandled direction: {never}")
    if order_type is OrderType.BUY_LIMIT:
        return TRADE_ACTION_PENDING, ORDER_TYPE_BUY_LIMIT
    if order_type is OrderType.SELL_LIMIT:
        return TRADE_ACTION_PENDING, ORDER_TYPE_SELL_LIMIT
    if order_type is OrderType.BUY_STOP:
        return TRADE_ACTION_PENDING, ORDER_TYPE_BUY_STOP
    if order_type is OrderType.SELL_STOP:
        return TRADE_ACTION_PENDING, ORDER_TYPE_SELL_STOP
    never_type: OrderType = order_type
    raise ValueError(f"Unhandled order type: {never_type}")


def normalize_volume(
    volume: float, volume_min: float, volume_max: float, volume_step: float
) -> float:
    step = volume_step if volume_step > 0 else 0.01
    low = volume_min if volume_min > 0 else step
    high = volume_max if volume_max > 0 else volume
    value = round(volume / step) * step
    if value < low:
        value = low
    if value > high:
        value = high
    return float(round(value, 8))


def jsonable(value: Any) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def result_payload(result: Any) -> dict[str, object]:
    if result is None:
        return {}
    if hasattr(result, "_asdict"):
        return {str(key): jsonable(item) for key, item in result._asdict().items()}
    return {"repr": str(result)}


def order_comment(text: str) -> str:
    cleaned = "".join(ch for ch in text if 32 <= ord(ch) <= 126).strip()
    if not cleaned:
        return "tg"
    return cleaned[:MAX_ORDER_COMMENT]


def build_demo_order_request(
    *,
    symbol: str,
    action: int,
    order_type: int,
    volume: float,
    price: float,
    stop_loss: float | None,
    take_profit: float | None,
    filling: int,
    comment: str,
    deviation: int = DEFAULT_DEVIATION,
    magic: int = DEFAULT_MAGIC,
) -> dict[str, object]:
    request: dict[str, object] = {
        "action": action,
        "symbol": symbol,
        "volume": volume,
        "type": order_type,
        "price": price,
        "deviation": deviation,
        "magic": magic,
        "comment": order_comment(comment),
        "type_time": ORDER_TIME_GTC,
        "type_filling": filling,
    }
    if stop_loss:
        request["sl"] = stop_loss
    if take_profit:
        request["tp"] = take_profit
    return request


class Mt5Service:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._initialized = False
        self._connected = False
        self._verified = False
        self._symbol_cache: list[BrokerSymbol] | None = None
        self._symbol_cache_at = 0.0

    @property
    def initialized(self) -> bool:
        return self._initialized

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def verified(self) -> bool:
        return self._verified

    def available(self) -> bool:
        return mt5 is not None

    def initialize(self) -> bool:
        if mt5 is None:
            raise Mt5ServiceError("MetaTrader5 package is not installed.")
        exe = resolve_terminal_path(self._settings.mt5_path)
        if exe is None:
            raise Mt5ServiceError(
                "terminal64.exe was not found. Set MT5_PATH to the desktop terminal."
            )
        already_running = _terminal_running()
        if not already_running:
            logger.info("Starting MT5 desktop: %s", exe)
            subprocess.Popen([str(exe)], cwd=str(exe.parent))
            for _ in range(30):
                time.sleep(1)
                if _terminal_running():
                    time.sleep(5)
                    break
        last_error: object = None
        for kwargs in build_initialize_attempts(exe, self._settings, already_running):
            logger.info("MT5 initialize try: %s", describe_initialize_kwargs(kwargs))
            ok = False
            for _attempt in range(3):
                ok = bool(mt5.initialize(**kwargs))
                if ok:
                    break
                last_error = mt5.last_error()
                code = last_error[0] if isinstance(last_error, tuple) and last_error else None
                mt5.shutdown()
                if code not in NOT_READY_CODES:
                    break
                time.sleep(3)
            if ok:
                self._initialized = True
                logger.info("MT5 initialized (%s)", describe_initialize_kwargs(kwargs))
                return True
            logger.warning(
                "MT5 initialize failed %s (%s)",
                last_error,
                describe_initialize_kwargs(kwargs),
            )
        extra = ""
        if isinstance(last_error, tuple) and last_error and last_error[0] == -6:
            extra = _authorization_help(self._settings)
        raise Mt5ServiceError(
            f"MT5 initialize failed: {last_error}.{extra} "
            "Leave the desktop terminal open, then Start again."
        )

    def login(self) -> bool:
        if mt5 is None or not self._initialized:
            raise Mt5ServiceError("MT5 is not initialized.")
        if not self._settings.has_mt5_credentials():
            raise Mt5ServiceError("MT5 credentials are not configured.")
        current = mt5.account_info()
        expected_server = (self._settings.mt5_server or "").strip()
        if (
            current is not None
            and int(current.login) == int(self._settings.mt5_login or 0)
            and str(current.server).strip() == expected_server
        ):
            self._connected = True
            logger.info(
                "MT5 already signed in as %s on %s",
                current.login,
                current.server,
            )
            return True
        try:
            ok = mt5.login(
                self._settings.mt5_login,
                password=self._settings.mt5_password,
                server=self._settings.mt5_server,
                timeout=INIT_TIMEOUT_MS,
            )
        except TypeError:
            ok = mt5.login(
                self._settings.mt5_login,
                password=self._settings.mt5_password,
                server=self._settings.mt5_server,
            )
        self._connected = bool(ok)
        if not ok:
            extra = ""
            error = mt5.last_error()
            if error and error[0] == -6:
                extra = _authorization_help(self._settings)
            current = mt5.account_info()
            if current is not None:
                extra += (
                    f" The open terminal is currently {current.login} on {current.server}."
                )
            raise Mt5ServiceError(f"MT5 login failed: {error}.{extra}")
        logger.info(
            "MT5 login succeeded for %s on %s",
            self._settings.mt5_login,
            self._settings.mt5_server,
        )
        return True

    def verify_account(self) -> AccountSnapshot:
        snapshot = self.get_account_info()
        expected_login = self._settings.mt5_login
        expected_server = (self._settings.mt5_server or "").strip()
        if expected_login is not None and snapshot.login != expected_login:
            self._verified = False
            raise Mt5AccountMismatchError(
                "Connected MT5 login does not match MT5_LOGIN."
            )
        if expected_server and snapshot.server.strip() != expected_server:
            self._verified = False
            raise Mt5AccountMismatchError(
                "Connected MT5 server does not match MT5_SERVER."
            )
        if self._settings.resolved_app_mode.value == "DEMO":
            if snapshot.trade_mode == ACCOUNT_TRADE_MODE_REAL:
                self._verified = False
                raise Mt5AccountMismatchError(
                    "APP_MODE=DEMO but the connected account is a real account."
                )
            if snapshot.trade_mode not in {
                ACCOUNT_TRADE_MODE_DEMO,
                ACCOUNT_TRADE_MODE_CONTEST,
            }:
                self._verified = False
                raise Mt5AccountMismatchError(
                    "Unable to confirm that the connected account is a demo account."
                )
        self._verified = True
        return snapshot

    def get_account_info(self) -> AccountSnapshot:
        if mt5 is None or not self._initialized:
            raise Mt5ServiceError("MT5 is not initialized.")
        info = mt5.account_info()
        if info is None:
            raise Mt5ServiceError(f"MT5 account_info failed: {mt5.last_error()}")
        mode = int(info.trade_mode)
        label = {
            ACCOUNT_TRADE_MODE_DEMO: "DEMO",
            ACCOUNT_TRADE_MODE_CONTEST: "CONTEST",
            ACCOUNT_TRADE_MODE_REAL: "REAL",
        }.get(mode, "UNKNOWN")
        return AccountSnapshot(
            login=int(info.login),
            server=str(info.server),
            name=str(info.name),
            balance=float(info.balance),
            equity=float(info.equity),
            trade_mode=mode,
            trade_mode_label=label,
            currency=str(info.currency),
        )

    def get_symbol_info(self, symbol: str) -> Any:
        if mt5 is None or not self._initialized:
            raise Mt5ServiceError("MT5 is not initialized.")
        info = mt5.symbol_info(symbol)
        if info is None:
            raise Mt5ServiceError(f"Symbol not found: {symbol}")
        return info

    def list_symbols(self) -> list[BrokerSymbol]:
        if mt5 is None or not self._initialized:
            raise Mt5ServiceError("MT5 is not initialized.")
        now = time.monotonic()
        if self._symbol_cache is not None and now - self._symbol_cache_at < 30:
            return self._symbol_cache
        rows = mt5.symbols_get()
        catalog: list[BrokerSymbol] = []
        for row in rows or []:
            bid = float(getattr(row, "bid", 0) or 0)
            ask = float(getattr(row, "ask", 0) or 0)
            catalog.append(
                BrokerSymbol(
                    name=str(row.name),
                    description=str(getattr(row, "description", "") or ""),
                    path=str(getattr(row, "path", "") or ""),
                    visible=bool(getattr(row, "visible", False)),
                    trade_mode=int(getattr(row, "trade_mode", 0) or 0),
                    bid=bid or None,
                    ask=ask or None,
                )
            )
        self._symbol_cache = catalog
        self._symbol_cache_at = now
        return catalog

    def symbol_exists(self, symbol: str) -> bool:
        try:
            self.get_symbol_info(symbol)
            return True
        except Mt5ServiceError:
            return False

    def ensure_symbol(self, symbol: str) -> bool:
        if mt5 is None or not self._initialized:
            raise Mt5ServiceError("MT5 is not initialized.")
        info = mt5.symbol_info(symbol)
        if info is None:
            return False
        if info.visible:
            return True
        return bool(mt5.symbol_select(symbol, True))

    def get_bid_ask(self, symbol: str) -> Quote:
        if mt5 is None or not self._initialized:
            raise Mt5ServiceError("MT5 is not initialized.")
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise Mt5ServiceError(f"No tick data for {symbol}: {mt5.last_error()}")
        spread = float(tick.ask) - float(tick.bid)
        return Quote(symbol=symbol, bid=float(tick.bid), ask=float(tick.ask), spread=spread)

    def get_positions(self) -> list[Any]:
        if mt5 is None or not self._initialized:
            raise Mt5ServiceError("MT5 is not initialized.")
        positions = mt5.positions_get()
        if positions is None:
            return []
        return list(positions)

    def submit_demo_order(self, signal: TradeSignal, rules: TradingRules) -> OrderResult:
        self._settings.assert_not_live()
        if self._settings.resolved_app_mode.value != "DEMO":
            raise LiveModeDisabledError("Orders are allowed only when APP_MODE=DEMO.")
        if mt5 is None or not self._initialized:
            raise Mt5ServiceError("MT5 is not initialized.")
        if not self._verified:
            raise Mt5ServiceError("MT5 account is not verified.")
        snapshot = self.get_account_info()
        if snapshot.trade_mode == ACCOUNT_TRADE_MODE_REAL:
            raise Mt5AccountMismatchError("Refusing to send an order on a real account.")
        if snapshot.trade_mode not in {
            ACCOUNT_TRADE_MODE_DEMO,
            ACCOUNT_TRADE_MODE_CONTEST,
        }:
            raise Mt5AccountMismatchError("Refusing to send an order on an unconfirmed account type.")
        if signal.direction is None or signal.order_type is None:
            raise Mt5ServiceError("Signal is missing direction or order type.")
        symbol = signal.broker_symbol or signal.normalized_symbol or signal.symbol
        if not symbol:
            raise Mt5ServiceError("Signal is missing a symbol.")
        if not self.ensure_symbol(symbol):
            raise Mt5ServiceError(f"Symbol is not available in MT5: {symbol}")
        info = self.get_symbol_info(symbol)
        quote = self.get_bid_ask(symbol)
        action, type_code = order_action_and_type(signal.order_type, signal.direction)
        if signal.order_type is OrderType.MARKET:
            price = quote.ask if signal.direction is Direction.BUY else quote.bid
        elif signal.entry_price is not None:
            price = float(signal.entry_price)
        else:
            raise Mt5ServiceError("Entry price is required for this order type.")
        digits = int(getattr(info, "digits", 5) or 5)
        price = round(float(price), digits)
        volume = normalize_volume(
            min(resolve_volume(signal, rules), rules.maximum_volume),
            float(getattr(info, "volume_min", 0.01) or 0.01),
            float(getattr(info, "volume_max", rules.maximum_volume) or rules.maximum_volume),
            float(getattr(info, "volume_step", 0.01) or 0.01),
        )
        stop_loss = (
            round(float(signal.stop_loss), digits) if signal.stop_loss is not None else None
        )
        take_profit_raw = select_take_profit(signal, rules)
        take_profit = (
            round(float(take_profit_raw), digits) if take_profit_raw is not None else None
        )
        point = float(getattr(info, "point", 0) or 0)
        stops = int(getattr(info, "trade_stops_level", 0) or 0)
        if stops and point:
            min_dist = stops * point
            if stop_loss is not None and abs(price - stop_loss) < min_dist:
                raise Mt5ServiceError("Stop loss is too close to price for this symbol.")
            if take_profit is not None and abs(price - take_profit) < min_dist:
                raise Mt5ServiceError("Take profit is too close to price for this symbol.")
        request = build_demo_order_request(
            symbol=symbol,
            action=action,
            order_type=type_code,
            volume=volume,
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            filling=filling_type(int(getattr(info, "filling_mode", 0) or 0)),
            comment=signal.comment or signal.signal_id,
        )
        logger.info(
            "Sending DEMO order %s %s volume=%s price=%s",
            symbol,
            signal.direction.value,
            volume,
            price,
        )
        raw = mt5.order_send(request)
        payload = result_payload(raw)
        retcode = int(getattr(raw, "retcode", 0) or 0) if raw is not None else None
        ok = raw is not None and retcode in ORDER_SUCCESS_CODES
        error_text = None if ok else str(getattr(raw, "comment", None) or mt5.last_error())
        if not ok:
            logger.error("DEMO order rejected retcode=%s comment=%s", retcode, error_text)
        return OrderResult(
            ok=ok,
            retcode=retcode,
            comment=str(getattr(raw, "comment", "") or ""),
            ticket=int(getattr(raw, "order", 0) or 0) or None,
            order=int(getattr(raw, "order", 0) or 0) or None,
            deal=int(getattr(raw, "deal", 0) or 0) or None,
            volume=float(getattr(raw, "volume", 0) or 0) or volume,
            price=float(getattr(raw, "price", 0) or 0) or price,
            request=request,
            response=payload,
            error_text=error_text,
        )

    def shutdown(self) -> None:
        if mt5 is None:
            return
        if self._initialized:
            mt5.shutdown()
        self._initialized = False
        self._connected = False
        self._verified = False
        self._symbol_cache = None
        self._symbol_cache_at = 0.0
        logger.info("MT5 shutdown complete")
