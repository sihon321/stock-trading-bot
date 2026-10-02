"""HTTP security contracts against temporary operator storage only."""
import re
from datetime import timedelta

import pytest
from werkzeug.security import generate_password_hash

from operator_fixtures import FixedClock
from trading_bot.web_config import WebSettings
from trading_bot.web_store import WebStore


@pytest.fixture
def web(tmp_path, monkeypatch):
    from trading_bot import web_app
    from trading_bot.web_auth import WebAuth
    class FastAuth(WebAuth):
        def __init__(self, store, **kwargs):
            super().__init__(store, hasher=lambda p: generate_password_hash(p, method='pbkdf2:sha256:1'), **kwargs)
    monkeypatch.setattr(web_app, 'WebAuth', FastAuth)
    clock = FixedClock()
    settings = WebSettings(operational_db_path=tmp_path / 'operations' / 'web.db',
        artifact_root=tmp_path / 'artifacts', cookie_secret='test-only-cookie-secret-' * 3)
    store = WebStore(settings)
    store.initialize()
    auth = FastAuth(store, clock=clock)
    auth.provision_operator('owner', 'synthetic-password')
    app = web_app.create_app(settings, clock=clock)
    return app, app.test_client(), clock


def csrf(client, path='/login', **kwargs):
    response = client.get(path, **kwargs)
    assert response.status_code == 200
    return re.search(r'name="csrf_token" value="([^"]+)"', response.text).group(1)


def login(client, **kwargs):
    token = csrf(client, **kwargs)
    return client.post('/login', data={'username': 'owner', 'password': 'synthetic-password',
                                     'csrf_token': token}, **kwargs)


@pytest.mark.parametrize('path', ['/', '/account', '/holdings', '/candidates', '/decisions',
    '/orders', '/fills', '/runs', '/workers', '/records/audit/runs:one',
    '/evidence/audit/runs:one', '/reports', '/alerts', '/validation/soak', '/downloads/fake',
    '/validation/replay/result', '/reports/'+'a'*64, '/downloads/'+'a'*64+'/txt',
    '/alerts/'+'a'*32, '/api/views/alerts', '/api/views/reports', '/api/views/validation-replay'])
def test_auth_guards_even_reserved_and_unknown_routes(web, path):
    app, client, _ = web
    response = client.get(path)
    assert response.status_code == (401 if path.startswith('/api/') else 302)
    if not path.startswith('/api/'):
        assert response.headers['Location'].startswith('/login')
    assert 'operator-snapshot' not in response.text
    assert client.get('/api/views/overview').status_code == 401


def test_login_logout_csrf_origin_rotation_and_audit(web):
    app, client, _ = web
    assert client.post('/login', data={'username': 'owner', 'password': 'synthetic-password'}).status_code == 400
    token = csrf(client)
    assert client.post('/login', data={'csrf_token': token}, headers={'Origin': 'https://evil.test'}).status_code == 400
    assert login(client).status_code == 303
    assert client.post('/logout').status_code == 400
    token = csrf(client, '/login')
    assert client.post('/logout', data={'csrf_token': token}).status_code == 303
    assert client.get('/').status_code == 302
    with app.extensions['web_store'].connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM web_actions WHERE actor='owner' AND action='LOGOUT'").fetchone()[0] == 1


def test_auth_absolute_expiry_concurrent_and_password_reset(web):
    app, client, clock = web
    other = app.test_client()
    assert login(client).status_code == login(other).status_code == 303
    assert client.get('/api/views/unknown').status_code == 404
    clock.advance(hours=12)
    assert client.get('/api/views/overview').status_code == 401
    clock.advance(seconds=1)
    assert login(client).status_code == 303
    app.extensions['web_auth'].reset_password('replacement-password')
    assert client.get('/').status_code == 302
    assert other.get('/').status_code == 302


@pytest.mark.parametrize('return_to', ['https://evil.test', '//evil.test', '/logout', '/reports/generate', '/%2f%2fevil', '/orders\\evil'])
def test_login_return_allowlist_no_post_replay(web, return_to):
    _, client, _ = web
    token = csrf(client)
    response = client.post('/login', data={'username': 'owner', 'password': 'synthetic-password',
        'csrf_token': token, 'return_to': return_to})
    assert response.headers['Location'] == '/'


def test_host_proxy_headers_and_error_boundaries(web):
    app, client, _ = web
    assert client.get('/login', base_url='http://evil.test').status_code == 400
    response = client.get('/login', headers={'X-Forwarded-Host': 'evil.test', 'X-Forwarded-Proto': 'https',
                                            'X-Forwarded-For': '203.0.113.7'})
    assert response.status_code == 200
    assert 'frame-ancestors' in response.headers['Content-Security-Policy']
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    cookie = response.headers['Set-Cookie']
    assert 'HttpOnly' in cookie and 'SameSite=Lax' in cookie
    assert client.post('/logout').status_code in {302, 400}


def test_private_proxy_requires_https_fixed_peer_and_count(web, tmp_path):
    from trading_bot.web_app import create_app
    base, _, clock = web
    settings = WebSettings(operational_db_path=tmp_path / 'operations' / 'web.db',
        artifact_root=tmp_path / 'artifacts', private_mode=True, bind_host='10.0.0.2',
        tls_termination=True, trusted_proxies=('127.0.0.1',), allowed_hosts=('operator.test',),
        allowed_origin='https://operator.test', cookie_secret='private-synthetic-secret-' * 3)
    app = create_app(settings, clock=clock)
    client = app.test_client()
    assert client.get('/login', base_url='http://operator.test').status_code == 400
    headers = {'X-Forwarded-Proto': 'https', 'X-Forwarded-Host': 'operator.test', 'X-Forwarded-For': '10.0.0.3'}
    response = app.test_client().get('/login', base_url='http://operator.test', headers=headers)
    assert response.status_code == 200
    assert 'Secure;' in response.headers['Set-Cookie']
    assert client.get('/login', base_url='http://operator.test', headers=headers,
                      environ_overrides={'REMOTE_ADDR': '10.0.0.8'}).status_code == 400
    assert client.get('/login', base_url='http://operator.test', headers={**headers,
        'X-Forwarded-For': '10.0.0.3, 10.0.0.4'}).status_code == 400


@pytest.fixture
def secure_sources(tmp_path, monkeypatch):
    from test_web_reports import setup
    from test_web_report_routes import report_web
    from test_web_alert_routes import alert_web
    return alert_web.__wrapped__(report_web.__wrapped__(monkeypatch, setup.__wrapped__(tmp_path)))


def _route_samples(app, episode):
    substitutions = {'view_id':'overview', 'resource_id':'audit', 'record_id':'runs:operator-run',
        'family':'replay', 'result_id':'missing', 'artifact_id':'a'*64,
        'format':'txt', 'episode_id':episode.episode_id, 'filename':'operator.css'}
    samples = {}
    for rule in app.url_map.iter_rules():
        samples[rule.endpoint] = (re.sub(r'<(?:[^:>]+:)?([^>]+)>',
            lambda m:substitutions[m[1]], rule.rule), rule.methods)
    return samples


def test_every_registered_endpoint_method_auth_csrf_and_no_trade_authority(secure_sources):
    app, client, sources, alerts, episode, _ = secure_sources
    from operator_fixtures import capture_sources, SECRET_SENTINEL
    baseline = capture_sources(sources)
    samples = _route_samples(app, episode)
    assert set(samples) == {'static','login','logout','api_view','api_session','operator_record',
        'operator_evidence','operator_validation','operator_validation_result','operator_reports',
        'generate_report','operator_artifact','operator_download','operator_alerts','operator_alert',
        'acknowledge_alert', *('operator_'+name for name in ('overview','account','holdings','candidates',
            'decisions','orders','fills','runs','workers'))}
    anonymous = app.test_client()
    for endpoint, (path, methods) in samples.items():
        if endpoint in {'static','login'}:
            continue
        for method in sorted(methods):
            response = anonymous.open(path, method=method)
            assert response.status_code == (401 if path.startswith('/api/') else 302), (endpoint,method)
            assert SECRET_SENTINEL not in response.text
            assert capture_sources(sources) == baseline
        for method in {'POST','PUT','PATCH','DELETE'}:
            response = client.open(path, method=method)
            assert response.status_code == 400, (endpoint,method,response.status_code)
    token = csrf(client,'/reports')
    for endpoint, (path, methods) in samples.items():
        if endpoint in {'static','login'}:
            continue
        wrong = next(m for m in ('DELETE','PUT','PATCH','POST','GET') if m not in methods)
        response = client.open(path,method=wrong,data={'csrf_token':token})
        assert response.status_code == 405, (endpoint,wrong,response.status_code)
    for forbidden in ('order','cancel','run','llm','policy','real-enable','waive','pause','kill','resume'):
        for prefix in ('/','/api/','/actions/'):
            assert client.get(prefix+forbidden).status_code == 404
            assert client.post(prefix+forbidden,data={'csrf_token':token}).status_code == 404
    assert capture_sources(sources) == baseline


@pytest.mark.parametrize('boundary',['expired','revoked'])
def test_all_protected_endpoints_revalidate_session_including_downloads(secure_sources,boundary):
    app, client, sources, _, episode, _ = secure_sources
    token = csrf(client,'/reports')
    if boundary == 'expired':
        sources.clock.advance(hours=12)
    else:
        app.extensions['web_store'].revoke_all_sessions(sources.clock())
    for endpoint,(path,methods) in _route_samples(app,episode).items():
        if endpoint in {'static','login'}:
            continue
        for method in methods:
            response = client.open(path,method=method,data={'csrf_token':token} if method=='POST' else None)
            assert response.status_code == (401 if path.startswith('/api/') else 302), (endpoint,method)
            assert 'operator-snapshot' not in response.text


@pytest.mark.parametrize('query', ['resource_id=../audit','resource_id=/etc/passwd','limit=10001',
    'page=0','period=custom&start=2020-01-01&end=2030-01-01','target=wrong','resource_id=audit&resource_id=portfolio'])
def test_query_bounds_reject_paths_and_ambiguous_scope(secure_sources,query):
    _,client,_,_,_,_=secure_sources
    assert client.get('/orders?'+query).status_code == 400


def test_owned_artifact_idor_symlink_traversal_and_disclosure(secure_sources):
    from trading_bot.web_reports import ReportRequest
    from operator_fixtures import SECRET_SENTINEL, capture_sources
    app,client,sources,_,episode,_=secure_sources
    before=capture_sources(sources)
    reports=app.extensions['report_service']
    foreign=reports.generate_report(ReportRequest(family='replay',resource_id='replay'),actor='owner')
    with app.extensions['web_store'].connection() as conn:
        for item in foreign.formats:
            conn.execute('UPDATE web_report_artifacts SET actor=? WHERE artifact_id=?',('other',item.artifact_id))
    for item in foreign.formats:
        assert client.get(f'/downloads/{item.artifact_id}/{item.format}').status_code==404
    owned=reports.generate_report(ReportRequest(family='replay',resource_id='replay'),actor='owner')
    item=owned.formats[0]
    path=sources.artifact_root/f'{item.artifact_id}.{item.format}'
    path.unlink()
    path.symlink_to(sources.paths['audit'])
    rejected=client.get(f'/downloads/{item.artifact_id}/{item.format}')
    assert rejected.status_code in {404,503}  # Whole writable topology fails closed on an alias.
    assert SECRET_SENTINEL.encode() not in rejected.data and b'SQLite format' not in rejected.data
    path.unlink()  # Test-owned hostile alias; restore safe topology before later operations.
    for attack in ('../audit','%2e%2e%2faudit','a'*65,'audit.db','a'*64+'?path=/etc/passwd'):
        assert client.get('/reports/'+attack).status_code in {400,404}
    token=csrf(client,'/alerts/'+episode.episode_id)
    response=client.post('/alerts/'+episode.episode_id+'/ack',data={'csrf_token':token,
        'expected_revision':1,'note':'<img src=x onerror=bad()> '+SECRET_SENTINEL})
    assert response.status_code==200
    assert SECRET_SENTINEL not in response.text and '<img src=x' not in response.text
    assert capture_sources(sources)==before
