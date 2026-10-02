"""Authenticated saved-evidence HTTP surface; no trading runtime capabilities."""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import sqlite3
import ipaddress
import secrets
from urllib.parse import urlsplit, parse_qsl, urlencode, quote

from flask import Flask, abort, g, jsonify, redirect, render_template, request, session
from flask_wtf.csrf import CSRFProtect, CSRFError, generate_csrf
from werkzeug.exceptions import HTTPException

from .web_auth import WebAuth
from .web_config import WebSettings
from .web_store import WebStore
from .web_evidence import OperatorEvidenceService, ReadOnlyPortfolioRepository, EvidenceUnavailable, _clean
from .web_models import ResourceScope, PeriodSelection, KST, EvidenceRecord, EvidenceSelection, RecordPage

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

LABELS = {
    'ticker': '종목', 'quantity': '보유 수량', 'orderable_quantity': '주문 가능 수량',
    'average_price': '평균 원가', 'current_price': '저장 가격', 'evaluation_amount': '평가액',
    'unrealized_profit': '미실현 손익', 'final_action': '최종 판단', 'parsed_decision': 'LLM 판단',
    'confidence': '신뢰도', 'order_reason': '판단 사유', 'override_reason': '위험 차단 사유',
    'run_id': '실행 ID', 'origin_run_id': '원래 실행 ID', 'observer_run_id': '관측 실행 ID',
    'event_type': '기록 유형', 'broker_status': '브로커 관측 상태', 'order_id': '브로커 주문 ID',
    'broker_order_id': '브로커 주문 ID', 'requested_qty': '요청 수량', 'filled_qty': '관측 체결 수량',
    'unfilled_qty': '관측 미체결 수량', 'remaining_quantity': '미체결 수량', 'status': '기록 상태',
    'side': '매매 구분', 'price': '저장 가격', 'fill_id': '체결 ID', 'order_intent_id': '로컬 주문 의도 ID',
    'freeze_kind': '동결 사유', 'state': '관측 상태', 'terminal_status': '최종 상태',
    'expected_running': '실행 기대', 'cadence_seconds': '문서화된 주기(초)',
    'lease_observed_at': '리스 관측', 'lease_age_seconds': '리스 경과(초)',
    'snapshot_id': '스냅샷 ID', 'source_ids': '원천 연결 ID', 'outcome_code': '선별 결과',
    'reason_code': '사유 코드', 'rank': '선별 순위', 'provider': '제공자', 'model': '모델',
    'risk_verdict': '위험 검증', 'evaluation_id': '일일 평가 ID', 'run_kind': '실행 종류',
    'target': '대상', 'trading_date_kst': '거래일(KST)', 'completed_tickers': '완료 종목 수',
    'total_tickers': '전체 종목 수', 'campaign_id': '캠페인 ID', 'state_identity': '상태 ID',
    'available_cash': '가용 현금', 'total_evaluation': '총 평가액', 'latest_attempt_status': '최근 시도 완전성',
}


def kst_time(value):
    return 'UNKNOWN' if value is None else value.astimezone(KST).strftime('%Y-%m-%d %H:%M:%S KST')


def source_presentation(envelope, record_id=None, **extra):
    return dict(resource_id=envelope.resource_id, record_id=record_id or 'UNKNOWN',
        observed_at=kst_time(envelope.source_observed_at), queried_at=kst_time(envelope.query_at),
        age='UNKNOWN' if envelope.age_seconds is None else f'{envelope.age_seconds:,.0f}초',
        freshness='SAVED' if envelope.freshness == 'FRESH' else envelope.freshness,
        completeness=envelope.completeness, query_status='SUCCESS' if envelope.query_status == 'OK' else envelope.query_status,
        diagnostic_code=envelope.diagnostic_code, provenance=envelope.provenance,
        schema_owner=envelope.schema_owner, schema_version=envelope.schema_version, **extra)


def _selection_id(rows):
    return hashlib.sha256(json.dumps([(r.resource_id, r.record_id) for r in rows], separators=(',', ':')).encode()).hexdigest()


def _record_path(prefix, resource_id, record_id):
    return f'/{prefix}/{quote(resource_id, safe="")}/{quote(record_id, safe="")}'


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
    try:
        parsed = urlsplit(value)
        query = parse_qsl(parsed.query, keep_blank_values=True, max_num_fields=16)
    except ValueError:
        return '/'
    if parsed.scheme or parsed.netloc or parsed.fragment or '%' in parsed.path:
        return '/'
    paths = {path for path, _ in OPERATIONAL_VIEWS.values()} | RESERVED_GET_PATHS
    if parsed.path not in paths:
        return '/'
    allowed = {'period', 'start', 'end', 'target', 'resource_id', 'cursor', 'eval_cursor', 'page', 'limit', 'selection_id'}
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
        evidence_service=evidence_service or OperatorEvidenceService(settings, clock=clock), report_service=report_service, alert_store=alert_store,
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

    def query_context():
        args = request.args
        if len(args) > 16 or any(len(v) > 2048 or len(args.getlist(k)) != 1 for k, v in args.items()):
            abort(400)
        period_name = args.get('period', 'today')
        try:
            if period_name == 'custom':
                period = PeriodSelection.custom(date.fromisoformat(args.get('start', '')), date.fromisoformat(args.get('end', '')))
            else:
                period = PeriodSelection.for_days(clock(), {'today': 1, '7d': 7, '30d': 30}[period_name])
            limit = int(args.get('limit', settings.default_rows))
            page_number = int(args.get('page', 1))
            if not 1 <= limit <= settings.max_rows or not 1 <= page_number <= 10000:
                raise ValueError()
            resource_id = args.get('resource_id') or None
            resource = settings.resource(resource_id) if resource_id else None
            target = args.get('target') or (resource.target if resource else None)
            if target and target not in {'mock', 'real', 'dry_run', 'simulated', 'shadow', 'dry-run', 'simulation', 'UNKNOWN'}:
                raise ValueError()
            target = {'dry-run': 'dry_run', 'simulation': 'simulated', 'UNKNOWN': None}.get(target, target)
            candidates = [r for r in settings.registered_resources if (not target or r.target == target) and (not resource or r.id == resource.id)]
            if target and not candidates:
                raise ValueError()
            chosen = resource or next((r for r in candidates if r.owner in {'audit', 'portfolio', 'soak', 'controller'}), None) or next(iter(candidates), None)
            if resource and target and resource.target != target:
                raise ValueError()
            scope = ResourceScope(chosen.account_hash, chosen.target, resource_id) if chosen else None
        except (ValueError, KeyError, TypeError):
            abort(400)
        params = dict(period=period_name)
        for key in ('start', 'end', 'resource_id', 'target', 'limit', 'selection_id'):
            if args.get(key):
                params[key] = args[key]
        return dict(period=period, period_name=period_name, scope_obj=scope, params=params,
            cursor=args.get('cursor') or None, limit=limit, page_number=page_number,
            target={'dry_run': 'dry-run', 'simulated': 'simulation'}.get(scope.target, scope.target) if scope else 'UNKNOWN')

    def contextual_url(path, context, **values):
        params = {**context['params'], **values}
        return path + ('?' + urlencode({k: v for k, v in params.items() if v is not None}) if params else '')

    def authorize_envelope(envelope):
        resource = settings.resource(envelope.resource_id)
        if resource.account_hash != envelope.account_hash or resource.target != envelope.target:
            abort(404)
        return resource

    def present_record(record, context, parent=None):
        authorize_envelope(record.envelope)
        fields = {name: _clean(value) for name, value in record.fields}
        for key in {'candidates': ('rank', 'screen_reason', 'coverage'),
            'decisions': ('evaluation_id', 'provider', 'model', 'risk_verdict'),
            'evaluations': ('action', 'confidence', 'reason', 'terminal_event_type'),
            'holdings': ('current_price', 'evaluation_amount', 'unrealized_profit'),
            'runs': ('completed_tickers', 'total_tickers')}.get(record.kind, ()):
            fields.setdefault(key, None)
        data = {k: 'UNKNOWN · 확인되지 않음' if v is None else v for k, v in fields.items()}
        numeric = {'available_cash', 'total_evaluation', 'evaluation_amount', 'average_price', 'current_price', 'price', 'unrealized_profit'}
        for name in numeric & data.keys():
            if isinstance(data[name], (int, float)) and not isinstance(data[name], bool):
                data[name] = format(data[name], ',.10f').rstrip('0').rstrip('.') + '원'
        for name in {'quantity', 'orderable_quantity', 'filled_quantity', 'remaining_quantity', 'requested_qty', 'filled_qty', 'unfilled_qty'} & data.keys():
            if isinstance(data[name], (int, float)):
                data[name] = f'{data[name]:,}주'
        if isinstance(data.get('confidence'), (int, float)):
            data['confidence'] = f'{data["confidence"]:.2f}'
        back = contextual_url(parent or OPERATIONAL_VIEWS.get(record.kind, ('/orders', ''))[0], context,
            **{key: context[value] for key, value in (('cursor', 'cursor'), ('page', 'page_number')) if value in context})
        return dict(**data, id=record.record_id, resource_id=record.resource_id,
            kind=record.kind, fields=fields, source=source_presentation(record.envelope, record.record_id),
            source_ids=record.selection.source_ids, selection_id=record.selection.selection_id,
            numerator=record.selection.numerator, denominator=record.selection.denominator,
            provenance=record.envelope.provenance, completeness=record.envelope.completeness,
            detail_url=_record_path('records', record.resource_id, record.record_id) + '?' + urlencode({'back': back}),
            evidence_url=_record_path('evidence', record.resource_id, record.record_id) + '?' + urlencode({'back': back}),
            back_url=back)

    def observer_status():
        # Inspect only the operational DB. Never construct observer/transport or create its schema.
        result = dict(state='NOT_STARTED', heartbeat_age_seconds=None, started_at=None, stopped_at=None,
                      failure_code=None, deliveries={})
        path, _ = settings.validate_topology()
        if not path.is_file():
            return result
        try:
            with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=1) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute('PRAGMA query_only=ON')
                tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if 'alert_observer' in tables:
                    row = conn.execute('SELECT * FROM alert_observer WHERE singleton=1').fetchone()
                    if row:
                        state = row['state'] if row['state'] in {'RUNNING', 'STOPPED', 'FAILED', 'STALE', 'NOT_STARTED'} else 'UNKNOWN'
                        age = max(0, clock().timestamp() - row['heartbeat_at']) if row['heartbeat_at'] is not None else None
                        # Default observer contract: 30s cadence, 180s stale threshold.
                        result.update(state='STALE' if state == 'RUNNING' and age is not None and age > 180 else state,
                            heartbeat_age_seconds=age, started_at=kst_time(datetime.fromtimestamp(row['started_at'], timezone.utc)) if row['started_at'] else None,
                            stopped_at=kst_time(datetime.fromtimestamp(row['stopped_at'], timezone.utc)) if row['stopped_at'] else None,
                            failure_code=_clean(row['failure_code']))
                if 'alert_outbox' in tables:
                    result['deliveries'] = {str(row[0]): row[1] for row in conn.execute('SELECT state,COUNT(*) FROM alert_outbox GROUP BY state LIMIT 16')}
        except (ValueError, TypeError, sqlite3.Error, OSError):
            result['state'], result['failure_code'] = 'UNKNOWN', 'OBSERVER_STATUS_UNAVAILABLE'
        return result

    def operational_view(view_id, api=False):
        context = query_context()
        reader = app.extensions['evidence_service']
        overview = reader.overview(context['scope_obj'])
        path, title = OPERATIONAL_VIEWS[view_id]
        common = dict(title=title, current_path=path, operator_name=g.operator_session.actor,
            csrf_token=generate_csrf(), scope='저장 증거 · 각 원천은 독립 관측이며 동시에 생성된 스냅샷이 아닙니다.',
            critical_count='UNKNOWN', **context)
        sources = [source_presentation(s) for s in overview.sources]
        for s in overview.sources:
            authorize_envelope(s)
        common.update(source=sources[0] if sources else dict(queried_at=kst_time(clock())), sources=sources)
        risk = tuple(overview.unresolved)
        risk_selection = _selection_id(risk)
        risk_complete = bool(overview.sources) and all(s.query_status == 'OK' for s in overview.sources if s.schema_owner in {'audit', 'soak', 'portfolio'})
        common.update(risk_rows=[present_record(r, context, '/orders') for r in risk[:100]],
            risk_total=len(risk) if risk_complete else None,
            risk_url=contextual_url('/orders', context, selection_id=risk_selection),
            risk_selection=risk_selection, observer=observer_status())
        common['safety_blocks'] = [present_record(row, context, '/') for row in overview.safety_blocks[:100]]
        if app.extensions['alert_store'] is not None:
            try:
                from .alert_models import Severity
                registered = {r.id: r for r in settings.registered_resources}
                episodes = tuple(episode for episode in app.extensions['alert_store'].list_incidents(active=True, limit=100)
                    if episode.subject.resource_id in registered
                    and registered[episode.subject.resource_id].account_hash == episode.subject.account_hash
                    and registered[episode.subject.resource_id].target == episode.subject.target
                    and (context['scope_obj'] is None or (episode.subject.account_hash == context['scope_obj'].account_hash
                         and episode.subject.target == context['scope_obj'].target)))
                common['critical_count'] = sum(1 for episode in episodes if episode.severity == Severity.CRITICAL)
                common['active_incidents'] = episodes
            except (ValueError, sqlite3.Error, OSError):
                common['active_incidents'] = ()
        else:
            common['active_incidents'] = ()
        accounts = []
        for account in overview.accounts:
            authorize_envelope(account.envelope)
            accounts.append(dict(snapshot_id=account.snapshot_id,
                available_cash=amount(account.available_cash), total_evaluation=amount(account.total_evaluation),
                unrealized_value=amount(account.unrealized_value), latest_attempt_status=account.latest_attempt_status,
                selection_id=account.selection.selection_id,
                source=source_presentation(account.envelope, account.snapshot_id, last_success_id=account.snapshot_id,
                    latest_attempt_id=account.latest_attempt_id),
                holdings_count=len(account.holdings) if account.snapshot_id else None,
                orders_count=len(account.orders) if account.snapshot_id else None,
                fills_count=len(account.fills) if account.snapshot_id else None,
                holdings_url=contextual_url('/holdings', context, resource_id=account.envelope.resource_id, selection_id=account.selection.selection_id),
                orders_url=contextual_url('/orders', context, resource_id=account.envelope.resource_id, selection_id=account.selection.selection_id),
                fills_url=contextual_url('/fills', context, resource_id=account.envelope.resource_id, selection_id=account.selection.selection_id),
                detail_url=_record_path('records', account.envelope.resource_id, 'account:' + (account.snapshot_id or 'UNKNOWN')) + '?' + urlencode({'back': contextual_url('/account', context)})))
        common['accounts'] = accounts
        workers = []
        for worker in overview.workers:
            authorize_envelope(worker.envelope)
            workers.append(dict(id=worker.worker_id, state=worker.state,
                expected_running=worker.expected_running, cadence_seconds=worker.cadence_seconds,
                lease_observed_at=kst_time(worker.lease_observed_at),
                lease_age_seconds=None if not worker.lease_observed_at else max(0, (clock()-worker.lease_observed_at).total_seconds()),
                source_ids=worker.source_ids, snapshot_id=worker.snapshot_id,
                source=source_presentation(worker.envelope, worker.worker_id),
                detail_url=_record_path('records', worker.envelope.resource_id, 'worker:' + worker.worker_id) + '?' + urlencode({'back': contextual_url('/workers', context)})))
        common['workers'] = workers
        if view_id in {'overview', 'account', 'workers'}:
            activity = reader.list_records('runs', context['scope_obj'], context['period'], limit=5) if view_id == 'overview' else None
            common.update(activity_rows=[present_record(r, context, '/runs') for r in activity.rows] if activity else [],
                          rows=[], total=None, columns=[])
            template = 'operator/overview.html' if view_id == 'overview' else 'operator/list.html'
        else:
            selection = request.args.get('selection_id')
            selected_account = next((a for a in overview.accounts if a.selection.selection_id == selection), None)
            if selection:
                if view_id == 'orders' and selection == risk_selection:
                    records, total = risk, len(risk) if risk_complete else None
                elif selected_account and view_id in {'holdings', 'orders', 'fills'}:
                    records = getattr(selected_account, view_id)
                    total = len(records) if selected_account.snapshot_id else None
                else:
                    abort(400)
                start = (context['page_number'] - 1) * context['limit']
                page = RecordPage(view_id, selection, tuple(records[start:start + context['limit']]), total)
                more = start + context['limit'] < len(records)
                next_url = contextual_url(path, context, page=context['page_number'] + 1) if more else None
            else:
                try:
                    page = reader.list_records(view_id, context['scope_obj'], context['period'], context['cursor'], context['limit'])
                except ValueError:
                    abort(400)
                if page.total == 0 and not page.sources:
                    page = RecordPage(view_id, page.selection_id, page.rows, None, page.cursor, page.sources)
                next_url = contextual_url(path, context, cursor=page.cursor, page=context['page_number'] + 1) if page.cursor else None
            rows = [present_record(r, context, path) for r in page.rows]
            keys = list(dict.fromkeys(k for row in rows for k in row['fields']))
            columns = [dict(key=k, label=LABELS.get(k, k), numeric=k in {'confidence', 'quantity', 'price', 'requested_qty', 'filled_qty', 'unfilled_qty'}) for k in keys[:12]]
            columns += [dict(key='resource_id', label='원천 ID'), dict(key='provenance', label='증거 구분'), dict(key='completeness', label='완전성')]
            common.update(rows=rows, total=page.total, columns=columns, selection_id=page.selection_id,
                next_url=next_url, previous_url=contextual_url(path, context) if context['page_number'] > 1 else None,
                exact_selection=bool(selection), diagnostic_code=page.diagnostic_code,
                page_sources=[source_presentation(s) for s in page.sources], excluded_count='UNKNOWN', unknown_count='UNKNOWN')
            if view_id == 'decisions':
                try:
                    evaluations = reader.list_records('evaluations', context['scope_obj'], context['period'],
                        request.args.get('eval_cursor') or None, context['limit'])
                except ValueError:
                    abort(400)
                common.update(evaluation_rows=[present_record(row, context, '/decisions') for row in evaluations.rows],
                    evaluation_total=evaluations.total if evaluations.sources else None,
                    evaluation_selection=evaluations.selection_id,
                    evaluation_next=contextual_url(path, context, eval_cursor=evaluations.cursor) if evaluations.cursor else None)
            template = 'operator/list.html'
        common['view_id'] = view_id
        html = render_template(template, **common)
        if api:
            # Same HTML/facts as the native GET view; JS does not invent evidence.
            module = app.jinja_env.get_template('operator/macros.html').module
            status_html = ''.join(str(module.source_metadata(source)) for source in sources)
            return dict(view_id=view_id, rendered_html=html, status_html=status_html,
                sources=sources, queried_at=kst_time(clock()), source_observed_at=sources[0]['observed_at'] if sources else 'UNKNOWN',
                query_status='FAILED' if any(s['query_status'] == 'FAILED' for s in sources) else 'SUCCESS',
                expires_at=g.operator_session.expires_at.isoformat(), expires_at_kst=kst_time(g.operator_session.expires_at), login_url='/login', selection_id=common.get('selection_id'),
                total=common.get('total'), status=dict(queried_at=kst_time(clock()), sources=sources))
        return html

    def amount(value):
        return None if value is None else format(value, ',.10f').rstrip('0').rstrip('.')

    for view_id, (path, _) in OPERATIONAL_VIEWS.items():
        def builder(api=False, selected=view_id):
            return operational_view(selected, api=api)
        app.extensions['operator_view_builders'][view_id] = builder
        app.add_url_rule(path, endpoint='operator_' + view_id, view_func=builder, methods=['GET'])

    def record_view(resource_id, record_id, evidence=False):
        try:
            resource = settings.resource(resource_id)
            if len(record_id) > 512 or any(c in record_id for c in ('/', '\\', '\r', '\n', '\t')):
                raise ValueError()
            back = safe_return_path(request.args.get('back'), app)
            # Resolve only fixed, trusted GET filters from the preserved parent URL.
            back_args = dict(parse_qsl(urlsplit(back).query, max_num_fields=16))
            reader = app.extensions['evidence_service']
            scoped = ResourceScope(resource.account_hash, resource.target, resource.id)
            if record_id.startswith('account:'):
                account = next((a for a in reader.overview(scoped).accounts if 'account:' + (a.snapshot_id or 'UNKNOWN') == record_id), None)
                if account is None:
                    account = ReadOnlyPortfolioRepository(resource, clock=clock).account(record_id.split(':', 1)[1])
                    if account.snapshot_id is None:
                        raise EvidenceUnavailable('RECORD_NOT_FOUND')
                record = EvidenceRecord(record_id, 'account', account.envelope, account.selection,
                    (('available_cash', account.available_cash), ('total_evaluation', account.total_evaluation),
                     ('unrealized_value', account.unrealized_value), ('snapshot_id', account.snapshot_id),
                     ('latest_attempt_status', account.latest_attempt_status)))
            elif record_id.startswith('worker:'):
                worker = next((w for w in reader.overview(scoped).workers if 'worker:' + w.worker_id == record_id), None)
                if worker is None:
                    raise EvidenceUnavailable('RECORD_NOT_FOUND')
                selection = EvidenceSelection(_selection_id(()), resource_id, 'workers', scoped, (record_id,), worker.snapshot_id, worker.source_ids, 1, 1)
                record = EvidenceRecord(record_id, 'workers', worker.envelope, selection,
                    (('state', worker.state), ('expected_running', worker.expected_running), ('cadence_seconds', worker.cadence_seconds),
                     ('lease_observed_at', kst_time(worker.lease_observed_at)), ('snapshot_id', worker.snapshot_id)))
            elif record_id.startswith('campaigns:'):
                record = next((row for row in reader.overview(scoped).safety_blocks if row.record_id == record_id), None)
                if record is None:
                    record = (reader.get_evidence if evidence else reader.get_record)(resource_id, record_id)
            else:
                record = (reader.get_evidence if evidence else reader.get_record)(resource_id, record_id)
            authorize_envelope(record.envelope)
        except (ValueError, EvidenceUnavailable):
            abort(404)
        context = dict(params=back_args)
        row = present_record(record, context, urlsplit(back).path)
        parent_kind = {'evaluations': 'decisions', 'evaluation_events': 'decisions', 'campaigns': 'overview', 'freezes': 'orders'}.get(record.kind, record.kind)
        parent = OPERATIONAL_VIEWS.get(parent_kind, ('/orders', '주문'))
        fields = {LABELS.get(k, k): ('UNKNOWN · 확인되지 않음' if v is None else _clean(v)) for k, v in row['fields'].items()}
        return render_template('operator/detail.html', title='정제된 원천 증거' if evidence else parent[1] + ' 상세',
            current_path=parent[0], operator_name=g.operator_session.actor, csrf_token=generate_csrf(),
            target={'simulated': 'simulation', 'dry_run': 'dry-run'}.get(resource.target, resource.target),
            source=row['source'], row=row, fields=fields, evidence=evidence, critical_count='UNKNOWN',
            scope='저장 증거 · 실행 권한 없음', back_url=back)

    app.add_url_rule('/records/<resource_id>/<record_id>', 'operator_record', record_view, methods=['GET'])
    app.add_url_rule('/evidence/<resource_id>/<record_id>', 'operator_evidence',
        lambda resource_id, record_id: record_view(resource_id, record_id, evidence=True), methods=['GET'])
    app.extensions.update(operator_query_context=query_context, operator_contextual_url=contextual_url,
        operator_source_presentation=source_presentation, operator_present_record=present_record,
        operator_observer_status=observer_status)

    app.wsgi_app = FixedProxyBoundary(app.wsgi_app, settings)
    return app
