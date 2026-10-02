"""Saved-only operational routes; fixtures are added with their route contracts."""
from test_web_security import web, csrf, login
import re
from urllib.parse import quote

import pytest


@pytest.fixture
def saved_web(web, tmp_path):
    from operator_fixtures import make_operator_sources
    from trading_bot.web_config import ResourceDescriptor, WebSettings
    from trading_bot.web_evidence import OperatorEvidenceService
    from trading_bot.web_app import create_app
    sources = make_operator_sources(tmp_path / 'sources')
    sources.artifact_root.chmod(0o700)
    settings = WebSettings(operational_db_path=sources.operational_db,
        artifact_root=sources.artifact_root, cookie_secret='synthetic-cookie-secret-' * 3,
        registered_resources=tuple(ResourceDescriptor(**vars(r)) for r in sources.resources))
    from trading_bot.web_store import WebStore
    store = WebStore(settings)
    store.initialize()
    from trading_bot.web_app import WebAuth
    WebAuth(store, clock=sources.clock).provision_operator('owner', 'synthetic-password')
    reader = OperatorEvidenceService(settings, clock=sources.clock, shadow_proof_catalog=sources.shadow_proof_catalog)
    app = create_app(settings, evidence_service=reader, clock=sources.clock)
    client = app.test_client()
    assert login(client).status_code == 303
    return app, client, sources


def test_auth_api_failure_is_safe(web):
    _, client, _ = web
    assert login(client).status_code == 303
    response = client.get('/api/views/not-registered')
    assert response.status_code == 404
    assert response.json['error_code'] == 'NOT_FOUND'


def test_overview_safety_order_all_date_source_times_and_unknown(saved_web):
    app, client, sources = saved_web
    response = client.get('/?period=7d')
    assert response.status_code == 200
    html = response.text
    assert html.index('id="safety"') < html.index('id="health"') < html.index('id="source-times"') < html.index('id="accounts"') < html.index('id="activity"')
    assert '000660 주문 결과 미확정 · 종목 동결 유지' in html
    assert 'NOT_STARTED' in html
    assert '모든 날짜' in html and '관측 경과' in html
    assert '원천 관측' in html and '화면 조회' in html
    assert '1,000,000원' in html and 'operator-snapshot' in html
    assert '동시에 생성된 스냅샷' in html
    assert html.count('navigation-group') == 4


@pytest.mark.parametrize('view', ['account', 'holdings', 'candidates', 'decisions', 'orders', 'fills', 'runs', 'workers'])
def test_operational_pages_api_render_and_native_filters(saved_web, view):
    app, client, sources = saved_web
    response = client.get('/' + view + '?period=7d')
    assert response.status_code == 200
    assert 'method="get"' in response.text
    assert '/validation/readiness' in response.text
    api = client.get('/api/views/' + view + '?period=7d')
    assert api.status_code == 200
    assert api.json['view_id'] == view
    assert api.json['queried_at'].endswith('KST')
    assert 'rendered_html' in api.json and 'status_html' in api.json
    assert str(sources.paths['audit']) not in response.text + api.text
    assert 'sk-test-operator-secret-sentinel' not in response.text + api.text


def test_exact_account_metric_list_record_evidence_and_back_context(saved_web):
    _, client, _ = saved_web
    html = client.get('/account?period=7d').text
    link = re.search(r'href="([^"]*holdings\?[^"]*selection_id=[^"]+)"', html).group(1).replace('&amp;', '&')
    result = client.get(link)
    assert result.status_code == 200
    assert '정확한 구성' in result.text
    detail_link = re.search(r'href="(/records/portfolio/[^"]+)"', result.text).group(1).replace('&amp;', '&')
    detail = client.get(detail_link)
    assert detail.status_code == 200 and '005930' in detail.text
    evidence_link = re.search(r'href="(/evidence/portfolio/[^"]+)"', detail.text).group(1).replace('&amp;', '&')
    evidence = client.get(evidence_link)
    assert evidence.status_code == 200 and '정제된 원천 증거 펼치기' in evidence.text
    assert 'period=7d' in detail.text
    assert client.get('/holdings?selection_id=forged').status_code == 400


def test_unresolved_metric_exact_list_survives_history(saved_web):
    _, client, _ = saved_web
    html = client.get('/?period=custom&start=2026-10-02&end=2026-10-02').text
    link = re.search(r'href="([^"]*/orders\?[^"]*selection_id=[^"]+)"', html).group(1).replace('&amp;', '&')
    response = client.get(link)
    assert response.status_code == 200
    assert '000660' in response.text and 'freezes' in response.text
    assert '원천 ID' in response.text and '총 3건' in response.text


def test_pagination_kst_authorization_and_hostile_bounded_errors(saved_web):
    _, client, _ = saved_web
    page = client.get('/runs?period=30d&limit=1')
    assert page.status_code == 200
    assert 'operator-run' in page.text
    assert 'historic-run' not in page.text
    for path in ['/runs?limit=101', '/orders?period=all', '/holdings?target=evil', '/holdings?target=real',
                 '/runs?resource_id=unregistered', '/runs?period=custom&start=2025-01-01&end=2026-10-02',
                 '/records/unregistered/runs%3Aoperator-run', '/evidence/audit/invalid']:
        assert client.get(path).status_code in {400, 404}
    record = client.get('/records/audit/decisions%3A1?period=7d')
    assert record.status_code == 200
    assert '[REDACTED]' in record.text
    assert '로컬 주문 기록' in client.get('/orders').text
    assert '확정 체결' in client.get('/fills').text


def test_cache_retains_historical_source_time_on_failure(saved_web):
    _, client, sources = saved_web
    first = client.get('/account').text
    sources.clock.advance(minutes=10)
    sources.paths['audit'].rename(sources.paths['audit'].with_suffix('.missing'))
    failed = client.get('/account')
    assert failed.status_code == 200 and '조회 실패' in failed.text
    assert '1,000,000원' in failed.text
    assert '2026-10-02 10:00:00 KST' in failed.text
    assert '2026-10-02 10:10:00 KST' in failed.text
    assert 'historic-freeze' not in first  # account does not merge risk/account records


def test_overview_safety_latch_visible_without_started_observer(saved_web):
    import sqlite3
    _, client, sources = saved_web
    with sqlite3.connect(sources.paths['soak']) as conn:
        conn.execute("UPDATE soak_campaigns SET safety_failure_code='BROKER_DIVERGENCE',state='FAILED' WHERE campaign_id='operator-campaign'")
    response = client.get('/')
    assert response.status_code == 200
    assert 'BROKER_DIVERGENCE' in response.text
    assert 'NOT_STARTED' in response.text


def test_routes_escape_untrusted_text_and_daily_evaluation_evidence(saved_web):
    import sqlite3
    from operator_fixtures import ACCOUNT_HASH, NOW
    _, client, sources = saved_web
    attack = '<script>alert(1)</script>'
    with sqlite3.connect(sources.paths['audit']) as conn:
        conn.execute('UPDATE decisions SET order_reason=?', (attack,))
        conn.execute("INSERT INTO daily_evaluations(evaluation_id,trading_date_kst,ticker,provenance_json,canonical_input,canonical_input_hash,account_scope_hash,status,started_at) VALUES(?,?,?,?,?,?,?,?,?)",
            ('daily-evaluation', '2026-10-02', '005930', '[]', b'secret-prompt', 'b'*64, ACCOUNT_HASH, 'STARTED', NOW.isoformat()))
    response = client.get('/records/audit/decisions%3A1')
    assert response.status_code == 200
    assert '&lt;script&gt;' in response.text and attack not in response.text
    response = client.get('/decisions')
    assert 'daily-evaluation' in response.text and 'secret-prompt' not in response.text


def test_detail_back_preserves_second_page_cursor(saved_web):
    _, client, _ = saved_web
    first = client.get('/runs?period=custom&start=2026-08-01&end=2026-10-02&limit=1')
    from bs4 import BeautifulSoup
    page = BeautifulSoup(first.text, 'html.parser')
    second_url = next(a['href'] for a in page.select('.pagination a') if '다음 페이지' in a.text)
    second = client.get(second_url)
    page = BeautifulSoup(second.text, 'html.parser')
    detail = client.get(page.select_one('.routine-table a')['href'])
    page = BeautifulSoup(detail.text, 'html.parser')
    back = page.select_one('.breadcrumb a')['href']
    assert 'cursor=' in back and 'page=2' in back
    assert 'operator-run' in client.get(back).text
