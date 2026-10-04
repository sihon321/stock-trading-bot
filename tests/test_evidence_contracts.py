"""Independent evidence imports and owner-schema drift gates."""

import importlib
import sqlite3
import subprocess
import sys

import pytest


FORBIDDEN = (
    'trading_bot.replay', 'trading_bot.execution', 'trading_bot.mock_broker',
    'trading_bot.brokers', 'trading_bot.providers', 'trading_bot.config',
    'trading_bot.mutation_lease', 'trading_bot.sqlite_audit',
    'trading_bot.portfolio_store', 'trading_bot.soak_store',
    'trading_bot.soak_controller',
)


def test_reporting_fresh_import_has_no_execution_or_writer_capability():
    script = f'''
import importlib.abc, sys
forbidden = {FORBIDDEN!r}
class Reject(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == name or fullname.startswith(name + '.') for name in forbidden):
            raise AssertionError('forbidden capability: ' + fullname)
sys.meta_path.insert(0, Reject())
import trading_bot.reporting
import trading_bot.evidence_contracts
assert not any(name in sys.modules for name in forbidden)
'''
    result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_replay_exports_and_frozen_utf8_identity():
    from trading_bot import replay, replay_evidence as pure
    for name in ('ReplayManifest', 'ReplayOutcome', 'ReplayResult', 'ReplayCount',
                 'ReplayFunnel', 'ReplayCheck', 'ReplayVerification',
                 'canonical_json_bytes', 'compute_result_id', 'build_replay_funnel',
                 'verify_replay_expectations', 'NON_PROFITABILITY_DISCLAIMER'):
        assert getattr(replay, name) is getattr(pure, name)
    manifest = pure.ReplayManifest('a'*64, 'b'*64, 'c'*64, {'이유': '보유'},
                                   'd'*40, 'e'*64, 'clean', {'cash': 100},
                                   '2026-07-01T15:30:00+09:00', '20260701', 1)
    result = pure.ReplayResult(manifest, ({'action': 'HOLD', '이유': '보유'},), {})
    assert result.result_id == '9bed5e5f217b5eb53831ff55c8ac93c761300e0e219f276ba5f7c1550170dceb'
    assert pure.canonical_json_bytes({'z': [2, 1], '이유': '보유'}) == '{"z":[2,1],"이유":"보유"}'.encode()
    assert result.normalized_bytes().endswith(b'\n')


def _columns(connection, table):
    return {row[1] for row in connection.execute(f'PRAGMA table_info({table})')}


@pytest.mark.parametrize('owner,version_name,migrator,schema_name,exact', [
    ('sqlite_audit', 'SCHEMA_VERSION', 'migrate', 'PRIMARY_REPORT_SCHEMA', False),
    ('soak_store', 'SOAK_SCHEMA_VERSION', 'migrate_soak_store', 'SOAK_REPORT_SCHEMA', True),
    ('soak_controller', 'CONTROLLER_SCHEMA_VERSION', 'migrate_controller', 'CONTROLLER_REPORT_SCHEMA', True),
    ('portfolio_store', 'SCHEMA_VERSION', 'migrate_portfolio', 'PORTFOLIO_REPORT_SCHEMA', False),
])
def test_contracts_match_temporary_owner_migrations(owner, version_name, migrator, schema_name, exact):
    from trading_bot import evidence_contracts as contracts
    module = importlib.import_module('trading_bot.' + owner)
    version_contract = {'sqlite_audit': 'PRIMARY_AUDIT_SCHEMA_VERSION',
                        'soak_store': 'SOAK_SCHEMA_VERSION',
                        'soak_controller': 'CONTROLLER_SCHEMA_VERSION',
                        'portfolio_store': 'PORTFOLIO_SCHEMA_VERSION'}[owner]
    assert getattr(contracts, version_contract) == getattr(module, version_name)
    connection = sqlite3.connect(':memory:')
    try:
        getattr(module, migrator)(connection)
        schema = getattr(contracts, schema_name)
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        assert set(schema) == tables if exact else set(schema) <= tables
        for table, columns in schema.items():
            assert columns == _columns(connection, table) if exact else columns <= _columns(connection, table)
        if owner == 'portfolio_store':
            assert connection.execute('SELECT version FROM portfolio_schema_metadata WHERE owner=?',
                                      (contracts.PORTFOLIO_SCHEMA_OWNER,)).fetchone()[0] == contracts.PORTFOLIO_SCHEMA_VERSION
        else:
            assert connection.execute('PRAGMA user_version').fetchone()[0] == getattr(contracts, version_contract)
    finally:
        connection.close()


def test_reader_rejects_schema_drift_and_keeps_shared_contract():
    from trading_bot import evidence_contracts as contracts, reporting, sqlite_audit
    assert reporting._REQUIRED_SCHEMA is contracts.AUDIT_REPORT_SCHEMA
    connection = sqlite3.connect(':memory:')
    connection.row_factory = sqlite3.Row
    try:
        sqlite_audit.migrate(connection)
        reporting.ReadOnlyAuditRepository._validate_schema(connection)
        connection.execute('PRAGMA user_version=999')
        with pytest.raises(RuntimeError, match='version'):
            reporting.ReadOnlyAuditRepository._validate_schema(connection)
        connection.execute(f'PRAGMA user_version={contracts.PRIMARY_AUDIT_SCHEMA_VERSION}')
        connection.execute('ALTER TABLE runs RENAME COLUMN run_id TO unsupported_id')
        with pytest.raises(RuntimeError, match='capability'):
            reporting.ReadOnlyAuditRepository._validate_schema(connection)
    finally:
        connection.close()


def _retained_v3(path):
    # Retain an actual old owner declaration, without calling the new migrator.
    from trading_bot import portfolio_store as owner
    conn = sqlite3.connect(path)
    for statement in owner._SCHEMA + owner._LEASE_SCHEMA:
        conn.execute(statement)
    conn.execute("INSERT INTO portfolio_schema_metadata VALUES('phase11',3)")
    conn.commit()
    return conn


@pytest.mark.parametrize('version', [3, 4])
def test_portfolio_supported_versions_have_exact_pure_contracts(tmp_path, version):
    from trading_bot import evidence_contracts as c, portfolio_store as owner
    assert c.PORTFOLIO_SCHEMA_VERSION == 4
    assert c.PORTFOLIO_SUPPORTED_READ_VERSIONS == frozenset({3, 4})
    conn = _retained_v3(tmp_path / 'saved.db') if version == 3 else owner.connect_portfolio_store(tmp_path / 'saved.db')
    schema = c.portfolio_read_schema(version)
    assert set(schema) == {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    for table, columns in schema.items():
        assert columns == _columns(conn, table)
    assert ('daily_evaluation_dispatches' in schema) == (version == 4)
    assert c.PORTFOLIO_REPORT_SCHEMA is c.PORTFOLIO_REPORT_SCHEMA_V4
    with pytest.raises(ValueError, match='version'):
        c.portfolio_read_schema(999)
    conn.close()


@pytest.mark.parametrize('version', [3, 4])
def test_saved_portfolio_reader_version_timestamp_and_private_envelope(tmp_path, version):
    from trading_bot import evidence_contracts as contracts
    assert contracts.PORTFOLIO_SCHEMA_VERSION == 4
    from datetime import date, datetime, timedelta, timezone
    from hashlib import sha256
    from trading_bot import portfolio_store as owner
    from trading_bot.mutation_lease import acquire_mutation_lease
    from trading_bot.service_models import DailyDispatchEnvelope
    from trading_bot.web_config import ResourceDescriptor, WebSettings
    from trading_bot.web_evidence import OperatorEvidenceService
    from trading_bot.web_models import PeriodSelection, ResourceScope
    path = tmp_path / 'saved.db'
    scope = 'a' * 64
    stamp = datetime(2026, 10, 5, 0, 10, tzinfo=timezone.utc)
    conn = _retained_v3(path) if version == 3 else owner.connect_portfolio_store(path)
    if version == 3:
        conn.execute("INSERT INTO daily_evaluations VALUES('saved','2026-10-05','005930','[\"HELD\"]',?,?,?,'STARTED',?,NULL)",
            (b'private canonical input', 'b' * 64, scope, stamp.isoformat()))
        conn.commit()
    else:
        envelope = DailyDispatchEnvelope(prompt_bytes=b'private canonical input',
            prompt_hash=sha256(b'private canonical input').hexdigest(), system_prompt='private system',
            schema_hash='b' * 64, provider='openai', model='synthetic', temperature=0, prompt_version='v1')
        with acquire_mutation_lease(conn, account_scope_hash=scope, lock_dir=tmp_path / 'locks',
                command='synthetic', cycle_id='synthetic', observed_at=stamp) as lease:
            saved = owner.start_daily_evaluation(conn, trading_date_kst=date(2026, 10, 5),
                ticker='005930', provenance=('HELD',), canonical_input=envelope.prompt_bytes,
                account_scope_hash=scope, observed_at=stamp, execution_target='mock', envelope=envelope, lease=lease)
            owner.claim_daily_dispatch(conn, saved.evaluation_id, lease, stamp,
                stamp.replace(minute=20))
    before = tuple(conn.iterdump())
    resource = ResourceDescriptor(id='portfolio', owner='portfolio', path=path,
        account_hash=scope, target='mock')
    settings = WebSettings(operational_db_path=tmp_path / 'web.db', artifact_root=tmp_path / 'artifacts',
        registered_resources=(resource,))
    reader = OperatorEvidenceService(settings, clock=lambda: stamp + timedelta(hours=2))
    period = PeriodSelection(stamp - timedelta(hours=1), stamp + timedelta(hours=1))
    page = reader.list_records('evaluations', scope=ResourceScope(scope, 'mock'), period=period)
    assert page.total == 1
    record = page.rows[0]
    assert record.envelope.schema_version == version
    assert record.envelope.source_observed_at == stamp
    assert record.envelope.account_hash == scope
    assert b'private canonical input' not in repr(record).encode()
    assert b'private system' not in repr(record).encode()
    if version == 4:
        assert record.data['dispatch_state'] == 'DISPATCHED'
        assert record.data['dispatch_id']
        assert record.data['envelope_hash'] == envelope.envelope_hash
        assert record.data['execution_target'] == 'mock'
        assert record.envelope.provenance == 'saved_daily_dispatch'
    else:
        assert 'dispatch_id' not in record.data
    reader.observe_alert_sources()
    reader.overview(ResourceScope(scope, 'mock'))
    assert tuple(conn.iterdump()) == before
    if version == 4:
        conn.execute('DROP TRIGGER immutable_daily_dispatch_envelope')
        conn.execute("UPDATE daily_evaluation_dispatches SET execution_target='real'")
        conn.commit()
        failed = reader.list_records('evaluations', scope=ResourceScope(scope, 'mock'), period=period)
        assert failed.total is None and not failed.rows
        assert failed.envelopes[0].diagnostic_code == 'SCOPE_CONFLICT'
    conn.close()


def test_v4_missing_dispatch_capability_and_unknown_owner_are_unavailable(tmp_path):
    from trading_bot import portfolio_store as owner
    from trading_bot.web_config import ResourceDescriptor
    from trading_bot.web_evidence import _transaction, EvidenceUnavailable
    path = tmp_path / 'saved.db'
    conn = owner.connect_portfolio_store(path)
    resource = ResourceDescriptor(id='portfolio', owner='portfolio', path=path,
        account_hash='a' * 64, target='mock')
    conn.execute('ALTER TABLE daily_evaluation_dispatches RENAME COLUMN envelope_hash TO unsupported_hash')
    conn.commit()
    with pytest.raises(EvidenceUnavailable, match='UNSUPPORTED_SCHEMA'):
        with _transaction(resource):
            pass
    conn.execute("UPDATE portfolio_schema_metadata SET owner='foreign'")
    conn.commit()
    with pytest.raises(EvidenceUnavailable, match='UNSUPPORTED_SCHEMA'):
        with _transaction(resource):
            pass
    conn.close()
