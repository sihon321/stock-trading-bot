"""Pure saved replay contracts and canonical identities; no execution capabilities."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, is_dataclass, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = 1


REQUIRED_BOUNDARIES = frozenset({
    "buy_at_threshold", "buy_below_threshold", "hold", "sell",
    "malformed_signal", "stale_data", "stop_loss", "take_profit",
    "daily_loss_block", "sizing_boundary", "future_access",
})


NON_PROFITABILITY_DISCLAIMER = (
    "This replay validates decision-policy paths only; it is not an estimate of "
    "profitability, returns, win rate, or investment performance."
)


class FutureDataAccessError(ValueError):
    """Raised whenever frozen data crosses its declared evaluation cutoff."""


class ReplayEvidenceError(RuntimeError):
    """Raised when deterministic revision evidence cannot be established."""


class ReplayOutputError(RuntimeError):
    """Raised when replay evidence cannot be persisted without ambiguity."""


def _canonical_value(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _canonical_value(asdict(value))
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("canonical JSON object keys must be strings")
        return {key: _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized = [_canonical_value(item) for item in value]
        return sorted(normalized, key=lambda item: canonical_json_bytes(item))
    if isinstance(value, Path):
        return str(value)
    return value


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize deterministic evidence using strict, compact canonical JSON."""
    return json.dumps(
        _canonical_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


@dataclass(frozen=True)
class ReplayManifest:
    scenario_hash: str
    ohlcv_hash: str
    raw_signal_hash: str
    policy: Mapping[str, Any]
    head_commit: str
    relevant_tracked_diff_hash: str
    code_state: str
    initial_state: Mapping[str, Any]
    evaluation_time: str
    trading_date: str
    fixture_schema_version: int


def _deterministic_result_document(
    manifest: ReplayManifest, outcomes: Sequence[Any], **extra: Any
) -> Mapping[str, Any]:
    document = {
        "manifest": _canonical_value(manifest),
        # Sequence order is policy evidence and must never be sorted.
        "outcomes": _canonical_value(tuple(outcomes)),
    }
    document.update({key: _canonical_value(value) for key, value in extra.items()})
    return document


def compute_result_id(
    manifest: ReplayManifest,
    outcomes: Sequence[Any],
    *,
    funnel: ReplayFunnel | None = None,
    verification: ReplayVerification | None = None,
    disclaimer: str = NON_PROFITABILITY_DISCLAIMER,
) -> str:
    """Hash the complete deterministic replay evidence document."""
    return hashlib.sha256(
        canonical_json_bytes(_deterministic_result_document(
            manifest, outcomes, funnel=funnel, verification=verification,
            disclaimer=disclaimer,
        ))
    ).hexdigest()


@dataclass(frozen=True)
class ReplayResult:
    manifest: ReplayManifest
    outcomes: tuple[Any, ...]
    observational_metadata: Mapping[str, Any]
    funnel: ReplayFunnel | None = None
    verification: ReplayVerification | None = None
    disclaimer: str = NON_PROFITABILITY_DISCLAIMER
    result_id: str = field(init=False)

    def __post_init__(self) -> None:
        normalized_outcomes = tuple(
            json.loads(canonical_json_bytes(outcome)) for outcome in self.outcomes
        )
        normalized_metadata = json.loads(canonical_json_bytes(self.observational_metadata))
        object.__setattr__(self, "outcomes", normalized_outcomes)
        object.__setattr__(self, "observational_metadata", normalized_metadata)
        object.__setattr__(
            self, "result_id", compute_result_id(
                self.manifest, self.outcomes, funnel=self.funnel,
                verification=self.verification, disclaimer=self.disclaimer,
            )
        )

    def deterministic_bytes(self) -> bytes:
        return canonical_json_bytes(
            _deterministic_result_document(
                self.manifest, self.outcomes, funnel=self.funnel,
                verification=self.verification, disclaimer=self.disclaimer,
            )
        )

    def normalized_bytes(self) -> bytes:
        document = {
            "schema_version": 1,
            "result_id": self.result_id,
            "evidence": json.loads(self.deterministic_bytes()),
            "observational_metadata": self.observational_metadata,
        }
        return canonical_json_bytes(document) + b"\n"


@dataclass(frozen=True)
class ReplayOutcome:
    scenario_id: str
    ticker: str
    rank: int
    action: str
    has_order: bool
    fill: str
    reason: str
    cash_after: float
    position_quantity_after: int
    expected_action: str
    matched: bool
    selected: bool = True
    buy_signaled: bool = False
    confidence_qualified: bool = False
    risk_qualified: bool = False
    validly_sized: bool = False
    order_eligible: bool = False
    blocked_reason: str | None = None
    realized_loss_after: float = 0.0
    boundary_id: str = ""
    expected_stage: str = "action"


@dataclass(frozen=True)
class ReplayCount:
    numerator: int
    denominator: int


@dataclass(frozen=True)
class ReplayFunnel:
    evaluated: ReplayCount
    selected: ReplayCount
    buy_signaled: ReplayCount
    confidence_qualified: ReplayCount
    risk_qualified: ReplayCount
    validly_sized: ReplayCount
    order_eligible: ReplayCount
    actions: Mapping[str, ReplayCount]
    blocked_reasons: Mapping[str, ReplayCount]


@dataclass(frozen=True)
class ReplayCheck:
    boundary_id: str
    scenario_id: str
    ticker: str
    stage: str
    expected: str
    actual: str
    passed: bool


@dataclass(frozen=True)
class ReplayVerification:
    passed: bool
    checks: tuple[ReplayCheck, ...]


def build_replay_funnel(outcomes: Sequence[ReplayOutcome]) -> ReplayFunnel:
    """Derive an explicit-denominator policy funnel from normalized stage facts."""
    total = len(outcomes)
    selected = sum(outcome.selected for outcome in outcomes)
    buy = sum(outcome.buy_signaled for outcome in outcomes)
    confidence = sum(outcome.confidence_qualified for outcome in outcomes)
    risk = sum(outcome.risk_qualified for outcome in outcomes)
    sized = sum(outcome.validly_sized for outcome in outcomes)
    eligible = sum(outcome.order_eligible for outcome in outcomes)
    if not total >= selected >= buy >= confidence >= risk >= sized >= eligible:
        raise ValueError("replay BUY-stage facts violate monotonic funnel invariants")
    actions = {
        action: ReplayCount(sum(x.action == action for x in outcomes), total)
        for action in ("BUY", "HOLD", "SELL")
    }
    reasons = sorted({x.blocked_reason for x in outcomes if x.blocked_reason})
    blocked = {
        reason: ReplayCount(sum(x.blocked_reason == reason for x in outcomes), total)
        for reason in reasons
    }
    return ReplayFunnel(
        ReplayCount(total, total), ReplayCount(selected, total),
        ReplayCount(buy, selected), ReplayCount(confidence, buy),
        ReplayCount(risk, confidence), ReplayCount(sized, risk),
        ReplayCount(eligible, sized), actions, blocked,
    )


def verify_replay_expectations(outcomes: Sequence[ReplayOutcome]) -> ReplayVerification:
    """Compare frozen expected terminal actions with normalized replay outcomes."""
    checks = tuple(
        ReplayCheck(
            outcome.boundary_id, outcome.scenario_id, outcome.ticker,
            outcome.expected_stage, outcome.expected_action,
            outcome.action, outcome.action == outcome.expected_action,
        )
        for outcome in outcomes
    )
    expected = Counter({boundary_id: 1 for boundary_id in REQUIRED_BOUNDARIES})
    executed = Counter(check.boundary_id for check in checks)
    attributed = all(
        check.scenario_id and check.ticker and check.stage
        and check.expected and check.actual for check in checks
    )
    return ReplayVerification(
        all(check.passed for check in checks) and executed == expected and attributed,
        checks,
    )
