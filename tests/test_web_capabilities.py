"""Full supported surface, with tripwires installed before target imports."""
import json
from pathlib import Path
import subprocess
import sys
import sqlite3
import re
import os


def _inventory(registry):
    values = {}
    for name, raw in registry['paths'].items():
        path = Path(raw)
        if not path.exists():
            values[name] = None
            continue
        if path.suffix == '.db':
            with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as conn:
                schema = tuple(conn.execute('SELECT type,name,sql FROM sqlite_master ORDER BY type,name'))
                tables = tuple(r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"))
                rows = {t: tuple(conn.execute('SELECT * FROM "' + t.replace('"', '""') + '"')) for t in tables}
            values[name] = (path.read_bytes(), schema, rows)
        else:
            values[name] = path.read_bytes()
    return values


def exercise(registry):
    """Called only by capability_probe after its import/write/network guards."""
    sys.modules['__main__'].FORBIDDEN += ('trading_bot.runtime','trading_bot.report_cli',
        'trading_bot.brokers','trading_bot.providers','trading_bot.preparation')
    from datetime import datetime, timezone
    from hashlib import sha256
    from html import unescape
    from trading_bot.web_config import WebSettings, ResourceDescriptor
    from trading_bot.web_store import WebStore
    from trading_bot.web_auth import WebAuth
    from trading_bot.web_reports import SavedReportService
    from trading_bot.web_evidence import OperatorEvidenceService
    from trading_bot.web_app import create_app, OPERATIONAL_VIEWS
    from trading_bot.alert_store import AlertStore
    from trading_bot.shadow_evidence import RegisteredShadowProof, SavedShadowProofCatalog
    from werkzeug.security import generate_password_hash
    from dataclasses import replace
    clock = lambda: datetime(2026, 10, 2, 1, tzinfo=timezone.utc)
    account = sha256(b'synthetic-operator-account').hexdigest()
    resources = tuple(ResourceDescriptor(id=k, path=registry['paths']['audit' if k == 'portfolio' else k],
        owner=k, account_hash=account, target='simulated' if k in {'replay','backtest','shadow'} else 'mock')
        for k in ('audit','portfolio','soak','controller','replay','backtest','shadow'))
    resources += tuple(ResourceDescriptor(id=k, path=registry['paths'][k], owner=k.removeprefix('cal-'),
        account_hash='b'*64, target='mock') for k in ('cal-audit','cal-soak'))
    settings = WebSettings(operational_db_path=Path(registry['writable_roots'][0])/'operator.db',
        artifact_root=Path(registry['writable_roots'][1]), registered_resources=resources,
        cookie_secret='synthetic-capability-cookie-secret-'*3)
    store = WebStore(settings)
    store.initialize()
    auth = WebAuth(store, clock=clock, hasher=lambda p:generate_password_hash(p, method='pbkdf2:sha256:1'))
    if store.get_operator() is None:
        auth.provision_operator('owner','synthetic-password')
    proofs = tuple(RegisteredShadowProof(**{k:v for k,v in p.items() if k != 'path'},
        document_json=Path(p['path']).read_text()) for p in registry['shadow_proofs'])
    from trading_bot.web_reports import SavedCalibrationProof, SavedReadinessFacts, proof_hash
    from trading_bot.calibration_evidence import VariantEvaluation, VariantMetrics, build_variant_catalog
    from trading_bot.replay_evidence import ReplayOutcome
    from trading_bot.promotion_readiness import ReadinessEvidence
    outcome=ReplayOutcome('run-1','000001',1,'HOLD',False,'NONE','HOLD',1000,0,'HOLD',True)
    evaluation=VariantEvaluation(build_variant_catalog()[0],VariantMetrics(1,1,0,1,0,0,0,0,0,0,0,0),(outcome,))
    calibration=SavedCalibrationProof('cal-soak','campaign-1',(evaluation,),('cal-audit','cal-soak'),
        (('run-1','000001',70000),),'0'*64)
    calibration=replace(calibration,expected_hash=proof_hash(calibration.document()))
    readiness_values={**registry['readiness'],'source_identities':tuple(registry['readiness']['source_identities'])}
    ready=SavedReadinessFacts('soak','operator-campaign',ReadinessEvidence(**readiness_values),
        (('threshold',0.8),),True,True,True,'0'*64)
    ready=replace(ready,expected_hash=proof_hash(ready.document()))
    reports = SavedReportService(settings, store=store, clock=clock, shadow_proof_catalog=SavedShadowProofCatalog(proofs),
        calibration_proof_catalog=(calibration,), readiness_proof_catalog=(ready,))
    alerts = AlertStore(settings.operational_db_path, clock=clock)
    alerts.initialize()
    app = create_app(settings, evidence_service=OperatorEvidenceService(settings, clock=clock),
        report_service=reports, alert_store=alerts, clock=clock)
    client = app.test_client()
    token = auth.authenticate('owner','synthetic-password','127.0.0.1')
    assert token
    with client.session_transaction() as session:
        session['operator_token'] = token
    baseline = _inventory(registry)
    checked = 0

    def request(path, data=None, expected=200):
        nonlocal checked
        response = client.post(path, data=data) if data is not None else client.get(path)
        assert response.status_code == expected, (path, response.status_code, response.text[:250])
        assert b'sk-test-operator-secret-sentinel' not in response.data
        assert _inventory(registry) == baseline, path
        checked += 1
        return response

    def csrf(path):
        return re.search(r'name="csrf_token" value="([^"]+)"', request(path).text)[1]

    surface = registry['surface']
    if surface == 'factory':
        request('/')
        assert 'conftest' not in sys.modules and 'trading_bot.config' not in sys.modules
    elif surface == 'routes':
        paths = [v[0] for v in OPERATIONAL_VIEWS.values()] + ['/alerts','/reports'] + [
            '/validation/'+f for f in ('replay','backtest','shadow','soak','calibration','readiness')]
        details = set()
        for path in paths:
            response = request(path)
            details.update(unescape(p) for p in re.findall(r'href="([^"]+)"', response.text)
                if p.startswith(('/records/','/evidence/','/validation/')))
        for path in sorted(details):
            response = request(path)
            for link in re.findall(r'href="([^"]+)"', response.text):
                if link.startswith('/evidence/'):
                    request(unescape(link))
        for view in app.extensions['operator_view_builders']:
            if view not in {'record','evidence'}:
                request('/api/views/'+view)
        for prefix in ('records','evidence'):
            request('/'+prefix+'/audit/runs:operator-run')
            request('/api/views/'+('record' if prefix=='records' else prefix)+'?resource_id=audit&record_id=runs:operator-run')
        request('/api/session')
        for path in ('/records/foreign/runs:operator-run','/evidence/audit/runs:missing'):
            request(path, expected=404)
        for family in ('replay','backtest','shadow','soak','calibration','readiness'):
            request('/validation/'+family+'?resource_id=unregistered', expected=400)
    elif surface == 'reports':
        from trading_bot.web_reports import ReportRequest
        # Existing probe observes openat names via cwd; writer itself pins dir_fd.
        os.chdir(settings.artifact_root)
        for entry in reports.catalog():
            resource = 'cal-soak' if entry.family == 'calibration' else entry.resource_ids[0]
            data = dict(csrf_token=csrf('/reports'), family=entry.family, resource_id=resource)
            if entry.family in {'daily','period'}:
                data['start'] = '2026-10-02'
                if entry.family == 'period':
                    data['end'] = '2026-10-02'
            elif resource in {'soak','cal-soak'}:
                data['result_id'] = 'campaign-1' if resource=='cal-soak' else 'operator-campaign'
            projection=reports.project(ReportRequest(**{k:v for k,v in data.items() if k!='csrf_token'}))
            assert projection.status=='AVAILABLE', (entry.family,projection.diagnostics)
            response = request('/reports/generate', data)
            links = re.findall(r'href="(/downloads/[a-f0-9]+/(?:txt|json|csv))"', response.text)
            assert len(links) == 3, entry.family
            for link in links:
                request(link)
                request(link.replace('/downloads/','/reports/').rsplit('/',1)[0])
    elif surface == 'ack':
        from trading_bot.alert_models import AlertSubject, AlertSourceFact, Severity
        fact = AlertSourceFact(AlertSubject('portfolio',account,'mock','000660','ORDER_AMBIGUOUS','saved'),
            'phase11','probe',1,clock(),'UNKNOWN_BROKER_RESULT',Severity.CRITICAL,delivery_owner='producer')
        episode = alerts.observe(fact)
        path = '/alerts/'+episode.episode_id
        request(path)
        request('/api/views/alerts?episode_id='+episode.episode_id)
        request(path+'/ack',dict(csrf_token=csrf(path),expected_revision=1,note='검토'))
        assert alerts.get_incident(episode.episode_id).active
    elif surface == 'observer':
        from trading_bot.alert_config import ObserverSettings
        from trading_bot.alert_observer import AlertObserver
        class FakeTransport:
            def send(self, text):
                assert text and len(text) <= 4096
                return True
        observer = AlertObserver(ObserverSettings(operational_db_path=settings.operational_db_path,
            registered_resources=resources), clock=clock, notifier=FakeTransport())
        observer.scan_once()
        assert _inventory(registry) == baseline
        class OneScan:
            stopped = False
            def is_set(self):
                return self.stopped
            def wait(self, seconds):
                assert seconds == 30
                self.stopped = True
        observer.watch(OneScan())
        assert observer.status()['state'] == 'STOPPED'
        checked += 3
    elif surface == 'cli':
        from typer.testing import CliRunner
        from trading_bot.web_cli import app as web_cli
        from trading_bot.alert_cli import app as alert_cli
        runner = CliRunner()
        for cli, argv in ((web_cli,['--help']),(web_cli,['serve','--help']),
                          (alert_cli,['--help'])):
            result = runner.invoke(cli,argv)
            assert result.exit_code == 0, result.exception
            checked += 1
    elif surface == 'failure':
        for path in ('/','/account','/reports','/validation/replay?resource_id=replay',
                     '/api/views/overview','/api/views/validation-replay?resource_id=replay'):
            request(path)
        request('/reports/generate',dict(csrf_token=csrf('/reports'),family='replay',resource_id='replay'),expected=400)
    else:
        raise AssertionError(surface)
    assert _inventory(registry) == baseline
    assert not any(n in sys.modules for n in ('trading_bot.config','trading_bot.cli','conftest'))
    return dict(checked=checked)


def test_fresh_supported_surface_and_each_source_owner_invariant(tmp_path):
    from operator_fixtures import capture_sources
    from test_web_reports import setup
    from dataclasses import replace, asdict
    from test_saved_calibration_evidence import _calibration_sources
    from test_promotion_readiness import _evidence
    sources, _, _ = setup.__wrapped__(tmp_path)
    root=tmp_path/'sources'/'calibration'
    root.mkdir()
    audit,soak=_calibration_sources(root)
    sources=replace(sources,paths={**sources.paths,'cal-audit':audit,'cal-soak':soak})
    sources.artifact_root.chmod(0o700)
    baseline = capture_sources(sources)
    actions = ['factory', 'routes', 'reports', 'ack', 'observer', 'cli', 'malformed', 'missing']
    for action in actions:
        registry = {**sources.probe_registry(), 'surface': action, 'readiness':asdict(_evidence())}
        original=sources.paths['replay'].read_bytes()
        if action in {'malformed','missing'}:
            if action=='malformed':
                sources.paths['replay'].write_bytes(b'{"bad":true}')
            else:
                sources.paths['replay'].unlink()
                registry['sources'].remove(str(sources.paths['replay']))
            registry['surface']='failure'
            baseline=capture_sources(sources) if action=='malformed' else _inventory(registry)
        result = subprocess.run([sys.executable, 'tests/capability_probe.py', '--module',
            'test_web_capabilities', '--action', 'exercise', '--registry', json.dumps(registry)],
            capture_output=True, text=True, timeout=35)
        assert result.returncode == 0, f'{action}: {result.stdout}\n{result.stderr}'
        proof = json.loads(result.stdout)
        assert proof['ok'] and not proof['shared_conftest']
        assert proof['result']['checked'] > 0
        assert _inventory(registry) == baseline, action
        if action in {'malformed','missing'}:
            sources.paths['replay'].write_bytes(original)
            baseline=capture_sources(sources)


def test_tripwire_negative_controls_block_constructors_env_socket_sql_and_files(tmp_path):
    from operator_fixtures import make_operator_sources
    sources=make_operator_sources(tmp_path)
    registry=sources.probe_registry()
    for action in ('constructor','socket','sql','attach','schema','write','env'):
        child=subprocess.run([sys.executable,'tests/capability_probe.py','--module','json',
            '--action','selfcheck-'+action,'--registry',json.dumps(registry)],capture_output=True,text=True,timeout=10)
        assert child.returncode==23,child.stderr
        result=json.loads(child.stdout)
        assert not result['ok'] and result['code'].startswith('FORBIDDEN_')
