"""Exact-date schedule hints and independent, append-only observer obligations.

These reducers never grant account, dispatch or order authority. The observer can
publish before the trading worker has ever run; missing history stays UNKNOWN.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Callable

from .control_store import ControlReader, EffectiveControl
from .service_config import ServiceSettings, load_service_settings, protected_file
from .service_models import (AppliedControl, ExpectationInputs, InstallationScope, KST,
    LogicalJobKey, OwnerLoginEvidence, ServiceExpectation, ServiceScope, SessionEvidence)
from .service_store import ExpectationWriter, _owned
from .session_evidence import load_session_evidence, unknown_session


def local(now: datetime) -> datetime:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('aware service clock required')
    return now.astimezone(KST)


def slot(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=KST)


@dataclass(frozen=True)
class ScheduledJob:
    key: LogicalJobKey
    due_at: datetime
    deadline_at: datetime
    state: str
    reason_code: str
    slot_at: datetime | None = None
    remaining_tickers: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScheduleDecision:
    due: tuple[ScheduledJob, ...] = ()
    blocked: tuple[ScheduledJob, ...] = ()
    missed: tuple[ScheduledJob, ...] = ()
    reconcile_only: bool = False
    terminal: bool = False


class ServiceSchedule:
    def __init__(self, scope: ServiceScope):
        self.scope = ServiceScope.model_validate(scope)

    def tick(self, now, session: SessionEvidence, controls, saved_jobs) -> ScheduleDecision:
        now = local(now); day = now.date()
        if now >= slot(day, 15, 30):
            return ScheduleDecision(terminal=True, reconcile_only=True)
        rows = {str(r['kind']): r for r in saved_jobs
            if str(r['trading_date_kst']) == str(day)
            and r.get('scope_hash', self.scope.account_scope_hash) == self.scope.account_scope_hash
            and r.get('target', 'mock') == 'mock'}
        def job(kind, hour, minute, end_hour, end_minute):
            return ScheduledJob(LogicalJobKey(scope=self.scope,trading_date_kst=day,kind=kind),
                slot(day,hour,minute),slot(day,end_hour,end_minute),'DUE','CURRENT_SLOT')
        prep=job('PREP',8,50,9,0); daily=job('DAILY',9,10,9,20); risk=job('RISK',9,0,15,30)
        due, blocked, missed = [], [], []
        if (not isinstance(session,SessionEvidence) or session.trading_date_kst != day
                or session.eligibility == 'UNKNOWN' or session.observed_at > now
                or session.effective_at > now or session.reviewed_at > now):
            return ScheduleDecision(blocked=(replace(daily,state='UNKNOWN',reason_code='SESSION_UNKNOWN'),))
        if session.eligibility == 'HOLIDAY': return ScheduleDecision()
        if not isinstance(controls,(AppliedControl,EffectiveControl)):
            return ScheduleDecision(blocked=(replace(daily,state='UNKNOWN',reason_code='CONTROL_UNKNOWN'),))
        applied=controls.applied if isinstance(controls,EffectiveControl) else controls
        if applied.applied_at>now:
            return ScheduleDecision(blocked=(replace(daily,state='UNKNOWN',reason_code='CONTROL_UNKNOWN'),))
        mode=controls.mode
        row=rows.get('DAILY')
        # Terminal/unknown consumed work cannot be manufactured into a new job.
        complete=row is not None and row['state'] in ('COMPLETED','MISSED','PARTIAL','UNKNOWN')
        remaining=tuple(row.get('remaining_tickers',())) if row else ()
        if not complete and now >= daily.deadline_at:
            missed.append(replace(daily,state='PARTIAL' if row else 'MISSED',
                reason_code='UNFINISHED_AT_DEADLINE' if row else 'DAILY_MISSED',remaining_tickers=remaining))
        opening=max(slot(day,9),session.continuous_open)
        cutoff=min(slot(day,15,20),session.continuous_close)
        active=opening <= now < cutoff
        if prep.due_at <= now < prep.deadline_at and 'PREP' not in rows:
            due.append(prep)
        if not complete and daily.due_at <= now < daily.deadline_at:
            if active and mode == 'RUNNING': due.append(replace(daily,remaining_tickers=remaining))
            else: blocked.append(replace(daily,state='BLOCKED',reason_code='CONTROL_STOPPED' if mode!='RUNNING' else 'PRE_OPEN'))
        # One coalesced current minute; never replay an accumulated minute list.
        if opening <= now < risk.deadline_at:
            current=now.replace(second=0,microsecond=0)
            prior=rows.get('RISK',{}).get('last_slot_at')
            if isinstance(prior,str): prior=datetime.fromisoformat(prior)
            if prior is None or current > prior:
                due.append(replace(risk,slot_at=current,reason_code='RECONCILIATION_ONLY'
                    if not active or mode=='KILLED' else 'CURRENT_SLOT'))
        return ScheduleDecision(tuple(due),tuple(blocked),tuple(missed),not active and now>=cutoff)


def derive_expectations(inputs: ExpectationInputs, now: datetime) -> tuple[ServiceExpectation, ...]:
    inputs=ExpectationInputs.model_validate(inputs); now=local(now); day=now.date()
    session=inputs.session; login=inputs.login_evidence
    result=[]
    for scope in inputs.registered_scopes:
        for kind,due,deadline in (('PREP',slot(day,8,50),slot(day,9)),
                ('DAILY',slot(day,9,10),slot(day,9,20)),
                ('RISK',slot(day,9),slot(day,15,30))):
            if kind=='RISK' and session.trading_date_kst==day and session.continuous_open is not None:
                due=max(due,session.continuous_open)
            state,reason='EXPECTED','LOCKED_SCHEDULE'
            if (session.trading_date_kst!=day or session.eligibility=='UNKNOWN'
                    or login.state=='UNKNOWN' or login.owner_uid!=os.getuid()
                    or login.observed_at>now or session.observed_at>now
                    or inputs.controls_observed_at>now or inputs.config_effective_at>now):
                state,reason='UNKNOWN','SOURCE_UNKNOWN'
            elif (not inputs.service_enabled or inputs.mode!='KIS_MOCK'
                    or login.state=='ABSENT' or session.eligibility=='HOLIDAY'):
                state,reason='NOT_EXPECTED','DISABLED_OR_ABSENT_OR_HOLIDAY'
            elif kind=='DAILY' and inputs.effective_controls.mode!='RUNNING':
                state,reason='NOT_EXPECTED','DAILY_CONTROL_STOPPED'
            elif kind=='RISK' and inputs.effective_controls.mode=='KILLED':
                reason='RECONCILIATION_ONLY'
            if due>=deadline:
                state,reason='NOT_EXPECTED','SESSION_AFTER_TERMINAL'
                due=None
            # A present sample cannot retrospectively cover a missed due interval.
            # Earlier persisted obligations survive independently and are read by
            # the observer. A later revision never rewrites those original facts.
            if due is not None and now>=due and any(t>due for t in (inputs.config_effective_at,login.observed_at,
                    session.observed_at,inputs.controls_observed_at)):
                state,reason='UNKNOWN','DUE_HISTORY_UNKNOWN'
            facts=inputs.model_dump(mode='json') | {'scope':scope.model_dump(mode='json'),'kind':kind,'date':str(day)}
            digest=hashlib.sha256(json.dumps(facts,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            effective=max(inputs.config_effective_at,login.effective_at,session.effective_at,inputs.controls_effective_at)
            # Wrong-date session facts must carry no inherited session interval.
            exact=session.trading_date_kst==day
            result.append(ServiceExpectation(expectation_id=digest,scope=scope,trading_date_kst=day,
                kind=kind,state=state,producer_kind='OBSERVER_DERIVED',source_id='observer-schedule',
                source_hash=digest,observed_at=now,effective_at=min(effective,now),
                eligibility=session.eligibility if exact else 'UNKNOWN',
                continuous_open=session.continuous_open if exact else None,
                continuous_close=session.continuous_close if exact else None,due_at=due,deadline_at=deadline,
                config_hash=inputs.config_hash,config_effective_at=min(inputs.config_effective_at,now),
                login_source_id=login.source_id,login_effective_at=min(login.effective_at,now),
                session_source_id=session.source_id,session_source_hash=session.source_hash,
                control_revision=inputs.effective_controls.revision,controls_source_id=inputs.controls_source_id,
                controls_observed_at=min(inputs.controls_observed_at,now),
                controls_effective_at=min(inputs.controls_effective_at,now),reason_code=reason))
    return tuple(result)


class OwnerLoginProbe:
    """Validate the installed bounded OS probe; import and construction perform no OS command."""
    def __init__(self, probe: Callable[[], OwnerLoginEvidence], *, clock,
                 owner_uid=None, monotonic=time.monotonic):
        self.probe,self.clock,self.monotonic=probe,clock,monotonic
        self.owner_uid=os.getuid() if owner_uid is None else owner_uid

    def observe_owner_gui(self):
        now=local(self.clock()); started=self.monotonic()
        try:
            value=self.probe()
            if type(value) is not OwnerLoginEvidence: raise ValueError('typed bounded login evidence required')
            value=OwnerLoginEvidence.model_validate(value)
            if (value.owner_uid!=self.owner_uid or not 0<=self.monotonic()-started<=1
                    or not 0<=(now-value.observed_at).total_seconds()<=120
                    or value.effective_at>now): raise ValueError('current owner GUI evidence required')
            return value
        except Exception:
            return OwnerLoginEvidence(owner_uid=self.owner_uid,gui_session_id=None,
                source_id='owner-gui-unknown',observed_at=now,effective_at=now,state='UNKNOWN')


class ExpectationProducer:
    """Non-trading observer root: protected source reads plus the narrow writer only."""
    def __init__(self, settings: ServiceSettings, *, config_path: Path, login_probe,
                 control_reader: ControlReader, writer: ExpectationWriter, clock):
        if type(settings) is not ServiceSettings or type(control_reader) is not ControlReader or type(writer) is not ExpectationWriter:
            raise TypeError('registered observer capabilities required')
        self.settings,self.config_path=settings,Path(config_path)
        self.probe=OwnerLoginProbe(login_probe.observe_owner_gui,clock=clock)
        self.controls,self.writer,self.clock=control_reader,writer,clock

    def publish(self):
        now=local(self.clock()); failures=[]; settings=self.settings
        config_hash='0'*64; effective=now
        try:
            settings=load_service_settings(self.config_path)
            if (settings.registered_scopes!=self.settings.registered_scopes
                    or settings.validate_topology()!=self.settings.validate_topology()):
                raise ValueError('registered observer topology changed')
            config_hash=hashlib.sha256(settings.model_dump_json().encode()).hexdigest()
            effective=datetime.fromtimestamp(protected_file(self.config_path).stat().st_mtime,timezone.utc)
            if effective>now: raise ValueError('config observation rollback')
        except (ValueError,OSError): failures.append(('CONFIG','service-config','CONFIG_UNKNOWN'))
        login=self.probe.observe_owner_gui()
        if login.state=='UNKNOWN': failures.append(('LOGIN',login.source_id,'LOGIN_UNKNOWN'))
        session=load_session_evidence(settings.session_evidence_path,now.date(),lambda:now)
        if session.eligibility=='UNKNOWN': failures.append(('SESSION',session.source_id,'SESSION_UNKNOWN'))
        control=AppliedControl(revision=0,mode='PAUSED',request_id=None,applied_at=now,safety_evidence_ids=())
        controls_id='control-unknown'; controls_at=now
        try:
            current=self.controls.effective_state()
            requests=self.controls.list_requests(limit=100)
            applications=self.controls.list_applications(limit=100)
            if self.controls.effective_state()!=current: raise ValueError('control read race')
            latest=next((r for r in requests if r['acceptance_revision']==current.acceptance_revision),None)
            controls_id=latest['request_id'] if latest else 'control-owner-setup'
            controls_at=max([current.applied.applied_at]+[
                datetime.fromtimestamp(r['requested_at'],timezone.utc) for r in requests
                if r['acceptance_revision']>current.applied.revision])
            if controls_at>now or not applications: raise ValueError('control history unknown')
            if current.acceptance_revision and latest is None: raise ValueError('revision source missing')
            control=AppliedControl(revision=current.acceptance_revision,mode=current.mode,
                request_id=latest['request_id'] if latest else None,applied_at=controls_at,
                safety_evidence_ids=current.applied.safety_evidence_ids)
        except (ValueError,OSError,sqlite3.DatabaseError): failures.append(('CONTROL',controls_id,'CONTROL_UNKNOWN'))
        values=ExpectationInputs(registered_scopes=self.settings.registered_scopes,
            service_enabled=settings.service_enabled,mode=settings.mode,config_hash=config_hash,
            config_effective_at=min(effective,now),login_evidence=login,session=session,
            effective_controls=control,control_scope=InstallationScope(registered_scopes=self.settings.registered_scopes),
            controls_source_id=controls_id,controls_observed_at=now,controls_effective_at=controls_at)
        records=derive_expectations(values,now)
        if failures:
            records=tuple(r.model_copy(update={'state':'UNKNOWN','reason_code':'SOURCE_UNKNOWN'}) for r in records)
        for r in records: self.writer.record_derived(r)
        for scope in self.settings.registered_scopes:
            for kind,source,reason in failures:
                self.writer.record_source_health(scope=scope,trading_date_kst=now.date(),
                    source_kind=kind,source_id=source,state='UNKNOWN',reason_code=reason,observed_at=now)
        return records


class ExpectationHistoryReader:
    """Query-only saved observer history. No migration or mutable collaborator."""
    def __init__(self, settings: ServiceSettings):
        self.settings=settings

    def for_date(self, day: date | None = None):
        registration=self.settings.model_copy(update={'service_enabled':False,'mode':'DISABLED'})
        path=protected_file(registration.validate_topology()[0])
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
        try:
            with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=1) as conn:
                conn.execute('PRAGMA query_only=ON'); conn.execute('BEGIN'); _owned(conn)
                where="producer_kind='OBSERVER_DERIVED'"; params=()
                if day is not None: where+=' AND trading_date_kst=?'; params=(str(day),)
                rows=conn.execute(f'SELECT evidence_json FROM service_expectations WHERE {where} ORDER BY observed_at,rowid LIMIT 10001',params).fetchall()
                if len(rows)>10000: raise ValueError('bounded expectation history exceeded')
                current=path.stat(); saved=os.fstat(fd)
                if (current.st_dev,current.st_ino)!=(saved.st_dev,saved.st_ino): raise ValueError('history source replaced')
                return tuple(ServiceExpectation.model_validate_json(r[0]) for r in rows)
        finally: os.close(fd)

    def absent_obligations(self, now: datetime, saved_jobs):
        now=local(now); chosen={}
        for r in self.for_date():
            # Only prior, attributable observer samples can prove the due interval.
            if r.due_at is not None and r.observed_at<=r.due_at and r.effective_at<=r.due_at:
                chosen[(r.scope,r.trading_date_kst,r.kind)]=r
        existing={(str(r['scope_hash']),str(r['target']),str(r['trading_date_kst']),str(r['kind'])) for r in saved_jobs}
        return tuple(r for r in chosen.values() if r.state=='EXPECTED'
            and now>=(r.due_at+timedelta(seconds=120) if r.kind=='RISK' else r.deadline_at)
            and (r.scope.account_scope_hash,r.scope.execution_target,str(r.trading_date_kst),r.kind) not in existing)
