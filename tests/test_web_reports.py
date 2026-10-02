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
    assert 'PROOF' in result.diagnostics[0]


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
