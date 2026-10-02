"""Explicit foreground monitoring, isolated from trading and browser lifecycle."""
from __future__ import annotations

from datetime import datetime, timezone
from contextlib import contextmanager
import json
import sqlite3
import uuid

from .alert_detector import AlertDetector
from .alert_models import AlertSubject, DeliveryState, timestamp
from .alert_store import AlertStore
from .notification_transport import DiscordNotifier, NoopNotifier
from .web_evidence import OperatorEvidenceService


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
                 clock=lambda: datetime.now(timezone.utc), after_send=None):
        self.settings, self.clock = settings, clock
        self.owner = uuid.uuid4().hex
        self.store = _ObserverStore(settings, clock=clock)
        self.detector = AlertDetector()
        self.evidence = evidence or OperatorEvidenceService(settings, clock=clock)
        # Construct transport lazily only for an explicitly started monitor.
        self.notifier, self.after_send = notifier, after_send
        self._owned = False

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
        batch = self.evidence.observe_alert_sources(self.store.get_checkpoint())
        if any(s.query_status != 'OK' for s in batch.sources
               if s.schema_owner in {'audit', 'portfolio', 'soak', 'controller'}):
            raise ObserverEvidenceError('SOURCE_FAILED')
        for fact in self.detector.detect(batch):
            self.store.observe(fact)
        self._receipts(batch)
        if batch.cursor is not None:
            self.store.set_checkpoint(batch.cursor)
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
