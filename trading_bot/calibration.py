"""Production replay calibration evaluation with compatible pure re-exports."""

from __future__ import annotations

from dataclasses import replace
import math

from .calibration_evidence import (
    CalibrationPolicy,
    CalibrationSourceCounts,
    CalibrationJudgment,
    CalibrationJudgmentStatus,
    EvidenceGrade,
    MATERIAL_EXPOSURE_DELTA_KRW,
    MATERIAL_ORDER_OPPORTUNITY_DELTA,
    MATERIAL_RISK_EVENT_DELTA,
    PolicyField,
    PolicyVariant,
    VariantEvaluation,
    VariantMetrics,
    baseline_policy,
    build_variant_catalog,
    judge_variants,
    validate_variant,
    _CANDIDATES,
    _risk_events,
)
from .replay import ReplayOutcome, ReplayScenario, run_replay_scenarios


def evaluate_variants(
    scenarios: tuple[ReplayScenario, ...] | list[ReplayScenario],
    variants: tuple[PolicyVariant, ...] | list[PolicyVariant],
) -> tuple[VariantEvaluation, ...]:
    """Evaluate immutable one-field variants through the shipped replay path."""

    source_scenarios = tuple(scenarios)
    selected_variants = tuple(variants)
    if not source_scenarios:
        raise ValueError("at least one replay scenario is required")
    if not selected_variants:
        raise ValueError("at least one policy variant is required")
    variant_ids = [variant.variant_id for variant in selected_variants]
    if len(variant_ids) != len(set(variant_ids)):
        raise ValueError("duplicate policy variant id")

    step_prices: dict[tuple[str, str], float] = {}
    for scenario in source_scenarios:
        for step in scenario.steps:
            identity = (scenario.scenario_id, step.ticker)
            if identity in step_prices:
                raise ValueError("duplicate replay step identity")
            price = float(step.current_price)
            if not math.isfinite(price) or price < 0:
                raise ValueError("replay step price must be finite and non-negative")
            step_prices[identity] = price

    evaluations: list[VariantEvaluation] = []
    baseline = baseline_policy()
    for variant in selected_variants:
        validate_variant(variant, baseline)
        candidate_scenarios: list[ReplayScenario] = []
        for scenario in source_scenarios:
            policy = dict(scenario.policy)
            missing = set(baseline.as_mapping()).difference(policy)
            if missing:
                raise ValueError("replay scenario is missing calibration policy fields")
            if variant.changed_field is not None:
                policy[variant.changed_field.value] = variant.policy.as_mapping()[
                    variant.changed_field.value
                ]
            candidate_scenarios.append(replace(scenario, policy=policy))

        outcomes = tuple(run_replay_scenarios(tuple(candidate_scenarios)))
        seen_outcomes: set[tuple[str, str]] = set()
        exposure_total = 0.0
        for outcome in outcomes:
            identity = (outcome.scenario_id, outcome.ticker)
            if identity in seen_outcomes:
                raise ValueError("duplicate replay outcome identity")
            seen_outcomes.add(identity)
            if identity not in step_prices:
                raise ValueError("replay outcome has no matching step identity")
            exposure = float(outcome.position_quantity_after) * step_prices[identity]
            if not math.isfinite(exposure) or exposure < 0:
                raise ValueError("derived exposure must be finite and non-negative")
            exposure_total += exposure
        if seen_outcomes != set(step_prices):
            raise ValueError("replay outcomes do not cover every step identity")

        evaluated = len(outcomes)
        metrics = VariantMetrics(
            evaluated=evaluated,
            denominator=evaluated,
            buy_actions=sum(outcome.action == "BUY" for outcome in outcomes),
            hold_actions=sum(outcome.action == "HOLD" for outcome in outcomes),
            sell_actions=sum(outcome.action == "SELL" for outcome in outcomes),
            order_eligible=sum(outcome.order_eligible for outcome in outcomes),
            low_confidence=sum(
                outcome.blocked_reason == "LOW_CONFIDENCE" for outcome in outcomes
            ),
            risk_blocks=sum(
                outcome.blocked_reason == "RISK_BLOCK" for outcome in outcomes
            ),
            stop_loss_triggers=sum(
                outcome.reason == "risk override: stop_loss" for outcome in outcomes
            ),
            take_profit_triggers=sum(
                outcome.reason == "risk override: take_profit" for outcome in outcomes
            ),
            exposure_total=exposure_total,
            expectation_deltas=sum(not outcome.matched for outcome in outcomes),
        )
        evaluations.append(VariantEvaluation(variant, metrics, outcomes))
    return tuple(evaluations)


__all__ = [
    "CalibrationPolicy",
    "CalibrationSourceCounts",
    "CalibrationJudgment",
    "CalibrationJudgmentStatus",
    "EvidenceGrade",
    "MATERIAL_EXPOSURE_DELTA_KRW",
    "MATERIAL_ORDER_OPPORTUNITY_DELTA",
    "MATERIAL_RISK_EVENT_DELTA",
    "PolicyField",
    "PolicyVariant",
    "VariantEvaluation",
    "VariantMetrics",
    "baseline_policy",
    "build_variant_catalog",
    "judge_variants",
    "validate_variant",
    "evaluate_variants",
]
