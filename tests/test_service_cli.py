import json
import os
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from tests.service_fixtures import TempServiceTopology, SCOPE, NoExternalCapabilities

RUNNER = CliRunner()


def configured(tmp_path):
    from trading_bot.control_store import ControlStore
    from trading_bot.service_store import ServiceJournal
    settings = TempServiceTopology(tmp_path).registration()
    ServiceJournal(settings).initialize()
    ControlStore(settings).initialize(actor='fixture-owner')
    config = tmp_path / 'registration' / 'service.json'
    config.parent.mkdir(mode=0o700)
    config.write_text(settings.model_dump_json())
    config.chmod(0o600)
    return settings, config


def invoke(config, *args):
    from trading_bot.service_cli import app
    return RUNNER.invoke(app, ['--config', str(config), *args])


def test_request_only_revision_replay_and_restriction(tmp_path):
    from trading_bot.control_store import ControlStore
    settings, config = configured(tmp_path)
    with NoExternalCapabilities() as external:
        for action, revision in [('pause',0), ('kill',1), ('resume',2)]:
            result = invoke(config, action, '--request-id', f'cli-{action}', '--expected-revision', str(revision))
            assert result.exit_code == 0, result.output
            assert 'REQUESTED' in result.output and 'pending' in result.output
        replay = invoke(config, 'resume', '--request-id', 'cli-resume', '--expected-revision', '2')
        assert replay.exit_code == 0
        assert not external.attempts
    current = ControlStore(settings).reader().effective_state()
    assert current.mode == 'KILLED' and current.applied.mode == 'PAUSED'
    assert current.acceptance_revision == 3
    assert invoke(config,'kill','--request-id','conflict','--expected-revision','0').exit_code == 1


def test_offline_status_disabled_run_and_missing_config(tmp_path):
    _, config = configured(tmp_path)
    with NoExternalCapabilities() as external, patch('trading_bot.service_cli.build_production_runtime', side_effect=AssertionError('trading')):
        assert invoke(config,'status').exit_code == 0
        assert invoke(config,'run').exit_code == 0
        assert invoke(config,'launch').exit_code == 0
        assert not external.attempts
    assert invoke(tmp_path/'missing.json','status').exit_code == 1
    values=json.loads(config.read_text()); values['password']='DO_NOT_ECHO'
    config.write_text(json.dumps(values))
    result=invoke(config,'status')
    assert result.exit_code == 1 and 'DO_NOT_ECHO' not in result.output


def test_disabled_setup_protected_distinct_initial_paused(tmp_path):
    config=tmp_path/'registration'/'service.json'
    with NoExternalCapabilities() as external:
        result=invoke(config,'setup-disabled','--root',str(tmp_path/'state'), '--account-scope-hash', SCOPE.account_scope_hash)
        assert result.exit_code == 0, result.output
        assert not external.attempts
    from trading_bot.service_config import load_service_settings
    from trading_bot.control_store import ControlStore
    settings=load_service_settings(config)
    assert not settings.service_enabled and settings.mode=='DISABLED'
    assert ControlStore(settings).reader().effective_state().mode=='PAUSED'
    assert not settings.acceptance_receipt_path.exists()
    assert config.stat().st_mode & 0o077 == 0
    assert invoke(config,'setup-disabled','--root',str(tmp_path/'state'), '--account-scope-hash', SCOPE.account_scope_hash).exit_code == 1


def test_receipt_capture_has_no_defaults_or_synthetic_authority(tmp_path):
    from tests.service_fixtures import ApprovalBundle
    _,config=configured(tmp_path)
    candidate=tmp_path/'registration'/'candidate.json'
    candidate.write_text(ApprovalBundle.synthetic().receipt.model_dump_json());candidate.chmod(0o600)
    result=invoke(config,'record-acceptance','--receipt-input',str(candidate),
        '--verified-task-1','--verified-task-2','--campaign-id','synthetic-campaign',
        '--profile-fingerprint','c'*64,'--source-id','synthetic-report')
    assert result.exit_code == 1 and not (config.parent/'acceptance.json').exists()
    assert invoke(config,'record-acceptance').exit_code != 0


def test_attention_reset_is_request_only_and_idempotent(tmp_path):
    settings,config=configured(tmp_path)
    result=invoke(config,'reset-attention','--request-id','manual-reset','--expected-revision','0')
    assert result.exit_code == 0, result.output
    from trading_bot.service_cli import attention_request_path
    request=json.loads(attention_request_path(settings).read_text())
    assert request['request_id']=='manual-reset' and request['action']=='RESET_ATTENTION'
    assert invoke(config,'reset-attention','--request-id','manual-reset','--expected-revision','0').exit_code==0
    assert invoke(config,'reset-attention','--request-id','different','--expected-revision','0').exit_code==1
    from trading_bot.service_store import ServiceJournal
    with ServiceJournal(settings).connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM service_attention_events').fetchone()[0]==0


def test_all_commands_and_entrypoint_registered():
    from trading_bot.service_cli import app
    result=RUNNER.invoke(app,['--help'])
    for command in ('setup-disabled','status','run','launch','dry-run','pause','resume','kill',
            'reset-attention','acceptance-status','record-acceptance','render-launchagents',
            'install-launchagents','start','stop','remove-launchagents'):
        assert command in result.output
    assert 'bot-service = "trading_bot.service_cli:app"' in Path('pyproject.toml').read_text()
