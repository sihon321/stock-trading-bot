"""Offline exact-date authority proofs; fixture notices confer no live acceptance."""
from datetime import date, datetime, timedelta
import json

import pytest

from service_fixtures import FakeServiceClock, session_evidence
from trading_bot.market_cycle import KST, MarketCyclePolicy, MarketSession

DAY = date(2026, 10, 5)


def at(hour, minute=0, second=0, day=DAY):
    return datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=KST)


def notice(kind='normal', **updates):
    value = session_evidence(kind).model_dump(mode='json')
    value.update(source_id='krx-reviewed-session', notice_id='20261005-session',
                 reviewer='owner', source_url='https://kind.krx.co.kr/notices/20261005')
    return value | updates


def save(tmp_path, value):
    path = tmp_path / 'sessions.json'
    path.write_text(json.dumps(value), encoding='utf-8')
    path.chmod(0o600)
    return path


class Calendar:
    def __init__(self, state=True):
        self.state = state

    def is_trading_day(self, day):
        return self.state

    def previous_trading_day(self, day):
        return day - timedelta(days=1)


def policy(path, clock, state=True):
    from trading_bot.session_evidence import SessionEvidenceProvider
    return MarketCyclePolicy(Calendar(state),
                             session_evidence_provider=SessionEvidenceProvider(path, clock))


@pytest.mark.parametrize(('kind', 'hour', 'minute', 'expected', 'executable'), [
    ('normal', 8, 50, MarketSession.PRE_OPEN, False),
    ('normal', 9, 0, MarketSession.CONTINUOUS, True),
    ('delayed', 9, 10, MarketSession.PRE_OPEN, False),
    ('delayed', 9, 19, MarketSession.PRE_OPEN, False),
    ('delayed', 10, 0, MarketSession.CONTINUOUS, True),
    ('delayed', 15, 20, MarketSession.CLOSING_AUCTION, False),
    ('delayed', 15, 30, MarketSession.CLOSING_AUCTION, False),
])
def test_exact_date_sessions(tmp_path, kind, hour, minute, expected, executable):
    clock = FakeServiceClock(at(hour, minute))
    result = policy(save(tmp_path, notice(kind)), clock).classify(clock())
    assert result.session is expected
    assert result.executable is executable


@pytest.mark.parametrize('updates', [
    {'trading_date_kst': '2025-10-05'},
    {'effective_at': at(8, day=date(2026, 10, 4)).isoformat()},
    {'observed_at': at(8, day=date(2026, 10, 4)).isoformat()},
    {'observed_at': at(11).isoformat()},
    {'reviewed_at': at(11).isoformat()},
    {'source_url': 'https://kind.krx.co.kr.evil.example/notice'},
    {'source_url': 'http://kind.krx.co.kr/notice'},
    {'source_url': 'https://owner@kind.krx.co.kr/notice'},
    {'source_hash': 'guessed'}, {'reviewer': ''}, {'notice_id': ''},
    {'continuous_close': at(8).isoformat()}, {'unknown_field': True},
])
def test_invalid_or_stale_notice_is_unknown(tmp_path, updates):
    clock = FakeServiceClock(at(10))
    result = policy(save(tmp_path, notice(**updates)), clock).classify(clock())
    assert result.session is MarketSession.UNKNOWN
    assert not result.executable


def test_missing_and_synthetic_authority_fail_closed(tmp_path):
    clock = FakeServiceClock(at(10))
    assert policy(tmp_path / 'missing', clock).classify(clock()).session is MarketSession.UNKNOWN
    result = policy(save(tmp_path, session_evidence().model_dump(mode='json')), clock).classify(clock())
    assert result.session is MarketSession.UNKNOWN


def test_contradictory_calendar_and_notices_fail_closed(tmp_path):
    clock = FakeServiceClock(at(10))
    path = save(tmp_path, {'sessions': [notice(), notice('delayed')]})
    assert policy(path, clock).classify(clock()).session is MarketSession.UNKNOWN
    path = save(tmp_path, notice('holiday'))
    assert policy(path, clock).classify(clock()).session is MarketSession.UNKNOWN
    path = save(tmp_path, notice())
    assert policy(path, clock, False).classify(clock()).session is MarketSession.UNKNOWN
    assert policy(path, clock, None).classify(clock()).session is MarketSession.UNKNOWN


def test_early_close_blocks_post(tmp_path):
    clock = FakeServiceClock(at(14))
    path = save(tmp_path, notice(continuous_close=at(14).isoformat()))
    assert not policy(path, clock).classify(clock()).executable


def test_owner_local_bounds_and_symlinks(tmp_path):
    clock = FakeServiceClock(at(10))
    path = save(tmp_path, notice())
    path.chmod(0o644)
    assert policy(path, clock).classify(clock()).session is MarketSession.UNKNOWN
    path.chmod(0o600)
    linked = tmp_path / 'linked'
    linked.symlink_to(path)
    assert policy(linked, clock).classify(clock()).session is MarketSession.UNKNOWN
    path.write_text(' ' * 65537)
    assert policy(path, clock).classify(clock()).session is MarketSession.UNKNOWN


def test_new_positive_notice_refreshes_unknown_without_cached_authority(tmp_path):
    clock = FakeServiceClock(at(10))
    path = tmp_path / 'sessions.json'
    shared = policy(path, clock)
    assert shared.classify(clock()).session is MarketSession.UNKNOWN
    save(tmp_path, notice())
    assert shared.classify(clock()).executable
    clock.advance(wall_seconds=24 * 3600)
    assert shared.classify(clock()).session is MarketSession.UNKNOWN


def test_calendar_refresh_requeries_unknown_and_current_witness():
    from trading_bot.data_source import ObservedKRXCalendar
    calls = []
    witness = [None, True, False]

    class Adapter:
        def fetch_market_ohlcv(self, *args, **kwargs):
            calls.append('fetch')
            raise RuntimeError('offline uncertainty')

    calendar = ObservedKRXCalendar(Adapter(), current_date=lambda: DAY,
                                   calendar_witness=lambda day: witness.pop(0))
    assert calendar.is_trading_day(DAY) is None
    assert calendar.refresh(DAY) is True
    assert calendar.refresh(DAY) is False
    assert calls == ['fetch', 'fetch', 'fetch']


def test_calendar_refresh_retains_confirmed_historical_cache():
    from trading_bot.data_source import ObservedKRXCalendar
    from trading_bot.data_models import OhlcvResult, SourceHealth, SourceStatus
    calls = []

    class Adapter:
        def fetch_market_ohlcv(self, *args, **kwargs):
            calls.append('fetch')
            return OhlcvResult(frame=object(), health=SourceHealth(
                source='pykrx', status=SourceStatus.AVAILABLE, reason='ok'))

    calendar = ObservedKRXCalendar(Adapter(), current_date=lambda: DAY)
    prior = DAY - timedelta(days=1)
    assert calendar.is_trading_day(prior) is True
    assert calendar.refresh(prior) is True
    assert calls == ['fetch']
