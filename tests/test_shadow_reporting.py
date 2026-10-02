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
    assert v['failure_denominator']==1 and v['agreement_denominator']==1


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


def test_saved_result_recomputed_and_outputs_are_idempotent(tmp_path):
    r=result(tmp_path);path=tmp_path/'result.json'
    catalog=r._creation_proof_catalog
    write_shadow_result(r,path);assert load_shadow_result(path,proof_catalog=catalog)==r
    with pytest.raises(SavedShadowUnavailable):load_shadow_result(path)
    text=render_shadow_report(r);out=tmp_path/'report.md'
    assert write_shadow_report(text,out)==write_shadow_report(text,out)
    assert '수동 결정' in text and 'UNKNOWN' in text and 'HINDSIGHT' in text
    raw=r.model_dump(mode='json');raw['result_id']='';metrics=strict_json(raw['metrics_document_json']);metrics['attempted']=999
    raw['metrics_document_json']=canonical_json(metrics);path2=tmp_path/'tampered.json';path2.write_text(canonical_json(raw))
    with pytest.raises(ValueError,match='METRICS'):load_shadow_result(path2)
    with pytest.raises(ValueError,match='CONFLICT'):write_shadow_report('different',out)
    sym=tmp_path/'symlink';sym.symlink_to(out)
    with pytest.raises(ValueError):write_shadow_report(text,sym)


def test_unknown_usage_is_not_zero_and_controls_removed(tmp_path):
    m=manifest()
    class Unknown(Fake):
        def observe(self,s,v):
            return ShadowObservation(provider=v.provider,requested_model=v.model,status='PROVIDER_ERROR',validation_code='FIXTURE',raw_output='\u001b[31msecret terminal')
    r=build_shadow_result(run_shadow(m,tmp_path/'s.db',provider_factory=lambda v,p:Unknown([])))
    v=strict_json(r.metrics_document_json)['variants'][0]
    assert v['estimated_cost_usd'] is None and v['retained_reservations']==3
    assert v['agreement_denominator']==0 and v['failure_numerator']==v['failure_denominator']==3
    text=render_shadow_report(r);assert '추정 비용 (ESTIMATED): UNKNOWN' in text
    out=tmp_path/'clean.md';write_shadow_report('title\x1b[31m\x00hello',out)
    assert '\x1b' not in out.read_text() and '\x00' not in out.read_text()


def test_rehashed_snapshot_fabrication_is_rejected_before_paid_call(tmp_path):
    from trading_bot.shadow_runner import run_shadow
    m=manifest();s=m.snapshots[0]
    forged=ShadowSnapshot.model_validate({**s.model_dump(),'available_cash':s.available_cash+1,'settled_cash':s.settled_cash+1,'snapshot_id':''})
    bad=ShadowManifest.model_validate({**m.model_dump(),'snapshots':(forged,*m.snapshots[1:]),'spec_id':''})
    with pytest.raises(ValueError,match='FROZEN_INPUT_REPLAY_MISMATCH'):
        run_shadow(bad,tmp_path/'s.db',provider_factory=lambda *a:pytest.fail('forged context must not dispatch'))


def test_linked_changed_spec_retains_parent_identity(tmp_path):
    from trading_bot.shadow_inputs import prepare_shadow_manifest
    from test_shadow_inputs import bundle
    from test_shadow_models import variant,pricing
    previous=result(tmp_path);b=bundle()
    changed=prepare_shadow_manifest(b,[variant()],[pricing()],start=b.calendar[5].session,seed='different',parent_result=previous)
    assert changed.spec_id!=previous.manifest.spec_id
    assert changed.parent_spec_id==previous.manifest.spec_id and changed.parent_run_id==previous.run_id


def test_saved_render_and_write_require_registered_provenance(tmp_path):
    r=result(tmp_path)
    detached=ShadowRunResult.model_validate(strict_json(canonical_json(r)))
    for action in (lambda: render_shadow_report(detached),
                   lambda: write_shadow_result(detached,tmp_path/'unsupported.json')):
        with pytest.raises(SavedShadowUnavailable) as error:action()
        assert error.value.status=='UNKNOWN'
    assert not (tmp_path/'unsupported.json').exists()
    assert render_shadow_report(detached,proof_catalog=r._creation_proof_catalog)==render_shadow_report(r)


def test_saved_path_and_proof_bounds_are_enforced(tmp_path):
    r=result(tmp_path);path=tmp_path/'saved.json';write_shadow_result(r,path)
    alias=tmp_path/'linked';alias.symlink_to(tmp_path,target_is_directory=True)
    with pytest.raises(ShadowInputError,match='UNSAFE'):
        load_shadow_result(alias/'saved.json',proof_catalog=r._creation_proof_catalog)
    with pytest.raises(ShadowInputError,match='TOO_LARGE'):
        write_shadow_report('x'*(DOCUMENT_LIMIT+1),tmp_path/'huge.txt')
    assert not (tmp_path/'huge.txt').exists()
