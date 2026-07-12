import json
from pathlib import Path

import pytest

from trading_bot.replay import (
    FutureDataAccessError,
    guarded_historical_view,
    load_replay_bundle,
    run_replay_scenarios,
)

FIXTURES = Path(__file__).parent / "fixtures" / "replay"


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
