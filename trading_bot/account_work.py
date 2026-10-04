"""One acquire/recover/fresh-truth/work/reconcile/release account section.

No provider or cadence wait belongs inside this capability. Deadlines interrupt
synchronous I/O on the main thread; another process never steals a live flock.
"""
from __future__ import annotations

import signal
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Callable

from trading_bot.mutation_lease import LeaseRecoveryBlocked, release_after_reconciliation
from trading_bot.portfolio import PortfolioCompleteness, PortfolioSnapshot
from trading_bot.portfolio_store import append_portfolio_snapshot


class AccountWorkTimeout(BaseException):
    """Must escape collaborators' ordinary fail-soft Exception handlers."""


class AccountWorkBudget:
    def __init__(self, *, seconds=45., cleanup_seconds=10., monotonic=time.monotonic):
        if not 0 < cleanup_seconds < seconds <= 45:
            raise ValueError('account budget must reserve cleanup within 45 seconds')
        self.monotonic = monotonic
        self.started = monotonic()
        self.deadline = self.started + seconds
        self.work_deadline = self.deadline - cleanup_seconds

    @property
    def remaining_seconds(self):
        return max(0., self.deadline - self.monotonic())

    def assert_available(self, *, cleanup=False, minimum_seconds=0):
        remaining = (self.deadline if cleanup else self.work_deadline) - self.monotonic()
        if remaining <= minimum_seconds:
            raise AccountWorkTimeout('account work budget exhausted')
        return remaining

    @contextmanager
    def submission_guard(self, lease, *, timeout_seconds):
        """Recheck configured POST capacity at every final owner assertion."""
        minimum = max(5., float(timeout_seconds))
        original = lease.assert_active_owner
        def current_owner(*args, **kwargs):
            self.assert_available(minimum_seconds=minimum)
            return original(*args, **kwargs)
        lease.assert_active_owner = current_owner
        try:
            current_owner()
            yield
        finally:
            lease.assert_active_owner = original

    @contextmanager
    def interrupt_after(self, *, cleanup=False):
        remaining = self.assert_available(cleanup=cleanup)
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError('bounded account work requires a main-thread worker process')
        prior_timer = signal.getitimer(signal.ITIMER_REAL)
        if prior_timer != (0., 0.):
            raise RuntimeError('bounded account work cannot replace an active timer')
        prior_handler = signal.getsignal(signal.SIGALRM)
        def expire(signum, frame):
            raise AccountWorkTimeout('account I/O deadline exceeded')
        signal.signal(signal.SIGALRM, expire)
        signal.setitimer(signal.ITIMER_REAL, remaining)
        try:
            yield
            self.assert_available(cleanup=cleanup)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, prior_handler)


class BoundedAccountWork:
    def __init__(self, *, conn, account_scope_hash, lease_factory, snapshot_reader,
                 terminalize_prior, reconcile_snapshot, terminalize,
                 persist_unresolved, clock=lambda: datetime.now(timezone.utc),
                 monotonic=time.monotonic, barrier=lambda name: None):
        self.conn = conn
        self.account_scope_hash = account_scope_hash
        self.lease_factory = lease_factory
        self.snapshot_reader = snapshot_reader
        self.terminalize_prior = terminalize_prior
        self.reconcile_snapshot = reconcile_snapshot
        self.terminalize = terminalize
        self.persist_unresolved = persist_unresolved
        self.clock = clock
        self.barrier = barrier
        self.budget_factory = lambda: AccountWorkBudget(monotonic=monotonic)

    def run(self, operation: Callable):
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError('bounded account work requires a main-thread worker process')
        if self.conn.in_transaction:
            raise RuntimeError('account work requires committed evidence')
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError('account work clock must be aware')
        budget = self.budget_factory()
        prior_busy_timeout = self.conn.execute('PRAGMA busy_timeout').fetchone()[0]
        self.conn.execute('PRAGMA busy_timeout=1000')
        lease = None
        terminalized = False
        def terminalize():
            nonlocal terminalized
            if not terminalized:
                self.terminalize()
                terminalized = True
        def fresh():
            if self.conn.in_transaction:
                raise RuntimeError('broker truth cannot span an open transaction')
            current = self.snapshot_reader()
            if (not isinstance(current, PortfolioSnapshot)
                    or current.account_scope_hash != self.account_scope_hash
                    or current.completeness is not PortfolioCompleteness.COMPLETE
                    or not current.mutation_capable or current.observed_at < lease.acquired_at):
                raise LeaseRecoveryBlocked('fresh same-account broker truth required')
            return current
        try:
            with budget.interrupt_after():
                lease = self.lease_factory()
                if lease.account_scope_hash != self.account_scope_hash or lease.closed:
                    raise LeaseRecoveryBlocked('active scope does not match account work')
                if lease.recovery_required:
                    current = lease.recover_to_active(terminalize_prior_cycles=self.terminalize_prior,
                        query_fresh_snapshot=fresh, reconcile_prior_orders=self.reconcile_snapshot,
                        observed_at=self.clock())
                else:
                    lease.assert_active_owner(observed_at=self.clock())
                    current = fresh()
                    append_portfolio_snapshot(self.conn, current, cycle_id=lease.cycle_id,
                        observation_id=f'account-work:{uuid.uuid4().hex}')
                result = operation(lease, current, budget)
            if not lease.closed:
                def reconcile():
                    snapshot = fresh()
                    append_portfolio_snapshot(self.conn, snapshot, cycle_id=lease.cycle_id,
                        observation_id=f'account-reconcile:{uuid.uuid4().hex}')
                    verdict = self.reconcile_snapshot(snapshot)
                    self.barrier('ACCOUNT_RECONCILED')
                    return verdict
                with budget.interrupt_after(cleanup=True):
                    determinate = release_after_reconciliation(lease, terminalize_cycle=terminalize,
                        reconcile_submitted=reconcile, persist_unresolved=self.persist_unresolved,
                        observed_at=self.clock(), preserve_blocked=True)
                if not determinate:
                    raise LeaseRecoveryBlocked('account reconciliation unresolved')
                self.barrier('ACCOUNT_RELEASED')
            return result
        except BaseException:
            if lease is not None and not lease.closed:
                # Never call healthy release after interruption or failed proof.
                # If evidence writing itself fails, keep kernel exclusion until
                # process shutdown rather than opening an undocumented takeover.
                self.conn.rollback()
                try:
                    with budget.interrupt_after(cleanup=True):
                        terminalize()
                        self.persist_unresolved()
                except AccountWorkTimeout:
                    pass  # durable lease event below still records exhausted work
                lease.mark_recovery_blocked(reason='ACCOUNT_WORK_STALLED', observed_at=self.clock())
                lease.close_blocked()
            raise
        finally:
            self.conn.execute(f'PRAGMA busy_timeout={int(prior_busy_timeout)}')
