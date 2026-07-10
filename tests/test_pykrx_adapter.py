"""Offline tests for the pykrx OHLCV adapter and source-health normalization.

Every test injects fake pykrx stock-module callables and pandas frames; no test
touches the live pykrx/KRX network. The adapter must convert empty, stale,
schema-invalid, bad-numeric, and vendor-exception inputs into typed
:class:`OhlcvResult` values with :class:`SourceHealth`, and must never raise a
vendor exception into its caller.
"""

import dataclasses
import importlib
import sys
import time

import pandas as pd
import pytest

from trading_bot.data_models import (
    DataAction,
    DataSourceAuditEvent,
    OhlcvResult,
    SourceHealth,
    SourceStatus,
    TickerRole,
    emit_data_warning,
    resolve_data_action,
)
from trading_bot.pykrx_adapter import PykrxOhlcvAdapter

TRADING_DATE = "20260630"  # a KRX weekday used as the asserted trading date.


def _frame(rows: int = 60, *, last_date: str = TRADING_DATE) -> pd.DataFrame:
    """Build a valid pykrx-style OHLCV frame with Korean column labels."""

    index = pd.date_range(end=pd.Timestamp(last_date), periods=rows, freq="D")
    base = list(range(100, 100 + rows))
    return pd.DataFrame(
        {
            "시가": [float(v) for v in base],
            "고가": [float(v) + 2.0 for v in base],
            "저가": [float(v) - 2.0 for v in base],
            "종가": [float(v) + 1.0 for v in base],
            "거래량": [1000 + v for v in base],
        },
        index=index,
    )


def _adapter(fetch) -> PykrxOhlcvAdapter:
    """Build an adapter with an injected fake stock-module fetch callable."""

    class _FakeStock:
        @staticmethod
        def get_market_ohlcv(*args, **kwargs):
            return fetch(*args, **kwargs)

    return PykrxOhlcvAdapter(stock_module=_FakeStock(), adjusted=True)


# --- Typed model shape ------------------------------------------------------


def test_source_models_are_frozen_dataclasses_and_string_enums() -> None:
    health = SourceHealth(
        source="pykrx",
        status=SourceStatus.AVAILABLE,
        reason="ok",
        observed_date=TRADING_DATE,
        expected_date=TRADING_DATE,
    )

    assert dataclasses.is_dataclass(health)
    assert isinstance(SourceStatus.AVAILABLE, str)
    assert isinstance(DataAction.SKIP_CANDIDATE, str)
    assert isinstance(TickerRole.HOLDING, str)
    assert SourceStatus.STALE.value == "STALE"
    with pytest.raises(dataclasses.FrozenInstanceError):
        health.reason = "mutated"  # type: ignore[misc]


# --- Happy path -------------------------------------------------------------


def test_valid_frame_is_available_with_matching_latest_date() -> None:
    adapter = _adapter(lambda *a, **k: _frame())

    result = adapter.fetch_daily_ohlcv("005930", TRADING_DATE, lookback_days=90)

    assert isinstance(result, OhlcvResult)
    assert result.health.status is SourceStatus.AVAILABLE
    assert result.frame is not None
    assert len(result.frame) == 60
    assert result.health.observed_date == TRADING_DATE


def test_adjusted_flag_is_propagated_to_pykrx() -> None:
    seen: dict = {}

    def fetch(*args, **kwargs):
        seen["adjusted"] = kwargs.get("adjusted")
        return _frame()

    class _FakeStock:
        @staticmethod
        def get_market_ohlcv(*args, **kwargs):
            return fetch(*args, **kwargs)

    adapter = PykrxOhlcvAdapter(stock_module=_FakeStock(), adjusted=False)
    adapter.fetch_daily_ohlcv("005930", TRADING_DATE, lookback_days=90)

    assert seen["adjusted"] is False


def test_natural_closure_fallback_date_is_available_not_stale() -> None:
    # Latest row is the accepted fallback trading day (a Friday) while the
    # asserted date is a weekend/holiday. This is a natural closure, not staleness.
    fallback = "20260626"
    adapter = _adapter(lambda *a, **k: _frame(last_date=fallback))

    result = adapter.fetch_daily_ohlcv(
        "005930",
        expected_date="20260628",  # a Sunday closure
        lookback_days=90,
        accepted_latest_date=fallback,
    )

    assert result.health.status is SourceStatus.AVAILABLE


# --- Fail-safe normalization ------------------------------------------------


def test_empty_frame_is_unavailable() -> None:
    adapter = _adapter(lambda *a, **k: pd.DataFrame())

    result = adapter.fetch_daily_ohlcv("005930", TRADING_DATE, lookback_days=90)

    assert result.frame is None
    assert result.health.status is SourceStatus.UNAVAILABLE
    assert "empty" in result.health.reason.lower()


def test_stale_latest_date_is_stale() -> None:
    stale = _frame(last_date="20260601")  # well before the asserted date.
    adapter = _adapter(lambda *a, **k: stale)

    result = adapter.fetch_daily_ohlcv("005930", TRADING_DATE, lookback_days=90)

    assert result.health.status is SourceStatus.STALE


def test_missing_required_column_is_unavailable() -> None:
    bad = _frame().drop(columns=["종가"])
    adapter = _adapter(lambda *a, **k: bad)

    result = adapter.fetch_daily_ohlcv("005930", TRADING_DATE, lookback_days=90)

    assert result.frame is None
    assert result.health.status is SourceStatus.UNAVAILABLE
    assert "column" in result.health.reason.lower()


def test_non_positive_price_is_unavailable() -> None:
    bad = _frame()
    bad.iloc[-1, bad.columns.get_loc("종가")] = 0.0
    adapter = _adapter(lambda *a, **k: bad)

    result = adapter.fetch_daily_ohlcv("005930", TRADING_DATE, lookback_days=90)

    assert result.frame is None
    assert result.health.status is SourceStatus.UNAVAILABLE


def test_negative_volume_is_unavailable() -> None:
    bad = _frame()
    bad.iloc[-1, bad.columns.get_loc("거래량")] = -5
    adapter = _adapter(lambda *a, **k: bad)

    result = adapter.fetch_daily_ohlcv("005930", TRADING_DATE, lookback_days=90)

    assert result.health.status is SourceStatus.UNAVAILABLE


def test_insufficient_rows_is_unavailable() -> None:
    tiny = _frame(rows=3)
    adapter = _adapter(lambda *a, **k: tiny)

    result = adapter.fetch_daily_ohlcv(
        "005930", TRADING_DATE, lookback_days=90, min_rows=20
    )

    assert result.frame is None
    assert result.health.status is SourceStatus.UNAVAILABLE


def test_non_monotonic_index_is_unavailable() -> None:
    scrambled = _frame()
    scrambled = scrambled.iloc[::-1]  # descending dates: not monotonic increasing.
    scrambled = pd.concat([scrambled.iloc[:1], scrambled])  # force disorder.
    adapter = _adapter(lambda *a, **k: scrambled)

    result = adapter.fetch_daily_ohlcv("005930", TRADING_DATE, lookback_days=90)

    assert result.health.status is SourceStatus.UNAVAILABLE


def test_vendor_exception_is_normalized_not_raised() -> None:
    def boom(*args, **kwargs):
        raise RuntimeError("pykrx scrape failed")

    adapter = _adapter(boom)

    result = adapter.fetch_daily_ohlcv("005930", TRADING_DATE, lookback_days=90)

    assert result.frame is None
    assert result.health.status is SourceStatus.UNAVAILABLE
    # The raw vendor message must not be trusted as a tradeable frame, but the
    # reason should describe the failure category without leaking secrets.
    assert result.health.reason


def test_vendor_call_timeout_is_unavailable_not_hanging() -> None:
    def slow_fetch(*args, **kwargs):
        time.sleep(1.0)
        return _frame()

    class _FakeStock:
        @staticmethod
        def get_market_ohlcv(*args, **kwargs):
            return slow_fetch(*args, **kwargs)

    adapter = PykrxOhlcvAdapter(
        stock_module=_FakeStock(),
        adjusted=True,
        request_timeout_seconds=0.05,
    )

    started = time.monotonic()
    result = adapter.fetch_daily_ohlcv("005930", TRADING_DATE, lookback_days=90)
    elapsed = time.monotonic() - started

    assert elapsed < 0.5
    assert result.frame is None
    assert result.health.status is SourceStatus.UNAVAILABLE
    assert "timed out" in result.health.reason


def test_fetch_market_ohlcv_normalizes_whole_market_frame() -> None:
    adapter = _adapter(lambda *a, **k: _frame(rows=5))

    result = adapter.fetch_market_ohlcv(TRADING_DATE, market="KOSPI")

    assert isinstance(result, OhlcvResult)
    assert result.health.status is SourceStatus.AVAILABLE
    assert result.frame is not None


def test_fetch_market_ohlcv_empty_is_unavailable() -> None:
    adapter = _adapter(lambda *a, **k: pd.DataFrame())

    result = adapter.fetch_market_ohlcv(TRADING_DATE, market="KOSPI")

    assert result.health.status is SourceStatus.UNAVAILABLE


# --- Hybrid policy (D-01/D-03) ---------------------------------------------


@pytest.mark.parametrize("status", [SourceStatus.UNAVAILABLE, SourceStatus.STALE])
def test_bad_data_for_candidate_skips(status: SourceStatus) -> None:
    health = SourceHealth(
        source="pykrx",
        status=status,
        reason="bad frame",
        observed_date="20260601",
        expected_date=TRADING_DATE,
    )

    action = resolve_data_action(health, TickerRole.CANDIDATE)

    assert action is DataAction.SKIP_CANDIDATE


@pytest.mark.parametrize("status", [SourceStatus.UNAVAILABLE, SourceStatus.STALE])
def test_bad_data_for_holding_forces_hold(status: SourceStatus) -> None:
    health = SourceHealth(
        source="pykrx",
        status=status,
        reason="bad frame",
        observed_date="20260601",
        expected_date=TRADING_DATE,
    )

    action = resolve_data_action(health, TickerRole.HOLDING)

    assert action is DataAction.FORCE_HOLD


def test_available_data_builds_context_for_both_roles() -> None:
    health = SourceHealth(
        source="pykrx",
        status=SourceStatus.AVAILABLE,
        reason="ok",
        observed_date=TRADING_DATE,
        expected_date=TRADING_DATE,
    )

    assert resolve_data_action(health, TickerRole.CANDIDATE) is DataAction.BUILD_CONTEXT
    assert resolve_data_action(health, TickerRole.HOLDING) is DataAction.BUILD_CONTEXT


def test_emit_data_warning_returns_audit_event_and_prints(capsys) -> None:
    health = SourceHealth(
        source="pykrx",
        status=SourceStatus.STALE,
        reason="latest date before expected",
        observed_date="20260601",
        expected_date=TRADING_DATE,
    )

    event = emit_data_warning("005930", health, DataAction.FORCE_HOLD)

    assert isinstance(event, DataSourceAuditEvent)
    assert event.ticker == "005930"
    assert event.source == "pykrx"
    assert event.action == DataAction.FORCE_HOLD.value
    captured = capsys.readouterr()
    assert "005930" in captured.out
    assert "pykrx" in captured.out


# --- Import boundary --------------------------------------------------------


def test_data_models_import_has_no_forbidden_side_effects() -> None:
    before_import = set(sys.modules)
    importlib.import_module("trading_bot.data_models")

    loaded = set(sys.modules) - before_import
    for prefix in ("pykrx", "httpx", "requests", "anthropic", "openai"):
        assert prefix not in loaded
