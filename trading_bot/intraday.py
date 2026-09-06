"""Foreground-only, LLM-free intraday position risk monitoring."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, time
from enum import StrEnum
from typing import Any, Callable
from zoneinfo import ZoneInfo

from trading_bot.domain import Money, Position, Ticker
from trading_bot.exit_manager import (
    ExitDisposition,
    ExitResult,
    evaluate_exit_candidate,
    evaluate_risk_exit_trigger,
)
from trading_bot.portfolio import PortfolioSnapshot
from trading_bot.risk import RiskConfig, evaluate_position_risk
from trading_bot.audit_models import (
    OperationalSeverity,
    TransitionNotification,
    TransitionObservation,
)
from trading_bot.mutation_lease import LeaseOwnershipLost, stop_after_ownership_loss


KST = ZoneInfo("Asia/Seoul")


class IntradaySessionPhase(StrEnum):
    PREFLIGHT_READ_ONLY = "PREFLIGHT_READ_ONLY"
    RECOVERY_ONLY = "RECOVERY_ONLY"
    ACTIVE = "ACTIVE"
    RECONCILE_ONLY = "RECONCILE_ONLY"
    STOPPING = "STOPPING"
    TERMINAL = "TERMINAL"


class IntradayIterationOutcome(StrEnum):
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    INTERRUPTED = "INTERRUPTED"
    FAILED = "FAILED"


class TransitionEvidenceError(RuntimeError):
    """Mandatory alert-attempt evidence failed; later mutation is forbidden."""


class TransitionEvidenceGuard:
    """Keep transport fail-soft while latching evidence persistence fail-closed."""

    def __init__(
        self,
        *,
        transport: Callable[[str], object],
        evidence_writer: Callable[[TransitionNotification, str, str | None], object],
    ) -> None:
        self._transport = transport
        self._evidence_writer = evidence_writer
        self._evidence_healthy = True

    def notify(self, notification: TransitionNotification) -> str:
        try:
            delivered = bool(self._transport(notification.text))
            status = "DELIVERED" if delivered else "FAILED"
            category = None if delivered else "TRANSPORT_FAILED"
        except Exception:
            status = "FAILED"
            category = "TRANSPORT_EXCEPTION"
        try:
            self._evidence_writer(notification, status, category)
        except Exception as exc:
            self._evidence_healthy = False
            raise TransitionEvidenceError("notification attempt evidence failed") from exc
        return status

    def assert_mutation_allowed(self) -> None:
        if not self._evidence_healthy:
            raise TransitionEvidenceError("notification evidence is unhealthy")


def transition_observations_for_snapshot(
    snapshot: PortfolioSnapshot,
    *,
    observed_at: datetime,
    long_open_seconds: int = 900,
) -> tuple[TransitionObservation, ...]:
    """Normalize current broker order states into bounded operational evidence."""

    observations: list[TransitionObservation] = []
    for order in snapshot.orders:
        state = order.status
        severity = OperationalSeverity.INFO
        if state == "UNKNOWN":
            state = "ORDER_AMBIGUOUS"
            severity = OperationalSeverity.CRITICAL
        elif state in {"OPEN", "PARTIAL"}:
            try:
                opened = datetime.strptime(
                    f"{order.order_date}{order.order_time[:6]}", "%Y%m%d%H%M%S"
                ).replace(tzinfo=KST)
                if (observed_at.astimezone(KST) - opened).total_seconds() >= long_open_seconds:
                    state = "LONG_OPEN_ORDER"
                    severity = OperationalSeverity.WARNING
            except ValueError:
                state = "BROKER_TRUTH_FAILED"
                severity = OperationalSeverity.CRITICAL
        observations.append(
            TransitionObservation(
                account_scope_hash=snapshot.account_scope_hash,
                ticker=order.ticker,
                event_family="BROKER_ORDER",
                normalized_state=state,
                broker_subject_id=order.order_id,
                severity=severity,
                observed_at=observed_at,
                detail={"remaining_quantity": order.remaining_quantity},
            )
        )
    return tuple(observations)


@dataclass(frozen=True)
class IntradayIterationResult:
    iteration_id: str
    phase: IntradaySessionPhase
    outcome: IntradayIterationOutcome
    snapshot_id: str | None
    exit_results: tuple[ExitResult, ...]
    reason_code: str


@dataclass(frozen=True)
class IntradayWatchResult:
    iterations: tuple[IntradayIterationResult, ...]
    final_phase: IntradaySessionPhase
    interrupted: bool


def session_phase_at(observed_at: datetime) -> IntradaySessionPhase:
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("intraday clock must be timezone-aware")
    current = observed_at.astimezone(KST).time()
    if current < time(9, 0):
        return IntradaySessionPhase.PREFLIGHT_READ_ONLY
    if current < time(15, 20):
        return IntradaySessionPhase.ACTIVE
    if current < time(15, 30):
        return IntradaySessionPhase.RECONCILE_ONLY
    return IntradaySessionPhase.TERMINAL


def run_intraday_check(
    *,
    clock: Callable[[], datetime],
    snapshot_reader: Callable[[], PortfolioSnapshot],
    quote_reader: Callable[[str], Money],
    risk_config: RiskConfig,
    lease: object,
    exit_submitter: Callable[[ExitResult, Money], object],
    audit_sink: Callable[[IntradayIterationResult], object],
    mutation_guard: Callable[[], object] = lambda: None,
    stop_requested: Callable[[], bool] = lambda: False,
    terminalize: Callable[[IntradayIterationResult], object] | None = None,
    reconcile: Callable[[], object] = lambda: True,
) -> IntradayIterationResult:
    """Run one fresh, independently identified, LLM-free held-position pass."""

    iteration_id = uuid.uuid4().hex
    phase = session_phase_at(clock())
    if getattr(lease, "recovery_required", False):
        phase = IntradaySessionPhase.RECOVERY_ONLY
    if phase is not IntradaySessionPhase.ACTIVE:
        outcome = (
            IntradayIterationOutcome.BLOCKED
            if phase is IntradaySessionPhase.RECOVERY_ONLY
            else IntradayIterationOutcome.COMPLETED
        )
        result = IntradayIterationResult(
            iteration_id, phase, outcome, None, (), phase.value
        )
        audit_sink(result)
        return result

    result: IntradayIterationResult | None = None
    submitted = False
    try:
        snapshot = snapshot_reader()
        if stop_requested():
            result = IntradayIterationResult(
                iteration_id, IntradaySessionPhase.STOPPING,
                IntradayIterationOutcome.INTERRUPTED, snapshot.snapshot_id, (),
                "STOP_REQUESTED",
            )
            if terminalize is not None:
                terminalize(result)
            return result
        if not snapshot.mutation_capable:
            result = IntradayIterationResult(
                iteration_id,
                phase,
                IntradayIterationOutcome.BLOCKED,
                snapshot.snapshot_id,
                (),
                "ACCOUNT_DATA_INCOMPLETE",
            )
            return result
        getattr(lease, "assert_active_owner")()
        exits: list[ExitResult] = []
        for holding in snapshot.holdings:
            quote = quote_reader(holding.ticker)
            position = Position(
                Ticker(holding.ticker), holding.total_quantity,
                Money(holding.average_price, quote.currency),
            )
            risk = evaluate_position_risk(position, quote, risk_config)
            trigger = evaluate_risk_exit_trigger(
                ticker=holding.ticker,
                cycle_id=iteration_id,
                decision=risk,
                entry_price=holding.average_price,
                stop_loss_pct=risk_config.stop_loss_pct,
                take_profit_pct=risk_config.take_profit_pct,
            )
            candidate = evaluate_exit_candidate(trigger, snapshot)
            exits.append(candidate)
            if candidate.disposition is ExitDisposition.SUBMIT:
                if stop_requested():
                    result = IntradayIterationResult(
                        iteration_id, IntradaySessionPhase.STOPPING,
                        IntradayIterationOutcome.INTERRUPTED, snapshot.snapshot_id,
                        tuple(exits), "STOP_REQUESTED",
                    )
                    if terminalize is not None:
                        terminalize(result)
                    return result
                mutation_guard()
                getattr(lease, "assert_active_owner")()
                if stop_requested():
                    result = IntradayIterationResult(
                        iteration_id, IntradaySessionPhase.STOPPING,
                        IntradayIterationOutcome.INTERRUPTED, snapshot.snapshot_id,
                        tuple(exits), "STOP_REQUESTED",
                    )
                    if terminalize is not None:
                        terminalize(result)
                    return result
                submitted = True
                exit_submitter(candidate, quote)
        result = IntradayIterationResult(
            iteration_id,
            phase,
            IntradayIterationOutcome.COMPLETED,
            snapshot.snapshot_id,
            tuple(exits),
            "COMPLETED",
        )
    except LeaseOwnershipLost:
        result = IntradayIterationResult(
            iteration_id, IntradaySessionPhase.STOPPING,
            IntradayIterationOutcome.INTERRUPTED, None, (), "LEASE_OWNERSHIP_LOST",
        )
        if hasattr(lease, "state"):
            stop_after_ownership_loss(
                lease, reconcile_submitted=reconcile,
                terminalize_cycle=(
                    (lambda: terminalize(result))
                    if terminalize is not None else (lambda: None)
                ),
            )
        elif terminalize is not None:
            terminalize(result)
    except Exception:
        result = IntradayIterationResult(
            iteration_id,
            IntradaySessionPhase.STOPPING,
            IntradayIterationOutcome.FAILED,
            None,
            (),
            "ITERATION_FAILED",
        )
    finally:
        if result is None:
            result = IntradayIterationResult(
                iteration_id, IntradaySessionPhase.STOPPING,
                IntradayIterationOutcome.FAILED, None, (), "ITERATION_FAILED",
            )
        audit_sink(result)
    return result


def _release(
    lease: object,
    reconcile: Callable[[], object],
    terminalize: Callable[[], object] | None = None,
) -> None:
    if getattr(lease, "closed", False):
        return
    if terminalize is None:
        raise RuntimeError("active intraday shutdown requires a terminalizer")
    method = getattr(lease, "release_after_reconciliation", None)
    if method is not None:
        method(reconcile_submitted=reconcile, terminalize_cycle=terminalize)
        return
    terminalize()
    reconcile()
    release = getattr(lease, "release", None)
    if release is not None:
        release()


def run_intraday_watch(
    *,
    clock: Callable[[], datetime],
    sleeper: Callable[[float], object],
    stop_requested: Callable[[], bool],
    snapshot_reader: Callable[[], PortfolioSnapshot],
    quote_reader: Callable[[str], Money],
    risk_config: RiskConfig,
    lease: object,
    exit_submitter: Callable[[ExitResult, Money], object],
    audit_sink: Callable[[IntradayIterationResult], object],
    reconcile: Callable[[], object] = lambda: True,
    interval_seconds: float = 60,
    max_iterations: int | None = None,
    mutation_guard: Callable[[], object] = lambda: None,
    terminalize: Callable[[], object] | None = None,
) -> IntradayWatchResult:
    """Run foreground iterations until stop, cutoff, or terminal close."""

    if interval_seconds < 60:
        raise ValueError("intraday interval must be at least 60 seconds")
    iterations: list[IntradayIterationResult] = []
    interrupted = False
    final_phase = IntradaySessionPhase.PREFLIGHT_READ_ONLY
    while max_iterations is None or len(iterations) < max_iterations:
        if stop_requested():
            interrupted = True
            final_phase = IntradaySessionPhase.STOPPING
            _release(lease, reconcile, terminalize)
            break
        now = clock()
        final_phase = session_phase_at(now)
        if final_phase is IntradaySessionPhase.TERMINAL:
            _release(lease, reconcile, terminalize)
            break
        if final_phase is IntradaySessionPhase.RECONCILE_ONLY:
            reconcile()
            sleeper(interval_seconds)
            continue
        result = run_intraday_check(
            clock=lambda value=now: value,
            snapshot_reader=snapshot_reader,
            quote_reader=quote_reader,
            risk_config=risk_config,
            lease=lease,
            exit_submitter=exit_submitter,
            audit_sink=audit_sink,
            mutation_guard=mutation_guard,
            stop_requested=stop_requested,
            reconcile=reconcile,
            terminalize=(
                (lambda result: terminalize()) if terminalize is not None else None
            ),
        )
        iterations.append(result)
        if result.outcome is IntradayIterationOutcome.INTERRUPTED:
            interrupted = True
            final_phase = IntradaySessionPhase.STOPPING
            _release(lease, reconcile, terminalize)
            break
        sleeper(interval_seconds)
    return IntradayWatchResult(tuple(iterations), final_phase, interrupted)
