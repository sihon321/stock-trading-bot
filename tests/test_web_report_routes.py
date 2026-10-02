"""Native saved validation/export routes with temporary sources only."""
import re
from urllib.parse import quote

import pytest
from test_web_security import web, csrf, login
from test_web_reports import setup
from operator_fixtures import capture_sources, SECRET_SENTINEL


@pytest.fixture
def report_web(monkeypatch, setup):
    from trading_bot import web_app
    from trading_bot.web_auth import WebAuth
    from werkzeug.security import generate_password_hash
    class FastAuth(WebAuth):
        def __init__(self, store, **kwargs):
            super().__init__(store, hasher=lambda p: generate_password_hash(p, method='pbkdf2:sha256:1'), **kwargs)
    monkeypatch.setattr(web_app, 'WebAuth', FastAuth)
    from trading_bot.web_store import WebStore
    from trading_bot.web_reports import SavedReportService
    from trading_bot.web_evidence import OperatorEvidenceService
    sources, settings, _ = setup
    sources.artifact_root.chmod(0o700)
    store = WebStore(settings)
    store.initialize()
    FastAuth(store, clock=sources.clock).provision_operator('owner', 'synthetic-password')
    service = SavedReportService(settings, store=store, clock=sources.clock,
        shadow_proof_catalog=sources.shadow_proof_catalog)
    app = web_app.create_app(settings, evidence_service=OperatorEvidenceService(settings, clock=sources.clock),
        report_service=service, clock=sources.clock)
    client = app.test_client()
    assert login(client).status_code == 303
    return app, client, sources


@pytest.mark.parametrize('family,resource', [('replay','replay'),('backtest','backtest'),
    ('shadow','shadow'),('soak','soak'),('calibration','soak'),('readiness','soak')])
def test_validation_exact_metric_constituents_and_unavailable(report_web, family, resource):
    from trading_bot.web_reports import ReportRequest
    app, client, sources = report_web
    before = capture_sources(sources)
    result_id = 'operator-campaign' if resource == 'soak' else None
    path = f'/validation/{family}' + (f'/{result_id}' if result_id else '')
    response = client.get(path + '?resource_id=' + resource)
    assert response.status_code == 200
    projection = app.extensions['report_service'].project(ReportRequest(
        family=family, resource_id=resource, result_id=result_id))
    assert projection.selection.selection_id in response.text
    if projection.status == 'UNKNOWN':
        assert projection.diagnostics[0] in response.text and 'UNKNOWN' in response.text
    else:
        metric = projection.metrics[0]
        detail = client.get(path + '?resource_id=' + resource + '&metric_id=' + quote(metric.metric_id))
        assert detail.status_code == 200
        assert metric.selection_id in detail.text
        for row in projection.metric_detail(metric.metric_id):
            evidence = client.get(path + '?resource_id=' + resource + '&record_id=' + quote(row.record_id))
            assert evidence.status_code == 200 and row.record_id in evidence.text
    assert SECRET_SENTINEL not in response.text
    assert capture_sources(sources) == before


def test_generate_downloads_owned_authorized_and_source_unchanged(report_web):
    app, client, sources = report_web
    before = capture_sources(sources)
    response = client.post('/reports/generate', data={'family':'replay','resource_id':'replay',
        'csrf_token':csrf(client, '/reports')})
    assert response.status_code == 200
    links = re.findall(r'href="(/downloads/[a-f0-9]+/(?:txt|json|csv))"', response.text)
    assert len(links) == 3
    for link in links:
        assert client.get(link.replace('/downloads/','/reports/').rsplit('/',1)[0]).status_code == 200
        downloaded = client.get(link)
        assert downloaded.status_code == 200
        assert downloaded.headers['Content-Disposition'].startswith('attachment;')
        assert downloaded.headers['Cache-Control'] == 'no-store'
        assert SECRET_SENTINEL.encode() not in downloaded.data
        assert client.get(link.rsplit('/',1)[0] + '/html').status_code == 404
    app.extensions['web_store'].revoke_all_sessions(sources.clock())
    assert client.get(links[0]).status_code == 302
    assert capture_sources(sources) == before


@pytest.mark.parametrize('extra', [{'path':'/etc/passwd'},{'manual_approval':'true'},
    {'format':'html'},{'resource_id':'unregistered'},{'family':'evil'}])
def test_generation_invalid_input_is_audited(report_web, extra):
    app, client, _ = report_web
    response = client.post('/reports/generate', data={'family':'replay','resource_id':'replay',
        'csrf_token':csrf(client, '/reports'), **extra})
    assert response.status_code == 400
    with app.extensions['web_store'].connection() as conn:
        assert conn.execute("SELECT count(*) FROM web_actions WHERE action='REPORT_GENERATE' AND result_code='INVALID_REQUEST'").fetchone()[0] == 1


def test_report_native_csrf_family_scope_and_artifact_idor(report_web):
    _, client, _ = report_web
    assert client.post('/reports/generate', data={'family':'replay','resource_id':'replay'}).status_code == 400
    assert client.get('/validation/replay?resource_id=audit').status_code == 400
    assert client.get('/validation/not-a-family').status_code == 404
    assert client.get('/downloads/' + 'a'*64 + '/txt').status_code == 404


def test_csrf_and_oversize_generation_audited(report_web):
    app, client, _ = report_web
    assert client.post('/reports/generate',data={'family':'replay','resource_id':'replay'}).status_code == 400
    assert client.post('/reports/generate',data={'csrf_token':csrf(client,'/reports'),'family':'replay',
        'resource_id':'replay','result_id':'x'*40000}).status_code == 413
    with app.extensions['web_store'].connection() as conn:
        codes={row[0] for row in conn.execute("SELECT result_code FROM web_actions WHERE action='REPORT_GENERATE'")}
    assert {'INVALID_REQUEST','REQUEST_BOUND'} <= codes
