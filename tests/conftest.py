from __future__ import annotations

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, TradingRules, load_symbol_aliases, load_trading_rules
from app.database.repository import Repository
from app.database.session import create_db_engine, create_session_factory, init_db
from app.trading.execution_controller import ExecutionController
from app.trading.processor import SignalProcessor
from app.utils.health import RuntimeState


@pytest.fixture
def aliases() -> dict[str, str]:
    return load_symbol_aliases()


@pytest.fixture
def rules() -> TradingRules:
    return load_trading_rules()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        allowed_channel_ids="1001",
        authorized_control_user_ids="2002",
        app_mode="DEMO",
        execution_mode="OBSERVE",
        dry_run=True,
        database_url="sqlite:///:memory:",
        telegram_listener_mode="USER",
    )


@pytest.fixture
def repository(settings: Settings) -> Repository:
    engine = create_db_engine(settings)
    init_db(engine)
    factory: sessionmaker[Session] = create_session_factory(engine)
    return Repository(factory)


@pytest.fixture
def processor(
    settings: Settings,
    rules: TradingRules,
    aliases: dict[str, str],
    repository: Repository,
) -> SignalProcessor:
    state = RuntimeState()
    execution = ExecutionController(settings)
    return SignalProcessor(settings, rules, aliases, repository, state, execution)
