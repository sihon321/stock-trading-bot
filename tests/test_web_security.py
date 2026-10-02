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
    '/evidence/audit/runs:one', '/reports', '/alerts', '/validation/soak', '/downloads/fake'])
def test_auth_guards_even_reserved_and_unknown_routes(web, path):
    app, client, _ = web
    response = client.get(path)
    assert response.status_code == 302
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
    response = client.get('/login', base_url='http://operator.test', headers=headers)
    assert response.status_code == 200
    assert 'Secure;' in response.headers['Set-Cookie']
    assert client.get('/login', base_url='http://operator.test', headers=headers,
                      environ_overrides={'REMOTE_ADDR': '10.0.0.8'}).status_code == 400
    assert client.get('/login', base_url='http://operator.test', headers={**headers,
        'X-Forwarded-For': '10.0.0.3, 10.0.0.4'}).status_code == 400
