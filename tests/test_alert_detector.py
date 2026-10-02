from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from trading_bot.alert_detector import AlertDetector
from trading_bot.alert_models import Severity
from trading_bot.alert_store import AlertStore
from trading_bot.web_models import (AlertSourceBatch, EvidenceRecord, EvidenceSelection,
                                    ResourceScope, SourceEnvelope, WorkerDTO)

NOW = datetime(2026, 10, 2, tzinfo=timezone.utc)
HASH = 'a' * 64


def record(kind, ident='1', seconds=0, **fields):
    env = SourceEnvelope('source', 'portfolio', 3, HASH, 'mock', NOW,
                         NOW + timedelta(seconds=seconds), completeness='COMPLETE')
    return EvidenceRecord(f'{kind}:{ident}', kind, env,
        EvidenceSelection(ident, 'source', kind, ResourceScope(HASH, 'mock')),
        tuple(fields.items()))


@pytest.mark.parametrize('kind,bad,good,family', [
    ('runs', {'status': 'FAILED', 'run_kind': 'daily'}, {'status': 'COMPLETED', 'run_kind': 'daily'}, 'CYCLE'),
    ('evaluations', {'status': 'LLM_UNAVAILABLE', 'ticker': '005930'}, {'status': 'SIGNAL_FINALIZED', 'ticker': '005930'}, 'EVALUATION'),
    ('orders', {'order_intent_id': 'intent', 'event_type': 'SUBMISSION_AMBIGUOUS'}, {'order_intent_id': 'intent', 'event_type': 'RECONCILED', 'broker_order_id': 'broker', 'broker_status': 'FILLED', 'unfilled_qty': 0}, 'UNRESOLVED_ORDER'),
    ('freezes', {'freeze_id': 'freeze', 'ticker': '000660', 'state': 'FROZEN'}, {'freeze_id': 'freeze', 'ticker': '000660', 'state': 'RELEASED', 'release_validated': True, 'release_evidence_id': 'proof'}, 'FREEZE'),
    ('campaigns', {'campaign_id': 'campaign', 'state': 'FAILED', 'safety_failure_code': 'LATCHED'}, {'campaign_id': 'campaign', 'state': 'COMPLETE'}, 'SAFETY_LATCH'),
    ('divergences', {'ticker': '005930', 'code': 'QUANTITY_MISMATCH'}, {'ticker': '005930', 'code': 'QUANTITY_MISMATCH', 'state': 'CLEARED', 'recovery_proof_id': 'proof'}, 'BROKER_DIVERGENCE'),
])
def test_families_stable_positive_recovery_only(tmp_path, kind, bad, good, family):
    detector = AlertDetector()
    store = AlertStore(tmp_path / 'ops' / 'alerts.db', clock=lambda: NOW)
    store.initialize()
    initial = detector.detect(AlertSourceBatch(NOW, (record(kind, **bad),)))
    assert initial and initial[0].subject.problem_family == family
    episode = store.observe(initial[0])
    assert detector.detect(AlertSourceBatch(NOW)) == ()
    unknown = record(kind, 'unknown', 1, **bad)
    unknown = replace(unknown, envelope=replace(unknown.envelope, query_status='FAILED'))
    assert detector.detect(AlertSourceBatch(NOW, (unknown,))) == ()
    assert store.get(episode.episode_id).active
    # A campaign completion cannot clear the irreversible safety latch.
    recovered = detector.detect(AlertSourceBatch(NOW, (record(kind, '2', 2, **good),)))
    if family == 'SAFETY_LATCH':
        assert not recovered or not recovered[0].positive_recovery
    else:
        assert recovered[0].positive_recovery
        assert recovered[0].subject == initial[0].subject
        store.observe(recovered[0])
        assert not store.get(episode.episode_id).active


def test_worker_strict_stale_boundary_and_recovery():
    env = record('watch').envelope
    worker = WorkerDTO(env, 'source:intraday', 'RUNNING', True, 30, source_ids=('saved-1',))
    detector = AlertDetector()
    boundary = detector.detect(AlertSourceBatch(NOW + timedelta(seconds=180), workers=(worker,)))
    assert all(f.positive_recovery for f in boundary)
    stale = detector.detect(AlertSourceBatch(NOW + timedelta(seconds=181), workers=(worker,)))[0]
    assert stale.normalized_state == 'STALE' and stale.severity == Severity.WARNING
    assert detector.detect(AlertSourceBatch(NOW, workers=(replace(worker, state='STOPPED', expected_running=False),))) == ()
    assert detector.detect(AlertSourceBatch(NOW, workers=(replace(worker, expected_running=None),))) == ()
    fresh = replace(worker, envelope=replace(env, source_observed_at=NOW + timedelta(seconds=182)), source_ids=('saved-2',))
    recovery = detector.detect(AlertSourceBatch(NOW + timedelta(seconds=182), workers=(fresh,)))[0]
    assert recovery.positive_recovery and recovery.subject == stale.subject
    assert recovery.source_id != stale.source_id


def test_phase11_producer_ids_and_severity():
    fact = record('transition_observations', state_identity='b'*64,
        state_code='ORDER_AMBIGUOUS', ticker='005930', event_family='BROKER_ORDER',
        broker_subject_id='order-1', severity='INFO', producer_event_code='STATE_BEGIN')
    result = AlertDetector().detect(AlertSourceBatch(NOW, (fact,)))[0]
    assert result.delivery_owner == 'producer'
    assert result.producer_event_id == 'b'*64 + ':STATE_BEGIN'
    assert result.producer_attempt_id is None
    assert result.severity == Severity.INFO
    recovered = record('transition_observations', '2', 1, state_identity='c'*64,
        state_code='FILLED', ticker='005930', event_family='BROKER_ORDER',
        broker_subject_id='order-1', severity='INFO', producer_event_code='STATE_RECOVERED')
    assert AlertDetector().detect(AlertSourceBatch(NOW, (recovered,)))[0].subject == result.subject


def test_unvalidated_release_and_generic_cleared_are_not_recovery():
    release = record('freezes', freeze_id='freeze', state='RELEASED')
    uncertain = record('orders', order_intent_id='intent', event_type='RECONCILED', broker_status='FILLED', unfilled_qty=0)
    assert AlertDetector().detect(AlertSourceBatch(NOW, (release,))) == ()
    assert not AlertDetector().detect(AlertSourceBatch(NOW, (uncertain,)))[0].positive_recovery


def test_finalized_evaluation_uses_saved_event_type_not_generic_status():
    unavailable = record('evaluations', status='FINALIZED', terminal_event_type='LLM_UNAVAILABLE', reason_code='TIMEOUT')
    result = AlertDetector().detect(AlertSourceBatch(NOW, (unavailable,)))[0]
    assert result.normalized_state == 'LLM_UNAVAILABLE' and not result.positive_recovery
    assert AlertDetector().detect(AlertSourceBatch(NOW, (record('evaluations', status='FINALIZED'),))) == ()
