import threading
import time
import pytest
from trading_bot.shadow_runner import *
from trading_bot.shadow_models import ShadowLimits, ShadowManifest,ShadowUsage
from trading_bot.shadow_inputs import prepare_shadow_manifest
from test_shadow_models import variant,pricing
from test_shadow_inputs import bundle


def manifest(**limits):
    b=bundle();return prepare_shadow_manifest(b,[variant()],[pricing()],start=b.calendar[5].session,limits=ShadowLimits(sample_limit=3,**limits))


class Fake:
    def __init__(self,calls,status='SUCCESS',cancel=None):self.calls=calls;self.status=status;self.cancel=cancel
    def observe(self,s,v):
        self.calls.append((s.unit_id,v.variant_id,s.snapshot_id))
        if self.cancel:self.cancel.set()
        return ShadowObservation(provider=v.provider,requested_model=v.model,returned_model=v.model,status=self.status,validation_code='FIXTURE',raw_output='{"decision":"HOLD","confidence":0.4,"reason":"fixture"}' if self.status=='SUCCESS' else 'bad',usage=ShadowUsage(input_tokens=10,output_tokens=5,total_tokens=15))


def test_end_to_end_and_finalized_resume_reuses_outcomes(tmp_path):
    m=manifest();calls=[];factory=lambda v,p:Fake(calls)
    run=run_shadow(m,tmp_path/'s.db',provider_factory=factory)
    assert run.status=='COMPLETE' and len(calls)==3 and len(run.observations)==3
    resumed=resume_shadow(m,tmp_path/'s.db',provider_factory=lambda *a:pytest.fail('no construction on finalized resume'))
    assert resumed==run


def test_group_budget_stops_calls(tmp_path):
    m=manifest(max_attempts=1);calls=[]
    run=run_shadow(m,tmp_path/'s.db',provider_factory=lambda v,p:Fake(calls))
    assert run.status=='BUDGET_EXHAUSTED' and len(calls)==1 and len(run.observations)==1


def test_paired_inputs_and_bounded_concurrency(tmp_path):
    b=bundle();v=variant();v2=ShadowVariant.model_validate({**v.model_dump(),'prompt_version':'2','variant_id':''})
    m=prepare_shadow_manifest(b,[v,v2],[pricing(),pricing()],start=b.calendar[5].session,limits=ShadowLimits(sample_limit=3,concurrency=2))
    calls=[];guard=threading.Lock();current=[0,0]
    class Concurrent(Fake):
        def observe(self,s,v):
            with guard:current[0]+=1;current[1]=max(current)
            time.sleep(.02);o=super().observe(s,v)
            with guard:current[0]-=1
            return o
    r=run_shadow(m,tmp_path/'s.db',provider_factory=lambda v,p:Concurrent(calls))
    assert r.status=='COMPLETE' and len(calls)==6 and current[1]==2
    assert all(len({row[2] for row in calls if row[0]==s.unit_id})==1 for s in m.snapshots)


def test_breach_preserves_actual_tokens_and_halts(tmp_path):
    calls=[];m=manifest()
    class Breach(Fake):
        def observe(self,s,v):
            o=super().observe(s,v)
            return ShadowObservation.model_validate({**o.model_dump(),'usage':dict(input_tokens=5000,output_tokens=5,total_tokens=5005)})
    r=run_shadow(m,tmp_path/'s.db',provider_factory=lambda v,p:Breach(calls))
    assert r.status=='ACCOUNTING_BREACH' and len(calls)==1 and r.observations[0].usage.total_tokens==5005
