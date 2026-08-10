from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import math
from pathlib import Path

import pytest

import trading_bot.calibration as calibration_module
from trading_bot.calibration import (
    CalibrationPolicy,
    PolicyField,
    PolicyVariant,
    baseline_policy,
    build_variant_catalog,
    evaluate_variants,
    validate_variant,
)
from trading_bot.replay import load_replay_bundle


FIXTURES = Path(__file__).parent / "fixtures" / "replay"


def test_baseline_policy_matches_runtime_defaults() -> None:
    baseline = baseline_policy()

    assert baseline == CalibrationPolicy(
        buy_confidence_threshold=0.80,
        sell_confidence_threshold=0.80,
        max_position_value=1_000_000.0,
        stop_loss_pct=0.05,
        take_profit_pct=0.10,
    )
    with pytest.raises(FrozenInstanceError):
        baseline.buy_confidence_threshold = 0.75  # type: ignore[misc]


def test_catalog_is_exact_ordered_and_one_field_at_a_time() -> None:
    baseline = baseline_policy()
    catalog = build_variant_catalog()

    assert [variant.variant_id for variant in catalog] == [
        "BASELINE",
        "BUY_CONFIDENCE_075",
        "BUY_CONFIDENCE_085",
        "SELL_CONFIDENCE_075",
        "SELL_CONFIDENCE_085",
        "MAX_POSITION_500000",
        "MAX_POSITION_1500000",
        "STOP_LOSS_003",
        "STOP_LOSS_007",
        "TAKE_PROFIT_005",
        "TAKE_PROFIT_015",
    ]
    assert catalog[0].changed_field is None
    assert catalog[0].policy == baseline

    expected_values = {
        PolicyField.BUY_CONFIDENCE_THRESHOLD: {0.75, 0.85},
        PolicyField.SELL_CONFIDENCE_THRESHOLD: {0.75, 0.85},
        PolicyField.MAX_POSITION_VALUE: {500_000.0, 1_500_000.0},
        PolicyField.STOP_LOSS_PCT: {0.03, 0.07},
        PolicyField.TAKE_PROFIT_PCT: {0.05, 0.15},
    }
    observed = {field: set() for field in expected_values}
    baseline_map = baseline.as_mapping()
    for variant in catalog:
        validate_variant(variant, baseline)
        changed = {
            key for key, value in variant.policy.as_mapping().items()
            if value != baseline_map[key]
        }
        if variant.changed_field is None:
            assert changed == set()
        else:
            assert changed == {variant.changed_field.value}
            observed[variant.changed_field].add(
                variant.policy.as_mapping()[variant.changed_field.value]
            )

    assert observed == expected_values


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("buy_confidence_threshold", float("nan")),
        ("sell_confidence_threshold", float("inf")),
        ("buy_confidence_threshold", -0.1),
        ("sell_confidence_threshold", 1.1),
        ("max_position_value", 0.0),
        ("stop_loss_pct", 0.0),
        ("take_profit_pct", -0.1),
    ],
)
def test_policy_rejects_non_finite_or_out_of_range_values(
    field: str, value: float
) -> None:
    values = baseline_policy().as_mapping()
    values[field] = value
    with pytest.raises(ValueError):
        CalibrationPolicy(**values)


def test_variant_rejects_mismatched_field_multiple_changes_and_bad_ids() -> None:
    baseline = baseline_policy()
    buy_changed = replace(baseline, buy_confidence_threshold=0.75)

    with pytest.raises(ValueError, match="changed_field"):
        validate_variant(PolicyVariant("BUY_BAD_FIELD", buy_changed, PolicyField.STOP_LOSS_PCT))

    multi_changed = replace(
        baseline, buy_confidence_threshold=0.75, stop_loss_pct=0.03
    )
    with pytest.raises(ValueError, match="exactly one"):
        validate_variant(
            PolicyVariant(
                "MULTI_FIELD",
                multi_changed,
                PolicyField.BUY_CONFIDENCE_THRESHOLD,
            )
        )

    with pytest.raises(ValueError, match="variant_id"):
        PolicyVariant("lowercase-id", buy_changed, PolicyField.BUY_CONFIDENCE_THRESHOLD)


def test_catalog_returns_fresh_immutable_values() -> None:
    first = build_variant_catalog()
    second = build_variant_catalog()
    assert first == second
    assert first is not second
    assert all(math.isfinite(value) for item in first for value in item.policy.as_mapping().values())


def test_counterfactual_changes_only_declared_policy_key_before_production_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenarios = load_replay_bundle(FIXTURES / "focused.json")
    catalog = build_variant_catalog()
    shipped = calibration_module.run_replay_scenarios
    calls: list[tuple[object, ...]] = []

    def spy(candidate_scenarios):
        calls.append(tuple(candidate_scenarios))
        return shipped(candidate_scenarios)

    monkeypatch.setattr(calibration_module, "run_replay_scenarios", spy)
    evaluations = evaluate_variants(scenarios, catalog)

    assert len(calls) == len(catalog) == len(evaluations)
    for variant, candidate_scenarios in zip(catalog, calls, strict=True):
        for source, candidate in zip(scenarios, candidate_scenarios, strict=True):
            changed = {
                key
                for key in source.policy
                if source.policy[key] != candidate.policy[key]
            }
            assert changed == (
                set() if variant.changed_field is None else {variant.changed_field.value}
            )
            assert replace(candidate, policy=source.policy) == source


def test_confidence_position_stop_and_take_variants_use_production_boundaries() -> None:
    scenarios = load_replay_bundle(FIXTURES / "focused.json")
    evaluations = {
        evaluation.variant.variant_id: evaluation
        for evaluation in evaluate_variants(scenarios, build_variant_catalog())
    }

    baseline = evaluations["BASELINE"].metrics
    assert evaluations["BUY_CONFIDENCE_075"].metrics.buy_actions == baseline.buy_actions + 1
    assert evaluations["BUY_CONFIDENCE_085"].metrics.low_confidence == baseline.low_confidence + 1
    assert evaluations["SELL_CONFIDENCE_075"].metrics.sell_actions == baseline.sell_actions
    assert evaluations["SELL_CONFIDENCE_085"].metrics.sell_actions == baseline.sell_actions
    assert evaluations["STOP_LOSS_003"].metrics.stop_loss_triggers == 1
    assert evaluations["STOP_LOSS_007"].metrics.stop_loss_triggers == 1
    assert evaluations["TAKE_PROFIT_005"].metrics.take_profit_triggers == 1
    assert evaluations["TAKE_PROFIT_015"].metrics.take_profit_triggers == 0

    full_day_source = load_replay_bundle(FIXTURES / "full_day.json")
    full_day = tuple(
        replace(
            scenario,
            policy={**scenario.policy, "buy_cash_fraction": 0.20},
        )
        for scenario in full_day_source
    )
    position_evaluations = {
        evaluation.variant.variant_id: evaluation.metrics
        for evaluation in evaluate_variants(full_day, build_variant_catalog())
    }
    assert (
        position_evaluations["MAX_POSITION_500000"].exposure_total
        < position_evaluations["BASELINE"].exposure_total
        < position_evaluations["MAX_POSITION_1500000"].exposure_total
    )


def test_counterfactual_metrics_are_explicit_and_deterministic() -> None:
    scenarios = load_replay_bundle(FIXTURES / "full_day.json")
    variants = build_variant_catalog()

    first = evaluate_variants(scenarios, variants)
    second = evaluate_variants(scenarios, variants)

    assert first == second
    for evaluation in first:
        metrics = evaluation.metrics
        assert metrics.evaluated == (
            metrics.buy_actions + metrics.hold_actions + metrics.sell_actions
        )
        assert metrics.denominator == metrics.evaluated
        assert 0 <= metrics.order_eligible <= metrics.evaluated
        assert metrics.exposure_total >= 0
        assert metrics.expectation_deltas == sum(
            not outcome.matched for outcome in evaluation.outcomes
        )


def test_counterfactual_rejects_duplicate_step_identity() -> None:
    scenarios = load_replay_bundle(FIXTURES / "focused.json")
    duplicated = replace(scenarios[0], steps=scenarios[0].steps * 2)

    with pytest.raises(ValueError, match="duplicate replay step identity"):
        evaluate_variants((duplicated,), build_variant_catalog()[:1])
