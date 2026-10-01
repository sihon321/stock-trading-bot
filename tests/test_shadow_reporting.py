import pytest
from trading_bot.shadow_reporting import *
from trading_bot.shadow_runner import run_shadow
from test_shadow_runner import manifest,Fake
from test_shadow_models import observation


def result(tmp_path,**limits):
    m=manifest(**limits);r=run_shadow(m,tmp_path/'s.db',provider_factory=lambda v,p:Fake([]));return build_shadow_result(r)


def test_raw_agreement_exact_denominators_and_no_mutation(tmp_path):
    r=result(tmp_path);metrics=strict_json(r.metrics_document_json);v=metrics['variants'][0]
    assert v['attempted']==3 and v['valid_pairs']==2
    assert sum(v['matrix'].values())==v['agreement_denominator']
    assert metrics['promotion_authority'] is False and metrics['alternative_portfolio_pnl'] is None
    assert v['actual_billed_cost'] is None
    before=r.manifest.baseline_hash
    for s in r.manifest.snapshots:
        c=compare_shadow_action(s,observation(status='MALFORMED',raw_output='bad'))
        assert c.shadow_action=='HOLD' and not c.risk_override and not c.valid_pair
    assert r.manifest.baseline_hash==before


def test_partial_budget_denominators(tmp_path):
    r=result(tmp_path,max_attempts=1);v=strict_json(r.metrics_document_json)['variants'][0]
    assert r.status=='BUDGET_EXHAUSTED' and v['not_dispatched']==2 and v['attempted']==1
    assert v['failure_denominator']==1 and v['agreement_denominator']==0


def test_confidence_gate_and_risk_share_canonical_projection(tmp_path):
    r=result(tmp_path);s=r.manifest.snapshots[0]
    low=observation(raw_output='{"decision":"BUY","confidence":0.79,"reason":"fixture"}')
    c=compare_shadow_action(s,low)
    assert c.shadow_action=='HOLD' and c.shadow_quantity==0
    held=ShadowSnapshot.model_validate({**s.model_dump(),'quantity':10,'orderable_quantity':10,'held':True,'average_price':str(s.price*Decimal('2')),'snapshot_id':''})
    c=compare_shadow_action(held,observation())
    assert c.shadow_action=='SELL' and c.risk_override
    malformed=compare_shadow_action(held,observation(status='MALFORMED',raw_output='invalid'))
    assert malformed.shadow_action=='HOLD' and not malformed.risk_override
