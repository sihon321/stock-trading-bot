"""Saved-source incidents and read acknowledgements never grant recovery authority."""
from dataclasses import replace

from test_web_alert_routes import alert_web, report_web, setup, web
from test_web_security import csrf


def test_web_read_worsening_positive_recovery_recurrence_and_producer_ownership(alert_web):
    from trading_bot.alert_models import Severity, DeliveryState
    from operator_fixtures import capture_sources
    app,client,sources,alerts,first,fact=alert_web
    baseline=capture_sources(sources)
    path='/alerts/'+first.episode_id
    assert client.post(path+'/ack',data={'csrf_token':csrf(client,path),
        'expected_revision':1,'note':'조사 중'}).status_code==200
    assert alerts.get_incident(first.episode_id).active
    sources.clock.advance(seconds=1)
    worsened=alerts.observe(replace(fact,source_id='severity-change',sequence=2,
        observed_at=sources.clock(),severity=Severity.CRITICAL,producer_event_id='producer-change'))
    assert worsened.revision==2 and not worsened.acknowledged
    assert client.get(path).status_code==200
    alerts.link_producer_delivery(first.episode_id,2,'WORSENING',source_owner='phase11',
        resource_id='portfolio',producer_event_id='producer-change',producer_attempt_id='saved-attempt',
        state=DeliveryState.DELIVERED,at=sources.clock())
    attempt=alerts.list_attempts(first.episode_id)[-1]
    assert attempt.delivery_owner=='producer' and attempt.state==DeliveryState.DELIVERED
    assert all(a.delivery_owner=='observer' and a.kind=='REMINDER' for a in alerts.pending_deliveries())
    sources.clock.advance(seconds=1)
    recovered=alerts.observe(replace(fact,source_id='positive-recovery',sequence=3,
        observed_at=sources.clock(),positive_recovery=True,recovery_proof_id='same-subject-proof',
        producer_event_id='producer-recovery'))
    assert not recovered.active
    sources.clock.advance(seconds=1)
    recurrent=alerts.observe(replace(fact,source_id='new-occurrence',sequence=4,
        observed_at=sources.clock(),producer_event_id='producer-recurrence'))
    assert recurrent.episode_id!=first.episode_id and recurrent.revision==1 and not recurrent.acknowledged
    assert '000660' in client.get('/alerts?period=today').text
    assert '동결 유지' in client.get('/').text
    assert capture_sources(sources)==baseline


def test_observer_crash_unknown_remains_visible_and_never_blindly_resends(tmp_path):
    from test_alert_observer import observer
    from trading_bot.alert_models import DeliveryState
    import pytest
    bot=observer(tmp_path,after_send=lambda:(_ for _ in ()).throw(SystemExit()))
    with pytest.raises(SystemExit):
        bot.scan_once()
    episode=bot.store.list_incidents()[0]
    attempt=bot.store.list_attempts(episode.episode_id)[0]
    assert attempt.state==DeliveryState.UNKNOWN
    restarted=observer(tmp_path)
    restarted.scan_once()
    assert restarted.notifier.sent==[]
    assert restarted.store.get_incident(episode.episode_id).active
    assert restarted.status()['deliveries']['UNKNOWN']==1
    assert {h.state for h in restarted.store.list_delivery_history(attempt.event_key)} >= {
        DeliveryState.CLAIMED,DeliveryState.UNKNOWN}


def test_independent_saved_owner_transactions_and_incomplete_zero_projection(tmp_path,monkeypatch):
    from operator_fixtures import make_operator_sources,capture_sources
    from trading_bot.web_config import WebSettings,ResourceDescriptor
    from trading_bot.web_evidence import OperatorEvidenceService
    import sqlite3
    sources=make_operator_sources(tmp_path,'incomplete_zero_cash')
    baseline=capture_sources(sources)
    settings=WebSettings(operational_db_path=sources.operational_db,artifact_root=sources.artifact_root,
        registered_resources=tuple(ResourceDescriptor(**vars(r)) for r in sources.resources))
    opened=[]
    original=sqlite3.connect
    def connect(path,*args,**kwargs):
        assert '?mode=ro' in str(path) and kwargs.get('uri') is True
        opened.append(str(path))
        return original(path,*args,**kwargs)
    monkeypatch.setattr(sqlite3,'connect',connect)
    overview=OperatorEvidenceService(settings,clock=sources.clock).overview(None)
    account=next(a for a in overview.accounts if a.envelope.resource_id=='portfolio')
    assert account.available_cash is None and account.total_evaluation is None
    assert any('audit.db' in p for p in opened) and any('soak.db' in p for p in opened)
    assert len({s.resource_id for s in overview.sources}) > 1
    assert '000660' in repr(overview.unresolved)
    monkeypatch.setattr(sqlite3,'connect',original)
    assert capture_sources(sources)==baseline
