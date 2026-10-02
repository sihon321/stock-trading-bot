"""Fresh interpreter saved load/render/write; no shared credential conftest."""
import json
import os
from pathlib import Path
import subprocess
import sys


def saved_action(registry):
    from trading_bot.shadow_evidence import RegisteredShadowProof, SavedShadowProofCatalog, SavedShadowUnavailable
    from trading_bot.shadow_models import canonical_json, read_shadow_json, ShadowInputError
    from trading_bot.shadow_reporting import load_shadow_result, render_shadow_report, write_shadow_result
    catalog = None
    if 'proof' in registry['paths']:
        document = read_shadow_json(registry['paths']['proof'])
        catalog = SavedShadowProofCatalog((RegisteredShadowProof(
            spec_id=registry['expected_spec'], run_id=registry['expected_run'],
            expected_hash=registry['proof_hash'], document_json=canonical_json(document),
        ),))
    try:
        result = load_shadow_result(registry['paths']['shadow'], proof_catalog=catalog)
        text = render_shadow_report(result, proof_catalog=catalog)
        write_shadow_result(result, Path(registry['writable_roots'][0]) / 'copy.json', proof_catalog=catalog)
        assert '수동 결정' in text and 'HINDSIGHT' in text and 'UNKNOWN' in text
        assert result.result_id == registry['expected_id']
        verdict = 'VERIFIED'
    except SavedShadowUnavailable as diagnostic:
        assert catalog is None
        assert diagnostic.status == 'UNKNOWN' and diagnostic.predicates
        verdict = 'UNKNOWN'
    except ShadowInputError:
        assert registry.get('malformed')
        verdict = 'REJECTED'
    except RuntimeError as error:
        import traceback
        raise AssertionError(traceback.format_exc()) from error
    assert not any(n.startswith(('trading_bot.shadow_store', 'trading_bot.shadow_runner',
        'trading_bot.shadow_inputs', 'trading_bot.backtest_engine', 'trading_bot.execution',
        'trading_bot.config', 'trading_bot.portfolio', 'trading_bot.kis_', 'openai', 'anthropic'))
        for n in sys.modules)
    return verdict


def probe(registry, action='saved_action', module='test_shadow_saved_capabilities'):
    root = Path(__file__).resolve().parents[1]
    env = {k: v for k, v in os.environ.items()
           if not any(part in k.upper() for part in ('KIS', 'API_KEY', 'AUTH_TOKEN', 'DISCORD'))}
    completed = subprocess.run([sys.executable, str(root / 'tests/capability_probe.py'),
        '--module', module, '--action', action, '--registry', json.dumps(registry)],
        cwd=root, env=env, capture_output=True, text=True, timeout=20)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload['ok'] and not payload['shared_conftest']
    return payload['result']


def test_fresh_saved_reporting_import_has_no_evaluation_capability():
    probe({'sources': [], 'writable_roots': [], 'paths': {}}, 'import', 'trading_bot.shadow_reporting')


def test_fresh_saved_load_render_write_with_registered_proof(tmp_path):
    from test_shadow_reporting import result
    from test_saved_shadow_evidence import proof_catalog
    from trading_bot.shadow_models import canonical_json
    saved = result(tmp_path); entry = proof_catalog(saved).proofs[0]
    path = tmp_path / 'shadow.json'; path.write_text(canonical_json(saved))
    proof_path = tmp_path / 'proof.json'; proof_path.write_text(entry.document_json)
    output = tmp_path / 'output'; output.mkdir()
    before = {p: p.read_bytes() for p in (path, proof_path)}
    registry = {'sources': [str(path), str(proof_path)], 'writable_roots': [str(output)],
        'paths': {'shadow': str(path), 'proof': str(proof_path)}, 'expected_id': saved.result_id,
        'expected_spec': entry.spec_id, 'expected_run': entry.run_id, 'proof_hash': entry.expected_hash}
    assert probe(registry) == 'VERIFIED'
    assert {p: p.read_bytes() for p in before} == before
    assert (output / 'copy.json').read_text() == canonical_json(saved) + '\n'


def test_fresh_unsupported_and_malformed_saved_evidence_never_evaluate(tmp_path):
    from test_shadow_reporting import result
    from trading_bot.shadow_models import canonical_json
    saved = result(tmp_path); path = tmp_path / 'shadow.json'
    path.write_text(canonical_json(saved))
    registry = {'sources': [str(path)], 'writable_roots': [], 'paths': {'shadow': str(path)}}
    assert probe(registry) == 'UNKNOWN'
    path.write_text('{"raw":"DO_NOT_DISCLOSE","result_id":"invalid"}')
    registry['malformed'] = True
    assert probe(registry) == 'REJECTED'
