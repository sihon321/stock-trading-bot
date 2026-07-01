"""Pure-transform tests for volatility-breakout technical indicators.

These mirror ``tests/test_risk.py``: deterministic, network-free, and fail-safe.
Valid OHLCV must produce flat finite technicals; insufficient history, missing
columns, and NaN warm-up tails must fail closed to typed unavailable source
health rather than zero-valued technicals.
"""

import importlib
import sys

import numpy as np
import pandas as pd
import pytest

from trading_bot.data_models import IndicatorConfig, SourceStatus
from trading_bot.indicators import IndicatorResult, calculate_technicals

_EXPECTED_KEYS = {
    "sma_short",
    "sma_long",
    "rsi_14",
    "atr_14",
    "historical_volatility",
    "volume_ratio",
}


def _ohlcv(rows: int = 60) -> pd.DataFrame:
    index = pd.date_range(end=pd.Timestamp("20260630"), periods=rows, freq="D")
    # A gently trending series with mild noise so RSI/ATR are well-defined.
    base = np.linspace(100.0, 160.0, rows) + np.sin(np.arange(rows)) * 2.0
    return pd.DataFrame(
        {
            "시가": base,
            "고가": base + 3.0,
            "저가": base - 3.0,
            "종가": base + 1.0,
            "거래량": np.linspace(1000.0, 3000.0, rows),
        },
        index=index,
    )


def _config() -> IndicatorConfig:
    return IndicatorConfig()


def test_valid_ohlcv_produces_flat_finite_technicals() -> None:
    result = calculate_technicals(_ohlcv(), _config())

    assert isinstance(result, IndicatorResult)
    assert result.health.status is SourceStatus.AVAILABLE
    assert set(result.technicals.keys()) == _EXPECTED_KEYS
    for key, value in result.technicals.items():
        assert isinstance(value, float), key
        assert np.isfinite(value), key


def test_technicals_mapping_is_string_to_float_only() -> None:
    result = calculate_technicals(_ohlcv(), _config())

    for key, value in result.technicals.items():
        assert isinstance(key, str)
        assert isinstance(value, float)


def test_volume_ratio_reflects_recent_expansion() -> None:
    frame = _ohlcv()
    # Spike the last volume well above its trailing average.
    frame.iloc[-1, frame.columns.get_loc("거래량")] = 100000.0

    result = calculate_technicals(frame, _config())

    assert result.health.status is SourceStatus.AVAILABLE
    assert result.technicals["volume_ratio"] > 1.0


def test_insufficient_history_is_unavailable() -> None:
    result = calculate_technicals(_ohlcv(rows=5), _config())

    assert result.technicals == {}
    assert result.health.status is SourceStatus.UNAVAILABLE
    assert "insufficient" in result.health.reason.lower()


def test_missing_column_is_unavailable() -> None:
    frame = _ohlcv().drop(columns=["고가"])

    result = calculate_technicals(frame, _config())

    assert result.technicals == {}
    assert result.health.status is SourceStatus.UNAVAILABLE
    assert "column" in result.health.reason.lower()


def test_nan_warmup_tail_fails_closed_as_unavailable() -> None:
    # Force a NaN into the final close so a computed indicator tail is NaN.
    frame = _ohlcv()
    frame.iloc[-1, frame.columns.get_loc("종가")] = np.nan

    result = calculate_technicals(frame, _config())

    assert result.technicals == {}
    assert result.health.status is SourceStatus.UNAVAILABLE


def test_empty_frame_is_unavailable() -> None:
    result = calculate_technicals(pd.DataFrame(), _config())

    assert result.technicals == {}
    assert result.health.status is SourceStatus.UNAVAILABLE


def test_indicators_import_has_no_forbidden_side_effects() -> None:
    before_import = set(sys.modules)
    importlib.import_module("trading_bot.indicators")

    loaded = set(sys.modules) - before_import
    for prefix in ("pykrx", "httpx", "requests", "anthropic", "openai"):
        assert prefix not in loaded
    forbidden_local = [
        name
        for name in loaded
        if name.startswith("trading_bot.")
        and any(frag in name for frag in ("pykrx", "adapter", "kis", "naver", "config"))
    ]
    assert forbidden_local == []
