"""Pure, dependency-free KRX cycle and quote-freshness policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from typing import Protocol
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
POLICY_VERSION = "krx-continuous-v1"


class CalendarState(StrEnum):
    TRADING_DAY = "TRADING_DAY"
    CLOSED_DAY = "CLOSED_DAY"
    UNKNOWN = "UNKNOWN"


class MarketSession(StrEnum):
    PRE_OPEN = "PRE_OPEN"
    CONTINUOUS = "CONTINUOUS"
    CLOSING_AUCTION = "CLOSING_AUCTION"
    AFTER_HOURS = "AFTER_HOURS"
    CLOSED_DAY = "CLOSED_DAY"
    UNKNOWN = "UNKNOWN"


class KRXCalendarProvider(Protocol):
    def is_trading_day(self, day: date) -> bool | None: ...

    def previous_trading_day(self, day: date) -> date | None: ...


@dataclass(frozen=True)
class MarketCycleEvidence:
    observed_at_kst: datetime
    trading_date: date
    calendar_state: CalendarState
    session: MarketSession
    executable: bool
    reason: str
    policy_version: str = POLICY_VERSION


@dataclass(frozen=True)
class CompletedBarCutoff:
    requested_date: date
    cutoff_date: date | None
    available: bool
    reason: str


@dataclass(frozen=True)
class QuoteObservation:
    observed_at: datetime


@dataclass(frozen=True)
class QuoteFreshness:
    age_seconds: float | None
    fresh: bool
    reason: str


class MarketCyclePolicy:
    """Classify market state and completed-data boundaries using an injected calendar."""

    def __init__(self, calendar: KRXCalendarProvider, *, max_quote_age_seconds: float = 10.0):
        self._calendar = calendar
        self.max_quote_age_seconds = float(max_quote_age_seconds)

    def classify(self, observed_at: datetime) -> MarketCycleEvidence:
        if observed_at.tzinfo is None:
            return self._unknown(observed_at.replace(tzinfo=KST), "naive observation time")
        kst = observed_at.astimezone(KST)
        try:
            trading_day = self._calendar.is_trading_day(kst.date())
        except Exception:  # provider uncertainty must fail closed
            return self._unknown(kst, "calendar unavailable")
        if trading_day is None:
            return self._unknown(kst, "calendar unavailable")
        if not trading_day:
            return MarketCycleEvidence(
                kst, kst.date(), CalendarState.CLOSED_DAY, MarketSession.CLOSED_DAY,
                False, "confirmed non-trading day",
            )
        local_time = kst.timetz().replace(tzinfo=None)
        if local_time < time(9, 0):
            session = MarketSession.PRE_OPEN
        elif local_time < time(15, 20):
            session = MarketSession.CONTINUOUS
        elif local_time <= time(15, 30):
            session = MarketSession.CLOSING_AUCTION
        else:
            session = MarketSession.AFTER_HOURS
        executable = session is MarketSession.CONTINUOUS
        return MarketCycleEvidence(
            kst, kst.date(), CalendarState.TRADING_DAY, session, executable,
            "continuous trading" if executable else "session is not executable",
        )

    def completed_bar_cutoff(self, requested_date: date) -> CompletedBarCutoff:
        try:
            cutoff = self._calendar.previous_trading_day(requested_date)
        except Exception:
            cutoff = None
        if cutoff is None or cutoff >= requested_date:
            return CompletedBarCutoff(requested_date, None, False, "calendar unavailable")
        return CompletedBarCutoff(requested_date, cutoff, True, "previous confirmed trading day")

    def quote_freshness(self, observation: QuoteObservation, checked_at: datetime) -> QuoteFreshness:
        if observation.observed_at.tzinfo is None or checked_at.tzinfo is None:
            return QuoteFreshness(None, False, "quote timestamps must be timezone-aware")
        age = (checked_at - observation.observed_at).total_seconds()
        if age < 0:
            return QuoteFreshness(age, False, "quote timestamp is in the future")
        fresh = age <= self.max_quote_age_seconds
        return QuoteFreshness(age, fresh, "fresh" if fresh else "quote is stale")

    @staticmethod
    def _unknown(observed_at: datetime, reason: str) -> MarketCycleEvidence:
        return MarketCycleEvidence(
            observed_at, observed_at.date(), CalendarState.UNKNOWN,
            MarketSession.UNKNOWN, False, reason,
        )

