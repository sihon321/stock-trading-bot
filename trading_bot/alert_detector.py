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
        for health in batch.service_health:
            facts.extend(self._service_health(health))
        return tuple(sorted(facts, key=lambda f: (f.observed_at, f.sequence, f.source_id)))

    @staticmethod
    def _service_health(health):
        env=health.envelope
        # Attention has an append-only occurrence/reset event. Its projection
        # appears on each worker but must not duplicate that one saved episode.
        if health.state=='SERVICE_MANUAL_ATTENTION':
            return ()
        if env.query_status=='OK' and health.state=='EXPECTATION_UNKNOWN' and env.source_observed_at is None:
            subject=AlertSubject(env.resource_id,env.account_hash,env.target,'ACCOUNT','EXPECTATION_UNKNOWN',health.subject_id)
            return (AlertSourceFact(subject,env.schema_owner,'expectation-missing:'+_saved_id(health.subject_id),
                0,env.query_at,'UNKNOWN',Severity.WARNING),)
        if env.query_status!='OK' or env.source_observed_at is None or not health.source_ids:
            return ()
        states={'MISSED_SCHEDULE':'MISSED_SCHEDULE','WORKER_STALLED':'WORKER_STALLED',
                'BLOCKED':'WORKER_STALLED','FAILED':'WORKER_STALLED','UNKNOWN':'WORKER_STALLED','RECOVERY_BLOCKED':'WORKER_STALLED',
                'EXPECTATION_UNKNOWN':'EXPECTATION_UNKNOWN','SERVICE_MANUAL_ATTENTION':'SERVICE_MANUAL_ATTENTION'}
        family=states.get(health.state)
        recovery=health.expected_running is True and health.mutation_ready is not False and health.last_progress_at is not None and health.state in {'RUNNING','COMPLETED','TERMINAL'}
        families=(family,) if family else ('MISSED_SCHEDULE','WORKER_STALLED','EXPECTATION_UNKNOWN') if recovery else ()
        facts=[]
        for family in families:
            subject=AlertSubject(env.resource_id,env.account_hash,env.target,'ACCOUNT',family,
                health.subject_id if family!='SERVICE_MANUAL_ATTENTION' else 'ATTENTION')
            key='service-health:'+_saved_id(subject.identity,health.source_ids,env.source_observed_at,health.state)
            facts.append(AlertSourceFact(subject,env.schema_owner,key,0,env.source_observed_at,
                'RECOVERED' if recovery else health.state,Severity.CRITICAL if family=='SERVICE_MANUAL_ATTENTION' else Severity.WARNING,
                recovery,key if recovery else None))
        return tuple(facts)

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
        if kind=='service_expectation_health' and d.get('state') in {'UNKNOWN','UNAVAILABLE'}:
            return self._fact(row,'EXPECTATION_UNKNOWN',d['state'],'WARNING',broker=d.get('source_kind') or 'SOURCE')
        if kind=='service_attention':
            if d.get('state') not in {'MANUAL_ATTENTION','RESET'}: return None
            return self._fact(row,'SERVICE_MANUAL_ATTENTION',d['state'],'CRITICAL',broker='ATTENTION',
                recovery=d['state']=='RESET')
        if kind=='service_job_events' and d.get('state')=='COMPLETED' and d.get('reason_code') in {'PREP_COMPLETED','PREP_READ_ONLY'}:
            return self._fact(row,'SERVICE_PREP','COMPLETED','INFO',broker=d.get('job_id') or 'PREP')
        if kind=='notifications':
            state=d.get('delivery_status')
            if state not in {'FAILED','UNKNOWN','DELIVERED'}: return None
            return self._fact(row,'NOTIFICATION_FAILURE',state,'WARNING',
                broker=d.get('run_id') or d.get('kind') or 'NOTIFICATION',recovery=state=='DELIVERED')
        if kind=='candidates' and d.get('reason_code') in {'QUOTE_STALE','STALE_QUOTE','MARKET_DATA_STALE'}:
            return self._fact(row,'MARKET_DATA_STALE','STALE','WARNING',broker='EXECUTION')
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
            unavailable = state == 'FINALIZED' and d.get('terminal_event_type') == 'LLM_UNAVAILABLE'
            if state == 'FINALIZED' and d.get('terminal_event_type') not in {'LLM_UNAVAILABLE', 'SIGNAL_FINALIZED'}:
                return None
            return self._fact(row, 'EVALUATION', 'LLM_UNAVAILABLE' if unavailable else state, 'WARNING',
                recovery=state in {'SIGNAL_FINALIZED', 'FINALIZED'} and not unavailable)
        if kind in {'orders', 'broker_orders'}:
            if d.get('event_type') in {'FRESHNESS_BLOCKED','FRESHNESS_CHECKED'}:
                recovery=d['event_type']=='FRESHNESS_CHECKED'
                return self._fact(row,'MARKET_DATA_STALE','FRESH' if recovery else 'STALE','WARNING',
                    broker='EXECUTION',recovery=recovery)
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
