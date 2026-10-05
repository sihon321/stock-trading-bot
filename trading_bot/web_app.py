"""Authenticated saved-evidence HTTP surface; no trading runtime capabilities."""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import sqlite3
import ipaddress
import secrets
import re
from uuid import uuid4
from urllib.parse import urlsplit, parse_qsl, urlencode, quote

from flask import Flask, Response, abort, g, jsonify, redirect, render_template, request, session
from flask_wtf.csrf import CSRFProtect, CSRFError, generate_csrf
from werkzeug.exceptions import HTTPException

from .web_auth import WebAuth
from .web_config import WebSettings
from .web_store import WebStore
from .web_evidence import OperatorEvidenceService, account_repository, EvidenceUnavailable, _clean
from .web_models import ResourceScope, PeriodSelection, KST, EvidenceRecord, EvidenceSelection, RecordPage

OPERATIONAL_VIEWS = {
    'overview': ('/', '안전 개요'), 'account': ('/account', '계좌 요약'),
    'holdings': ('/holdings', '보유 종목'), 'candidates': ('/candidates', '선별 후보'),
    'decisions': ('/decisions', 'LLM 판단'), 'orders': ('/orders', '주문'),
    'fills': ('/fills', '체결'), 'runs': ('/runs', '실행 이력'), 'workers': ('/workers', '작업 상태'),
}
RESERVED_GET_PATHS = {'/alerts', '/reports', '/validation/replay', '/validation/backtest',
    '/validation/shadow', '/validation/soak', '/validation/calibration', '/validation/readiness', '/controls'}
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
    'lease_observed_at': '리스 관측', 'lease_age_seconds': '리스 경과(년·개월·일 시:분:초)',
    'snapshot_id': '스냅샷 ID', 'source_ids': '원천 연결 ID', 'outcome_code': '선별 결과',
    'reason_code': '사유 코드', 'rank': '선별 순위', 'provider': '제공자', 'model': '모델',
    'risk_verdict': '위험 검증', 'evaluation_id': '일일 평가 ID', 'run_kind': '실행 종류',
    'target': '대상', 'trading_date_kst': '거래일(KST)', 'completed_tickers': '완료 종목 수',
    'total_tickers': '전체 종목 수', 'campaign_id': '캠페인 ID', 'state_identity': '상태 ID',
    'available_cash': '가용 현금', 'total_evaluation': '총 평가액', 'latest_attempt_status': '최근 시도 완전성',
    'unrealized_value': '미실현 손익', 'unrealized_return': '평가수익률',
}


def kst_time(value):
    return 'UNKNOWN' if value is None else value.astimezone(KST).strftime('%Y-%m-%d %H:%M:%S KST')


def elapsed_time(seconds, observed_at):
    """Completed calendar months in KST, then remaining days and whole seconds."""
    if seconds is None or observed_at is None:
        return 'UNKNOWN'
    try:
        if observed_at.tzinfo is None:
            return 'UNKNOWN'
        start = observed_at.astimezone(KST)
        end = start + timedelta(seconds=max(0, int(seconds)))
        months = (end.year - start.year) * 12 + end.month - start.month

        def anniversary(offset):
            year, month = divmod(start.year * 12 + start.month - 1 + offset, 12)
            return start.replace(year=year, month=month + 1,
                day=min(start.day, monthrange(year, month + 1)[1]))

        if anniversary(months) > end:
            months -= 1
        years, months_remaining = divmod(months, 12)
        days, remainder = divmod(int((end - anniversary(months)).total_seconds()), 86400)
        hours, remainder = divmod(remainder, 3600)
    except (ValueError, TypeError, OverflowError, AttributeError):
        return 'UNKNOWN'
    minutes, seconds = divmod(remainder, 60)
    return f'{years}년 {months_remaining}개월 {days}일 {hours:02d}:{minutes:02d}:{seconds:02d}'


def source_presentation(envelope, record_id=None, **extra):
    return dict(resource_id=envelope.resource_id, record_id=record_id or 'UNKNOWN',
        observed_at=kst_time(envelope.source_observed_at), queried_at=kst_time(envelope.query_at),
        age=elapsed_time(envelope.age_seconds, envelope.source_observed_at),
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
    if report_service is None:
        from .web_reports import SavedReportService
        report_service = SavedReportService(settings, store=store, clock=clock)
    if alert_store is None:
        from .alert_store import AlertStore
        alert_store = AlertStore(settings.operational_db_path, clock=clock)
    app.extensions.update(web_settings=settings, web_store=store, web_auth=auth,
        evidence_service=evidence_service or OperatorEvidenceService(settings, clock=clock), report_service=report_service, alert_store=alert_store,
        operator_clock=clock, operator_view_builders={})
    csrf = CSRFProtect(app)

    from .web_control import WebControlRequestService, ACTIONS
    control_service = WebControlRequestService(settings.control_resource, clock=clock) if settings.control_resource else None
    app.extensions['control_request_service'] = control_service

    def saved_control_health():
        reader = app.extensions['evidence_service']
        try:
            health = reader.service_health()
            controls = reader.control_states()
        except (OSError, ValueError, sqlite3.Error):
            return (), ()
        scopes = set(settings.control_resource.registered_scopes) if control_service else set()
        return (tuple(row for row in health if (row.envelope.account_hash, row.envelope.target) in scopes),
            tuple(row for row in controls if control_service and row.envelope.resource_id == settings.control_resource.resource_id))

    def resume_request_ready(facts, health):
        if not facts or not control_service:
            return False
        now = clock()
        healthy_scopes = {(row.envelope.account_hash, row.envelope.target) for row in health
            if row.kind == 'RISK' and row.state in {'RUNNING', 'WAITING', 'NOT_EXPECTED'}
            and row.mutation_ready is not False and not row.manual_attention
            and row.control_revision == facts['state'].acceptance_revision
            and row.envelope.query_status == 'OK' and row.envelope.completeness == 'COMPLETE'
            and row.envelope.freshness != 'STALE'
            and row.envelope.source_observed_at is not None
            and 0 <= (now-row.envelope.source_observed_at).total_seconds() <= 180}
        return set(settings.control_resource.registered_scopes).issubset(healthy_scopes)

    def controls_view(resource_id=None, *, result=None, error=None, note='', submitted_action=None):
        if resource_id is not None and (control_service is None or resource_id != settings.control_resource.resource_id):
            abort(404)
        facts = None
        if control_service is not None:
            try:
                facts = control_service.snapshot(actor=g.operator_session.actor)
            except (OSError, ValueError, sqlite3.Error):
                error = error or '제어 저장소를 확인할 수 없습니다. 상태는 UNKNOWN입니다.'
        health, saved_controls = saved_control_health()
        audits = {}
        if facts:
            try:
                with store.connection() as conn:
                    for row in facts['requests']:
                        saved = conn.execute("SELECT details_json FROM web_actions WHERE action='CONTROL_REQUEST' "
                            "AND resource_id=? AND json_extract(details_json,'$.request_id')=? LIMIT 1",
                            (settings.control_resource.resource_id, row['request_id'])).fetchone()
                        audits[row['request_id']] = dict(state='기록됨' if saved else '미연결 · 확인 대기',
                            note=_clean(json.loads(saved[0]).get('note', '')) if saved else '')
            except (OSError, ValueError, sqlite3.Error):
                audits = {}
        form_ids = {action:str(uuid4()) for action in ACTIONS}
        form_revisions = {action:facts['state'].acceptance_revision if facts else 0 for action in ACTIONS}
        if result and submitted_action in ACTIONS and (result.audit_pending or result.status == 'UNAVAILABLE'):
            # A manual retry repairs this exact correlation; it cannot create a second request.
            form_ids[submitted_action] = result.request_id
            form_revisions[submitted_action] = int(request.form['expected_revision'])
        common = common_view('운영 제어', '/controls', facts=facts, result=result, error=error,
            note=note, resource_id=settings.control_resource.resource_id if control_service else None,
            control_scopes=settings.control_resource.registered_scopes if control_service else (),
            resume_allowed=resume_request_ready(facts, health),
            control_health=[dict(kind=row.kind, state=row.state, reason=_clean(row.reason_code),
                source=source_presentation(row.envelope, row.subject_id), source_ids=row.source_ids,
                last_progress=kst_time(row.last_progress_at), login_source_id=row.login_source_id,
                session_source_id=row.session_source_id, manual_attention=row.manual_attention,
                control_revision=row.control_revision, mutation_ready=row.mutation_ready) for row in health],
            saved_controls=[source_presentation(row.envelope, row.request_id) for row in saved_controls],
            form_ids=form_ids, form_revisions=form_revisions, control_audits=audits,
            applied_at=kst_time(facts['state'].applied.applied_at) if facts else 'UNKNOWN')
        common.update(target='mock' if control_service else 'UNKNOWN',
            scope='등록된 설치 전체 · 제어 요청 · 적용은 서비스가 검증합니다.')
        return render_template('operator/controls.html', **common)

    @app.get('/controls')
    @app.get('/controls/<resource_id>')
    def controls(resource_id=None):
        if request.args:
            abort(400)
        return controls_view(resource_id)

    @app.post('/controls/<resource_id>/<action>')
    def request_control(resource_id, action):
        if control_service is None or resource_id != settings.control_resource.resource_id or action not in ACTIONS:
            abort(404)
        if request.args:
            abort(400)
        note = _clean(request.form.get('note', ''))[:500]
        try:
            facts = None
            if action == 'resume':
                try:
                    facts = control_service.snapshot(actor=g.operator_session.actor)
                except (OSError, ValueError, sqlite3.Error):
                    pass
            result = control_service.append_request(action, request.form, actor=g.operator_session.actor,
                audit=store.append_control_action,
                resume_allowed=action != 'resume' or resume_request_ready(facts, saved_control_health()[0]))
        except (ValueError, TypeError):
            return controls_view(resource_id, error=FORM_ERROR, note=note), 400
        status = 409 if result.status == 'CONFLICT' else 503 if result.status == 'UNAVAILABLE' or result.audit_pending else 200
        error = ('재개 요청에 필요한 최신 서비스 증거를 확인할 수 없습니다. 차단 상태를 유지합니다.'
            if result.reason_code == 'SAVED_HEALTH_UNAVAILABLE' else '제어 revision이 변경되었거나 요청 ID가 충돌했습니다. 최신 상태를 확인하세요.') if status == 409 else (
            '제어 요청을 확인할 수 없습니다. 저장 증거를 새로 조회하세요.' if result.status == 'UNAVAILABLE' else None)
        return controls_view(resource_id, result=result, error=error, note=note, submitted_action=action), status

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
            # Anonymous icon/poll requests must not invalidate an open login form.
            # A presented invalid or expired operator session still gets cleared.
            if 'operator_token' in session:
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
        if g.get('operator_session') and request.endpoint in {'generate_report', 'acknowledge_alert'}:
            action_audit('ALERT_ACK' if request.endpoint == 'acknowledge_alert' else 'REPORT_GENERATE', 'INVALID_REQUEST')
            if request.endpoint == 'acknowledge_alert':
                return alerts_view(request.view_args['episode_id'],error=FORM_ERROR,note=_clean(request.form.get('note',''))),400
        return safe_error('INVALID_REQUEST', 400)

    @app.errorhandler(HTTPException)
    def http_error(error):
        if error.code == 413 and g.get('operator_session') and request.endpoint in {'generate_report','acknowledge_alert'}:
            action_audit('ALERT_ACK' if request.endpoint == 'acknowledge_alert' else 'REPORT_GENERATE','REQUEST_BOUND')
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

    @app.get('/api/session')
    def api_session():
        return jsonify(expires_at=g.operator_session.expires_at.isoformat(), login_url='/login')

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
            severity = args.get('severity') or None
            active = args.get('active') or None
            if severity not in {None, 'INFO', 'WARNING', 'CRITICAL'} or active not in {None, '0', '1'}:
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            abort(400)
        params = dict(period=period_name)
        for key in ('start', 'end', 'resource_id', 'target', 'limit', 'selection_id', 'severity', 'active'):
            if args.get(key):
                params[key] = args[key]
        return dict(period=period, period_name=period_name, scope_obj=scope, params=params,
            cursor=args.get('cursor') or None, limit=limit, page_number=page_number,
            alert_severity=severity, alert_active=active,
            target={'dry_run': 'dry-run', 'simulated': 'simulation'}.get(scope.target, scope.target) if scope else 'UNKNOWN')

    def contextual_url(path, context, **values):
        params = {**context['params'], **values}
        return path + ('?' + urlencode({k: v for k, v in params.items() if v is not None}) if params else '')

    def incident_selection(context, *, active, severity=None, period=None, include_page=False):
        # Apply the complete registered subject scope before counting or bounding rows.
        # COUNT and page IDs share a read transaction in the operational database.
        alerts = app.extensions['alert_store']
        if alerts is None:
            raise ValueError('alert storage unavailable')
        alerts._verify_ownership()
        scope = context['scope_obj']
        resources = tuple(r for r in settings.registered_resources
            if scope is None or (r.account_hash == scope.account_hash and r.target == scope.target
                and (not scope.resource_id or r.id == scope.resource_id)))
        subjects = ' OR '.join("(json_extract(subject_json,'$[0]')=? AND "
            "json_extract(subject_json,'$[1]')=? AND json_extract(subject_json,'$[2]')=?)" for _ in resources) or '0'
        where = 'active=? AND (' + subjects + ')'
        args = [int(active), *(v for r in resources for v in (r.id, r.account_hash, r.target))]
        if severity:
            where += ' AND severity=?'
            args.append(severity)
        if period is not None:
            where += ' AND last_at>=? AND last_at<?'
            args.extend((period.start.timestamp(), period.end.timestamp()))
        with sqlite3.connect(alerts.path.as_uri() + '?mode=ro', uri=True, timeout=1) as conn:
            conn.execute('PRAGMA query_only=ON')
            conn.execute('BEGIN')
            total = conn.execute('SELECT COUNT(*) FROM alert_episodes WHERE ' + where, args).fetchone()[0]
            ids = ()
            if include_page:
                offset = (context['page_number'] - 1) * context['limit']
                ids = tuple(row[0] for row in conn.execute('SELECT episode_id FROM alert_episodes WHERE ' + where
                    + ' ORDER BY last_at DESC,episode_id LIMIT ? OFFSET ?', (*args, context['limit'], offset)))
        return total, ids

    def critical_summary(context):
        scope = context['scope_obj']
        params = {k: context['params'][k] for k in ('resource_id', 'limit') if k in context['params']}
        if scope is not None:
            params['target'] = scope.target
        params.update(severity='CRITICAL', active='1')
        result = dict(critical_count='UNKNOWN', critical_url='/alerts?' + urlencode(params))
        try:
            result['critical_count'], _ = incident_selection(context, active=True, severity='CRITICAL')
        except (ValueError, sqlite3.Error, OSError):
            pass
        return result

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
            'holdings': ('current_price', 'evaluation_amount', 'unrealized_profit', 'unrealized_return'),
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
        if isinstance(data.get('unrealized_return'), (int, float)):
            data['unrealized_return'] = f'{data["unrealized_return"]:.2f}%'
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
        result = dict(state='NOT_STARTED', heartbeat_age_seconds=None, heartbeat_age='UNKNOWN', started_at=None, stopped_at=None,
                      failure_code=None, deliveries={})
        heartbeat_at = None
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
                        heartbeat_at = datetime.fromtimestamp(row['heartbeat_at'], timezone.utc) if row['heartbeat_at'] is not None else None
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
        result['heartbeat_age'] = elapsed_time(result['heartbeat_age_seconds'], heartbeat_at)
        return result

    def operational_view(view_id, api=False):
        context = query_context()
        reader = app.extensions['evidence_service']
        overview = reader.overview(context['scope_obj'])
        path, title = OPERATIONAL_VIEWS[view_id]
        common = dict(title=title, current_path=path, operator_name=g.operator_session.actor,
            expires_at=g.operator_session.expires_at.isoformat(),
            csrf_token=generate_csrf(), scope='저장 증거 · 각 원천은 독립 관측이며 동시에 생성된 스냅샷이 아닙니다.',
            **critical_summary(context), **context)
        visible_sources = tuple(a.envelope for a in overview.accounts) if view_id in {'account','holdings'} else overview.sources
        sources = [source_presentation(s) for s in visible_sources]
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
                _, ids = incident_selection(context, active=True, include_page=True)
                common['active_incidents'] = tuple(app.extensions['alert_store'].get_incident(i) for i in ids)
            except (ValueError, sqlite3.Error, OSError):
                common['active_incidents'] = ()
        else:
            common['active_incidents'] = ()
        accounts = []
        for account in overview.accounts:
            authorize_envelope(account.envelope)
            accounts.append(dict(snapshot_id=account.snapshot_id,
                balance_only=account.envelope.schema_owner == 'account_view',
                cash_label='예수금' if account.envelope.schema_owner == 'account_view' else '가용 현금',
                available_cash=amount(account.available_cash), total_evaluation=amount(account.total_evaluation),
                unrealized_value=amount(account.unrealized_value), latest_attempt_status=account.latest_attempt_status,
                latest_attempt_at=kst_time(account.latest_attempt_at),
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
            lease_age = None if not worker.lease_observed_at else max(0, (clock()-worker.lease_observed_at).total_seconds())
            workers.append(dict(id=worker.worker_id, state=worker.state,
                expected_running=worker.expected_running, cadence_seconds=worker.cadence_seconds,
                lease_observed_at=kst_time(worker.lease_observed_at),
                lease_age_seconds=lease_age, lease_age=elapsed_time(lease_age, worker.lease_observed_at),
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
            if view_id == 'holdings':
                keys = ['ticker', 'quantity' if any('quantity' in row['fields'] for row in rows) else 'total_quantity',
                    'orderable_quantity', 'average_price', 'current_price', 'evaluation_amount', 'unrealized_profit', 'unrealized_return']
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

    def record_view(resource_id, record_id, evidence=False, api=False):
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
                    account = account_repository(resource, clock=clock).account(record_id.split(':', 1)[1])
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
        fields = {LABELS.get(k, k): (elapsed_time(v, record.envelope.source_observed_at) if k == 'lease_age_seconds' else 'UNKNOWN · 확인되지 않음' if v is None else _clean(v)) for k, v in row['fields'].items()}
        common = dict(title='정제된 원천 증거' if evidence else parent[1] + ' 상세',
            current_path=parent[0], operator_name=g.operator_session.actor, csrf_token=generate_csrf(),
            target={'simulated': 'simulation', 'dry_run': 'dry-run'}.get(resource.target, resource.target),
            source=row['source'], row=row, fields=fields, evidence=evidence,
            **critical_summary(dict(scope_obj=scoped, params=dict(resource_id=resource.id))),
            scope='저장 증거 · 실행 권한 없음', back_url=back,
            expires_at=g.operator_session.expires_at.isoformat(), view_id='evidence' if evidence else 'record',
            selection_id=record.selection.selection_id)
        return saved_response('operator/detail.html',common,api)

    app.add_url_rule('/records/<resource_id>/<record_id>', 'operator_record', record_view, methods=['GET'])
    app.add_url_rule('/evidence/<resource_id>/<record_id>', 'operator_evidence',
        lambda resource_id, record_id: record_view(resource_id, record_id, evidence=True), methods=['GET'])
    app.extensions.update(operator_query_context=query_context, operator_contextual_url=contextual_url,
        operator_source_presentation=source_presentation, operator_present_record=present_record,
        operator_observer_status=observer_status)
    for record_kind in ('record','evidence'):
        app.extensions['operator_view_builders'][record_kind] = lambda api=False, kind=record_kind: record_view(
            request.args.get('resource_id',''),request.args.get('record_id',''),kind=='evidence',api)

    validation_names = dict(replay='Replay', backtest='백테스트', shadow='LLM Shadow',
        soak='모의투자 Soak', calibration='위험 보정', readiness='준비도')

    def action_audit(action, code, resource_id=None):
        store.append_action(actor=g.operator_session.actor, action=action, result_code=code,
            resource_id=resource_id, at=clock())

    def common_view(title, path, view_id=None, **values):
        return dict(title=title, current_path=path, view_id=view_id,
            operator_name=g.operator_session.actor, csrf_token=generate_csrf(),
            expires_at=g.operator_session.expires_at.isoformat(),
            **critical_summary(query_context()), params={}, source=dict(queried_at=kst_time(clock())),
            scope='저장 증거 · 실행 권한 없음', **values)

    def saved_response(template, common, api=False):
        html = render_template(template, **common)
        if not api:
            return html
        sources = common.get('sources', [common['source']])
        module = app.jinja_env.get_template('operator/macros.html').module
        return dict(view_id=common['view_id'], rendered_html=html,
            status_html=''.join(str(module.source_metadata(s)) for s in sources), sources=sources,
            queried_at=kst_time(clock()), source_observed_at=sources[0].get('observed_at', 'UNKNOWN') if sources else 'UNKNOWN',
            query_status=common.get('query_status', 'SUCCESS'), selection_id=common.get('selection_id'),
            expires_at=g.operator_session.expires_at.isoformat(), login_url='/login')

    def catalog():
        return app.extensions['report_service'].catalog()

    def validation_view(family, result_id=None, api=False):
        from .web_reports import ReportRequest
        if family not in validation_names:
            abort(404)
        if set(request.args) - {'resource_id', 'metric_id', 'record_id', 'result_id'} or any(
                len(v) > 512 or len(request.args.getlist(k)) != 1 for k,v in request.args.items()):
            abort(400)
        entry = next(e for e in catalog() if e.family == family)
        resource_id = request.args.get('resource_id') or next(iter(entry.resource_ids), None)
        path = '/validation/' + family + ('/' + quote(result_id, safe='') if result_id else '')
        common = common_view(validation_names[family], path, 'validation-' + family,
            family=family, entries=entry.resource_ids, projection=None, selected_rows=(), metric=None,
            result_id=result_id or request.args.get('result_id'), resource_id=resource_id)
        common['params'] = dict(request.args)
        if resource_id is None:
            common.update(diagnostic='NO_REGISTERED_SOURCE', selection_id='UNKNOWN')
        else:
            try:
                projection = app.extensions['report_service'].project(ReportRequest(family=family,
                    resource_id=resource_id, result_id=common['result_id']))
                rows = projection.rows
                metric_id = request.args.get('metric_id')
                if metric_id:
                    rows = projection.metric_detail(metric_id)
                    common['metric'] = next(m for m in projection.metrics if m.metric_id == metric_id)
                if request.args.get('record_id'):
                    rows = tuple(r for r in rows if r.record_id == request.args['record_id'])
                    if not rows:
                        abort(404)
                if len(rows) > settings.export_rows:
                    abort(400)
                common.update(projection=projection, selected_rows=rows,
                    source=source_presentation(projection.envelope, common['result_id']),
                    selection_id=projection.selection.selection_id, diagnostic=None)
                common['target'] = {'simulated':'simulation','dry_run':'dry-run'}.get(projection.envelope.target,projection.envelope.target)
                common['link'] = lambda **params: path + '?' + urlencode(dict(resource_id=resource_id,
                    **({'result_id':common['result_id']} if common['result_id'] and not result_id else {}), **params))
            except (ValueError, KeyError, StopIteration):
                abort(400)
        return saved_response('operator/validation.html', common, api)

    app.add_url_rule('/validation/<family>', 'operator_validation', validation_view)
    app.add_url_rule('/validation/<family>/<result_id>', 'operator_validation_result', validation_view)
    for family in validation_names:
        app.extensions['operator_view_builders']['validation-' + family] = (
            lambda api=False, selected=family: validation_view(selected, request.args.get('result_id'), api))

    def reports_view(api=False, artifact=None, error=None):
        common = common_view('보고서', '/reports', 'reports', catalog=catalog(), artifact=artifact,
            error=error, generated_at=kst_time(artifact.generated_at) if artifact else None,
            resource_targets={r.id:r.target for r in settings.registered_resources},
            today=clock().astimezone(KST).date().isoformat())
        return saved_response('operator/reports.html', common, api)

    app.add_url_rule('/reports', 'operator_reports', reports_view)
    app.extensions['operator_view_builders']['reports'] = reports_view

    @app.post('/reports/generate')
    def generate_report():
        from .web_reports import ReportRequest, ReportGenerationError
        allowed = {'csrf_token','family','resource_id','result_id','start','end','format'}
        try:
            if set(request.form) - allowed or any(len(request.form.getlist(k)) != 1 for k in request.form):
                raise ValueError()
            values = {k:v for k,v in request.form.items() if k not in {'csrf_token','format'} and v}
            if request.form.get('format') and request.form['format'] != 'all':
                values['formats'] = (request.form['format'],)
            report_request = ReportRequest.model_validate(values)
            settings.resource(report_request.resource_id)
            if report_request.resource_id not in next(e.resource_ids for e in catalog() if e.family == report_request.family):
                raise ValueError()
        except (ValueError, StopIteration):
            action_audit('REPORT_GENERATE', 'INVALID_REQUEST')
            return reports_view(error=FORM_ERROR), 400
        try:
            artifact = app.extensions['report_service'].generate_report(report_request, actor=g.operator_session.actor)
        except (ValueError, OSError, sqlite3.Error):
            return reports_view(error='보고서를 생성하지 못했습니다. 원천 상태와 선택 범위를 확인한 뒤 다시 시도하세요.'), 400
        return reports_view(artifact=artifact)

    def owned_artifact(artifact_id, format=None, download=False):
        try:
            if not re.fullmatch(r'[a-f0-9]{64}', artifact_id) or request.args or (download and format not in {'txt','json','csv'}):
                raise ValueError()
            owned = app.extensions['report_service'].load_owned_artifact(artifact_id, actor=g.operator_session.actor)
            settings.resource(owned.resource_id)
            if format is not None and owned.format != format:
                raise ValueError()
        except (ValueError, OSError, sqlite3.Error):
            action_audit('REPORT_DOWNLOAD', 'NOT_FOUND')
            abort(404)
        if not download:
            return render_template('operator/reports.html', **common_view('보고서', '/reports',
                catalog=catalog(), artifact=None, owned=owned,
                resource_targets={r.id:r.target for r in settings.registered_resources},
                today=clock().astimezone(KST).date().isoformat()))
        if len(owned.data) > min(settings.export_bytes, 10*1024*1024):
            abort(413)
        action_audit('REPORT_DOWNLOAD', 'SUCCEEDED', owned.resource_id)
        response = Response(owned.data, content_type={'txt':'text/plain; charset=utf-8',
            'json':'application/json; charset=utf-8', 'csv':'text/csv; charset=utf-8'}[owned.format])
        response.headers['Content-Disposition'] = f'attachment; filename="report-{artifact_id}.{owned.format}"'
        return response

    app.add_url_rule('/reports/<artifact_id>', 'operator_artifact', owned_artifact)
    app.add_url_rule('/downloads/<artifact_id>/<format>', 'operator_download',
        lambda artifact_id, format: owned_artifact(artifact_id, format, True))

    def authorized_incident(episode_id):
        if not re.fullmatch(r'[a-f0-9]{32}', episode_id):
            abort(404)
        alerts = app.extensions['alert_store']
        try:
            incident = alerts.get_incident(episode_id)
            if incident is None:
                abort(404)
            resource = settings.resource(incident.subject.resource_id)
            if resource.account_hash != incident.subject.account_hash or resource.target != incident.subject.target:
                abort(404)
            return incident
        except (ValueError, sqlite3.Error, OSError):
            abort(404)

    def present_incident(incident):
        from dataclasses import fields
        values = {f.name: _clean(getattr(incident, f.name)) for f in fields(incident)
            if f.name not in {'subject','first_observed_at','last_observed_at','recovered_at','next_reminder_at'}}
        values.update(resource_id=incident.subject.resource_id, target=incident.subject.target,
            duration=elapsed_time(incident.duration_seconds, incident.first_observed_at),
            ticker=_clean(incident.subject.ticker_or_account), family=_clean(incident.subject.problem_family),
            broker_subject=_clean(incident.subject.broker_subject),
            first=kst_time(incident.first_observed_at), last=kst_time(incident.last_observed_at),
            recovered=kst_time(incident.recovered_at), reminder=kst_time(incident.next_reminder_at),
            url='/alerts/' + incident.episode_id,
            deliveries=tuple(dict(state=a.state.value, owner=a.delivery_owner, kind=a.kind)
                for a in app.extensions['alert_store'].list_attempts(incident.episode_id)))
        return values

    def alerts_view(episode_id=None, api=False, error=None, note='', message=None):
        from dataclasses import fields
        context = query_context()
        alerts = app.extensions['alert_store']
        common = common_view('알림 상세' if episode_id else '알림', '/alerts',
            'alerts', active_rows=(), history_rows=(), incident=None, revisions=(), reads=(), attempts=(),
            observations=(), error=error, note=note, message=message, observer=observer_status(),
            unavailable=None, page_number=context['page_number'], previous_url=None, next_url=None)
        common.update(period_name=context['period_name'], params=context['params'])
        common.update(active_total=None, history_total=None, alert_severity=context['alert_severity'],
            alert_active=context['alert_active'])
        if episode_id:
            incident = authorized_incident(episode_id)
            common['incident'] = present_incident(incident)
            common['params']['episode_id'] = episode_id
            common['revisions'] = [dict(revision=r.revision, severity=r.severity.value,
                observed=kst_time(r.observed_at), source_owner=_clean(r.source_owner), source_id=_clean(r.source_id))
                for r in alerts.list_revisions(episode_id)]
            common['reads'] = [dict(revision=a.revision, actor=_clean(a.actor), at=kst_time(a.at), note=_clean(a.note))
                for a in alerts.list_acknowledgements(episode_id)]
            attempts = alerts.list_attempts(episode_id)
            common['attempts'] = [dict(kind=a.kind, state=a.state.value, revision=a.revision,
                delivery_owner=a.delivery_owner, due=kst_time(a.due_at), finalized=kst_time(a.finalized_at),
                failure_code=_clean(a.failure_code), producer_event_id=_clean(a.producer_event_id),
                producer_attempt_id=_clean(a.producer_attempt_id),
                history=tuple(dict(state=h.state.value, due=kst_time(h.due_at), failure_code=_clean(h.failure_code))
                    for h in alerts.list_delivery_history(a.event_key))) for a in attempts]
            with alerts.connection() as conn:
                common['observations'] = [dict(source_owner=_clean(r['source_owner']), source_id=_clean(r['source_id']),
                    sequence=r['sequence'], observed=kst_time(datetime.fromtimestamp(r['observed_at'], timezone.utc)))
                    for r in conn.execute('SELECT source_owner,source_id,sequence,observed_at FROM alert_observations WHERE episode_id=? ORDER BY sequence LIMIT 1000', (episode_id,))]
            common['selection_id'] = f'{episode_id}:{incident.revision}'
            common['source'] = dict(resource_id=incident.subject.resource_id, record_id=episode_id,
                observed_at=kst_time(incident.last_observed_at), queried_at=kst_time(clock()),
                age=elapsed_time(max(0,(clock()-incident.last_observed_at).total_seconds()), incident.last_observed_at),
                freshness='UNKNOWN', completeness='COMPLETE', query_status='SUCCESS', provenance='saved')
        else:
            try:
                for active, name in ((1,'active_rows'),(0,'history_rows')):
                    if context['alert_active'] is not None and int(context['alert_active']) != active:
                        continue
                    total, ids = incident_selection(context, active=active, severity=context['alert_severity'],
                        period=None if active else context['period'], include_page=True)
                    common['active_total' if active else 'history_total'] = total
                    common[name] = [present_incident(authorized_incident(i)) for i in ids]
                    if context['page_number'] * context['limit'] < total:
                        common['next_url'] = contextual_url('/alerts',context,page=context['page_number']+1)
                if context['page_number']>1:
                    common['previous_url'] = contextual_url('/alerts',context,page=context['page_number']-1)
                common['selection_id'] = proof_hash_alert(common)
            except (ValueError, sqlite3.Error, OSError):
                common.update(unavailable='ALERT_STORAGE_UNAVAILABLE', query_status='FAILED')
        return saved_response('operator/alerts.html', common, api)

    def proof_hash_alert(common):
        return hashlib.sha256(json.dumps([(r['episode_id'],r['revision'],r['acknowledged'])
            for r in (*common['active_rows'],*common['history_rows'])]).encode()).hexdigest()

    app.add_url_rule('/alerts', 'operator_alerts', alerts_view)
    app.add_url_rule('/alerts/<episode_id>', 'operator_alert', alerts_view)
    app.extensions['operator_view_builders']['alerts'] = lambda api=False: alerts_view(request.args.get('episode_id'),api)

    @app.post('/alerts/<episode_id>/ack')
    def acknowledge_alert(episode_id):
        from .alert_store import RevisionConflict
        try:
            incident = authorized_incident(episode_id)
        except HTTPException:
            action_audit('ALERT_ACK','NOT_FOUND')
            raise
        note = request.form.get('note','')
        try:
            if set(request.form) - {'csrf_token','expected_revision','note'} or any(
                    len(request.form.getlist(k)) != 1 for k in request.form) or len(note)>500:
                raise ValueError()
            revision = int(request.form.get('expected_revision',''))
            if revision<1:
                raise ValueError()
        except ValueError:
            action_audit('ALERT_ACK','INVALID_REQUEST',incident.subject.resource_id)
            return alerts_view(episode_id,error=FORM_ERROR,note=_clean(note)),400
        safe_note = _clean(note)[:500]
        try:
            app.extensions['alert_store'].acknowledge(episode_id, revision, g.operator_session.actor, note=safe_note)
        except RevisionConflict:
            action_audit('ALERT_ACK','REVISION_CONFLICT',incident.subject.resource_id)
            return alerts_view(episode_id,error='알림 상태가 변경되었습니다. 최신 증거를 확인한 뒤 읽음으로 기록하세요.', note=safe_note),409
        except (ValueError, OSError, sqlite3.Error):
            action_audit('ALERT_ACK','FAILED',incident.subject.resource_id)
            return alerts_view(episode_id,error='읽음 기록을 저장하지 못했습니다. 알림은 미확인 상태입니다. 메모를 확인하고 다시 시도하세요.',note=safe_note),503
        action_audit('ALERT_ACK','SUCCEEDED',incident.subject.resource_id)
        return alerts_view(episode_id,message='읽음으로 기록했습니다. 원천 증거의 복구 확인 전까지 활성 알림을 유지합니다.')

    app.wsgi_app = FixedProxyBoundary(app.wsgi_app, settings)
    return app
