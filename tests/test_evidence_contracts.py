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
