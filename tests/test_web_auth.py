"""Absolute sessions and throttling use an injected aware clock."""
import hashlib
from datetime import timedelta

import pytest

from trading_bot.web_auth import SCRYPT_METHOD, WebAuth, hash_password
from trading_bot.web_store import WebStore
from test_web_config import settings
from operator_fixtures import FixedClock, NOW

PASSWORD = 'synthetic-operator-password'


def fast_hash(value):
    return 'test:' + hashlib.sha256(value.encode()).hexdigest()


def auth_fixture(tmp_path):
    store = WebStore(settings(tmp_path))
    store.initialize()
    clock = FixedClock()
    auth = WebAuth(store, clock=clock, hasher=fast_hash,
                   verifier=lambda hashed, password: hashed == fast_hash(password))
    auth.provision_operator('operator', PASSWORD)
    return auth, store, clock


def test_concurrent_pc_phone_logout_and_forgery(tmp_path):
    auth, store, clock = auth_fixture(tmp_path)
    pc = auth.authenticate('operator', PASSWORD, '127.0.0.1')
    phone = auth.authenticate('operator', PASSWORD, '100.100.1.2')
    assert pc and phone and pc != phone
    assert auth.validate_session(pc).actor == 'operator'
    assert auth.validate_session(phone)
    auth.logout(pc)
    assert auth.validate_session(pc) is None
    assert auth.validate_session(phone)
    for forged in ('x', 'a' * 43, None, '../source/audit.db'):
        assert auth.validate_session(forged) is None
    assert PASSWORD not in repr(auth) and phone not in repr(auth.validate_session(phone))
    assert pc.encode() not in store.settings.operational_db_path.read_bytes()
    assert phone.encode() not in store.settings.operational_db_path.read_bytes()


def test_exact_expiry_and_polling_never_slide(tmp_path):
    auth, store, clock = auth_fixture(tmp_path)
    pc = auth.authenticate('operator', PASSWORD, '127.0.0.1')
    initial = auth.validate_session(pc)
    clock.advance(hours=6)
    phone = auth.authenticate('operator', PASSWORD, '100.100.1.2')
    for _ in range(3):
        assert auth.validate_session(pc).expires_at == initial.expires_at
    clock.now = NOW + timedelta(hours=12, microseconds=-1)
    assert auth.validate_session(pc)
    clock.advance(microseconds=1)
    assert auth.validate_session(pc) is None
    assert auth.validate_session(phone)
    assert store.get_session(hashlib.sha256(pc.encode()).hexdigest()).issued_at == NOW
    clock.now = NOW - timedelta(seconds=1)
    assert auth.validate_session(phone) is None


def test_reset_revokes_all_and_keeps_dedicated_hash_only(tmp_path):
    auth, store, clock = auth_fixture(tmp_path)
    pc = auth.authenticate('operator', PASSWORD, '127.0.0.1')
    phone = auth.authenticate('operator', PASSWORD, '100.100.1.2')
    new_password = 'synthetic-new-operator-password'
    auth.reset_password(new_password)
    assert auth.validate_session(pc) is None and auth.validate_session(phone) is None
    assert auth.authenticate('operator', PASSWORD, '127.0.0.1') is None
    assert auth.authenticate('operator', new_password, '127.0.0.1')
    data = store.settings.operational_db_path.read_bytes()
    assert PASSWORD.encode() not in data and new_password.encode() not in data
    with store.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM web_actions WHERE action='PASSWORD_RESET'").fetchone()[0] == 1


def test_persistent_five_failure_account_and_source_throttle(tmp_path):
    auth, store, clock = auth_fixture(tmp_path)
    for index in range(5):
        assert auth.authenticate('operator', 'wrong', f'100.100.1.{index + 1}') is None
    restarted = WebAuth(store, clock=clock, hasher=fast_hash,
                        verifier=lambda hashed, password: hashed == fast_hash(password))
    assert restarted.authenticate('operator', PASSWORD, '127.0.0.1') is None
    clock.advance(minutes=5)
    assert restarted.authenticate('operator', PASSWORD, '127.0.0.1')
    for index in range(5):
        assert restarted.authenticate(f'unknown-{index}', 'wrong', '100.100.1.2') is None
    assert restarted.authenticate('operator', PASSWORD, '100.100.1.2') is None
    with store.connection() as conn:
        assert all(row[0] <= 5 for row in conn.execute('SELECT failures FROM web_login_throttle'))
        assert not any('unknown' in row[0] for row in conn.execute('SELECT bucket_hash FROM web_login_throttle'))


def test_unknown_and_bad_inputs_generic_and_no_secret_audit(tmp_path):
    auth, store, clock = auth_fixture(tmp_path)
    for username, password, source in [('unknown', PASSWORD, '127.0.0.1'),
                                      ('operator', 'sk-test-secret-sentinel', '127.0.0.1'),
                                      ('operator', 'a' * 1025, '127.0.0.1')]:
        assert auth.authenticate(username, password, source) is None
    assert b'sk-test-secret-sentinel' not in store.settings.operational_db_path.read_bytes()
    with pytest.raises(ValueError, match='password'):
        auth.reset_password('short')
    assert PASSWORD not in repr(store.get_operator())


def test_naive_clock_rejected(tmp_path):
    auth, store, clock = auth_fixture(tmp_path)
    clock.now = NOW.replace(tzinfo=None)
    with pytest.raises(ValueError, match='aware'):
        auth.authenticate('operator', PASSWORD, '127.0.0.1')


def test_real_scrypt_parameters_and_random_salt():
    from werkzeug.security import check_password_hash
    value = hash_password(PASSWORD)
    assert value.startswith(SCRYPT_METHOD + '$')
    assert SCRYPT_METHOD == 'scrypt:131072:8:1'
    assert check_password_hash(value, PASSWORD)
    assert not check_password_hash(value, 'wrong')
    assert hash_password(PASSWORD) != value
