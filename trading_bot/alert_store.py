"""Independent operational incident metadata; never connects to trading sources."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import uuid

from .alert_models import (Acknowledgement, AlertAction, AlertSourceFact, AlertSubject,
                           DeliveryAttempt, DeliveryState, IncidentEpisode, Severity,
                           SeverityRevision, bounded_identity, timestamp)

ALERT_SCHEMA_VERSION = 2


class RevisionConflict(ValueError):
    """The selected revision is no longer the currently observed revision."""


def _instant(value):
    return None if value is None else datetime.fromtimestamp(value, timezone.utc)


_V1 = (
    'CREATE TABLE phase14_alert_metadata(singleton INTEGER PRIMARY KEY CHECK(singleton=1), version INTEGER NOT NULL)',
    'INSERT INTO phase14_alert_metadata VALUES(1,1)',
    '''CREATE TABLE alert_episodes(episode_id TEXT PRIMARY KEY, subject_id TEXT NOT NULL,
       subject_json TEXT NOT NULL, revision INTEGER NOT NULL, severity TEXT NOT NULL,
       normalized_state TEXT NOT NULL, active INTEGER NOT NULL, first_at REAL NOT NULL,
       last_at REAL NOT NULL, occurrence_count INTEGER NOT NULL, recovered_at REAL,
       recovery_proof_id TEXT, next_reminder_at REAL)''',
    'CREATE UNIQUE INDEX alert_one_active_subject ON alert_episodes(subject_id) WHERE active=1',
    '''CREATE TABLE alert_observations(source_owner TEXT NOT NULL, resource_id TEXT NOT NULL,
       source_id TEXT NOT NULL, sequence INTEGER NOT NULL, observed_at REAL NOT NULL,
       subject_id TEXT NOT NULL, normalized_state TEXT NOT NULL, severity TEXT NOT NULL,
       positive_recovery INTEGER NOT NULL, recovery_proof_id TEXT, episode_id TEXT,
       PRIMARY KEY(source_owner,resource_id,source_id))''',
    '''CREATE TABLE alert_cursors(source_owner TEXT NOT NULL, resource_id TEXT NOT NULL,
       sequence INTEGER NOT NULL, PRIMARY KEY(source_owner,resource_id))''',
    '''CREATE TABLE alert_revisions(episode_id TEXT NOT NULL REFERENCES alert_episodes,
       revision INTEGER NOT NULL, severity TEXT NOT NULL, observed_at REAL NOT NULL,
       source_owner TEXT NOT NULL, source_id TEXT NOT NULL, PRIMARY KEY(episode_id,revision))''',
    '''CREATE TABLE alert_acknowledgements(acknowledgement_id INTEGER PRIMARY KEY,
       episode_id TEXT NOT NULL, revision INTEGER NOT NULL, actor TEXT NOT NULL, at REAL NOT NULL,
       note TEXT CHECK(note IS NULL OR length(note)<=500), UNIQUE(episode_id,revision),
       FOREIGN KEY(episode_id,revision) REFERENCES alert_revisions)''',
    '''CREATE TABLE alert_actions(action_id INTEGER PRIMARY KEY, actor TEXT NOT NULL,
       action TEXT NOT NULL, episode_id TEXT NOT NULL, revision INTEGER NOT NULL,
       result_code TEXT NOT NULL, at REAL NOT NULL)''',
)

_V2 = (
    '''CREATE TABLE alert_outbox(event_key TEXT PRIMARY KEY,
       episode_id TEXT NOT NULL REFERENCES alert_episodes, revision INTEGER NOT NULL,
       kind TEXT NOT NULL, delivery_owner TEXT NOT NULL, state TEXT NOT NULL, due_at REAL NOT NULL,
       claim_id TEXT UNIQUE, owner TEXT, claimed_at REAL, finalized_at REAL, failure_code TEXT,
       producer_event_id TEXT, producer_attempt_id TEXT,
       UNIQUE(episode_id,revision,kind,due_at))''',
    '''CREATE TABLE alert_producer_links(source_owner TEXT NOT NULL,resource_id TEXT NOT NULL,
       producer_event_id TEXT NOT NULL,event_key TEXT NOT NULL REFERENCES alert_outbox,
       episode_id TEXT NOT NULL REFERENCES alert_episodes,revision INTEGER NOT NULL,
       PRIMARY KEY(source_owner,resource_id,producer_event_id,episode_id,revision))''',
    '''CREATE TABLE alert_producer_attempts(source_owner TEXT NOT NULL,resource_id TEXT NOT NULL,
       producer_attempt_id TEXT NOT NULL,event_key TEXT NOT NULL REFERENCES alert_outbox,
       state TEXT NOT NULL,at REAL NOT NULL,
       PRIMARY KEY(source_owner,resource_id,producer_attempt_id))''',
    '''CREATE TABLE alert_delivery_history(history_id INTEGER PRIMARY KEY,
       event_key TEXT NOT NULL REFERENCES alert_outbox, payload_json TEXT NOT NULL)''',
    'CREATE INDEX alert_delivery_due ON alert_outbox(state,due_at)',
    'CREATE TABLE alert_checkpoints(stream TEXT PRIMARY KEY,cursor TEXT NOT NULL)',
)


class AlertStore:
    def __init__(self, path: Path | str, *, clock=None):
        self.path = Path(path).absolute()
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _verify_ownership(self):
        if self.path.is_symlink() or (self.path.exists() and self.path.stat().st_nlink != 1):
            raise ValueError('invalid operational ownership')
        if not self.path.exists() or not self.path.stat().st_size:
            return 0
        try:
            with sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True) as conn:
                tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if any(not name.startswith(('alert_', 'phase14_alert_', 'web_', 'phase14_web_'))
                       for name in tables):
                    raise ValueError('operational storage ownership mismatch')
                if 'phase14_web_metadata' in tables:
                    row = conn.execute('SELECT version FROM phase14_web_metadata WHERE singleton=1').fetchone()
                    if row is None or row[0] not in (1, 2):
                        raise ValueError('unsupported web operational schema')
                if 'phase14_alert_metadata' not in tables:
                    if tables and ('phase14_web_metadata' not in tables or any(n.startswith('alert_') for n in tables)):
                        raise ValueError('operational storage ownership missing')
                    return 0
                row = conn.execute('SELECT version FROM phase14_alert_metadata WHERE singleton=1').fetchone()
                if row is None or row[0] not in (1, ALERT_SCHEMA_VERSION):
                    raise ValueError('unsupported alert operational schema')
                return row[0]
        except sqlite3.DatabaseError:
            raise ValueError('invalid operational storage ownership') from None

    def initialize(self, *, fail_after_step: str | None = None):
        self._verify_ownership()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.parent.stat().st_mode & 0o022:
            raise ValueError('operational directory must be owner protected')
        if not self.path.exists():
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_WRONLY, 0o600)
            os.close(fd)
        with self.connection(check_owner=False) as conn:
            # Recheck inside the writer transaction to serialize independent initializers.
            row = conn.execute("SELECT name FROM sqlite_master WHERE name='phase14_alert_metadata'").fetchone()
            if row is None:
                for statement in _V1:
                    conn.execute(statement)
                for table in ('alert_observations', 'alert_revisions', 'alert_acknowledgements', 'alert_actions'):
                    for operation in ('UPDATE', 'DELETE'):
                        conn.execute(f"CREATE TRIGGER {table}_no_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'append-only alert evidence'); END")
            version = conn.execute('SELECT version FROM phase14_alert_metadata WHERE singleton=1').fetchone()[0]
            if version < 2:
                for statement in _V2:
                    conn.execute(statement)
                if fail_after_step == 'outbox':
                    raise RuntimeError('injected alert migration failure')
                for table in ('alert_producer_links', 'alert_producer_attempts', 'alert_delivery_history'):
                    for operation in ('UPDATE', 'DELETE'):
                        conn.execute(f"CREATE TRIGGER {table}_no_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'append-only delivery evidence'); END")
                conn.execute('UPDATE phase14_alert_metadata SET version=2 WHERE singleton=1')

    @contextmanager
    def connection(self, *, check_owner=True):
        if check_owner and self._verify_ownership() != ALERT_SCHEMA_VERSION:
            raise ValueError('alert storage not initialized')
        if self.path.stat().st_mode & 0o077:
            raise ValueError('operational DB must be owner protected')
        conn = sqlite3.connect(self.path.as_uri() + '?mode=rw', uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('PRAGMA foreign_keys=ON')
            conn.execute('BEGIN IMMEDIATE')
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _incident(self, conn, episode_id):
        row = conn.execute('SELECT * FROM alert_episodes WHERE episode_id=?', (episode_id,)).fetchone()
        if row is None:
            return None
        acknowledged = conn.execute('SELECT 1 FROM alert_acknowledgements WHERE episode_id=? AND revision=?',
                                    (episode_id, row['revision'])).fetchone() is not None
        return IncidentEpisode(row['episode_id'], AlertSubject(*json.loads(row['subject_json'])),
            row['revision'], Severity(row['severity']), row['normalized_state'], bool(row['active']),
            _instant(row['first_at']), _instant(row['last_at']), row['occurrence_count'],
            row['last_at'] - row['first_at'], _instant(row['recovered_at']), row['recovery_proof_id'],
            acknowledged, _instant(row['next_reminder_at']))

    def observe(self, fact: AlertSourceFact) -> IncidentEpisode | None:
        if not isinstance(fact, AlertSourceFact):
            raise ValueError('typed alert fact required')
        with self.connection() as conn:
            existing = conn.execute('SELECT episode_id FROM alert_observations WHERE source_owner=? AND resource_id=? AND source_id=?',
                (fact.source_owner, fact.subject.resource_id, fact.source_id)).fetchone()
            if existing is not None:
                return self._incident(conn, existing['episode_id'])
            stamp = timestamp(fact.observed_at)
            current = conn.execute('SELECT * FROM alert_episodes WHERE subject_id=? AND active=1',
                                   (fact.subject.identity,)).fetchone()
            if current is not None and stamp < current['first_at']:
                historical = conn.execute('SELECT * FROM alert_episodes WHERE subject_id=? AND recovered_at>=? ORDER BY recovered_at ASC LIMIT 1',
                    (fact.subject.identity, stamp)).fetchone()
                if historical is not None:
                    current = historical
            episode_id = None if current is None else current['episode_id']
            kind = None
            if current is None and not fact.positive_recovery:
                # Historical inserts after a closed episode cannot manufacture a recurrence.
                historical = conn.execute('SELECT * FROM alert_episodes WHERE subject_id=? AND recovered_at>=? ORDER BY recovered_at DESC LIMIT 1',
                    (fact.subject.identity, stamp)).fetchone()
                if historical is not None:
                    episode_id = historical['episode_id']
                    current = historical
                    conn.execute('UPDATE alert_episodes SET first_at=min(first_at,?),occurrence_count=occurrence_count+1 WHERE episode_id=?',
                                 (stamp, episode_id))
                else:
                    episode_id = uuid.uuid4().hex
                    kind = 'OCCURRENCE'
                    due = timestamp(self.clock()) + 1800 if fact.severity == Severity.CRITICAL else None
                    conn.execute('INSERT INTO alert_episodes VALUES(?,?,?,?,?,?,1,?,?,1,NULL,NULL,?)',
                        (episode_id, fact.subject.identity, json.dumps(fact.subject.parts), 1,
                         fact.severity.value, fact.normalized_state, stamp, stamp, due))
                    conn.execute('INSERT INTO alert_revisions VALUES(?,?,?,?,?,?)',
                        (episode_id, 1, fact.severity.value, stamp, fact.source_owner, fact.source_id))
            elif current is not None:
                first = min(stamp, current['first_at'])
                last = max(stamp, current['last_at'])
                revision = current['revision']
                severity = Severity(current['severity'])
                state = current['normalized_state']
                due = current['next_reminder_at']
                active = current['active']
                recovered_at = current['recovered_at']
                proof = current['recovery_proof_id']
                if active and stamp >= current['last_at']:
                    if fact.positive_recovery:
                        active, recovered_at, proof, due = 0, stamp, fact.recovery_proof_id, None
                        kind = 'RECOVERY'
                    else:
                        state = fact.normalized_state
                        if fact.severity.rank > severity.rank:
                            revision += 1
                            kind = 'WORSENING'
                            severity = fact.severity
                            due = timestamp(self.clock()) + 1800 if severity == Severity.CRITICAL else None
                            conn.execute('INSERT INTO alert_revisions VALUES(?,?,?,?,?,?)',
                                (episode_id, revision, severity.value, stamp, fact.source_owner, fact.source_id))
                        elif fact.severity.rank < severity.rank:
                            severity, due = fact.severity, None
                conn.execute('UPDATE alert_episodes SET revision=?,severity=?,normalized_state=?,active=?,first_at=?,last_at=?,occurrence_count=occurrence_count+1,recovered_at=?,recovery_proof_id=?,next_reminder_at=? WHERE episode_id=?',
                    (revision, severity.value, state, active, first, last, recovered_at, proof, due, episode_id))
            conn.execute('INSERT INTO alert_observations VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (fact.source_owner, fact.subject.resource_id, fact.source_id, fact.sequence, stamp,
                 fact.subject.identity, fact.normalized_state, fact.severity.value,
                 int(fact.positive_recovery), fact.recovery_proof_id, episode_id))
            conn.execute('INSERT INTO alert_cursors VALUES(?,?,?) ON CONFLICT(source_owner,resource_id) DO UPDATE SET sequence=max(sequence,excluded.sequence)',
                (fact.source_owner, fact.subject.resource_id, fact.sequence))
            episode = self._incident(conn, episode_id)
            if episode is not None and kind is not None:
                if fact.delivery_owner == 'producer':
                    self._link_producer(conn, episode_id, episode.revision, kind,
                        fact.source_owner, fact.subject.resource_id, fact.producer_event_id or fact.source_id,
                        fact.producer_attempt_id, fact.producer_delivery_state or DeliveryState.UNKNOWN, stamp)
                elif episode.severity != Severity.INFO:
                    self._queue(conn, episode_id, episode.revision, kind, timestamp(self.clock()))
            return self._incident(conn, episode_id)

    def get_cursor(self, source_owner: str, resource_id: str) -> int | None:
        with self.connection() as conn:
            row = conn.execute('SELECT sequence FROM alert_cursors WHERE source_owner=? AND resource_id=?',
                               (source_owner, resource_id)).fetchone()
            return None if row is None else row[0]

    def get_incident(self, episode_id: str) -> IncidentEpisode | None:
        with self.connection() as conn:
            return self._incident(conn, episode_id)

    get = get_incident

    def list_incidents(self, *, active: bool | None = None, severity: Severity | None = None,
                       resource_id: str | None = None, limit: int = 100) -> tuple[IncidentEpisode, ...]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('bounded incident limit required')
        where, args = [], []
        if active is not None:
            where.append('active=?')
            args.append(int(active))
        if severity is not None:
            where.append('severity=?')
            args.append(Severity(severity).value)
        if resource_id is not None:
            where.append('json_extract(subject_json,\'$[0]\')=?')
            args.append(bounded_identity(resource_id))
        sql = 'SELECT episode_id FROM alert_episodes' + (' WHERE ' + ' AND '.join(where) if where else '')
        with self.connection() as conn:
            return tuple(self._incident(conn, row[0]) for row in conn.execute(sql + ' ORDER BY last_at DESC,episode_id LIMIT ?', (*args, limit)))

    def list_revisions(self, episode_id: str) -> tuple[SeverityRevision, ...]:
        with self.connection() as conn:
            return tuple(SeverityRevision(r['episode_id'], r['revision'], Severity(r['severity']),
                _instant(r['observed_at']), r['source_owner'], r['source_id']) for r in
                conn.execute('SELECT * FROM alert_revisions WHERE episode_id=? ORDER BY revision LIMIT 1000', (episode_id,)))

    def list_acknowledgements(self, episode_id: str) -> tuple[Acknowledgement, ...]:
        with self.connection() as conn:
            return tuple(self._ack(r) for r in conn.execute('SELECT * FROM alert_acknowledgements WHERE episode_id=? ORDER BY acknowledgement_id LIMIT 1000', (episode_id,)))

    @staticmethod
    def _ack(row):
        return Acknowledgement(row['acknowledgement_id'], row['episode_id'], row['revision'],
                               row['actor'], _instant(row['at']), row['note'])

    def acknowledge(self, episode_id: str, revision: int, actor: str, at: datetime | None = None,
                    note: str | None = None) -> Acknowledgement:
        bounded_identity(actor, limit=64)
        if type(revision) is not int or revision < 1:
            raise ValueError('expected revision required')
        if note is not None and (not isinstance(note, str) or len(note) > 500):
            raise ValueError('note must be at most 500 characters')
        # Actor comes from authenticated server session; supplied browser time has no authority.
        now = timestamp(self.clock())
        conflict = False
        with self.connection() as conn:
            current = conn.execute('SELECT revision FROM alert_episodes WHERE episode_id=?', (episode_id,)).fetchone()
            conflict = current is None or current[0] != revision
            conn.execute('INSERT INTO alert_actions(actor,action,episode_id,revision,result_code,at) VALUES(?,?,?,?,?,?)',
                (actor, 'ACKNOWLEDGE', episode_id, revision, 'REVISION_CONFLICT' if conflict else 'SUCCESS', now))
            if not conflict:
                conn.execute('INSERT OR IGNORE INTO alert_acknowledgements(episode_id,revision,actor,at,note) VALUES(?,?,?,?,?)',
                    (episode_id, revision, actor, now, note))
                result = self._ack(conn.execute('SELECT * FROM alert_acknowledgements WHERE episode_id=? AND revision=?', (episode_id, revision)).fetchone())
                conn.execute('UPDATE alert_episodes SET next_reminder_at=NULL WHERE episode_id=?', (episode_id,))
        if conflict:
            raise RevisionConflict('currently observed revision required')
        return result

    def list_actions(self) -> tuple[AlertAction, ...]:
        with self.connection() as conn:
            return tuple(AlertAction(r['actor'], r['action'], r['episode_id'], r['revision'],
                r['result_code'], _instant(r['at'])) for r in conn.execute('SELECT * FROM alert_actions ORDER BY action_id DESC LIMIT 100'))[::-1]

    @staticmethod
    def _event_key(*parts):
        return hashlib.sha256(json.dumps(parts, separators=(',', ':')).encode()).hexdigest()

    @staticmethod
    def _delivery(row):
        if row is None:
            return None
        return DeliveryAttempt(row['event_key'], row['episode_id'], row['revision'], row['kind'],
            row['delivery_owner'], DeliveryState(row['state']), _instant(row['due_at']),
            row['claim_id'], row['owner'], _instant(row['claimed_at']), _instant(row['finalized_at']),
            row['failure_code'], row['producer_event_id'], row['producer_attempt_id'])

    def _history(self, conn, event_key):
        attempt = self._delivery(conn.execute('SELECT * FROM alert_outbox WHERE event_key=?', (event_key,)).fetchone())
        payload = json.dumps(asdict(attempt), default=lambda value: value.isoformat(), sort_keys=True)
        conn.execute('INSERT INTO alert_delivery_history(event_key,payload_json) VALUES(?,?)', (event_key, payload))
        return attempt

    def _queue(self, conn, episode_id, revision, kind, due):
        key = self._event_key('observer', episode_id, revision, kind, due if kind == 'REMINDER' else None)
        inserted = conn.execute('INSERT OR IGNORE INTO alert_outbox(event_key,episode_id,revision,kind,delivery_owner,state,due_at) VALUES(?,?,?,?,?,?,?)',
            (key, episode_id, revision, kind, 'observer', 'QUEUED', due)).rowcount
        if inserted:
            self._history(conn, key)
        return self._delivery(conn.execute('SELECT * FROM alert_outbox WHERE event_key=?', (key,)).fetchone())

    def _link_producer(self, conn, episode_id, revision, kind, source_owner, resource_id,
                       producer_event_id, producer_attempt_id, state, at):
        if conn.execute('SELECT 1 FROM alert_revisions WHERE episode_id=? AND revision=?',
                        (episode_id, revision)).fetchone() is None:
            raise ValueError('known episode revision required')
        if self._incident(conn, episode_id).subject.resource_id != resource_id:
            raise ValueError('producer resource mismatch')
        key = self._event_key('producer', source_owner, resource_id, producer_event_id)
        inserted = conn.execute('INSERT OR IGNORE INTO alert_outbox(event_key,episode_id,revision,kind,delivery_owner,state,due_at,finalized_at,producer_event_id) VALUES(?,?,?,?,?,?,?,?,?)',
            (key, episode_id, revision, kind, 'producer', 'UNKNOWN', at, at, producer_event_id)).rowcount
        if inserted:
            self._history(conn, key)
        conn.execute('INSERT OR IGNORE INTO alert_producer_links VALUES(?,?,?,?,?,?)',
                     (source_owner, resource_id, producer_event_id, key, episode_id, revision))
        if producer_attempt_id is not None:
            existing = conn.execute('SELECT event_key,state,at FROM alert_producer_attempts WHERE source_owner=? AND resource_id=? AND producer_attempt_id=?',
                (source_owner, resource_id, producer_attempt_id)).fetchone()
            if existing is not None:
                if tuple(existing) != (key, state.value, at):
                    raise ValueError('immutable producer attempt mismatch')
            else:
                conn.execute('INSERT INTO alert_producer_attempts VALUES(?,?,?,?,?,?)',
                    (source_owner, resource_id, producer_attempt_id, key, state.value, at))
                current = conn.execute('SELECT * FROM alert_outbox WHERE event_key=?', (key,)).fetchone()
                # Backdated saved attempts retain their evidence without rewriting later delivery truth.
                if current['producer_attempt_id'] is None or at >= current['finalized_at']:
                    conn.execute('UPDATE alert_outbox SET state=?,finalized_at=?,producer_attempt_id=? WHERE event_key=?',
                        (state.value, at, producer_attempt_id, key))
                    self._history(conn, key)
                else:
                    evidence = asdict(self._delivery(current))
                    evidence.update(state=state.value, finalized_at=_instant(at), producer_attempt_id=producer_attempt_id)
                    conn.execute('INSERT INTO alert_delivery_history(event_key,payload_json) VALUES(?,?)',
                        (key, json.dumps(evidence, default=lambda value: value.isoformat(), sort_keys=True)))
        return self._delivery(conn.execute('SELECT * FROM alert_outbox WHERE event_key=?', (key,)).fetchone())

    def link_producer_delivery(self, episode_id: str, revision: int, kind: str, *,
            source_owner: str, resource_id: str, producer_event_id: str,
            producer_attempt_id: str | None = None, state: DeliveryState = DeliveryState.UNKNOWN,
            at: datetime):
        for value in (source_owner, resource_id, producer_event_id):
            bounded_identity(value, limit=256)
        if producer_attempt_id is not None:
            bounded_identity(producer_attempt_id, limit=256)
        state = DeliveryState(state)
        if state not in {DeliveryState.DELIVERED, DeliveryState.FAILED, DeliveryState.UNKNOWN, DeliveryState.DISABLED}:
            raise ValueError('terminal producer state required')
        if kind not in {'OCCURRENCE', 'WORSENING', 'RECOVERY'}:
            raise ValueError('invalid producer event kind')
        with self.connection() as conn:
            return self._link_producer(conn, episode_id, revision, kind, source_owner, resource_id,
                                       producer_event_id, producer_attempt_id, state, timestamp(at))

    def get_delivery(self, event_key: str) -> DeliveryAttempt | None:
        with self.connection() as conn:
            return self._delivery(conn.execute('SELECT * FROM alert_outbox WHERE event_key=?', (event_key,)).fetchone())

    def pending_deliveries(self, *, limit: int = 100) -> tuple[DeliveryAttempt, ...]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('bounded delivery limit required')
        with self.connection() as conn:
            return tuple(self._delivery(r) for r in conn.execute("SELECT * FROM alert_outbox WHERE state='QUEUED' AND delivery_owner='observer' AND due_at<=? ORDER BY due_at,rowid LIMIT ?",
                (timestamp(self.clock()), limit)))

    def list_attempts(self, episode_id: str) -> tuple[DeliveryAttempt, ...]:
        with self.connection() as conn:
            return tuple(self._delivery(r) for r in conn.execute('''SELECT * FROM alert_outbox WHERE episode_id=? OR event_key IN
                (SELECT event_key FROM alert_producer_links WHERE episode_id=?) ORDER BY rowid LIMIT 1000''',
                (episode_id, episode_id)))

    def list_delivery_history(self, event_key: str) -> tuple[DeliveryAttempt, ...]:
        with self.connection() as conn:
            rows = conn.execute('SELECT payload_json FROM alert_delivery_history WHERE event_key=? ORDER BY history_id LIMIT 1000', (event_key,)).fetchall()
        result = []
        for row in rows:
            fields = json.loads(row[0])
            fields['state'] = DeliveryState(fields['state'])
            for field in ('due_at', 'claimed_at', 'finalized_at'):
                fields[field] = None if fields[field] is None else datetime.fromisoformat(fields[field])
            result.append(DeliveryAttempt(**fields))
        return tuple(result)

    def due_reminders(self, now: datetime) -> tuple[DeliveryAttempt, ...]:
        stamp = timestamp(now)
        with self.connection() as conn:
            rows = conn.execute('''SELECT * FROM alert_episodes e WHERE active=1 AND severity='CRITICAL'
                AND next_reminder_at<=? AND NOT EXISTS(SELECT 1 FROM alert_acknowledgements a
                WHERE a.episode_id=e.episode_id AND a.revision=e.revision)
                ORDER BY next_reminder_at,episode_id LIMIT 100''', (stamp,)).fetchall()
            return tuple(self._queue(conn, r['episode_id'], r['revision'], 'REMINDER', r['next_reminder_at']) for r in rows)

    def claim_delivery(self, event_key: str, owner: str) -> DeliveryAttempt | None:
        bounded_identity(owner)
        now = timestamp(self.clock())
        with self.connection() as conn:
            row = conn.execute('SELECT * FROM alert_outbox WHERE event_key=?', (event_key,)).fetchone()
            if row is None or row['state'] != 'QUEUED' or row['delivery_owner'] != 'observer' or row['due_at'] > now:
                return None
            if row['kind'] == 'REMINDER':
                incident = self._incident(conn, row['episode_id'])
                if not incident.active or incident.acknowledged or incident.revision != row['revision'] or incident.severity != Severity.CRITICAL:
                    conn.execute("UPDATE alert_outbox SET state='SUPPRESSED',finalized_at=? WHERE event_key=?", (now, event_key))
                    self._history(conn, event_key)
                    return None
                conn.execute('UPDATE alert_episodes SET next_reminder_at=? WHERE episode_id=?',
                             (now + 1800, row['episode_id']))
            conn.execute("UPDATE alert_outbox SET state='CLAIMED',claim_id=?,owner=?,claimed_at=? WHERE event_key=? AND state='QUEUED'",
                         (uuid.uuid4().hex, owner, now, event_key))
            result = self._history(conn, event_key)
        # connection's transaction has committed before any caller may perform I/O.
        return result

    def finalize_attempt(self, event_key: str, owner: str, claim_id: str,
                         state: DeliveryState, *, failure_code: str | None = None) -> DeliveryAttempt:
        state = DeliveryState(state)
        if state not in {DeliveryState.DELIVERED, DeliveryState.FAILED, DeliveryState.UNKNOWN, DeliveryState.DISABLED}:
            raise ValueError('terminal attempt state required')
        if failure_code is not None and not re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', failure_code):
            raise ValueError('bounded failure code required')
        now = timestamp(self.clock())
        with self.connection() as conn:
            row = conn.execute('SELECT * FROM alert_outbox WHERE event_key=?', (event_key,)).fetchone()
            if row is None or row['delivery_owner'] != 'observer' or row['owner'] != owner or row['claim_id'] != claim_id:
                raise ValueError('delivery claim ownership mismatch')
            if row['state'] != 'CLAIMED':
                if row['state'] == state.value and row['failure_code'] == failure_code:
                    return self._delivery(row)
                raise ValueError('delivery claim already terminal')
            conn.execute('UPDATE alert_outbox SET state=?,finalized_at=?,failure_code=? WHERE event_key=?',
                         (state.value, now, failure_code, event_key))
            return self._history(conn, event_key)

    def expire_claims(self, now: datetime, *, stale_after_seconds: float = 60,
                      owner: str | None = None) -> int:
        if not 0 <= stale_after_seconds <= 86400:
            raise ValueError('bounded claim expiry required')
        stamp = timestamp(now)
        sql = "SELECT event_key FROM alert_outbox WHERE state='CLAIMED' AND claimed_at<=?"
        args = [stamp - stale_after_seconds]
        if owner is not None:
            sql += ' AND owner=?'
            args.append(bounded_identity(owner))
        with self.connection() as conn:
            rows = conn.execute(sql + ' ORDER BY claimed_at LIMIT 100', args).fetchall()
            for row in rows:
                conn.execute("UPDATE alert_outbox SET state='UNKNOWN',finalized_at=?,failure_code='CLAIM_EXPIRED' WHERE event_key=?",
                             (stamp, row[0]))
                self._history(conn, row[0])
            return len(rows)

    def get_checkpoint(self, stream: str = 'sources') -> str | None:
        with self.connection() as conn:
            row = conn.execute('SELECT cursor FROM alert_checkpoints WHERE stream=?', (bounded_identity(stream),)).fetchone()
            return None if row is None else row[0]

    def set_checkpoint(self, cursor: str, stream: str = 'sources') -> None:
        if not isinstance(cursor, str) or len(cursor) > 65536:
            raise ValueError('bounded source checkpoint required')
        with self.connection() as conn:
            conn.execute('INSERT INTO alert_checkpoints VALUES(?,?) ON CONFLICT(stream) DO UPDATE SET cursor=excluded.cursor',
                         (bounded_identity(stream), cursor))
