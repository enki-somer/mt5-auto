from __future__ import annotations

from pathlib import Path

from app.config import Settings
from app.services.mt5_service import (
    ORDER_TYPE_BUY,
    TRADE_ACTION_DEAL,
    Mt5Service,
    build_demo_order_request,
    build_initialize_attempts,
    describe_initialize_kwargs,
    filling_type,
    normalize_volume,
    order_action_and_type,
)
from app.trading.models import Direction, OrderType
from app.utils.telegram_ids import is_allowed_channel


def test_order_helpers() -> None:
    action, type_code = order_action_and_type(OrderType.MARKET, Direction.BUY)
    assert action == TRADE_ACTION_DEAL
    assert type_code == ORDER_TYPE_BUY
    assert filling_type(2) == 1
    assert normalize_volume(0.013, 0.01, 1.0, 0.01) == 0.01
    request = build_demo_order_request(
        symbol="XAUUSD",
        action=action,
        order_type=type_code,
        volume=0.01,
        price=3642.0,
        stop_loss=3628.0,
        take_profit=3650.0,
        filling=1,
        comment="abc123",
    )
    assert request["symbol"] == "XAUUSD"
    assert request["sl"] == 3628.0
    assert request["tp"] == 3650.0
    assert "password" not in request


def test_submit_demo_order_refuses_unverified() -> None:
    settings = Settings(app_mode="DEMO", database_url="sqlite:///:memory:")
    service = Mt5Service(settings)
    try:
        service.submit_demo_order  # exists
    except AttributeError:
        raise AssertionError("submit_demo_order must exist")
    assert hasattr(Mt5Service, "submit_demo_order")


def test_live_mode_is_blocked() -> None:
    settings = Settings(app_mode="LIVE", database_url="sqlite:///:memory:")
    assert settings.resolved_app_mode.value == "BLOCKED"
    assert settings.live_trading_enabled is False


def test_typo_mode_is_blocked() -> None:
    settings = Settings(app_mode="DEEMO", database_url="sqlite:///:memory:")
    assert settings.resolved_app_mode.value == "BLOCKED"


def test_channel_id_variants() -> None:
    assert is_allowed_channel(-1004410224742, [-1004410224742])
    assert is_allowed_channel(4410224742, [-1004410224742])
    assert is_allowed_channel(-1004410224742, [4410224742])
    assert not is_allowed_channel(-100111, [-1004410224742])


def test_empty_optional_numbers_are_none() -> None:
    settings = Settings(
        telegram_api_id="",
        control_chat_id="",
        mt5_login="",
        telegram_api_hash="",
        mt5_password="",
        database_url="sqlite:///:memory:",
    )
    assert settings.telegram_api_id is None
    assert settings.control_chat_id is None
    assert settings.mt5_login is None
    assert settings.telegram_api_hash is None
    assert settings.mt5_password is None


def test_initialize_attempts_use_login_and_hide_password() -> None:
    settings = Settings(
        mt5_login=123456,
        mt5_password="secret-pass",
        mt5_server="Broker-Demo",
        mt5_path=r"C:\Program Files\MetaTrader 5\terminal64.exe",
        database_url="sqlite:///:memory:",
    )
    exe = Path(r"C:\Program Files\MetaTrader 5\terminal64.exe")
    attempts = build_initialize_attempts(exe, settings)
    assert attempts[0]["login"] == 123456
    assert attempts[0]["server"] == "Broker-Demo"
    assert attempts[0]["password"] == "secret-pass"
    text = describe_initialize_kwargs(attempts[0])
    assert "secret-pass" not in text
    assert "123456" in text
    assert "Broker-Demo" in text
    existing = build_initialize_attempts(exe, settings, prefer_existing=True)
    assert "login" not in existing[0]
