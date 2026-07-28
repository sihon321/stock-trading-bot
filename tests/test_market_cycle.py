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


def test_observed_calendar_treats_current_day_empty_ohlcv_as_unknown():
    from trading_bot.data_models import OhlcvResult, SourceHealth, SourceStatus

    class Adapter:
        def fetch_market_ohlcv(self, day, *, market, min_rows):
            return OhlcvResult(
                frame=None,
                health=SourceHealth(
                    source="pykrx",
                    status=SourceStatus.UNAVAILABLE,
                    reason="empty OHLCV frame after validation",
                    expected_date=day,
                ),
            )

    calendar = ObservedKRXCalendar(
        Adapter(), current_date=lambda: date(2026, 7, 24)
    )
    assert calendar.is_trading_day(date(2026, 7, 24)) is None
    assert calendar.is_trading_day(date(2026, 7, 23)) is False


def test_observed_calendar_uses_only_explicit_current_day_mock_witness_for_pykrx_lag():
    from trading_bot.data_models import OhlcvResult, SourceHealth, SourceStatus

    calls: list[date] = []

    class Adapter:
        def fetch_market_ohlcv(self, day, *, market, min_rows):
            return OhlcvResult(
                frame=None,
                health=SourceHealth(
                    source="pykrx", status=SourceStatus.UNAVAILABLE, reason="empty OHLCV frame"
                ),
            )

    calendar = ObservedKRXCalendar(
        Adapter(),
        current_date=lambda: date(2026, 7, 24),
        calendar_witness=lambda day: calls.append(day) or True,
    )
    policy = MarketCyclePolicy(calendar)

    assert calendar.is_trading_day(date(2026, 7, 24)) is True
    assert calls == [date(2026, 7, 24)]
    evidence = policy.classify(datetime(2026, 7, 24, 9, 0, tzinfo=KST))
    assert evidence.session is MarketSession.CONTINUOUS
    assert evidence.executable


@pytest.mark.parametrize("witness", [lambda _day: None, lambda _day: "Y"])
def test_observed_calendar_keeps_missing_or_invalid_current_day_witness_unknown(witness):
    from trading_bot.data_models import OhlcvResult, SourceHealth, SourceStatus

    class Adapter:
        def fetch_market_ohlcv(self, day, *, market, min_rows):
            return OhlcvResult(
                frame=None,
                health=SourceHealth(
                    source="pykrx", status=SourceStatus.UNAVAILABLE, reason="empty OHLCV frame"
                ),
            )

    calendar = ObservedKRXCalendar(
        Adapter(), current_date=lambda: date(2026, 7, 24), calendar_witness=witness
    )
    evidence = MarketCyclePolicy(calendar).classify(datetime(2026, 7, 24, 10, 0, tzinfo=KST))
    assert evidence.session is MarketSession.UNKNOWN
    assert not evidence.executable


def test_observed_calendar_treats_witness_exception_as_unknown_and_historical_empty_as_closed():
    from trading_bot.data_models import OhlcvResult, SourceHealth, SourceStatus

    class Adapter:
        def fetch_market_ohlcv(self, day, *, market, min_rows):
            return OhlcvResult(
                frame=None,
                health=SourceHealth(
                    source="pykrx", status=SourceStatus.UNAVAILABLE, reason="empty OHLCV frame"
                ),
            )

    def broken_witness(_day):
        raise RuntimeError("untrusted provider detail")

    calendar = ObservedKRXCalendar(
        Adapter(), current_date=lambda: date(2026, 7, 24), calendar_witness=broken_witness
    )
    assert calendar.is_trading_day(date(2026, 7, 24)) is None
    assert calendar.is_trading_day(date(2026, 7, 23)) is False


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


@pytest.mark.parametrize("outcome", ["exception", "unavailable", "malformed", "empty"])
@pytest.mark.parametrize("witness_value, expected", [(True, True), (False, False)])
def test_observed_calendar_uses_exact_witness_for_every_current_day_pykrx_uncertainty(
    outcome: str, witness_value: bool, expected: bool
) -> None:
    from trading_bot.data_models import OhlcvResult, SourceHealth, SourceStatus

    calls: list[date] = []

    class Adapter:
        def fetch_market_ohlcv(self, day, *, market, min_rows):
            if outcome == "exception":
                raise RuntimeError("untrusted pykrx response body")
            if outcome == "malformed":
                return object()
            if outcome == "empty":
                return OhlcvResult(
                    frame=None,
                    health=SourceHealth(source="pykrx", status=SourceStatus.UNAVAILABLE, reason="empty OHLCV frame"),
                )
            return OhlcvResult(
                frame=None,
                health=SourceHealth(source="pykrx", status=SourceStatus.UNAVAILABLE, reason="provider timeout: payload"),
            )

    current_day = date(2026, 7, 24)
    calendar = ObservedKRXCalendar(
        Adapter(), current_date=lambda: current_day,
        calendar_witness=lambda day: calls.append(day) or witness_value,
    )

    assert calendar.is_trading_day(current_day) is expected
    assert calendar.is_trading_day(current_day) is expected
    assert calls == [current_day]
    assert calendar.diagnostic_for(current_day) is None


@pytest.mark.parametrize("outcome", ["exception", "unavailable", "malformed", "empty"])
@pytest.mark.parametrize("witness", [None, lambda _day: None, lambda _day: "Y"])
def test_observed_calendar_current_day_weak_witness_stays_unknown_with_safe_diagnostic(
    outcome: str, witness
) -> None:
    from trading_bot.data_models import OhlcvResult, SourceHealth, SourceStatus

    class Adapter:
        def fetch_market_ohlcv(self, day, *, market, min_rows):
            if outcome == "exception":
                raise RuntimeError("secret pykrx provider response")
            if outcome == "malformed":
                return object()
            return OhlcvResult(
                frame=None,
                health=SourceHealth(
                    source="pykrx", status=SourceStatus.UNAVAILABLE,
                    reason="secret provider payload" if outcome == "unavailable" else "empty OHLCV frame",
                ),
            )

    current_day = date(2026, 7, 24)
    calendar = ObservedKRXCalendar(Adapter(), current_date=lambda: current_day, calendar_witness=witness)

    assert calendar.is_trading_day(current_day) is None
    diagnostic = calendar.diagnostic_for(current_day)
    assert diagnostic == (
        "PYKRX_CURRENT_UNCERTAIN_NO_WITNESS"
        if witness is None else "PYKRX_CURRENT_UNCERTAIN_KIS_WITNESS_UNAVAILABLE"
    )
    assert "secret" not in diagnostic.lower()
    assert "payload" not in diagnostic.lower()


def test_observed_calendar_current_day_witness_exception_is_safe_and_cached() -> None:
    from trading_bot.data_models import OhlcvResult, SourceHealth, SourceStatus

    calls = 0

    class Adapter:
        def fetch_market_ohlcv(self, day, *, market, min_rows):
            return OhlcvResult(
                frame=None,
                health=SourceHealth(source="pykrx", status=SourceStatus.UNAVAILABLE, reason="no OHLCV"),
            )

    def witness(_day):
        nonlocal calls
        calls += 1
        raise RuntimeError("KIS secret response")

    current_day = date(2026, 7, 24)
    calendar = ObservedKRXCalendar(Adapter(), current_date=lambda: current_day, calendar_witness=witness)
    assert calendar.is_trading_day(current_day) is None
    assert calendar.is_trading_day(current_day) is None
    assert calls == 1
    assert calendar.diagnostic_for(current_day) == "PYKRX_CURRENT_UNCERTAIN_KIS_WITNESS_UNAVAILABLE"
