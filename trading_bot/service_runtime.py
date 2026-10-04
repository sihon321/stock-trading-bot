"""Recovery-first leader and spawned, broker-free, single-shot provider worker.

The CLI composition root binds data and concrete account trading collaborators.
No callback returning a truth flag can grant mutation or bypass the final POST.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
import multiprocessing
import signal
import time
from typing import Callable, Protocol

from pydantic import Field, SecretStr

from .account_work import AccountWorkBudget, AccountWorkTimeout, BoundedAccountWork
from .config import LLMProviderName
from .control_runtime import ControlApplier
from .control_store import ControlStore
from .domain import Decision, LLMSignal
from .llm_provider import ProviderDispatchAdmission, build_single_shot_llm_provider
from .market_cycle import MarketCyclePolicy
from .mutation_lease import LeaseBusyError, LeaseRecoveryBlocked
from .portfolio_store import (claim_daily_dispatch, finalize_daily_dispatch,
    load_daily_dispatch, recover_daily_dispatches, start_daily_evaluation)
from .service_activation import OfflineActivationAuthority
from .service_composition import ServiceComposition
from .service_config import ServiceSettings
from .service_leader import ServiceLeader
from .service_models import (DailyDispatchEnvelope, ExpectationInputs, KST, LogicalJobKey,
    ProviderCallAdmission, ServiceContract)
from .service_schedule import ServiceSchedule, derive_expectations, local, slot
from .service_store import ProviderAdmissionWriter, ServiceJournal


class RuntimeBlocked(RuntimeError):
    pass


@dataclass(frozen=True)
class DailyInput:
    ticker: str
    provenance: tuple[str, ...]
    envelope: DailyDispatchEnvelope

    def __post_init__(self):
        if (len(self.ticker)!=6 or not self.ticker.isdigit() or not self.provenance
                or not set(self.provenance)<={'HELD','SCREENED'}
                or type(self.envelope) is not DailyDispatchEnvelope):
            raise ValueError('typed exact daily input required')


class DailyInputSource(Protocol):
    """Collect input outside account authority; first saved input always wins."""
    def collect(self, day, held_tickers: tuple[str, ...]) -> tuple[DailyInput, ...]: ...


class ProviderSettings(ServiceContract):
    """Only provider credentials/options cross spawn. No KIS account/settings."""
    llm_provider: LLMProviderName
    api_key: SecretStr | None = Field(default=None, repr=False)
    anthropic_auth_token: SecretStr | None = None
    anthropic_model: str = 'claude-opus-4-8'
    anthropic_temperature: float = 0
    openai_model: str = 'gpt-4.1'
    openai_temperature: float = 0
    codex_cli_binary: str = 'codex'
    codex_cli_model: str | None = None
    codex_cli_temperature: float = 0
    codex_cli_extra_args: tuple[str, ...] = ()

    @property
    def active_llm_api_key(self):
        if self.api_key is None: raise RuntimeBlocked('PROVIDER_CREDENTIAL_MISSING')
        return self.api_key


@dataclass(frozen=True)
class ProviderChildFactory:
    settings: ProviderSettings
    offline_authority: OfflineActivationAuthority | None = None
    transport_handler: Callable | None = field(default=None, repr=False)
    before_entry: Callable | None = field(default=None, repr=False)

    def __post_init__(self):
        if type(self.settings) is not ProviderSettings:
            raise TypeError('provider-only settings required')
        if (self.transport_handler is not None or self.before_entry is not None) and type(self.offline_authority) is not OfflineActivationAuthority:
            raise ValueError('injected child transport requires explicit temporary authority')

    def build(self):
        import httpx
        transport=httpx.MockTransport(self.transport_handler) if self.transport_handler else None
        # Actual Codex remains closed until its single-shot contract is verified.
        return build_single_shot_llm_provider(self.settings,transport=transport)


def _provider_child(factory, envelope, admission, sender):
    """Spawn args contain no leader, account lease/DB, broker or account secret."""
    try:
        if factory.before_entry: factory.before_entry()
        provider=factory.build()
        result=provider.generate_signal_from_envelope(envelope,admission)
        from .signal_parser import parse_signal
        signal_value=parse_signal(json.dumps({'decision':result.decision.value,
            'confidence':result.confidence,'reason':result.reason})).signal
        sender.send(('SIGNAL',signal_value.decision.value,signal_value.confidence,signal_value.reason))
    except BaseException:
        # Never serialize vendor exceptions, credentials or arbitrary response text.
        sender.send(('UNKNOWN','HOLD',0.,'LLM_UNAVAILABLE'))
    finally: sender.close()


@dataclass
class ProviderChild:
    process: object
    receiver: object
    dispatch: dict
    deadline: float
    result: tuple | None = None


@dataclass(frozen=True)
class AccountTradingBinding:
    """Actual account execution contract, bound by the installed CLI root.

    broker_factory must return a concrete KISBroker with concrete
    SubmissionAuthority and committed audit sink. It receives fresh account
    authority, rather than returning an authorization boolean.
    """
    broker_factory: Callable
    quote_reader: Callable
    execution_config: object
    risk_config: object
    daily_loss_state: object
    audit_cycle: Callable

    def __post_init__(self):
        from .execution import ExecutionConfig
        from .risk import DailyLossState, RiskConfig
        if (type(self.execution_config) is not ExecutionConfig or type(self.risk_config) is not RiskConfig
                or type(self.daily_loss_state) is not DailyLossState
                or not .8<=self.execution_config.buy_confidence_threshold<=1
                or not all(callable(c) for c in (self.broker_factory,self.quote_reader,self.audit_cycle))):
            raise TypeError('typed production execution and risk contracts required')

    def _broker(self, runtime, lease, current, budget):
        from .kis_broker import KISBroker
        from .submission_authority import OwnedActivationCheck, SubmissionAuthority
        broker=self.broker_factory(lease,current,budget)
        if type(broker) is not KISBroker or type(broker._submission_authority) is not SubmissionAuthority:
            raise RuntimeBlocked('CONCRETE_FINAL_AUTHORITY_REQUIRED')
        if not callable(broker._evidence_sink):
            raise RuntimeBlocked('COMMITTED_ORDER_AUDIT_REQUIRED')
        authority=broker._submission_authority
        if authority.store.settings!=runtime.settings or authority.policy is not runtime.policy:
            raise RuntimeBlocked('REGISTERED_FINAL_AUTHORITY_REQUIRED')
        if runtime.offline_authority is None and (not authority.unattended
                or type(authority.activation_check) is not OwnedActivationCheck):
            raise RuntimeBlocked('OWNED_UNATTENDED_ACTIVATION_REQUIRED')
        return broker

    def daily(self, runtime, lease, current, budget, dispatch, saved_signal):
        from .cli import _LeaseGuardedBroker
        from .domain import Money, Position, Ticker
        from .execution import execute_signal_cycle
        broker=self._broker(runtime,lease,current,budget)
        quote=self.quote_reader(dispatch['ticker'])
        if quote.price is None: raise RuntimeBlocked('CURRENT_QUOTE_UNAVAILABLE')
        class FreshSnapshotBroker(_LeaseGuardedBroker):
            def get_position(self,ticker):
                holding=next((h for h in current.holdings if h.ticker==ticker.value),None)
                return None if holding is None else Position(ticker,holding.total_quantity,Money(holding.average_price))
        guarded=FreshSnapshotBroker(broker,lease,portfolio_refresh=runtime.work.snapshot_reader,
            cycle_snapshot_id=current.snapshot_id,evaluation_id=dispatch['evaluation_id'],work_budget=budget)
        raw=json.dumps({'decision':saved_signal.decision.value,'confidence':saved_signal.confidence,'reason':saved_signal.reason})
        result=execute_signal_cycle(raw,Ticker(dispatch['ticker']),quote.price,
            float(current.account.available_cash),guarded,self.execution_config,self.risk_config,
            self.daily_loss_state,dry_run=False,origin_run_id=lease.cycle_id)
        self.audit_cycle(result,dispatch['evaluation_id'],lease.cycle_id)
        return result

    def risk(self, runtime, lease, current, budget):
        from .intraday import run_intraday_check
        from .exit_manager import submit_exit
        from .portfolio_store import append_watch_iteration
        broker=self._broker(runtime,lease,current,budget)
        def submit(candidate,price):
            with budget.submission_guard(lease,timeout_seconds=runtime.settings.post_timeout_seconds):
                return submit_exit(candidate,broker=broker,limit_price=price,
                    portfolio_refresh=runtime.work.snapshot_reader,lease_guard=lease,
                    cycle_snapshot_id=current.snapshot_id,origin_run_id=lease.cycle_id,
                    submission_authority=broker._submission_authority)
        return run_intraday_check(clock=runtime.clock,snapshot_reader=lambda:current,
            quote_reader=lambda ticker:self.quote_reader(ticker).price,risk_config=self.risk_config,
            lease=lease,exit_submitter=submit,
            audit_sink=lambda result:append_watch_iteration(runtime.work.conn,result,observed_at=runtime.clock()),
            mutation_guard=lambda:lease.assert_active_owner(observed_at=runtime.clock()),
            work_budget=budget,policy=runtime.policy)


class ServiceRuntime:
    def __init__(self, *, settings: ServiceSettings, journal: ServiceJournal, controls: ControlStore,
                 composition: ServiceComposition, account_work: BoundedAccountWork,
                 policy: MarketCyclePolicy, daily_inputs: DailyInputSource,
                 provider_factory: ProviderChildFactory, trading: AccountTradingBinding | None = None,
                 clock=lambda:datetime.now(timezone.utc), monotonic=time.monotonic,
                 offline_authority=None, activation_check=None, barrier=lambda name:None):
        if (type(settings) is not ServiceSettings or type(journal) is not ServiceJournal
                or type(controls) is not ControlStore or type(account_work) is not BoundedAccountWork
                or type(composition) is not ServiceComposition or type(provider_factory) is not ProviderChildFactory
                or journal.settings!=settings or controls.settings!=settings):
            raise TypeError('concrete registered runtime collaborators required')
        if trading is not None and type(trading) is not AccountTradingBinding:
            raise TypeError('concrete trading binding required')
        self.settings,self.journal,self.controls=settings,journal,controls
        self.composition,self.work,self.policy=composition,account_work,policy
        self.daily_inputs,self.provider_factory,self.trading=daily_inputs,provider_factory,trading
        self.clock,self.monotonic,self.offline_authority,self.barrier=clock,monotonic,offline_authority,barrier
        self.activation_check=activation_check
        self.scope=composition.scope or settings.registered_scopes[0]
        self.leader=ServiceLeader(settings,journal=journal,scope=self.scope)
        self.schedule=ServiceSchedule(self.scope)
        self.state='UNSTARTED'; self.child=None; self.last_dispatch_id=None
        self.no_new_dispatch=False; self.last_heartbeat=None; self.fresh=None
        self.inputs=(); self.last_risk_slot=None; self.applier=None
        self.active_day=None

    def _validate(self):
        self.settings.validate_topology()
        if (not self.settings.service_enabled or self.settings.mode!='KIS_MOCK'
                or self.scope not in self.settings.registered_scopes
                or self.work.account_scope_hash!=self.scope.account_scope_hash
                or self.composition.mode!='KIS_MOCK' or self.composition.execution_target!='mock'
                or not self.composition.activation.allowed):
            raise RuntimeBlocked('UNATTENDED_ACTIVATION_BLOCKED')
        if self.composition.activation.authority=='OFFLINE_ONLY':
            if type(self.offline_authority) is not OfflineActivationAuthority:
                raise RuntimeBlocked('OFFLINE_CAPABILITY_REQUIRED')
            self.offline_authority.assert_settings(self.settings)
        elif (self.composition.activation.authority!='OWNED_KIS_OBSERVED'
                or self.trading is None or not callable(self.composition.guarded_broker_builder)):
            raise RuntimeBlocked('CONCRETE_PRODUCTION_BINDING_REQUIRED')
        if self.offline_authority is None:
            from .submission_authority import OwnedActivationCheck
            if type(self.activation_check) is not OwnedActivationCheck or self.activation_check.settings!=self.settings:
                raise RuntimeBlocked('CURRENT_OWNED_ACTIVATION_REQUIRED')
            current=self.activation_check()
            if (not current.allowed or current.authority!='OWNED_KIS_OBSERVED'
                    or current.reason_codes==('SCOPED_FREEZE_CHECK_REQUIRED',)):
                # Initial activation retains 15-06's conservative freeze denial.
                raise RuntimeBlocked('CURRENT_ACTIVATION_BLOCKED')

    def _generation(self,state):
        self.leader.assert_owner()
        with self.journal.connection() as conn:
            conn.execute('UPDATE service_generations SET state=? WHERE generation_id=?',
                (state,self.leader.generation_id))
        self.leader.state=state

    def start(self):
        self._validate(); self.leader.acquire(); self._generation('RECOVERY_ONLY')
        self.state='RECOVERY_ONLY'
        self.applier=ControlApplier(self.controls.service_capability(self.leader),clock=self.clock)
        self.applier.apply_pending()  # restrictive controls apply even if recovery fails
        try:
            self.recover()
        except (LeaseBusyError,LeaseRecoveryBlocked,AccountWorkTimeout,RuntimeError):
            self.state='RECOVERY_BLOCKED'; self.heartbeat(force=True)
            return self.state
        self._generation('RUNNING'); self.state='RUNNING'; self.heartbeat(force=True)
        self.active_day=local(self.clock()).date()
        return self.state

    def recover(self):
        def operation(lease,current,budget):
            lease.assert_active_owner(observed_at=self.clock()); self.fresh=current
            conn=self.work.conn
            dates=tuple(r[0] for r in conn.execute('SELECT DISTINCT trading_date_kst FROM daily_evaluations WHERE account_scope_hash=? AND status=?',
                (self.scope.account_scope_hash,'STARTED')))
            for day_text in dates:
                day=datetime.fromisoformat(day_text).date()
                recover_daily_dispatches(conn,lease=lease,account_scope_hash=self.scope.account_scope_hash,
                    execution_target='mock',trading_date_kst=day,now=self.clock(),deadline=slot(day,9,20))
            self.journal.recover_provider_admissions(observed_at=self.clock())
            self.barrier('RECOVERY_RECONCILED')
        self.work.run(operation)
        self._load_saved_inputs()
        if self.inputs and slot(local(self.clock()).date(),9,10)<=local(self.clock())<slot(local(self.clock()).date(),9,20):
            self._event('DAILY','CLAIMED','RECOVERY_SAVED_INPUTS',tuple(v.ticker for v in self.inputs))
        risk=self.job('RISK')
        if risk:
            for event in reversed(self.journal.list_events(risk['job_id'])):
                slots=[s for s in json.loads(event['source_ids_json']) if s.startswith('risk-slot:')]
                if slots:
                    self.last_risk_slot=datetime.strptime(slots[0][10:],'%Y%m%dT%H%M').replace(tzinfo=KST)
                    break

    def _load_saved_inputs(self):
        day=local(self.clock()).date(); row=self.job('DAILY')
        if row is None or row['universe_json'] is None: self.inputs=(); return
        result=[]
        for ticker in json.loads(row['universe_json']):
            evaluation=self.work.conn.execute('SELECT evaluation_id FROM daily_evaluations WHERE trading_date_kst=? AND ticker=? AND account_scope_hash=?',
                (str(day),ticker,self.scope.account_scope_hash)).fetchone()
            if evaluation is None: continue  # no saved input cannot be recreated on recovery
            dispatch=load_daily_dispatch(self.work.conn,evaluation[0])
            if (dispatch['execution_target']!='mock' or dispatch['envelope_json'] is None
                    or dispatch['dispatch_state']!='NEVER_DISPATCHED'): continue
            envelope=DailyDispatchEnvelope.model_validate_json(dispatch['envelope_json'])
            if envelope.envelope_hash!=dispatch['envelope_hash']: raise RuntimeBlocked('SAVED_INPUT_MISMATCH')
            result.append(DailyInput(ticker,('HELD',) if ticker in {h.ticker for h in self.fresh.holdings} else ('SCREENED',),envelope))
        self.inputs=tuple(result)

    def job(self,kind):
        key=LogicalJobKey(scope=self.scope,trading_date_kst=local(self.clock()).date(),kind=kind)
        return self.journal.load_job(key.logical_id)

    def heartbeat(self,*,force=False):
        now=self.clock()
        if force or self.last_heartbeat is None or (now-self.last_heartbeat).total_seconds()>=30:
            self.journal.heartbeat('service-leader',self.leader.generation_id,
                phase=self.state,observed_at=now)
            self.last_heartbeat=now

    def _event(self,kind,state,reason,source_ids=(),*,day=None):
        key=LogicalJobKey(scope=self.scope,trading_date_kst=day or local(self.clock()).date(),kind=kind)
        row=self.journal.load_job(key.logical_id)
        if row is not None:
            self.journal.append_job_event(row['job_id'],state,reason_code=reason,
                source_ids=source_ids,observed_at=self.clock())

    def _claim(self,job):
        self.journal.claim_job(job.key,due_at=job.due_at,dispatch_deadline_at=job.deadline_at,
            owner_generation=self.leader.generation_id)

    def tick(self, *, expectation_inputs: ExpectationInputs | None = None):
        if self.state in ('UNSTARTED','STOPPED'): raise RuntimeBlocked('RUNTIME_NOT_STARTED')
        self.leader.assert_owner(); self.applier.apply_pending(); self.heartbeat()
        if self.state=='RECOVERY_BLOCKED': return None
        if self.child is not None: self._poll_child()
        now=local(self.clock()); session=self.policy.session_evidence_provider.for_date(now.date())
        controls=self.controls.reader().effective_state(self.scope)
        if self.active_day!=now.date():
            if (session.trading_date_kst!=now.date() or session.eligibility=='UNKNOWN'
                    or any(stamp>now for stamp in (session.observed_at,session.effective_at,session.reviewed_at))):
                changed=self.state!='SESSION_UNKNOWN'; self.state='SESSION_UNKNOWN'
                self.heartbeat(force=changed); return None
            if session.eligibility=='HOLIDAY':
                changed=self.state!='IDLE'; self.state='IDLE'
                self.heartbeat(force=changed); return None
            if self.child is not None:
                # Let the previous consumed call finish/suppress boundedly. New
                # date recovery must not relabel its pending entry UNKNOWN first.
                self.state='RECOVERY_ONLY'; return None
            try:
                self._validate(); self._generation('RECOVERY_ONLY'); self.state='RECOVERY_ONLY'
                self.recover()
            except (Exception,AccountWorkTimeout):
                self.state='RECOVERY_BLOCKED'; self.heartbeat(force=True); return None
            self.active_day=now.date(); self.last_risk_slot=None
            self._generation('RUNNING'); self.state='RUNNING'; self.heartbeat(force=True)
        rows=[]
        for kind in ('PREP','DAILY','RISK'):
            row=self.job(kind)
            if row:
                row['last_slot_at']=self.last_risk_slot if kind=='RISK' else None
                if kind=='DAILY': row['remaining_tickers']=tuple(v.ticker for v in self.inputs)
                rows.append(row)
        decision=self.schedule.tick(now,session,controls,rows)
        if expectation_inputs is not None:
            for e in derive_expectations(expectation_inputs,now):
                self.journal.record_expectation(e.model_copy(update={'producer_kind':'RUNTIME_OBSERVED'}))
        if decision.terminal:
            # Only the risk session ends. Successful launcher exit would disable
            # next-day work under KeepAlive/SuccessfulExit=false.
            if self.state!='IDLE':
                if self.child is not None: self._poll_child(force_unknown=True)
                self._event('RISK','COMPLETED','RISK_SESSION_TERMINAL')
                remaining=self._remaining()
                if remaining:
                    self._event('DAILY','PARTIAL','UNFINISHED_AT_DEADLINE',remaining)
                self.state='IDLE'; self.heartbeat(force=True)
            return decision
        for missed in decision.missed:
            self._claim(missed)
            if self.child is None:
                sources=self._remaining()
                if sources:
                    try:
                        self.work.run(lambda lease,current,budget:recover_daily_dispatches(self.work.conn,
                            lease=lease,account_scope_hash=self.scope.account_scope_hash,execution_target='mock',
                            trading_date_kst=now.date(),now=self.clock(),deadline=slot(now.date(),9,20)))
                    except (Exception,AccountWorkTimeout):
                        self._event('DAILY','UNKNOWN','EXPIRY_RECOVERY_REQUIRED',sources)
                        continue
                self._event('DAILY',missed.state,missed.reason_code,sources)
                self.inputs=()
        # Daily reservation precedes new risk; provider response waits never do.
        for job in decision.due:
            if job.key.kind=='PREP':
                self._claim(job)
                try:
                    if self.composition.prep_read_only is None: raise RuntimeBlocked('PREP_UNWIRED')
                    self.composition.prep_read_only(); self._event('PREP','COMPLETED','PREP_READ_ONLY')
                except Exception: self._event('PREP','UNKNOWN','PREP_UNAVAILABLE')
            elif job.key.kind=='DAILY' and self.child is None and not self.no_new_dispatch:
                self._claim(job)
                try: self._daily(job)
                except LeaseBusyError: self._event('DAILY','CLAIMED','ACCOUNT_BUSY')
                except (Exception,AccountWorkTimeout): self._event('DAILY','UNKNOWN','DAILY_UNAVAILABLE')
            elif job.key.kind=='RISK':
                self._claim(job)
                try:
                    def risk(lease,current,budget):
                        if controls.mode!='KILLED' and self.trading is not None and self.policy.classify(self.clock()).executable:
                            return self.trading.risk(self,lease,current,budget)
                        return current  # explicit reconciliation only, never a mutation grant
                    self.work.run(risk)
                    self.last_risk_slot=job.slot_at
                    self._event('RISK','RUNNING','RECONCILIATION_ONLY' if controls.mode=='KILLED' or job.reason_code=='RECONCILIATION_ONLY'
                        else 'RISK_PROTECTED' if self.trading is not None else 'RISK_RECONCILED',
                        (f"risk-slot:{job.slot_at.strftime('%Y%m%dT%H%M')}",))
                except LeaseBusyError: self._event('RISK','CLAIMED','ACCOUNT_BUSY')
                except (Exception,AccountWorkTimeout): self._event('RISK','BLOCKED','RISK_UNAVAILABLE')
        return decision

    def _daily(self,job):
        row=self.job('DAILY')
        if row['universe_json'] is None:
            if self.work.conn.in_transaction: raise RuntimeBlocked('INPUT_COLLECTION_OWNS_TRANSACTION')
            # Capture exact first inputs outside ownership; sort held before screened.
            held=tuple(h.ticker for h in self.fresh.holdings)
            inputs=tuple(self.daily_inputs.collect(job.key.trading_date_kst,held))
            if len(inputs)>4096 or len({v.ticker for v in inputs})!=len(inputs) or any(type(v) is not DailyInput for v in inputs):
                raise RuntimeBlocked('DAILY_INPUT_UNIVERSE_INVALID')
            order={ticker:index for index,ticker in enumerate(held)}
            inputs=tuple(sorted(inputs,key=lambda v:(0,order[v.ticker]) if v.ticker in order else (1,inputs.index(v))))
            self.journal.commit_universe(row['job_id'],tuple(v.ticker for v in inputs))
            def save(lease,current,budget):
                for value in inputs:
                    budget.assert_available()
                    start_daily_evaluation(self.work.conn,trading_date_kst=job.key.trading_date_kst,
                        ticker=value.ticker,provenance=value.provenance,canonical_input=value.envelope.prompt_bytes,
                        account_scope_hash=self.scope.account_scope_hash,execution_target='mock',envelope=value.envelope,
                        lease=lease,observed_at=self.clock())
                    self.barrier('INPUT_COMMITTED')
            self.work.run(save)
            self.inputs=inputs
        if not self.inputs:
            remaining=self._remaining()
            self._event('DAILY','PARTIAL' if remaining else 'COMPLETED',
                'MISSING_SAVED_INPUTS' if remaining else 'DAILY_TERMINAL',remaining); return
        value=self.inputs[0]
        def reserve(lease,current,budget):
            # Re-read current admission prerequisites before consuming the primary row.
            current_time=local(self.clock())
            session=self.policy.session_evidence_provider.for_date(current_time.date())
            if (current_time.date()!=job.key.trading_date_kst or not job.due_at<=current_time<job.deadline_at
                    or not self.policy.classify(self.clock()).executable
                    or self.controls.reader().effective_state(self.scope).mode!='RUNNING'):
                raise RuntimeBlocked('DAILY_DISPATCH_BLOCKED')
            row=self.work.conn.execute('SELECT evaluation_id FROM daily_evaluations WHERE trading_date_kst=? AND ticker=? AND account_scope_hash=?',
                (str(job.key.trading_date_kst),value.ticker,self.scope.account_scope_hash)).fetchone()
            if row is None: raise RuntimeBlocked('SAVED_INPUT_MISSING')
            dispatch=claim_daily_dispatch(self.work.conn,row[0],lease,self.clock(),job.deadline_at)
            if dispatch is None: raise RuntimeBlocked('DISPATCH_ALREADY_CONSUMED')
            self.barrier('DISPATCH_COMMITTED')
            control=self.controls.reader().effective_state(self.scope)
            writer=self.journal.prepare_provider_admission(ProviderCallAdmission(dispatch_id=dispatch['dispatch_id'],
                evaluation_id=dispatch['evaluation_id'],scope=self.scope,trading_date_kst=job.key.trading_date_kst,
                envelope_hash=dispatch['envelope_hash'],state='PREPARED',reason_code='READY',
                control_revision=control.acceptance_revision,session_source_id=session.source_id,
                observed_at=self.clock(),invocation_started_at=None),consumed_dispatch=dispatch)
            admission=ProviderDispatchAdmission(dispatch_id=dispatch['dispatch_id'],scope=self.scope,
                trading_date_kst=job.key.trading_date_kst,envelope_hash=dispatch['envelope_hash'],
                session_source_id=session.source_id,control_reader=self.controls.reader(),
                session_reader=self.policy.session_evidence_provider.for_date,clock=self.clock,writer=writer,
                lock_factory=self.controls.admission_lock,
                session_fingerprint=hashlib.sha256(session.model_dump_json().encode()).hexdigest())
            return dispatch,admission
        dispatch,admission=self.work.run(reserve)
        self.barrier('ACCOUNT_RELEASED')
        if self.work.conn.in_transaction: raise RuntimeBlocked('CHILD_START_OWNS_TRANSACTION')
        ctx=multiprocessing.get_context('spawn'); receiver,sender=ctx.Pipe(duplex=False)
        process=ctx.Process(target=_provider_child,args=(self.provider_factory,value.envelope,admission,sender))
        try: process.start()
        except BaseException: receiver.close(); sender.close(); raise
        sender.close()
        self.child=ProviderChild(process,receiver,dispatch,self.monotonic()+90)
        self.last_dispatch_id=dispatch['dispatch_id']
        self._event('DAILY','RUNNING','PROVIDER_CHILD_STARTED',(dispatch['evaluation_id'],))
        self.barrier('CHILD_STARTED')

    def _poll_child(self, *, force_unknown=False):
        child=self.child
        if child is None: return
        timed_out=self.monotonic()>=child.deadline
        if child.result is None:
            if force_unknown or timed_out:
                if child.process.is_alive(): child.process.terminate(); child.process.join(timeout=.5)
                if child.process.is_alive(): child.process.kill(); child.process.join(timeout=.5)
                child.result=('UNKNOWN','HOLD',0.,'DISPATCHED_UNKNOWN')
            elif child.receiver.poll():
                try: child.result=child.receiver.recv()
                except EOFError: child.result=('UNKNOWN','HOLD',0.,'DISPATCHED_UNKNOWN')
            elif not child.process.is_alive(): child.result=('UNKNOWN','HOLD',0.,'DISPATCHED_UNKNOWN')
            else: return
        message=child.result
        unknown=message[0]!='SIGNAL'
        saved_signal=LLMSignal(Decision(message[1]),message[2],message[3])
        day=datetime.fromisoformat(child.dispatch['trading_date_kst']).date()
        def finish(lease,current,budget):
            self.barrier('RESPONSE_BEFORE_FINALIZATION')
            # A crash after the final signal commit cannot repeat execution.
            # Existing final POST intents are checked by the concrete broker;
            # this parent nevertheless never calls an execution wrapper twice.
            prior=load_daily_dispatch(self.work.conn,child.dispatch['evaluation_id'])
            if prior['status']=='FINALIZED': return
            finalize_daily_dispatch(self.work.conn,child.dispatch['evaluation_id'],lease=lease,now=self.clock(),
                action=saved_signal.decision.value,confidence=saved_signal.confidence,
                reason_code='LLM_UNAVAILABLE' if unknown else 'SIGNAL_FINALIZED',unknown=unknown,
                signal_reason=None if unknown else saved_signal.reason)
            # Signal completion after 09:20 is allowed; every POST still rechecks
            # current controls, absolute cutoff, quote and immutable intent.
            if (not unknown and self.trading is not None and not self.no_new_dispatch
                    and local(self.clock()).date()==day):
                self.trading.daily(self,lease,current,budget,child.dispatch,saved_signal)
        try: self.work.run(finish)
        except (Exception,AccountWorkTimeout):
            self._event('DAILY','UNKNOWN','RESPONSE_RECOVERY_REQUIRED',(child.dispatch['evaluation_id'],),day=day)
            return  # consumed primary row stays unknown; no provider replay
        admission=self.journal.load_provider_admission(child.dispatch['dispatch_id'])
        if admission is not None and admission.state=='IN_FLIGHT':
            writer=ProviderAdmissionWriter(self.journal,admission.dispatch_id,admission.scope,admission.envelope_hash)
            writer.transition_prepared('UNKNOWN' if unknown else 'FINISHED',reason_code='DISPATCHED_UNKNOWN' if unknown else 'RESPONSE_SAVED',
                observed_at=self.clock(),invocation_started_at=admission.invocation_started_at)
        child.process.join(timeout=.1); child.receiver.close()
        self.child=None; self.inputs=tuple(v for v in self.inputs if v.ticker!=child.dispatch['ticker'])
        self._event('DAILY','RUNNING' if self.inputs else 'UNKNOWN' if unknown else 'COMPLETED',
            'DAILY_REMAINING' if self.inputs else 'DISPATCHED_UNKNOWN' if unknown else 'DAILY_TERMINAL',
            tuple(v.ticker for v in self.inputs),day=day)

    def _remaining(self):
        row=self.job('DAILY')
        if row is None or row['universe_json'] is None: return ()
        day=local(self.clock()).date(); result=[]
        for ticker in json.loads(row['universe_json']):
            saved=self.work.conn.execute('SELECT status FROM daily_evaluations WHERE trading_date_kst=? AND ticker=? AND account_scope_hash=?',
                (str(day),ticker,self.scope.account_scope_hash)).fetchone()
            if saved is None or saved[0]!='FINALIZED': result.append(ticker)
        return tuple(result)

    def stop(self):
        if self.state in ('UNSTARTED','STOPPED'): return
        self.no_new_dispatch=True; self.state='STOPPING'; self.heartbeat(force=True)
        deadline=self.monotonic()+self.settings.shutdown_timeout_seconds
        previous_budget=self.work.budget_factory
        def shutdown_budget():
            remaining=min(29.,deadline-self.monotonic())
            if remaining<=1: raise AccountWorkTimeout('shutdown account budget exhausted')
            return AccountWorkBudget(seconds=remaining,cleanup_seconds=min(10.,remaining/3),monotonic=self.monotonic)
        self.work.budget_factory=shutdown_budget
        try:
            if self.child is not None: self._poll_child(force_unknown=True)
            if self.child is not None:
                self.journal.recover_provider_admissions(observed_at=self.clock())
                self.child.receiver.close(); self.child=None
            self._event('RISK','COMPLETED','SERVICE_STOPPED')
            if self.job('DAILY') and self.job('DAILY')['state'] not in ('COMPLETED','MISSED','PARTIAL','UNKNOWN'):
                self._event('DAILY','PARTIAL','SERVICE_STOPPED',tuple(v.ticker for v in self.inputs))
        finally:
            self.work.budget_factory=previous_budget
            self.leader.close(clean_stop=True); self.state='STOPPED'

    def successor(self):
        return type(self)(settings=self.settings,journal=self.journal,controls=self.controls,
            composition=self.composition,account_work=self.work,policy=self.policy,daily_inputs=self.daily_inputs,
            provider_factory=self.provider_factory,trading=self.trading,clock=self.clock,monotonic=self.monotonic,
            offline_authority=self.offline_authority,activation_check=self.activation_check,barrier=self.barrier)

    def run(self, *, wait=time.sleep):
        """Main-thread account worker; timer wakeups only, no sleep owns authority."""
        previous=signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGTERM,lambda signum,frame:setattr(self,'no_new_dispatch',True))
        try:
            if self.state=='UNSTARTED': self.start()
            while self.state!='STOPPED':
                if self.no_new_dispatch: self.stop(); break
                self.tick()
                if self.state!='STOPPED': wait(min(1.,30.))
        finally:
            self.stop(); signal.signal(signal.SIGTERM,previous)
