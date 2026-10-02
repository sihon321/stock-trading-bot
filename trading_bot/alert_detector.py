"""Pure saved-fact adapter. Absence/UNKNOWN never resolves an incident.

Derived defaults: worker/cycle/evaluation failure WARNING; unresolved orders,
freezes, safety latches and broker divergence CRITICAL. Saved severity wins.
"""
from __future__ import annotations

import hashlib
import json

from .alert_models import AlertSourceFact, AlertSubject, DeliveryState, Severity


def _saved_id(*parts):
    return hashlib.sha256(json.dumps(parts, default=str, separators=(',', ':')).encode()).hexdigest()


class AlertDetector:
    def detect(self, batch):
        facts = []
        for row in batch.facts:
            fact = self._record(row)
            if fact is not None:
                facts.append(fact)
        for worker in batch.workers:
            fact = self._worker(worker, batch.query_at)
            if fact is not None:
                facts.append(fact)
        return tuple(sorted(facts, key=lambda f: (f.observed_at, f.sequence, f.source_id)))

    @staticmethod
    def _fact(row, family, state, default, *, broker='NONE', ticker=None,
              recovery=False, proof=None, producer=False):
        d, env = row.data, row.envelope
        source_id = row.record_id
        # Mutable projection rows do not define durable occurrences. Consume the
        # ordered append-only transition observations/attempts instead.
        try:
            sequence = int(source_id.rsplit(':', 1)[-1])
        except ValueError:
            sequence = 0
        subject = AlertSubject(env.resource_id, env.account_hash, env.target,
            ticker or d.get('ticker') or 'ACCOUNT', family, broker or 'NONE')
        event = d.get('event_code') or d.get('producer_event_code') or ('STATE_RECOVERED' if recovery else 'STATE_BEGIN')
        delivery = d.get('delivery_status')
        return AlertSourceFact(subject, env.schema_owner, source_id, sequence,
            env.source_observed_at, state, Severity(d.get('severity') or default),
            recovery, proof or (source_id if recovery else None),
            'producer' if producer else 'observer',
            f'{d["state_identity"]}:{event}' if producer else None,
            f'transition-notification:{source_id.rsplit(":", 1)[-1]}'
                if producer and row.kind == 'transition_notifications' else None,
            DeliveryState(delivery) if delivery in {'DELIVERED', 'FAILED', 'DISABLED'} else
                DeliveryState.UNKNOWN if producer else None)

    def _record(self, row):
        env, d, kind = row.envelope, row.data, row.kind
        if env.query_status != 'OK' or env.source_observed_at is None:
            return None
        if kind in {'transition_observations', 'transition_notifications'}:
            if not all(d.get(k) for k in ('state_identity', 'event_family')):
                return None
            state = d.get('state_code')
            # Notification rows are delivery receipts, not another occurrence.
            if kind == 'transition_notifications':
                return None
            recovery = d.get('producer_event_code') == 'STATE_RECOVERED'
            return self._fact(row, d['event_family'], state or 'UNKNOWN', 'WARNING',
                broker=d.get('broker_subject_id'), recovery=recovery, producer=True)
        if kind == 'runs':
            state = d.get('status')
            if state not in {'FAILED', 'INTERRUPTED', 'COMPLETED', 'PARTIAL', 'ABANDONED'}:
                return None
            return self._fact(row, 'CYCLE', state, 'WARNING',
                broker=d.get('run_kind') or 'UNKNOWN', recovery=state == 'COMPLETED')
        if kind == 'evaluations':
            state = d.get('status')
            if state not in {'FAILED', 'LLM_UNAVAILABLE', 'SIGNAL_FINALIZED', 'FINALIZED'}:
                return None
            unavailable = state == 'FINALIZED' and d.get('reason_code') == 'LLM_UNAVAILABLE'
            return self._fact(row, 'EVALUATION', 'LLM_UNAVAILABLE' if unavailable else state, 'WARNING',
                recovery=state in {'SIGNAL_FINALIZED', 'FINALIZED'} and not unavailable)
        if kind in {'orders', 'broker_orders'}:
            broker = d.get('order_intent_id') or d.get('broker_order_id')
            if not broker:
                return None
            recovery = (env.provenance == 'saved_broker_progression' or
                        d.get('event_type') in {'BROKER_OBSERVED', 'RECONCILED'}) and (
                d.get('broker_status') in {'FILLED', 'CANCELLED', 'REJECTED'} and
                d.get('unfilled_qty') == 0 and bool(d.get('broker_order_id')))
            return self._fact(row, 'UNRESOLVED_ORDER', 'TERMINAL' if recovery else 'UNRESOLVED',
                              'CRITICAL', broker=broker, recovery=recovery)
        if kind == 'freezes':
            state = d.get('state')
            recovery = state == 'RELEASED' and d.get('release_validated') is True and bool(d.get('release_evidence_id'))
            if state != 'FROZEN' and not recovery:
                return None
            return self._fact(row, 'FREEZE', state, 'CRITICAL', broker=d.get('freeze_id'),
                recovery=recovery, proof=d.get('release_evidence_id') if recovery else None)
        if kind == 'campaigns' and d.get('safety_failure_code'):
            # D-09 latch is irreversible; routine campaign completion isn't clear proof.
            return self._fact(row, 'SAFETY_LATCH', 'LATCHED', 'CRITICAL', broker=d.get('campaign_id'))
        if kind == 'divergences':
            code = d.get('code')
            if not code:
                return None
            recovery = d.get('state') == 'CLEARED' and bool(d.get('recovery_proof_id'))
            return self._fact(row, 'BROKER_DIVERGENCE', 'CLEARED' if recovery else code,
                'CRITICAL', broker=d.get('order_intent_id') or code,
                recovery=recovery, proof=d.get('recovery_proof_id'))
        return None

    @staticmethod
    def _worker(worker, now):
        env = worker.envelope
        if env.query_status != 'OK' or env.source_observed_at is None or not worker.source_ids:
            return None
        age = (now - env.source_observed_at).total_seconds()
        if age < 0:
            return None
        stale = (worker.expected_running is True and worker.cadence_seconds is not None
                 and age > max(180, 3 * worker.cadence_seconds))
        failed = worker.state == 'FAILED'
        fresh = (worker.expected_running is True and worker.cadence_seconds is not None
                 and not stale and worker.state == 'RUNNING')
        if not (failed or stale or fresh):
            return None
        state = 'FAILED' if failed else 'STALE' if stale else 'RECOVERED'
        saved = 'worker:' + _saved_id(worker.worker_id, worker.source_ids, env.source_observed_at, state)
        return AlertSourceFact(AlertSubject(env.resource_id, env.account_hash, env.target,
            'ACCOUNT', 'WORKER', worker.worker_id), env.schema_owner, saved, 0,
            env.source_observed_at, state, Severity.WARNING, fresh, saved if fresh else None)
