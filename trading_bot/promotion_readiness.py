"""Pure, fail-closed real-money promotion readiness assessment."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import math

from .replay_evidence import canonical_json_bytes


class ReadinessState(StrEnum):
    PASS = "PASS"
    BLOCK = "BLOCK"
    UNKNOWN = "UNKNOWN"


class PromotionState(StrEnum):
    READY = "READY"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class ReadinessCheck:
    code: str
    state: ReadinessState
    evidence: tuple[tuple[str, str | int | bool | None], ...]


@dataclass(frozen=True)
class ReadinessEvidence:
    replay_verified: bool | None
    credited_days: int
    target_days: int
    safety_failure_code: str | None
    reconciliation_incomplete: int
    reconciliation_unknown: int
    active_freezes: int
    cross_store_unknown: int
    reports_complete: bool | None
    unresolved_orders: int
    calibration_valid: bool | None
    calibration_id: str
    policy_frozen: bool | None
    resolved_historical_ambiguity: int
    source_identities: tuple[str, ...]

    def __post_init__(self) -> None:
        counts = (
            self.credited_days, self.target_days, self.reconciliation_incomplete,
            self.reconciliation_unknown, self.active_freezes,
            self.cross_store_unknown, self.unresolved_orders,
            self.resolved_historical_ambiguity,
        )
        if any(isinstance(value, bool) or value < 0 for value in counts):
            raise ValueError("readiness counts must be non-negative")
        if self.target_days <= 0 or len(self.calibration_id) != 64:
            raise ValueError("readiness identity inputs are invalid")
        if not self.source_identities:
            raise ValueError("source identities are required")


@dataclass(frozen=True)
class PromotionReadinessAssessment:
    assessment_id: str
    state: PromotionState
    checks: tuple[ReadinessCheck, ...]
    warnings: tuple[str, ...]
    calibration_id: str


def _boolean_state(value: bool | None) -> ReadinessState:
    if value is None:
        return ReadinessState.UNKNOWN
    return ReadinessState.PASS if value else ReadinessState.BLOCK


def build_readiness_assessment(
    evidence: ReadinessEvidence,
    *,
    policy_snapshot: tuple[tuple[str, float], ...],
    rollback_ack: bool,
    kill_ack: bool,
    manual_approval: bool,
) -> PromotionReadinessAssessment:
    """Reduce normalized facts to READY/BLOCKED; this result grants no authority."""

    if not policy_snapshot or len({key for key, _ in policy_snapshot}) != len(policy_snapshot):
        raise ValueError("policy snapshot must contain unique fields")
    if any(not math.isfinite(float(value)) for _, value in policy_snapshot):
        raise ValueError("policy snapshot values must be finite")
    soak_pass = (
        evidence.credited_days >= evidence.target_days
        and evidence.safety_failure_code is None
        and evidence.reconciliation_incomplete == 0
        and evidence.reconciliation_unknown == 0
        and evidence.active_freezes == 0
        and evidence.cross_store_unknown == 0
    )
    checks = (
        ReadinessCheck("REPLAY_VERIFIED", _boolean_state(evidence.replay_verified), ()),
        ReadinessCheck(
            "SOAK_ACCEPTED", ReadinessState.PASS if soak_pass else ReadinessState.BLOCK,
            (("credited_days", evidence.credited_days), ("target_days", evidence.target_days),
             ("safety_failure_code", evidence.safety_failure_code),
             ("active_freezes", evidence.active_freezes)),
        ),
        ReadinessCheck("REPORTS_COMPLETE", _boolean_state(evidence.reports_complete), ()),
        ReadinessCheck(
            "ORDERS_RESOLVED",
            ReadinessState.PASS if evidence.unresolved_orders == 0 else ReadinessState.BLOCK,
            (("unresolved_orders", evidence.unresolved_orders),),
        ),
        ReadinessCheck("CALIBRATION_VALID", _boolean_state(evidence.calibration_valid),
                       (("calibration_id", evidence.calibration_id),)),
        ReadinessCheck("POLICY_FROZEN", _boolean_state(evidence.policy_frozen), ()),
        ReadinessCheck("ROLLBACK_ACK", _boolean_state(rollback_ack), ()),
        ReadinessCheck("KILL_ACK", _boolean_state(kill_ack), ()),
        ReadinessCheck("MANUAL_APPROVAL", _boolean_state(manual_approval), ()),
    )
    state = (
        PromotionState.READY
        if all(check.state is ReadinessState.PASS for check in checks)
        else PromotionState.BLOCKED
    )
    warnings = (
        (f"RESOLVED_HISTORICAL_AMBIGUITY:{evidence.resolved_historical_ambiguity}",)
        if evidence.resolved_historical_ambiguity
        else ()
    )
    document = {
        "schema_version": 1,
        "evidence": evidence,
        "policy_snapshot": tuple(sorted(policy_snapshot)),
        "rollback_ack": rollback_ack,
        "kill_ack": kill_ack,
        "manual_approval": manual_approval,
        "checks": checks,
        "state": state,
        "warnings": warnings,
    }
    assessment_id = hashlib.sha256(canonical_json_bytes(document)).hexdigest()
    return PromotionReadinessAssessment(
        assessment_id, state, checks, warnings, evidence.calibration_id
    )


def render_readiness_assessment(result: PromotionReadinessAssessment) -> str:
    lines = [
        "실거래 승격 준비도 [READ_ONLY_ASSESSMENT]",
        f"assessment_id={result.assessment_id}",
        f"calibration_id={result.calibration_id}",
        f"state={result.state.value}",
    ]
    for check in result.checks:
        facts = ",".join(f"{key}={value}" for key, value in check.evidence) or "NONE"
        lines.append(f"- {check.code}={check.state.value} evidence={facts}")
    lines.extend(f"warning={warning}" for warning in result.warnings)
    lines.append("이 평가는 거래 모드를 변경하거나 주문을 제출할 권한이 없습니다.")
    return "\n".join(lines) + "\n"


__all__ = [
    "PromotionReadinessAssessment", "PromotionState", "ReadinessCheck",
    "ReadinessEvidence", "ReadinessState", "build_readiness_assessment",
    "render_readiness_assessment",
]
