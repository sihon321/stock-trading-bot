from dataclasses import replace
from datetime import timedelta
import sqlite3
from threading import Event

import pytest

from trading_bot.alert_config import ObserverSettings
from trading_bot.alert_observer import AlertObserver, ObserverBusy, ObserverEvidenceError
from trading_bot.alert_models import DeliveryState
from trading_bot.web_models import AlertSourceBatch
from test_alert_detector import NOW, record


class Clock:
    value = NOW
    def __call__(self):
        return self.value
    def advance(self, seconds):
        self.value += timedelta(seconds=seconds)


class Reader:
    def __init__(self, batch):
        self.batch, self.cursors = batch, []
    def observe_alert_sources(self, cursor=None):
        self.cursors.append(cursor)
        return self.batch


class Transport:
    def __init__(self, result=True):
        self.result, self.sent = result, []
    def send(self, text):
        self.sent.append(text)
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


def observer(tmp_path, *, transport=None, clock=None, reader=None, **kwargs):
    settings = ObserverSettings(operational_db_path=tmp_path / 'ops' / 'alerts.db')
    return AlertObserver(settings, clock=clock or Clock(), notifier=transport or Transport(),
        evidence=reader or Reader(AlertSourceBatch(NOW, (record('orders', order_intent_id='intent'),), cursor='saved')), **kwargs)


def test_commit_before_send_and_replay_checkpoint(tmp_path):
    bot = observer(tmp_path)
    transport = bot.notifier
    original = transport.send
    def check(text):
        with sqlite3.connect(bot.store.path) as conn:
            assert conn.execute('SELECT state FROM alert_outbox').fetchone()[0] == 'CLAIMED'
            assert conn.execute('SELECT cursor FROM alert_checkpoints').fetchone()[0] == 'saved'
        return original(text)
    transport.send = check
    bot.scan_once()
    bot.scan_once()
    assert len(transport.sent) == 1
    assert bot.evidence.cursors == [None, 'saved']
    assert bot.store.list_incidents()[0].occurrence_count == 1
    assert bot.status()['state'] == 'STOPPED'


def test_certified_healthy_partition_cursor_advances_during_source_failure(tmp_path):
    bot = observer(tmp_path)
    failed = replace(record('runs').envelope,resource_id='failed-source',query_status='FAILED')
    bot.evidence.batch = replace(bot.evidence.batch,sources=(failed,),partial_cursor='healthy-partition')
    bot.scan_once()
    assert bot.store.get_checkpoint() == 'healthy-partition'
    bot.scan_once()
    assert bot.evidence.cursors == [None,'healthy-partition']


@pytest.mark.parametrize('during_read', [False,True])
def test_source_read_recovery_preserves_historical_producer_timestamp(tmp_path,during_read):
    clock = Clock()
    bot = observer(tmp_path,clock=clock)
    old = clock()-timedelta(days=40)
    failed = replace(record('runs').envelope,resource_id='failed-source',query_status='FAILED',source_observed_at=old)
    bot.evidence.batch=AlertSourceBatch(clock(),sources=(failed,))
    bot.scan_once()
    episode=next(e for e in bot.store.list_incidents() if e.subject.resource_id=='failed-source')
    clock.advance(30)
    scan_started=clock()
    if during_read:
        clock.advance(1)
    healthy=replace(failed,query_status='OK',query_at=clock())
    bot.evidence.batch=AlertSourceBatch(clock(),sources=(healthy,))
    bot.scan_once(now=scan_started)
    recovered=bot.store.get(episode.episode_id)
    assert not recovered.active and recovered.recovered_at==clock()
    assert healthy.source_observed_at==old


def test_notification_distinguishes_saved_subject_and_observation_time(tmp_path):
    bot=observer(tmp_path)
    old=NOW-timedelta(days=40)
    rows=tuple(replace(record('campaigns',str(i),campaign_id=campaign,safety_failure_code='BROKER_DIVERGENCE'),
        envelope=replace(record('campaigns').envelope,source_observed_at=old))
        for i,campaign in enumerate(('campaign-one','campaign-two'),1))
    bot.evidence.batch=AlertSourceBatch(NOW,rows)
    bot.scan_once()
    assert len(bot.notifier.sent)==2
    assert 'campaign-one' in bot.notifier.sent[0] and 'campaign-two' in bot.notifier.sent[1]
    assert all('원천 관측: 2026-08-23 09:00:00 KST' in message for message in bot.notifier.sent)


def test_critical_reminder_boundary_ack_and_delayed_restart(tmp_path):
    clock = Clock()
    bot = observer(tmp_path, clock=clock)
    bot.scan_once()
    clock.advance(1799)
    bot.scan_once()
    assert len(bot.notifier.sent) == 1
    clock.advance(1)
    bot.scan_once()
    assert len(bot.notifier.sent) == 2
    clock.advance(9000)
    bot.scan_once()
    assert len(bot.notifier.sent) == 3
    episode = bot.store.list_incidents()[0]
    assert episode.next_reminder_at == clock() + timedelta(seconds=1800)
    bot.store.acknowledge(episode.episode_id, episode.revision, 'operator')
    clock.advance(1800)
    bot.scan_once()
    assert len(bot.notifier.sent) == 3


@pytest.mark.parametrize('severity,count', [('INFO', 0), ('WARNING', 1)])
def test_info_web_only_and_warning_no_reminder(tmp_path, severity, count):
    clock = Clock()
    reader = Reader(AlertSourceBatch(NOW, (record('runs', status='FAILED', run_kind='daily', severity=severity),)))
    bot = observer(tmp_path, clock=clock, reader=reader)
    bot.scan_once()
    clock.advance(3600)
    bot.scan_once()
    assert len(bot.notifier.sent) == count


@pytest.mark.parametrize('result,state', [(False, 'FAILED'), (RuntimeError('SECRET'), 'UNKNOWN')])
def test_transport_fail_soft_sanitized_and_never_reclaimed(tmp_path, result, state):
    bot = observer(tmp_path, transport=Transport(result))
    bot.scan_once()
    bot.scan_once()
    episode = bot.store.list_incidents()[0]
    assert bot.store.list_attempts(episode.episode_id)[0].state == state
    assert len(bot.notifier.sent) == 1
    assert 'SECRET' not in str(bot.status())


def test_process_exclusion_takeover_and_crash_unknown(tmp_path):
    clock = Clock()
    bot = observer(tmp_path, clock=clock)
    bot.start()
    competitor = observer(tmp_path, clock=clock)
    with pytest.raises(ObserverBusy):
        competitor.scan_once()
    fact = bot.detector.detect(bot.evidence.batch)[0]
    episode = bot.store.observe(fact)
    event = bot.store.pending_deliveries()[0]
    bot.store.claim_delivery(event.event_key, bot.owner)
    clock.advance(301)
    competitor.scan_once()
    assert competitor.store.get_delivery(event.event_key).state == DeliveryState.UNKNOWN
    assert competitor.notifier.sent == []
    with pytest.raises(ObserverEvidenceError):
        bot.heartbeat()
    assert competitor.status()['state'] == 'STOPPED'


def test_failure_durable_stop_event_and_status_readonly(tmp_path):
    bot = observer(tmp_path)
    def bad(cursor):
        raise RuntimeError('private secret')
    bot.evidence.observe_alert_sources = bad
    bot.scan_once()
    assert bot.status()['state'] == 'STOPPED'
    assert bot.status()['failure_code'] is None
    assert any(e.subject.problem_family=='SERVICE_SOURCE_UNAVAILABLE' for e in bot.store.list_incidents())
    before = bot.store.path.read_bytes()
    bot.status()
    assert bot.store.path.read_bytes() == before
    stop = Event()
    stop.set()
    bot.watch(stop)
    assert bot.status()['state'] == 'STOPPED'


def test_unknown_source_does_not_recover(tmp_path):
    bot = observer(tmp_path)
    bot.scan_once()
    episode = bot.store.list_incidents()[0]
    failed = replace(record('orders', '2', order_intent_id='intent'),
        envelope=replace(record('orders').envelope, query_status='FAILED'))
    bot.evidence.batch = AlertSourceBatch(NOW, (failed,))
    bot.scan_once()
    assert bot.store.get(episode.episode_id).active


def test_phase11_owned_and_late_receipt_link_without_send(tmp_path):
    occurrence = record('transition_observations', state_identity='b'*64,
        state_code='ORDER_AMBIGUOUS', ticker='005930', event_family='BROKER_ORDER',
        broker_subject_id='broker', severity='CRITICAL', producer_event_code='STATE_BEGIN')
    receipt = record('transition_notifications', '7', state_identity='b'*64,
        event_code='STATE_BEGIN', ticker='005930', event_family='BROKER_ORDER',
        broker_subject_id='broker', severity='CRITICAL', delivery_status='DELIVERED')
    reader = Reader(AlertSourceBatch(NOW, (receipt,), cursor='receipt'))
    bot = observer(tmp_path, reader=reader)
    bot.scan_once()
    reader.batch = AlertSourceBatch(NOW, (occurrence,), cursor='occurrence')
    bot.scan_once()
    episode = bot.store.list_incidents()[0]
    attempt = bot.store.list_attempts(episode.episode_id)[0]
    assert attempt.delivery_owner == 'producer' and attempt.state == DeliveryState.DELIVERED
    assert attempt.producer_attempt_id == 'transition-notification:7'
    assert bot.notifier.sent == []


def test_real_source_observation_leaves_source_bytes_unchanged(tmp_path):
    from operator_fixtures import make_operator_sources, capture_sources
    from trading_bot.web_config import ResourceDescriptor
    sources = make_operator_sources(tmp_path)
    settings = ObserverSettings(operational_db_path=sources.operational_db,
        registered_resources=tuple(ResourceDescriptor(id=r.id, path=r.path, owner=r.owner,
            account_hash=r.account_hash, target=r.target) for r in sources.resources))
    before = capture_sources(sources)
    bot = AlertObserver(settings, clock=sources.clock, notifier=Transport())
    bot.scan_once()
    assert capture_sources(sources) == before


def test_operational_schema_coexists_with_web_store(tmp_path):
    from trading_bot.web_config import WebSettings
    from trading_bot.web_store import WebStore
    bot = observer(tmp_path)
    settings = WebSettings(operational_db_path=bot.store.path,
        artifact_root=tmp_path / 'artifacts')
    web = WebStore(settings)
    web.initialize()
    bot.scan_once()
    web.initialize()
    assert bot.status()['state'] == 'STOPPED'


def test_source_failure_preserves_outbox_but_checkpoint_failure_blocks_send(tmp_path, monkeypatch):
    bot = observer(tmp_path)
    env = replace(record('runs').envelope, schema_owner='audit', query_status='FAILED')
    bot.evidence.batch = replace(bot.evidence.batch, sources=(env,))
    bot.scan_once()
    assert bot.notifier.sent
    assert bot.store.get_checkpoint() is None
    bot.evidence.batch = replace(bot.evidence.batch, sources=())
    bot.notifier.sent.clear()
    monkeypatch.setattr(bot.store, 'set_checkpoint', lambda *_: (_ for _ in ()).throw(sqlite3.Error('secret')))
    with pytest.raises(ObserverEvidenceError):
        bot.scan_once()
    assert bot.notifier.sent == []
    assert bot.store.get_checkpoint() is None


def test_persistent_service_control_failure_keeps_owned_delivery_reminders_and_ack(tmp_path):
    clock=Clock()
    bot=observer(tmp_path,clock=clock)
    bot.start()
    incident=bot.store.observe(bot.detector.detect(bot.evidence.batch)[0])
    failure=replace(record('runs').envelope,resource_id='service',schema_owner='service',query_status='FAILED',
        source_observed_at=None,diagnostic_code='SOURCE_UNAVAILABLE')
    control=replace(failure,resource_id='control',schema_owner='control')
    bot.evidence.batch=AlertSourceBatch(clock(), sources=(failure,control),cursor='must-not-advance')
    bot._scan(clock())
    assert any('UNRESOLVED_ORDER' in text for text in bot.notifier.sent)
    assert bot.store.get_checkpoint() is None
    clock.advance(1799)
    bot._scan(clock())
    count=len(bot.notifier.sent)
    clock.advance(1)
    bot._scan(clock())
    assert len(bot.notifier.sent)==count+1
    assert bot.store.get(incident.episode_id).active
    failures=[e for e in bot.store.list_incidents() if e.subject.problem_family=='SERVICE_SOURCE_UNAVAILABLE']
    assert len(failures)==2 and all(e.occurrence_count==1 for e in failures)
    bot.store.acknowledge(incident.episode_id,incident.revision,'operator')
    clock.advance(1800)
    bot._scan(clock())
    assert len(bot.notifier.sent)==count+1
    assert bot.status()['state']=='RUNNING'
    # Fresh positive source evidence resolves source availability alone.
    bot.evidence.batch=AlertSourceBatch(clock(),sources=(replace(failure,query_status='OK',
        source_observed_at=clock(),diagnostic_code=None), control),cursor='healthy-partial')
    bot._scan(clock())
    bot._scan(clock())
    assert not bot.store.get(failures[0].episode_id).active or not bot.store.get(failures[1].episode_id).active
    assert bot.store.get(incident.episode_id).active
    assert len([t for t in bot.notifier.sent if 'RECOVERY: SERVICE_SOURCE_UNAVAILABLE' in t])==1
    bot.stop()


def test_source_failure_unknown_delivery_never_blindly_retried(tmp_path):
    bot=observer(tmp_path,transport=Transport(RuntimeError('private transport token')))
    failure=replace(record('runs').envelope,schema_owner='service',query_status='FAILED',source_observed_at=None)
    bot.evidence.batch=AlertSourceBatch(NOW,sources=(failure,))
    bot.scan_once(); bot.scan_once()
    assert len(bot.notifier.sent)==1
    episode=bot.store.list_incidents()[0]
    assert bot.store.list_attempts(episode.episode_id)[0].state==DeliveryState.UNKNOWN


def test_lost_owner_or_own_store_failure_stops_sends_with_sources_down(tmp_path,monkeypatch):
    bot=observer(tmp_path)
    bot.start()
    bot.store.observe(bot.detector.detect(bot.evidence.batch)[0])
    with bot.store.connection() as conn:
        conn.execute("UPDATE alert_observer SET owner='competitor'")
    with pytest.raises(ObserverEvidenceError): bot._scan(NOW)
    assert bot.notifier.sent==[]
    bot._owned=False
    second=observer(tmp_path/'second')
    second.start()
    monkeypatch.setattr(second.store,'get_checkpoint',lambda: (_ for _ in ()).throw(sqlite3.DatabaseError('private')))
    with pytest.raises(sqlite3.DatabaseError): second._scan(NOW)
    assert second.notifier.sent==[]
    second.stop()


def test_expectation_publication_failure_does_not_suppress_existing_outbox(tmp_path):
    class Producer:
        def publish(self): raise ValueError('private session token')
    bot=observer(tmp_path,expectation_producer=Producer())
    bot.scan_once()
    assert any('UNRESOLVED_ORDER' in text for text in bot.notifier.sent)
    assert any(e.subject.problem_family=='EXPECTATION_UNKNOWN' for e in bot.store.list_incidents())
    assert bot.store.get_checkpoint() is None


def test_watch_survives_repeated_reader_exception_and_due_reminder(tmp_path):
    clock=Clock()
    bot=observer(tmp_path,clock=clock)
    bot._initialize()
    episode=bot.store.observe(bot.detector.detect(bot.evidence.batch)[0])
    def unavailable(cursor): raise OSError('private source path')
    bot.evidence.observe_alert_sources=unavailable
    class Stop:
        waits=0
        def is_set(self): return self.waits>=3
        def wait(self,seconds):
            assert seconds==30 and bot._owned
            self.waits+=1
            clock.advance(1799 if self.waits==1 else 1)
    bot.watch(Stop())
    assert bot.status()['state']=='STOPPED'
    assert len([t for t in bot.notifier.sent if 'UNRESOLVED_ORDER' in t])==2
    assert bot.store.get(episode.episode_id).active


def test_failed_partition_recovery_row_cannot_clear_prior_incident(tmp_path):
    clock=Clock()
    bot=observer(tmp_path,clock=clock)
    bot.scan_once()
    incident=bot.store.list_incidents()[0]
    clock.advance(30)
    recovery=record('orders','2',30,order_intent_id='intent',event_type='RECONCILED',
        broker_status='FILLED',broker_order_id='broker',unfilled_qty=0)
    failure=replace(recovery.envelope,query_status='FAILED')
    bot.evidence.batch=AlertSourceBatch(clock(),(recovery,),sources=(failure,),cursor='incomplete')
    bot.scan_once()
    assert bot.store.get(incident.episode_id).active
    assert bot.store.get_checkpoint()=='saved'


def test_crash_after_send_stays_unknown_no_duplicate(tmp_path):
    bot = observer(tmp_path, after_send=lambda: (_ for _ in ()).throw(SystemExit()))
    with pytest.raises(SystemExit):
        bot.scan_once()
    episode = bot.store.list_incidents()[0]
    assert bot.store.list_attempts(episode.episode_id)[0].state == DeliveryState.UNKNOWN
    restarted = observer(tmp_path)
    restarted.scan_once()
    assert restarted.notifier.sent == []


def test_recovery_worsening_recurrence_deliver_once(tmp_path):
    reader = Reader(AlertSourceBatch(NOW, (record('runs', status='FAILED', run_kind='daily'),)))
    clock = Clock()
    bot = observer(tmp_path, reader=reader, clock=clock)
    bot.scan_once()
    first = bot.store.list_incidents()[0]
    bot.store.acknowledge(first.episode_id, first.revision, 'operator')
    clock.advance(1)
    reader.batch = AlertSourceBatch(clock(), (record('runs', '2', 1, status='FAILED', run_kind='daily', severity='CRITICAL'),))
    bot.scan_once()
    assert not bot.store.get(first.episode_id).acknowledged
    clock.advance(1)
    reader.batch = AlertSourceBatch(clock(), (record('runs', '3', 2, status='COMPLETED', run_kind='daily'),))
    bot.scan_once()
    assert not bot.store.get(first.episode_id).active
    clock.advance(1)
    reader.batch = AlertSourceBatch(clock(), (record('runs', '4', 3, status='FAILED', run_kind='daily'),))
    bot.scan_once()
    bot.scan_once()
    assert len(bot.store.list_incidents()) == 2
    assert len(bot.notifier.sent) == 4
