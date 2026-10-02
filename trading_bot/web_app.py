"""Authenticated saved-evidence HTTP surface; no trading runtime capabilities."""
from __future__ import annotations

from datetime import datetime, timezone
import ipaddress
import secrets
from urllib.parse import urlsplit, parse_qsl, urlencode

from flask import Flask, abort, g, jsonify, redirect, render_template, request, session
from flask_wtf.csrf import CSRFProtect, CSRFError, generate_csrf
from werkzeug.exceptions import HTTPException

from .web_auth import WebAuth
from .web_config import WebSettings
from .web_store import WebStore

OPERATIONAL_VIEWS = {
    'overview': ('/', '안전 개요'), 'account': ('/account', '계좌 요약'),
    'holdings': ('/holdings', '보유 종목'), 'candidates': ('/candidates', '선별 후보'),
    'decisions': ('/decisions', 'LLM 판단'), 'orders': ('/orders', '주문'),
    'fills': ('/fills', '체결'), 'runs': ('/runs', '실행 이력'), 'workers': ('/workers', '작업 상태'),
}
RESERVED_GET_PATHS = {'/alerts', '/reports', '/validation/replay', '/validation/backtest',
    '/validation/shadow', '/validation/soak', '/validation/calibration', '/validation/readiness'}
FORM_ERROR = '요청을 확인할 수 없습니다. 화면을 다시 연 뒤 입력 내용을 확인하고 다시 시도하세요.'
RECORD_ERROR = '요청한 증거를 열 수 없습니다. 목록으로 돌아가 등록된 증거를 선택하세요.'


class FixedProxyBoundary:
    """One explicit peer/one header value, matching the Waitress CLI topology.

    Waitress strips consumed forwarding headers. In that case its already
    normalized WSGI environment is retained; arbitrary direct headers are removed.
    """
    def __init__(self, application, settings):
        self.application, self.settings = application, settings

    def __call__(self, environ, start_response):
        peer = environ.get('REMOTE_ADDR')
        trusted = peer in self.settings.trusted_proxies
        names = ('HTTP_X_FORWARDED_PROTO', 'HTTP_X_FORWARDED_HOST', 'HTTP_X_FORWARDED_FOR', 'HTTP_X_FORWARDED_PORT')
        if trusted:
            values = {name: environ.get(name) for name in names}
            if any(value and (',' in value or len(value) > 256) for value in values.values()):
                environ['operator.bad_proxy'] = True
            else:
                proto, host, address, port = (values[name] for name in names)
                if proto:
                    if proto not in {'http', 'https'}:
                        environ['operator.bad_proxy'] = True
                    else:
                        environ['wsgi.url_scheme'] = proto
                if host:
                    environ['HTTP_HOST'] = host
                if port:
                    if not port.isdecimal() or not 1 <= int(port) <= 65535:
                        environ['operator.bad_proxy'] = True
                    else:
                        environ['SERVER_PORT'] = port
                        if host and ':' not in host:
                            environ['HTTP_HOST'] = host + ('' if port == '443' and proto == 'https' else ':' + port)
                if address:
                    try:
                        environ['REMOTE_ADDR'] = str(ipaddress.ip_address(address))
                    except ValueError:
                        environ['operator.bad_proxy'] = True
        for name in tuple(environ):
            if name.startswith('HTTP_X_FORWARDED_') or name == 'HTTP_FORWARDED':
                environ.pop(name, None)
        return self.application(environ, start_response)


def safe_return_path(value, app):
    """Only fixed registered GET destinations; never actions or external URLs."""
    if not isinstance(value, str) or len(value) > 2048 or any(c in value for c in ('\\', '\r', '\n', '\t', '\x00')):
        return '/'
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.fragment or '%' in parsed.path:
        return '/'
    paths = {path for path, _ in OPERATIONAL_VIEWS.values()} | RESERVED_GET_PATHS
    if parsed.path not in paths:
        return '/'
    allowed = {'period', 'start', 'end', 'target', 'resource_id', 'cursor', 'limit', 'selection_id'}
    query = parse_qsl(parsed.query, keep_blank_values=True, max_num_fields=16)
    if any(k not in allowed or len(v) > 2048 for k, v in query):
        return '/'
    return parsed.path + ('?' + urlencode(query) if query else '')


def create_app(settings, *, evidence_service=None, report_service=None, alert_store=None, clock=None):
    if not isinstance(settings, WebSettings):
        raise ValueError('WebSettings required')
    if settings.private_mode and len(settings.trusted_proxies) != 1:
        raise ValueError('one fixed proxy required')
    settings.validate_topology()
    clock = clock or (lambda: datetime.now(timezone.utc))
    app = Flask(__name__)
    app.config.update(SECRET_KEY=settings.cookie_secret.get_secret_value() if settings.cookie_secret else secrets.token_hex(32),
        SESSION_COOKIE_NAME='operator_session', SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=settings.private_mode,
        SESSION_REFRESH_EACH_REQUEST=False, PERMANENT_SESSION_LIFETIME=43200,
        TRUSTED_HOSTS=list(settings.allowed_hosts), MAX_CONTENT_LENGTH=32768,
        MAX_FORM_MEMORY_SIZE=16384, MAX_FORM_PARTS=16, WTF_CSRF_CHECK_DEFAULT=False,
        WTF_CSRF_SSL_STRICT=False)
    store = WebStore(settings)
    auth = WebAuth(store, clock=clock)
    app.extensions.update(web_settings=settings, web_store=store, web_auth=auth,
        evidence_service=evidence_service, report_service=report_service, alert_store=alert_store,
        operator_clock=clock, operator_view_builders={})
    csrf = CSRFProtect(app)

    def safe_error(code, status):
        if request.path.startswith('/api/'):
            return jsonify(error_code=code), status
        return render_template('operator/login.html', title='요청 확인', error=FORM_ERROR if status == 400 else RECORD_ERROR,
                               error_code=code, csrf_token=generate_csrf(), return_to='/'), status
    app.extensions['operator_safe_error'] = safe_error

    @app.before_request
    def guard():
        # Access host explicitly even for unmatched routes; Flask also validates routing.
        parsed = urlsplit(request.host_url)
        if parsed.hostname not in settings.allowed_hosts or request.environ.get('operator.bad_proxy'):
            abort(400)
        if settings.private_mode and (not request.is_secure or request.host_url.rstrip('/') != settings.allowed_origin):
            abort(400)
        if request.endpoint == 'static':
            if request.view_args.get('filename') not in {'operator.css', 'operator.js'}:
                abort(404)
            return None
        public = request.endpoint == 'login'
        g.operator_session = auth.validate_session(session.get('operator_token')) if not public else None
        if not public and g.operator_session is None:
            session.clear()
            if request.path.startswith('/api/'):
                return safe_error('AUTH_REQUIRED', 401)
            path = safe_return_path(request.full_path.rstrip('?'), app) if request.method == 'GET' else '/'
            return redirect('/login?' + urlencode({'return_to': path}), code=302)
        if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            origin = request.headers.get('Origin')
            expected = settings.allowed_origin or request.host_url.rstrip('/')
            referrer = request.headers.get('Referer')
            if (origin and origin != expected) or (not origin and referrer and
                    f'{urlsplit(referrer).scheme}://{urlsplit(referrer).netloc}' != expected):
                abort(400)
            csrf.protect()

    @app.after_request
    def headers(response):
        response.headers.update({'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
            'Referrer-Policy': 'same-origin', 'X-Frame-Options': 'DENY',
            'Content-Security-Policy': "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; form-action 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"})
        return response

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        return safe_error('INVALID_REQUEST', 400)

    @app.errorhandler(HTTPException)
    def http_error(error):
        return safe_error({400: 'INVALID_REQUEST', 404: 'NOT_FOUND', 405: 'METHOD_NOT_ALLOWED',
                           413: 'REQUEST_BOUND'}.get(error.code, 'REQUEST_FAILED'), error.code)

    @app.errorhandler(Exception)
    def unknown_error(error):
        return safe_error('SERVICE_UNAVAILABLE', 503)

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        target = safe_return_path(request.form.get('return_to') if request.method == 'POST' else request.args.get('return_to'), app)
        error = None
        if request.method == 'POST':
            token = auth.authenticate(request.form.get('username', ''), request.form.get('password', ''), request.remote_addr)
            if token:
                session.clear()
                session['operator_token'] = token
                return redirect(target, code=303)
            error = '로그인할 수 없습니다. 계정과 비밀번호를 확인하세요. 잠시 후 다시 로그인하세요.'
        return render_template('operator/login.html', title='로그인', error=error,
                               csrf_token=generate_csrf(), return_to=target), (401 if error else 200)

    @app.post('/logout')
    def logout():
        auth.logout(session.get('operator_token'))
        session.clear()
        return redirect('/login', code=303)

    @app.get('/api/views/<view_id>')
    def api_view(view_id):
        builder = app.extensions['operator_view_builders'].get(view_id)
        if builder is None:
            abort(404)
        return jsonify(builder(api=True))

    app.wsgi_app = FixedProxyBoundary(app.wsgi_app, settings)
    return app
