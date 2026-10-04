"""CLI proof must execute the shipped service, without external capabilities."""
import json
from pathlib import Path

from tests.service_fixtures import NoExternalCapabilities
from tests.test_service_cli import configured, invoke
from tests.test_replay import FIXTURES


def test_dry_run_runs_owned_runtime_recovery_and_preserves_registered_sources(tmp_path):
    settings, config = configured(tmp_path)
    sources = (config, settings.service_db_path, settings.control_db_path,
               settings.acceptance_receipt_path, settings.session_evidence_path)
    before = {p: p.read_bytes() for p in sources}
    output = tmp_path / 'offline'
    with NoExternalCapabilities() as capabilities:
        result = invoke(config, 'dry-run', '--fixture', str(FIXTURES / 'focused.json'),
                        '--output-root', str(output))
    assert result.exit_code == 0, result.output
    assert capabilities.attempts == ()
    proof = json.loads((output / 'service-result.json').read_text())
    assert proof['evidence_class'] == 'SYNTHETIC'
    assert proof['authority'] == 'OFFLINE_ONLY'
    assert proof['provider_calls'] == proof['broker_calls'] == 0
    assert proof['recovered_dispatch_state'] == 'DISPATCHED_UNKNOWN'
    assert proof['runtime_states'][-1] == 'IDLE'
    assert proof['stable_job_ids'] and proof['evaluation_ids']
    assert proof['account_leases_released']
    assert {p: p.read_bytes() for p in sources} == before
    assert not (output / 'acceptance.json').exists()
    assert json.loads((output / 'replay-result.json').read_text())['outcomes']
