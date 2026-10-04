"""Installation-global final admission, independently committed before one POST.

The flock spans transport and terminal evidence, never a SQLite transaction.
An admission without its primary attempt is UNKNOWN, not permission to retry.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from .control_store import ControlStore
from .domain import OrderSide
from .market_cycle import MarketCyclePolicy, QuoteObservation
from .mutation_lease import MutationLease
from .portfolio import PortfolioSnapshot, canonical_account_scope_hash
from .service_activation import OfflineActivationAuthority, ActivationVerdict
from .service_models import ServiceScope


class SubmissionDenied(RuntimeError):
    """Stable, sanitized denial; no vendor/configuration content."""


class OwnedActivationCheck:
    """Re-read protected receipt and exact owned acceptance evidence each time."""
    def __init__(self, settings, saved_reader, current_safety, clock):
        from .service_activation import ReadOnlyAcceptanceEvidenceReader
        if type(saved_reader) is not ReadOnlyAcceptanceEvidenceReader or saved_reader._settings!=settings:
            raise ValueError('owned acceptance reader required')
        self.settings,self.reader,self.safety,self.clock=settings,saved_reader,current_safety,clock

    def __call__(self):
        from .service_activation import load_acceptance_receipt, validate_unattended_activation
        receipt=load_acceptance_receipt(self.settings.acceptance_receipt_path)
        verdict=validate_unattended_activation(self.settings,receipt,self.reader,self.safety,now=self.clock())
        # Initial activation remains conservative. At final admission a known
        # ticker freeze has already been checked against this particular order.
        if verdict.reason_codes==('UNRESOLVED_FREEZE',):
            return ActivationVerdict(allowed=True,reason_codes=('SCOPED_FREEZE_CHECK_REQUIRED',),
                source_ids=verdict.source_ids,receipt_id=verdict.receipt_id,authority='OWNED_KIS_OBSERVED')
        return verdict


@dataclass(frozen=True)
class SubmissionAdmission:
    admission_id: str
    intent_id: str
    submission_id: str
    control_revision: int
    state: str
    source_ids: tuple[str, ...]
    admitted_at: datetime

    def detail(self):
        return dict(admission_id=self.admission_id, control_revision=self.control_revision,
            admission_state=self.state, admission_source_ids=json.dumps(self.source_ids),
            admitted_at=self.admitted_at.isoformat())


class FinalPostEntry:
    """Exact-order single-use transport capability from a live admission flock."""
    def __init__(self, authority, admission, adapter, account, order, snapped_price, prepared, origin):
        if type(authority) is not SubmissionAuthority or authority._active is None:
            raise SubmissionDenied('LIVE_ADMISSION_REQUIRED')
        self.authority,self.admission,self.adapter,self.account=authority,admission,adapter,account
        self.order,self.price,self.prepared,self.origin=order,snapped_price,prepared,origin
        self._used=False

    def enter(self, adapter, account, order, snapped_price, prepared):
        if (self._used or adapter is not self.adapter or account!=self.account or order!=self.order
            or snapped_price!=self.price or prepared is not self.prepared):
            raise SubmissionDenied('POST_ENTRY_IDENTITY_OR_REPLAY_DENIED')
        self._used=True
        active=self.authority._active
        if active is None or active[1]!=self.admission:
            raise SubmissionDenied('LIVE_ADMISSION_REQUIRED')
        lock,admission,scope,lease,evidence=active
        lock.assert_owned(self.authority.store)
        state=self.authority.store.reader().effective_state(scope)
        if (state.acceptance_revision!=admission.control_revision or not state.allows_risk_sell
            or (order.side is OrderSide.BUY and not state.allows_buy)):
            raise SubmissionDenied('CURRENT_CONTROL_DENIED')
        self.authority._saved_safety(scope,admission.intent_id,order.ticker.value,
            attempted_submission=admission.submission_id)
        self.authority.verify_attempt(admission,order,self.origin,lease=lease,fresh_evidence=evidence)


class SubmissionAuthority:
    def __init__(self, store: ControlStore, *, policy: MarketCyclePolicy, clock=None,
                 offline_authority: OfflineActivationAuthority | None = None,
                 unattended=False, activation_check=None):
        if type(store) is not ControlStore or type(policy) is not MarketCyclePolicy:
            raise ValueError('actual registered control and market owners required')
        if offline_authority is not None:
            if type(offline_authority) is not OfflineActivationAuthority:
                raise ValueError('explicit offline authority required')
            offline_authority.assert_settings(store.settings)
        else:
            from .session_evidence import SessionEvidenceProvider
            if type(policy.session_evidence_provider) is not SessionEvidenceProvider:
                raise ValueError('reviewed protected session authority required')
        self.store, self.policy = store, policy
        self.clock = clock or (lambda:datetime.now(timezone.utc))
        self.offline_authority = offline_authority
        self.unattended, self.activation_check = unattended, activation_check
        self._prepared_session = None
        self._active=None
        self._scope_aliases={}

    def _session_allows(self, prepared, now):
        """Only local protected notice readback while holding admission.lock."""
        from datetime import time
        from .service_models import SessionEligibility
        day=now.astimezone(ZoneInfo('Asia/Seoul')).date()
        if (prepared is None or not prepared.executable or prepared.trading_date!=day
            or not 0<=(now-prepared.observed_at_kst).total_seconds()<=10):
            return False
        notice=self.policy.session_evidence_provider.for_date(day)
        return (notice.eligibility is SessionEligibility.ELIGIBLE
            and notice.continuous_open is not None and notice.continuous_close is not None
            and notice.continuous_open<=now<notice.continuous_close
            and now.astimezone(ZoneInfo('Asia/Seoul')).time()<time(15,20))

    def assert_account(self, account, adapter, *, expected_scope=None):
        domain = getattr(adapter, '_domain', None)
        if self.offline_authority is not None:
            from .kis_order import KisOrderAdapter
            if isinstance(adapter, KisOrderAdapter) and not adapter._test_only_allow_unguarded_mutation:
                raise SubmissionDenied('OFFLINE_AUTHORITY_CANNOT_USE_KIS_ADAPTER')
        else:
            from .kis_order import KisOrderAdapter
            if type(adapter) is not KisOrderAdapter:
                raise SubmissionDenied('ACTUAL_KIS_ADAPTER_REQUIRED')
        if domain is not None and domain.rstrip('/') != 'https://openapivts.koreainvestment.com:29443':
            raise SubmissionDenied('SERVICE_TARGET_REAL_DENIED')
        # Existing Phase09 receipts use suffix; Phase11 manual leases include
        # product code. Preserve each owner identity instead of rewriting it.
        candidates=tuple(ServiceScope(account_scope_hash=canonical_account_scope_hash('mock',value),
            execution_target='mock') for value in (account.cano[-4:],f'{account.cano[-4:]}:{account.account_product_code}'))
        matches=tuple(s for s in candidates if s in self.store.settings.registered_scopes
            and (expected_scope is None or s.account_scope_hash==expected_scope))
        if len(matches)!=1:
            raise SubmissionDenied('ACCOUNT_SCOPE_MISMATCH')
        self._scope_aliases[matches[0].account_scope_hash]={s.account_scope_hash for s in candidates}
        timeout = getattr(adapter, '_timeout_seconds', 10)
        if not 0 < timeout <= 10:
            raise SubmissionDenied('POST_TIMEOUT_UNBOUNDED')
        return matches[0]

    def _saved_safety(self, scope, intent_id, ticker, *, attempted_submission=None):
        from .soak_reporting import ReadOnlySoakRepository, build_soak_report, _valid_release
        paths = self.store.settings.trading_journal_paths
        if len(paths)!=3:
            raise SubmissionDenied('EXACT_TRADING_JOURNALS_REQUIRED')
        repo = ReadOnlySoakRepository(*paths)
        iterator = repo.transactions()
        primary, soak, controller = next(iterator)
        try:
            aliases=self._scope_aliases.get(scope.account_scope_hash,{scope.account_scope_hash})
            if primary.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise SubmissionDenied('AUDIT_INTEGRITY_UNKNOWN')
            sources = [f'control:{self.store.scope_hash}']
            # Same local intent remains consumed even if a control commit failed.
            attempts=primary.execute("SELECT submission_id FROM order_events WHERE order_intent_id=? AND event_type='SUBMISSION_ATTEMPTED'",(intent_id,)).fetchall()
            if attempts and (attempted_submission is None or len(attempts)!=1 or attempts[0][0]!=attempted_submission):
                raise SubmissionDenied('INTENT_ALREADY_ATTEMPTED')
            terminal_intents=set()
            frozen=set()
            run_scopes={}
            for item in primary.execute('SELECT origin_cycle_id,account_scope_hash FROM mutation_lease_events'):
                if item[0]: run_scopes.setdefault(item[0],set()).add(item[1])
            for row in soak.execute('SELECT campaign_id FROM soak_campaigns ORDER BY campaign_id'):
                data=repo._load(primary,soak,controller,campaign_id=row[0])
                # Use the immutable owner identity table, not an ambient selected campaign.
                identities=soak.execute('SELECT * FROM soak_identity_receipts WHERE campaign_id=?',(row[0],)).fetchall()
                known_scopes={canonical_account_scope_hash('mock',r['account_suffix']) for r in identities if r['target']=='mock'}
                for event in data['events']:
                    if event['run_id'] and known_scopes:
                        run_scopes.setdefault(event['run_id'],set()).update(known_scopes)
                # Historical proof campaigns have no identity receipt. Their
                # known ticker freezes remain restrictions; absence must not
                # silently make the original 000660 ambiguity disappear.
                applicable=not known_scopes or bool(known_scopes & aliases)
                if not applicable:
                    continue
                class Saved:
                    def load(self, campaign_id): return data
                report=build_soak_report(Saved(), row[0])
                if data['campaign']['safety_failure_code'] or report.cross_store_unknown:
                    raise SubmissionDenied('GLOBAL_SAFETY_UNKNOWN')
                frozen.update(report.freezes.tickers)
                # Only shipped report validation can recognize a terminal freeze release.
                for frozen_subject in data['freezes']:
                    releases=[r for r in data['releases'] if r['freeze_id']==frozen_subject['freeze_id']]
                    if len(releases)==1 and _valid_release(data,frozen_subject,releases[0]):
                        terminal_intents.add(str(frozen_subject['order_intent_id']))
                sources.append(f'campaign:{row[0]}')
            if ticker in frozen:
                raise SubmissionDenied('TICKER_FROZEN')
            unresolved={}
            rows=primary.execute("SELECT e.*,r.target FROM order_events e JOIN runs r ON r.run_id=e.origin_run_id ORDER BY e.id").fetchall()
            for row in rows:
                if row['target'] not in ('mock','kis_mock'):
                    continue
                attributed=run_scopes.get(row['origin_run_id'])
                if attributed and not attributed & aliases:
                    continue
                key=row['order_intent_id']
                if row['event_type'] in ('SUBMISSION_ATTEMPTED','SUBMISSION_AMBIGUOUS','SUBMISSION_ACCEPTED'):
                    unresolved[key]=row['ticker']
                elif row['event_type']=='RECONCILED':
                    unresolved.pop(key,None)
            if any(key not in terminal_intents and value==ticker
                and not (key==intent_id and attempted_submission is not None) for key,value in unresolved.items()):
                raise SubmissionDenied('TICKER_UNRESOLVED')
            digest=hashlib.sha256(json.dumps([(r['id'],r['event_type']) for r in rows]).encode()).hexdigest()
            sources.append(f'audit:{digest}')
            return tuple(sources)
        finally:
            iterator.close()

    @contextmanager
    def admit(self, order, scope, intent_id, submission_id, lease, fresh_evidence,
              activation_check=None):
        """Yield only after durable admission; caller must commit primary attempt.

        Fresh evidence is (actual portfolio snapshot, available timestamped quote).
        No truth Boolean or duck-typed owner can replace these owners.
        """
        try:
            # Calendar refresh may use network; finish it before global locking.
            prepared_session=self.policy.classify(self.clock())
            with self.store.admission_lock() as lock:
                now=self.clock()
                state=self.store.reader().effective_state(scope)
                if not state.allows_risk_sell or (order.side is OrderSide.BUY and not state.allows_buy):
                    raise SubmissionDenied('EFFECTIVE_CONTROL_DENIED')
                if type(lease) is not MutationLease or lease.account_scope_hash!=scope.account_scope_hash:
                    raise SubmissionDenied('ACTUAL_ACCOUNT_OWNER_REQUIRED')
                paths=self.store.settings.trading_journal_paths
                lease_path=lease._conn.execute('PRAGMA database_list').fetchone()[2]
                if Path(lease_path).resolve()!=Path(paths[0]).resolve():
                    raise SubmissionDenied('LEASE_JOURNAL_MISMATCH')
                lease.assert_active_owner(observed_at=now)
                snapshot,quote=fresh_evidence
                if (type(snapshot) is not PortfolioSnapshot or not snapshot.mutation_capable
                    or snapshot.account_scope_hash!=scope.account_scope_hash
                    or snapshot.trading_date!=now.astimezone(ZoneInfo('Asia/Seoul')).date()
                    or not 0<=(now-snapshot.observed_at).total_seconds()<=10):
                    raise SubmissionDenied('FRESH_ACCOUNT_TRUTH_REQUIRED')
                from .data_models import SourceStatus
                if (getattr(getattr(quote,'health',None),'status',None) is not SourceStatus.AVAILABLE
                    or not self.policy.quote_freshness(QuoteObservation(quote.observed_at),now).fresh):
                    raise SubmissionDenied('FRESH_QUOTE_REQUIRED')
                if not self._session_allows(prepared_session, now):
                    raise SubmissionDenied('CURRENT_SESSION_DENIED')
                sources=self._saved_safety(scope,intent_id,order.ticker.value)
                notice=self.policy.session_evidence_provider.for_date(snapshot.trading_date)
                sources+=(f'snapshot:{snapshot.snapshot_id}',f'session:{notice.source_id}:{notice.source_hash}',
                    f'quote:{quote.observed_at.isoformat()}')
                with self.store._connection() as conn:
                    # Missing primary attempt after a crash has no attributable ticker.
                    prior=conn.execute("SELECT intent_id FROM submission_admissions WHERE scope_hash=? AND state IN ('IN_FLIGHT','UNKNOWN')",(scope.account_scope_hash,)).fetchall()
                from .reporting import ReadOnlyAuditRepository
                repo=ReadOnlyAuditRepository(paths[0]); primary=repo._connect()
                try:
                    for item in prior:
                        if primary.execute("SELECT 1 FROM order_events WHERE order_intent_id=? AND event_type='SUBMISSION_ATTEMPTED'",(item[0],)).fetchone() is None:
                            raise SubmissionDenied('CROSS_JOURNAL_ADMISSION_UNKNOWN')
                finally: primary.close()
                if self.unattended:
                    check=self.activation_check or activation_check
                    verdict=check() if type(check) is OwnedActivationCheck and check.settings==self.store.settings else None
                    if (type(verdict) is not ActivationVerdict or not verdict.allowed
                        or verdict.authority!='OWNED_KIS_OBSERVED' or not verdict.receipt_id or not verdict.source_ids):
                        raise SubmissionDenied('UNATTENDED_ACTIVATION_DENIED')
                    sources+=verdict.source_ids
                admission_id=self.store._record_admission(lock,scope=scope,intent_id=intent_id,
                    submission_id=submission_id,control_revision=state.acceptance_revision,admitted_at=now)
                admission=SubmissionAdmission(admission_id,intent_id,submission_id,state.acceptance_revision,'IN_FLIGHT',sources,now)
                self._prepared_session=prepared_session
                self._active=(lock,admission,scope,lease,fresh_evidence)
                try:
                    yield admission
                except BaseException:
                    try:
                        self.store._finish_admission(lock,admission_id,state='UNKNOWN',finished_at=max(now,self.clock()))
                    except Exception:
                        pass  # Retained IN_FLIGHT is also consumed and requires reconciliation.
                    raise
                else:
                    self.store._finish_admission(lock,admission_id,state='FINISHED',finished_at=max(now,self.clock()))
                finally:
                    self._active=None
        except SubmissionDenied:
            raise
        except Exception:
            raise SubmissionDenied('FINAL_ADMISSION_UNAVAILABLE') from None

    def verify_attempt(self, admission, order, origin_run_id, *, lease=None, fresh_evidence=None):
        from .reporting import ReadOnlyAuditRepository
        repo=ReadOnlyAuditRepository(self.store.settings.trading_journal_paths[0]); conn=repo._connect()
        try:
            repo._validate_schema(conn)
            run=conn.execute('SELECT target,dry_run FROM runs WHERE run_id=?',(origin_run_id,)).fetchone()
            if run is None or run['target'] not in ('mock','kis_mock') or run['dry_run']:
                raise SubmissionDenied('PRIMARY_RUN_TARGET_DENIED')
            rows=conn.execute("SELECT * FROM order_events WHERE order_intent_id=? AND event_type='SUBMISSION_ATTEMPTED'",(admission.intent_id,)).fetchall()
            if (len(rows)!=1 or rows[0]['submission_id']!=admission.submission_id
                or rows[0]['origin_run_id']!=origin_run_id or rows[0]['ticker']!=order.ticker.value
                or rows[0]['side']!=order.side.value or rows[0]['requested_qty']!=order.quantity
                or json.loads(rows[0]['detail_json']).get('admission_id')!=admission.admission_id):
                raise SubmissionDenied('PRIMARY_ATTEMPT_NOT_COMMITTED')
        finally: conn.close()
        # The primary sink is mutable application code. It must not invalidate
        # the account lease or advance the clock beyond admission freshness.
        if lease is not None:
            if type(lease) is not MutationLease or lease.cycle_id!=origin_run_id:
                raise SubmissionDenied('ACTUAL_ACCOUNT_OWNER_REQUIRED')
            lease.assert_active_owner(observed_at=self.clock())
            snapshot,quote=fresh_evidence
            now=self.clock()
            if (not 0<=(now-snapshot.observed_at).total_seconds()<=10
                or not self.policy.quote_freshness(QuoteObservation(quote.observed_at),now).fresh
                or not self._session_allows(self._prepared_session,now)):
                raise SubmissionDenied('FINAL_FRESHNESS_EXPIRED')


class ProofSubmissionContext:
    """Explicit manual proof authority; it does not require unattended acceptance.

    The proof owner retains its original IDs and accounting. This owner adds
    fresh account exclusion and admission before the original attempted event.
    """
    def __init__(self, authority, *, adapter, quote_reader):
        if type(authority) is not SubmissionAuthority or authority.unattended:
            raise ValueError('manual final authority required')
        self.authority,self.adapter,self.quote_reader=authority,adapter,quote_reader
        self._active=None
        self.post_kwargs={}

    @contextmanager
    def __call__(self, request, order, ids):
        from . import sqlite_audit
        from .portfolio_store import migrate_portfolio, append_portfolio_snapshot
        from .mutation_lease import acquire_mutation_lease
        from .portfolio import collect_portfolio_snapshot
        from .kis_order import MOCK_TR_PROFILE_CANDIDATES
        paths=tuple(Path(p).resolve() for p in self.authority.store.settings.trading_journal_paths)
        if paths!=tuple(Path(p).resolve() for p in (request.primary_audit_db_path,request.soak_db_path,request.controller_db_path)):
            raise SubmissionDenied('PROOF_JOURNAL_MISMATCH')
        scope=self.authority.assert_account(request.account,self.adapter)
        if scope.account_scope_hash!=canonical_account_scope_hash('mock',request.receipt.account_suffix):
            raise SubmissionDenied('PROOF_ACCOUNT_MISMATCH')
        profile=next(p for p in MOCK_TR_PROFILE_CANDIDATES if p.version==request.receipt.profile_version)
        now=self.authority.clock(); day=now.astimezone(ZoneInfo('Asia/Seoul')).date()
        cutoff=self.authority.policy.completed_bar_cutoff(day)
        if not cutoff.available:
            raise SubmissionDenied('PROOF_CALENDAR_UNKNOWN')
        conn=sqlite_audit.connect(paths[0]); lease=None
        try:
            migrate_portfolio(conn)
            lease=acquire_mutation_lease(conn,account_scope_hash=scope.account_scope_hash,
                lock_dir=paths[0].parent/'.mutation-locks',command='proof',cycle_id=ids[1],observed_at=now)
            lease.assert_active_owner(observed_at=now)  # Recovery is never auto-promoted.
            snapshot=collect_portfolio_snapshot(adapter=self.adapter,account=request.account,profile=profile,
                trading_date=day,previous_trading_date=cutoff.cutoff_date,account_scope_hash=scope.account_scope_hash,
                observed_at=self.authority.clock())
            append_portfolio_snapshot(conn,snapshot,cycle_id=ids[1],observation_id=snapshot.snapshot_id)
            quote=self.quote_reader(order.ticker.value)
            from .kis_broker import KISBroker
            refreshed=KISBroker._regate_order(order,snapshot)
            if refreshed.quantity!=order.quantity:
                raise SubmissionDenied('EXACT_PROOF_QUANTITY_CHANGED')
            from .kis_order import KisOrderAdapter, snap_to_tick
            price=snap_to_tick(order.limit_price.amount,side=order.side)
            prepared=(self.adapter.prepare_order_cash(account=request.account,order=order,snapped_price=price)
                if isinstance(self.adapter,KisOrderAdapter) else None)
            with self.authority.admit(order,scope,ids[2],ids[3],lease,(snapshot,quote)) as admission:
                self._active=(admission,order,ids[1],lease,snapshot,quote)
                self.post_kwargs=(dict(prepared_order=prepared,submission_entry=FinalPostEntry(
                    self.authority,admission,self.adapter,request.account,order,price,prepared,ids[1]))
                    if prepared is not None else {})
                try: yield admission
                finally: self._active=None;self.post_kwargs={}
        finally:
            if lease is not None: lease.release()
            conn.close()

    def verify_attempt(self):
        if self._active is None:
            raise SubmissionDenied('ACTIVE_PROOF_ADMISSION_REQUIRED')
        admission,order,origin,lease,snapshot,quote=self._active
        self.authority.verify_attempt(admission,order,origin,lease=lease,fresh_evidence=(snapshot,quote))
