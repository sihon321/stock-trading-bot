"""Bounded shadow scheduling. Only this path dispatches provider observations."""
from __future__ import annotations
import time
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from dataclasses import dataclass
from .shadow_models import *
from .shadow_store import ShadowJournal
from .shadow_providers import build_shadow_provider, validate_provider_profile
from .shadow_inputs import shadow_code_identity


@dataclass(frozen=True)
class ShadowExecution:
    manifest: ShadowManifest
    run_id: str
    status: str
    observations: tuple
    events: tuple


def _attributed(o,m,run_id,a):
    if not isinstance(o,ShadowObservation): raise ShadowInputError('INVALID_PROVIDER_OBSERVATION')
    return ShadowObservation.model_validate({**o.model_dump(), 'spec_id':m.spec_id,'run_id':run_id,**{k:a[k] for k in ('attempt_id','unit_id','variant_id','snapshot_id','repetition','retry_of')}})


def _unknown(v,code):
    return ShadowObservation(provider=v.provider,requested_model=v.model,status='TIMEOUT_UNKNOWN',validation_code=code,output_complete=False)


def _execute(manifest,journal_path,*,resume=False,retry_of=None,provider_factory=build_shadow_provider,cancel_event=None,fault=None):
    m=ShadowManifest.model_validate(manifest.model_dump())
    if m.code_content_hash!=shadow_code_identity(): raise ShadowInputError('SHADOW_CODE_MISMATCH')
    test_injection=provider_factory is not build_shadow_provider
    for v,p in zip(m.variants,m.pricing): validate_provider_profile(v,p,allow_synthetic=test_injection)
    providers={};status='COMPLETE'
    with ShadowJournal(journal_path,m,resume=resume) as journal:
        if resume: journal.recover_unknown_attempts()
        attempts,_=journal.read_shadow_evidence()
        if any(a['charge'].get('breach') for a in attempts.values()): status='ACCOUNTING_BREACH'
        schedule=[]
        if retry_of:
            old=attempts.get(retry_of)
            if old is None or old['observation'] is None or old['observation'].status=='SUCCESS': raise ShadowInputError('INVALID_RETRY_LINK')
            schedule=[[{k:old[k] for k in ('unit_id','variant_id','snapshot_id','repetition')}|{'retry_of':retry_of}]]
        else:
            seen={(a['unit_id'],a['variant_id'],a['repetition']) for a in attempts.values()}
            for s in m.snapshots:
                if not s.eligible: continue
                group=[dict(unit_id=s.unit_id,variant_id=v.variant_id,snapshot_id=s.snapshot_id,repetition=r,retry_of=None) for r in range(m.limits.repetitions) for v in m.variants if (s.unit_id,v.variant_id,r) not in seen]
                if group:schedule.append(group)
        snapshots={s.unit_id:s for s in m.snapshots}; variants={v.variant_id:(v,p) for v,p in zip(m.variants,m.pricing)}
        executor=ThreadPoolExecutor(max_workers=m.limits.concurrency)
        try:
            for group in schedule:
                if status!='COMPLETE':break
                if cancel_event and cancel_event.is_set():status='INTERRUPTED';break
                # Construction remains lazy; no credential validation on finalized resume.
                for spec in group:
                    v,p=variants[spec['variant_id']]
                    if v.variant_id not in providers: providers[v.variant_id]=provider_factory(v,p)
                if fault:fault('before_intent',journal)
                try: started=journal.record_dispatch_started(group)
                except ShadowInputError as exc:
                    if str(exc) not in ('BUDGET_EXHAUSTED','ACCOUNTING_BREACH'):raise
                    status=str(exc);break
                if fault:fault('after_intent',journal)
                pending={}
                for a in started:
                    v,_=variants[a['variant_id']]
                    pending[executor.submit(providers[v.variant_id].observe,snapshots[a['unit_id']],v)]=a
                drain_until=None
                while pending:
                    try:
                        if cancel_event and cancel_event.is_set():status='INTERRUPTED'
                        if status in ('INTERRUPTED','ACCOUNTING_BREACH') and drain_until is None:
                            drain_until=time.monotonic()+60
                            for future in pending:future.cancel()
                        ready,_=wait(pending,timeout=.05,return_when=FIRST_COMPLETED)
                        if drain_until is not None and time.monotonic()>=drain_until:ready=set(pending)
                        for future in ready:
                            a=pending.pop(future);v,_=variants[a['variant_id']]
                            if future.cancelled() or not future.done(): o=_unknown(v,'CANCELLED_AFTER_INTENT')
                            else:
                                try:o=future.result()
                                except KeyboardInterrupt:status='INTERRUPTED';o=_unknown(v,'INTERRUPTED_PROVIDER')
                                except Exception:o=ShadowObservation(provider=v.provider,requested_model=v.model,status='PROVIDER_ERROR',validation_code='PROVIDER_OBSERVATION_FAILED',output_complete=False)
                            journal.record_observation(_attributed(o,m,journal.run_id,a))
                            if fault:fault('after_observation',journal)
                            current,_=journal.read_shadow_evidence()
                            if any(x['charge'].get('breach') for x in current.values()):status='ACCOUNTING_BREACH'
                    except KeyboardInterrupt:status='INTERRUPTED'
            attempts,events=journal.read_shadow_evidence()
            if any(a['observation'] is None for a in attempts.values()): raise ShadowInputError('UNFINALIZED_DISPATCH')
            if status=='COMPLETE' and (not m.snapshots or any(a['observation'].status=='TIMEOUT_UNKNOWN' for a in attempts.values())): status='PARTIAL'
            observations=tuple(a['observation'] for a in attempts.values())
            return ShadowExecution(m,journal.run_id,status,observations,tuple(events))
        finally:
            executor.shutdown(wait=False,cancel_futures=True)
            for provider in providers.values():
                if hasattr(provider,'close'):provider.close()


def run_shadow(manifest,journal_path,**kwargs): return _execute(manifest,journal_path,**kwargs)
def resume_shadow(manifest,journal_path,**kwargs): return _execute(manifest,journal_path,resume=True,**kwargs)
def request_shadow_retry(manifest,journal_path,attempt_id,**kwargs): return _execute(manifest,journal_path,resume=True,retry_of=attempt_id,**kwargs)
