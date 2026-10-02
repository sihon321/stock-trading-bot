"""Registered immutable proofs, never self-authenticating result hashes."""
import copy

import pytest

from trading_bot.shadow_evidence import (
    RegisteredShadowProof, SavedShadowProof, SavedShadowProofCatalog,
    SavedShadowUnavailable, VerifiedSavedShadow, validate_saved_shadow_result,
)
from trading_bot.shadow_models import (
    ShadowInputError, ShadowRunResult, canonical_json, shadow_content_hash, strict_json,
)
from test_shadow_reporting import result


def proof_catalog(saved):
    from trading_bot.backtest_models import BacktestBundle
    from trading_bot.backtest_reporting import BacktestResult
    from trading_bot.shadow_inputs import collect_shadow_snapshots, render_snapshot, FrozenHistoricalNews
    from trading_bot.shadow_reporting import compare_shadow_action
    m = saved.manifest
    inventory, _ = collect_shadow_snapshots(
        BacktestBundle.model_validate(strict_json(m.bundle_document_json)),
        BacktestResult.model_validate(strict_json(m.baseline_document_json)),
    )
    news = tuple(FrozenHistoricalNews.model_validate(n) for n in strict_json(m.news_document_json))
    inventory = tuple(render_snapshot(s, news) for s in inventory)
    units = {s.unit_id: s for s in m.snapshots}
    proof = SavedShadowProof(
        spec_id=m.spec_id, run_id=saved.run_id, baseline_hash=m.baseline_hash,
        bundle_hash=m.bundle_hash, source_hashes=m.source_hashes,
        news_hash=shadow_content_hash(strict_json(m.news_document_json)),
        code_revision=m.code_revision, code_content_hash=m.code_content_hash,
        inventory=inventory,
        comparisons=tuple(compare_shadow_action(units[o.unit_id], o).model_dump() for o in saved.observations),
        events_hash=shadow_content_hash(strict_json(saved.events_document_json)),
        observations_hash=shadow_content_hash([o.model_dump(mode='json') for o in saved.observations]),
    )
    return SavedShadowProofCatalog((RegisteredShadowProof(
        spec_id=m.spec_id, run_id=saved.run_id,
        expected_hash=shadow_content_hash(proof), document_json=canonical_json(proof),
    ),))


def rehash(raw):
    raw['result_id'] = ''
    return ShadowRunResult.model_validate(raw)


def test_registered_proof_passes_without_any_evaluator(monkeypatch, tmp_path):
    saved = result(tmp_path)
    catalog = proof_catalog(saved)
    import trading_bot.shadow_inputs as inputs
    import trading_bot.backtest_engine as engine
    import trading_bot.execution as execution
    def forbidden(*a, **k):
        pytest.fail('saved integrity must never evaluate')
    for module, names in ((inputs, ('collect_shadow_snapshots', 'validate_shadow_preparation')),
                          (engine, ('run_backtest', 'project_backtest_action')),
                          (execution, ('execute_signal_cycle',))):
        for name in names:
            monkeypatch.setattr(module, name, forbidden)
    checked = validate_saved_shadow_result(saved, catalog)
    assert isinstance(checked, VerifiedSavedShadow)
    assert checked.status == 'VERIFIED' and checked.result == saved
    assert checked.result.result_id == saved.result_id
    assert canonical_json(checked.result) == canonical_json(saved)


def test_absent_proof_is_named_unknown_even_with_valid_hashes(tmp_path):
    saved = result(tmp_path)
    unavailable = validate_saved_shadow_result(saved)
    assert isinstance(unavailable, SavedShadowUnavailable)
    assert unavailable.status == 'UNKNOWN'
    assert unavailable.code == 'SAVED_SHADOW_PROVENANCE_UNAVAILABLE'
    assert {'UNIT_INVENTORY', 'PRE_DECISION_FACTS', 'RECORDED_ACTIONS'} <= set(unavailable.predicates)


@pytest.mark.parametrize('field', ['cash', 'baseline', 'source', 'input', 'selection', 'coverage', 'metric', 'cost', 'journal'])
def test_rehashed_forgery_never_verifies(tmp_path, field):
    saved = result(tmp_path)
    catalog = proof_catalog(saved)
    raw = copy.deepcopy(saved.model_dump(mode='json'))
    m = raw['manifest']
    if field == 'cash':
        m['snapshots'][0]['available_cash'] = str(saved.manifest.snapshots[0].available_cash + 1)
        m['snapshots'][0]['settled_cash'] = str(saved.manifest.snapshots[0].settled_cash + 1)
        m['snapshots'][0]['snapshot_id'] = ''
    elif field == 'baseline':
        m['snapshots'][0]['baseline_reason'] = 'FABRICATED'
        m['snapshots'][0]['snapshot_id'] = ''
    elif field == 'source':
        m['source_hashes'] = ['a' * 64]
    elif field == 'input':
        bundle = strict_json(m['bundle_document_json'])
        bundle['bars'][0]['volume'] += 1
        m['bundle_document_json'] = canonical_json(bundle)
        m['bundle_hash'] = shadow_content_hash(bundle)
    elif field == 'selection':
        m['seed'] = 'forged-seed'
    elif field == 'coverage':
        coverage = strict_json(m['coverage_json']); coverage['observed_units'] += 1
        m['coverage_json'] = canonical_json(coverage)
    elif field == 'metric':
        metrics = strict_json(raw['metrics_document_json']); metrics['attempted'] += 1
        raw['metrics_document_json'] = canonical_json(metrics)
    else:
        events = strict_json(raw['events_document_json'])
        if field == 'cost': events[0]['data']['charge']['charged_tokens'] += 1
        else: events.pop()
        previous = '0' * 64
        for index, event in enumerate(events, 1):
            event.update(seq=index, prev=previous)
            event['hash'] = shadow_content_hash({k: v for k, v in event.items() if k != 'hash'})
            previous = event['hash']
        raw['events_document_json'] = canonical_json(events)
    if m != saved.manifest.model_dump(mode='json'):
        # Rehash the whole nested result, including attribution: still no new trust root.
        from trading_bot.shadow_models import ShadowManifest
        m['spec_id'] = ''
        m = ShadowManifest.model_validate(m)
        raw['manifest'] = m.model_dump(mode='json')
        for o in raw['observations']: o['spec_id'] = m.spec_id
    checked = None
    try:
        checked = validate_saved_shadow_result(rehash(raw), catalog)
    except ShadowInputError:
        pass
    assert not isinstance(checked, VerifiedSavedShadow)


def test_proof_document_cannot_register_itself_by_rehash(tmp_path):
    saved = result(tmp_path); catalog = proof_catalog(saved)
    entry = catalog.proofs[0]
    raw = strict_json(entry.document_json)
    raw['inventory'][0]['technicals_json'] = '{}'
    raw['inventory'][0]['snapshot_id'] = ''
    changed = RegisteredShadowProof(spec_id=entry.spec_id, run_id=entry.run_id,
        expected_hash=entry.expected_hash, document_json=canonical_json(raw))
    with pytest.raises(ShadowInputError, match='REGISTERED_PROOF_HASH'):
        validate_saved_shadow_result(saved, SavedShadowProofCatalog((changed,)))


def test_historical_code_identity_is_not_checked_against_checkout(tmp_path):
    saved = result(tmp_path)
    raw = saved.model_dump(mode='json'); m = raw['manifest']; m['code_content_hash'] = 'b' * 64
    m['code_revision'] = 'historical-revision'; m['spec_id'] = ''
    from trading_bot.shadow_models import ShadowManifest
    m = ShadowManifest.model_validate(m); raw['manifest'] = m.model_dump(mode='json')
    events = strict_json(raw['events_document_json']); previous = '0' * 64
    for event in events:
        if event['type'] == 'OBSERVATION': event['data']['observation']['spec_id'] = m.spec_id
        event['prev'] = previous
        event['hash'] = shadow_content_hash({k: v for k, v in event.items() if k != 'hash'})
        previous = event['hash']
    raw['events_document_json'] = canonical_json(events)
    for o in raw['observations']: o['spec_id'] = m.spec_id
    historical = rehash(raw)
    checked = validate_saved_shadow_result(historical, proof_catalog(historical))
    assert checked.result.manifest.code_content_hash == 'b' * 64
    assert checked.result.result_id == historical.result_id
