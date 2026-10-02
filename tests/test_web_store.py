"""Independent operational schema; never initialize a source owner."""
import sqlite3
from datetime import timedelta

import pytest

from trading_bot.web_store import WEB_SCHEMA_VERSION, WebStore
from test_web_config import settings, resource
from operator_fixtures import NOW


def test_initialize_restart_owner_permissions_and_source_bytes(tmp_path):
    src = tmp_path / 'sources' / 'audit.db'
    src.parent.mkdir()
    sqlite3.connect(src).close()
    before = src.read_bytes()
    config = settings(tmp_path, registered_resources=(resource(src),))
    store = WebStore(config)
    store.initialize()
    store.initialize()
    assert src.read_bytes() == before
    assert config.operational_db_path.stat().st_mode & 0o777 == 0o600
    assert config.artifact_root.stat().st_mode & 0o777 == 0o700
    with store.connection() as conn:
        assert conn.execute('SELECT version FROM phase14_web_metadata').fetchone()[0] == WEB_SCHEMA_VERSION
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 0


def test_future_version_and_foreign_store_fail_without_mutation(tmp_path):
    config = settings(tmp_path)
    store = WebStore(config)
    store.initialize()
    with store.connection() as conn:
        conn.execute('UPDATE phase14_web_metadata SET version=999')
    before = config.operational_db_path.read_bytes()
    with pytest.raises(ValueError, match='unsupported'):
        store.initialize()
    assert config.operational_db_path.read_bytes() == before
    foreign = tmp_path / 'foreign' / 'web.db'
    foreign.parent.mkdir()
    conn = sqlite3.connect(foreign)
    conn.execute('CREATE TABLE trading_evidence(id INTEGER)')
    conn.commit()
    conn.close()
    before = foreign.read_bytes()
    with pytest.raises(ValueError, match='ownership'):
        WebStore(config.model_copy(update={'operational_db_path': foreign})).initialize()
    assert foreign.read_bytes() == before


def test_upgrade_and_failed_upgrade_are_transactional(tmp_path):
    config = settings(tmp_path)
    store = WebStore(config)
    store.initialize()
    with store.connection() as conn:
        conn.execute('DROP TABLE web_report_artifacts')
        conn.execute('UPDATE phase14_web_metadata SET version=1')
    with pytest.raises(RuntimeError):
        store.initialize(fail_after_step='artifacts')
    with store.connection() as conn:
        assert conn.execute('SELECT version FROM phase14_web_metadata').fetchone()[0] == 1
        assert not conn.execute("SELECT name FROM sqlite_master WHERE name='web_report_artifacts'").fetchone()
    store.initialize()
    assert store.get_operator() is None


def test_operator_sessions_and_append_only_safe_audit(tmp_path):
    store = WebStore(settings(tmp_path))
    store.initialize()
    store.provision_operator('operator', 'dedicated-hash', NOW)
    assert 'dedicated-hash' not in repr(store.get_operator())
    with pytest.raises(ValueError):
        store.provision_operator('operator', 'overwrite', NOW)
    store.create_session('a' * 64, NOW, NOW + timedelta(hours=12))
    assert store.get_session('a' * 64).expires_at == NOW + timedelta(hours=12)
    with store.connection() as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute('UPDATE web_sessions SET expires_at=expires_at+1')
    store.revoke_session('a' * 64, NOW)
    assert store.get_session('a' * 64).revoked_at == NOW
    store.append_action(actor='operator', action='LOGIN', result_code='SUCCESS', at=NOW)
    with pytest.raises(ValueError):
        store.append_action(actor='operator', action='LOGIN', result_code='SUCCESS', at=NOW,
                            details={'password': 'secret-sentinel'})
    with store.connection() as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute('DELETE FROM web_actions')
    assert b'secret-sentinel' not in store.settings.operational_db_path.read_bytes()


def test_revalidate_topology_after_construction(tmp_path):
    config = settings(tmp_path)
    store = WebStore(config)
    config.operational_db_path.parent.symlink_to(tmp_path / 'source', target_is_directory=True)
    with pytest.raises(ValueError):
        store.initialize()
    assert not (tmp_path / 'source').exists()


def test_artifact_ownership_and_unregistered_resource_fail(tmp_path):
    src = tmp_path / 'sources' / 'audit.db'
    src.parent.mkdir()
    src.touch()
    store = WebStore(settings(tmp_path, registered_resources=(resource(src),)))
    store.initialize()
    store.provision_operator('operator', 'hash', NOW)
    store.record_artifact('report-1', resource_id='audit', actor='operator',
                          filename='report-1.json', format='json', at=NOW)
    assert store.get_artifact('report-1', actor='operator').resource_id == 'audit'
    assert store.get_artifact('report-1', actor='someone-else') is None
    with pytest.raises(ValueError):
        store.record_artifact('report-2', resource_id='audit', actor='operator',
                              filename='../source/audit.db', format='json', at=NOW)
