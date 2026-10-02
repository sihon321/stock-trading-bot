"""Test-owned saved evidence. Never copy or inspect an owner's runtime stores."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from itertools import count
from unittest.mock import patch
from uuid import UUID


NOW = datetime(2026, 10, 2, 1, 0, tzinfo=timezone.utc)
ACCOUNT_HASH = hashlib.sha256(b"synthetic-operator-account").hexdigest()
SECRET_SENTINEL = "sk-test-operator-secret-sentinel"


class FixedClock:
    def __init__(self, now=NOW):
        if now.tzinfo is None:
            raise ValueError("aware clock required")
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, **duration):
        self.now += timedelta(**duration)
        return self.now


class FakeTransport:
    def __init__(self, outcomes=(True,), *, max_calls=20):
        self.outcomes = list(outcomes)
        self.max_calls = max_calls
        self.calls = []

    def send(self, summary):
        if len(self.calls) >= self.max_calls or len(summary) > 4096:
            raise AssertionError("fake transport bound exceeded")
        self.calls.append(summary)
        if not self.outcomes:
            raise AssertionError("fake transport outcomes exhausted")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    __call__ = send


@dataclass(frozen=True)
class FixtureResource:
    id: str
    path: Path
    owner: str
    account_hash: str
    target: str

    @property
    def resource_id(self):
        return self.id


@dataclass(frozen=True)
class OperatorSources:
    resources: tuple[FixtureResource, ...]
    paths: dict[str, Path]
    clock: FixedClock
    expected_ids: dict[str, str]
    operational_db: Path
    artifact_root: Path
    account_hash: str = ACCOUNT_HASH

    def probe_registry(self):
        return {"sources": [str(p) for p in self.paths.values()],
                "writable_roots": [str(self.operational_db.parent), str(self.artifact_root)],
                "paths": {k: str(v) for k, v in self.paths.items()},
                "expected_ids": self.expected_ids}


def capture_sources(sources):
    """Capture bytes plus owner schema, tables and rows, with read-only connections."""
    captured = {}
    for name, path in sources.paths.items():
        content = path.read_bytes()
        if path.suffix == ".db":
            with sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True) as conn:
                schema = tuple(conn.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name"))
                tables = tuple(row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"))
                data = {table: tuple(conn.execute('SELECT * FROM "' + table.replace('"', '""') + '"')) for table in tables}
            captured[name] = (content, schema, data)
        else:
            captured[name] = content
    return captured


def make_operator_sources(tmp_path, scenario="linked"):
    if scenario not in {"linked", "unknown_marks", "incomplete_zero_cash", "broken_links", "scope_conflict"}:
        raise ValueError("unknown operator fixture scenario")
    root = Path(tmp_path).resolve()
    evidence = root / "sources"
    evidence.mkdir(parents=True)
    operation = root / "operation"
    operation.mkdir()
    artifact = root / "artifacts"
    artifact.mkdir()
    paths = {k: evidence / f"{k}.db" for k in ("audit", "soak", "controller")}

    # Writers run solely during test preparation, before the child tripwires.
    from trading_bot import sqlite_audit, soak_store
    from trading_bot.audit_models import RunKind, RunStatus, OrderEvent, OrderEventType
    from trading_bot.portfolio import (PortfolioSnapshot, PortfolioCompleteness, PortfolioHolding,
        PortfolioOrder, PortfolioFill, PortfolioAccountSummary)
    from trading_bot.portfolio_store import connect_portfolio_store, append_portfolio_snapshot
    from trading_bot.soak_controller import connect_controller

    with sqlite_audit.connect(paths["audit"]) as conn:
        for run_id, stamp, target in (("operator-run", NOW, "real" if scenario == "scope_conflict" else "mock"),
                                     ("historic-run", NOW - timedelta(days=40), "mock")):
            sqlite_audit.start_run(conn, run_id=run_id, trading_mode="mock", dry_run=False,
                run_kind=RunKind.RUN, status=RunStatus.COMPLETED,
                started_at=stamp.isoformat(), trading_date_kst=stamp.strftime("%Y%m%d"), target=target,
                provenance={"account_scope_hash": ACCOUNT_HASH})
        sqlite_audit.append_order_event(conn, OrderEvent("historic-intent", "historic-run",
            "historic-run", "000660", OrderEventType.INTENT_CREATED,
            observed_at=(NOW - timedelta(days=40)).isoformat()))
        event = SimpleNamespace(ticker="005930", final_action="HOLD", parsed_decision="HOLD",
            parse_error=None, risk_override=False, override_reason="", order_reason=SECRET_SENTINEL,
            broker_order_id=None)
        sqlite_audit.write_decision(conn, "operator-run", event, confidence=0.79,
            current_price=None, correlation_id="operator-decision", created_at=NOW.isoformat())
    conn.close()
    complete = scenario != "incomplete_zero_cash"
    snapshot = PortfolioSnapshot("operator-snapshot", ACCOUNT_HASH, NOW.date(),
        (NOW - timedelta(days=1)).date(), NOW,
        PortfolioCompleteness.COMPLETE if complete else PortfolioCompleteness.INCOMPLETE,
        "COMPLETE" if complete else "MISSING_PAGE", 1, 1 if complete else 0,
        (PortfolioHolding("005930", 3, 2, 70000),),
        (PortfolioOrder("broker-order-1", None, "005930", "SELL", 2, 1, 1, 0, 0,
                        71000, "PARTIALLY_FILLED", "20261002", "100000"),),
        (PortfolioFill("broker-fill-1", "broker-order-1", "005930", 1, 71000),),
        PortfolioAccountSummary(1000000 if complete else 0, 1210000 if complete else 0))
    conn = connect_portfolio_store(paths["audit"])
    append_portfolio_snapshot(conn, snapshot, cycle_id="operator-run", observation_id="operator-observation")
    conn.execute("INSERT INTO watch_iterations VALUES (?,?,?,?,?)",
                 ("operator-watch", "operator-run", snapshot.snapshot_id, NOW.isoformat(), "COMPLETED"))
    conn.execute("INSERT INTO watch_observations(iteration_id,state_code,detail_json,observed_at) VALUES (?,?,?,?)",
                 ("operator-watch", "ACTIVE", '{"reason_code":"COMPLETED"}', NOW.isoformat()))
    conn.commit()
    conn.close()
    conn = soak_store.connect_soak_store(paths["soak"])
    soak_store.create_campaign(conn, campaign_id="operator-campaign", accepted_profile_fingerprint="sha256:synthetic",
        accepted_profile_version="official-example-v1", field_contract_version="kis-mock-compat-v1",
        ambiguity_policy_version="ambiguity-v1", ambiguity_window_seconds=60,
        ambiguity_poll_cadence_seconds=5, ambiguity_max_observations=12, created_at=NOW.isoformat())
    soak_store.freeze_ticker(conn, freeze_id="historic-freeze", campaign_id="operator-campaign",
        ticker="000660", order_intent_id="missing-intent" if scenario == "broken_links" else "historic-intent",
        freeze_kind="AMBIGUITY", observed_at=(NOW - timedelta(days=40)).isoformat())
    conn.close()
    connect_controller(paths["controller"], paths["audit"], paths["soak"]).close()

    # Reuse established synthetic fixtures, not production stores. No paid/live provider.
    from test_reporting import _result
    from test_backtest_engine import run
    from trading_bot.backtest_reporting import build_backtest_result, write_backtest_result
    from test_shadow_runner import manifest, Fake
    from trading_bot.shadow_runner import run_shadow
    from trading_bot.shadow_reporting import build_shadow_result, write_shadow_result
    paths.update({k: evidence / f"{k}.json" for k in ("replay", "backtest", "shadow")})
    replay = _result(paths["replay"])
    backtest = build_backtest_result(run())
    write_backtest_result(backtest, paths["backtest"])
    sequence = count(1)
    # Replace only this module's UUID collaborator; unrelated writers keep their behavior.
    with patch("trading_bot.shadow_store.uuid", SimpleNamespace(uuid4=lambda: UUID(int=next(sequence)))):
        shadow = build_shadow_result(run_shadow(manifest(), operation / "fixture-shadow.db",
                                                provider_factory=lambda v, p: Fake([])))
    write_shadow_result(shadow, paths["shadow"])
    resources = tuple(FixtureResource(k, paths["audit"] if k == "portfolio" else paths[k],
        k, ACCOUNT_HASH, "simulated" if k in {"replay", "backtest", "shadow"} else "mock")
        for k in ("audit", "portfolio", "soak", "controller", "replay", "backtest", "shadow"))
    return OperatorSources(resources, paths, FixedClock(),
        {"snapshot": snapshot.snapshot_id, "run": "operator-run", "campaign": "operator-campaign",
         "freeze": "historic-freeze", "replay": replay.result_id,
         "backtest": backtest.result_id, "shadow": shadow.result_id},
        operation / "operator.db", artifact)
