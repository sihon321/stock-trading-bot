"""Local credential commands and fake production serving; no network/owner stores."""
import json
import subprocess
import sys
from types import SimpleNamespace

from typer.testing import CliRunner

from trading_bot import web_cli
from trading_bot.web_store import WebStore
from test_web_auth import PASSWORD, fast_hash
from operator_fixtures import NOW

runner = CliRunner()


def config_file(tmp_path, **values):
    root = tmp_path / 'config'
    root.mkdir(mode=0o700)
    path = root / 'web.json'
    content = {'operational_db_path': str(tmp_path / 'operations' / 'web.db'),
               'artifact_root': str(tmp_path / 'artifacts')}
    path.write_text(json.dumps(content | values))
    path.chmod(0o600)
    return path


def fast_auth(monkeypatch):
    original = web_cli.WebAuth
    monkeypatch.setattr(web_cli, 'WebAuth', lambda store: original(
        store, hasher=fast_hash, verifier=lambda hashed, password: hashed == fast_hash(password)))


def test_help_has_independent_commands_and_no_trading_imports(tmp_path):
    result = runner.invoke(web_cli.app, ['--help'])
    assert result.exit_code == 0
    assert all(name in result.output for name in ('setup', 'reset-password', 'serve'))
    code = "import sys; import trading_bot.web_cli; assert not any(x in sys.modules for x in ('trading_bot.config','trading_bot.cli','trading_bot.broker','trading_bot.llm'))"
    assert subprocess.run([sys.executable, '-c', code], capture_output=True).returncode == 0


def test_hidden_setup_secret_persistence_and_refuse_overwrite(tmp_path, monkeypatch):
    fast_auth(monkeypatch)
    path = config_file(tmp_path)
    result = runner.invoke(web_cli.app, ['setup', '--config', str(path)],
                           input=PASSWORD + '\n' + PASSWORD + '\n')
    assert result.exit_code == 0, result.output
    assert PASSWORD not in result.output
    settings = web_cli.load_settings(path)
    secret = settings.cookie_secret.get_secret_value()
    assert len(secret) >= 32 and secret not in result.output
    assert path.stat().st_mode & 0o777 == 0o600
    assert WebStore(settings).get_operator().username == 'operator'
    before = settings.operational_db_path.read_bytes()
    second = runner.invoke(web_cli.app, ['setup', '--config', str(path)])
    assert second.exit_code != 0
    assert 'reset-password' in second.output
    assert settings.operational_db_path.read_bytes() == before


def test_local_reset_revokes_every_session_and_hidden_confirmation(tmp_path, monkeypatch):
    fast_auth(monkeypatch)
    path = config_file(tmp_path)
    runner.invoke(web_cli.app, ['setup', '--config', str(path)], input=PASSWORD + '\n' + PASSWORD + '\n')
    store = WebStore(web_cli.load_settings(path))
    store.create_session('a' * 64, NOW, NOW.replace(hour=NOW.hour + 12))
    value = 'synthetic-reset-password'
    result = runner.invoke(web_cli.app, ['reset-password', '--config', str(path)],
                           input=value + '\n' + value + '\n')
    assert result.exit_code == 0, result.output
    assert value not in result.output
    assert store.get_session('a' * 64).revoked_at is not None
    assert value.encode() not in store.settings.operational_db_path.read_bytes()


def test_serve_fake_factory_loopback_no_debug_and_revalidated_overrides(tmp_path, monkeypatch):
    path = config_file(tmp_path, cookie_secret='synthetic-cookie-' + 'a' * 32)
    called = []
    fake = SimpleNamespace(config={}, debug=True)
    monkeypatch.setattr(web_cli, '_create_app', lambda settings: called.append(settings) or fake)
    monkeypatch.setattr(web_cli, '_serve', lambda app, **kwargs: called.append((app, kwargs)))
    store = WebStore(web_cli.load_settings(path))
    store.initialize()
    store.provision_operator('operator', 'hash', NOW)
    result = runner.invoke(web_cli.app, ['serve', '--config', str(path)])
    assert result.exit_code == 0, result.output
    assert called[0].bind_host == '127.0.0.1'
    assert called[1][1]['host'] == '127.0.0.1' and called[1][1]['port'] == 8765
    assert called[1][1]['expose_tracebacks'] is False
    assert called[1][1]['clear_untrusted_proxy_headers'] is True
    assert fake.debug is False and fake.config['DEBUG'] is False
    called.clear()
    result = runner.invoke(web_cli.app, ['serve', '--config', str(path), '--host', '0.0.0.0'])
    assert result.exit_code != 0 and not called


def test_private_proxy_fixed_address_no_wildcard(tmp_path, monkeypatch):
    path = config_file(tmp_path, private_mode=True, bind_host='100.100.1.2',
                       allowed_hosts=['bot.example.internal'], allowed_origin='https://bot.example.internal',
                       tls_termination=True, trusted_proxies=['127.0.0.1'],
                       cookie_secret='synthetic-cookie-' + 'a' * 32)
    store = WebStore(web_cli.load_settings(path))
    store.initialize()
    store.provision_operator('operator', 'hash', NOW)
    captured = {}
    monkeypatch.setattr(web_cli, '_create_app', lambda settings: SimpleNamespace(config={}, debug=True))
    monkeypatch.setattr(web_cli, '_serve', lambda app, **kwargs: captured.update(kwargs))
    result = runner.invoke(web_cli.app, ['serve', '--config', str(path)])
    assert result.exit_code == 0, result.output
    assert captured['trusted_proxy'] == '127.0.0.1'
    assert captured['trusted_proxy_count'] == 1
    assert captured['trusted_proxy_headers'] == {'x-forwarded-proto', 'x-forwarded-for', 'x-forwarded-host', 'x-forwarded-port'}


def test_config_permission_alias_secret_and_unavailable_app_fail_safe(tmp_path, monkeypatch):
    path = config_file(tmp_path, kis_app_key='secret-sentinel')
    result = runner.invoke(web_cli.app, ['serve', '--config', str(path)])
    assert result.exit_code != 0 and 'secret-sentinel' not in result.output
    path.write_text('{}')
    path.chmod(0o644)
    assert runner.invoke(web_cli.app, ['setup', '--config', str(path)]).exit_code != 0
    alias = path.parent / 'alias.json'
    alias.symlink_to(path)
    assert runner.invoke(web_cli.app, ['setup', '--config', str(alias)]).exit_code != 0


def test_mismatched_confirmation_never_provisions(tmp_path, monkeypatch):
    fast_auth(monkeypatch)
    path = config_file(tmp_path)
    result = runner.invoke(web_cli.app, ['setup', '--config', str(path)],
                           input=PASSWORD + '\n' + 'different-password' + '\n')
    assert result.exit_code != 0
    assert WebStore(web_cli.load_settings(path)).get_operator() is None


def test_serve_missing_future_app_honest_error(tmp_path, monkeypatch):
    path = config_file(tmp_path, cookie_secret='synthetic-cookie-' + 'a' * 32)
    store = WebStore(web_cli.load_settings(path))
    store.initialize()
    store.provision_operator('operator', 'hash', NOW)
    def unavailable(settings):
        raise ImportError('synthetic-secret-sentinel')
    monkeypatch.setattr(web_cli, '_create_app', unavailable)
    result = runner.invoke(web_cli.app, ['serve', '--config', str(path)])
    assert result.exit_code != 0
    assert 'Traceback' not in result.output and 'synthetic-secret-sentinel' not in result.output
