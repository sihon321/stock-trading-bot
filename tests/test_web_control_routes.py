"""Authenticated installation requests on temporary protected stores only."""
import json
import sqlite3
from uuid import uuid4

import pytest
from werkzeug.datastructures import MultiDict

from test_web_security import web, csrf, login
from tests.service_fixtures import TempServiceTopology, FakeServiceClock, SCOPE
from trading_bot.control_store import ControlStore
from trading_bot.web_config import ControlResourceDescriptor, ResourceDescriptor


@pytest.fixture
def control_web(web, tmp_path):
    from trading_bot.web_app import create_app
    base, _, _ = web
    clock = FakeServiceClock()
    (tmp_path / 'service-fixture').mkdir(mode=0o700)
    owner = ControlStore(TempServiceTopology(tmp_path / 'service-fixture').registration(), clock=clock)
    owner.initialize(actor='owner')
    descriptor = ControlResourceDescriptor(resource_id='controls', path=owner.path,
        lock_dir=owner.lock_path.parent,
        registered_scopes=((SCOPE.account_scope_hash, 'mock'),))
    settings = base.extensions['web_settings'].model_copy(update={
        'registered_resources': (ResourceDescriptor(id='controls', path=owner.path,
            owner='control', account_hash=SCOPE.account_scope_hash, target='mock'),),
        'control_resource': descriptor})
    app = create_app(settings, clock=clock)
    client = app.test_client()
    assert login(client).status_code == 303
    return app, client, owner, clock


def submit(client, action='pause', *, rid=None, revision=0, **fields):
    return client.post('/controls/controls/' + action, data={
        'csrf_token': csrf(client, '/controls/controls'),
        'request_id': rid or str(uuid4()), 'expected_revision': str(revision),
        'note': '', **fields})


def test_request_only_durable_actor_revision_replay_and_correlation(control_web):
    app, client, owner, clock = control_web
    rid = str(uuid4())
    response = submit(client, rid=rid)
    assert response.status_code == 200 and rid in response.text
    assert 'REQUESTED' in response.text and '적용 대기' in response.text
    rows = owner.reader().list_requests()
    assert len(rows) == 1 and rows[0]['actor'] == 'owner'
    assert rows[0]['requested_at'] == clock().isoformat()
    assert rows[0]['scope_hash'] == owner.scope_hash and rows[0]['acceptance_revision'] == 1
    assert owner.reader().effective_state().applied.revision == 0
    clock.advance(wall_seconds=10)
    assert submit(client, rid=rid).status_code == 200
    assert len(owner.reader().list_requests()) == 1
    assert owner.reader().list_requests()[0]['requested_at'] == rows[0]['requested_at']
    with app.extensions['web_store'].connection() as conn:
        actions = conn.execute("SELECT details_json FROM web_actions WHERE action='CONTROL_REQUEST'").fetchall()
    assert len(actions) == 1
    assert json.loads(actions[0][0])['request_id'] == rid
    assert json.loads(actions[0][0])['accepted_revision'] == 1


@pytest.mark.parametrize('field', ['actor','at','scope','path','job','policy','receipt','target'])
def test_client_authority_fields_rejected(control_web, field):
    _, client, owner, _ = control_web
    assert submit(client, **{field:'forged'}).status_code == 400
    assert not owner.reader().list_requests()


@pytest.mark.parametrize('action', ['PAUSE','Resume','delete','liquidate'])
def test_exact_action_and_fixed_resource(control_web, action):
    _, client, owner, _ = control_web
    assert submit(client, action).status_code == 404
    token = csrf(client, '/controls/controls')
    assert client.post('/controls/foreign/pause', data={'csrf_token':token}).status_code == 404
    assert client.get('/controls/foreign').status_code == 404
    assert not owner.reader().list_requests()


def test_auth_csrf_origin_host_duplicate_and_revision_guards(control_web):
    app, client, owner, _ = control_web
    path = '/controls/controls/pause'
    assert app.test_client().get('/controls').status_code == 302
    assert app.test_client().post(path).status_code == 302
    assert client.post(path).status_code == 400
    token = csrf(client, '/controls/controls')
    fields = {'csrf_token':token,'request_id':str(uuid4()),'expected_revision':'0'}
    assert client.post(path, data=fields, headers={'Origin':'https://evil.test'}).status_code == 400
    assert client.post(path, data=fields, base_url='http://evil.test').status_code == 400
    duplicate = MultiDict(fields); duplicate.add('request_id', str(uuid4()))
    assert client.post(path, data=duplicate).status_code == 400
    assert submit(client, revision='-1').status_code == 400
    assert submit(client, request_id='not-a-uuid').status_code == 400
    assert submit(client, note='x'*501).status_code == 400
    assert not owner.reader().list_requests()
    assert submit(client).status_code == 200
    assert submit(client, 'resume', revision=0).status_code == 409
    assert len(owner.reader().list_requests()) == 1


def test_busy_no_acceptance_and_changed_replay_conflict(control_web):
    _, client, owner, _ = control_web
    with owner.admission_lock():
        response = submit(client)
    assert response.status_code == 503 and not owner.reader().list_requests()
    rid = str(uuid4())
    assert submit(client, rid=rid).status_code == 200
    assert submit(client, 'kill', rid=rid).status_code == 409
    assert len(owner.reader().list_requests()) == 1


def test_web_audit_failure_truth_and_same_id_repair(control_web, monkeypatch):
    app, client, owner, _ = control_web
    store = app.extensions['web_store']
    original = store.append_control_action
    def failed(**kwargs):
        raise sqlite3.OperationalError('sensitive unavailable path')
    monkeypatch.setattr(store, 'append_control_action', failed)
    rid = str(uuid4())
    response = submit(client, 'kill', rid=rid)
    assert response.status_code == 503 and rid in response.text
    assert '요청은 저장' in response.text and '웹 감사' in response.text
    assert 'sensitive unavailable path' not in response.text
    assert owner.reader().effective_state().mode == 'KILLED'
    assert owner.reader().effective_state().applied.revision == 0
    monkeypatch.setattr(store, 'append_control_action', original)
    assert submit(client, 'kill', rid=rid).status_code == 200
    assert len(owner.reader().list_requests()) == 1


def test_descriptor_factory_has_no_service_or_trading_capabilities(control_web):
    from trading_bot.control_store import control_request_capabilities
    app, _, _, clock = control_web
    reader, writer = control_request_capabilities(app.extensions['web_settings'].control_resource,
        actor='owner', clock=clock)
    for port in (reader, writer):
        for forbidden in ('settings','path','initialize','service_capability','apply_pending','claim_job'):
            assert not hasattr(port, forbidden)
    assert reader.effective_state().applied.revision == 0
    import ast
    from pathlib import Path
    source = Path('trading_bot/web_control.py').read_text()
    tree = ast.parse(source)
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert not imports & {'config','kis_broker','llm_provider','service_runtime','service_composition','service_store'}


def test_older_admitted_submission_stays_visible(control_web):
    _, client, owner, clock = control_web
    with owner.admission_lock() as lock:
        owner._record_admission(lock, scope=SCOPE, intent_id='old-intent', submission_id='old-post',
            control_revision=0, admitted_at=clock())
    response = submit(client, 'kill')
    assert response.status_code == 200 and 'IN_FLIGHT' in response.text
    assert '이전 승인 주문' in response.text
    assert owner.reader().list_admissions()[0]['state'] == 'IN_FLIGHT'
