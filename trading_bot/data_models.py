"""Typed source-health, adapter-result, and audit models for the data pipeline.

These are pure standard-library frozen dataclasses and string enums, following
the same conventions as :mod:`trading_bot.domain` and :mod:`trading_bot.execution`.
They carry the source metadata and health decisions that must stay OUT of the
compact LLM-facing :class:`~trading_bot.domain.DataContext` (D-04). Every source
adapter normalizes vendor failures into these types (D-15) so the orchestrator
applies the hybrid skip/freeze policy consistently (D-01).

This module must not import vendor libraries (pykrx, httpx, requests) or any
concrete adapter — it is a shared model layer consumed by both.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class SourceStatus(str, Enum):
    """Health of a single source fetch after normalization (D-15)."""

    AVAILABLE = "AVAILABLE"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"


class DataAction(str, Enum):
    """Policy action resolved from source health and ticker role (D-01)."""

    BUILD_CONTEXT = "BUILD_CONTEXT"
    SKIP_CANDIDATE = "SKIP_CANDIDATE"
    FORCE_HOLD = "FORCE_HOLD"


class TickerRole(str, Enum):
    """Whether a ticker is a screener candidate or an existing holding (D-01).

    The hybrid freshness policy differs by role: bad data for a new candidate
    skips it, while bad data for a held position freezes actions to HOLD.
    """

    CANDIDATE = "CANDIDATE"
    HOLDING = "HOLDING"


@dataclass(frozen=True)
class SourceHealth:
    """Normalized health of a source fetch, kept out of ``DataContext`` (D-04).

    Attributes:
        source: Short source name, e.g. ``"pykrx"``. Non-secret.
        status: The normalized :class:`SourceStatus`.
        reason: Human-readable, non-secret reason category.
        observed_date: Latest observed data date (``YYYYMMDD``) when known.
        expected_date: The asserted trading date the fetch targeted.
    """

    source: str
    status: SourceStatus
    reason: str
    observed_date: Optional[str] = None
    expected_date: Optional[str] = None


@dataclass(frozen=True)
class OhlcvResult:
    """Adapter result pairing a validated OHLCV frame with its source health.

    ``frame`` is a pandas DataFrame only when ``health.status`` is
    :attr:`SourceStatus.AVAILABLE`; otherwise it is ``None`` so unusable vendor
    data can never be mistaken for tradeable input. The frame is typed ``Any``
    to keep this model layer free of a hard pandas import at type level.
    """

    frame: Optional[Any]
    health: SourceHealth


@dataclass(frozen=True)
class DataSourceAuditEvent:
    """Machine-checkable record of a skip/freeze decision (D-03).

    Records ticker, source, reason, observed/expected dates, and the action
    taken. Contains only non-secret fields — no tokens, headers, or raw vendor
    payloads (threat T-03-02-I).
    """

    ticker: str
    source: str
    status: str
    reason: str
    action: str
    observed_date: Optional[str] = None
    expected_date: Optional[str] = None


@dataclass(frozen=True)
class IndicatorConfig:
    """Window configuration for the volatility-breakout indicator transform (D-05).

    Windows are positive integers. Defaults cover a standard short/long moving
    average pair, 14-period RSI/ATR, a historical-volatility lookback, and the
    volume-ratio averaging window.
    """

    sma_short_window: int = 5
    sma_long_window: int = 20
    rsi_window: int = 14
    atr_window: int = 14
    historical_volatility_window: int = 20
    volume_ratio_window: int = 20


def resolve_data_action(health: SourceHealth, role: TickerRole) -> DataAction:
    """Resolve the hybrid freshness policy action for a source health (D-01).

    Available data builds context for either role. Bad or stale data skips a
    screener candidate but freezes a holding to HOLD so a stale/unavailable
    source can never justify a new trade.
    """

    if health.status is SourceStatus.AVAILABLE:
        return DataAction.BUILD_CONTEXT
    if role is TickerRole.HOLDING:
        return DataAction.FORCE_HOLD
    return DataAction.SKIP_CANDIDATE


def emit_data_warning(
    ticker: str,
    health: SourceHealth,
    action: DataAction,
) -> DataSourceAuditEvent:
    """Print a visible console warning and return a structured audit event (D-03).

    The printed line and returned event include ticker, source, status, reason,
    observed/expected dates, and the action taken — non-secret fields only.
    """

    event = DataSourceAuditEvent(
        ticker=ticker,
        source=health.source,
        status=health.status.value,
        reason=health.reason,
        action=action.value,
        observed_date=health.observed_date,
        expected_date=health.expected_date,
    )
    print(
        "DATA WARNING "
        f"ticker={event.ticker} source={event.source} status={event.status} "
        f"action={event.action} reason={event.reason} "
        f"observed={event.observed_date} expected={event.expected_date}"
    )
    return event
