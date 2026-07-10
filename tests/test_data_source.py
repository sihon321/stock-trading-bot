"""Offline integration tests for the thin DataSource orchestrator (Plan 03-06).

These tests wire ONLY fake adapters and pure transforms into
:class:`~trading_bot.data_source.MarketDataSource`; no pykrx, KIS, or Naver live
calls occur. They assert the D-01/D-02/D-03/D-04/D-15 safety contract:

  - Healthy OHLCV + indicators + KIS price + sanitized news -> compact
    :class:`~trading_bot.domain.DataContext` (BUILD_CONTEXT).
  - Unavailable/stale OHLCV or unavailable KIS price for a HOLDING -> FORCE_HOLD
    with a typed audit event and a visible console warning, and NO tradeable
    context (never a Money(0) default price).
  - Bad data for a CANDIDATE -> SKIP_CANDIDATE audit before candidate output.
  - News failure degrades to empty news but still builds context (fail-soft).
  - Rich source metadata stays OUT of DataContext.
  - ``screen_daily_candidates`` composes the pykrx adapter + pure screener.
"""

from __future__ import annotations

import inspect
from typing import Any, List, Mapping, Optional, Tuple

import pandas as pd
import pytest

from trading_bot.data_models import (
    DataAction,
    DataSourceAuditEvent,
    OhlcvResult,
    SourceHealth,
    SourceStatus,
    TickerRole,
)
from trading_bot.domain import DataContext, Money, Ticker
from trading_bot.indicators import IndicatorResult
from trading_bot.kis_quote import KisQuoteResult
from trading_bot.naver_news import NaverNewsResult
from trading_bot.ports import DataSource
from trading_bot.data_source import (
    DataSourceConfig,
    DataSourceResult,
    MarketDataSource,
)

EXPECTED_DATE = "20260630"
TICKER = "005930"


# ---------------------------------------------------------------------------
# Fakes: each mimics the typed result of a Wave 1-2 component without vendors.
# ---------------------------------------------------------------------------


def _ohlcv_frame() -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=30, freq="D")
    return pd.DataFrame(
        {
            "시가": [1000.0] * 30,
            "고가": [1010.0] * 30,
            "저가": [990.0] * 30,
            "종가": [1005.0] * 30,
            "거래량": [10_000] * 30,
        },
        index=idx,
    )


def _available_ohlcv() -> OhlcvResult:
    return OhlcvResult(
        frame=_ohlcv_frame(),
        health=SourceHealth(
            source="pykrx",
            status=SourceStatus.AVAILABLE,
            reason="ok",
            observed_date=EXPECTED_DATE,
            expected_date=EXPECTED_DATE,
        ),
    )


def _stale_ohlcv() -> OhlcvResult:
    return OhlcvResult(
        frame=None,
        health=SourceHealth(
            source="pykrx",
            status=SourceStatus.STALE,
            reason="latest data date is before the expected trading date",
            observed_date="20260628",
            expected_date=EXPECTED_DATE,
        ),
    )


def _unavailable_ohlcv() -> OhlcvResult:
    return OhlcvResult(
        frame=None,
        health=SourceHealth(
            source="pykrx",
            status=SourceStatus.UNAVAILABLE,
            reason="empty OHLCV frame",
            expected_date=EXPECTED_DATE,
        ),
    )


def _available_indicators() -> IndicatorResult:
    return IndicatorResult(
        technicals={
            "sma_short": 1004.0,
            "sma_long": 1002.0,
            "rsi_14": 55.0,
            "atr_14": 12.0,
            "historical_volatility": 0.02,
            "volume_ratio": 1.2,
        },
        health=SourceHealth(source="indicators", status=SourceStatus.AVAILABLE, reason="ok"),
    )


def _unavailable_indicators() -> IndicatorResult:
    return IndicatorResult(
        technicals={},
        health=SourceHealth(
            source="indicators",
            status=SourceStatus.UNAVAILABLE,
            reason="indicator warm-up produced a NaN/non-finite tail value",
        ),
    )


def _available_quote() -> KisQuoteResult:
    return KisQuoteResult(
        price=Money(70000.0, "KRW"),
        health=SourceHealth(source="kis_quote", status=SourceStatus.AVAILABLE, reason="ok"),
    )


def _unavailable_quote() -> KisQuoteResult:
    return KisQuoteResult(
        price=None,
        health=SourceHealth(
            source="kis_quote",
            status=SourceStatus.UNAVAILABLE,
            reason="KIS auth unavailable for quote",
        ),
    )


def _available_news() -> NaverNewsResult:
    return NaverNewsResult(
        articles=(),
        rendered=("Samsung reports strong quarter",),
        health=SourceHealth(source="naver_news", status=SourceStatus.AVAILABLE, reason="ok"),
    )


def _empty_news() -> NaverNewsResult:
    return NaverNewsResult(
        articles=(),
        rendered=(),
        health=SourceHealth(
            source="naver_news",
            status=SourceStatus.UNAVAILABLE,
            reason="news request returned HTTP 403",
        ),
    )


class _FakeOhlcvAdapter:
    def __init__(self, result: OhlcvResult) -> None:
        self._result = result
        self.calls: List[str] = []

    def fetch_daily_ohlcv(self, ticker: str, expected_date: str, **_: Any) -> OhlcvResult:
        self.calls.append(ticker)
        return self._result


class _FakeQuoteAdapter:
    def __init__(self, result: KisQuoteResult) -> None:
        self._result = result
        self.calls: List[str] = []

    def fetch_current_price(self, ticker: str) -> KisQuoteResult:
        self.calls.append(ticker)
        return self._result


class _FakeNewsAdapter:
    def __init__(self, result: NaverNewsResult) -> None:
        self._result = result
        self.calls: List[str] = []

    def fetch_news(self, ticker: str) -> NaverNewsResult:
        self.calls.append(ticker)
        return self._result


def _indicator_fn(result: IndicatorResult):
    def _calc(frame: Any, config: Any) -> IndicatorResult:
        return result

    return _calc


def _config() -> DataSourceConfig:
    from trading_bot.data_models import IndicatorConfig

    return DataSourceConfig(
        expected_date=EXPECTED_DATE,
        accepted_latest_date=None,
        indicator_config=IndicatorConfig(),
    )


def _build_source(
    *,
    ohlcv: OhlcvResult,
    indicators: IndicatorResult,
    quote: KisQuoteResult,
    news: NaverNewsResult,
) -> MarketDataSource:
    return MarketDataSource(
        ohlcv_adapter=_FakeOhlcvAdapter(ohlcv),
        indicator_fn=_indicator_fn(indicators),
        quote_adapter=_FakeQuoteAdapter(quote),
        news_adapter=_FakeNewsAdapter(news),
        config=_config(),
    )


# ---------------------------------------------------------------------------
# Structural port compatibility
# ---------------------------------------------------------------------------


def test_market_data_source_satisfies_datasource_protocol() -> None:
    source = _build_source(
        ohlcv=_available_ohlcv(),
        indicators=_available_indicators(),
        quote=_available_quote(),
        news=_available_news(),
    )
    assert isinstance(source, DataSource)


def test_build_context_is_synchronous() -> None:
    assert not inspect.iscoroutinefunction(MarketDataSource.build_context)
    assert not inspect.iscoroutinefunction(MarketDataSource.build_context_result)
    assert not inspect.iscoroutinefunction(MarketDataSource.screen_daily_candidates)


# ---------------------------------------------------------------------------
# Happy path: compact DataContext
# ---------------------------------------------------------------------------


def test_healthy_sources_produce_compact_context() -> None:
    source = _build_source(
        ohlcv=_available_ohlcv(),
        indicators=_available_indicators(),
        quote=_available_quote(),
        news=_available_news(),
    )
    context = source.build_context(Ticker(TICKER))

    assert isinstance(context, DataContext)
    assert context.ticker == Ticker(TICKER)
    assert context.current_price == Money(70000.0, "KRW")
    assert context.technicals["rsi_14"] == 55.0
    assert tuple(context.news) == ("Samsung reports strong quarter",)


def test_context_carries_no_source_metadata_fields() -> None:
    source = _build_source(
        ohlcv=_available_ohlcv(),
        indicators=_available_indicators(),
        quote=_available_quote(),
        news=_available_news(),
    )
    context = source.build_context(Ticker(TICKER))

    # DataContext must remain compact: only ticker/price/technicals/news (D-04).
    assert set(vars(context).keys()) == {"ticker", "current_price", "technicals", "news"}


def test_build_context_result_reports_build_action_and_audit() -> None:
    source = _build_source(
        ohlcv=_available_ohlcv(),
        indicators=_available_indicators(),
        quote=_available_quote(),
        news=_available_news(),
    )
    result = source.build_context_result(Ticker(TICKER), TickerRole.CANDIDATE)

    assert isinstance(result, DataSourceResult)
    assert result.action is DataAction.BUILD_CONTEXT
    assert result.context is not None
    assert result.context.current_price == Money(70000.0, "KRW")


# ---------------------------------------------------------------------------
# Unavailable OHLCV: candidate skip vs holding force-hold
# ---------------------------------------------------------------------------


def test_unavailable_ohlcv_candidate_is_skipped(capsys: pytest.CaptureFixture[str]) -> None:
    source = _build_source(
        ohlcv=_unavailable_ohlcv(),
        indicators=_available_indicators(),
        quote=_available_quote(),
        news=_available_news(),
    )
    result = source.build_context_result(Ticker(TICKER), TickerRole.CANDIDATE)

    assert result.action is DataAction.SKIP_CANDIDATE
    assert result.context is None
    assert any(e.action == "SKIP_CANDIDATE" for e in result.audit_events)
    assert any(e.source == "pykrx" for e in result.audit_events)
    assert "DATA WARNING" in capsys.readouterr().out


def test_stale_ohlcv_holding_forces_hold(capsys: pytest.CaptureFixture[str]) -> None:
    source = _build_source(
        ohlcv=_stale_ohlcv(),
        indicators=_available_indicators(),
        quote=_available_quote(),
        news=_available_news(),
    )
    result = source.build_context_result(Ticker(TICKER), TickerRole.HOLDING)

    assert result.action is DataAction.FORCE_HOLD
    assert result.context is None
    event = next(e for e in result.audit_events if e.source == "pykrx")
    assert event.action == "FORCE_HOLD"
    assert event.status == "STALE"
    assert event.observed_date == "20260628"
    assert event.expected_date == EXPECTED_DATE
    assert "DATA WARNING" in capsys.readouterr().out


def test_build_context_raises_on_no_context_for_holding() -> None:
    source = _build_source(
        ohlcv=_unavailable_ohlcv(),
        indicators=_available_indicators(),
        quote=_available_quote(),
        news=_available_news(),
    )
    # build_context must never fabricate a zero/default price for bad data.
    with pytest.raises(Exception):
        source.build_context(Ticker(TICKER))


# ---------------------------------------------------------------------------
# Unavailable indicators (bad transform on otherwise-fetched frame)
# ---------------------------------------------------------------------------


def test_unavailable_indicators_candidate_is_skipped() -> None:
    source = _build_source(
        ohlcv=_available_ohlcv(),
        indicators=_unavailable_indicators(),
        quote=_available_quote(),
        news=_available_news(),
    )
    result = source.build_context_result(Ticker(TICKER), TickerRole.CANDIDATE)

    assert result.action is DataAction.SKIP_CANDIDATE
    assert result.context is None
    assert any(e.source == "indicators" for e in result.audit_events)


# ---------------------------------------------------------------------------
# Unavailable KIS price
# ---------------------------------------------------------------------------


def test_unavailable_price_holding_forces_hold(capsys: pytest.CaptureFixture[str]) -> None:
    source = _build_source(
        ohlcv=_available_ohlcv(),
        indicators=_available_indicators(),
        quote=_unavailable_quote(),
        news=_available_news(),
    )
    result = source.build_context_result(Ticker(TICKER), TickerRole.HOLDING)

    assert result.action is DataAction.FORCE_HOLD
    assert result.context is None
    event = next(e for e in result.audit_events if e.source == "kis_quote")
    assert event.action == "FORCE_HOLD"
    assert "DATA WARNING" in capsys.readouterr().out


def test_unavailable_price_candidate_is_skipped() -> None:
    source = _build_source(
        ohlcv=_available_ohlcv(),
        indicators=_available_indicators(),
        quote=_unavailable_quote(),
        news=_available_news(),
    )
    result = source.build_context_result(Ticker(TICKER), TickerRole.CANDIDATE)

    assert result.action is DataAction.SKIP_CANDIDATE
    assert result.context is None


# ---------------------------------------------------------------------------
# News failure: fail-soft, context still built with empty news
# ---------------------------------------------------------------------------


def test_news_failure_continues_with_empty_news() -> None:
    source = _build_source(
        ohlcv=_available_ohlcv(),
        indicators=_available_indicators(),
        quote=_available_quote(),
        news=_empty_news(),
    )
    context = source.build_context(Ticker(TICKER))

    assert isinstance(context, DataContext)
    assert tuple(context.news) == ()
    assert context.current_price == Money(70000.0, "KRW")


# ---------------------------------------------------------------------------
# Screener composition (DATA-05)
# ---------------------------------------------------------------------------


class _FakeMarketOhlcvAdapter:
    """Adapter exposing a whole-market frame for screener input."""

    def __init__(self, rows: Tuple[Mapping[str, Any], ...]) -> None:
        self._rows = rows
        self.calls: List[str] = []

    def fetch_market_rows(self, trading_date: str) -> Tuple[Mapping[str, Any], ...]:
        self.calls.append(trading_date)
        return self._rows


def test_screen_daily_candidates_composes_screener() -> None:
    from trading_bot.config import Settings, KisCredentialGroup

    rows = (
        {
            "ticker": "005930",
            "market": "KOSPI",
            "state": "NORMAL",
            "trading_value": 5_000_000_000.0,
            "technicals": {
                "atr_14": 20.0,
                "historical_volatility": 0.03,
                "volume_ratio": 1.5,
                "rsi_14": 60.0,
                "sma_short": 1010.0,
                "sma_long": 1000.0,
            },
            "health": SourceHealth(
                source="pykrx", status=SourceStatus.AVAILABLE, reason="ok"
            ),
        },
        {
            "ticker": "000660",
            "market": "KOSPI",
            "state": "HALTED",
            "trading_value": 5_000_000_000.0,
            "technicals": {},
            "health": SourceHealth(
                source="pykrx", status=SourceStatus.AVAILABLE, reason="ok"
            ),
        },
    )

    kis = KisCredentialGroup(
        domain="https://mock.kis.example.test",
        app_key="k",
        app_secret="s",
        tr_id_profile="mock",
        label="mock",
    )
    settings = Settings(
        _env_file=None,
        kis_mock=kis,
        kis_real=kis,
        anthropic_api_key="a",
        screener_min_trading_value=1_000_000_000.0,
        screener_markets=("KOSPI", "KOSDAQ"),
    )

    source = MarketDataSource(
        ohlcv_adapter=_FakeMarketOhlcvAdapter(rows),
        indicator_fn=_indicator_fn(_available_indicators()),
        quote_adapter=_FakeQuoteAdapter(_available_quote()),
        news_adapter=_FakeNewsAdapter(_available_news()),
        config=_config(),
        settings=settings,
    )

    result = source.screen_daily_candidates(EXPECTED_DATE)

    tickers = [c.ticker for c in result.candidates]
    assert "005930" in tickers
    assert "000660" not in tickers  # HALTED hard-excluded before ranking.
    assert any(e.action == "SKIP_CANDIDATE" for e in result.audit_events)
