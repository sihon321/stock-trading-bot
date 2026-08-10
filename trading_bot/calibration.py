"""Pure, advisory-only policy calibration contracts.

This module deliberately has no settings, storage, provider, or broker capability.
It defines the frozen policy space used by later read-only calibration services.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
import math
import re
from typing import Mapping

from .replay import ReplayOutcome, ReplayScenario, run_replay_scenarios


class PolicyField(StrEnum):
    BUY_CONFIDENCE_THRESHOLD = "buy_confidence_threshold"
    SELL_CONFIDENCE_THRESHOLD = "sell_confidence_threshold"
    MAX_POSITION_VALUE = "max_position_value"
    STOP_LOSS_PCT = "stop_loss_pct"
    TAKE_PROFIT_PCT = "take_profit_pct"


class EvidenceGrade(StrEnum):
    INSUFFICIENT = "INSUFFICIENT"
    LIMITED = "LIMITED"
    SUFFICIENT = "SUFFICIENT"


@dataclass(frozen=True)
class CalibrationPolicy:
    buy_confidence_threshold: float
    sell_confidence_threshold: float
    max_position_value: float
    stop_loss_pct: float
    take_profit_pct: float

    def __post_init__(self) -> None:
        values = self.as_mapping()
        for name, value in values.items():
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        for name in (
            PolicyField.BUY_CONFIDENCE_THRESHOLD.value,
            PolicyField.SELL_CONFIDENCE_THRESHOLD.value,
        ):
            if not 0.0 <= values[name] <= 1.0:
                raise ValueError(f"{name} must be between zero and one")
        if self.max_position_value <= 0:
            raise ValueError("max_position_value must be positive")
        if self.stop_loss_pct <= 0:
            raise ValueError("stop_loss_pct must be positive")
        if self.take_profit_pct <= 0:
            raise ValueError("take_profit_pct must be positive")

    def as_mapping(self) -> dict[str, float]:
        return {
            PolicyField.BUY_CONFIDENCE_THRESHOLD.value: float(
                self.buy_confidence_threshold
            ),
            PolicyField.SELL_CONFIDENCE_THRESHOLD.value: float(
                self.sell_confidence_threshold
            ),
            PolicyField.MAX_POSITION_VALUE.value: float(self.max_position_value),
            PolicyField.STOP_LOSS_PCT.value: float(self.stop_loss_pct),
            PolicyField.TAKE_PROFIT_PCT.value: float(self.take_profit_pct),
        }


@dataclass(frozen=True)
class PolicyVariant:
    variant_id: str
    policy: CalibrationPolicy
    changed_field: PolicyField | None

    def __post_init__(self) -> None:
        if re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", self.variant_id) is None:
            raise ValueError("variant_id must be a bounded stable code")
        if self.changed_field is not None:
            object.__setattr__(self, "changed_field", PolicyField(self.changed_field))


@dataclass(frozen=True)
class CalibrationSourceCounts:
    eligible_days: int
    normal_cycles: int
    excluded_cycles: int
    unknown_cycles: int

    def __post_init__(self) -> None:
        for name, value in (
            ("eligible_days", self.eligible_days),
            ("normal_cycles", self.normal_cycles),
            ("excluded_cycles", self.excluded_cycles),
            ("unknown_cycles", self.unknown_cycles),
        ):
            if isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")

    @property
    def total_cycles(self) -> int:
        return self.normal_cycles + self.excluded_cycles + self.unknown_cycles


@dataclass(frozen=True)
class VariantMetrics:
    evaluated: int
    denominator: int
    buy_actions: int
    hold_actions: int
    sell_actions: int
    order_eligible: int
    low_confidence: int
    risk_blocks: int
    stop_loss_triggers: int
    take_profit_triggers: int
    exposure_total: float
    expectation_deltas: int

    def __post_init__(self) -> None:
        counts = (
            self.evaluated,
            self.denominator,
            self.buy_actions,
            self.hold_actions,
            self.sell_actions,
            self.order_eligible,
            self.low_confidence,
            self.risk_blocks,
            self.stop_loss_triggers,
            self.take_profit_triggers,
            self.expectation_deltas,
        )
        if any(isinstance(value, bool) or value < 0 for value in counts):
            raise ValueError("variant metric counts must be non-negative integers")
        if self.denominator != self.evaluated:
            raise ValueError("variant denominator must equal evaluated outcomes")
        if self.buy_actions + self.hold_actions + self.sell_actions > self.evaluated:
            raise ValueError("action counts exceed evaluated denominator")
        for value in counts[2:]:
            if value > self.evaluated:
                raise ValueError("variant metric count exceeds evaluated denominator")
        if not math.isfinite(self.exposure_total) or self.exposure_total < 0:
            raise ValueError("exposure_total must be finite and non-negative")


@dataclass(frozen=True)
class VariantEvaluation:
    variant: PolicyVariant
    metrics: VariantMetrics
    outcomes: tuple[ReplayOutcome, ...]


def baseline_policy() -> CalibrationPolicy:
    """Return a fresh immutable copy of the shipped policy baseline."""

    return CalibrationPolicy(
        buy_confidence_threshold=0.80,
        sell_confidence_threshold=0.80,
        max_position_value=1_000_000.0,
        stop_loss_pct=0.05,
        take_profit_pct=0.10,
    )


_CANDIDATES: tuple[tuple[PolicyField, float, str], ...] = (
    (PolicyField.BUY_CONFIDENCE_THRESHOLD, 0.75, "BUY_CONFIDENCE_075"),
    (PolicyField.BUY_CONFIDENCE_THRESHOLD, 0.85, "BUY_CONFIDENCE_085"),
    (PolicyField.SELL_CONFIDENCE_THRESHOLD, 0.75, "SELL_CONFIDENCE_075"),
    (PolicyField.SELL_CONFIDENCE_THRESHOLD, 0.85, "SELL_CONFIDENCE_085"),
    (PolicyField.MAX_POSITION_VALUE, 500_000.0, "MAX_POSITION_500000"),
    (PolicyField.MAX_POSITION_VALUE, 1_500_000.0, "MAX_POSITION_1500000"),
    (PolicyField.STOP_LOSS_PCT, 0.03, "STOP_LOSS_003"),
    (PolicyField.STOP_LOSS_PCT, 0.07, "STOP_LOSS_007"),
    (PolicyField.TAKE_PROFIT_PCT, 0.05, "TAKE_PROFIT_005"),
    (PolicyField.TAKE_PROFIT_PCT, 0.15, "TAKE_PROFIT_015"),
)


def validate_variant(
    variant: PolicyVariant,
    baseline: CalibrationPolicy | None = None,
) -> None:
    """Reject variants that are not baseline or one-field-only comparisons."""

    reference = baseline or baseline_policy()
    reference_values = reference.as_mapping()
    candidate_values = variant.policy.as_mapping()
    changed = {
        PolicyField(name)
        for name, value in candidate_values.items()
        if value != reference_values[name]
    }
    if variant.changed_field is None:
        if variant.variant_id != "BASELINE" or changed:
            raise ValueError("baseline variant must match the baseline policy")
        return
    if len(changed) != 1:
        raise ValueError("non-baseline variant must change exactly one policy field")
    if changed != {variant.changed_field}:
        raise ValueError("changed_field does not match the policy difference")
    if variant.variant_id == "BASELINE":
        raise ValueError("non-baseline variant cannot use BASELINE id")


def build_variant_catalog() -> tuple[PolicyVariant, ...]:
    """Build the exact, deterministic one-variable-at-a-time candidate catalog."""

    baseline = baseline_policy()
    variants: list[PolicyVariant] = [PolicyVariant("BASELINE", baseline, None)]
    for field, value, variant_id in _CANDIDATES:
        policy = replace(baseline, **{field.value: value})
        variant = PolicyVariant(variant_id, policy, field)
        validate_variant(variant, baseline)
        variants.append(variant)
    return tuple(variants)


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
    "EvidenceGrade",
    "PolicyField",
    "PolicyVariant",
    "VariantEvaluation",
    "VariantMetrics",
    "baseline_policy",
    "build_variant_catalog",
    "evaluate_variants",
    "validate_variant",
]
