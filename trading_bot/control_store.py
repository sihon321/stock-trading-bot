"""Owner-local global stop journal; request/read facades never acquire trading authority."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
import re
import sqlite3
import stat
import time
import uuid
import weakref

from .service_config import ServiceSettings
from .service_models import AppliedControl, ControlMode, ControlRequest, InstallationScope, ServiceScope
from .web_config import checked_path

CONTROL_OWNER = 'phase15-control'
CONTROL_SCHEMA_VERSION = 1
_TABLES = {
    'control_metadata': 'owner TEXT PRIMARY KEY, version INTEGER NOT NULL',
    'control_requests': "request_id TEXT PRIMARY KEY, actor TEXT NOT NULL, requested_at TEXT NOT NULL, scope_hash TEXT NOT NULL, target TEXT NOT NULL CHECK(target='mock'), action TEXT NOT NULL CHECK(action IN ('PAUSE','RESUME','KILL')), expected_revision INTEGER NOT NULL CHECK(expected_revision>=0), acceptance_revision INTEGER UNIQUE NOT NULL CHECK(acceptance_revision=expected_revision+1), payload_hash TEXT NOT NULL",
    'control_applications': "application_id TEXT PRIMARY KEY, request_id TEXT UNIQUE REFERENCES control_requests(request_id), revision INTEGER NOT NULL CHECK(revision>=0), mode TEXT NOT NULL CHECK(mode IN ('PAUSED','RUNNING','KILLED')), applied_at TEXT NOT NULL, safety_evidence_ids_json TEXT NOT NULL, result TEXT NOT NULL CHECK(result IN ('APPLIED','REJECTED','CONFLICT')), reason_code TEXT NOT NULL",
    'control_request_audit': 'event_id INTEGER PRIMARY KEY, request_id TEXT REFERENCES control_requests(request_id), actor TEXT NOT NULL, scope_hash TEXT NOT NULL, target TEXT NOT NULL, event TEXT NOT NULL, observed_at TEXT NOT NULL',
    'submission_admissions': "admission_id TEXT PRIMARY KEY, scope_hash TEXT NOT NULL, target TEXT NOT NULL CHECK(target='mock'), intent_id TEXT NOT NULL, submission_id TEXT NOT NULL, control_revision INTEGER NOT NULL CHECK(control_revision>=0), state TEXT NOT NULL CHECK(state IN ('IN_FLIGHT','FINISHED','UNKNOWN')), admitted_at TEXT NOT NULL, finished_at TEXT, UNIQUE(scope_hash,target,intent_id)",
}
_APPEND_ONLY = ('control_requests', 'control_applications', 'control_request_audit')


def _identity(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.:/ -]{0,127}', value):
        raise ValueError('bounded stable identity required')
    return value


def _stamp(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('aware observation required')
    return value.astimezone(timezone.utc).isoformat()


def _directory(path):
    path = checked_path(path)
    missing, cursor = [], path
    while not cursor.exists():
        missing.append(cursor); cursor = cursor.parent
    if cursor.stat().st_uid != os.getuid() or cursor.stat().st_mode & 0o022:
        raise ValueError('owner controlled parent required')
    for item in reversed(missing): item.mkdir(mode=0o700)
    info = path.stat()
    if not path.is_dir() or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError('0700 owner directory required')


def _descriptor(path, *, create=False):
    path = checked_path(path)
    fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | (os.O_CREAT if create else 0), 0o600)
    try:
        _same_file(fd, path)
        os.set_inheritable(fd, False)
        return fd
    except BaseException:
        os.close(fd); raise


def _same_file(fd, path):
    checked_path(path)
    info, current = os.fstat(fd), path.stat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or info.st_mode & 0o077 or info.st_nlink != 1
            or (info.st_dev, info.st_ino) != (current.st_dev, current.st_ino)):
        raise ValueError('0600 unlinked owner regular file required')


def _owned(conn, *, allow_empty=False):
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not tables and allow_empty: return False
    if tables != set(_TABLES): raise ValueError('control schema ownership missing or foreign')
    rows = conn.execute('SELECT owner,version FROM control_metadata').fetchall()
    if len(rows) != 1 or tuple(rows[0]) != (CONTROL_OWNER, CONTROL_SCHEMA_VERSION):
        raise ValueError('unsupported control owner/version')
    for name in _TABLES:
        expected = {
            'control_metadata': ('owner','version'),
            'control_requests': ('request_id','actor','requested_at','scope_hash','target','action','expected_revision','acceptance_revision','payload_hash'),
            'control_applications': ('application_id','request_id','revision','mode','applied_at','safety_evidence_ids_json','result','reason_code'),
            'control_request_audit': ('event_id','request_id','actor','scope_hash','target','event','observed_at'),
            'submission_admissions': ('admission_id','scope_hash','target','intent_id','submission_id','control_revision','state','admitted_at','finished_at'),
        }[name]
        if tuple(r[1] for r in conn.execute(f'PRAGMA table_info({name})')) != expected:
            raise ValueError('control schema contract mismatch')
    triggers = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
    expected_triggers = {f'{name}_no_{verb}' for name in _APPEND_ONLY for verb in ('update','delete')}
    if not (expected_triggers | {'admission_identity','admission_transition','admission_no_delete'}).issubset(triggers):
        raise ValueError('control evidence immutability missing')
    return True


def migrate_control(conn, *, fail_after_step=None):
    """Owned version-one migration; no foreign schema or primary audit version writes."""
    if conn.in_transaction: raise ValueError('independent migration transaction required')
    conn.execute('BEGIN IMMEDIATE')
    try:
        if not _owned(conn, allow_empty=True):
            for name, columns in _TABLES.items():
                conn.execute(f'CREATE TABLE {name} ({columns})')
                if fail_after_step == name: raise RuntimeError('injected control migration failure')
            conn.execute('INSERT INTO control_metadata VALUES(?,?)', (CONTROL_OWNER, CONTROL_SCHEMA_VERSION))
            for name in _APPEND_ONLY:
                for verb in ('UPDATE', 'DELETE'):
                    conn.execute(f"CREATE TRIGGER {name}_no_{verb.lower()} BEFORE {verb} ON {name} BEGIN SELECT RAISE(ABORT,'append-only control evidence'); END")
            conn.execute("CREATE TRIGGER admission_identity BEFORE UPDATE OF admission_id,scope_hash,target,intent_id,submission_id,control_revision,admitted_at ON submission_admissions BEGIN SELECT RAISE(ABORT,'immutable admission'); END")
            conn.execute("CREATE TRIGGER admission_transition BEFORE UPDATE OF state,finished_at ON submission_admissions WHEN OLD.state!='IN_FLIGHT' OR NEW.state NOT IN ('FINISHED','UNKNOWN') OR NEW.finished_at IS NULL BEGIN SELECT RAISE(ABORT,'terminal admission'); END")
            conn.execute("CREATE TRIGGER admission_no_delete BEFORE DELETE ON submission_admissions BEGIN SELECT RAISE(ABORT,'durable admission'); END")
        conn.commit()
    except BaseException:
        conn.rollback(); raise


class ControlLockUnavailable(RuntimeError):
    pass


class AdmissionLock:
    """The installation-global serialization point, held across one later bounded POST."""
    def __init__(self, store):
        self._store, self._fd, self._pid = store, None, os.getpid()
        ref = weakref.ref(self)
        def after_child():
            owner = ref()
            if owner is not None and owner._fd is not None:
                os.close(owner._fd); owner._fd = None
        os.register_at_fork(after_in_child=after_child)

    def __enter__(self):
        if self._fd is not None or os.getpid() != self._pid: raise ValueError('lock lifecycle invalid')
        self._store._validate_paths()
        fd = _descriptor(self._store.lock_path)
        self.deadline = time.monotonic() + 1
        try:
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB); break
                except BlockingIOError:
                    if time.monotonic() >= self.deadline: raise ControlLockUnavailable('global admission lock unavailable') from None
                    time.sleep(min(.01, max(0, self.deadline-time.monotonic())))
            _same_file(fd, self._store.lock_path)
            self._fd = fd
            return self
        except BaseException:
            os.close(fd); raise

    def assert_owned(self, store=None):
        if self._fd is None or os.getpid() != self._pid or (store is not None and store is not self._store):
            raise ValueError('current global admission lock required')
        _same_file(self._fd, self._store.lock_path)

    def __exit__(self, *args):
        if self._fd is not None:
            if os.getpid() == self._pid: fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd); self._fd = None


@dataclass(frozen=True)
class RequestAcceptance:
    status: str
    request_id: str
    acceptance_revision: int | None
    reason_code: str
    idempotent: bool = False


@dataclass(frozen=True)
class EffectiveControl:
    applied: AppliedControl
    mode: ControlMode
    acceptance_revision: int
    pending_request_ids: tuple[str, ...]

    @property
    def allows_buy(self): return self.mode == ControlMode.RUNNING
    @property
    def allows_daily(self): return self.mode == ControlMode.RUNNING
    @property
    def allows_risk_sell(self): return self.mode != ControlMode.KILLED
    @property
    def allows_reconciliation(self): return True


class ControlStore:
    """Trusted composition root. Never hand this owner object to web/CLI routes."""
    def __init__(self, settings: ServiceSettings, *, clock=None):
        if not isinstance(settings, ServiceSettings): raise TypeError('protected registration required')
        self.settings = settings
        self.scope = InstallationScope(registered_scopes=settings.registered_scopes)
        self.scope_hash = hashlib.sha256(self.scope.model_dump_json().encode()).hexdigest()
        self.path = settings.validate_topology()[1]
        self.lock_path = settings.validate_topology()[2] / 'admission.lock'
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _validate_paths(self):
        self.settings.validate_topology()
        for root in (self.path.parent, self.lock_path.parent):
            info = root.stat()
            if not root.is_dir() or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError('owner protected control roots required')

    def initialize(self, *, actor, fail_after_step=None):
        actor = _identity(actor)
        self.settings.validate_topology()
        _directory(self.path.parent); _directory(self.lock_path.parent)
        for path in (self.path, self.lock_path):
            fd = _descriptor(path, create=True); os.close(fd)
        with self.admission_lock() as lock:
            fd = _descriptor(self.path)
            try:
                conn = sqlite3.connect(self.path.as_uri()+'?mode=rw', uri=True, timeout=1)
                try:
                    conn.execute('PRAGMA foreign_keys=ON')
                    migrate_control(conn, fail_after_step=fail_after_step)
                finally: conn.close()
            finally: os.close(fd)
            with self._connection(write=True, check_setup=False, lock=lock) as conn:
                setup = conn.execute("SELECT 1 FROM control_request_audit WHERE event='OWNER_SETUP'").fetchone()
                if setup is None:
                    if conn.execute('SELECT 1 FROM control_requests').fetchone() or conn.execute('SELECT 1 FROM control_applications').fetchone():
                        raise ValueError('cannot reset existing control evidence')
                    at = _stamp(self.clock())
                    conn.execute('INSERT INTO control_request_audit VALUES(NULL,NULL,?,?,?,?,?)',
                        (actor,self.scope_hash,'mock','OWNER_SETUP',at))
                    info = self.lock_path.stat()
                    conn.execute('INSERT INTO control_request_audit VALUES(NULL,NULL,?,?,?,?,?)',
                        (f'{info.st_dev}:{info.st_ino}',self.scope_hash,'mock','LOCK_IDENTITY',at))
                    conn.execute('INSERT INTO control_applications VALUES(?,NULL,0,?,?,?, ?,?)',
                        (str(uuid.uuid4()),'PAUSED',at,'[]','APPLIED','OWNER_SETUP'))
                self._verify_setup(conn)

    def _verify_setup(self, conn):
        rows = conn.execute("SELECT * FROM control_request_audit WHERE event='OWNER_SETUP'").fetchall()
        if len(rows) != 1 or rows[0]['scope_hash'] != self.scope_hash or rows[0]['target'] != 'mock':
            raise ValueError('protected installation registration mismatch')
        identities = conn.execute("SELECT actor FROM control_request_audit WHERE event='LOCK_IDENTITY'").fetchall()
        info = self.lock_path.stat()
        if len(identities) != 1 or identities[0][0] != f'{info.st_dev}:{info.st_ino}':
            raise ValueError('registered global lock identity changed')
        row = conn.execute('SELECT * FROM control_applications WHERE revision=0').fetchall()
        if len(row) != 1 or row[0]['request_id'] is not None or row[0]['mode'] != 'PAUSED' or row[0]['result'] != 'APPLIED':
            raise ValueError('explicit conservative owner setup missing')
        minimum, highest, count = conn.execute('SELECT MIN(acceptance_revision),MAX(acceptance_revision),COUNT(*) FROM control_requests').fetchone()
        if count > 100000 or (count and (minimum != 1 or highest != count)):
            raise ValueError('control revision chain unavailable')
        if conn.execute("SELECT 1 FROM control_requests r WHERE r.scope_hash!=? OR r.target!='mock' OR NOT EXISTS (SELECT 1 FROM control_request_audit a WHERE a.request_id=r.request_id AND a.event='REQUESTED' AND a.actor=r.actor AND a.scope_hash=r.scope_hash AND a.target=r.target) LIMIT 1", (self.scope_hash,)).fetchone():
            raise ValueError('control request acceptance evidence missing')

    @contextmanager
    def _connection(self, *, write=False, check_setup=True, lock=None, timeout=1):
        self._validate_paths()
        if write:
            if not isinstance(lock, AdmissionLock): raise ValueError('global lock required for control mutation')
            lock.assert_owned(self)
        lock_fd = _descriptor(self.lock_path)
        fd, conn = None, None
        try:
            fd = _descriptor(self.path)
            conn = sqlite3.connect(self.path.as_uri()+('?mode=rw' if write else '?mode=ro'), uri=True, timeout=max(0,min(1,timeout)))
            _same_file(fd, self.path)
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA foreign_keys=ON')
            if not write: conn.execute('PRAGMA query_only=ON')
            conn.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            _owned(conn)
            if check_setup: self._verify_setup(conn)
            yield conn
            _same_file(fd, self.path); _same_file(lock_fd, self.lock_path)
            if write: lock.assert_owned(self)
            conn.commit()
        except BaseException:
            if conn is not None: conn.rollback()
            raise
        finally:
            if conn is not None: conn.close()
            if fd is not None: os.close(fd)
            os.close(lock_fd)

    def admission_lock(self): return AdmissionLock(self)
    def reader(self): return ControlReader(self)
    def request_writer(self, *, actor): return ControlRequestWriter(self, actor=actor)

    def _request_from_row(self, row):
        result = ControlRequest(request_id=row['request_id'], actor=row['actor'], requested_at=row['requested_at'],
            scope=self.scope, action=row['action'], expected_revision=row['expected_revision'])
        if row['scope_hash'] != self.scope_hash or row['payload_hash'] != _payload_hash(result):
            raise ValueError('control request payload evidence corrupt')
        return result

    def _effective(self, conn):
        rows = conn.execute('SELECT * FROM control_requests ORDER BY acceptance_revision').fetchall()
        for row in rows: self._request_from_row(row)
        applied_rows = conn.execute("SELECT * FROM control_applications WHERE result='APPLIED' ORDER BY revision").fetchall()
        applied = None
        highest = rows[-1]['acceptance_revision'] if rows else 0
        for row in applied_rows:
            applied = AppliedControl(revision=row['revision'], mode=row['mode'], request_id=row['request_id'],
                applied_at=row['applied_at'], safety_evidence_ids=json.loads(row['safety_evidence_ids_json']))
            if applied.revision > highest: raise ValueError('applied control revision exceeds acceptance')
        if applied is None: raise ValueError('conservative applied state missing')
        pending = [r for r in rows if r['acceptance_revision'] > applied.revision]
        mode = applied.mode
        for row in pending:
            if row['action'] == 'KILL': mode = ControlMode.KILLED
            elif row['action'] == 'PAUSE' and mode != ControlMode.KILLED: mode = ControlMode.PAUSED
        processed = {r[0] for r in conn.execute('SELECT request_id FROM control_applications WHERE request_id IS NOT NULL')}
        return EffectiveControl(applied, mode, highest,
            tuple(r['request_id'] for r in pending if r['request_id'] not in processed))

    def service_capability(self, leader):
        # Import here: read/request paths do not load service/trading writer modules.
        from .service_leader import ServiceLeader
        if type(leader) is not ServiceLeader or leader.settings != self.settings:
            raise ValueError('actual registered service leader required')
        leader.assert_owner()
        return _ServiceControlCapability(self, leader)

    def _record_admission(self, lock, *, scope, intent_id, submission_id, control_revision, admitted_at):
        if scope not in self.scope.registered_scopes: raise ValueError('registered mock scope required')
        intent_id, submission_id = _identity(intent_id), _identity(submission_id)
        if type(control_revision) is not int or control_revision < 0: raise ValueError('strict control revision required')
        with self._connection(write=True, lock=lock) as conn:
            if self._effective(conn).acceptance_revision != control_revision: raise ValueError('stale admission revision')
            admission_id = str(uuid.uuid4())
            conn.execute('INSERT INTO submission_admissions VALUES(?,?,?,?,?,?,?, ?,NULL)',
                (admission_id,scope.account_scope_hash,scope.execution_target,intent_id,submission_id,control_revision,'IN_FLIGHT',_stamp(admitted_at)))
        return admission_id

    def _finish_admission(self, lock, admission_id, *, state, finished_at):
        if state not in ('FINISHED','UNKNOWN'): raise ValueError('terminal admission state required')
        with self._connection(write=True, lock=lock) as conn:
            row = conn.execute('SELECT * FROM submission_admissions WHERE admission_id=?', (_identity(admission_id),)).fetchone()
            if row is None or row['state'] != 'IN_FLIGHT' or _stamp(finished_at) < row['admitted_at']:
                raise ValueError('terminal or uncertain admission cannot replay')
            conn.execute('UPDATE submission_admissions SET state=?,finished_at=? WHERE admission_id=?', (state,_stamp(finished_at),admission_id))


def _payload_hash(request):
    values = request.model_dump(mode='json')
    values['requested_at'] = _stamp(request.requested_at)
    return hashlib.sha256(json.dumps(values,sort_keys=True,separators=(',',':')).encode()).hexdigest()


class ControlReader:
    __slots__ = ('__store',)
    def __init__(self, store): self.__store = store

    def effective_state(self, scope=None):
        if scope is not None and scope not in self.__store.scope.registered_scopes and scope != self.__store.scope:
            raise ValueError('registered control scope required')
        with self.__store._connection() as conn: return self.__store._effective(conn)

    def _list(self, table, limit):
        if type(limit) is not int or not 1 <= limit <= 100: raise ValueError('bounded read required')
        with self.__store._connection() as conn:
            return tuple(dict(r) for r in conn.execute(f'SELECT * FROM {table} ORDER BY rowid DESC LIMIT ?', (limit,)))

    def list_requests(self, *, limit=50): return self._list('control_requests',limit)
    def list_applications(self, *, limit=50): return self._list('control_applications',limit)
    def list_admissions(self, *, limit=50): return self._list('submission_admissions',limit)


class ControlRequestWriter:
    __slots__ = ('__store', '__actor')
    def __init__(self, store, *, actor): self.__store, self.__actor = store, _identity(actor)

    def append_request(self, request):
        request = ControlRequest.model_validate(request)
        if request.actor != self.__actor or request.scope != self.__store.scope:
            raise ValueError('fixed actor and entire registered installation required')
        digest = _payload_hash(request)
        try:
            with self.__store.admission_lock() as lock:
                with self.__store._connection(write=True,lock=lock,timeout=lock.deadline-time.monotonic()) as conn:
                    existing = conn.execute('SELECT * FROM control_requests WHERE request_id=?', (request.request_id,)).fetchone()
                    highest = conn.execute('SELECT COALESCE(MAX(acceptance_revision),0) FROM control_requests').fetchone()[0]
                    if existing:
                        same = existing['payload_hash'] == digest
                        result = RequestAcceptance('REQUESTED' if same else 'CONFLICT',request.request_id,
                            existing['acceptance_revision'] if same else None,'IDEMPOTENT' if same else 'REPLAY_CONFLICT',same)
                    elif request.expected_revision != highest:
                        result = RequestAcceptance('CONFLICT',request.request_id,None,'REVISION_CONFLICT')
                    else:
                        revision = highest + 1
                        conn.execute('INSERT INTO control_requests VALUES(?,?,?,?,?,?,?,?,?)',
                            (request.request_id,request.actor,_stamp(request.requested_at),self.__store.scope_hash,'mock',request.action.value,request.expected_revision,revision,digest))
                        conn.execute('INSERT INTO control_request_audit VALUES(NULL,?,?,?,?,?,?)',
                            (request.request_id,request.actor,self.__store.scope_hash,'mock','REQUESTED',_stamp(self.__store.clock())))
                        result = RequestAcceptance('REQUESTED',request.request_id,revision,'DURABLE_ACCEPTANCE')
                    if result.status == 'CONFLICT':
                        # A new conflicting ID was never accepted: NULL retains FK truth.
                        conn.execute('INSERT INTO control_request_audit VALUES(NULL,?,?,?,?,?,?)',
                            (request.request_id if existing else None,request.actor,self.__store.scope_hash,'mock',
                             result.reason_code,_stamp(self.__store.clock())))
                # Successful acknowledgement only after durable commit, then lock release.
            return result
        except ControlLockUnavailable:
            return RequestAcceptance('UNAVAILABLE',request.request_id,None,'LOCK_UNAVAILABLE')
        except (OSError, ValueError, sqlite3.DatabaseError):
            return RequestAcceptance('UNAVAILABLE',request.request_id,None,'STORAGE_UNAVAILABLE')


class _ServiceControlCapability:
    __slots__ = ('_store','_leader')
    def __init__(self, store, leader): self._store, self._leader = store, leader
    def assert_owner(self): self._leader.assert_owner()
