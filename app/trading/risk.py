from __future__ import annotations

from app.config import TakeProfitStrategy, TradingRules
from app.trading.models import TradeSignal


def resolve_volume(signal: TradeSignal, rules: TradingRules) -> float:
    if signal.volume is not None:
        return signal.volume
    return rules.default_volume


def select_take_profit(signal: TradeSignal, rules: TradingRules) -> float | None:
    strategy = rules.take_profit_strategy
    if strategy is TakeProfitStrategy.FIRST_TP:
        return signal.selected_take_profit("FIRST_TP")
    if strategy is TakeProfitStrategy.SELECTED_TP:
        return signal.selected_take_profit("SELECTED_TP", rules.selected_take_profit_index)
    if strategy is TakeProfitStrategy.LAST_TP:
        return signal.selected_take_profit("LAST_TP")
    never: TakeProfitStrategy = strategy
    raise ValueError(f"Unhandled take-profit strategy: {never}")
