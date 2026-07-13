import json
import hashlib
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

import trading_bot.replay as replay_module
from trading_bot.data_models import IndicatorConfig
from trading_bot.replay import (
    FutureDataAccessError,
    ReplayManifest,
    ReplayOutputError,
    ReplayResult,
    ReplayOutcome,
    build_replay_funnel,
    verify_replay_expectations,
    build_replay_manifest,
    canonical_json_bytes,
    compute_result_id,
    guarded_historical_view,
    load_replay_bundle,
    run_replay_scenarios,
    write_replay_result,
    REQUIRED_BOUNDARIES,
    ReplayCheck,
)

FIXTURES = Path(__file__).parent / "fixtures" / "replay"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _manifest(repo: Path, **overrides) -> ReplayManifest:
    values = {
        "scenario_fixtures": {"b": 2, "a": 1},
        "ohlcv_fixtures": [{"date": "20260701", "close": 70000}],
        "raw_signal_fixtures": {"005930": '{"decision":"HOLD"}'},
        "policy": {"buy_threshold": 0.8, "markets": ["KOSPI"]},
        "initial_state": {"cash": 1_000_000, "positions": []},
        "evaluation_time": "2026-07-01T15:30:00+09:00",
        "trading_date": "20260701",
        "fixture_schema_version": 1,
        "repo_root": repo,
        "relevant_paths": ("trading_bot", "pyproject.toml"),
    }
    values.update(overrides)
    return build_replay_manifest(**values)


def test_canonical_json_is_sorted_strict_and_stable() -> None:
    assert canonical_json_bytes({"z": [2, 1], "a": {"d": 4, "c": 3}}) == (
        b'{"a":{"c":3,"d":4},"z":[2,1]}'
    )
    with pytest.raises(ValueError):
        canonical_json_bytes({"bad": float("nan")})
    with pytest.raises(ValueError):
        canonical_json_bytes({"bad": float("inf")})


def test_manifest_records_complete_deterministic_evidence(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "trading_bot").mkdir()
    (tmp_path / "trading_bot" / "replay.py").write_text("VERSION = 1\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='fixture'\n")
    _git(tmp_path, "add", "trading_bot/replay.py", "pyproject.toml")
    _git(tmp_path, "commit", "-qm", "initial")

    manifest = _manifest(tmp_path)

    assert manifest.scenario_hash == hashlib.sha256(
        canonical_json_bytes({"b": 2, "a": 1})
    ).hexdigest()
    assert len(manifest.ohlcv_hash) == len(manifest.raw_signal_hash) == 64
    assert manifest.policy == {"buy_threshold": 0.8, "markets": ["KOSPI"]}
    assert manifest.initial_state == {"cash": 1_000_000, "positions": []}
    assert manifest.head_commit == _git(tmp_path, "rev-parse", "HEAD")
    assert manifest.relevant_tracked_diff_hash == hashlib.sha256(b"").hexdigest()
    assert manifest.code_state == "clean"
    assert manifest.evaluation_time == "2026-07-01T15:30:00+09:00"
    assert manifest.trading_date == "20260701"
    assert manifest.fixture_schema_version == 1


def test_dirty_relevant_tracked_content_changes_manifest_but_untracked_does_not(
    tmp_path: Path,
) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "trading_bot").mkdir()
    source = tmp_path / "trading_bot" / "replay.py"
    source.write_text("VERSION = 1\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='fixture'\n")
    _git(tmp_path, "add", "trading_bot/replay.py", "pyproject.toml")
    _git(tmp_path, "commit", "-qm", "initial")
    clean = _manifest(tmp_path)

    (tmp_path / "result.json").write_text("generated")
    assert _manifest(tmp_path) == clean

    source.write_text("VERSION = 2\n")
    dirty = _manifest(tmp_path)
    assert dirty.code_state == "dirty"
    assert dirty.head_commit == clean.head_commit
    assert dirty.relevant_tracked_diff_hash != clean.relevant_tracked_diff_hash


def _static_manifest(**changes) -> ReplayManifest:
    values = {
        "scenario_hash": "1" * 64,
        "ohlcv_hash": "2" * 64,
        "raw_signal_hash": "3" * 64,
        "policy": {"threshold": 0.8},
        "head_commit": "abc123",
        "relevant_tracked_diff_hash": "4" * 64,
        "code_state": "clean",
        "initial_state": {"cash": 1000, "positions": []},
        "evaluation_time": "2026-07-01T15:30:00+09:00",
        "trading_date": "20260701",
        "fixture_schema_version": 1,
    }
    values.update(changes)
    return ReplayManifest(**values)


def test_result_identity_is_repeatable_order_sensitive_and_metadata_independent() -> None:
    manifest = _static_manifest()
    outcomes = ({"ticker": "000010", "action": "BUY"}, {"ticker": "000020", "action": "HOLD"})
    first = ReplayResult(manifest, outcomes, {"invoked_at": "now", "duration_ms": 1})
    second = ReplayResult(manifest, outcomes, {"invoked_at": "later", "duration_ms": 99})

    assert first.result_id == second.result_id == compute_result_id(manifest, outcomes)
    assert first.deterministic_bytes() == second.deterministic_bytes()
    assert ReplayResult(manifest, tuple(reversed(outcomes)), {}).result_id != first.result_id
    changed = ({"ticker": "000010", "action": "HOLD"}, outcomes[1])
    assert ReplayResult(manifest, changed, {}).result_id != first.result_id
    assert ReplayResult(_static_manifest(trading_date="20260702"), outcomes, {}).result_id != first.result_id


def test_reordered_unordered_input_keeps_result_identity() -> None:
    left = _static_manifest(policy={"a": 1, "b": {"x": 2, "y": 3}})
    right = _static_manifest(policy={"b": {"y": 3, "x": 2}, "a": 1})
    outcomes = ({"ticker": "000010", "action": "HOLD"},)
    assert compute_result_id(left, outcomes) == compute_result_id(right, outcomes)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("scenario_hash", "a" * 64),
        ("ohlcv_hash", "b" * 64),
        ("raw_signal_hash", "c" * 64),
        ("policy", {"threshold": 0.9}),
        ("head_commit", "def456"),
        ("relevant_tracked_diff_hash", "d" * 64),
        ("code_state", "dirty"),
        ("initial_state", {"cash": 999, "positions": []}),
        ("evaluation_time", "2026-07-01T15:31:00+09:00"),
        ("trading_date", "20260702"),
        ("fixture_schema_version", 2),
    ],
)
def test_each_manifest_input_changes_result_identity(field: str, value) -> None:
    outcomes = ({"ticker": "000010", "action": "HOLD"},)
    baseline = compute_result_id(_static_manifest(), outcomes)
    assert compute_result_id(_static_manifest(**{field: value}), outcomes) != baseline


def test_output_is_normalized_idempotent_and_conflict_safe(tmp_path: Path) -> None:
    result = ReplayResult(
        _static_manifest(),
        ({"ticker": "000010", "action": "HOLD"},),
        {"invoked_at": "2026-07-01T16:00:00+09:00", "output_path": "ignored-for-id"},
    )
    path = write_replay_result(result, tmp_path)
    original = path.read_bytes()
    assert original == result.normalized_bytes()
    assert write_replay_result(result, tmp_path) == path
    assert path.read_bytes() == original

    path.write_text("different", encoding="utf-8")
    with pytest.raises(ReplayOutputError, match="conflict"):
        write_replay_result(result, tmp_path)


def test_output_rejects_traversal_and_symlink_escape(tmp_path: Path) -> None:
    result = ReplayResult(_static_manifest(), (), {})
    with pytest.raises(ReplayOutputError):
        write_replay_result(result, tmp_path, filename="../escape.json")

    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "linked"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ReplayOutputError):
        write_replay_result(result, link)


def test_fixture_bundles_are_strict_and_catalog_is_enumerable() -> None:
    focused = load_replay_bundle(FIXTURES / "focused.json")
    full_day = load_replay_bundle(FIXTURES / "full_day.json")
    assert {x.scenario_id for x in focused} >= {
        "buy-at-threshold", "buy-below-threshold", "malformed-signal",
        "stop-loss-override", "daily-loss-block",
    }
    assert full_day[0].mode == "FULL_DAY"
    assert all(isinstance(step.raw_signal, str) for s in (*focused, *full_day) for step in s.steps)
    raw = json.loads((FIXTURES / "focused.json").read_text())
    assert len(raw["boundaries"]) == 11


def test_fixture_schema_uses_only_raw_ohlcv_inputs() -> None:
    expected_history_fields = {
        "ticker", "market", "state", "trading_value", "health", "ohlcv",
    }
    expected_ohlcv_fields = {
        "observed_at", "open", "high", "low", "close", "volume",
    }
    expected_indicator_fields = {
        "sma_short_window", "sma_long_window", "rsi_window", "atr_window",
        "historical_volatility_window", "volume_ratio_window",
    }

    for fixture_name in ("focused.json", "full_day.json"):
        raw = json.loads((FIXTURES / fixture_name).read_text())
        for scenario in raw["scenarios"]:
            assert set(scenario["policy"]["indicator_config"]) == expected_indicator_fields
            for record in scenario["market_history"]:
                assert set(record) == expected_history_fields
                assert "technicals" not in record
                assert all(set(row) == expected_ohlcv_fields for row in record["ohlcv"])
            assert all("market_row" not in step for step in scenario["steps"])


def test_replay_calls_shipped_indicator_transform_with_explicit_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[object, IndicatorConfig]] = []
    shipped = replay_module.calculate_technicals

    def spy(frame: object, config: IndicatorConfig):
        calls.append((frame, config))
        return shipped(frame, config)

    monkeypatch.setattr(replay_module, "calculate_technicals", spy)
    scenarios = load_replay_bundle(FIXTURES / "full_day.json")
    run_replay_scenarios(scenarios)

    assert len(calls) == len(scenarios[0].market_history)
    expected_config = IndicatorConfig(**scenarios[0].policy["indicator_config"])
    for frame, config in calls:
        assert list(frame.columns) == ["시가", "고가", "저가", "종가", "거래량"]
        assert frame.index.is_monotonic_increasing
        assert frame.index.is_unique
        assert config == expected_config


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(extra=True),
    lambda d: d.update(schema_version=99),
])
def test_fixture_rejects_unknown_fields_and_versions(tmp_path: Path, mutation) -> None:
    data = json.loads((FIXTURES / "focused.json").read_text())
    mutation(data)
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError): load_replay_bundle(path)


def test_lookahead_guard_fails_loudly() -> None:
    with pytest.raises(FutureDataAccessError):
        guarded_historical_view(
            [{"observed_at": "2026-07-01T00:00:00+09:00"}],
            "2026-06-30T15:30:00+09:00",
        )


def test_boundary_catalog_matches_expected_actions() -> None:
    outcomes = run_replay_scenarios(load_replay_bundle(FIXTURES / "focused.json"))
    assert outcomes
    assert all(x.matched for x in outcomes)
    by_id = {x.scenario_id: x for x in outcomes}
    assert by_id["buy-at-threshold"].action == "BUY"
    assert by_id["buy-below-threshold"].action == "HOLD"
    assert by_id["malformed-signal"].has_order is False
    assert by_id["stop-loss-override"].position_quantity_after == 0


def test_required_boundaries_have_exactly_one_executed_attributed_check() -> None:
    outcomes = run_replay_scenarios(load_replay_bundle(FIXTURES / "focused.json"))
    verification = verify_replay_expectations(outcomes)
    assert verification.passed
    assert {check.boundary_id for check in verification.checks} == REQUIRED_BOUNDARIES
    assert len(verification.checks) == len(REQUIRED_BOUNDARIES)
    assert all(
        check.scenario_id and check.ticker and check.stage
        and check.expected and check.actual
        for check in verification.checks
    )


@pytest.mark.parametrize("kind", ["missing", "duplicate", "unknown"])
def test_boundary_bijection_fails_closed(kind: str) -> None:
    outcomes = list(run_replay_scenarios(load_replay_bundle(FIXTURES / "focused.json")))
    if kind == "missing":
        outcomes.pop()
    elif kind == "duplicate":
        outcomes.append(outcomes[0])
    else:
        outcomes[0] = outcomes[0].__class__(
            **{**outcomes[0].__dict__, "boundary_id": "unknown"}
        )
    verification = verify_replay_expectations(outcomes)
    assert verification.passed is False


def test_complete_result_helper_matches_replay_result() -> None:
    outcomes = run_replay_scenarios(load_replay_bundle(FIXTURES / "focused.json"))
    funnel = build_replay_funnel(outcomes)
    verification = verify_replay_expectations(outcomes)
    result = ReplayResult(_static_manifest(), outcomes, {}, funnel, verification)
    assert compute_result_id(
        result.manifest, result.outcomes, funnel=result.funnel,
        verification=result.verification, disclaimer=result.disclaimer,
    ) == result.result_id


@pytest.mark.parametrize("component", ["funnel", "verification", "disclaimer"])
def test_complete_result_identity_is_sensitive_to_all_deterministic_evidence(
    component: str,
) -> None:
    outcomes = run_replay_scenarios(load_replay_bundle(FIXTURES / "focused.json"))
    funnel = build_replay_funnel(outcomes)
    verification = verify_replay_expectations(outcomes)
    baseline = ReplayResult(_static_manifest(), outcomes, {}, funnel, verification)
    values = {
        "funnel": replace(funnel, evaluated=replace(funnel.evaluated, numerator=999)),
        "verification": replace(verification, passed=False),
        "disclaimer": baseline.disclaimer + " fixed",
    }
    kwargs = {
        "funnel": funnel,
        "verification": verification,
        "disclaimer": baseline.disclaimer,
    }
    kwargs[component] = values[component]
    changed = ReplayResult(
        baseline.manifest, baseline.outcomes, {"duration_ms": 999}, **kwargs
    )
    assert changed.result_id != baseline.result_id


def test_full_day_uses_production_rank_and_fill_state() -> None:
    outcomes = run_replay_scenarios(load_replay_bundle(FIXTURES / "full_day.json"))
    assert [x.ticker for x in outcomes] == ["000010", "000020", "000030"]
    assert outcomes[0].cash_after < 10_000_000
    assert outcomes[1].cash_after == outcomes[0].cash_after
    assert outcomes[1].position_quantity_after == 0


def test_historical_input_materially_drives_production_screener_rank(tmp_path: Path) -> None:
    data = json.loads((FIXTURES / "full_day.json").read_text())
    baseline = run_replay_scenarios(load_replay_bundle(FIXTURES / "full_day.json"))
    assert [outcome.ticker for outcome in baseline] == ["000010", "000020", "000030"]

    for record in data["scenarios"][0]["market_history"]:
        if record["ticker"] == "000020":
            record["technicals"]["atr_14"] = 80
            record["technicals"]["historical_volatility"] = 0.5
    path = tmp_path / "mutated-history.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    mutated = run_replay_scenarios(load_replay_bundle(path))
    assert [outcome.ticker for outcome in mutated] == ["000020", "000010", "000030"]


def test_full_day_daily_loss_progresses_and_blocks_later_buy() -> None:
    outcomes = run_replay_scenarios(load_replay_bundle(FIXTURES / "full_day.json"))
    assert [outcome.realized_loss_after for outcome in outcomes] == [500_000, 500_000, 500_000]
    assert outcomes[-1].ticker == "000030"
    assert outcomes[-1].action == "HOLD"
    assert outcomes[-1].blocked_reason == "RISK_BLOCK"


def test_fixture_rejects_future_rows_before_replay(tmp_path: Path) -> None:
    data = json.loads((FIXTURES / "focused.json").read_text())
    data["scenarios"][0]["market_history"][0]["ohlcv"].append({
        "observed_at": "2026-07-01T00:00:00+09:00",
        "open": 100,
        "high": 102,
        "low": 99,
        "close": 101,
        "volume": 1000,
    })
    path = tmp_path / "future.json"
    path.write_text(json.dumps(data))
    with pytest.raises(FutureDataAccessError): load_replay_bundle(path)


def test_funnel_has_explicit_denominators_and_monotonic_buy_stages() -> None:
    outcomes = run_replay_scenarios(load_replay_bundle(FIXTURES / "focused.json"))
    funnel = build_replay_funnel(outcomes)
    assert funnel.evaluated == type(funnel.evaluated)(len(outcomes), len(outcomes))
    assert funnel.buy_signaled.denominator == funnel.selected.numerator
    assert funnel.confidence_qualified.denominator == funnel.buy_signaled.numerator
    assert funnel.order_eligible.numerator <= funnel.validly_sized.numerator
    assert set(funnel.actions) == {"BUY", "HOLD", "SELL"}
    assert all(value.denominator == len(outcomes) for value in funnel.actions.values())
    assert list(funnel.blocked_reasons) == sorted(funnel.blocked_reasons)


def test_funnel_rejects_non_monotonic_normalized_facts() -> None:
    outcome = ReplayOutcome(
        "broken", "000001", 1, "HOLD", False, "NONE", "broken", 1, 0,
        "HOLD", True, selected=False, buy_signaled=True,
    )
    with pytest.raises(ValueError, match="monotonic"):
        build_replay_funnel((outcome,))


def test_verification_attributes_every_mismatch_and_json_has_disclaimer() -> None:
    outcome = ReplayOutcome(
        "scenario", "000001", 1, "HOLD", False, "NONE", "reason", 1, 0,
        "BUY", False,
    )
    verification = verify_replay_expectations((outcome,))
    assert verification.passed is False
    assert (verification.checks[0].scenario_id, verification.checks[0].ticker,
            verification.checks[0].stage) == ("scenario", "000001", "action")
    result = ReplayResult(
        _static_manifest(), (outcome,), {}, build_replay_funnel((outcome,)), verification
    )
    document = json.loads(result.normalized_bytes())
    assert "decision-policy paths only" in document["evidence"]["disclaimer"]
    forbidden = {"pnl", "return", "win_rate", "sharpe", "profitability"}
    assert not forbidden.intersection(document["evidence"])
