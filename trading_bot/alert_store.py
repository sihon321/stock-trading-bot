"""Independent operational incident metadata; never connects to trading sources."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3
import uuid

from .alert_models import (Acknowledgement, AlertAction, AlertSourceFact, AlertSubject,
                           IncidentEpisode, Severity, SeverityRevision, bounded_identity, timestamp)

ALERT_SCHEMA_VERSION = 1


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
                if row is None or row[0] != ALERT_SCHEMA_VERSION:
                    raise ValueError('unsupported alert operational schema')
                return row[0]
        except sqlite3.DatabaseError:
            raise ValueError('invalid operational storage ownership') from None

    def initialize(self):
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

    @contextmanager
    def connection(self, *, check_owner=True):
        if check_owner and self._verify_ownership() == 0:
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
            episode_id = None if current is None else current['episode_id']
            if current is None and not fact.positive_recovery:
                # Historical inserts after a closed episode cannot manufacture a recurrence.
                historical = conn.execute('SELECT * FROM alert_episodes WHERE subject_id=? AND recovered_at>=? ORDER BY recovered_at DESC LIMIT 1',
                    (fact.subject.identity, stamp)).fetchone()
                if historical is not None:
                    episode_id = historical['episode_id']
                    current = historical
                else:
                    episode_id = uuid.uuid4().hex
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
                    else:
                        state = fact.normalized_state
                        if fact.severity.rank > severity.rank:
                            revision += 1
                            severity = fact.severity
                            due = timestamp(self.clock()) + 1800 if severity == Severity.CRITICAL else None
                            conn.execute('INSERT INTO alert_revisions VALUES(?,?,?,?,?,?)',
                                (episode_id, revision, severity.value, stamp, fact.source_owner, fact.source_id))
                conn.execute('UPDATE alert_episodes SET revision=?,severity=?,normalized_state=?,active=?,first_at=?,last_at=?,occurrence_count=occurrence_count+1,recovered_at=?,recovery_proof_id=?,next_reminder_at=? WHERE episode_id=?',
                    (revision, severity.value, state, active, first, last, recovered_at, proof, due, episode_id))
            conn.execute('INSERT INTO alert_observations VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (fact.source_owner, fact.subject.resource_id, fact.source_id, fact.sequence, stamp,
                 fact.subject.identity, fact.normalized_state, fact.severity.value,
                 int(fact.positive_recovery), fact.recovery_proof_id, episode_id))
            conn.execute('INSERT INTO alert_cursors VALUES(?,?,?) ON CONFLICT(source_owner,resource_id) DO UPDATE SET sequence=max(sequence,excluded.sequence)',
                (fact.source_owner, fact.subject.resource_id, fact.sequence))
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
