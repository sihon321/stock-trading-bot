"""Thin synchronous DataSource orchestrator wiring Wave 1-2 components (Plan 03-06).

This is the ONLY Phase 3 module that composes the source adapters and pure
transforms into a concrete :class:`~trading_bot.ports.DataSource`. It preserves
the D-13 split: it re-implements none of the adapter/transform logic and only
sequences their typed results, applies the hybrid freshness policy (D-01), and
emits a compact LLM-facing :class:`~trading_bot.domain.DataContext` (D-04) — or a
typed no-context :class:`DataSourceResult` with ``SKIP_CANDIDATE`` / ``FORCE_HOLD``
audit events and visible warnings (D-03) — so bad, stale, missing, throttled, or
unavailable data can never create a tradeable context with a default price
(threat T-03-06-T).

Rich source metadata (headers, tokens, vendor payloads, source health) is kept
OUT of ``DataContext`` (threat T-03-06-I) and lives only on the internal
``DataSourceResult``. Core ``ports.py`` stays adapter-free; concrete adapters are
opt-in through this module (threat T-03-06-E).

This module does NOT implement LLM calls, prompt assembly, orders, notifications,
scheduling, backtesting, or portfolio optimization — those remain later phases.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, List, Mapping, Optional, Tuple

from trading_bot.data_models import (
    DataAction,
    DataSourceAuditEvent,
    IndicatorConfig,
    OhlcvResult,
    SourceHealth,
    SourceStatus,
    TickerRole,
    emit_data_warning,
    resolve_data_action,
)
from trading_bot.domain import DataContext, Money, Ticker
from trading_bot.indicators import IndicatorResult, calculate_technicals
from trading_bot.kis_quote import KisQuoteResult
from trading_bot.naver_news import NaverNewsResult
from trading_bot.pykrx_adapter import PykrxOhlcvAdapter
from trading_bot.screener import (
    ScreenerResult,
    build_screener_config,
    screen_candidates,
)


class NoContextError(RuntimeError):
    """Raised by :meth:`MarketDataSource.build_context` when policy forbids context.

    Carries the resolved :class:`DataSourceResult` so callers that want the
    richer action/audit outcome can inspect it. The plain ``build_context``
    Protocol method fails closed by raising rather than fabricating a
    zero/default-price :class:`~trading_bot.domain.DataContext` (threat T-03-06-T).
    """

    def __init__(self, result: "DataSourceResult") -> None:
        super().__init__(
            f"no tradeable context for {result.ticker}: action={result.action.value}"
        )
        self.result = result


# Pure indicator transform signature: (frame, IndicatorConfig) -> IndicatorResult.
IndicatorFn = Callable[[Any, IndicatorConfig], IndicatorResult]


@dataclass(frozen=True)
class DataSourceConfig:
    """Point-in-time policy inputs for one orchestration pass (D-01/D-12).

    Attributes:
        expected_date: Explicit Asia/Seoul KRX trading date (``YYYYMMDD``) the
            OHLCV fetch targets — never an implicit current-date lookup.
        accepted_latest_date: Last valid KRX trading day when ``expected_date`` is
            a natural closure, so a legitimate holiday/weekend is AVAILABLE.
        indicator_config: Window configuration for the pure indicator transform.
        lookback_days: OHLCV history window passed to the pykrx adapter.
        min_rows: Minimum OHLCV rows required before a frame is usable.
    """

    expected_date: str
    accepted_latest_date: Optional[str] = None
    indicator_config: IndicatorConfig = field(default_factory=IndicatorConfig)
    lookback_days: int = 90
    min_rows: int = 20


@dataclass(frozen=True)
class DataSourceResult:
    """Rich internal outcome of one orchestration pass, kept out of ``DataContext``.

    ``context`` is a compact :class:`~trading_bot.domain.DataContext` only when
    ``action`` is :attr:`DataAction.BUILD_CONTEXT`; otherwise it is ``None`` and
    ``audit_events`` records why the ticker was skipped or frozen (D-03).
    """

    ticker: str
    role: TickerRole
    action: DataAction
    context: Optional[DataContext]
    audit_events: Tuple[DataSourceAuditEvent, ...] = ()


class MarketDataSource:
    """Concrete synchronous :class:`~trading_bot.ports.DataSource` orchestrator.

    Composes, in fixed order, the pykrx OHLCV adapter (03-02), the pure indicator
    transform (03-02), the KIS quote adapter (03-04), and the Naver news adapter
    (03-05). Every required source must resolve to AVAILABLE before a context is
    built; the first unhealthy required source resolves the whole pass to
    ``SKIP_CANDIDATE`` (candidate) or ``FORCE_HOLD`` (holding) per D-01. News is
    optional and fail-soft: an unavailable news source degrades to empty news
    rather than blocking the context (D-06).

    Args:
        ohlcv_adapter: Object exposing ``fetch_daily_ohlcv(ticker, expected_date,
            **kw) -> OhlcvResult`` and, for screening, ``fetch_market_rows(
            trading_date) -> rows``. Injectable for offline tests.
        indicator_fn: Pure ``(frame, IndicatorConfig) -> IndicatorResult`` transform.
        quote_adapter: Object exposing ``fetch_current_price(ticker) -> KisQuoteResult``.
        news_adapter: Object exposing ``fetch_news(ticker) -> NaverNewsResult``.
        config: Point-in-time :class:`DataSourceConfig`.
        settings: Optional :class:`~trading_bot.config.Settings` used to build the
            screener policy for :meth:`screen_daily_candidates`.
    """

    def __init__(
        self,
        *,
        ohlcv_adapter: Any,
        indicator_fn: IndicatorFn,
        quote_adapter: Any,
        news_adapter: Any,
        config: DataSourceConfig,
        settings: Any = None,
    ) -> None:
        self._ohlcv_adapter = ohlcv_adapter
        self._indicator_fn = indicator_fn
        self._quote_adapter = quote_adapter
        self._news_adapter = news_adapter
        self._config = config
        self._settings = settings

    # -- DataSource Protocol -------------------------------------------------

    def build_context(self, ticker: Ticker) -> DataContext:
        """Build compact context for ``ticker`` or fail closed (Protocol method).

        Treats the ticker as a CANDIDATE for the plain Protocol call. Raises
        :class:`NoContextError` when source-health policy forbids a context so a
        bad-data pass can never return a zero/default-price context.
        """

        result = self.build_context_result(ticker, TickerRole.CANDIDATE)
        if result.context is None:
            raise NoContextError(result)
        return result.context

    # -- Rich internal orchestration -----------------------------------------

    def build_context_result(
        self, ticker: Ticker, ticker_role: TickerRole
    ) -> DataSourceResult:
        """Compose sources and resolve the hybrid freshness policy (D-01/D-02/D-03).

        Returns a :class:`DataSourceResult` carrying either a compact
        ``DataContext`` (BUILD_CONTEXT) or a typed no-context skip/freeze outcome
        with audit events and visible console warnings.
        """

        symbol = ticker.value
        audits: List[DataSourceAuditEvent] = []

        # 1) Daily OHLCV (required).
        ohlcv = self._ohlcv_adapter.fetch_daily_ohlcv(
            symbol,
            self._config.expected_date,
            lookback_days=self._config.lookback_days,
            min_rows=self._config.min_rows,
            accepted_latest_date=self._config.accepted_latest_date,
        )
        blocked = self._guard(symbol, ticker_role, ohlcv.health, audits)
        if blocked is not None:
            return self._no_context(symbol, ticker_role, blocked, audits)

        # 2) Indicators (required pure transform over the validated frame).
        indicators = self._indicator_fn(ohlcv.frame, self._config.indicator_config)
        blocked = self._guard(symbol, ticker_role, indicators.health, audits)
        if blocked is not None:
            return self._no_context(symbol, ticker_role, blocked, audits)

        # 3) KIS current price (required).
        quote = self._quote_adapter.fetch_current_price(symbol)
        blocked = self._guard(symbol, ticker_role, quote.health, audits)
        if blocked is not None:
            return self._no_context(symbol, ticker_role, blocked, audits)

        # 4) Naver news (optional, fail-soft: empty news never blocks context).
        news = self._news_adapter.fetch_news(symbol)
        news_strings = tuple(news.rendered) if news.rendered else ()

        # All required sources AVAILABLE and a positive price is guaranteed by the
        # quote adapter's own validation; build the compact context.
        price = quote.price
        assert price is not None  # AVAILABLE quote always carries a Money price.
        context = DataContext(
            ticker=ticker,
            current_price=price,
            technicals=dict(indicators.technicals),
            news=news_strings,
        )
        return DataSourceResult(
            ticker=symbol,
            role=ticker_role,
            action=DataAction.BUILD_CONTEXT,
            context=context,
            audit_events=tuple(audits),
        )

    # -- Screener composition (DATA-05) --------------------------------------

    def screen_daily_candidates(
        self,
        trading_date: str,
        *,
        progress: Optional[Callable[[str], None]] = None,
    ) -> ScreenerResult:
        """Compose the pykrx market adapter with the pure screener (DATA-05, D-13).

        Fetches per-ticker screener rows from the OHLCV adapter, then delegates
        all filtering/ranking to the pure :func:`~trading_bot.screener.screen_candidates`
        transform. Requires ``settings`` to build the screener policy.
        """

        if self._settings is None:
            raise ValueError("screen_daily_candidates requires Settings")

        if progress is None:
            rows = self._ohlcv_adapter.fetch_market_rows(trading_date)
        else:
            rows = self._ohlcv_adapter.fetch_market_rows(
                trading_date,
                progress=progress,
            )
        config = build_screener_config(self._settings)
        return screen_candidates(trading_date, rows, config)

    # -- Policy helpers ------------------------------------------------------

    def _guard(
        self,
        ticker: str,
        role: TickerRole,
        health: SourceHealth,
        audits: List[DataSourceAuditEvent],
    ) -> Optional[DataAction]:
        """Resolve one source's health into a blocking action, or ``None`` if OK.

        On a non-AVAILABLE required source, emits a visible warning + audit event
        and returns the blocking :class:`DataAction` (SKIP_CANDIDATE/FORCE_HOLD).
        """

        action = resolve_data_action(health, role)
        if action is DataAction.BUILD_CONTEXT:
            return None
        audits.append(emit_data_warning(ticker, health, action))
        return action

    def _no_context(
        self,
        ticker: str,
        role: TickerRole,
        action: DataAction,
        audits: List[DataSourceAuditEvent],
    ) -> DataSourceResult:
        return DataSourceResult(
            ticker=ticker,
            role=role,
            action=action,
            context=None,
            audit_events=tuple(audits),
        )


# ---------------------------------------------------------------------------
# Factory wiring for the real adapters (production use).
# ---------------------------------------------------------------------------


def build_data_source_config(
    settings: Any,
    *,
    expected_date: str,
    accepted_latest_date: Optional[str] = None,
) -> DataSourceConfig:
    """Build a :class:`DataSourceConfig` for a point-in-time run from ``Settings``.

    ``expected_date`` and ``accepted_latest_date`` are supplied by the caller so
    the trading date stays an explicit, auditable input (D-01/D-12) rather than an
    implicit current-date lookup.
    """

    return DataSourceConfig(
        expected_date=expected_date,
        accepted_latest_date=accepted_latest_date,
        indicator_config=IndicatorConfig(),
    )


def build_data_source(
    settings: Any,
    *,
    expected_date: str,
    accepted_latest_date: Optional[str] = None,
    ohlcv_adapter: Any = None,
    quote_adapter: Any = None,
    news_adapter: Any = None,
    indicator_fn: Optional[IndicatorFn] = None,
) -> MarketDataSource:
    """Wire the real Wave 1-2 adapters into a :class:`MarketDataSource`.

    Each adapter is injectable so tests and future variants can substitute fakes;
    when omitted, the real adapters are constructed from ``Settings`` policy. KIS
    quote wiring requires a shared :class:`~trading_bot.kis_auth.KisTokenManager`
    (D-14), so a real ``quote_adapter`` MUST be provided by the caller who owns the
    token manager — this factory does not open a second token flow.
    """

    config = build_data_source_config(
        settings,
        expected_date=expected_date,
        accepted_latest_date=accepted_latest_date,
    )

    if ohlcv_adapter is None:
        ohlcv_adapter = PykrxOhlcvAdapter(
            adjusted=settings.ohlcv_adjusted,
            request_timeout_seconds=settings.pykrx_request_timeout_seconds,
        )

    if quote_adapter is None:
        raise ValueError(
            "build_data_source requires a quote_adapter built from the shared "
            "KisTokenManager (D-14); the factory does not open a second token flow"
        )

    if news_adapter is None:
        from trading_bot.naver_news import NaverNewsAdapter

        news_adapter = NaverNewsAdapter(
            enabled=settings.naver_news_enabled,
            max_items=settings.naver_news_max_items,
            max_chars=settings.naver_news_max_chars,
        )

    if indicator_fn is None:
        indicator_fn = calculate_technicals

    return MarketDataSource(
        ohlcv_adapter=ohlcv_adapter,
        indicator_fn=indicator_fn,
        quote_adapter=quote_adapter,
        news_adapter=news_adapter,
        config=config,
        settings=settings,
    )
