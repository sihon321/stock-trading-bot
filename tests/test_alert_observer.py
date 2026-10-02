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
    with pytest.raises(ObserverEvidenceError):
        bot.scan_once()
    assert bot.status()['state'] == 'FAILED'
    assert bot.status()['failure_code'] == 'SOURCE_FAILED'
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


def test_mandatory_source_failure_and_checkpoint_failure_block_send(tmp_path, monkeypatch):
    bot = observer(tmp_path)
    env = replace(record('runs').envelope, schema_owner='audit', query_status='FAILED')
    bot.evidence.batch = replace(bot.evidence.batch, sources=(env,))
    with pytest.raises(ObserverEvidenceError):
        bot.scan_once()
    assert bot.notifier.sent == []
    assert bot.store.get_checkpoint() is None
    bot.evidence.batch = replace(bot.evidence.batch, sources=())
    monkeypatch.setattr(bot.store, 'set_checkpoint', lambda *_: (_ for _ in ()).throw(sqlite3.Error('secret')))
    with pytest.raises(ObserverEvidenceError):
        bot.scan_once()
    assert bot.notifier.sent == []
    assert bot.store.get_checkpoint() is None


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
