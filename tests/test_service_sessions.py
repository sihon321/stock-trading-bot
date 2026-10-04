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


def test_loader_aliases_and_positive_holiday(tmp_path):
    from trading_bot.session_evidence import load_session_evidence
    clock = FakeServiceClock(at(10))
    value = notice()
    value['date'] = value.pop('trading_date_kst')
    value['content_hash'] = value.pop('source_hash')
    path = save(tmp_path, {'sessions': [value]})
    assert load_session_evidence(path, DAY, clock).continuous_open == at(9)
    path = save(tmp_path, notice('holiday'))
    assert policy(path, clock, False).classify(clock()).session is MarketSession.CLOSED_DAY


def test_duplicate_fields_and_alias_conflicts_are_not_authority(tmp_path):
    clock = FakeServiceClock(at(10))
    path = save(tmp_path, notice(date=DAY.isoformat()))
    assert not policy(path, clock).classify(clock()).executable
    path.write_text(json.dumps(notice())[:-1] + ', "reviewer": "other"}')
    assert not policy(path, clock).classify(clock()).executable


def test_policy_refreshes_current_unknown_calendar_with_same_saved_session(tmp_path):
    from trading_bot.data_source import ObservedKRXCalendar
    witness = [None, True]

    class Adapter:
        def fetch_market_ohlcv(self, *args, **kwargs):
            raise RuntimeError('offline')

    from trading_bot.session_evidence import SessionEvidenceProvider
    clock = FakeServiceClock(at(10))
    calendar = ObservedKRXCalendar(Adapter(), current_date=lambda: DAY,
                                   calendar_witness=lambda day: witness.pop(0))
    shared = MarketCyclePolicy(calendar, session_evidence_provider=SessionEvidenceProvider(
        save(tmp_path, notice()), clock))
    assert shared.classify(clock()).session is MarketSession.UNKNOWN
    assert shared.classify(clock()).executable


@pytest.mark.parametrize(('kind', 'instant', 'expected'), [
    ('normal', at(8, 50), 'PREFLIGHT_READ_ONLY'),
    ('normal', at(9), 'ACTIVE'),
    ('delayed', at(9), 'PREFLIGHT_READ_ONLY'),
    ('delayed', at(9, 19, 59), 'PREFLIGHT_READ_ONLY'),
    ('delayed', at(10), 'ACTIVE'),
    ('delayed', at(15, 19, 59), 'ACTIVE'),
    ('delayed', at(15, 20), 'RECONCILE_ONLY'),
    ('delayed', at(15, 30), 'TERMINAL'),
    ('unknown', at(10), 'RECOVERY_ONLY'),
    ('holiday', at(10), 'RECOVERY_ONLY'),
])
def test_intraday_uses_shared_session_authority(tmp_path, kind, instant, expected):
    from trading_bot.intraday import session_phase_at
    clock = FakeServiceClock(instant)
    shared = policy(save(tmp_path, notice(kind)), clock, kind != 'holiday')
    assert session_phase_at(clock(), policy=shared).value == expected


def check_kwargs(clock, calls):
    from trading_bot.domain import Money
    from trading_bot.risk import RiskConfig
    from test_exit_manager import _snapshot
    return dict(clock=clock, snapshot_reader=lambda: (calls.append('snapshot'), _snapshot())[1],
        quote_reader=lambda ticker: Money(50_000, 'KRW'), risk_config=RiskConfig(0.05, 0.10),
        lease=type('Lease', (), {'assert_active_owner': lambda self: None})(),
        exit_submitter=lambda candidate, price: calls.append('post'), audit_sink=lambda result: None,
        reconcile=lambda: calls.append('reconcile'))


@pytest.mark.parametrize(('kind', 'instant', 'expected_calls'), [
    ('normal', at(8, 50), []), ('delayed', at(9, 10), []),
    ('unknown', at(10), []), ('normal', at(15, 20), ['reconcile']),
    ('delayed', at(15, 30), []),
])
def test_nonactive_check_never_constructs_risk_or_post(tmp_path, kind, instant, expected_calls):
    from trading_bot.intraday import run_intraday_check
    calls = []
    clock = FakeServiceClock(instant)
    shared = policy(save(tmp_path, notice(kind)), clock)
    run_intraday_check(**check_kwargs(clock, calls), policy=shared)
    assert calls == expected_calls


def test_intraday_early_close_and_unknown_absolute_cutoffs(tmp_path):
    from trading_bot.intraday import session_phase_at
    clock = FakeServiceClock(at(14))
    shared = policy(save(tmp_path, notice(continuous_close=at(14).isoformat())), clock)
    assert session_phase_at(clock(), policy=shared).value == 'RECONCILE_ONLY'
    missing = policy(tmp_path / 'missing', clock)
    assert session_phase_at(at(15, 20), policy=missing).value == 'RECONCILE_ONLY'
    assert session_phase_at(at(15, 30), policy=missing).value == 'TERMINAL'


def test_session_rechecked_after_slow_quote_before_post(tmp_path):
    from trading_bot.intraday import run_intraday_check
    from trading_bot.domain import Money
    calls = []
    clock = FakeServiceClock(at(15, 19, 59))
    shared = policy(save(tmp_path, notice('delayed')), clock)
    kwargs = check_kwargs(clock, calls)

    def quote(ticker):
        clock.advance(wall_seconds=1)
        return Money(50_000, 'KRW')

    kwargs['quote_reader'] = quote
    result = run_intraday_check(**kwargs, policy=shared)
    assert 'post' not in calls
    assert result.phase.value == 'RECONCILE_ONLY'


def test_watch_wakes_at_cutoff_and_terminates_without_post(tmp_path):
    from trading_bot.intraday import run_intraday_watch
    calls = []
    clock = FakeServiceClock(at(9, 10))
    shared = policy(save(tmp_path, notice('delayed')), clock)
    advances = iter([6 * 3600 + 10 * 60, 10 * 60])
    watch = run_intraday_watch(**check_kwargs(clock, calls), policy=shared,
        sleeper=lambda seconds: clock.advance(wall_seconds=next(advances)),
        stop_requested=lambda: False, terminalize=lambda: calls.append('terminalize'))
    assert watch.final_phase.value == 'TERMINAL'
    assert calls == ['reconcile', 'terminalize', 'reconcile']


def test_watch_midnight_rollover_terminates_previous_day(tmp_path):
    from trading_bot.intraday import run_intraday_watch
    calls = []
    clock = FakeServiceClock(at(14))
    shared = policy(save(tmp_path, notice('unknown')), clock)
    watch = run_intraday_watch(**check_kwargs(clock, calls), policy=shared,
        sleeper=lambda seconds: clock.advance(wall_seconds=11 * 3600),
        stop_requested=lambda: False, terminalize=lambda: calls.append('terminalize'),
        max_iterations=2)
    assert watch.final_phase.value == 'TERMINAL'
    assert calls == ['terminalize', 'reconcile']
