import dataclasses
import importlib
import json
import sys
from typing import Optional

import pytest

from trading_bot.domain import Money, Order, OrderSide, Position, Ticker
from trading_bot.execution import (
    CycleAuditEvent,
    ExecutionAction,
    ExecutionConfig,
    ExecutionResult,
    build_order_intent,
    evaluate_signal_action,
    execute_signal_cycle,
)
from trading_bot.risk import DailyLossState, RiskConfig


FORBIDDEN_MODULE_PREFIXES = (
    "anthropic",
    "openai",
    "pykrx",
    "requests",
    "httpx",
)

FORBIDDEN_LOCAL_MODULE_FRAGMENTS = (
    "adapter",
    "kis",
    "naver",
    "scrap",
)


TICKER = Ticker("005930")


class RecordingBroker:
    """Structural Broker fake that fails loudly if place_order is called.

    Plan 02-02 must not mutate the broker; that boundary lands in Plan 02-03.
    """

    def __init__(self, position: Optional[Position] = None) -> None:
        self._position = position
        self.placed: list = []

    def get_position(self, ticker: Ticker) -> Optional[Position]:
        return self._position

    def place_order(self, order: Order) -> str:  # pragma: no cover - must not run
        self.placed.append(order)
        raise AssertionError("place_order must not be called in Plan 02-02")


def _exec_config(
    buy_threshold: float = 0.8,
    sell_threshold: float = 0.8,
    cash_fraction: float = 0.1,
    max_position_value: float = 1_000_000.0,
) -> ExecutionConfig:
    return ExecutionConfig(
        buy_confidence_threshold=buy_threshold,
        sell_confidence_threshold=sell_threshold,
        buy_cash_fraction=cash_fraction,
        max_position_value=max_position_value,
    )


def _risk_config() -> RiskConfig:
    return RiskConfig(stop_loss_pct=0.05, take_profit_pct=0.10)


def _no_loss() -> DailyLossState:
    return DailyLossState(realized_loss=0.0, threshold=500000.0)


def _signal(decision: str, confidence: float, reason: str = "test reason") -> str:
    return json.dumps({"decision": decision, "confidence": confidence, "reason": reason})


def test_execution_result_and_config_are_frozen_dataclasses() -> None:
    result = ExecutionResult(action=ExecutionAction.HOLD, order=None, reason="test")

    assert dataclasses.is_dataclass(result)
    assert isinstance(ExecutionAction.BUY, str)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.reason = "mutated"  # type: ignore[misc]


def test_buy_requires_buy_decision_and_threshold() -> None:
    config = _exec_config(buy_threshold=0.8)

    at_threshold = evaluate_signal_action(
        parsed_decision="BUY", confidence=0.8, position=None, config=config
    )
    below = evaluate_signal_action(
        parsed_decision="BUY", confidence=0.79, position=None, config=config
    )

    assert at_threshold.action is ExecutionAction.BUY
    assert below.action is ExecutionAction.HOLD


def test_buy_sizing_uses_cash_percent_and_max_cap() -> None:
    # 10% of 10,000,000 = 1,000,000 budget, uncapped -> 1,000,000 // 70000 = 14.
    uncapped = build_order_intent(
        action=ExecutionAction.BUY,
        ticker=TICKER,
        current_price=Money(70000.0, "KRW"),
        available_cash=10_000_000.0,
        position=None,
        config=_exec_config(cash_fraction=0.1, max_position_value=5_000_000.0),
    )
    # Cap budget at 200,000 -> 200,000 // 70000 = 2.
    capped = build_order_intent(
        action=ExecutionAction.BUY,
        ticker=TICKER,
        current_price=Money(70000.0, "KRW"),
        available_cash=10_000_000.0,
        position=None,
        config=_exec_config(cash_fraction=0.1, max_position_value=200_000.0),
    )

    assert uncapped is not None
    assert uncapped.side is OrderSide.BUY
    assert uncapped.quantity == 14
    assert capped is not None
    assert capped.quantity == 2


def test_buy_sizing_zero_or_negative_price_yields_no_order() -> None:
    order = build_order_intent(
        action=ExecutionAction.BUY,
        ticker=TICKER,
        current_price=Money(0.0, "KRW"),
        available_cash=10_000_000.0,
        position=None,
        config=_exec_config(),
    )

    assert order is None


def test_sell_requires_position_and_threshold() -> None:
    config = _exec_config(sell_threshold=0.8)
    held = Position(ticker=TICKER, quantity=5, average_price=Money(70000.0, "KRW"))

    with_position = evaluate_signal_action(
        parsed_decision="SELL", confidence=0.85, position=held, config=config
    )
    without_position = evaluate_signal_action(
        parsed_decision="SELL", confidence=0.85, position=None, config=config
    )
    below_threshold = evaluate_signal_action(
        parsed_decision="SELL", confidence=0.5, position=held, config=config
    )

    assert with_position.action is ExecutionAction.SELL
    assert without_position.action is ExecutionAction.HOLD
    assert below_threshold.action is ExecutionAction.HOLD


def test_sell_order_intent_uses_full_held_quantity() -> None:
    held = Position(ticker=TICKER, quantity=7, average_price=Money(70000.0, "KRW"))

    order = build_order_intent(
        action=ExecutionAction.SELL,
        ticker=TICKER,
        current_price=Money(72000.0, "KRW"),
        available_cash=0.0,
        position=held,
        config=_exec_config(),
    )

    assert order is not None
    assert order.side is OrderSide.SELL
    assert order.quantity == 7


def test_parser_failure_becomes_hold_no_order() -> None:
    broker = RecordingBroker()

    result = execute_signal_cycle(
        raw_signal="{not valid json",
        ticker=TICKER,
        current_price=Money(70000.0, "KRW"),
        available_cash=10_000_000.0,
        broker=broker,
        execution_config=_exec_config(),
        risk_config=_risk_config(),
        daily_loss_state=_no_loss(),
    )

    assert result.action is ExecutionAction.HOLD
    assert result.order is None
    assert "parse" in result.reason.lower() or "invalid" in result.reason.lower()
    assert broker.placed == []


def test_valid_buy_cycle_builds_order_without_placing_it() -> None:
    broker = RecordingBroker(position=None)

    result = execute_signal_cycle(
        raw_signal=_signal("BUY", 0.9),
        ticker=TICKER,
        current_price=Money(70000.0, "KRW"),
        available_cash=10_000_000.0,
        broker=broker,
        execution_config=_exec_config(cash_fraction=0.1, max_position_value=5_000_000.0),
        risk_config=_risk_config(),
        daily_loss_state=_no_loss(),
    )

    assert result.action is ExecutionAction.BUY
    assert result.order is not None
    assert result.order.side is OrderSide.BUY
    assert broker.placed == []


def test_risk_override_suppresses_llm_action() -> None:
    # Held position breaching stop-loss; LLM says BUY. Risk must win.
    held = Position(ticker=TICKER, quantity=5, average_price=Money(70000.0, "KRW"))
    broker = RecordingBroker(position=held)

    result = execute_signal_cycle(
        raw_signal=_signal("BUY", 0.99),
        ticker=TICKER,
        current_price=Money(60000.0, "KRW"),  # -14% -> stop-loss
        available_cash=10_000_000.0,
        broker=broker,
        execution_config=_exec_config(),
        risk_config=_risk_config(),
        daily_loss_state=_no_loss(),
    )

    assert result.action is ExecutionAction.SELL
    assert result.risk_override is True
    assert "stop_loss" in (result.override_reason or "")
    assert isinstance(result.audit, CycleAuditEvent)
    assert result.audit.risk_override is True
    assert "stop_loss" in result.audit.override_reason
    # LLM BUY was suppressed; the resulting order is a risk SELL, not a BUY.
    assert result.order is not None
    assert result.order.side is OrderSide.SELL
    assert broker.placed == []


def test_daily_loss_breach_blocks_buy_but_allows_sell() -> None:
    breached = DailyLossState(realized_loss=600000.0, threshold=500000.0)
    held = Position(ticker=TICKER, quantity=5, average_price=Money(70000.0, "KRW"))

    blocked_buy = execute_signal_cycle(
        raw_signal=_signal("BUY", 0.99),
        ticker=TICKER,
        current_price=Money(70000.0, "KRW"),  # within risk bounds
        available_cash=10_000_000.0,
        broker=RecordingBroker(position=None),
        execution_config=_exec_config(),
        risk_config=_risk_config(),
        daily_loss_state=breached,
    )
    allowed_sell = execute_signal_cycle(
        raw_signal=_signal("SELL", 0.99),
        ticker=TICKER,
        current_price=Money(71000.0, "KRW"),  # within risk bounds
        available_cash=0.0,
        broker=RecordingBroker(position=held),
        execution_config=_exec_config(),
        risk_config=_risk_config(),
        daily_loss_state=breached,
    )

    assert blocked_buy.action is ExecutionAction.HOLD
    assert blocked_buy.order is None
    assert "daily_loss" in blocked_buy.reason or "kill" in blocked_buy.reason.lower()
    assert allowed_sell.action is ExecutionAction.SELL
    assert allowed_sell.order is not None


def test_execution_import_has_no_forbidden_external_or_adapter_side_effects() -> None:
    before_import = set(sys.modules)
    importlib.import_module("trading_bot.execution")

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
