import json
from threading import Event

from typer.testing import CliRunner

from trading_bot.alert_cli import app, load_settings
from trading_bot.alert_config import ObserverSettings


def config(tmp_path, **values):
    folder = tmp_path / 'config'
    folder.mkdir(mode=0o700)
    path = folder / 'observer.json'
    path.write_text(json.dumps({'operational_db_path': str(tmp_path/'ops'/'alerts.db'), **values}))
    path.chmod(0o600)
    return path


def test_status_without_webhook_no_writes(tmp_path):
    path = config(tmp_path)
    result = CliRunner().invoke(app, ['--config', str(path), 'status'])
    assert result.exit_code == 0, result.output
    assert 'NOT_STARTED' in result.output
    assert not (tmp_path / 'ops').exists()


def test_once_offline_and_private_errors(tmp_path):
    path = config(tmp_path)
    result = CliRunner().invoke(app, ['--config', str(path), 'once'])
    assert result.exit_code == 0, result.output
    assert 'STOPPED' in CliRunner().invoke(app, ['--config', str(path), 'status']).output
    path.write_text('{"webhook_url":"SECRET", "invalid":"SECRET"}')
    result = CliRunner().invoke(app, ['--config', str(path), 'once'])
    assert result.exit_code == 1
    assert 'SECRET' not in result.output


def test_no_trading_env_and_no_dotenv(tmp_path, monkeypatch):
    monkeypatch.setenv('KIS_APP_KEY', 'SECRET')
    monkeypatch.setenv('DISCORD_WEBHOOK_URL', 'SECRET')
    path = config(tmp_path)
    settings = load_settings(path)
    assert settings.webhook_url is None
    assert 'SECRET' not in repr(settings)
    assert ObserverSettings.model_config['env_file'] is None


def test_signal_watch_graceful_and_handlers_restored(tmp_path, monkeypatch):
    import signal
    import trading_bot.alert_cli as cli
    calls = []
    old = signal.getsignal(signal.SIGTERM)
    def fake_watch(self, stop):
        handler = signal.getsignal(signal.SIGTERM)
        handler(signal.SIGTERM, None)
        assert stop.is_set()
        calls.append('stopped')
    monkeypatch.setattr(cli.AlertObserver, 'watch', fake_watch)
    result = CliRunner().invoke(app, ['--config', str(config(tmp_path)), 'watch'])
    assert result.exit_code == 0, result.output
    assert calls == ['stopped']
    assert signal.getsignal(signal.SIGTERM) == old
