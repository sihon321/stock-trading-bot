from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from trading_bot.market_cycle import (
    CalendarState,
    MarketCyclePolicy,
    MarketSession,
    QuoteObservation,
)
from trading_bot.data_source import ObservedKRXCalendar

KST = ZoneInfo("Asia/Seoul")


class FakeCalendar:
    def __init__(self, *, open_day=True, previous=date(2026, 7, 10), error=False):
        self.open_day = open_day
        self.previous = previous
        self.error = error

    def is_trading_day(self, day):
        if self.error:
            raise RuntimeError("calendar down")
        return self.open_day

    def previous_trading_day(self, day):
        if self.error:
            raise RuntimeError("calendar down")
        return self.previous


def at(hour, minute, second=0):
    return datetime(2026, 7, 13, hour, minute, second, tzinfo=KST)


@pytest.mark.parametrize(
    ("instant", "session", "executable"),
    [
        (at(8, 59, 59), MarketSession.PRE_OPEN, False),
        (at(9, 0), MarketSession.CONTINUOUS, True),
        (at(15, 19, 59), MarketSession.CONTINUOUS, True),
        (at(15, 20), MarketSession.CLOSING_AUCTION, False),
        (at(15, 30), MarketSession.CLOSING_AUCTION, False),
        (at(15, 30, 1), MarketSession.AFTER_HOURS, False),
    ],
)
def test_continuous_session_is_half_open(instant, session, executable):
    evidence = MarketCyclePolicy(FakeCalendar()).classify(instant)
    assert evidence.session is session
    assert evidence.executable is executable
    assert evidence.policy_version == "krx-continuous-v1"


def test_confirmed_closure_and_unknown_provider_fail_closed():
    closed = MarketCyclePolicy(FakeCalendar(open_day=False)).classify(at(10, 0))
    assert closed.calendar_state is CalendarState.CLOSED_DAY
    assert closed.session is MarketSession.CLOSED_DAY
    assert not closed.executable

    unknown = MarketCyclePolicy(FakeCalendar(error=True)).classify(at(10, 0))
    assert unknown.calendar_state is CalendarState.UNKNOWN
    assert unknown.session is MarketSession.UNKNOWN
    assert not unknown.executable


def test_completed_bar_cutoff_is_previous_confirmed_day():
    policy = MarketCyclePolicy(FakeCalendar(previous=date(2026, 7, 10)))
    cutoff = policy.completed_bar_cutoff(date(2026, 7, 13))
    assert cutoff.available
    assert cutoff.requested_date == date(2026, 7, 13)
    assert cutoff.cutoff_date == date(2026, 7, 10)

    unavailable = MarketCyclePolicy(FakeCalendar(error=True)).completed_bar_cutoff(date(2026, 7, 13))
    assert not unavailable.available
    assert unavailable.cutoff_date is None


@pytest.mark.parametrize(("age", "fresh"), [(9.999, True), (10.0, True), (10.001, False)])
def test_quote_age_uses_inclusive_ten_second_limit(age, fresh):
    checked = at(10, 0)
    result = MarketCyclePolicy(FakeCalendar()).quote_freshness(
        QuoteObservation(checked - timedelta(seconds=age)), checked
    )
    assert result.fresh is fresh
    assert result.age_seconds == pytest.approx(age)


def test_future_and_naive_quote_timestamps_fail_closed():
    checked = at(10, 0)
    policy = MarketCyclePolicy(FakeCalendar())
    assert not policy.quote_freshness(
        QuoteObservation(checked + timedelta(milliseconds=1)), checked
    ).fresh
    assert not policy.quote_freshness(
        QuoteObservation(datetime(2026, 7, 13, 10, 0)), checked
    ).fresh


def test_observed_calendar_distinguishes_closure_from_provider_failure():
    from trading_bot.data_models import OhlcvResult, SourceHealth, SourceStatus

    class Adapter:
        def fetch_market_ohlcv(self, day, *, market, min_rows):
            reason = ("empty OHLCV frame" if day == "20260712"
                      else "pykrx market fetch failed: TimeoutError")
            return OhlcvResult(
                frame=None,
                health=SourceHealth(source="pykrx", status=SourceStatus.UNAVAILABLE, reason=reason),
            )

    calendar = ObservedKRXCalendar(Adapter())
    assert calendar.is_trading_day(date(2026, 7, 12)) is False
    assert calendar.is_trading_day(date(2026, 7, 13)) is None


def test_observed_calendar_rejects_available_but_empty_holiday_frame():
    import pandas as pd

    from trading_bot.data_models import OhlcvResult, SourceHealth, SourceStatus

    class Adapter:
        def fetch_market_ohlcv(self, day, *, market, min_rows):
            return OhlcvResult(
                frame=pd.DataFrame(),
                health=SourceHealth(
                    source="pykrx",
                    status=SourceStatus.AVAILABLE,
                    reason="ok",
                    expected_date=day,
                ),
            )

    assert ObservedKRXCalendar(Adapter()).is_trading_day(date(2026, 7, 12)) is False


def test_observed_calendar_resolves_immediately_previous_confirmed_day():
    from trading_bot.data_models import OhlcvResult, SourceHealth, SourceStatus

    class Adapter:
        def fetch_market_ohlcv(self, day, *, market, min_rows):
            available = day == "20260710"
            return OhlcvResult(
                frame=object() if available else None,
                health=SourceHealth(
                    source="pykrx",
                    status=SourceStatus.AVAILABLE if available else SourceStatus.UNAVAILABLE,
                    reason="ok" if available else "empty OHLCV frame",
                ),
            )

    assert ObservedKRXCalendar(Adapter()).previous_trading_day(date(2026, 7, 13)) == date(2026, 7, 10)
