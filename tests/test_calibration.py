from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import math

import pytest

from trading_bot.calibration import (
    CalibrationPolicy,
    PolicyField,
    PolicyVariant,
    baseline_policy,
    build_variant_catalog,
    validate_variant,
)


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
