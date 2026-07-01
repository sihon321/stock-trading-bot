"""Pure daily volatility-breakout screener (DATA-05, D-07/D-10/D-11/D-13).

This module is a pure transform in the spirit of :mod:`trading_bot.risk` and
:mod:`trading_bot.indicators`: it takes already-fetched, already-validated inputs
(an asserted trading date, per-ticker source health, technicals, trading value,
market, and ticker state) plus an explicit :class:`ScreenerConfig`, and returns a
:class:`ScreenerResult` with a capped, ranked candidate universe and audit
evidence for every exclusion. It performs NO pykrx / HTTP / KIS / Naver calls —
those live behind the source adapters (D-13). This boundary is guarded by an
import test.

Safety order (D-11): hard exclusions run BEFORE ranking. Unhealthy source data,
low liquidity (trading-value floor), low volume ratio, suspended/halted/excluded
states, out-of-scope markets, and missing/non-finite technicals are all dropped
into ``SKIP_CANDIDATE`` audit events (D-03) so bad data can never influence a BUY.
Only survivors are scored. Ranking (D-07/D-10) puts ATR / historical volatility
and a liquidity floor first, then volume expansion and recent momentum order the
surviving set. Candidate breadth and market inclusion are configurable (D-08/D-09)
and driven from :class:`~trading_bot.config.Settings`, never hard-coded.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple

from trading_bot.data_models import (
    DataSourceAuditEvent,
    SourceHealth,
    SourceStatus,
)

_SOURCE = "screener"
_ACTION_SKIP = "SKIP_CANDIDATE"

# Technicals that must be present and finite for a ticker to be scoreable.
_REQUIRED_TECHNICALS = (
    "atr_14",
    "historical_volatility",
    "volume_ratio",
    "rsi_14",
    "sma_short",
    "sma_long",
)


@dataclass(frozen=True)
class ScreenerConfig:
    """Configurable screener policy, sourced from ``Settings`` (D-08/D-09/D-11).

    Attributes:
        max_candidates: Hard cap on the ranked candidate universe (D-08).
        markets: Allowed market codes, e.g. ``("KOSPI", "KOSDAQ")`` (D-09).
        min_trading_value: Liquidity floor in KRW; below this a ticker is
            hard-excluded before ranking (D-10/D-11).
        min_volume_ratio: Minimum recent-volume-expansion ratio to qualify.
        excluded_states: Ticker state flags that hard-exclude, e.g. suspended,
            halted, delisting, or admin-issue codes (D-11).
    """

    max_candidates: int
    markets: Tuple[str, ...]
    min_trading_value: float
    min_volume_ratio: float
    excluded_states: Tuple[str, ...]


@dataclass(frozen=True)
class ScreenerCandidate:
    """A survivor row with its volatility-breakout score (ranking output)."""

    ticker: str
    market: str
    score: float
    trading_value: float
    technicals: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ScreenerResult:
    """Capped, ranked candidates plus audit evidence for every exclusion.

    ``trading_date`` is the explicit asserted point-in-time KRX trading date the
    screening targeted (D-01/D-12) — never an implicit current-date lookup.
    """

    trading_date: str
    candidates: Tuple[ScreenerCandidate, ...]
    audit_events: Tuple[DataSourceAuditEvent, ...]


def build_screener_config(settings: Any) -> ScreenerConfig:
    """Build a :class:`ScreenerConfig` from Phase 3 ``Settings`` fields (D-08/D-09).

    Policy is driven entirely from settings so candidate breadth, market
    inclusion, liquidity floors, and excluded states remain operator-reviewable
    and are never hard-coded in the transform.
    """

    return ScreenerConfig(
        max_candidates=settings.screener_max_candidates,
        markets=tuple(settings.screener_markets),
        min_trading_value=settings.screener_min_trading_value,
        min_volume_ratio=settings.screener_min_volume_ratio,
        excluded_states=tuple(settings.screener_excluded_states),
    )


def screen_candidates(
    trading_date: str,
    rows: Iterable[Mapping[str, Any]],
    config: ScreenerConfig,
) -> ScreenerResult:
    """Filter unsafe tickers, then rank survivors for volatility breakout.

    Args:
        trading_date: Explicit asserted KRX trading date (``YYYYMMDD``). Never an
            implicit current-date lookup (D-01/D-12).
        rows: Per-ticker input mappings, each carrying ``ticker``, ``market``,
            ``state``, ``trading_value``, ``technicals`` (a flat ``str -> float``
            mapping), and ``health`` (a :class:`SourceHealth`).
        config: Resolved :class:`ScreenerConfig` policy.

    Returns:
        A :class:`ScreenerResult` whose ``candidates`` are ranked best-first and
        capped at ``config.max_candidates``, and whose ``audit_events`` record a
        ``SKIP_CANDIDATE`` for every excluded ticker (D-03).
    """

    survivors: list[ScreenerCandidate] = []
    audits: list[DataSourceAuditEvent] = []

    for row in rows:
        ticker = str(row.get("ticker", ""))
        market = str(row.get("market", ""))
        health = row.get("health")
        exclusion = _exclusion_reason(row, market, health, config)
        if exclusion is not None:
            audits.append(
                _skip_audit(ticker, health, market, trading_date, exclusion)
            )
            continue

        technicals = dict(row["technicals"])
        score = score_volatility_breakout(
            technicals,
            trading_value=float(row["trading_value"]),
            config=config,
        )
        survivors.append(
            ScreenerCandidate(
                ticker=ticker,
                market=market,
                score=score,
                trading_value=float(row["trading_value"]),
                technicals=technicals,
            )
        )

    # Stable rank: highest score first, ties broken by ticker for determinism.
    survivors.sort(key=lambda c: (-c.score, c.ticker))
    capped = tuple(survivors[: max(config.max_candidates, 0)])

    return ScreenerResult(
        trading_date=trading_date,
        candidates=capped,
        audit_events=tuple(audits),
    )


def score_volatility_breakout(
    technicals: Mapping[str, float],
    *,
    trading_value: float,
    config: ScreenerConfig,
) -> float:
    """Score a survivor for volatility-breakout readiness (D-07/D-10).

    ATR and historical volatility dominate, weighted by a liquidity factor above
    the configured floor, so liquid high-volatility names rank first. Volume
    expansion and recent momentum add smaller, secondary ordering terms among the
    surviving set. This function is pure and assumes the row already passed
    :func:`_exclusion_reason` (finite required technicals, liquidity/volume floors).
    """

    atr = float(technicals["atr_14"])
    hist_vol = float(technicals["historical_volatility"])
    volume_ratio = float(technicals["volume_ratio"])
    sma_short = float(technicals["sma_short"])
    sma_long = float(technicals["sma_long"])

    # Primary: volatility readiness. Historical volatility (return-scale) and ATR
    # (price-scale, normalized) both count; volatility is the dominant term.
    atr_component = atr / (abs(sma_long) + 1.0)
    volatility = (hist_vol * 100.0) + (atr_component * 10.0)

    # Liquidity factor scales the volatility term: more liquid names above the
    # floor score higher, so the liquidity floor is a primary ranking input (D-10).
    liquidity_factor = 1.0 + math.log10(
        max(trading_value / config.min_trading_value, 1.0) + 1.0
    )
    primary = volatility * liquidity_factor

    # Secondary: volume expansion beyond the floor.
    volume_component = max(volume_ratio - config.min_volume_ratio, 0.0)

    # Secondary: recent momentum via short-vs-long moving-average spread.
    momentum_component = 0.0
    if sma_long > 0:
        momentum_component = max((sma_short - sma_long) / sma_long, 0.0)

    return primary + volume_component + momentum_component


def _exclusion_reason(
    row: Mapping[str, Any],
    market: str,
    health: Optional[SourceHealth],
    config: ScreenerConfig,
) -> Optional[str]:
    """Return a non-secret hard-exclusion reason, or ``None`` if the row qualifies.

    All checks run before any scoring so unsafe data never reaches ranking (D-11).
    """

    if market not in config.markets:
        return f"market {market!r} not in configured universe"

    if not isinstance(health, SourceHealth) or health.status is not SourceStatus.AVAILABLE:
        status = health.status.value if isinstance(health, SourceHealth) else "MISSING"
        return f"source not available (status={status})"

    state = str(row.get("state", "")).upper()
    if state in {s.upper() for s in config.excluded_states}:
        return f"ticker state {state!r} is excluded"

    trading_value = _finite(row.get("trading_value"))
    if trading_value is None or trading_value < config.min_trading_value:
        return "trading value below liquidity floor"

    technicals = row.get("technicals")
    if not isinstance(technicals, Mapping) or not technicals:
        return "missing technicals"
    for key in _REQUIRED_TECHNICALS:
        value = _finite(technicals.get(key))
        if value is None:
            return f"missing or non-finite technical {key!r}"

    volume_ratio = float(technicals["volume_ratio"])
    if volume_ratio < config.min_volume_ratio:
        return "volume ratio below minimum expansion floor"

    return None


def _skip_audit(
    ticker: str,
    health: Optional[SourceHealth],
    market: str,
    trading_date: str,
    reason: str,
) -> DataSourceAuditEvent:
    """Build a ``SKIP_CANDIDATE`` audit event with only non-secret fields (D-03)."""

    if isinstance(health, SourceHealth):
        status = health.status.value
        observed = health.observed_date
        source = health.source
    else:
        status = "MISSING"
        observed = None
        source = _SOURCE

    return DataSourceAuditEvent(
        ticker=ticker,
        source=source,
        status=status,
        reason=reason,
        action=_ACTION_SKIP,
        observed_date=observed,
        expected_date=trading_date,
    )


def _finite(value: Any) -> Optional[float]:
    """Coerce ``value`` to a finite float, or return ``None``."""

    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result
