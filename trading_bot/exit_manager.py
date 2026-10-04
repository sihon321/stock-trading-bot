"""Broker-authoritative exit lifecycle shared by daily and intraday decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Callable

from trading_bot.portfolio import PortfolioOrder, PortfolioSnapshot
from trading_bot.domain import Money, Order, OrderSide, Ticker
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
    entry_price: float | None = None
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None

    def __post_init__(self) -> None:
        if not self.ticker or not self.cycle_id:
            raise ValueError("exit trigger requires ticker and cycle identity")

    def remains_actionable(
        self, snapshot: PortfolioSnapshot, current_price: Money
    ) -> bool:
        """Re-prove a deterministic risk decision using fresh broker truth."""

        del snapshot  # quantity/open-order gates remain at the broker boundary.
        if self.kind is ExitTriggerKind.DAILY_LLM_SELL:
            return True
        if (
            self.entry_price is None
            or self.stop_loss_pct is None
            or self.take_profit_pct is None
            or self.entry_price <= 0
            or current_price.amount <= 0
        ):
            return False
        if self.kind is ExitTriggerKind.INTRADAY_STOP_LOSS:
            return current_price.amount <= self.entry_price * (1 - abs(self.stop_loss_pct))
        if self.kind is ExitTriggerKind.INTRADAY_TAKE_PROFIT:
            return current_price.amount >= self.entry_price * (1 + abs(self.take_profit_pct))
        return False


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

    def revalidate_refreshed_truth(
        self, snapshot: PortfolioSnapshot, current_price: Money
    ) -> bool:
        return self.trigger is not None and self.trigger.remains_actionable(
            snapshot, current_price
        )


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
    *, ticker: str, cycle_id: str, decision: RiskDecision,
    entry_price: float | None = None,
    stop_loss_pct: float | None = None,
    take_profit_pct: float | None = None,
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
    return ExitTrigger(
        kind, ticker, cycle_id, kind.value,
        entry_price, stop_loss_pct, take_profit_pct,
    )


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


def submit_exit(
    result: ExitResult,
    *,
    broker: object,
    limit_price: Money,
    portfolio_refresh: object,
    lease_guard: object,
    cycle_snapshot_id: str,
    origin_run_id: str,
    trigger_revalidator: Callable[[PortfolioSnapshot, Money], bool] | None = None,
    submission_authority: object = None,
) -> str | None:
    """Submit only a current ``SUBMIT`` result through the KIS boundary."""

    if result.disposition is not ExitDisposition.SUBMIT or result.quantity <= 0:
        return None
    if submission_authority is not None:
        from .submission_authority import SubmissionAuthority
        if (type(submission_authority) is not SubmissionAuthority
            or getattr(broker,'_submission_authority',None) is not submission_authority):
            raise ValueError('exit final authority binding mismatch')
    order = Order(
        Ticker(result.ticker),
        OrderSide.SELL,
        result.quantity,
        limit_price,
    )
    place_order = getattr(broker, "place_order")
    return str(
        place_order(
            order,
            order_intent_id=f"{origin_run_id}:{result.ticker}:SELL",
            origin_run_id=origin_run_id,
            observer_run_id=origin_run_id,
            portfolio_refresh=portfolio_refresh,
            lease_guard=lease_guard,
            cycle_snapshot_id=cycle_snapshot_id,
            trigger_revalidator=(
                trigger_revalidator
                if trigger_revalidator is not None
                else result.revalidate_refreshed_truth
            ),
        )
    )
