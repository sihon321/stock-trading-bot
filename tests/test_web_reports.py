"""Saved report services use synthetic sources and never acquire trading authority."""
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from operator_fixtures import make_operator_sources, capture_sources, SECRET_SENTINEL


@pytest.fixture
def setup(tmp_path):
    from trading_bot.web_config import WebSettings, ResourceDescriptor
    from trading_bot.web_reports import SavedReportService
    sources = make_operator_sources(tmp_path)
    # The historical reporting fixture has aggregate-only stage provenance.
    # This web vector records every stage fact needed for exact constituents.
    from test_reporting import _manifest
    from trading_bot.replay_evidence import ReplayOutcome, ReplayResult, ReplayVerification, build_replay_funnel
    outcome=ReplayOutcome('saved-scenario','000660',1,'BUY',True,'FILLED','saved',1000,1,'BUY',True,
        selected=True,buy_signaled=True,confidence_qualified=True,risk_qualified=True,validly_sized=True,order_eligible=True)
    replay=ReplayResult(_manifest(),(outcome,),{},build_replay_funnel((outcome,)),ReplayVerification(True,()))
    sources.paths['replay'].write_bytes(replay.normalized_bytes())
    settings = WebSettings(operational_db_path=sources.operational_db,
        artifact_root=sources.artifact_root,
        registered_resources=tuple(ResourceDescriptor(**vars(r)) for r in sources.resources))
    return sources, settings, SavedReportService(settings, clock=sources.clock,
        shadow_proof_catalog=sources.shadow_proof_catalog)


def test_catalog_all_eight_registered_families(setup):
    _, _, service = setup
    assert {entry.family for entry in service.catalog()} == {
        'daily', 'period', 'replay', 'backtest', 'shadow', 'soak', 'calibration', 'readiness'}


@pytest.mark.parametrize('family,resource', [('daily','audit'), ('period','audit'),
    ('replay','replay'), ('backtest','backtest'), ('shadow','shadow'), ('soak','soak')])
def test_projection_saved_families_same_selection_and_source_bytes(setup, family, resource):
    from trading_bot.web_reports import ReportRequest
    sources, _, service = setup
    before = capture_sources(sources)
    request = ReportRequest(family=family, resource_id=resource,
        result_id='operator-campaign' if family == 'soak' else None,
        start=sources.clock().date() if family in {'daily','period'} else None,
        end=sources.clock().date() if family == 'period' else None)
    projection = service.project(request)
    assert projection.status == 'AVAILABLE', projection.diagnostics
    assert projection.selection.scope.account_hash == sources.account_hash
    assert all(m.selection_id == projection.selection.selection_id for m in projection.metrics)
    assert all(set(m.constituent_ids + m.excluded_ids + m.unknown_ids) <=
               {row.record_id for row in projection.rows} for m in projection.metrics)
    assert SECRET_SENTINEL not in repr(projection)
    assert capture_sources(sources) == before


@pytest.mark.parametrize('family,code', [('calibration','SAVED_CALIBRATION_PROOF_MISSING'),
    ('readiness','SAVED_READINESS_FACTS_MISSING')])
def test_unavailable_provenance_is_named(setup, family, code):
    from trading_bot.web_reports import ReportRequest
    _, _, service = setup
    result = service.project(ReportRequest(family=family, resource_id='soak', result_id='operator-campaign'))
    assert result.status == 'UNKNOWN'
    assert result.diagnostics == (code,)


def test_unavailable_shadow_needs_registered_proof(setup):
    from trading_bot.web_reports import SavedReportService, ReportRequest
    _, settings, _ = setup
    result = SavedReportService(settings).project(ReportRequest(family='shadow', resource_id='shadow'))
    assert result.status == 'UNKNOWN'
    assert result.diagnostics == ('SAVED_SHADOW_PROVENANCE_UNAVAILABLE',)


@pytest.mark.parametrize('extra', [{'path':'/etc/passwd'}, {'manual_approval':True},
    {'policy':{}}, {'command':'run'}, {'resource_id':'../audit'}, {'formats':('exe',)}])
def test_projection_request_rejects_authority_and_paths(extra):
    from trading_bot.web_reports import ReportRequest
    with pytest.raises((ValueError, TypeError)):
        ReportRequest(**({'family':'daily','resource_id':'audit'} | extra))


def test_capability_fresh_import_and_valid_invalid_calls(setup):
    from test_saved_calibration_evidence import PROBE
    sources, settings, _ = setup
    script = PROBE + '''
from trading_bot.web_config import WebSettings
from trading_bot.web_reports import SavedReportService, ReportRequest
settings = WebSettings.model_validate(payload['settings'])
service = SavedReportService(settings)
assert service.project(ReportRequest(family='backtest',resource_id='backtest')).status == 'AVAILABLE'
assert service.project(ReportRequest(family='readiness',resource_id='soak',result_id='operator-campaign')).status == 'UNKNOWN'
try: ReportRequest(family='daily',resource_id='../audit',manual_approval=True)
except ValueError: pass
else: raise AssertionError('unsafe request accepted')
print('ok')
'''
    child = subprocess.run([sys.executable, '-B', '-c', script,
        json.dumps({'settings':settings.model_dump(mode='json')})], capture_output=True,
        text=True, timeout=20)
    assert child.returncode == 0, child.stderr


def test_projection_registered_calibration_outcomes_and_readiness_saved_facts(setup, tmp_path):
    from test_saved_calibration_evidence import _calibration_sources
    from trading_bot.web_config import WebSettings, ResourceDescriptor
    from trading_bot.web_reports import (SavedReportService, ReportRequest, SavedCalibrationProof,
        SavedReadinessFacts, proof_hash)
    from trading_bot.calibration_evidence import VariantEvaluation, VariantMetrics, build_variant_catalog
    from trading_bot.replay_evidence import ReplayOutcome
    from test_promotion_readiness import _evidence
    sources, settings, service = setup
    root=tmp_path/'calibration';root.mkdir()
    audit,soak=_calibration_sources(root)
    settings2=WebSettings(registered_resources=tuple(ResourceDescriptor(id=owner,path=path,
        owner=owner,account_hash=sources.account_hash,target='mock') for owner,path in (('audit',audit),('soak',soak))))
    outcome=ReplayOutcome('run-1','000001',1,'HOLD',False,'NONE','HOLD',1000,0,'HOLD',True)
    evaluation=VariantEvaluation(build_variant_catalog()[0],VariantMetrics(1,1,0,1,0,0,0,0,0,0,0,0),(outcome,))
    proof=SavedCalibrationProof('soak','campaign-1',(evaluation,),('audit','soak'),(('run-1','000001',70000),),'0'*64)
    proof=replace(proof,expected_hash=proof_hash(proof.document()))
    request=ReportRequest(family='calibration',resource_id='soak',result_id='campaign-1')
    result=SavedReportService(settings2,calibration_proof_catalog=(proof,)).project(request)
    assert result.status=='AVAILABLE',result.diagnostics
    assert {r.kind for r in result.rows}=={'outcomes','excluded','unknown'}
    assert dict(result.facts)['normal_cycles']==1 and dict(result.facts)['unknown_cycles']==1
    bad=replace(proof,evaluations=(replace(evaluation,outcomes=()),))
    bad=replace(bad,expected_hash=proof_hash(bad.document()))
    assert SavedReportService(settings2,calibration_proof_catalog=(bad,)).project(request).diagnostics==('SAVED_CALIBRATION_OUTCOMES_MISSING',)
    readiness=SavedReadinessFacts('soak','operator-campaign',_evidence(),(('threshold',0.8),),True,True,True,'0'*64)
    readiness=replace(readiness,expected_hash=proof_hash(readiness.document()))
    result=SavedReportService(settings,readiness_proof_catalog=(readiness,)).project(
        ReportRequest(family='readiness',resource_id='soak',result_id='operator-campaign'))
    assert result.status=='AVAILABLE',result.diagnostics
    assert dict(result.facts)['state']=='BLOCKED'
    assert next(r for r in result.rows if r.record_id=='checks:SOAK_ACCEPTED').data['active_freezes']==1
    assert len(result.rows)==9


@pytest.mark.parametrize('family,resource', [('daily','audit'),('period','audit'),('replay','replay'),
    ('backtest','backtest'),('shadow','shadow'),('soak','soak'),('calibration','soak'),('readiness','soak')])
def test_unavailable_missing_broken_saved_source_all_families(setup, family, resource):
    from trading_bot.web_reports import ReportRequest
    sources, _, service=setup
    request=ReportRequest(family=family,resource_id=resource,result_id='missing-campaign' if family in {'soak','calibration','readiness'} else None,
        start=sources.clock().date() if family in {'daily','period'} else None,
        end=sources.clock().date() if family=='period' else None)
    sources.paths[resource].unlink()
    result=service.project(request)
    assert result.status=='UNKNOWN' and result.diagnostics==('SOURCE_MISSING',)


def test_projection_scope_and_period_and_exact_metric_links(setup):
    from trading_bot.web_reports import ReportRequest
    sources,settings,service=setup
    result=service.project(ReportRequest(family='replay',resource_id='replay'))
    assert result.status=='AVAILABLE',result.diagnostics
    for metric in result.metrics:
        assert metric.numerator==len(metric.constituent_ids)
        assert len(metric.constituent_ids)+len(metric.excluded_ids)==len(result.rows)
    with pytest.raises(ValueError):
        service.project(ReportRequest(family='period',resource_id='audit',start='2026-01-01',end='2026-03-01'))
    from operator_fixtures import make_operator_sources
    from trading_bot.web_config import ResourceDescriptor
    conflict=make_operator_sources(sources.artifact_root/'conflict',scenario='scope_conflict')
    w=settings.model_copy(update={'registered_resources':tuple(ResourceDescriptor(**vars(r)) for r in conflict.resources)})
    result=type(service)(w).project(ReportRequest(family='daily',resource_id='audit',start=sources.clock().date()))
    assert result.diagnostics==('SCOPE_CONFLICT',)
