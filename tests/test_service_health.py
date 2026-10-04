"""Offline owner-store health proof; no runtime tick is needed for obligations."""
from datetime import timedelta
import sqlite3
import pytest

from service_fixtures import TempServiceTopology, FakeServiceClock, NOW, SCOPE, session_evidence
from trading_bot.service_store import ServiceJournal
from trading_bot.control_store import ControlStore
from trading_bot.service_models import ExpectationInputs, AppliedControl, InstallationScope, OwnerLoginEvidence
from trading_bot.service_schedule import derive_expectations
from trading_bot.web_config import ResourceDescriptor, WebSettings
from trading_bot.web_evidence import OperatorEvidenceService
from trading_bot.web_models import ResourceScope


def health_fixture(tmp_path, *, calendar='normal', mode='RUNNING', enabled=True, login='CONFIRMED'):
    topology = TempServiceTopology(tmp_path)
    settings = topology.registration()
    clock = FakeServiceClock(NOW - timedelta(hours=1))
    journal = ServiceJournal(settings, clock=clock)
    journal.initialize()
    ControlStore(settings, clock=clock).initialize(actor='synthetic-owner')
    inputs = ExpectationInputs(registered_scopes=(SCOPE,), service_enabled=enabled,
        mode='KIS_MOCK' if enabled else 'DISABLED', config_hash='c'*64,
        config_effective_at=clock(), login_evidence=OwnerLoginEvidence(owner_uid=__import__('os').getuid(),
        gui_session_id='fixture' if login=='CONFIRMED' else None, source_id='login',
        observed_at=clock(), effective_at=clock(), state=login), session=session_evidence(calendar),
        effective_controls=AppliedControl(revision=0, mode=mode, request_id=None,
        applied_at=clock(), safety_evidence_ids=()), control_scope=InstallationScope(registered_scopes=(SCOPE,)),
        controls_source_id='control', controls_observed_at=clock(), controls_effective_at=clock())
    for expectation in derive_expectations(inputs, clock()):
        journal.expectation_writer().record_derived(expectation)
    resources = tuple(ResourceDescriptor(id=owner, owner=owner, path=path,
        account_hash=SCOPE.account_scope_hash, target='mock') for owner, path in (
        ('service', topology.service_db_path), ('control', topology.control_db_path)))
    reader = OperatorEvidenceService(WebSettings(operational_db_path=topology.web_db_path,
        artifact_root=tmp_path/'exports', registered_resources=resources), clock=clock)
    return reader, journal, clock, topology


def test_owner_migrated_pure_schema_and_query_only_bytes(tmp_path):
    from trading_bot import evidence_contracts as contracts
    reader, _, clock, topology = health_fixture(tmp_path)
    for owner, path in (('SERVICE', topology.service_db_path), ('CONTROL', topology.control_db_path)):
        schema = getattr(contracts, owner+'_REPORT_SCHEMA')
        with sqlite3.connect(path) as conn:
            assert set(schema) == {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table, columns in schema.items():
                assert columns == {r[1] for r in conn.execute(f'PRAGMA table_info({table})')}
    before = [p.read_bytes() for p in (topology.service_db_path, topology.control_db_path)]
    clock.advance(3700)
    view = reader.overview(ResourceScope(SCOPE.account_scope_hash, 'mock'))
    assert view.service_health
    reader.observe_alert_sources()
    assert before == [p.read_bytes() for p in (topology.service_db_path, topology.control_db_path)]


def test_absent_runtime_missed_obligation_preserves_provenance(tmp_path):
    reader, _, clock, _ = health_fixture(tmp_path)
    clock.advance(4800)
    daily = next(h for h in reader.service_health() if h.kind=='DAILY')
    risk = next(h for h in reader.service_health() if h.kind=='RISK')
    assert daily.state == 'MISSED_SCHEDULE'
    assert risk.state == 'WORKER_STALLED'
    assert daily.expected_running is True and daily.producer_kind == 'OBSERVER_DERIVED'
    assert daily.envelope.source_observed_at < daily.envelope.query_at
    assert daily.session_source_id and daily.login_source_id and daily.config_hash
    assert daily.source_ids and daily.last_progress_at is None
    saved = daily.envelope.source_observed_at
    clock.advance(30)
    assert next(h for h in reader.service_health() if h.kind=='DAILY').envelope.source_observed_at == saved


@pytest.mark.parametrize('options', [dict(calendar='holiday'), dict(enabled=False), dict(login='ABSENT')])
def test_positive_not_expected_negatives(tmp_path, options):
    reader, _, clock, _ = health_fixture(tmp_path, **options)
    clock.advance(4200)
    assert all(h.expected_running is False and h.state=='NOT_EXPECTED' for h in reader.service_health())


def test_pause_keeps_risk_observation_expected(tmp_path):
    reader, _, clock, _ = health_fixture(tmp_path, mode='PAUSED')
    clock.advance(4200)
    health = {h.kind:h for h in reader.service_health()}
    assert health['DAILY'].expected_running is False
    assert health['RISK'].expected_running is True


@pytest.mark.parametrize('options', [dict(calendar='unknown'), dict(login='UNKNOWN')])
def test_unknown_input_never_invents_miss_or_recovery(tmp_path, options):
    reader, _, clock, _ = health_fixture(tmp_path, **options)
    clock.advance(4200)
    assert all(h.state=='EXPECTATION_UNKNOWN' and h.expected_running is None for h in reader.service_health())


def test_midnight_needs_exact_date_source(tmp_path):
    reader, _, clock, _ = health_fixture(tmp_path)
    clock.advance(18*3600)
    assert all(h.state=='EXPECTATION_UNKNOWN' for h in reader.service_health())


@pytest.mark.parametrize('owner', ['service','control'])
def test_schema_drift_blocks_saved_projection(tmp_path, owner):
    reader, _, _, topology = health_fixture(tmp_path)
    path = getattr(topology, owner+'_db_path')
    with sqlite3.connect(path) as conn:
        conn.execute(f"UPDATE {owner}_metadata SET version=999")
    status = next(s for s in reader.source_status() if s.schema_owner==owner)
    assert status.query_status=='FAILED'
    if owner=='service':
        assert reader.service_health()[0].state=='SERVICE_SOURCE_UNAVAILABLE'


def test_reader_imports_no_service_control_writer_or_composition():
    import subprocess, sys
    script = '''
import importlib.abc, sys
class Reject(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {'trading_bot.service_store','trading_bot.control_store','trading_bot.service_runtime','trading_bot.service_composition'}:
            raise AssertionError(fullname)
sys.meta_path.insert(0, Reject())
import trading_bot.web_evidence
'''
    result = subprocess.run([sys.executable,'-c',script], capture_output=True,text=True)
    assert result.returncode==0, result.stderr


def test_stale_runtime_heartbeat_and_manual_attention_do_not_imply_health(tmp_path):
    reader, journal, clock, _ = health_fixture(tmp_path)
    with journal.connection() as conn:
        conn.execute('INSERT INTO service_generations VALUES(?,?,?,?,?,?,?)',
            ('fixture',SCOPE.account_scope_hash,'mock',__import__('os').getpid(),clock().timestamp(),None,'RUNNING'))
    clock.advance(3700)
    journal.heartbeat('service-leader','fixture',phase='RECOVERY_BLOCKED')
    risk=next(h for h in reader.service_health() if h.kind=='RISK')
    assert risk.state=='RECOVERY_BLOCKED' and risk.mutation_ready is False
    clock.advance(121)
    assert next(h for h in reader.service_health() if h.kind=='RISK').state=='WORKER_STALLED'
    with journal.connection() as conn:
        conn.execute("INSERT INTO service_attention_events VALUES(NULL,'MANUAL_ATTENTION','RESTART_EXHAUSTED',?)",(clock().timestamp(),))
    health=reader.service_health()
    assert next(h for h in health if h.kind=='RISK').state=='SERVICE_MANUAL_ATTENTION'
    assert all(h.manual_attention for h in health)


def test_global_control_owner_scope_mismatch_is_unavailable(tmp_path):
    reader, _, _, topology=health_fixture(tmp_path)
    with sqlite3.connect(topology.control_db_path) as conn:
        conn.execute('DROP TRIGGER control_request_audit_no_update')
        conn.execute("UPDATE control_request_audit SET scope_hash=?",('f'*64,))
    assert reader.control_states()[0].envelope.query_status=='FAILED'
    assert all(h.state=='EXPECTATION_UNKNOWN' for h in reader.service_health())
