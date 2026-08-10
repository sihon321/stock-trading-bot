from dataclasses import replace

import pytest

from trading_bot.promotion_readiness import (
    PromotionState,
    ReadinessEvidence,
    ReadinessState,
    build_readiness_assessment,
)


def _evidence(**changes) -> ReadinessEvidence:
    values = dict(
        replay_verified=True,
        credited_days=20,
        target_days=20,
        safety_failure_code=None,
        reconciliation_incomplete=0,
        reconciliation_unknown=0,
        active_freezes=0,
        cross_store_unknown=0,
        reports_complete=True,
        unresolved_orders=0,
        calibration_valid=True,
        calibration_id="a" * 64,
        policy_frozen=True,
        resolved_historical_ambiguity=0,
        source_identities=("source-a",),
    )
    values.update(changes)
    return ReadinessEvidence(**values)


def _assessment(evidence=None, **acks):
    return build_readiness_assessment(
        evidence or _evidence(),
        policy_snapshot=(("buy_confidence_threshold", 0.8),),
        rollback_ack=acks.get("rollback_ack", True),
        kill_ack=acks.get("kill_ack", True),
        manual_approval=acks.get("manual_approval", True),
    )


def test_all_nine_gates_pass_only_for_complete_evidence() -> None:
    result = _assessment()
    assert result.state is PromotionState.READY
    assert [check.code for check in result.checks] == [
        "REPLAY_VERIFIED", "SOAK_ACCEPTED", "REPORTS_COMPLETE",
        "ORDERS_RESOLVED", "CALIBRATION_VALID", "POLICY_FROZEN",
        "ROLLBACK_ACK", "KILL_ACK", "MANUAL_APPROVAL",
    ]
    assert all(check.state is ReadinessState.PASS for check in result.checks)


@pytest.mark.parametrize(
    "changes",
    [
        {"replay_verified": False}, {"credited_days": 10},
        {"safety_failure_code": "D09_TEST"}, {"reconciliation_unknown": 1},
        {"active_freezes": 1}, {"cross_store_unknown": 1},
        {"reports_complete": False}, {"unresolved_orders": 1},
        {"calibration_valid": False}, {"policy_frozen": False},
    ],
)
def test_each_objective_gate_blocks_and_manual_approval_cannot_waive(changes) -> None:
    result = _assessment(_evidence(**changes))
    assert result.state is PromotionState.BLOCKED


def test_unknown_blocks_resolved_history_warns_and_identity_is_snapshot_bound() -> None:
    unknown = _assessment(_evidence(replay_verified=None))
    history = _assessment(_evidence(resolved_historical_ambiguity=2))
    changed = _assessment(_evidence(source_identities=("source-b",)))
    ack_changed = _assessment(manual_approval=False)

    assert unknown.state is PromotionState.BLOCKED
    assert any(check.state is ReadinessState.UNKNOWN for check in unknown.checks)
    assert history.state is PromotionState.READY
    assert history.warnings == ("RESOLVED_HISTORICAL_AMBIGUITY:2",)
    assert len({history.assessment_id, changed.assessment_id, ack_changed.assessment_id}) == 3
    assert history == _assessment(_evidence(resolved_historical_ambiguity=2))
