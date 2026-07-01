"""Pure, LLM-independent risk decisions for held positions.

This module owns the rules-based risk net: stop-loss / take-profit exits and the
daily-loss kill switch. Every function is pure — it accepts explicit value-object
inputs and returns a decision object. It never reads settings, calls a broker,
touches the network, logs, or depends on :class:`~trading_bot.domain.LLMSignal`.
Risk decisions are evaluated *before* any LLM-derived action so that a risk exit
can suppress a conflicting same-ticker LLM action (D-07).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from trading_bot.domain import Money, Position


class RiskAction(str, Enum):
    """Machine-checkable risk-net actions."""

    HOLD = "HOLD"
    SELL = "SELL"


@dataclass(frozen=True)
class RiskConfig:
    """Configurable stop-loss / take-profit percentages (D-09).

    Percentages are fractional moves against the position's average price, e.g.
    ``stop_loss_pct=0.05`` exits on a 5% adverse move.
    """

    stop_loss_pct: float
    take_profit_pct: float


@dataclass(frozen=True)
class DailyLossState:
    """Explicit per-cycle daily-loss input for the kill switch (D-08).

    ``realized_loss`` is the loss magnitude accrued so far today; once it reaches
    ``threshold`` the kill switch arms and blocks new BUYs for the rest of the day.
    """

    realized_loss: float
    threshold: float


@dataclass(frozen=True)
class RiskDecision:
    """Immutable risk outcome with a machine-checkable action and reason."""

    action: RiskAction
    reason: str


def evaluate_position_risk(
    position: Optional[Position],
    current_price: Money,
    config: RiskConfig,
) -> RiskDecision:
    """Return a risk decision for a held position, independent of any LLM signal.

    Emits ``SELL`` with reason ``stop_loss`` or ``take_profit`` when the current
    price breaches the configured percentage move against the position's average
    price. Returns ``HOLD`` when there is no position, zero quantity, or a
    non-positive entry/current price (fail-safe: never trade on bad price data).
    """

    if position is None or position.quantity <= 0:
        return RiskDecision(RiskAction.HOLD, "no held position")

    entry = position.average_price.amount
    price = current_price.amount
    if entry <= 0 or price <= 0:
        return RiskDecision(RiskAction.HOLD, "non-positive price input")

    change_pct = (price - entry) / entry
    if change_pct <= -abs(config.stop_loss_pct):
        return RiskDecision(RiskAction.SELL, "stop_loss")
    if change_pct >= abs(config.take_profit_pct):
        return RiskDecision(RiskAction.SELL, "take_profit")
    return RiskDecision(RiskAction.HOLD, "within risk bounds")


def blocks_new_buy(daily_loss_state: DailyLossState, config: RiskConfig) -> bool:
    """Return True when the daily-loss kill switch blocks new BUY actions (D-08).

    The kill switch is a BUY gate only. It never suppresses SELLs or risk exits —
    those are decided by :func:`evaluate_position_risk`. ``config`` is accepted for
    signature symmetry with the rest of the risk net and future thresholds.
    """

    del config  # kill-switch arming depends only on the daily-loss state.
    return daily_loss_state.realized_loss >= daily_loss_state.threshold
