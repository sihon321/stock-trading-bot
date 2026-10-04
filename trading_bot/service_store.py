"""Owned operational evidence. No broker, control or trading-journal writers."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import sqlite3
import stat

from .service_config import ServiceSettings
from .service_models import (LogicalJobKey, ProviderCallAdmission, ProviderAdmissionState,
                             KST, ServiceExpectation, ServiceJobState, ServiceScope)
from .web_config import checked_path
from .web_store import timestamp

SERVICE_SCHEMA_VERSION = 1
SERVICE_OWNER = 'phase15-service'

_TABLES = {
    'service_generations': 'generation_id TEXT PRIMARY KEY, scope_hash TEXT NOT NULL, target TEXT NOT NULL, pid INTEGER NOT NULL, started_at REAL NOT NULL, stopped_at REAL, state TEXT NOT NULL',
    'service_jobs': 'job_id TEXT PRIMARY KEY, scope_hash TEXT NOT NULL, target TEXT NOT NULL, trading_date_kst TEXT NOT NULL, kind TEXT NOT NULL, due_at REAL NOT NULL, dispatch_deadline_at REAL NOT NULL, state TEXT NOT NULL, universe_json TEXT, universe_hash TEXT, owner_generation TEXT NOT NULL, revision INTEGER NOT NULL, UNIQUE(scope_hash,target,trading_date_kst,kind)',
    'service_job_events': 'event_id INTEGER PRIMARY KEY, job_id TEXT NOT NULL REFERENCES service_jobs(job_id), sequence INTEGER NOT NULL, state TEXT NOT NULL, reason_code TEXT NOT NULL, source_ids_json TEXT NOT NULL, observed_at REAL NOT NULL, UNIQUE(job_id,sequence)',
    'service_restart_attempts': 'attempt_id INTEGER PRIMARY KEY, generation_id TEXT UNIQUE NOT NULL, admitted_at REAL NOT NULL, reason TEXT NOT NULL, admitted INTEGER NOT NULL CHECK(admitted=1)',
    'service_attention_events': 'event_id INTEGER PRIMARY KEY, state TEXT NOT NULL, reason_code TEXT NOT NULL, observed_at REAL NOT NULL',
    'service_launcher_events': 'event_id INTEGER PRIMARY KEY, generation_id TEXT NOT NULL, reason_code TEXT NOT NULL, observed_at REAL NOT NULL',
    'service_expectations': 'expectation_id TEXT PRIMARY KEY, scope_hash TEXT NOT NULL, target TEXT NOT NULL, trading_date_kst TEXT NOT NULL, kind TEXT NOT NULL, due_at REAL, expected_until REAL, calendar_state TEXT NOT NULL, session_source_id TEXT NOT NULL, control_revision INTEGER NOT NULL, expected_running TEXT NOT NULL, reason_code TEXT NOT NULL, observed_at REAL NOT NULL, producer_kind TEXT NOT NULL, config_hash TEXT NOT NULL, config_effective_at REAL NOT NULL, login_source_id TEXT NOT NULL, login_effective_at REAL NOT NULL, session_source_hash TEXT NOT NULL, controls_observed_at REAL NOT NULL, evidence_json TEXT NOT NULL',
    'service_expectation_health': 'event_id INTEGER PRIMARY KEY, scope_hash TEXT NOT NULL, target TEXT NOT NULL, trading_date_kst TEXT NOT NULL, source_kind TEXT NOT NULL, source_id TEXT NOT NULL, state TEXT NOT NULL, reason_code TEXT NOT NULL, observed_at REAL NOT NULL',
    'service_provider_admissions': 'dispatch_id TEXT PRIMARY KEY, evaluation_id TEXT UNIQUE NOT NULL, scope_hash TEXT NOT NULL, target TEXT NOT NULL, trading_date_kst TEXT NOT NULL, envelope_hash TEXT NOT NULL, state TEXT NOT NULL, reason_code TEXT NOT NULL, control_revision INTEGER NOT NULL, session_source_id TEXT NOT NULL, observed_at REAL NOT NULL, invocation_started_at REAL',
    'service_heartbeats': 'worker_id TEXT PRIMARY KEY, generation_id TEXT NOT NULL REFERENCES service_generations(generation_id), observed_at REAL NOT NULL, phase TEXT NOT NULL, job_id TEXT',
}
_APPEND_ONLY = ('service_job_events', 'service_restart_attempts', 'service_attention_events',
                'service_launcher_events', 'service_expectations', 'service_expectation_health')


def code(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', value):
        raise ValueError('bounded reason code required')
    return value


def identity(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,128}', value):
        raise ValueError('bounded identity required')
    return value


def private_directory(path):
    path = checked_path(path)
    missing = []
    cursor = path
    while not cursor.exists():
        missing.append(cursor)
        cursor = cursor.parent
    if cursor.stat().st_uid != os.getuid() or cursor.stat().st_mode & 0o022:
        raise ValueError('owner controlled parent required')
    for item in reversed(missing):
        item.mkdir(mode=0o700)
    if not path.is_dir() or path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
        raise ValueError('0700 owner directory required')
    return path


def protected_descriptor(path, *, create=False):
    path = checked_path(path)
    flags = os.O_RDWR | os.O_NOFOLLOW | (os.O_CREAT if create else 0)
    fd = os.open(path, flags, 0o600)
    info = os.fstat(fd)
    current = path.stat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or info.st_mode & 0o077 or info.st_nlink != 1
            or (info.st_dev, info.st_ino) != (current.st_dev, current.st_ino)):
        os.close(fd)
        raise ValueError('0600 unlinked owner regular file required')
    return fd


def _owned(conn, *, allow_empty=False):
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not tables and allow_empty:
        return False
    if 'service_metadata' not in tables:
        raise ValueError('service schema ownership missing')
    rows = conn.execute('SELECT owner,version FROM service_metadata').fetchall()
    if len(rows) != 1 or tuple(rows[0]) != (SERVICE_OWNER, SERVICE_SCHEMA_VERSION):
        raise ValueError('foreign or unsupported service schema')
    if not set(_TABLES).issubset(tables):
        raise ValueError('incomplete service schema')
    return True


def migrate_service(conn, *, fail_after_step=None):
    """Rollback every DDL step together; never migrate a foreign schema."""
    if conn.in_transaction:
        raise ValueError('migration needs an independent transaction')
    conn.execute('BEGIN IMMEDIATE')
    try:
        if not _owned(conn, allow_empty=True):
            conn.execute('CREATE TABLE service_metadata(owner TEXT PRIMARY KEY, version INTEGER NOT NULL)')
            conn.execute('INSERT INTO service_metadata VALUES(?,?)', (SERVICE_OWNER, SERVICE_SCHEMA_VERSION))
            for name, columns in _TABLES.items():
                conn.execute(f'CREATE TABLE {name} ({columns})')
                if fail_after_step == name or (fail_after_step == 'jobs' and name == 'service_jobs'):
                    raise RuntimeError('injected service migration failure')
            for name in _APPEND_ONLY:
                for action in ('UPDATE', 'DELETE'):
                    conn.execute(f"CREATE TRIGGER {name}_no_{action.lower()} BEFORE {action} ON {name} BEGIN SELECT RAISE(ABORT,'append-only service evidence'); END")
            conn.execute("CREATE TRIGGER immutable_job BEFORE UPDATE OF job_id,scope_hash,target,trading_date_kst,kind,due_at,dispatch_deadline_at ON service_jobs BEGIN SELECT RAISE(ABORT,'immutable logical job'); END")
            conn.execute("CREATE TRIGGER immutable_universe BEFORE UPDATE OF universe_json,universe_hash ON service_jobs WHEN OLD.universe_json IS NOT NULL BEGIN SELECT RAISE(ABORT,'immutable universe'); END")
            conn.execute("CREATE TRIGGER immutable_admission BEFORE UPDATE OF dispatch_id,evaluation_id,scope_hash,target,trading_date_kst,envelope_hash ON service_provider_admissions BEGIN SELECT RAISE(ABORT,'immutable consumed dispatch'); END")
            conn.execute("CREATE TRIGGER no_admission_delete BEFORE DELETE ON service_provider_admissions BEGIN SELECT RAISE(ABORT,'consumed dispatch'); END")
        conn.commit()
    except BaseException:
        conn.rollback()
        raise


class ServiceJournal:
    def __init__(self, settings: ServiceSettings, *, clock=None):
        self.settings = settings
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.path = settings.validate_topology()[0]

    def _scope(self, scope):
        if not isinstance(scope, ServiceScope) or scope not in self.settings.registered_scopes:
            raise ValueError('configured service scope required')

    def initialize(self, *, fail_after_step=None):
        self.settings.validate_topology()
        private_directory(self.path.parent)
        fd = protected_descriptor(self.path, create=True)
        try:
            conn = sqlite3.connect(self.path.as_uri()+'?mode=rw', uri=True, timeout=1)
            try:
                conn.execute('PRAGMA foreign_keys=ON')
                migrate_service(conn, fail_after_step=fail_after_step)
            finally:
                conn.close()
        finally:
            os.close(fd)

    @contextmanager
    def connection(self):
        self.settings.validate_topology()
        private_directory(self.path.parent)
        fd = protected_descriptor(self.path)
        conn = None
        try:
            conn = sqlite3.connect(self.path.as_uri()+'?mode=rw', uri=True, timeout=1)
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA foreign_keys=ON')
            conn.execute('BEGIN IMMEDIATE')
            _owned(conn)
            yield conn
            conn.commit()
        except BaseException:
            if conn is not None:
                conn.rollback()
            raise
        finally:
            if conn is not None:
                conn.close()
            os.close(fd)

    def claim_job(self, key: LogicalJobKey, *, due_at, dispatch_deadline_at, owner_generation):
        self._scope(key.scope)
        identity(owner_generation)
        if timestamp(due_at) >= timestamp(dispatch_deadline_at):
            raise ValueError('ordered dispatch slot required')
        if any(v.astimezone(KST).date() != key.trading_date_kst for v in (due_at, dispatch_deadline_at)):
            raise ValueError('exact-date dispatch slot required')
        with self.connection() as c:
            if c.execute('SELECT 1 FROM service_jobs WHERE job_id=?', (key.logical_id,)).fetchone():
                return None
            c.execute('INSERT INTO service_jobs VALUES(?,?,?,?,?,?,?,?,NULL,NULL,?,0)',
                (key.logical_id,key.scope.account_scope_hash,key.scope.execution_target,str(key.trading_date_kst),key.kind.value,timestamp(due_at),timestamp(dispatch_deadline_at),'CLAIMED',owner_generation))
            self._event(c,key.logical_id,'CLAIMED','RESERVED',(),self.clock())
            return key.logical_id

    @staticmethod
    def _event(c, job_id, state, reason_code, sources, at):
        sequence = c.execute('SELECT COALESCE(MAX(sequence),0)+1 FROM service_job_events WHERE job_id=?',(job_id,)).fetchone()[0]
        c.execute('INSERT INTO service_job_events(job_id,sequence,state,reason_code,source_ids_json,observed_at) VALUES(?,?,?,?,?,?)',
                  (job_id,sequence,state,code(reason_code),json.dumps(sources),timestamp(at)))

    def append_job_event(self, job_id, state, *, reason_code, source_ids=(), observed_at=None, expected_revision=None):
        state = ServiceJobState(state).value
        if len(source_ids)>128: raise ValueError('bounded sources required')
        for s in source_ids: identity(s)
        with self.connection() as c:
            row=c.execute('SELECT revision FROM service_jobs WHERE job_id=?',(job_id,)).fetchone()
            if row is None or (expected_revision is not None and row['revision']!=expected_revision):
                raise ValueError('job revision conflict')
            self._event(c,job_id,state,reason_code,source_ids,observed_at or self.clock())
            c.execute('UPDATE service_jobs SET state=?,revision=revision+1 WHERE job_id=?',(state,job_id))
            return row['revision']+1

    def load_job(self, job_id):
        with self.connection() as c:
            row=c.execute('SELECT * FROM service_jobs WHERE job_id=?',(job_id,)).fetchone()
            return None if row is None else dict(row)

    def commit_universe(self, job_id, universe):
        if not isinstance(universe,(tuple,list)) or len(universe)>4096 or len(set(universe))!=len(universe) or any(not isinstance(s,str) or not re.fullmatch(r'\d{6}',s) for s in universe):
            raise ValueError('bounded ordered unique ticker universe required')
        data=json.dumps(universe,separators=(',',':')); digest=hashlib.sha256(data.encode()).hexdigest()
        with self.connection() as c:
            row=c.execute('SELECT universe_json FROM service_jobs WHERE job_id=?',(job_id,)).fetchone()
            if row is None: raise ValueError('job missing')
            if row[0] is not None:
                if row[0]!=data: raise ValueError('universe conflict')
            else:
                c.execute('UPDATE service_jobs SET universe_json=?,universe_hash=?,revision=revision+1 WHERE job_id=?',(data,digest,job_id))
            return digest

    def list_events(self, job_id):
        with self.connection() as c:
            return tuple(dict(r) for r in c.execute('SELECT * FROM service_job_events WHERE job_id=? ORDER BY sequence',(job_id,)))

    def heartbeat(self, worker_id, generation_id, *, phase, job_id=None, observed_at=None):
        identity(worker_id); identity(generation_id); code(phase)
        with self.connection() as c:
            if not c.execute('SELECT 1 FROM service_generations WHERE generation_id=? AND pid=? AND stopped_at IS NULL',(generation_id,os.getpid())).fetchone():
                raise ValueError('live generation owner required')
            c.execute('INSERT INTO service_heartbeats VALUES(?,?,?,?,?) ON CONFLICT(worker_id) DO UPDATE SET generation_id=excluded.generation_id,observed_at=excluded.observed_at,phase=excluded.phase,job_id=excluded.job_id',
                (worker_id,generation_id,timestamp(observed_at or self.clock()),phase,job_id))

    def _reserve_restart(self,c,generation_id,reason,now,*,predecessor_timing_known=True):
        latest=c.execute('SELECT * FROM service_attention_events ORDER BY event_id DESC LIMIT 1').fetchone()
        prior=c.execute('SELECT MAX(admitted_at) FROM service_restart_attempts').fetchone()[0]
        denied=None
        if latest is not None and latest['state']=='MANUAL_ATTENTION': denied='MANUAL_ATTENTION'
        elif (not predecessor_timing_known or (prior is not None and now<prior)
              or (latest is not None and now<latest['observed_at'])): denied='CLOCK_OR_PREDECESSOR_UNKNOWN'
        elif c.execute('SELECT COUNT(*) FROM service_restart_attempts WHERE admitted_at>=?',(now-600,)).fetchone()[0]>=3: denied='RESTART_EXHAUSTED'
        if denied:
            if latest is None or latest['state']!='MANUAL_ATTENTION':
                c.execute('INSERT INTO service_attention_events(state,reason_code,observed_at) VALUES(?,?,?)',('MANUAL_ATTENTION',denied,now))
            c.execute('INSERT INTO service_launcher_events(generation_id,reason_code,observed_at) VALUES(?,?,?)',(generation_id,denied,now))
            return False
        c.execute('INSERT INTO service_restart_attempts(generation_id,admitted_at,reason,admitted) VALUES(?,?,?,1)',(generation_id,now,reason))
        return True

    def reserve_restart(self,generation_id,*,reason,observed_at=None,predecessor_timing_known=True):
        identity(generation_id); code(reason)
        with self.connection() as c:
            return self._reserve_restart(c,generation_id,reason,timestamp(observed_at or self.clock()),predecessor_timing_known=predecessor_timing_known)

    def request_attention_reset(self,*,safety_validated,recovery_validated,observed_at=None):
        now=timestamp(observed_at or self.clock())
        with self.connection() as c:
            row=c.execute('SELECT * FROM service_attention_events ORDER BY event_id DESC LIMIT 1').fetchone()
            last=c.execute('SELECT MAX(admitted_at) FROM service_restart_attempts').fetchone()[0]
            if (type(safety_validated) is not bool or type(recovery_validated) is not bool or not safety_validated or not recovery_validated or row is None or row['state']!='MANUAL_ATTENTION' or now-max(row['observed_at'],last or row['observed_at'])<600):
                return False
            c.execute("INSERT INTO service_attention_events(state,reason_code,observed_at) VALUES('RESET','EXPLICIT_VALIDATED_RESET',?)",(now,))
            return True

    def record_expectation(self, expectation):
        if expectation.producer_kind!='RUNTIME_OBSERVED': raise ValueError('runtime provenance required')
        return self._record_expectation(expectation)

    def _record_expectation(self,e):
        e=ServiceExpectation.model_validate(e); self._scope(e.scope)
        facts=e.model_dump(mode='json',exclude={'expectation_id','observed_at'})
        key=hashlib.sha256(json.dumps(facts,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        payload=e.model_copy(update={'expectation_id':key}).model_dump_json()
        with self.connection() as c:
            c.execute('INSERT OR IGNORE INTO service_expectations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (key,e.scope.account_scope_hash,e.scope.execution_target,str(e.trading_date_kst),e.kind.value,
                 None if e.due_at is None else timestamp(e.due_at),None if e.deadline_at is None else timestamp(e.deadline_at),
                 e.eligibility.value,e.session_source_id,e.control_revision,e.state,e.reason_code,timestamp(e.observed_at),e.producer_kind,
                 e.config_hash,timestamp(e.config_effective_at),e.login_source_id,timestamp(e.login_effective_at),e.session_source_hash,timestamp(e.controls_observed_at),payload))
        return key

    def expectation_writer(self):
        return ExpectationWriter(self)

    def prepare_provider_admission(self,admission,*,consumed_dispatch):
        a=ProviderCallAdmission.model_validate(admission); self._scope(a.scope)
        if a.state!=ProviderAdmissionState.PREPARED: raise ValueError('new PREPARED handoff required')
        # Parent supplies a committed read-back from the trading owner, never a new claim.
        expected=dict(dispatch_id=a.dispatch_id,evaluation_id=a.evaluation_id,account_scope_hash=a.scope.account_scope_hash,
            execution_target=a.scope.execution_target,trading_date_kst=str(a.trading_date_kst),envelope_hash=a.envelope_hash,dispatch_state='DISPATCHED')
        if not isinstance(consumed_dispatch,dict) or any(consumed_dispatch.get(k)!=v for k,v in expected.items()):
            raise ValueError('exact consumed trading dispatch required')
        try: started=datetime.fromisoformat(consumed_dispatch['dispatched_at'])
        except (KeyError,ValueError,TypeError): raise ValueError('committed consumed timestamp required') from None
        if timestamp(started)>timestamp(a.observed_at): raise ValueError('future consumed handoff')
        if started.astimezone(KST).date()!=a.trading_date_kst: raise ValueError('exact-date consumed handoff')
        with self.connection() as c:
            universe=c.execute("SELECT universe_json FROM service_jobs WHERE scope_hash=? AND target=? AND trading_date_kst=? AND kind='DAILY'",
                (a.scope.account_scope_hash,a.scope.execution_target,str(a.trading_date_kst))).fetchone()
            if universe is None or universe[0] is None:
                raise ValueError('committed daily universe required before provider handoff')
            if c.execute('SELECT 1 FROM service_provider_admissions WHERE dispatch_id=? OR evaluation_id=?',(a.dispatch_id,a.evaluation_id)).fetchone():
                raise ValueError('dispatch already consumed operationally')
            c.execute('INSERT INTO service_provider_admissions VALUES(?,?,?,?,?,?,?,?,?,?,?,NULL)',
                (a.dispatch_id,a.evaluation_id,a.scope.account_scope_hash,a.scope.execution_target,str(a.trading_date_kst),a.envelope_hash,a.state.value,a.reason_code,a.control_revision,a.session_source_id,timestamp(a.observed_at)))
        return ProviderAdmissionWriter(self,a.dispatch_id,a.scope,a.envelope_hash)

    def recover_provider_admissions(self, *, observed_at=None):
        """Parent recovery only: preserve consumption, never grant another call."""
        with self.connection() as c:
            return self._recover_provider_admissions(c,timestamp(observed_at or self.clock()))

    def _recover_provider_admissions(self,c,now):
        count=0
        for scope in self.settings.registered_scopes:
            count+=c.execute("UPDATE service_provider_admissions SET state='UNKNOWN',reason_code='PREDECESSOR_EXIT',observed_at=MAX(observed_at,?) WHERE scope_hash=? AND target=? AND state IN ('PREPARED','IN_FLIGHT')",
                (now,scope.account_scope_hash,scope.execution_target)).rowcount
        return count

    def load_provider_admission(self,dispatch_id):
        with self.connection() as c:
            r=c.execute('SELECT * FROM service_provider_admissions WHERE dispatch_id=?',(dispatch_id,)).fetchone()
            if r is None: return None
            return ProviderCallAdmission(dispatch_id=r['dispatch_id'],evaluation_id=r['evaluation_id'],
                scope=ServiceScope(account_scope_hash=r['scope_hash'],execution_target=r['target']),trading_date_kst=r['trading_date_kst'],
                envelope_hash=r['envelope_hash'],state=r['state'],reason_code=r['reason_code'],control_revision=r['control_revision'],
                session_source_id=r['session_source_id'],observed_at=datetime.fromtimestamp(r['observed_at'],timezone.utc),
                invocation_started_at=None if r['invocation_started_at'] is None else datetime.fromtimestamp(r['invocation_started_at'],timezone.utc))


class ExpectationWriter:
    """Operational facade; never composed with source or account writer capabilities."""
    __slots__=('__journal',)

    def __init__(self,journal): self.__journal=journal

    def record_derived(self,expectation):
        if expectation.producer_kind!='OBSERVER_DERIVED': raise ValueError('independent observer provenance required')
        return self.__journal._record_expectation(expectation)

    def record_source_health(self,*,scope,trading_date_kst,source_kind,source_id,state,reason_code,observed_at):
        self.__journal._scope(scope); code(source_kind); identity(source_id); code(reason_code)
        if state not in ('AVAILABLE','UNKNOWN','UNAVAILABLE'): raise ValueError('source-health state required')
        with self.__journal.connection() as c:
            c.execute('INSERT INTO service_expectation_health(scope_hash,target,trading_date_kst,source_kind,source_id,state,reason_code,observed_at) VALUES(?,?,?,?,?,?,?,?)',
                (scope.account_scope_hash,scope.execution_target,str(trading_date_kst),source_kind,source_id,state,reason_code,timestamp(observed_at)))


class ProviderAdmissionWriter:
    """One consumed operational row; terminal evidence never creates replay authority."""
    __slots__=('__journal','__dispatch_id','__scope','__envelope_hash')

    def __init__(self,journal,dispatch_id,scope,envelope_hash):
        self.__journal=journal; self.__dispatch_id=dispatch_id; self.__scope=scope; self.__envelope_hash=envelope_hash

    def transition_prepared(self,state,*,reason_code,observed_at,invocation_started_at=None,control_revision=None,session_source_id=None):
        state=ProviderAdmissionState(state)
        with self.__journal.connection() as c:
            r=c.execute('SELECT * FROM service_provider_admissions WHERE dispatch_id=? AND scope_hash=? AND target=? AND envelope_hash=?',
                (self.__dispatch_id,self.__scope.account_scope_hash,self.__scope.execution_target,self.__envelope_hash)).fetchone()
            transitions={'PREPARED':{'IN_FLIGHT','SUPPRESSED_NO_CALL','UNKNOWN'},'IN_FLIGHT':{'UNKNOWN','FINISHED'}}
            if r is None or state.value not in transitions.get(r['state'],set()): raise ValueError('consumed or terminal provider admission')
            started=invocation_started_at
            if r['invocation_started_at'] is not None:
                prior=datetime.fromtimestamp(r['invocation_started_at'],timezone.utc)
                if started is not None and started!=prior: raise ValueError('immutable invocation entry')
                started=prior
            a=ProviderCallAdmission(dispatch_id=r['dispatch_id'],evaluation_id=r['evaluation_id'],scope=self.__scope,
                trading_date_kst=r['trading_date_kst'],envelope_hash=r['envelope_hash'],state=state,reason_code=reason_code,
                control_revision=r['control_revision'] if control_revision is None else control_revision,
                session_source_id=r['session_source_id'] if session_source_id is None else session_source_id,
                observed_at=observed_at,invocation_started_at=started)
            if timestamp(observed_at)<r['observed_at']: raise ValueError('admission observation rollback')
            c.execute('UPDATE service_provider_admissions SET state=?,reason_code=?,control_revision=?,session_source_id=?,observed_at=?,invocation_started_at=? WHERE dispatch_id=?',
                (a.state.value,a.reason_code,a.control_revision,a.session_source_id,timestamp(a.observed_at),None if started is None else timestamp(started),a.dispatch_id))
            return a
