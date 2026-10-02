"""Self-check the evidence and capability harness before downstream tests trust it."""

import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from operator_fixtures import make_operator_sources, capture_sources, FakeTransport, FixedClock


def rows(path, sql):
    with sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True) as conn:
        return conn.execute(sql).fetchall()


def test_links_scope_history_unknown_marks_and_no_read_mutation(tmp_path):
    sources = make_operator_sources(tmp_path, "linked")
    before = capture_sources(sources)
    assert rows(sources.paths["audit"], "SELECT target FROM runs WHERE run_id='operator-run'") == [("mock",)]
    scope, snapshot = rows(sources.paths["audit"], "SELECT account_scope_hash,snapshot_id FROM portfolio_snapshots")[0]
    assert scope == sources.account_hash and snapshot == sources.expected_ids["snapshot"]
    assert rows(sources.paths["audit"], "SELECT snapshot_id FROM watch_iterations") == [(snapshot,)]
    assert rows(sources.paths["audit"], "SELECT order_id FROM portfolio_orders") == [("broker-order-1",)]
    assert rows(sources.paths["audit"], "SELECT order_id FROM portfolio_fills") == [("broker-order-1",)]
    freeze = rows(sources.paths["soak"], "SELECT ticker,order_intent_id,state FROM soak_ticker_freezes")
    assert freeze == [("000660", "historic-intent", "FROZEN")]
    assert rows(sources.paths["audit"], "SELECT origin_run_id FROM order_events WHERE order_intent_id='historic-intent'") == [("historic-run",)]
    assert rows(sources.paths["audit"], "SELECT current_price FROM decisions") == [(None,)]
    assert before == capture_sources(sources)
    assert sources.operational_db.parent != sources.paths["audit"].parent
    assert {r.owner for r in sources.resources} >= {"audit", "portfolio", "soak", "controller", "replay", "backtest", "shadow"}


@pytest.mark.parametrize("scenario", ["incomplete_zero_cash", "broken_links", "scope_conflict", "unknown_marks"])
def test_adversarial_scenarios_are_real_saved_facts(tmp_path, scenario):
    sources = make_operator_sources(tmp_path, scenario)
    if scenario == "incomplete_zero_cash":
        assert rows(sources.paths["audit"], "SELECT completeness,available_cash FROM portfolio_snapshots") == [("INCOMPLETE", 0.0)]
    elif scenario == "broken_links":
        assert rows(sources.paths["soak"], "SELECT order_intent_id FROM soak_ticker_freezes") == [("missing-intent",)]
        assert rows(sources.paths["audit"], "SELECT COUNT(*) FROM order_events WHERE order_intent_id='missing-intent'") == [(0,)]
    elif scenario == "scope_conflict":
        assert rows(sources.paths["audit"], "SELECT target FROM runs WHERE run_id='operator-run'") == [("real",)]
        assert all(r.target == "mock" for r in sources.resources if r.owner in {"audit", "portfolio"})
    else:
        assert rows(sources.paths["audit"], "SELECT current_price FROM decisions") == [(None,)]


def test_saved_reports_validate_original_identities(tmp_path):
    from trading_bot.reporting import load_replay_results
    from trading_bot.backtest_reporting import load_backtest_result
    from trading_bot.shadow_reporting import load_shadow_result
    sources = make_operator_sources(tmp_path)
    before = capture_sources(sources)
    assert load_replay_results((sources.paths["replay"],))[0].stable_result_id == sources.expected_ids["replay"]
    assert load_backtest_result(sources.paths["backtest"]).result_id == sources.expected_ids["backtest"]
    assert load_shadow_result(sources.paths["shadow"],proof_catalog=sources.shadow_proof_catalog).result_id == sources.expected_ids["shadow"]
    assert before == capture_sources(sources)


def test_saved_report_fixtures_repeat_with_identical_content_and_ids(tmp_path):
    first = make_operator_sources(tmp_path / "first")
    second = make_operator_sources(tmp_path / "second")
    assert first.expected_ids == second.expected_ids
    for family in ("replay", "backtest", "shadow"):
        assert first.paths[family].read_bytes() == second.paths[family].read_bytes()


def probe(sources, action, module="json", **extra):
    registry = sources.probe_registry() | extra
    return subprocess.run([sys.executable, "tests/capability_probe.py", "--module", module,
                           "--action", action, "--registry", json.dumps(registry)],
                          text=True, capture_output=True, timeout=15)


@pytest.mark.parametrize("action,code", [
    ("selfcheck-constructor", "FORBIDDEN_IMPORT"), ("selfcheck-socket", "FORBIDDEN_NETWORK"),
    ("selfcheck-sql", "FORBIDDEN_SOURCE_SQL"), ("selfcheck-write", "FORBIDDEN_WRITE"),
    ("selfcheck-attach", "FORBIDDEN_SOURCE_SQL"), ("selfcheck-schema", "FORBIDDEN_SOURCE_SQL"),
    ("selfcheck-env", "FORBIDDEN_READ"),
])
def test_fresh_process_tripwires_reject_forbidden_operations(tmp_path, action, code):
    sources = make_operator_sources(tmp_path)
    before = capture_sources(sources)
    result = probe(sources, action)
    assert result.returncode == 23, result.stderr
    assert json.loads(result.stdout)["code"] == code
    assert before == capture_sources(sources)


def test_read_only_import_and_probe_without_shared_conftest(tmp_path):
    sources = make_operator_sources(tmp_path)
    result = probe(sources, "selfcheck-read", "trading_bot.reporting")
    assert result.returncode == 0, result.stdout + result.stderr
    body = json.loads(result.stdout)
    assert body["shared_conftest"] is False and body["ok"] is True
    assert body["result"]["count"] == 2


def test_socket_allowance_is_exact_loopback_only(tmp_path):
    sources = make_operator_sources(tmp_path)
    result = probe(sources, "selfcheck-loopback", allow_loopback=["127.0.0.1", 0])
    assert result.returncode == 0, result.stdout
    result = probe(sources, "selfcheck-remote", allow_loopback=["127.0.0.1", 0])
    assert result.returncode == 23 and json.loads(result.stdout)["code"] == "FORBIDDEN_NETWORK"


def test_clock_and_transport_are_bounded_and_deterministic():
    clock = FixedClock()
    old = clock()
    clock.advance(seconds=1800)
    assert (clock() - old).total_seconds() == 1800
    transport = FakeTransport([False, True], max_calls=2)
    assert transport.send("safe") is False and transport.send("safe") is True
    with pytest.raises(AssertionError, match="bound"):
        transport.send("third")


def test_browser_conftest_collection_is_lazy():
    code = ("import importlib.util,sys; s=importlib.util.spec_from_file_location('browser_harness',"
            "'tests/browser/conftest.py'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
            "assert 'trading_bot.web_app' not in sys.modules; "
            "assert 'trading_bot.config' not in sys.modules")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


def test_local_saved_server_serves_and_stops_without_app_import():
    import importlib.util
    import urllib.request
    from flask import Flask
    spec = importlib.util.spec_from_file_location("browser_harness", "tests/browser/conftest.py")
    harness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harness)
    app = Flask("fixture-selfcheck")
    app.add_url_rule("/", view_func=lambda: "saved fixture")
    with harness.serve_saved_app(app) as origin:
        assert origin.startswith("http://127.0.0.1:")
        assert urllib.request.urlopen(origin, timeout=3).read() == b"saved fixture"
    with pytest.raises(OSError):
        urllib.request.urlopen(origin, timeout=1)
