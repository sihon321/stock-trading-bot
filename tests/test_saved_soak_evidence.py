"""Three-owner saved soak reads retain provenance without controller capability."""

from contextlib import closing
import hashlib
import json
import sqlite3
import subprocess
import sys

import pytest


PROBE = r'''
import builtins, importlib.abc, json, os, socket, sqlite3, sys
from pathlib import Path
forbidden = (
    'trading_bot.calibration', 'trading_bot.replay', 'trading_bot.execution',
    'trading_bot.config', 'trading_bot.soak_config', 'trading_bot.mock_broker',
    'trading_bot.brokers', 'trading_bot.providers', 'trading_bot.soak_store',
    'trading_bot.sqlite_audit', 'trading_bot.portfolio_store',
    'trading_bot.soak_controller', 'trading_bot.mutation_lease',
)
class Reject(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == name or fullname.startswith(name + '.') for name in forbidden):
            raise AssertionError('forbidden capability: ' + fullname)
sys.meta_path.insert(0, Reject())
def deny(*args, **kwargs):
    raise AssertionError('saved reader acquired socket/write capability')
socket.create_connection = socket.getaddrinfo = deny
def audit(event, args):
    if event.startswith('socket.'):
        deny()
    if event == 'open':
        mode, flags = args[1:3]
        if (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
            isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)
        ):
            deny()
    if event in ('os.remove', 'os.rename', 'os.mkdir', 'os.rmdir', 'os.link', 'os.symlink'):
        deny()
sys.addaudithook(audit)
real_connect = sqlite3.connect
def read_connection(database, *args, **kwargs):
    assert str(database).endswith('?mode=ro') and kwargs.get('uri') is True
    conn = real_connect(database, *args, **kwargs)
    def authorize(action, first, second, db, trigger):
        allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION,
                   sqlite3.SQLITE_TRANSACTION}
        if action == sqlite3.SQLITE_PRAGMA:
            return sqlite3.SQLITE_OK if first.lower() in ('query_only', 'user_version', 'table_info') and (second is None or first.lower() in ('query_only', 'table_info')) else sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY
    conn.set_authorizer(authorize)
    return conn
sqlite3.connect = read_connection
payload = json.loads(sys.argv[1])
'''


def _child(script, payload):
    child = subprocess.run(
        [sys.executable, "-B", "-c", PROBE + script, json.dumps(payload)],
        capture_output=True, text=True, timeout=20,
    )
    assert child.returncode == 0, child.stderr
    return json.loads(child.stdout)


def _inventory(paths):
    result = {}
    for path in paths:
        with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)) as conn:
            result[str(path)] = (
                path.read_bytes(), conn.execute("PRAGMA user_version").fetchone()[0],
                tuple(conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name")),
                tuple(conn.iterdump()),
            )
    return result


def _sources(tmp_path, broken=None):
    from test_soak_reporting import _stores, _write_primary_intent, _write_resume_comparison
    from trading_bot import soak_store
    from trading_bot.portfolio_store import connect_portfolio_store
    from trading_bot.soak_controller import (
        append_controller_observation, commit_drill_contract, connect_controller,
        finalize_drill, prepare_drill,
    )
    from trading_bot.soak_models import DrillVerdict, FaultName, InjectionBoundary, SoakEvidenceClass
    paths = _stores(tmp_path)
    connect_portfolio_store(paths[0]).close()
    _write_primary_intent(paths[0])
    _write_resume_comparison(paths[1])
    with closing(connect_controller(paths[2], *paths[:2])) as controller:
        prepare_drill(controller, campaign_id="campaign-1", drill_id="controlled-1",
                      fault=FaultName.STALE_DATA, boundary=InjectionBoundary.DATA,
                      expected_containment=("NO_ORDER_POST",),
                      required_observations=("CONTAINMENT_CHECKED",), policy_version="fault-drill-v1")
        commit_drill_contract(controller, drill_id="controlled-1")
        append_controller_observation(controller, drill_id="controlled-1",
                                      observation_type="CONTAINMENT_CHECKED",
                                      evidence_class=SoakEvidenceClass.CONTROLLED_INJECTION,
                                      facts={"passed": True})
        finalize_drill(controller, drill_id="controlled-1", requested_verdict=DrillVerdict.PASSED)
    with closing(soak_store.connect_soak_store(paths[1])) as soak:
        soak_store.designate_day(soak, campaign_id="campaign-1", trading_date="2026-07-20",
                                run_id="primary-run", run_kind="RUN", terminal=True,
                                credit_state="CREDITED")
        soak_store.append_campaign_event(soak, campaign_id="campaign-1",
                                         run_id="run-closed", event_code="DAY_NOT_CREDITED")
        soak_store.freeze_ticker(soak, freeze_id="freeze-history", campaign_id="campaign-1",
                                 ticker="000660", order_intent_id="intent-resume", freeze_kind="AMBIGUITY")
        soak_store.transition_freeze(soak, freeze_id="freeze-history",
                                     release_evidence_type="COMPARISON",
                                     release_evidence_id="resume-comparison")
        for link_id, evidence_class, verdict, drill_id in (
            ("controlled-link", "CONTROLLED_INJECTION", "PASSED", "controlled-1"),
            ("kis-link", "KIS_OBSERVED", "UNKNOWN", "kis-1"),
            ("synthetic-link", "SYNTHETIC", "PASSED", "synthetic-1"),
        ):
            soak_store.append_drill_link(soak, link_id=link_id, campaign_id="campaign-1",
                                         drill_id=drill_id, evidence_class=evidence_class, verdict=verdict)
    if broken:
        with closing(sqlite3.connect(paths[1])) as conn:
            table = "soak_ticker_freezes" if broken == "release" else (
                "soak_drill_links" if broken == "drill" else "soak_comparisons")
            for (name,) in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name=?", (table,)
            ).fetchall():
                conn.execute('DROP TRIGGER "' + name.replace('"', '""') + '"')
            if broken == "primary":
                conn.execute("UPDATE soak_comparisons SET order_intent_id='missing-intent'")
            elif broken == "snapshot":
                conn.execute("UPDATE soak_comparisons SET snapshot_id='missing-snapshot'")
            elif broken == "drill":
                conn.execute("UPDATE soak_drill_links SET drill_id='missing-contract' WHERE evidence_class='CONTROLLED_INJECTION'")
            else:
                conn.execute("UPDATE soak_ticker_freezes SET release_evidence_id='missing' WHERE state='RELEASED'")
            conn.commit()
    return paths


@pytest.mark.parametrize("broken", [None, "primary", "snapshot", "drill", "release"])
def test_soak_load_build_render_in_fresh_child_preserves_links(tmp_path, broken):
    paths = _sources(tmp_path, broken)
    before = _inventory(paths)
    files_before = set(tmp_path.iterdir())
    result = _child("""
from dataclasses import asdict
from trading_bot.soak_reporting import ReadOnlySoakRepository, build_soak_report, render_soak_report
repo = ReadOnlySoakRepository(*(Path(p) for p in payload['paths']))
assert repo.load('campaign-1')['campaign']['campaign_id'] == 'campaign-1'
report = build_soak_report(repo, 'campaign-1')
assert report.campaign.credited_days == 1 and report.campaign.designated_runs == 1
assert report.campaign.non_credit_runs == 1 and report.campaign.target_days == 20
assert report.campaign.availability_used == 0 and report.campaign.availability_budget == 2
coverage = {d.evidence_class.value: d for d in report.drills}
assert coverage['KIS_OBSERVED'].required == 1 and coverage['KIS_OBSERVED'].unknown == 1
assert coverage['SYNTHETIC'].required == 1 and coverage['SYNTHETIC'].passed == 1
controlled = coverage['CONTROLLED_INJECTION']
assert controlled.required == 1
assert controlled.passed == (0 if payload['broken'] == 'drill' else 1)
assert controlled.unknown == (1 if payload['broken'] == 'drill' else 0)
if payload['broken'] in ('primary', 'snapshot', 'release'):
    assert report.freezes.active_count == 1 and report.resolved_historical_ambiguity == 0
else:
    assert report.freezes.active_count == 0 and report.resolved_historical_ambiguity == 1
assert (report.cross_store_unknown > 0) == bool(payload['broken'])
assert report.reconciliation.total == 2
try:
    repo.load("campaign-1' OR 1=1 --")
except KeyError:
    pass
else:
    raise AssertionError('campaign parameter bypassed')
text = render_soak_report(report)
assert 'UNKNOWN=' in text and 'combined' not in text.lower()
print(json.dumps({'report': asdict(report), 'text': text}))
""", {"paths": [str(p) for p in paths], "broken": broken})
    if broken is None:
        assert hashlib.sha256(result["text"].encode()).hexdigest() == (
            "be50512fb818b1b297a6dec996785a443e9139cac0be399f0928fd8915b13453"
        )
    assert _inventory(paths) == before
    assert set(tmp_path.iterdir()) == files_before


@pytest.mark.parametrize("owner", [0, 1, 2])
@pytest.mark.parametrize("corruption", ["version", "column", "table"])
def test_soak_owner_schema_fail_closed_in_fresh_child(tmp_path, owner, corruption):
    paths = _sources(tmp_path)
    with closing(sqlite3.connect(paths[owner])) as conn:
        if corruption == "version":
            conn.execute("PRAGMA user_version=999")
        elif corruption == "column":
            table = ("runs", "soak_campaigns", "drill_contracts")[owner]
            conn.execute(f"ALTER TABLE {table} ADD COLUMN unsupported TEXT")
        elif owner == 0:
            conn.execute("DROP TABLE notification_attempts")
        else:
            conn.execute("CREATE TABLE unsupported (value TEXT)")
        conn.commit()
    before = _inventory(paths)
    assert _child("""
from trading_bot.soak_reporting import ReadOnlySoakRepository, build_soak_report
try:
    build_soak_report(ReadOnlySoakRepository(*(Path(p) for p in payload['paths'])), 'campaign-1')
except RuntimeError as exc:
    assert 'unsupported' in str(exc)
    print('true')
else:
    raise AssertionError('unsupported owner schema accepted')
""", {"paths": [str(p) for p in paths]}) is True
    assert _inventory(paths) == before


def test_soak_missing_inode_alias_and_shared_schema_contracts(tmp_path):
    paths = _sources(tmp_path)
    alias = tmp_path / "alias.db"
    alias.hardlink_to(paths[0])
    before = _inventory((*paths, alias))
    assert _child("""
from trading_bot import evidence_contracts as contracts, soak_reporting as reports
assert reports._PRIMARY_SCHEMA is contracts.PRIMARY_REPORT_SCHEMA
assert reports._SOAK_SCHEMA is contracts.SOAK_REPORT_SCHEMA
assert reports._CONTROLLER_SCHEMA is contracts.CONTROLLER_REPORT_SCHEMA
assert reports.SCHEMA_VERSION == contracts.PRIMARY_AUDIT_SCHEMA_VERSION
assert reports.SOAK_SCHEMA_VERSION == contracts.SOAK_SCHEMA_VERSION
assert reports.CONTROLLER_SCHEMA_VERSION == contracts.CONTROLLER_SCHEMA_VERSION
for paths, error in (
    ([payload['paths'][0], payload['alias'], payload['paths'][2]], ValueError),
    ([payload['missing'], *payload['paths'][1:]], FileNotFoundError),
):
    try:
        reports.ReadOnlySoakRepository(*(Path(p) for p in paths))
    except error:
        pass
    else:
        raise AssertionError('missing or aliased evidence source accepted')
print('true')
""", {"paths": [str(p) for p in paths], "alias": str(alias),
      "missing": str(tmp_path / "missing.db")}) is True
    assert _inventory((*paths, alias)) == before
    assert not (tmp_path / "missing.db").exists()
