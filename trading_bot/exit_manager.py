"""Broker-authoritative exit lifecycle shared by daily and intraday decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from trading_bot.portfolio import PortfolioOrder, PortfolioSnapshot
from trading_bot.risk import RiskAction, RiskDecision


class ExitTriggerKind(StrEnum):
    DAILY_LLM_SELL = "DAILY_LLM_SELL"
    INTRADAY_STOP_LOSS = "INTRADAY_STOP_LOSS"
    INTRADAY_TAKE_PROFIT = "INTRADAY_TAKE_PROFIT"


@dataclass(frozen=True)
class ExitTrigger:
    kind: ExitTriggerKind
    ticker: str
    cycle_id: str
    reason_code: str

    def __post_init__(self) -> None:
        if not self.ticker or not self.cycle_id:
            raise ValueError("exit trigger requires ticker and cycle identity")


class ExitDisposition(StrEnum):
    HOLD = "HOLD"
    SUBMIT = "SUBMIT"
    RECONCILE_ONLY = "RECONCILE_ONLY"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class ExitResult:
    disposition: ExitDisposition
    ticker: str
    quantity: int
    reason_code: str
    trigger: ExitTrigger | None = None
    broker_subject_id: str | None = None


def evaluate_daily_exit_trigger(
    *, ticker: str, cycle_id: str, decision: str, confidence: float, threshold: float
) -> ExitTrigger | None:
    """Reduce a qualified strict LLM SELL to the common exit trigger."""

    if str(decision).upper() != "SELL" or confidence < threshold:
        return None
    return ExitTrigger(
        ExitTriggerKind.DAILY_LLM_SELL,
        ticker,
        cycle_id,
        "DAILY_LLM_SELL",
    )


def evaluate_risk_exit_trigger(
    *, ticker: str, cycle_id: str, decision: RiskDecision
) -> ExitTrigger | None:
    """Map the existing pure stop/take decision without copying its formulas."""

    if decision.action is not RiskAction.SELL:
        return None
    kinds = {
        "stop_loss": ExitTriggerKind.INTRADAY_STOP_LOSS,
        "take_profit": ExitTriggerKind.INTRADAY_TAKE_PROFIT,
    }
    kind = kinds.get(decision.reason)
    if kind is None:
        return None
    return ExitTrigger(kind, ticker, cycle_id, kind.value)


def _active_sell(snapshot: PortfolioSnapshot, ticker: str) -> PortfolioOrder | None:
    return next(
        (
            order
            for order in snapshot.orders
            if order.ticker == ticker
            and order.side == "SELL"
            and order.status in {"OPEN", "PARTIAL"}
        ),
        None,
    )


def blocks_new_buy_for_ticker(snapshot: PortfolioSnapshot, ticker: str) -> bool:
    """An observed OPEN/PARTIAL SELL freezes BUY as well as another SELL."""

    return _active_sell(snapshot, ticker) is not None


def evaluate_exit_candidate(
    trigger: ExitTrigger | None,
    snapshot: PortfolioSnapshot,
    *,
    latest_terminal_cycle_id: str | None = None,
) -> ExitResult:
    """Reduce current trigger and complete broker truth to a no-oversell action."""

    ticker = trigger.ticker if trigger is not None else ""
    if trigger is None:
        return ExitResult(ExitDisposition.HOLD, ticker, 0, "NO_ACTIVE_TRIGGER")
    if not snapshot.mutation_capable:
        return ExitResult(
            ExitDisposition.BLOCKED, ticker, 0, "ACCOUNT_DATA_INCOMPLETE", trigger
        )
    active = _active_sell(snapshot, ticker)
    if active is not None:
        return ExitResult(
            ExitDisposition.RECONCILE_ONLY,
            ticker,
            0,
            "OPEN_SELL_REQUIRES_RECONCILIATION",
            trigger,
            active.order_id,
        )
    if latest_terminal_cycle_id == trigger.cycle_id:
        return ExitResult(
            ExitDisposition.BLOCKED,
            ticker,
            0,
            "INDEPENDENT_CYCLE_REQUIRED",
            trigger,
        )
    holding = next((item for item in snapshot.holdings if item.ticker == ticker), None)
    if holding is None or holding.orderable_quantity <= 0:
        return ExitResult(
            ExitDisposition.HOLD, ticker, 0, "NO_ORDERABLE_HOLDING", trigger
        )
    return ExitResult(
        ExitDisposition.SUBMIT,
        ticker,
        holding.orderable_quantity,
        "EXIT_READY",
        trigger,
    )
