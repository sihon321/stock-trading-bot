import dataclasses
import importlib
import sys

import pytest

from trading_bot.domain import Money, Position, Ticker
from trading_bot.risk import (
    DailyLossState,
    RiskAction,
    RiskConfig,
    RiskDecision,
    blocks_new_buy,
    evaluate_position_risk,
)


FORBIDDEN_MODULE_PREFIXES = (
    "anthropic",
    "openai",
    "pykrx",
    "requests",
    "httpx",
    "pydantic",
)

FORBIDDEN_LOCAL_MODULE_FRAGMENTS = (
    "adapter",
    "kis",
    "naver",
    "scrap",
    "signal_parser",
    "execution",
    "config",
    "ports",
)


def _ticker() -> Ticker:
    return Ticker("005930")


def _position(avg: float, quantity: int = 10) -> Position:
    return Position(ticker=_ticker(), quantity=quantity, average_price=Money(avg, "KRW"))


def _config(stop: float = 0.05, take: float = 0.10) -> RiskConfig:
    return RiskConfig(stop_loss_pct=stop, take_profit_pct=take)


def test_risk_result_objects_are_frozen_dataclasses_and_string_enums() -> None:
    decision = RiskDecision(action=RiskAction.SELL, reason="stop_loss")

    assert dataclasses.is_dataclass(decision)
    assert isinstance(RiskAction.SELL, str)
    assert RiskAction.HOLD.value == "HOLD"
    assert RiskAction.SELL.value == "SELL"
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.reason = "mutated"  # type: ignore[misc]


def test_no_position_holds_without_a_trade() -> None:
    decision = evaluate_position_risk(None, Money(70000.0, "KRW"), _config())

    assert decision.action is RiskAction.HOLD


def test_zero_quantity_position_holds_without_a_trade() -> None:
    decision = evaluate_position_risk(_position(70000.0, quantity=0), Money(50000.0, "KRW"), _config())

    assert decision.action is RiskAction.HOLD


def test_stop_loss_breach_emits_sell_without_llm_signal() -> None:
    # entry 70000, stop 5% -> exit at/below 66500.
    decision = evaluate_position_risk(_position(70000.0), Money(66000.0, "KRW"), _config(stop=0.05))

    assert decision.action is RiskAction.SELL
    assert decision.reason == "stop_loss"


def test_take_profit_breach_emits_sell_without_llm_signal() -> None:
    # entry 70000, take 10% -> exit at/above 77000.
    decision = evaluate_position_risk(_position(70000.0), Money(78000.0, "KRW"), _config(take=0.10))

    assert decision.action is RiskAction.SELL
    assert decision.reason == "take_profit"


def test_price_within_bounds_holds() -> None:
    decision = evaluate_position_risk(_position(70000.0), Money(71000.0, "KRW"), _config())

    assert decision.action is RiskAction.HOLD


@pytest.mark.parametrize("entry, price", [(0.0, 70000.0), (-1.0, 70000.0), (70000.0, 0.0), (70000.0, -5.0)])
def test_non_positive_prices_hold_safely_rather_than_trade(entry: float, price: float) -> None:
    decision = evaluate_position_risk(_position(entry), Money(price, "KRW"), _config())

    assert decision.action is RiskAction.HOLD


def test_daily_loss_breach_blocks_new_buys() -> None:
    config = _config()
    breached = DailyLossState(realized_loss=600000.0, threshold=500000.0)

    assert blocks_new_buy(breached, config) is True


def test_daily_loss_within_threshold_does_not_block_buys() -> None:
    config = _config()
    within = DailyLossState(realized_loss=100000.0, threshold=500000.0)

    assert blocks_new_buy(within, config) is False


def test_daily_loss_kill_switch_only_gates_buys_not_risk_exits() -> None:
    # The kill switch is a BUY gate only. A SELL/risk exit for a breaching
    # position is decided by evaluate_position_risk and is never suppressed
    # by daily-loss state.
    breached = DailyLossState(realized_loss=600000.0, threshold=500000.0)
    exit_decision = evaluate_position_risk(_position(70000.0), Money(60000.0, "KRW"), _config())

    assert blocks_new_buy(breached, _config()) is True
    assert exit_decision.action is RiskAction.SELL
    assert exit_decision.reason == "stop_loss"


def test_risk_import_has_no_forbidden_module_side_effects() -> None:
    before_import = set(sys.modules)
    importlib.import_module("trading_bot.risk")

    loaded = set(sys.modules) - before_import
    for prefix in FORBIDDEN_MODULE_PREFIXES:
        assert prefix not in loaded
    forbidden_local = [
        name
        for name in loaded
        if name.startswith("trading_bot.")
        and any(fragment in name for fragment in FORBIDDEN_LOCAL_MODULE_FRAGMENTS)
    ]
    assert forbidden_local == []
