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


# ---------------------------------------------------------------------------
# Plan 02-03, Task 2: dry-run side-effect gate + audit chain (EXEC-05).
# ---------------------------------------------------------------------------

from trading_bot.mock_broker import MockBroker  # noqa: E402


def _broker_snapshot(broker: MockBroker, tickers) -> dict:
    return {
        "cash": broker.cash.amount,
        "positions": {t.value: broker.get_position(t) for t in tickers},
        "history": list(broker.order_history),
    }


def test_dry_run_skips_broker_place_order_and_logs_intent() -> None:
    broker = MockBroker(cash=Money(10_000_000.0, "KRW"))
    before = _broker_snapshot(broker, [TICKER])

    result = execute_signal_cycle(
        raw_signal=_signal("BUY", 0.95),
        ticker=TICKER,
        current_price=Money(70000.0, "KRW"),
        available_cash=10_000_000.0,
        broker=broker,
        execution_config=_exec_config(cash_fraction=0.1, max_position_value=5_000_000.0),
        risk_config=_risk_config(),
        daily_loss_state=_no_loss(),
        dry_run=True,
    )

    after = _broker_snapshot(broker, [TICKER])

    # Would-be order is computed and logged, but never placed.
    assert result.action is ExecutionAction.BUY
    assert result.order is not None
    assert result.order.side is OrderSide.BUY
    assert result.broker_order_id is None
    assert result.audit is not None
    assert result.audit.dry_run is True
    assert result.audit.broker_order_id is None
    # Zero mutation: cash, positions, and order history are all unchanged.
    assert after == before
    assert broker.order_history == []


def test_dry_run_leaves_mock_broker_state_unchanged_for_sell() -> None:
    held = Position(ticker=TICKER, quantity=7, average_price=Money(70000.0, "KRW"))
    broker = MockBroker(cash=Money(0.0, "KRW"), positions=[held])
    before = _broker_snapshot(broker, [TICKER])

    result = execute_signal_cycle(
        raw_signal=_signal("SELL", 0.95),
        ticker=TICKER,
        current_price=Money(72000.0, "KRW"),  # within risk bounds, LLM SELL
        available_cash=0.0,
        broker=broker,
        execution_config=_exec_config(),
        risk_config=_risk_config(),
        daily_loss_state=_no_loss(),
        dry_run=True,
    )

    after = _broker_snapshot(broker, [TICKER])

    assert result.action is ExecutionAction.SELL
    assert result.order is not None
    assert result.broker_order_id is None
    assert after == before
    assert broker.order_history == []


def test_dry_run_risk_exit_records_override_and_places_nothing() -> None:
    held = Position(ticker=TICKER, quantity=5, average_price=Money(70000.0, "KRW"))
    broker = MockBroker(cash=Money(0.0, "KRW"), positions=[held])
    before = _broker_snapshot(broker, [TICKER])

    result = execute_signal_cycle(
        raw_signal=_signal("BUY", 0.99),  # LLM BUY; risk must override
        ticker=TICKER,
        current_price=Money(60000.0, "KRW"),  # -14% -> stop-loss
        available_cash=10_000_000.0,
        broker=broker,
        execution_config=_exec_config(),
        risk_config=_risk_config(),
        daily_loss_state=_no_loss(),
        dry_run=True,
    )

    after = _broker_snapshot(broker, [TICKER])

    assert result.action is ExecutionAction.SELL
    assert result.risk_override is True
    assert result.broker_order_id is None
    assert result.audit is not None
    assert result.audit.dry_run is True
    assert result.audit.risk_override is True
    assert "stop_loss" in result.audit.override_reason
    assert after == before
    assert broker.order_history == []


def test_live_run_places_buy_and_mutates_only_via_place_order() -> None:
    broker = MockBroker(cash=Money(10_000_000.0, "KRW"))

    result = execute_signal_cycle(
        raw_signal=_signal("BUY", 0.95),
        ticker=TICKER,
        current_price=Money(70000.0, "KRW"),
        available_cash=10_000_000.0,
        broker=broker,
        execution_config=_exec_config(cash_fraction=0.1, max_position_value=5_000_000.0),
        risk_config=_risk_config(),
        daily_loss_state=_no_loss(),
        dry_run=False,
    )

    assert result.action is ExecutionAction.BUY
    assert result.order is not None
    assert result.broker_order_id == "MOCK-1"
    assert result.audit is not None
    assert result.audit.dry_run is False
    assert result.audit.broker_order_id == "MOCK-1"
    # Broker state mutated only through place_order.
    position = broker.get_position(TICKER)
    assert position is not None
    assert position.quantity == result.order.quantity
    assert broker.order_history == [result.order]
    # 10% of 10,000,000 = 1,000,000 budget capped at 5,000,000 -> 14 shares.
    assert result.order.quantity == 14
    assert broker.cash.amount == pytest.approx(10_000_000.0 - 14 * 70000.0)


def test_live_run_hold_places_no_order() -> None:
    broker = MockBroker(cash=Money(10_000_000.0, "KRW"))

    result = execute_signal_cycle(
        raw_signal=_signal("HOLD", 0.99),
        ticker=TICKER,
        current_price=Money(70000.0, "KRW"),
        available_cash=10_000_000.0,
        broker=broker,
        execution_config=_exec_config(),
        risk_config=_risk_config(),
        daily_loss_state=_no_loss(),
        dry_run=False,
    )

    assert result.action is ExecutionAction.HOLD
    assert result.order is None
    assert result.broker_order_id is None
    assert broker.order_history == []


# ---------------------------------------------------------------------------
# Plan 02-03, Task 3: full mock-safe Phase 2 chain, parse -> risk -> execute
# -> log, covering every Phase 2 requirement ID against hand-written signals.
# ---------------------------------------------------------------------------


def test_integration_exec_01_valid_buy_signal_produces_mock_buy() -> None:
    """EXEC-01: a valid BUY at/above threshold produces a live mock BUY."""
    broker = MockBroker(cash=Money(10_000_000.0, "KRW"))

    result = execute_signal_cycle(
        raw_signal=_signal("BUY", 0.8),  # exactly at threshold
        ticker=TICKER,
        current_price=Money(70000.0, "KRW"),
        available_cash=10_000_000.0,
        broker=broker,
        execution_config=_exec_config(cash_fraction=0.1, max_position_value=5_000_000.0),
        risk_config=_risk_config(),
        daily_loss_state=_no_loss(),
        dry_run=False,
    )

    assert result.action is ExecutionAction.BUY
    assert result.broker_order_id == "MOCK-1"
    assert broker.get_position(TICKER) is not None


def test_integration_exec_01_below_threshold_buy_does_not_trade() -> None:
    """EXEC-01: a BUY below threshold becomes HOLD and places nothing."""
    broker = MockBroker(cash=Money(10_000_000.0, "KRW"))

    result = execute_signal_cycle(
        raw_signal=_signal("BUY", 0.79),
        ticker=TICKER,
        current_price=Money(70000.0, "KRW"),
        available_cash=10_000_000.0,
        broker=broker,
        execution_config=_exec_config(),
        risk_config=_risk_config(),
        daily_loss_state=_no_loss(),
        dry_run=False,
    )

    assert result.action is ExecutionAction.HOLD
    assert broker.get_position(TICKER) is None
    assert broker.order_history == []


def test_integration_exec_02_buy_sizing_respects_percent_and_cap() -> None:
    """EXEC-02: BUY quantity uses cash fraction capped by max position value."""
    broker = MockBroker(cash=Money(10_000_000.0, "KRW"))

    result = execute_signal_cycle(
        raw_signal=_signal("BUY", 0.95),
        ticker=TICKER,
        current_price=Money(70000.0, "KRW"),
        available_cash=10_000_000.0,
        broker=broker,
        # Cap budget at 200,000 -> 200,000 // 70000 = 2 shares.
        execution_config=_exec_config(cash_fraction=0.1, max_position_value=200_000.0),
        risk_config=_risk_config(),
        daily_loss_state=_no_loss(),
        dry_run=False,
    )

    assert result.action is ExecutionAction.BUY
    assert result.order is not None
    assert result.order.quantity == 2
    position = broker.get_position(TICKER)
    assert position is not None and position.quantity == 2


def test_integration_exec_03_held_position_sell_produces_mock_sell() -> None:
    """EXEC-03: a SELL at/above threshold on a held position sells in full."""
    held = Position(ticker=TICKER, quantity=6, average_price=Money(70000.0, "KRW"))
    broker = MockBroker(cash=Money(0.0, "KRW"), positions=[held])

    result = execute_signal_cycle(
        raw_signal=_signal("SELL", 0.9),
        ticker=TICKER,
        current_price=Money(72000.0, "KRW"),  # +2.8%: within risk bounds
        available_cash=0.0,
        broker=broker,
        execution_config=_exec_config(),
        risk_config=_risk_config(),
        daily_loss_state=_no_loss(),
        dry_run=False,
    )

    assert result.action is ExecutionAction.SELL
    assert result.order is not None and result.order.quantity == 6
    assert broker.get_position(TICKER) is None  # fully closed
    assert broker.cash.amount == pytest.approx(6 * 72000.0)


def test_integration_exec_03_sell_without_position_does_not_trade() -> None:
    """EXEC-03: a SELL with no held position becomes HOLD."""
    broker = MockBroker(cash=Money(0.0, "KRW"))

    result = execute_signal_cycle(
        raw_signal=_signal("SELL", 0.99),
        ticker=TICKER,
        current_price=Money(72000.0, "KRW"),
        available_cash=0.0,
        broker=broker,
        execution_config=_exec_config(),
        risk_config=_risk_config(),
        daily_loss_state=_no_loss(),
        dry_run=False,
    )

    assert result.action is ExecutionAction.HOLD
    assert broker.order_history == []


def test_integration_malformed_signal_becomes_hold_no_trade() -> None:
    """EXEC-01/D-01: malformed input fails closed to HOLD with no place_order."""
    broker = MockBroker(cash=Money(10_000_000.0, "KRW"))

    result = execute_signal_cycle(
        raw_signal='{"decision": "BUY", "confidence": "high"}',  # bad confidence
        ticker=TICKER,
        current_price=Money(70000.0, "KRW"),
        available_cash=10_000_000.0,
        broker=broker,
        execution_config=_exec_config(),
        risk_config=_risk_config(),
        daily_loss_state=_no_loss(),
        dry_run=False,
    )

    assert result.action is ExecutionAction.HOLD
    assert result.order is None
    assert result.audit is not None
    assert result.audit.parse_error is not None
    assert broker.order_history == []


def test_integration_risk_01_stop_loss_sells_without_llm_sell() -> None:
    """RISK-01: a stop-loss breach sells a held position with no LLM SELL."""
    held = Position(ticker=TICKER, quantity=5, average_price=Money(70000.0, "KRW"))
    broker = MockBroker(cash=Money(0.0, "KRW"), positions=[held])

    result = execute_signal_cycle(
        raw_signal=_signal("HOLD", 0.99),  # LLM does NOT say SELL
        ticker=TICKER,
        current_price=Money(60000.0, "KRW"),  # -14% -> stop-loss
        available_cash=0.0,
        broker=broker,
        execution_config=_exec_config(),
        risk_config=_risk_config(),
        daily_loss_state=_no_loss(),
        dry_run=False,
    )

    assert result.action is ExecutionAction.SELL
    assert result.risk_override is True
    assert "stop_loss" in (result.override_reason or "")
    assert result.broker_order_id == "MOCK-1"
    assert broker.get_position(TICKER) is None


def test_integration_risk_02_risk_suppresses_conflicting_llm_buy() -> None:
    """RISK-02/D-07: a take-profit exit overrides a same-ticker LLM BUY, logged."""
    held = Position(ticker=TICKER, quantity=5, average_price=Money(70000.0, "KRW"))
    broker = MockBroker(cash=Money(10_000_000.0, "KRW"), positions=[held])

    result = execute_signal_cycle(
        raw_signal=_signal("BUY", 0.99),  # LLM wants to BUY more
        ticker=TICKER,
        current_price=Money(80000.0, "KRW"),  # +14% -> take-profit
        available_cash=10_000_000.0,
        broker=broker,
        execution_config=_exec_config(),
        risk_config=_risk_config(),
        daily_loss_state=_no_loss(),
        dry_run=False,
    )

    assert result.action is ExecutionAction.SELL  # BUY suppressed
    assert result.risk_override is True
    assert result.audit is not None
    assert result.audit.risk_override is True
    assert "take_profit" in result.audit.override_reason
    assert result.audit.parsed_decision == "BUY"  # records the suppressed LLM action
    assert broker.get_position(TICKER) is None


def test_integration_risk_03_daily_loss_blocks_buy_allows_exits() -> None:
    """RISK-03/D-08: daily-loss breach blocks new BUY but allows SELL exits."""
    breached = DailyLossState(realized_loss=600000.0, threshold=500000.0)

    buy_broker = MockBroker(cash=Money(10_000_000.0, "KRW"))
    blocked_buy = execute_signal_cycle(
        raw_signal=_signal("BUY", 0.99),
        ticker=TICKER,
        current_price=Money(70000.0, "KRW"),
        available_cash=10_000_000.0,
        broker=buy_broker,
        execution_config=_exec_config(),
        risk_config=_risk_config(),
        daily_loss_state=breached,
        dry_run=False,
    )

    held = Position(ticker=TICKER, quantity=4, average_price=Money(70000.0, "KRW"))
    sell_broker = MockBroker(cash=Money(0.0, "KRW"), positions=[held])
    allowed_sell = execute_signal_cycle(
        raw_signal=_signal("SELL", 0.99),
        ticker=TICKER,
        current_price=Money(71000.0, "KRW"),  # within risk bounds
        available_cash=0.0,
        broker=sell_broker,
        execution_config=_exec_config(),
        risk_config=_risk_config(),
        daily_loss_state=breached,
        dry_run=False,
    )

    assert blocked_buy.action is ExecutionAction.HOLD
    assert buy_broker.order_history == []
    assert allowed_sell.action is ExecutionAction.SELL
    assert sell_broker.get_position(TICKER) is None


def test_integration_exec_05_dry_run_vs_live_same_decision_different_effect() -> None:
    """EXEC-05: identical inputs decide the same order; only live mutates state."""
    common = dict(
        raw_signal=_signal("BUY", 0.95),
        ticker=TICKER,
        current_price=Money(70000.0, "KRW"),
        available_cash=10_000_000.0,
        execution_config=_exec_config(cash_fraction=0.1, max_position_value=5_000_000.0),
        risk_config=_risk_config(),
        daily_loss_state=_no_loss(),
    )

    dry_broker = MockBroker(cash=Money(10_000_000.0, "KRW"))
    dry = execute_signal_cycle(broker=dry_broker, dry_run=True, **common)

    live_broker = MockBroker(cash=Money(10_000_000.0, "KRW"))
    live = execute_signal_cycle(broker=live_broker, dry_run=False, **common)

    # Same computed order intent.
    assert dry.order == live.order
    # Dry run: no place_order, no mutation.
    assert dry.broker_order_id is None
    assert dry_broker.order_history == []
    assert dry_broker.get_position(TICKER) is None
    assert dry_broker.cash.amount == pytest.approx(10_000_000.0)
    # Live run: placed and mutated.
    assert live.broker_order_id == "MOCK-1"
    assert live_broker.order_history == [live.order]
    assert live_broker.get_position(TICKER) is not None


def test_phase2_core_modules_import_no_forbidden_dependencies() -> None:
    """T-02-10: parser, risk, execution, mock broker stay adapter/external-free."""
    core_modules = (
        "trading_bot.signal_parser",
        "trading_bot.risk",
        "trading_bot.execution",
        "trading_bot.mock_broker",
    )

    before_import = set(sys.modules)
    for name in core_modules:
        importlib.import_module(name)
    loaded = set(sys.modules) - before_import

    for prefix in FORBIDDEN_MODULE_PREFIXES:
        assert prefix not in loaded, f"{prefix} leaked into Phase 2 core imports"

    forbidden_local = [
        name
        for name in loaded
        if name.startswith("trading_bot.")
        and any(fragment in name for fragment in FORBIDDEN_LOCAL_MODULE_FRAGMENTS)
    ]
    assert forbidden_local == []
