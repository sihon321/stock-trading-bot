"""Saved advisory reductions must not acquire execution or writer capabilities."""

import hashlib
from contextlib import closing
import json
import sqlite3
import subprocess
import sys

import pytest


# Runs before any trading_bot import in a clean interpreter, independent of conftest.
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


SAVED_ROWS = [
    dict(variant_id=variant_id, metrics=dict(
        evaluated=3, denominator=3, buy_actions=1, hold_actions=1, sell_actions=1,
        order_eligible=opportunity, low_confidence=0, risk_blocks=risk,
        stop_loss_triggers=0, take_profit_triggers=0, exposure_total=exposure,
        expectation_deltas=0,
    ))
    for variant_id, risk, exposure, opportunity in (
        ("BASELINE", 1, 500_000.0, 2),
        ("BUY_CONFIDENCE_085", 0, 400_000.0, 1),
        ("MAX_POSITION_500000", 1, 300_000.0, 1),
    )
]

LOAD_ROWS = '''
from trading_bot.calibration_evidence import (
    VariantEvaluation, VariantMetrics, build_variant_catalog, judge_variants,
)
catalog = {v.variant_id: v for v in build_variant_catalog()}
rows = tuple(VariantEvaluation(catalog[r['variant_id']], VariantMetrics(**r['metrics']), ())
             for r in payload['rows'])
'''


def _child(script, payload):
    child = subprocess.run(
        [sys.executable, "-B", "-c", PROBE + script, json.dumps(payload)],
        capture_output=True, text=True, timeout=20,
    )
    assert child.returncode == 0, child.stderr
    return json.loads(child.stdout)


def test_pure_judgment_in_fresh_child_from_saved_rows():
    result = _child(LOAD_ROWS + '''
from dataclasses import asdict, replace
judgment = judge_variants(rows)
try:
    judge_variants((rows[0], replace(rows[1], metrics=replace(rows[1].metrics,
                    evaluated=4, denominator=4))))
except ValueError as exc:
    assert 'one denominator' in str(exc)
else:
    raise AssertionError('malformed saved denominator accepted')
print(json.dumps(asdict(judgment)))
''', {"rows": SAVED_ROWS})
    assert result == dict(
        status="PROVISIONAL_CANDIDATE", selected_variant_id="BUY_CONFIDENCE_085",
        ranked_variant_ids=["BUY_CONFIDENCE_085", "MAX_POSITION_500000", "BASELINE"],
        risk_event_delta=-1, exposure_delta=-100_000.0, order_eligible_delta=-1,
    )


def test_legacy_calibration_exports_are_identical_and_catalog_is_frozen():
    from trading_bot import calibration as legacy, calibration_evidence as pure
    from trading_bot.replay_evidence import canonical_json_bytes
    for name in (*pure.__all__, "_CANDIDATES", "_risk_events"):
        assert getattr(legacy, name) is getattr(pure, name)
    assert "evaluate_variants" not in pure.__dict__
    assert hashlib.sha256(canonical_json_bytes(pure.build_variant_catalog())).hexdigest() == (
        "69c54b1500d054cce561f6d45bf41179a8f6083eb9e6d535f81ab7bf789c6262"
    )


@pytest.mark.parametrize("module", ["trading_bot.replay", "trading_bot.soak_store"])
def test_probe_rejects_forbidden_imports(module):
    result = _child('''
try:
    __import__(payload['module'])
except AssertionError:
    print('true')
else:
    raise AssertionError('probe did not reject capability')
''', {"module": module})
    assert result is True


def _calibration_sources(tmp_path):
    from test_calibration_reporting import _run, _stores
    from trading_bot import soak_store
    from trading_bot.audit_models import RunStatus
    from trading_bot.portfolio_store import connect_portfolio_store
    paths = _stores(tmp_path)
    connect_portfolio_store(paths[0]).close()  # Independently owned extra primary tables.
    _run(*paths, index=1)
    _run(*paths, index=2, status=RunStatus.FAILED)
    with closing(soak_store.connect_soak_store(paths[1])) as conn:
        soak_store.designate_day(conn, campaign_id="campaign-1", trading_date="2026-07-03",
                                run_id="missing-primary", run_kind="RUN", terminal=True,
                                credit_state="CREDITED")
    return paths


def _source_inventory(paths):
    result = {}
    for path in paths:
        with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)) as conn:
            result[str(path)] = (
                path.read_bytes(), conn.execute("PRAGMA user_version").fetchone()[0],
                tuple(conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name")),
                tuple(conn.iterdump()),
            )
    return result


def _saved_evaluations():
    from trading_bot.calibration_evidence import VariantEvaluation, VariantMetrics, build_variant_catalog
    catalog = {v.variant_id: v for v in build_variant_catalog()}
    return tuple(VariantEvaluation(catalog[r["variant_id"]], VariantMetrics(**r["metrics"]), ())
                 for r in SAVED_ROWS)


def test_saved_calibration_load_build_render_in_fresh_child(tmp_path):
    paths = _calibration_sources(tmp_path)
    before = _source_inventory(paths)
    files_before = set(tmp_path.iterdir())
    result = _child(LOAD_ROWS + '''
from dataclasses import asdict
from trading_bot.calibration_reporting import (
    ReadOnlyCalibrationEvidenceRepository, build_calibration_report, render_calibration_report,
)
repo = ReadOnlyCalibrationEvidenceRepository(*(Path(p) for p in payload['paths']))
evidence = repo.load('campaign-1')
assert asdict(evidence.source_counts) == dict(eligible_days=3, normal_cycles=1,
                                           excluded_cycles=1, unknown_cycles=1)
assert evidence.excluded_cycle_ids == ('run-2',)
assert evidence.unknown_cycle_ids == ('missing-primary',)
assert evidence.grade.value == 'INSUFFICIENT'
report = build_calibration_report(evidence, rows, source_identities=('source-a',))
text = render_calibration_report(report)
assert 'unknown_cycles=1' in text and 'UNEVALUABLE_MISSING_PORTFOLIO_STATE' in text
assert report.judgment.selected_variant_id == 'BUY_CONFIDENCE_085'
assert len(report.rows) == 3
assert next(r for r in report.rows if r.selected).risk_event_delta == -1
try:
    build_calibration_report(evidence, (), source_identities=('source-a',))
except ValueError:
    pass
else:
    raise AssertionError('missing saved evaluations were filled')
try:
    repo.load('missing-campaign')
except KeyError:
    pass
else:
    raise AssertionError('missing campaign accepted')
print(json.dumps({'id': report.calibration_id, 'text': text}))
''', {"paths": [str(p) for p in paths], "rows": SAVED_ROWS})
    assert result["id"] == "21fbfeb3ea35609a0cf85df1c6b9a6cd112363ffca3d2150a3964b6df7d2a19c"
    assert hashlib.sha256(result["text"].encode()).hexdigest() == (
        "dde4ef760eff8c04e5df394a89390880fb92cc6e6b795f01bbdfef5f23e82f79"
    )
    assert _source_inventory(paths) == before
    assert set(tmp_path.iterdir()) == files_before


@pytest.mark.parametrize("owner,corruption", [
    (0, "version"), (1, "version"), (0, "column"), (1, "column"),
    (0, "missing_table"), (1, "extra_table"),
])
def test_calibration_owner_schema_rejected_in_fresh_child(tmp_path, owner, corruption):
    paths = _calibration_sources(tmp_path)
    with sqlite3.connect(paths[owner]) as conn:
        if corruption == "version":
            conn.execute("PRAGMA user_version=999")
        elif corruption == "column":
            table = "runs" if owner == 0 else "soak_campaigns"
            conn.execute(f"ALTER TABLE {table} ADD COLUMN unsupported TEXT")
        elif corruption == "missing_table":
            conn.execute("DROP TABLE notification_attempts")
        else:
            conn.execute("CREATE TABLE unsupported (value TEXT)")
    before = _source_inventory(paths)
    assert _child('''
from trading_bot.calibration_reporting import ReadOnlyCalibrationEvidenceRepository
try:
    ReadOnlyCalibrationEvidenceRepository(*(Path(p) for p in payload['paths'])).load('campaign-1')
except RuntimeError as exc:
    assert 'unsupported' in str(exc)
    print('true')
else:
    raise AssertionError('unsupported owner schema accepted')
''', {"paths": [str(p) for p in paths]}) is True
    assert _source_inventory(paths) == before


def test_calibration_missing_and_inode_alias_fail_without_creation(tmp_path):
    paths = _calibration_sources(tmp_path)
    alias = tmp_path / "alias.db"
    alias.hardlink_to(paths[0])
    before = _source_inventory((*paths, alias))
    assert _child('''
from trading_bot.calibration_reporting import ReadOnlyCalibrationEvidenceRepository
for primary, soak, error in (
    (payload['primary'], payload['alias'], ValueError),
    (payload['missing'], payload['soak'], FileNotFoundError),
):
    try:
        ReadOnlyCalibrationEvidenceRepository(Path(primary), Path(soak))
    except error:
        pass
    else:
        raise AssertionError('missing or aliased source accepted')
print('true')
''', dict(primary=str(paths[0]), soak=str(paths[1]), alias=str(alias),
         missing=str(tmp_path / "missing.db"))) is True
    assert _source_inventory((*paths, alias)) == before
    assert not (tmp_path / "missing.db").exists()


READINESS_FACTS = dict(
    replay_verified=True, credited_days=20, target_days=20, safety_failure_code=None,
    reconciliation_incomplete=0, reconciliation_unknown=0, active_freezes=0,
    cross_store_unknown=0, reports_complete=True, unresolved_orders=0,
    calibration_valid=True, calibration_id="a" * 64, policy_frozen=True,
    resolved_historical_ambiguity=0, source_identities=["source-a"],
)


@pytest.mark.parametrize("unknown_field", [None, "replay_verified", "reports_complete",
                                          "calibration_valid", "policy_frozen"])
def test_readiness_build_render_in_own_fresh_child(unknown_field):
    result = _child('''
from dataclasses import replace
from trading_bot.promotion_readiness import (
    ReadinessEvidence, build_readiness_assessment, render_readiness_assessment,
)
facts = payload['facts']
facts['source_identities'] = tuple(facts['source_identities'])
evidence = ReadinessEvidence(**facts)
def build(e):
    return build_readiness_assessment(e, policy_snapshot=(('buy_confidence_threshold', 0.8),),
                                    rollback_ack=True, kill_ack=True, manual_approval=True)
baseline = build(evidence)
result = build(replace(evidence, **{payload['unknown']: None})) if payload['unknown'] else baseline
assert len(result.checks) == 9
assert [c.code for c in result.checks] == [
    'REPLAY_VERIFIED', 'SOAK_ACCEPTED', 'REPORTS_COMPLETE', 'ORDERS_RESOLVED',
    'CALIBRATION_VALID', 'POLICY_FROZEN', 'ROLLBACK_ACK', 'KILL_ACK', 'MANUAL_APPROVAL']
assert result.state.value == ('BLOCKED' if payload['unknown'] else 'READY')
assert any(c.state.value == 'UNKNOWN' for c in result.checks) == bool(payload['unknown'])
assert build(replace(evidence, active_freezes=1)).state.value == 'BLOCKED'
assert build(replace(evidence, cross_store_unknown=1)).state.value == 'BLOCKED'
assert build(replace(evidence, resolved_historical_ambiguity=2)).warnings == (
    'RESOLVED_HISTORICAL_AMBIGUITY:2',)
assert '주문을 제출할 권한이 없습니다' in render_readiness_assessment(result)
try:
    build(replace(evidence, unresolved_orders=-1))
except ValueError:
    pass
else:
    raise AssertionError('negative counts accepted')
print(json.dumps({'baseline_id': baseline.assessment_id, 'id': result.assessment_id}))
''', {"facts": READINESS_FACTS, "unknown": unknown_field})
    assert result["baseline_id"] == "19cfe199f4ac5a933eea4cb674826c1fc23a64fc3f1a2e7e7f0e6b17e143c6c9"
    assert (result["id"] != result["baseline_id"]) == bool(unknown_field)
