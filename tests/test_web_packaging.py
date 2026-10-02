"""Offline wheel installation, without editable checkout import fallbacks."""
from pathlib import Path


def test_phase14_runbook_matches_local_private_and_observer_contract():
    text=Path('docs/operator-runbook.md').read_text()
    for required in ('## Phase 14 운영자 웹과 독립 알림 관찰','bot-web setup --config',
        'bot-web reset-password --config','bot-web serve --config','bot-alerts --config',
        'trusted_proxies','allowed_origin','UNKNOWN','SIGINT','SIGTERM','StrEnum','3.14.3',
        'mobile data','source_observed_at','query_at','30분','수식','phase14_web_metadata'):
        assert required in text,required


def test_offline_installed_wheel_has_native_resources_independent_entrypoints_and_render(tmp_path):
    proof=installed_wheel_probe(tmp_path)
    assert proof['python']=='3.14.3'
    assert proof['resource_count']>=10
    assert proof['help_commands']==['bot-web','bot-alerts']
    assert proof['rendered'] and proof['source_checkout_absent'] and proof['network_calls']==0
