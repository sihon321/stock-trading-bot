"""Independent operator storage. This module has no production migration imports."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .web_config import WebSettings, checked_path

WEB_SCHEMA_VERSION = 2
_ID = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}\Z')
_CODE = re.compile(r'[A-Z][A-Z0-9_]{0,63}\Z')


def timestamp(value: datetime) -> float:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('aware server timestamp required')
    return value.timestamp()


def instant(value) -> datetime | None:
    return None if value is None else datetime.fromtimestamp(value, timezone.utc)


def identifier(value: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError('invalid bounded identity')
    return value


@dataclass(frozen=True)
class Operator:
    username: str
    password_hash: str = field(repr=False)


@dataclass(frozen=True)
class Session:
    reference_hash: str = field(repr=False)
    actor: str
    issued_at: datetime
    expires_at: datetime
    revoked_at: datetime | None


@dataclass(frozen=True)
class ReportArtifact:
    artifact_id: str
    resource_id: str
    actor: str
    filename: str
    format: str
    created_at: datetime


_V1 = (
    'CREATE TABLE phase14_web_metadata (singleton INTEGER PRIMARY KEY CHECK(singleton=1), version INTEGER NOT NULL)',
    'INSERT INTO phase14_web_metadata VALUES(1,1)',
    'CREATE TABLE web_operator (singleton INTEGER PRIMARY KEY CHECK(singleton=1), username TEXT NOT NULL, password_hash TEXT NOT NULL, updated_at REAL NOT NULL)',
    'CREATE TABLE web_sessions (reference_hash TEXT PRIMARY KEY, actor TEXT NOT NULL, issued_at REAL NOT NULL, expires_at REAL NOT NULL CHECK(expires_at=issued_at+43200), revoked_at REAL)',
    "CREATE TRIGGER web_session_immutable BEFORE UPDATE OF reference_hash,actor,issued_at,expires_at ON web_sessions BEGIN SELECT RAISE(ABORT,'immutable session'); END",
    'CREATE TABLE web_actions (action_id INTEGER PRIMARY KEY, actor TEXT NOT NULL, action TEXT NOT NULL, result_code TEXT NOT NULL, resource_id TEXT, observed_at REAL NOT NULL, details_json TEXT NOT NULL)',
    "CREATE TRIGGER web_actions_no_update BEFORE UPDATE ON web_actions BEGIN SELECT RAISE(ABORT,'append-only audit'); END",
    "CREATE TRIGGER web_actions_no_delete BEFORE DELETE ON web_actions BEGIN SELECT RAISE(ABORT,'append-only audit'); END",
    'CREATE TABLE web_login_throttle (bucket_hash TEXT PRIMARY KEY, window_start REAL NOT NULL, failures INTEGER NOT NULL CHECK(failures BETWEEN 0 AND 5))',
)
_ARTIFACTS = 'CREATE TABLE web_report_artifacts (artifact_id TEXT PRIMARY KEY, resource_id TEXT NOT NULL, actor TEXT NOT NULL, filename TEXT UNIQUE NOT NULL, format TEXT NOT NULL, created_at REAL NOT NULL)'


def _private_directory(path: Path) -> None:
    missing = []
    cursor = path
    while not cursor.exists():
        missing.append(cursor)
        cursor = cursor.parent
    for directory in reversed(missing):
        directory.mkdir(mode=0o700)
    if path.stat().st_mode & 0o022:
        raise ValueError('writable directory must not be group/world writable')


class WebStore:
    def __init__(self, settings: WebSettings):
        self.settings = settings

    def _verify_ownership(self, path: Path) -> int:
        if not path.exists() or path.stat().st_size == 0:
            return 0
        try:
            with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as conn:
                conn.execute('PRAGMA query_only=ON')
                tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if 'phase14_web_metadata' not in tables:
                    raise ValueError('operational storage ownership missing')
                version = conn.execute('SELECT version FROM phase14_web_metadata WHERE singleton=1').fetchone()
                if version is None or version[0] not in (1, WEB_SCHEMA_VERSION):
                    raise ValueError('unsupported operational schema version')
                return version[0]
        except sqlite3.DatabaseError:
            raise ValueError('invalid operational storage ownership') from None

    def initialize(self, *, fail_after_step: str | None = None) -> None:
        db, artifacts = self.settings.validate_topology()
        version = self._verify_ownership(db)
        _private_directory(db.parent)
        # Atomic no-follow creation prevents replacing another inode through a link.
        if not db.exists():
            descriptor = os.open(db, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            os.close(descriptor)
        if db.stat().st_mode & 0o077:
            raise ValueError('operational DB must be owner protected')
        with self.connection(check_owner=False) as conn:
            if version == 0:
                for statement in _V1:
                    conn.execute(statement)
            if version < 2:
                conn.execute(_ARTIFACTS)
                if fail_after_step == 'artifacts':
                    raise RuntimeError('injected migration failure')
                conn.execute('UPDATE phase14_web_metadata SET version=2 WHERE singleton=1')
        _private_directory(artifacts)
        if artifacts.stat().st_mode & 0o077:
            # Existing artifacts are explicit operator authority; require safe permissions.
            raise ValueError('artifact root must be owner protected')

    @contextmanager
    def connection(self, *, check_owner: bool = True):
        db, _ = self.settings.validate_topology()
        if check_owner:
            self._verify_ownership(db)
            if not db.exists():
                raise ValueError('operational storage not initialized')
        if db.stat().st_mode & 0o077:
            raise ValueError('operational DB must be owner protected')
        # mode=rw never creates a missing DB during a service request.
        conn = sqlite3.connect(db.as_uri() + '?mode=rw', uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('PRAGMA foreign_keys=ON')
            conn.execute('PRAGMA secure_delete=ON')
            conn.execute('BEGIN IMMEDIATE')
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_operator(self) -> Operator | None:
        with self.connection() as conn:
            row = conn.execute('SELECT username,password_hash FROM web_operator WHERE singleton=1').fetchone()
            return None if row is None else Operator(*row)

    def provision_operator(self, username: str, password_hash: str, at: datetime, *, reset: bool = False):
        identifier(username)
        if not isinstance(password_hash, str) or not 1 <= len(password_hash) <= 1024:
            raise ValueError('invalid password hash')
        with self.connection() as conn:
            exists = conn.execute('SELECT username FROM web_operator WHERE singleton=1').fetchone()
            if (exists is not None and not reset) or (exists is None and reset):
                raise ValueError('operator provisioning state mismatch')
            if reset and exists[0] != username:
                raise ValueError('operator identity mismatch')
            conn.execute('INSERT INTO web_operator VALUES(1,?,?,?) ON CONFLICT(singleton) DO UPDATE SET password_hash=excluded.password_hash,updated_at=excluded.updated_at',
                         (username, password_hash, timestamp(at)))
            if reset:
                conn.execute('UPDATE web_sessions SET revoked_at=? WHERE revoked_at IS NULL', (timestamp(at),))
                conn.execute('DELETE FROM web_login_throttle')
            self._append_action(conn, username, 'PASSWORD_RESET' if reset else 'OPERATOR_SETUP', 'SUCCESS', None, at, {})

    def create_session(self, reference_hash: str, issued_at: datetime, expires_at: datetime):
        if not re.fullmatch(r'[a-f0-9]{64}', reference_hash) or expires_at != issued_at + timedelta(hours=12):
            raise ValueError('invalid absolute session contract')
        with self.connection() as conn:
            operator = conn.execute('SELECT username FROM web_operator WHERE singleton=1').fetchone()
            if operator is None:
                raise ValueError('operator not provisioned')
            conn.execute('INSERT INTO web_sessions VALUES(?,?,?,?,NULL)',
                         (reference_hash, operator[0], timestamp(issued_at), timestamp(expires_at)))

    def get_session(self, reference_hash: str) -> Session | None:
        with self.connection() as conn:
            row = conn.execute('SELECT * FROM web_sessions WHERE reference_hash=?', (reference_hash,)).fetchone()
            if row is None:
                return None
            return Session(row['reference_hash'], row['actor'], instant(row['issued_at']),
                           instant(row['expires_at']), instant(row['revoked_at']))

    def revoke_session(self, reference_hash: str, at: datetime):
        with self.connection() as conn:
            conn.execute('UPDATE web_sessions SET revoked_at=? WHERE reference_hash=? AND revoked_at IS NULL',
                         (timestamp(at), reference_hash))

    def revoke_all_sessions(self, at: datetime):
        with self.connection() as conn:
            conn.execute('UPDATE web_sessions SET revoked_at=? WHERE revoked_at IS NULL', (timestamp(at),))

    def _append_action(self, conn, actor, action, result_code, resource_id, at, details):
        identifier(actor)
        if not _CODE.fullmatch(action) or not _CODE.fullmatch(result_code):
            raise ValueError('invalid action/result code')
        if resource_id is not None:
            self.settings.resource(resource_id)
        if len(details) > 8 or any(k not in {'row_count', 'byte_count', 'attempt_count'}
                                 or type(v) is not int or not 0 <= v <= 10000000
                                 for k, v in details.items()):
            raise ValueError('unsafe action details')
        conn.execute('INSERT INTO web_actions(actor,action,result_code,resource_id,observed_at,details_json) VALUES(?,?,?,?,?,?)',
                     (actor, action, result_code, resource_id, timestamp(at), json.dumps(details, sort_keys=True)))

    def append_action(self, *, actor, action, result_code, at, resource_id=None, details=None):
        with self.connection() as conn:
            self._append_action(conn, actor, action, result_code, resource_id, at, details or {})

    def record_artifact(self, artifact_id, *, resource_id, actor, filename, format, at):
        identifier(artifact_id)
        identifier(actor)
        self.settings.resource(resource_id)
        if format not in {'txt', 'json', 'csv'} or filename != f'{artifact_id}.{format}':
            raise ValueError('invalid owned artifact name')
        checked_path(self.settings.artifact_root / filename)
        with self.connection() as conn:
            conn.execute('INSERT INTO web_report_artifacts VALUES(?,?,?,?,?,?)',
                         (artifact_id, resource_id, actor, filename, format, timestamp(at)))

    def get_artifact(self, artifact_id, *, actor) -> ReportArtifact | None:
        with self.connection() as conn:
            row = conn.execute('SELECT * FROM web_report_artifacts WHERE artifact_id=? AND actor=?', (artifact_id, actor)).fetchone()
            return None if row is None else ReportArtifact(*tuple(row)[:-1], instant(row['created_at']))

    @staticmethod
    def throttle_keys(username: str, source_address: str) -> tuple[str, str]:
        # Hash unknown account/address inputs; never persist caller-controlled plaintext.
        return tuple(hashlib.sha256(value.encode()).hexdigest() for value in
                     ('account:' + username, 'source:' + source_address))

    def login_attempt(self, username: str, source_address: str, at: datetime, verify,
                      *, session_reference_hash: str | None = None) -> str:
        """Serialize lock check+verification+failure update across processes."""
        now = timestamp(at)
        keys = self.throttle_keys(username, source_address)
        with self.connection() as conn:
            conn.execute('DELETE FROM web_login_throttle WHERE window_start<=?', (now - 300,))
            rows = [conn.execute('SELECT failures FROM web_login_throttle WHERE bucket_hash=?', (key,)).fetchone() for key in keys]
            if any(row is not None and row[0] >= 5 for row in rows):
                return 'AUTH_FAILED'
            count = conn.execute('SELECT COUNT(*) FROM web_login_throttle').fetchone()[0]
            if count + sum(row is None for row in rows) > 2048:
                return 'AUTH_FAILED'
            operator = conn.execute('SELECT username,password_hash FROM web_operator WHERE singleton=1').fetchone()
            correct = verify(None if operator is None else Operator(*operator))
            if correct:
                if session_reference_hash is not None:
                    if not re.fullmatch(r'[a-f0-9]{64}', session_reference_hash):
                        raise ValueError('invalid session reference')
                    conn.execute('INSERT INTO web_sessions VALUES(?,?,?,?,NULL)',
                                 (session_reference_hash, operator[0], now, now + 43200))
                    self._append_action(conn, operator[0], 'LOGIN', 'SUCCESS', None, at, {})
                return 'SUCCESS'
            # Bound adversarial cardinality; new identities fail closed at capacity.
            if count + sum(row is None for row in rows) <= 2048:
                for key in keys:
                    conn.execute('INSERT INTO web_login_throttle VALUES(?,?,1) ON CONFLICT(bucket_hash) DO UPDATE SET failures=MIN(5,failures+1)', (key, now))
            else:
                return 'AUTH_FAILED'
            self._append_action(conn, 'anonymous', 'LOGIN', 'AUTH_FAILED', None, at, {})
            return 'AUTH_FAILED'
