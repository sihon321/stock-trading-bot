"""Explicit foreground monitoring, isolated from trading and browser lifecycle."""
from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import dataclass, replace
from contextlib import contextmanager
import json
import sqlite3
import uuid

from .alert_detector import AlertDetector
from .alert_models import AlertSubject, AlertSourceFact, Severity, DeliveryState, timestamp
from .alert_store import AlertStore
from .notification_transport import DiscordNotifier, NoopNotifier
from .web_evidence import OperatorEvidenceService
from .web_models import AlertSourceBatch, SourceEnvelope, KST


@dataclass(frozen=True)
class ScanSourceOutcome:
    resource_id: str
    source_owner: str
    state: str
    diagnostic_code: str | None = None


class ObserverBusy(ValueError):
    """A positively recent operational observer already owns dispatch."""


class ObserverEvidenceError(RuntimeError):
    """Mandatory operational evidence/ownership failed; no further dispatch."""


class _ObserverStore(AlertStore):
    """Revalidate source isolation at every operational transaction boundary."""
    def __init__(self, settings, *, clock):
        self.settings = settings
        super().__init__(settings.operational_db_path, clock=clock)

    @contextmanager
    def connection(self, **kwargs):
        self.settings.validate_topology()
        with super().connection(**kwargs) as conn:
            yield conn


class AlertObserver:
    def __init__(self, settings, *, evidence=None, notifier=None,
                 clock=lambda: datetime.now(timezone.utc), after_send=None, expectation_producer=None):
        self.settings, self.clock = settings, clock
        self.owner = uuid.uuid4().hex
        self.store = _ObserverStore(settings, clock=clock)
        self.detector = AlertDetector()
        self.evidence = evidence or OperatorEvidenceService(settings, clock=clock)
        # Construct transport lazily only for an explicitly started monitor.
        self.notifier, self.after_send = notifier, after_send
        self._owned = False
        self.expectation_producer=expectation_producer
        self.last_source_outcomes=()

    def _source_fact(self, env, now, *, family='SERVICE_SOURCE_UNAVAILABLE'):
        """Persist availability transitions without poll-time freshness renewal."""
        if env.target not in {'mock','real','simulated','unknown'}:
            return None
        subject=AlertSubject(env.resource_id,env.account_hash,env.target,'ACCOUNT',family,'SOURCE')
        existing=next((e for e in self.store.list_incidents(active=True,resource_id=env.resource_id)
            if e.subject==subject),None)
        healthy=env.query_status=='OK' and env.source_observed_at is not None and env.source_observed_at<=now
        if healthy:
            if existing is None or env.query_at<existing.first_observed_at or env.query_at>self.clock():
                return None
            # Successful source reading recovers availability, not data freshness.
            key='source-recovered:'+existing.episode_id+':'+str(int(env.query_at.timestamp()*1000000))
            return AlertSourceFact(subject,env.schema_owner,key,0,env.query_at,'AVAILABLE',Severity.WARNING,
                True,key)
        if env.query_status=='OK':
            return None
        stamp=existing.first_observed_at if existing else now
        key='source-unavailable:'+(existing.episode_id if existing else str(int(stamp.timestamp()*1000000)))+':'+family
        # First source failure is stable even across process restart. Existing
        # incident has already recorded it; no repeated occurrence is invented.
        if existing is not None:
            return None
        return AlertSourceFact(subject,env.schema_owner,key,0,stamp,'UNAVAILABLE',Severity.WARNING)

    def _unavailable_sources(self, now):
        resources=self.settings.registered_resources
        return tuple(SourceEnvelope(r.id,r.owner,None,r.account_hash,r.target,now,
            query_status='FAILED',diagnostic_code='SOURCE_UNAVAILABLE') for r in resources) or (
                SourceEnvelope('observer-source','service',None,'0'*64,'mock',now,
                    query_status='FAILED',diagnostic_code='SOURCE_UNAVAILABLE'),)

    def _initialize(self):
        self.settings.validate_topology()
        self.store.initialize()
        with self.store.connection() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS phase14_alert_observer_metadata(singleton INTEGER PRIMARY KEY CHECK(singleton=1),version INTEGER NOT NULL)')
            conn.execute('INSERT OR IGNORE INTO phase14_alert_observer_metadata VALUES(1,1)')
            if conn.execute('SELECT version FROM phase14_alert_observer_metadata').fetchone()[0] != 1:
                raise ObserverEvidenceError('OBSERVER_SCHEMA_UNSUPPORTED')
            conn.execute('CREATE TABLE IF NOT EXISTS alert_observer(singleton INTEGER PRIMARY KEY CHECK(singleton=1),owner TEXT,state TEXT NOT NULL,started_at REAL,heartbeat_at REAL,stopped_at REAL,failure_code TEXT)')
            conn.execute('CREATE TABLE IF NOT EXISTS alert_observer_events(id INTEGER PRIMARY KEY,owner TEXT NOT NULL,state TEXT NOT NULL,at REAL NOT NULL,failure_code TEXT)')
            conn.execute('CREATE TABLE IF NOT EXISTS alert_observer_receipts(source_owner TEXT,resource_id TEXT,source_id TEXT,payload TEXT NOT NULL,linked INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(source_owner,resource_id,source_id))')

    def start(self):
        self._initialize()
        now = timestamp(self.clock())
        with self.store.connection() as conn:
            prior = conn.execute('SELECT * FROM alert_observer WHERE singleton=1').fetchone()
            if prior and prior['owner']:
                # Clock reversal cannot grant takeover; bounded transport has
                # one attempt with a 5s per-phase timeout (<300s ownership age).
                if now - prior['heartbeat_at'] <= self.settings.takeover_after_seconds:
                    raise ObserverBusy('OBSERVER_ALREADY_RUNNING')
                for row in conn.execute("SELECT event_key FROM alert_outbox WHERE state='CLAIMED' AND owner=?", (prior['owner'],)).fetchall():
                    conn.execute("UPDATE alert_outbox SET state='UNKNOWN',finalized_at=?,failure_code='OBSERVER_LOST' WHERE event_key=?", (now, row[0]))
                    self.store._history(conn, row[0])
                conn.execute('INSERT INTO alert_observer_events(owner,state,at,failure_code) VALUES(?,?,?,?)',
                             (prior['owner'], 'FAILED', now, 'HEARTBEAT_EXPIRED'))
            conn.execute("INSERT INTO alert_observer VALUES(1,?,'RUNNING',?,?,NULL,NULL) ON CONFLICT(singleton) DO UPDATE SET owner=excluded.owner,state=excluded.state,started_at=excluded.started_at,heartbeat_at=excluded.heartbeat_at,stopped_at=NULL,failure_code=NULL", (self.owner, now, now))
            conn.execute("INSERT INTO alert_observer_events(owner,state,at) VALUES(?,'STARTED',?)", (self.owner, now))
        self._owned = True
        if self.notifier is None:
            self.notifier = (DiscordNotifier(webhook_url=self.settings.webhook_url,
                max_retries=1, timeout_seconds=5) if self.settings.webhook_url else NoopNotifier())

    def heartbeat(self):
        try:
            with self.store.connection() as conn:
                changed = conn.execute("UPDATE alert_observer SET heartbeat_at=? WHERE singleton=1 AND owner=? AND state='RUNNING'",
                                       (timestamp(self.clock()), self.owner)).rowcount
                if changed != 1:
                    raise ObserverEvidenceError('OBSERVER_OWNERSHIP_LOST')
        except (sqlite3.Error, ValueError, OSError):
            raise ObserverEvidenceError('OBSERVER_EVIDENCE_FAILED') from None

    def stop(self, *, failure_code=None):
        if not self._owned:
            return
        state, now = ('FAILED' if failure_code else 'STOPPED'), timestamp(self.clock())
        try:
            with self.store.connection() as conn:
                # In-flight uncertainty is terminal even for graceful interruption.
                for row in conn.execute("SELECT event_key FROM alert_outbox WHERE state='CLAIMED' AND owner=?", (self.owner,)).fetchall():
                    conn.execute("UPDATE alert_outbox SET state='UNKNOWN',finalized_at=?,failure_code='OBSERVER_STOPPED' WHERE event_key=?", (now, row[0]))
                    self.store._history(conn, row[0])
                changed = conn.execute('UPDATE alert_observer SET owner=NULL,state=?,stopped_at=?,failure_code=? WHERE singleton=1 AND owner=?',
                                       (state, now, failure_code, self.owner)).rowcount
                if changed:
                    conn.execute('INSERT INTO alert_observer_events(owner,state,at,failure_code) VALUES(?,?,?,?)',
                                 (self.owner, state, now, failure_code))
        except (sqlite3.Error, ValueError, OSError):
            raise ObserverEvidenceError('OBSERVER_EVIDENCE_FAILED') from None
        finally:
            self._owned = False

    def _receipts(self, batch):
        with self.store.connection() as conn:
            for row in batch.facts:
                d, env = row.data, row.envelope
                if row.kind != 'transition_notifications' or env.query_status != 'OK' or env.source_observed_at is None:
                    continue
                if not d.get('event_family') or not d.get('state_identity'):
                    continue
                subject = AlertSubject(row.resource_id, env.account_hash, env.target,
                    d.get('ticker') or 'ACCOUNT', d['event_family'], d.get('broker_subject_id') or 'NONE')
                payload = dict(subject_id=subject.identity,
                    producer_event_id=d['state_identity'] + ':' + d['event_code'],
                    producer_attempt_id='transition-notification:' + row.record_id.rsplit(':', 1)[-1],
                    state=d['delivery_status'] if d['delivery_status'] in {'DELIVERED', 'FAILED', 'DISABLED'} else 'UNKNOWN',
                    at=env.source_observed_at.isoformat(),
                    kind='RECOVERY' if d['event_code'] == 'STATE_RECOVERED' else 'WORSENING' if d['event_code'] == 'STATE_CHANGED' else 'OCCURRENCE')
                conn.execute('INSERT OR IGNORE INTO alert_observer_receipts(source_owner,resource_id,source_id,payload) VALUES(?,?,?,?)',
                    (env.schema_owner, row.resource_id, row.record_id, json.dumps(payload)))
            receipts = conn.execute('SELECT * FROM alert_observer_receipts WHERE linked=0 ORDER BY rowid LIMIT 100').fetchall()
        for row in receipts:
            data = json.loads(row['payload'])
            with self.store.connection() as conn:
                episode = conn.execute('SELECT episode_id,revision FROM alert_episodes WHERE subject_id=? AND first_at<=? ORDER BY first_at DESC LIMIT 1',
                    (data['subject_id'], timestamp(datetime.fromisoformat(data['at'])))).fetchone()
            if episode is None:
                continue
            self.store.link_producer_delivery(episode['episode_id'], episode['revision'], data['kind'],
                source_owner=row['source_owner'], resource_id=row['resource_id'],
                producer_event_id=data['producer_event_id'], producer_attempt_id=data['producer_attempt_id'],
                state=DeliveryState(data['state']), at=datetime.fromisoformat(data['at']))
            with self.store.connection() as conn:
                conn.execute('UPDATE alert_observer_receipts SET linked=1 WHERE source_owner=? AND resource_id=? AND source_id=?',
                             (row['source_owner'], row['resource_id'], row['source_id']))

    def _scan(self, now, stop_event=None):
        self.heartbeat()
        # Observer-owned reads stay outside source exception handling: corruption,
        # failed checkpoints and lost ownership still stop delivery fail-closed.
        checkpoint=self.store.get_checkpoint()
        expectation_healthy=True
        if self.expectation_producer is not None:
            try:
                if self.settings.expectation_service_config_path is not None:
                    from .service_config import protected_file
                    path=protected_file(self.settings.expectation_service_config_path)
                    if path!=self.expectation_producer.config_path.absolute():
                        raise ValueError('registered expectation producer required')
                records=self.expectation_producer.publish()
                expectation_healthy=all(r.state!='UNKNOWN' or r.reason_code=='DUE_HISTORY_UNKNOWN' for r in (records or ()))
            except Exception:
                expectation_healthy=False
        elif self.settings.expectation_service_config_path is not None:
            expectation_healthy=False
        try:
            batch = self.evidence.observe_alert_sources(checkpoint)
        except Exception:
            batch=AlertSourceBatch(now,sources=self._unavailable_sources(now))
        failed={s.resource_id for s in batch.sources if s.query_status!='OK'}
        failed.update(r.resource_id for r in batch.facts if r.envelope.query_status!='OK')
        self.last_source_outcomes=tuple(ScanSourceOutcome(s.resource_id,s.schema_owner,
            'UNAVAILABLE' if s.resource_id in failed else 'AVAILABLE',s.diagnostic_code) for s in batch.sources)
        healthy=replace(batch,facts=tuple(r for r in batch.facts if r.resource_id not in failed),
            workers=tuple(w for w in batch.workers if w.envelope.resource_id not in failed),
            service_health=tuple(h for h in batch.service_health if h.envelope.resource_id not in failed))
        for fact in self.detector.detect(healthy):
            self.store.observe(fact)
        for env in batch.sources:
            fact=self._source_fact(replace(env,query_status='FAILED') if env.resource_id in failed else env,now)
            if fact is not None: self.store.observe(fact)
        if not expectation_healthy:
            for env in self._unavailable_sources(now):
                if env.schema_owner=='service':
                    fact=self._source_fact(env,now,family='EXPECTATION_UNKNOWN')
                    if fact is not None: self.store.observe(fact)
        else:
            for env in batch.sources:
                if env.schema_owner=='service' and env.resource_id not in failed:
                    fact=self._source_fact(env,now,family='EXPECTATION_UNKNOWN')
                    if fact is not None: self.store.observe(fact)
        self._receipts(healthy)
        # Only reader-certified healthy stream positions can advance on partial
        # reads. Failed partitions remain at their prior checkpoint for recovery.
        progress = batch.partial_cursor if failed else batch.cursor
        if progress is not None and expectation_healthy:
            self.store.set_checkpoint(progress)
        self.store.due_reminders(now)
        sent = 0
        for event in self.store.pending_deliveries():
            if stop_event is not None and stop_event.is_set():
                break
            self.heartbeat()
            claim = self.store.claim_delivery(event.event_key, self.owner)
            if claim is None:
                continue
            episode = self.store.get(claim.episode_id)
            text = f'[{episode.severity.value}] {claim.kind}: {episode.subject.problem_family} / {episode.subject.ticker_or_account} / {episode.normalized_state}'
            text += f'\n원천: {episode.subject.resource_id} · 대상 기록: {episode.subject.broker_subject}'
            text += '\n원천 관측: ' + episode.last_observed_at.astimezone(KST).strftime('%Y-%m-%d %H:%M:%S KST')
            if claim.kind == 'REMINDER':
                text += '\n미확인 알림 반복입니다. 웹에서 읽음 처리하면 반복이 멈춥니다.'
            try:
                result = self.notifier.send(text)
                state = DeliveryState.DISABLED if isinstance(self.notifier, NoopNotifier) else DeliveryState.DELIVERED if result else DeliveryState.FAILED
                failure = None if state != DeliveryState.FAILED else 'TRANSPORT_FAILED'
            except Exception:
                state, failure = DeliveryState.UNKNOWN, 'TRANSPORT_UNCERTAIN'
            if self.after_send:
                self.after_send()
            self.store.finalize_attempt(claim.event_key, self.owner, claim.claim_id, state, failure_code=failure)
            sent += 1
        return sent

    def scan_once(self, now=None):
        self.start()
        failure = None
        try:
            return self._scan(now or self.clock())
        except Exception:
            failure = 'SOURCE_FAILED'
            raise ObserverEvidenceError(failure) from None
        finally:
            self.stop(failure_code=failure)

    def watch(self, stop_event):
        self.start()
        failure = None
        try:
            while not stop_event.is_set():
                self._scan(self.clock(), stop_event)
                stop_event.wait(self.settings.scan_interval_seconds)
        except Exception:
            failure = 'SOURCE_FAILED'
            raise ObserverEvidenceError(failure) from None
        finally:
            self.stop(failure_code=failure)

    def status(self):
        """Credential-free, query-only inspection; never initialize or acquire."""
        path = self.settings.validate_topology()
        result = dict(state='NOT_STARTED', heartbeat_age_seconds=None,
                      started_at=None, stopped_at=None, failure_code=None, cursor=None, deliveries={})
        if not path.is_file():
            return result
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=1) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA query_only=ON')
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'alert_observer' in tables:
                row = conn.execute('SELECT * FROM alert_observer WHERE singleton=1').fetchone()
                if row:
                    result.update(state=row['state'], started_at=row['started_at'], stopped_at=row['stopped_at'], failure_code=row['failure_code'])
                    result['heartbeat_age_seconds'] = max(0, timestamp(self.clock()) - row['heartbeat_at'])
                    if row['owner'] and result['heartbeat_age_seconds'] > self.settings.takeover_after_seconds:
                        result['state'] = 'STALE'
            if 'alert_checkpoints' in tables:
                row = conn.execute("SELECT cursor FROM alert_checkpoints WHERE stream='sources'").fetchone()
                result['cursor'] = row[0] if row else None
            if 'alert_outbox' in tables:
                result['deliveries'] = dict(conn.execute('SELECT state,COUNT(*) FROM alert_outbox GROUP BY state'))
        return result
