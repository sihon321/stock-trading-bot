"""One owner for synthetic Phase 15 fixtures. Never opens production stores."""
from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import json
import multiprocessing
import os
from pathlib import Path
import tempfile
from threading import Lock
from types import MappingProxyType
from unittest.mock import patch

from trading_bot.alert_models import (
    AlertSourceFact, AlertSubject, DeliveryAttempt, DeliveryState, IncidentEpisode, Severity,
)
from trading_bot.domain import Decision, LLMSignal
from trading_bot.service_config import ServiceSettings
from trading_bot.service_models import (
    AcceptanceReceipt, CheckpointApproval, KST, OwnerLoginEvidence,
    ServiceScope, SessionEvidence, SourceHash,
)

NOW = datetime(2026, 10, 5, 0, 0, tzinfo=timezone.utc)
SCOPE = ServiceScope(account_scope_hash='a' * 64, execution_target='mock')


class FakeServiceClock:
    def __init__(self, wall=NOW, monotonic_seconds=0.0):
        if wall.tzinfo is None or wall.utcoffset() is None:
            raise ValueError('aware fixture clock required')
        self.wall = wall.astimezone(timezone.utc)
        self._monotonic = float(monotonic_seconds)

    def __call__(self):
        return self.wall

    def now_utc(self):
        return self.wall

    def now_kst(self):
        return self.wall.astimezone(KST)

    def monotonic(self):
        return self._monotonic

    def advance(self, wall_seconds=0, monotonic_seconds=None):
        elapsed = max(0, wall_seconds) if monotonic_seconds is None else monotonic_seconds
        if elapsed < 0:
            raise ValueError('monotonic fixture clock cannot reverse')
        self.wall += timedelta(seconds=wall_seconds)
        self._monotonic += elapsed


def observer_only_midnight_progression():
    """Observer time samples only; no claims of Mac wake or runtime progress."""
    clock = FakeServiceClock(datetime(2026, 10, 5, 14, 59, tzinfo=timezone.utc))
    samples = [clock.now_kst()]
    clock.advance(wall_seconds=120, monotonic_seconds=0)
    samples.append(clock.now_kst())
    clock.advance(wall_seconds=9 * 3600, monotonic_seconds=0)
    samples.append(clock.now_kst())
    return tuple(samples)


def session_evidence(kind='normal', day=date(2026, 10, 5)):
    if kind not in {'normal', 'holiday', 'unknown', 'delayed'}:
        raise ValueError('unknown synthetic session kind')
    start = datetime(day.year, day.month, day.day, 10 if kind == 'delayed' else 9, tzinfo=KST)
    observed = start.replace(hour=8, minute=0)
    eligibility = {'holiday': 'HOLIDAY', 'unknown': 'UNKNOWN'}.get(kind, 'ELIGIBLE')
    return SessionEvidence(trading_date_kst=day, source_id=f'synthetic-{kind}-{day}',
        source_hash='b' * 64, source_url='https://kind.krx.co.kr/synthetic-offline',
        notice_id=f'synthetic-{day}', reviewed_at=observed, reviewer='synthetic-owner',
        observed_at=observed, effective_at=observed, eligibility=eligibility,
        continuous_open=start if eligibility == 'ELIGIBLE' else None,
        continuous_close=start + timedelta(hours=6, minutes=30) if eligibility == 'ELIGIBLE' else None)


@dataclass(frozen=True)
class ApprovalBundle:
    """Shape proofs only: SYNTHETIC is never authenticated elapsed-day acceptance."""
    receipt: AcceptanceReceipt

    @classmethod
    def synthetic(cls):
        return cls(AcceptanceReceipt(receipt_id='synthetic-receipt', evidence_class='SYNTHETIC',
            scope=SCOPE, campaign_id='synthetic-campaign', profile_fingerprint='c' * 64,
            source_hashes=(SourceHash(source_id='synthetic-report', source_hash='d' * 64),),
            checkpoint_approvals=tuple(CheckpointApproval(checkpoint=f'09-08 task {task}',
                actor='synthetic-owner', approved_at=NOW, evidence_ids=('synthetic-proof',))
                for task in (1, 2)), evidence_ids=('synthetic-proof',), approved_at=NOW))


def _temporary_path(raw):
    path = Path(raw).absolute()
    base = Path(tempfile.gettempdir()).resolve()
    repo = Path(__file__).resolve().parents[1]
    if (path.is_symlink() or not path.resolve().is_relative_to(base) or path.resolve() == base
            or path.resolve().is_relative_to(repo)):
        raise ValueError('pytest temporary location required')
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise ValueError('linked fixture path forbidden')
    return path


@dataclass(frozen=True)
class TempServiceTopology:
    root: Path

    def __post_init__(self):
        root = _temporary_path(self.root)
        if not root.is_dir() or root.stat().st_uid != os.getuid():
            raise ValueError('existing owned pytest tmp_path required')
        object.__setattr__(self, 'root', root)

    @property
    def audit_db_path(self):
        return self.root / 'audit' / 'audit.db'

    @property
    def service_db_path(self):
        return self.root / 'service' / 'service.db'

    @property
    def control_db_path(self):
        return self.root / 'control' / 'control.db'

    @property
    def web_db_path(self):
        return self.root / 'web' / 'web.db'

    @property
    def soak_db_path(self):
        return self.root / 'soak' / 'soak.db'

    @property
    def controller_db_path(self):
        return self.root / 'controller' / 'controller.db'

    @property
    def lock_dir(self):
        return self.root / 'locks'

    def registration(self, *, enabled=False, mode=None):
        config_root = self.root / 'config'
        config_root.mkdir(mode=0o700, exist_ok=True)
        paths = {name: config_root / f'{name}.json' for name in (
            'trading_config_path', 'acceptance_receipt_path', 'session_evidence_path', 'observer_config_path')}
        for name, path in paths.items():
            content = (ApprovalBundle.synthetic().receipt.model_dump_json()
                       if name == 'acceptance_receipt_path' else
                       session_evidence().model_dump_json() if name == 'session_evidence_path' else
                       json.dumps({'evidence_class': 'SYNTHETIC'}))
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8') as file:
                file.write(content)
            path.chmod(0o600)
        settings = ServiceSettings(service_enabled=enabled,
            mode=mode or ('KIS_MOCK' if enabled else 'DISABLED'), registered_scopes=(SCOPE,),
            service_db_path=self.service_db_path, control_db_path=self.control_db_path,
            lock_dir=self.lock_dir, trading_journal_paths=(self.audit_db_path, self.soak_db_path,
                self.controller_db_path), artifact_roots=(self.root / 'artifacts',), **paths)
        registration = config_root / ('enabled.json' if enabled else 'disabled.json')
        registration.write_text(settings.model_dump_json(), encoding='utf-8')
        registration.chmod(0o600)
        return settings


class FakeOwnerLoginProbe:
    def __init__(self, state='CONFIRMED', clock=None):
        self.state, self.clock = state, clock or FakeServiceClock()
        self._calls = []

    @property
    def calls(self):
        return tuple(self._calls)

    def observe_owner_gui(self):
        self._calls.append(self.clock())
        return OwnerLoginEvidence(owner_uid=os.getuid(),
            gui_session_id='synthetic-gui' if self.state == 'CONFIRMED' else None,
            source_id='synthetic-login-probe', observed_at=self.clock(),
            effective_at=self.clock(), state=self.state)


class FixtureSourceUnavailable(RuntimeError):
    pass


class FakeSourceReader:
    def __init__(self, sources, failures=()):
        self.sources, self.failures = dict(sources), frozenset(failures)
        self._calls = []

    @property
    def calls(self):
        return tuple(self._calls)

    def read(self, source_id):
        self._calls.append(source_id)
        if source_id in self.failures or source_id not in self.sources:
            raise FixtureSourceUnavailable('SYNTHETIC_SOURCE_UNAVAILABLE')
        return self.sources[source_id]


class AppendOnlyCallCounter:
    """Durable records at actual collaborator entry, inspectable after termination."""
    def __init__(self, path):
        self.path = _temporary_path(path)
        self._lock = Lock()

    @property
    def calls(self):
        if not self.path.exists():
            return ()
        return tuple(MappingProxyType(json.loads(line)) for line in self.path.read_text().splitlines())

    def append(self, kind, subject='synthetic'):
        with self._lock:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8') as file:
                file.write(json.dumps({'kind': kind, 'subject': subject}) + '\n')
                file.flush()
                os.fsync(file.fileno())


class FixtureAlreadyCalled(RuntimeError):
    pass


class FakeSingleShotProvider:
    def __init__(self, counter, result=None):
        self.counter = counter
        self.result = result if result is not None else LLMSignal(Decision.HOLD, 0.0, 'SYNTHETIC_OFFLINE')
        self._called = False

    def generate_signal(self, context):
        if self._called:
            raise FixtureAlreadyCalled('SYNTHETIC_SINGLE_SHOT_CONSUMED')
        self._called = True
        self.counter.append('PROVIDER')
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


class FakeBroker:
    def __init__(self, counter, result='SYNTHETIC_POST_RETURNED'):
        self.counter, self.result = counter, result

    def place_order(self, order, **kwargs):
        self.counter.append('BROKER')
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


class FakeNotificationTransport:
    def __init__(self, counter, result=True):
        self.counter, self.result = counter, result

    def send(self, text):
        self.counter.append('NOTIFICATION')
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


@dataclass(frozen=True)
class PendingCriticalFixture:
    incident: IncidentEpisode
    outbox: DeliveryAttempt
    next_reminder_at: datetime
    worker_state: str = 'HEALTHY'


def healthy_pending_critical(now=NOW):
    """Use shipped owner contracts; pending delivery is QUEUED, not runtime success."""
    subject = AlertSubject('synthetic-service', SCOPE.account_scope_hash, 'mock',
                           'ACCOUNT', 'SYNTHETIC_SOURCE_FAILURE')
    due = now + timedelta(seconds=1800)
    incident = IncidentEpisode('synthetic-pending-critical', subject, 1, Severity.CRITICAL,
        'UNAVAILABLE', True, now, now, 1, 0.0, None, None, False, due)
    outbox = DeliveryAttempt('synthetic-event', incident.episode_id, 1, 'IMMEDIATE',
                            'observer', DeliveryState.QUEUED, now)
    return PendingCriticalFixture(incident, outbox, due)


def temporary_pending_critical_store(tmp_path, clock=None):
    """Only the existing alert owner migrates this temporary alert store."""
    from trading_bot.alert_store import AlertStore
    root = _temporary_path(tmp_path)
    clock = clock or FakeServiceClock()
    store = AlertStore(root / 'alert-operations' / 'alerts.db', clock=clock)
    store.initialize()
    pending = healthy_pending_critical(clock())
    store.observe(AlertSourceFact(pending.incident.subject, 'synthetic-service',
        'synthetic-source', 1, clock(), 'UNAVAILABLE', Severity.CRITICAL))
    return store


BARRIER_NAMES = (
    'INPUT_COMMITTED', 'DISPATCHED', 'CHILD_STARTED', 'PROVIDER_ADMISSION_PREPARED',
    'BEFORE_TRANSPORT_ENTRY', 'TRANSPORT_ENTERED', 'RESPONSE_RECEIVED',
    'SIGNAL_FINALIZED', 'ACCOUNT_RECONCILED', 'SUBMISSION_ATTEMPTED',
    'POST_RETURNED', 'ACCOUNT_RELEASED',
)


def _append_checkpoint(path, name):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as file:
        file.write(name + '\n')
        file.flush()
        os.fsync(file.fileno())


def crash_barrier_entrypoint(checkpoint_path, counter_path, barrier, reached, release, entered, admission_lock):
    """Spawn-safe fake workflow. Provider acknowledgement precedes blocked response."""
    counter = AppendOnlyCallCounter(counter_path)
    for name in BARRIER_NAMES:
        if name == 'TRANSPORT_ENTERED':
            with admission_lock:
                counter.append('PROVIDER')
                _append_checkpoint(checkpoint_path, name)
                entered.set()
                if name == barrier:
                    reached.set()
            if name == barrier:
                if not release.wait(30):
                    return
            continue
        if name == 'SUBMISSION_ATTEMPTED':
            counter.append('BROKER')
        _append_checkpoint(checkpoint_path, name)
        if name == barrier:
            reached.set()
            if not release.wait(30):
                return


class SpawnedCrashBarrier:
    def __init__(self, tmp_path, barrier):
        if barrier not in BARRIER_NAMES:
            raise ValueError('unknown crash barrier')
        self.root = _temporary_path(tmp_path)
        self.checkpoint_path = self.root / f'{barrier}.checkpoints'
        self.counter = AppendOnlyCallCounter(self.root / f'{barrier}.calls.jsonl')
        ctx = multiprocessing.get_context('spawn')
        self.reached, self.release, self.entered = ctx.Event(), ctx.Event(), ctx.Event()
        self.admission_lock = ctx.Lock()
        self.process = ctx.Process(target=crash_barrier_entrypoint, args=(
            str(self.checkpoint_path), str(self.counter.path), barrier,
            self.reached, self.release, self.entered, self.admission_lock))

    @property
    def checkpoints(self):
        return tuple(self.checkpoint_path.read_text().splitlines()) if self.checkpoint_path.exists() else ()

    def __enter__(self):
        self.process.start()
        return self

    def __exit__(self, *args):
        if self.process.is_alive():
            self.process.terminate()
        self.process.join(5)
        if self.process.is_alive():
            self.process.kill()
            self.process.join(5)
        if self.process.is_alive():
            raise AssertionError('fixture process did not terminate')


class ExternalCapabilityForbidden(RuntimeError):
    pass


class NoExternalCapabilities:
    """Scoped tripwires; explicit multiprocessing fixtures run outside this context."""
    def __init__(self):
        self._attempts = []
        self._stack = ExitStack()

    @property
    def attempts(self):
        return tuple(self._attempts)

    def _deny(self, kind):
        def denied(*args, **kwargs):
            self._attempts.append(kind)
            raise ExternalCapabilityForbidden(kind)
        return denied

    def __enter__(self):
        targets = {
            'socket.create_connection': 'SOCKET', 'socket.socket.connect': 'SOCKET',
            'socket.socket.connect_ex': 'SOCKET', 'socket.socket.bind': 'SOCKET',
            'socket.getaddrinfo': 'SOCKET', 'socket.socket.sendto': 'SOCKET',
            'httpx.Client.send': 'HTTP', 'httpx.AsyncClient.send': 'HTTP',
            'urllib.request.urlopen': 'HTTP', 'http.client.HTTPConnection.connect': 'HTTP',
            'subprocess.Popen': 'PROCESS', 'os.system': 'PROCESS',
            'os.posix_spawn': 'PROCESS', 'os.posix_spawnp': 'PROCESS',
            'os.execv': 'PROCESS', 'os.execve': 'PROCESS', 'os.execvp': 'PROCESS',
            'os.execvpe': 'PROCESS',
            'openai.OpenAI': 'SDK', 'openai.AsyncOpenAI': 'SDK',
            'anthropic.Anthropic': 'SDK', 'anthropic.AsyncAnthropic': 'SDK',
        }
        try:
            for target, kind in targets.items():
                self._stack.enter_context(patch(target, self._deny(kind)))
        except BaseException:
            self._stack.close()
            raise
        return self

    def __exit__(self, *args):
        self._stack.close()
