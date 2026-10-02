"""Incident reading is independent of source recovery and trading safety."""
from dataclasses import replace

import pytest
from test_web_report_routes import report_web, setup
from test_web_security import csrf, login, web
from operator_fixtures import capture_sources, SECRET_SENTINEL


@pytest.fixture
def alert_web(report_web):
    from trading_bot.alert_store import AlertStore
    from trading_bot.alert_models import AlertSubject, AlertSourceFact, Severity, DeliveryState
    app, client, sources = report_web
    alerts = AlertStore(sources.operational_db, clock=sources.clock)
    alerts.initialize()
    app.extensions['alert_store'] = alerts
    base = AlertSourceFact(AlertSubject('portfolio', sources.account_hash, 'mock', '000660',
        'ORDER_AMBIGUOUS', 'saved-order'), 'phase11', 'first', 1, sources.clock(),
        'UNKNOWN_BROKER_RESULT', Severity.WARNING, delivery_owner='producer', producer_event_id='producer-event')
    episode = alerts.observe(base)
    for severity in [Severity.INFO, Severity.CRITICAL]:
        alerts.observe(replace(base, subject=replace(base.subject, ticker_or_account=severity.value),
            source_id=severity.value, producer_event_id=severity.value, severity=severity,
            producer_attempt_id='attempt-' + severity.value, producer_delivery_state=DeliveryState.FAILED))
    return app, client, sources, alerts, episode, base


def test_all_date_severities_read_recovery_and_deliveries(alert_web):
    _, client, _, alerts, episode, _ = alert_web
    response = client.get('/alerts?period=custom&start=2020-01-01&end=2020-01-01')
    assert response.status_code == 200
    for value in ['INFO','WARNING','CRITICAL','000660','UNKNOWN','FAILED','NOT_STARTED']:
        assert value in response.text
    detail = client.get('/alerts/' + episode.episode_id)
    assert detail.status_code == 200 and 'expected_revision' in detail.text
    assert '반복 알림만 중지' in detail.text
    assert alerts.get_incident(episode.episode_id).active


def test_ack_actor_time_blank_note_source_freeze_unchanged(alert_web):
    app, client, sources, alerts, episode, _ = alert_web
    before = capture_sources(sources)
    path = '/alerts/' + episode.episode_id
    response = client.post(path + '/ack', data={'csrf_token':csrf(client, path),
        'expected_revision':episode.revision, 'note':''})
    assert response.status_code == 200
    ack = alerts.list_acknowledgements(episode.episode_id)[0]
    assert ack.actor == 'owner' and ack.at == sources.clock() and ack.note == ''
    assert alerts.get_incident(episode.episode_id).active
    assert '000660' in client.get('/alerts?period=7d').text
    assert '동결 유지' in client.get('/').text
    assert capture_sources(sources) == before
    with app.extensions['web_store'].connection() as conn:
        assert conn.execute("SELECT count(*) FROM web_actions WHERE action='ALERT_ACK' AND result_code='SUCCEEDED'").fetchone()[0] == 1


def test_stale_revision_409_retains_note_and_unread(alert_web):
    app, client, sources, alerts, episode, fact = alert_web
    from trading_bot.alert_models import Severity
    path = '/alerts/' + episode.episode_id
    token = csrf(client, path)
    alerts.observe(replace(fact, source_id='worse', sequence=2, severity=Severity.CRITICAL))
    response = client.post(path + '/ack', data={'csrf_token':token,
        'expected_revision':episode.revision, 'note':'검토 메모'})
    assert response.status_code == 409 and '검토 메모' in response.text
    assert '알림 상태가 변경되었습니다' in response.text and 'value="2"' in response.text
    assert not alerts.get_incident(episode.episode_id).acknowledged
    with app.extensions['web_store'].connection() as conn:
        assert conn.execute("SELECT count(*) FROM web_actions WHERE result_code='REVISION_CONFLICT'").fetchone()[0] == 1


@pytest.mark.parametrize('payload', [{'note':'x'*501}, {'expected_revision':'bad'},
    {'actor':'forged'}, {'at':'2020-01-01'}, {'path':'/etc/passwd'}])
def test_ack_invalid_audited_and_preserves_unread(alert_web, payload):
    app, client, _, alerts, episode, _ = alert_web
    path = '/alerts/' + episode.episode_id
    response = client.post(path + '/ack', data={'csrf_token':csrf(client,path),
        'expected_revision':episode.revision, 'note':'keep', **payload})
    assert response.status_code == 400
    assert not alerts.get_incident(episode.episode_id).acknowledged
    assert not alerts.list_acknowledgements(episode.episode_id)


def test_ack_notes_sanitized_and_csrf_subject_scope_guards(alert_web):
    _, client, _, alerts, episode, fact = alert_web
    path = '/alerts/' + episode.episode_id
    assert client.post(path+'/ack',data={'expected_revision':1}).status_code == 400
    note = '<script>alert(1)</script> ' + SECRET_SENTINEL
    response = client.post(path+'/ack',data={'csrf_token':csrf(client,path),'expected_revision':1,'note':note})
    assert response.status_code == 200 and '<script>alert' not in response.text
    assert SECRET_SENTINEL not in response.text
    assert SECRET_SENTINEL not in alerts.list_acknowledgements(episode.episode_id)[0].note
    unauthorized = alerts.observe(replace(fact, subject=replace(fact.subject, account_hash='b'*64), source_id='foreign'))
    assert client.get('/alerts/'+unauthorized.episode_id).status_code == 404
    assert unauthorized.episode_id not in client.get('/alerts').text


def test_positive_recovery_history_remains_distinct(alert_web):
    _, client, _, alerts, episode, fact = alert_web
    alerts.observe(replace(fact, source_id='recovered', sequence=2, positive_recovery=True,
        recovery_proof_id='same-subject-proof'))
    response = client.get('/alerts/' + episode.episode_id)
    assert response.status_code == 200 and '복구 확인' in response.text
    assert 'same-subject-proof' in response.text and '미확인' in response.text


@pytest.mark.parametrize('foreign', ['same', 'mismatch', 'registered', 'unregistered'])
def test_critical_total_exact_scoped_and_all_pages(alert_web, foreign):
    from bs4 import BeautifulSoup
    from trading_bot.alert_models import Severity
    _, client, sources, alerts, _, fact = alert_web
    before = capture_sources(sources)
    sources.clock.advance(seconds=1)
    for i in range(100):
        subject = replace(fact.subject, ticker_or_account=f'new-{i}')
        if foreign == 'mismatch':
            subject = replace(subject, account_hash='b'*64, target='real')
        elif foreign == 'registered':
            subject = replace(subject, resource_id='soak')
        elif foreign == 'unregistered':
            subject = replace(subject, resource_id='unregistered')
        alerts.observe(replace(fact, subject=subject, source_id=f'new-{i}',
            observed_at=sources.clock(), severity=Severity.CRITICAL))
    expected = 101 if foreign == 'same' else 1
    page = BeautifulSoup(client.get('/?resource_id=portfolio&limit=10').text, 'html.parser')
    header = page.select_one('.critical-count')
    assert header.get_text(strip=True) == f'미해결 CRITICAL · {expected}'
    link = header['href']
    assert 'resource_id=portfolio' in link and 'severity=CRITICAL' in link and 'active=1' in link
    episodes = set()
    for _ in range(12):
        response = client.get(link)
        assert response.status_code == 200
        page = BeautifulSoup(response.text, 'html.parser')
        cards = page.select('.record-card')
        assert len(cards) <= 10
        for card in cards:
            assert 'CRITICAL' in card.get_text() and '활성' in card.get_text()
            assert 'real' not in card.get_text()
            episodes.add(card['id'])
        next_link = page.find('a', string='다음 페이지')
        if next_link is None:
            break
        link = next_link['href']
    assert len(episodes) == expected
    assert capture_sources(sources) == before


def test_critical_storage_failure_is_unknown_and_filters_are_validated(alert_web, monkeypatch):
    _, client, _, alerts, _, _ = alert_web
    def unavailable():
        raise ValueError('unavailable')
    monkeypatch.setattr(alerts, '_verify_ownership', unavailable)
    assert '미해결 CRITICAL · UNKNOWN' in client.get('/').text
    assert 'ALERT_STORAGE_UNAVAILABLE' in client.get('/alerts?active=1&severity=CRITICAL').text
    for path in ['/alerts?severity=bogus', '/alerts?active=bogus']:
        assert client.get(path).status_code == 400
