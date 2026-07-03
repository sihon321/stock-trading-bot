"""Deterministic execution rules with risk precedence over LLM actions.

This module owns the parse -> risk -> execute decision core for Phase 2. It is
adapter-free: it consumes :class:`~trading_bot.ports.Broker` only as a Protocol
dependency (to read positions) and never calls ``Broker.place_order`` — the
side-effect / dry-run boundary is completed in Plan 02-03.

Ordering guarantees (safety-critical):
    1. Parser failure is caught here and mapped to HOLD / no-order (D-01).
    2. Risk is evaluated before any LLM-derived action; a risk exit suppresses a
       conflicting same-ticker LLM action and records an override (D-07/RISK-02).
    3. The daily-loss kill switch blocks new BUYs while still allowing SELLs and
       risk exits (D-08/RISK-03).
    4. BUY/SELL thresholds and sizing are deterministic execution rules
       (EXEC-01/02/03, D-05/D-06).
    5. The dry-run gate lives here, *before* ``Broker.place_order`` (EXEC-05).
       A dry run computes and logs the would-be order but performs zero
       ``place_order`` calls and zero broker mutation; a live run places the
       order and records the returned broker order ID for audit. The gate is
       never delegated to the broker, so tests can prove no side effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from trading_bot.domain import Decision, Money, Order, OrderSide, Position, Ticker
from trading_bot.ports import Broker
from trading_bot.risk import (
    DailyLossState,
    RiskAction,
    RiskConfig,
    blocks_new_buy,
    evaluate_position_risk,
)
from trading_bot.signal_parser import SignalParseError, parse_signal


class ExecutionAction(str, Enum):
    """Final action produced by the execution core."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass(frozen=True)
class ExecutionConfig:
    """Deterministic execution thresholds and sizing bounds (D-05/D-06)."""

    buy_confidence_threshold: float
    sell_confidence_threshold: float
    buy_cash_fraction: float
    max_position_value: float


@dataclass(frozen=True)
class CycleAuditEvent:
    """Machine-checkable record of a single decision cycle (D-07 repudiation).

    Captures parser diagnostics, whether risk overrode the LLM action, and the
    override reason so an operator can see *why* an LLM action was suppressed.
    """

    ticker: str
    parsed_decision: Optional[str]
    parse_error: Optional[str]
    risk_override: bool
    override_reason: str
    final_action: str
    order_reason: str
    dry_run: bool = True
    broker_order_id: Optional[str] = None


@dataclass(frozen=True)
class ExecutionResult:
    """Immutable outcome of a decision cycle.

    ``broker_order_id`` is populated only on a live (non-dry-run) cycle that
    actually placed an order via ``Broker.place_order``; it is ``None`` for every
    dry run and for any cycle that produced no order.
    """

    action: ExecutionAction
    order: Optional[Order]
    reason: str
    risk_override: bool = False
    override_reason: Optional[str] = None
    audit: Optional[CycleAuditEvent] = None
    broker_order_id: Optional[str] = None
    confidence: Optional[float] = None


def evaluate_signal_action(
    parsed_decision: str,
    confidence: float,
    position: Optional[Position],
    config: ExecutionConfig,
) -> ExecutionResult:
    """Map a validated signal to a qualified execution action.

    BUY requires ``Decision.BUY`` and confidence at/above the BUY threshold.
    SELL requires ``Decision.SELL``, confidence at/above the SELL threshold, and
    an existing held position. Anything else is HOLD / no-order.
    """

    if parsed_decision == Decision.BUY.value:
        if confidence >= config.buy_confidence_threshold:
            return ExecutionResult(ExecutionAction.BUY, None, "buy signal qualified")
        return ExecutionResult(
            ExecutionAction.HOLD, None, "buy confidence below threshold"
        )

    if parsed_decision == Decision.SELL.value:
        if position is None or position.quantity <= 0:
            return ExecutionResult(
                ExecutionAction.HOLD, None, "sell without held position"
            )
        if confidence >= config.sell_confidence_threshold:
            return ExecutionResult(ExecutionAction.SELL, None, "sell signal qualified")
        return ExecutionResult(
            ExecutionAction.HOLD, None, "sell confidence below threshold"
        )

    return ExecutionResult(ExecutionAction.HOLD, None, "no qualified action")


def build_order_intent(
    action: ExecutionAction,
    ticker: Ticker,
    current_price: Money,
    available_cash: float,
    position: Optional[Position],
    config: ExecutionConfig,
) -> Optional[Order]:
    """Construct an order intent for a qualified action, or None.

    BUY quantity = ``floor(min(cash * fraction, max_position_value) / price)``
    (EXEC-02/D-06); a non-positive price or zero quantity yields no order. SELL
    exits the full held quantity.
    """

    if action is ExecutionAction.BUY:
        price = current_price.amount
        if price <= 0:
            return None
        budget = min(available_cash * config.buy_cash_fraction, config.max_position_value)
        quantity = int(budget // price)
        if quantity <= 0:
            return None
        return Order(
            ticker=ticker,
            side=OrderSide.BUY,
            quantity=quantity,
            limit_price=current_price,
        )

    if action is ExecutionAction.SELL:
        if position is None or position.quantity <= 0:
            return None
        return Order(
            ticker=ticker,
            side=OrderSide.SELL,
            quantity=position.quantity,
            limit_price=current_price,
        )

    return None


def _finalize_cycle(
    *,
    broker: Broker,
    dry_run: bool,
    action: ExecutionAction,
    order: Optional[Order],
    reason: str,
    ticker: Ticker,
    parsed_decision: Optional[str],
    parse_error: Optional[str],
    risk_override: bool,
    override_reason: str,
    order_reason: str,
    confidence: Optional[float] = None,
) -> ExecutionResult:
    """Apply the dry-run gate, then build the audit event and result (EXEC-05).

    This is the *only* place ``Broker.place_order`` is invoked. On a dry run it is
    never called and the broker is never mutated; the would-be order is still
    recorded in the audit event. On a live run, an existing order intent is placed
    and the returned broker order ID is recorded.
    """

    broker_order_id: Optional[str] = None
    if not dry_run and order is not None:
        broker_order_id = broker.place_order(order)

    audit = CycleAuditEvent(
        ticker=ticker.value,
        parsed_decision=parsed_decision,
        parse_error=parse_error,
        risk_override=risk_override,
        override_reason=override_reason,
        final_action=action.value,
        order_reason=order_reason,
        dry_run=dry_run,
        broker_order_id=broker_order_id,
    )
    return ExecutionResult(
        action,
        order,
        reason,
        risk_override=risk_override,
        override_reason=override_reason or None,
        audit=audit,
        broker_order_id=broker_order_id,
        confidence=confidence,
    )


def execute_signal_cycle(
    raw_signal: str,
    ticker: Ticker,
    current_price: Money,
    available_cash: float,
    broker: Broker,
    execution_config: ExecutionConfig,
    risk_config: RiskConfig,
    daily_loss_state: DailyLossState,
    dry_run: bool = True,
) -> ExecutionResult:
    """Run one parse -> risk -> execute -> (gated) place decision cycle.

    ``broker`` is read via ``get_position`` for decision inputs. ``place_order`` is
    invoked exactly once, and only when ``dry_run`` is ``False`` and a valid order
    intent exists — the gate lives here, before the broker, so a dry run performs
    zero ``place_order`` calls and zero broker mutation (EXEC-05). ``dry_run``
    defaults to ``True`` (safety-first, matching ``Settings.dry_run``).

    Returns an :class:`ExecutionResult` with an attached :class:`CycleAuditEvent`
    recording the final action, would-be order, dry-run status, parse diagnostics,
    no-order reason, risk-override evidence, and the broker order ID when placed.
    """

    position = broker.get_position(ticker)

    # 1. Parse fail-safe: malformed input becomes HOLD / no-order (D-01).
    try:
        parsed = parse_signal(raw_signal)
    except SignalParseError as exc:
        return _finalize_cycle(
            broker=broker,
            dry_run=dry_run,
            action=ExecutionAction.HOLD,
            order=None,
            reason="invalid signal payload; parser failed",
            ticker=ticker,
            parsed_decision=None,
            parse_error=str(exc),
            risk_override=False,
            override_reason="",
            order_reason="invalid signal payload",
        )

    parsed_decision = parsed.signal.decision.value
    confidence = parsed.signal.confidence

    # 2. Risk first: a risk exit overrides any same-ticker LLM action (D-07).
    risk = evaluate_position_risk(position, current_price, risk_config)
    if risk.action is RiskAction.SELL:
        order = build_order_intent(
            ExecutionAction.SELL, ticker, current_price, available_cash, position,
            execution_config,
        )
        return _finalize_cycle(
            broker=broker,
            dry_run=dry_run,
            action=ExecutionAction.SELL,
            order=order,
            reason=f"risk override: {risk.reason}",
            ticker=ticker,
            parsed_decision=parsed_decision,
            parse_error=None,
            risk_override=True,
            override_reason=risk.reason,
            order_reason=f"risk exit ({risk.reason}) overrides LLM {parsed_decision}",
            confidence=confidence,
        )

    # 3. LLM action evaluation, gated by the daily-loss kill switch (D-08).
    action_result = evaluate_signal_action(
        parsed_decision, confidence, position, execution_config
    )

    if action_result.action is ExecutionAction.BUY and blocks_new_buy(
        daily_loss_state, risk_config
    ):
        return _finalize_cycle(
            broker=broker,
            dry_run=dry_run,
            action=ExecutionAction.HOLD,
            order=None,
            reason="daily_loss kill switch blocks new BUY",
            ticker=ticker,
            parsed_decision=parsed_decision,
            parse_error=None,
            risk_override=False,
            override_reason="",
            order_reason="daily_loss kill switch blocks new BUY",
            confidence=confidence,
        )

    # 4. Build the order intent for the qualified action.
    order = build_order_intent(
        action_result.action, ticker, current_price, available_cash, position,
        execution_config,
    )
    final_action = action_result.action
    order_reason = action_result.reason
    if order is None and final_action is not ExecutionAction.HOLD:
        # Qualified action produced no valid order (e.g. sizing rounded to zero).
        final_action = ExecutionAction.HOLD
        order_reason = f"{action_result.reason}; no valid order quantity"

    return _finalize_cycle(
        broker=broker,
        dry_run=dry_run,
        action=final_action,
        order=order,
        reason=order_reason,
        ticker=ticker,
        parsed_decision=parsed_decision,
        parse_error=None,
        risk_override=False,
        override_reason="",
        order_reason=order_reason,
        confidence=confidence,
    )
