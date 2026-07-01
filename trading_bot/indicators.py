"""Pure OHLCV -> compact volatility-breakout technical transform (D-05).

This module is a pure transform in the spirit of :mod:`trading_bot.risk`: it
accepts an explicit validated OHLCV DataFrame plus an explicit
:class:`~trading_bot.data_models.IndicatorConfig` and returns either a flat
``Mapping[str, float]`` of technicals or a typed unavailable source-health
result. It never reads settings, logs, touches the network, or imports pykrx,
KIS, Naver, or adapter code — those boundaries are guarded by an import test.

Indicators are computed with the ``ta`` library so warm-up windows and NaN
handling are consistent. If any produced indicator tail is NaN (warm-up) or any
input is missing/insufficient, the transform fails closed to UNAVAILABLE rather
than emitting zero-valued technicals (threat T-03-02-T).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import SMAIndicator
from ta.volatility import AverageTrueRange

from trading_bot.data_models import (
    IndicatorConfig,
    SourceHealth,
    SourceStatus,
)

_SOURCE = "indicators"
_REQUIRED_COLUMNS = ("고가", "저가", "종가", "거래량")
_HIGH, _LOW, _CLOSE, _VOLUME = _REQUIRED_COLUMNS


@dataclass(frozen=True)
class IndicatorResult:
    """Compact technicals with source health, suitable for ``DataContext``.

    ``technicals`` is a flat ``str -> float`` mapping only when ``health.status``
    is :attr:`SourceStatus.AVAILABLE`; otherwise it is an empty mapping so a
    warm-up/NaN/insufficient result can never be read as zero-valued signals.
    """

    technicals: Mapping[str, float]
    health: SourceHealth


def _unavailable(reason: str) -> IndicatorResult:
    return IndicatorResult(
        technicals={},
        health=SourceHealth(
            source=_SOURCE,
            status=SourceStatus.UNAVAILABLE,
            reason=reason,
        ),
    )


def _min_required_rows(config: IndicatorConfig) -> int:
    return max(
        config.sma_short_window,
        config.sma_long_window,
        config.rsi_window,
        config.atr_window,
        config.historical_volatility_window,
        config.volume_ratio_window,
    )


def calculate_technicals(ohlcv: Any, config: IndicatorConfig) -> IndicatorResult:
    """Compute flat volatility-breakout technicals or a typed unavailable result.

    Returned keys: ``sma_short``, ``sma_long``, ``rsi_14``, ``atr_14``,
    ``historical_volatility``, ``volume_ratio``. Any missing column, insufficient
    history, or NaN indicator tail yields UNAVAILABLE health with empty technicals.
    """

    if ohlcv is None or not isinstance(ohlcv, pd.DataFrame) or ohlcv.empty:
        return _unavailable("empty or non-DataFrame OHLCV input")

    missing = [col for col in _REQUIRED_COLUMNS if col not in ohlcv.columns]
    if missing:
        return _unavailable(f"missing required OHLCV column(s): {missing}")

    min_rows = _min_required_rows(config)
    if len(ohlcv) < min_rows:
        return _unavailable(
            f"insufficient history: {len(ohlcv)} rows < required {min_rows}"
        )

    high = pd.to_numeric(ohlcv[_HIGH], errors="coerce")
    low = pd.to_numeric(ohlcv[_LOW], errors="coerce")
    close = pd.to_numeric(ohlcv[_CLOSE], errors="coerce")
    volume = pd.to_numeric(ohlcv[_VOLUME], errors="coerce")

    if not close.notna().all() or not high.notna().all() or not low.notna().all():
        return _unavailable("NaN or non-numeric price input")
    if not volume.notna().all():
        return _unavailable("NaN or non-numeric volume input")

    sma_short = SMAIndicator(close=close, window=config.sma_short_window)
    sma_long = SMAIndicator(close=close, window=config.sma_long_window)
    rsi = RSIIndicator(close=close, window=config.rsi_window)
    atr = AverageTrueRange(
        high=high, low=low, close=close, window=config.atr_window
    )
    log_returns = (close / close.shift(1)).apply(_safe_log)
    hist_vol = log_returns.rolling(config.historical_volatility_window).std()
    volume_avg = volume.rolling(config.volume_ratio_window).mean()

    technicals = {
        "sma_short": _tail(sma_short.sma_indicator()),
        "sma_long": _tail(sma_long.sma_indicator()),
        "rsi_14": _tail(rsi.rsi()),
        "atr_14": _tail(atr.average_true_range()),
        "historical_volatility": _tail(hist_vol),
        "volume_ratio": _volume_ratio(volume, volume_avg),
    }

    if any(value is None or not math.isfinite(value) for value in technicals.values()):
        return _unavailable("indicator warm-up produced a NaN/non-finite tail value")

    return IndicatorResult(
        technicals={key: float(value) for key, value in technicals.items()},
        health=SourceHealth(
            source=_SOURCE,
            status=SourceStatus.AVAILABLE,
            reason="ok",
        ),
    )


def _tail(series: pd.Series) -> Any:
    try:
        value = series.iloc[-1]
    except (IndexError, ValueError):
        return None
    if pd.isna(value):
        return None
    return float(value)


def _volume_ratio(volume: pd.Series, volume_avg: pd.Series) -> Any:
    latest_avg = _tail(volume_avg)
    latest_volume = _tail(volume)
    if latest_avg is None or latest_volume is None or latest_avg <= 0:
        return None
    return float(latest_volume / latest_avg)


def _safe_log(value: float) -> float:
    if value is None or not math.isfinite(value) or value <= 0:
        return math.nan
    return math.log(value)
