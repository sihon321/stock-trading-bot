import json
import hashlib
import subprocess
from pathlib import Path

import pytest

from trading_bot.replay import (
    FutureDataAccessError,
    ReplayManifest,
    ReplayOutputError,
    ReplayResult,
    build_replay_manifest,
    canonical_json_bytes,
    compute_result_id,
    guarded_historical_view,
    load_replay_bundle,
    run_replay_scenarios,
    write_replay_result,
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


def test_full_day_uses_production_rank_and_fill_state() -> None:
    outcomes = run_replay_scenarios(load_replay_bundle(FIXTURES / "full_day.json"))
    assert [x.ticker for x in outcomes] == ["000010", "000020"]
    assert outcomes[0].cash_after < 10_000_000
    assert outcomes[1].cash_after == outcomes[0].cash_after
    assert outcomes[1].position_quantity_after == 0


def test_fixture_rejects_future_rows_before_replay(tmp_path: Path) -> None:
    data = json.loads((FIXTURES / "focused.json").read_text())
    data["scenarios"][0]["market_history"].append({"observed_at":"2026-07-01T00:00:00+09:00","close":1})
    path = tmp_path / "future.json"
    path.write_text(json.dumps(data))
    with pytest.raises(FutureDataAccessError): load_replay_bundle(path)
