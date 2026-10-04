"""Process-exclusive service supervision, independent of account POST authority."""
from __future__ import annotations

import fcntl
import os
import uuid
import weakref

from .service_store import ServiceJournal, private_directory, protected_descriptor
from .web_store import timestamp


class ServiceLeaderBusy(RuntimeError):
    pass


class ServiceRestartDenied(RuntimeError):
    pass


class ServiceOwnershipLost(RuntimeError):
    pass


class ServiceLeader:
    def __init__(self, settings, *, journal: ServiceJournal, scope=None, automatic_restart=False):
        if settings != journal.settings:
            raise ValueError('leader/journal registration mismatch')
        self.settings, self.journal = settings, journal
        self.scope = scope or (settings.registered_scopes[0] if settings.registered_scopes else None)
        journal._scope(self.scope)
        if type(automatic_restart) is not bool:
            raise ValueError('explicit restart classification required')
        self.automatic_restart = automatic_restart
        self.lock_path = settings.validate_topology()[2] / 'service-leader.lock'
        self.generation_id = str(uuid.uuid4())
        self.state = 'UNACQUIRED'
        self._lock_fd = None
        self._pid = os.getpid()
        # fork children close their inherited descriptor without LOCK_UN, which
        # would unlock the parent's shared open-file description too.
        ref = weakref.ref(self)
        def after_child():
            owner = ref()
            if owner is not None and owner._lock_fd is not None:
                os.close(owner._lock_fd)
                owner._lock_fd = None
                owner.state = 'INHERITED_NO_AUTHORITY'
        os.register_at_fork(after_in_child=after_child)

    def acquire(self):
        if self._lock_fd is not None or self.state != 'UNACQUIRED':
            raise ServiceOwnershipLost('leader cannot reacquire a generation')
        self.settings.validate_topology()
        private_directory(self.lock_path.parent)
        fd = protected_descriptor(self.lock_path, create=True)
        os.set_inheritable(fd, False)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ServiceLeaderBusy('live service leader owns OS lock') from None
            info = os.fstat(fd)
            self._inode = (info.st_dev, info.st_ino)
            now = timestamp(self.journal.clock())
            denied = False
            with self.journal.connection() as c:
                predecessor = c.execute('SELECT * FROM service_generations ORDER BY rowid DESC LIMIT 1').fetchone()
                unexpected = predecessor is not None and predecessor['stopped_at'] is None
                # A removed/replaced lock cannot masquerade as an exited owner.
                if unexpected and predecessor['state'] in ('RUNNING','RECOVERY_ONLY'):
                    try:
                        os.kill(predecessor['pid'], 0)
                    except ProcessLookupError:
                        pass
                    except PermissionError:
                        raise ServiceLeaderBusy('predecessor process identity remains uncertain') from None
                    else:
                        raise ServiceLeaderBusy('durable predecessor remains live')
                timing_known = (predecessor is None or
                    (isinstance(predecessor['started_at'], (int,float)) and now >= predecessor['started_at']
                     and (predecessor['stopped_at'] is None or now >= predecessor['stopped_at'])))
                last_attention = c.execute('SELECT state FROM service_attention_events ORDER BY event_id DESC LIMIT 1').fetchone()
                attention = last_attention is not None and last_attention[0] == 'MANUAL_ATTENTION'
                if unexpected or self.automatic_restart or attention or not timing_known:
                    denied = not self.journal._reserve_restart(c, self.generation_id,
                        'UNEXPECTED_EXIT' if unexpected else 'AUTOMATIC_RESTART', now,
                        predecessor_timing_known=timing_known and (predecessor is not None or not self.automatic_restart))
                if not denied:
                    if unexpected:
                        c.execute("UPDATE service_generations SET state='UNEXPECTED_EXIT' WHERE generation_id=?", (predecessor['generation_id'],))
                        self.journal._recover_provider_admissions(c,now)
                    self.state = 'RECOVERY_ONLY' if unexpected else 'RUNNING'
                    c.execute('INSERT INTO service_generations VALUES(?,?,?,?,?,NULL,?)',
                        (self.generation_id,self.scope.account_scope_hash,self.scope.execution_target,self._pid,now,self.state))
            if denied:
                self.state = 'MANUAL_ATTENTION'
                raise ServiceRestartDenied('durable service restart admission denied')
            self._lock_fd = fd
            return self
        except BaseException:
            os.close(fd)
            raise

    def assert_owner(self):
        if self._lock_fd is None or os.getpid() != self._pid:
            raise ServiceOwnershipLost('service leader process ownership absent')
        try:
            descriptor = os.fstat(self._lock_fd)
            path = self.lock_path.stat()
            if ((descriptor.st_dev, descriptor.st_ino) != self._inode
                    or (path.st_dev,path.st_ino) != self._inode or path.st_nlink != 1
                    or path.st_mode & 0o077 or path.st_uid != self._pid_uid):
                raise ServiceOwnershipLost('service leader file identity changed')
            with self.journal.connection() as c:
                row=c.execute('SELECT * FROM service_generations WHERE generation_id=?',(self.generation_id,)).fetchone()
                if (row is None or row['pid'] != self._pid or row['stopped_at'] is not None
                        or row['state'] != self.state):
                    raise ServiceOwnershipLost('durable service generation lost')
        except (OSError, ValueError):
            raise ServiceOwnershipLost('service leader evidence unavailable') from None

    @property
    def _pid_uid(self):
        return os.getuid()

    def close(self, clean_stop=True):
        if self._lock_fd is None:
            return
        if os.getpid() != self._pid:
            os.close(self._lock_fd)
            self._lock_fd=None
            return
        try:
            with self.journal.connection() as c:
                c.execute('UPDATE service_generations SET stopped_at=?,state=? WHERE generation_id=? AND pid=? AND stopped_at IS NULL',
                    (timestamp(self.journal.clock()) if clean_stop else None,
                     'STOPPED' if clean_stop else 'UNEXPECTED_EXIT',self.generation_id,self._pid))
            self.state='STOPPED' if clean_stop else 'UNEXPECTED_EXIT'
        finally:
            os.close(self._lock_fd)
            self._lock_fd=None

    def __enter__(self):
        return self.acquire() if self._lock_fd is None else self

    def __exit__(self, exc_type, exc, traceback):
        self.close(clean_stop=exc_type is None)
