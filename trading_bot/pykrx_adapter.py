"""pykrx OHLCV adapter that isolates the vendor and normalizes source health.

This is the only module that imports :mod:`pykrx`. It converts pykrx exceptions,
empty frames, stale dates, invalid schema, and bad numeric values into typed
:class:`~trading_bot.data_models.OhlcvResult` values (D-15) and never raises a
vendor exception into callers (threat T-03-02-D). The concrete ``pykrx.stock``
module is injectable so tests run fully offline with fake stock modules/frames.

Validation performed before a frame is marked AVAILABLE (threat T-03-02-T):
required OHLCV columns present, a monotonic-increasing date index, a minimum row
count, finite positive prices, nonnegative volume, and a latest trading date at
or after the expected/accepted trading date. Holiday/weekend natural closures
are honored via ``accepted_latest_date`` so a legitimate closure is AVAILABLE,
not STALE.
"""

from __future__ import annotations

import signal
import threading
from contextlib import contextmanager
from typing import Any, Callable, Mapping, Optional, Tuple

import pandas as pd

from trading_bot.data_models import (
    OhlcvResult,
    SourceHealth,
    SourceStatus,
)

_SOURCE = "pykrx"
_REQUIRED_COLUMNS = ("시가", "고가", "저가", "종가", "거래량")
_PRICE_COLUMNS = ("시가", "고가", "저가", "종가")
_VOLUME_COLUMN = "거래량"
_DEFAULT_MIN_ROWS = 20
_DEFAULT_REQUEST_TIMEOUT_SECONDS = 10.0


class _PykrxRequestTimeout(TimeoutError):
    """Raised when a pykrx vendor call exceeds the configured timeout."""


@contextmanager
def _request_timeout(seconds: Optional[float]):
    """Bound pykrx calls on Unix main-thread runs; no-op where signals are unsafe."""

    if (
        seconds is None
        or seconds <= 0
        or threading.current_thread() is not threading.main_thread()
        or not hasattr(signal, "SIGALRM")
    ):
        yield
        return

    def _raise_timeout(_signum, _frame) -> None:
        raise _PykrxRequestTimeout(
            f"pykrx request timed out after {seconds:.1f}s"
        )

    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    signal.signal(signal.SIGALRM, _raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, *previous_timer)
        signal.signal(signal.SIGALRM, previous_handler)


def _unavailable(reason: str, *, expected_date: Optional[str] = None,
                 observed_date: Optional[str] = None) -> OhlcvResult:
    return OhlcvResult(
        frame=None,
        health=SourceHealth(
            source=_SOURCE,
            status=SourceStatus.UNAVAILABLE,
            reason=reason,
            observed_date=observed_date,
            expected_date=expected_date,
        ),
    )


def _stale(observed_date: str, expected_date: str) -> OhlcvResult:
    return OhlcvResult(
        frame=None,
        health=SourceHealth(
            source=_SOURCE,
            status=SourceStatus.STALE,
            reason="latest data date is before the expected trading date",
            observed_date=observed_date,
            expected_date=expected_date,
        ),
    )


def _observed_date(frame: pd.DataFrame) -> Optional[str]:
    try:
        latest = frame.index[-1]
        return pd.Timestamp(latest).strftime("%Y%m%d")
    except (IndexError, ValueError, TypeError):
        return None


def _normalize_frame(
    frame: Any,
    *,
    expected_date: str,
    min_rows: int,
    accepted_latest_date: Optional[str],
    check_freshness: bool,
    check_index_is_date: bool = True,
) -> OhlcvResult:
    """Validate a raw pykrx frame into a typed OHLCV result (never raises)."""

    if frame is None or not isinstance(frame, pd.DataFrame):
        return _unavailable("no OHLCV frame returned", expected_date=expected_date)

    if frame.empty:
        return _unavailable("empty OHLCV frame", expected_date=expected_date)

    missing = [col for col in _REQUIRED_COLUMNS if col not in frame.columns]
    if missing:
        return _unavailable(
            f"missing required OHLCV column(s): {missing}",
            expected_date=expected_date,
        )

    if len(frame) < min_rows:
        return _unavailable(
            f"insufficient rows: {len(frame)} < required {min_rows}",
            expected_date=expected_date,
            observed_date=_observed_date(frame) if check_index_is_date else None,
        )

    observed_date = None
    if check_index_is_date:
        try:
            index = pd.DatetimeIndex(frame.index)
        except (ValueError, TypeError):
            return _unavailable(
                "OHLCV index is not a valid date index",
                expected_date=expected_date,
            )
        if not index.is_monotonic_increasing:
            return _unavailable(
                "OHLCV date index is not monotonic increasing",
                expected_date=expected_date,
                observed_date=_observed_date(frame),
            )
        observed_date = _observed_date(frame)

    # Finite positive prices and nonnegative volume across the frame.
    if check_index_is_date:
        for col in _PRICE_COLUMNS:
            series = pd.to_numeric(frame[col], errors="coerce")
            if not series.notna().all() or not (series > 0).all():
                return _unavailable(
                    f"column {col!r} has non-finite or non-positive prices",
                    expected_date=expected_date,
                    observed_date=observed_date,
                )
        volume = pd.to_numeric(frame[_VOLUME_COLUMN], errors="coerce")
        if not volume.notna().all() or (volume < 0).any():
            return _unavailable(
                "volume column has non-finite or negative values",
                expected_date=expected_date,
                observed_date=observed_date,
            )
    else:
        try:
            for col in _PRICE_COLUMNS:
                frame[col] = pd.to_numeric(frame[col], errors="coerce")
            frame[_VOLUME_COLUMN] = pd.to_numeric(frame[_VOLUME_COLUMN], errors="coerce")
            
            valid_mask = True
            for col in _PRICE_COLUMNS:
                valid_mask = valid_mask & (frame[col] > 0)
            valid_mask = valid_mask & (frame[_VOLUME_COLUMN] >= 0)
            
            frame = frame[valid_mask]
        except Exception as exc:
            return _unavailable(
                f"failed to filter whole-market frame: {exc}",
                expected_date=expected_date,
            )
        if frame.empty:
            return _unavailable(
                "empty OHLCV frame after validation",
                expected_date=expected_date,
            )

    # Freshness: the latest observed date must meet the expected trading date,
    # honoring an accepted natural-closure fallback date when supplied.
    if check_freshness and observed_date is not None:
        acceptable = accepted_latest_date or expected_date
        if observed_date < acceptable:
            return _stale(observed_date, expected_date)

    return OhlcvResult(
        frame=frame,
        health=SourceHealth(
            source=_SOURCE,
            status=SourceStatus.AVAILABLE,
            reason="ok",
            observed_date=observed_date,
            expected_date=expected_date,
        ),
    )


class PykrxOhlcvAdapter:
    """Synchronous pykrx adapter returning typed, health-checked OHLCV results.

    Args:
        stock_module: The ``pykrx.stock`` module (or any object exposing
            ``get_market_ohlcv``). Injectable so tests run offline; defaults to
            the real ``pykrx.stock`` import when omitted.
        adjusted: Whether to request adjusted prices (수정주가). Sourced from
            ``Settings.ohlcv_adjusted`` by the caller; never hardcoded policy.
    """

    def __init__(
        self,
        stock_module: Any = None,
        *,
        adjusted: bool = True,
        request_timeout_seconds: Optional[float] = _DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        if stock_module is None:
            from pykrx import stock as stock_module  # isolated vendor import.
        self._stock = stock_module
        self._adjusted = adjusted
        self._request_timeout_seconds = request_timeout_seconds

    def fetch_daily_ohlcv(
        self,
        ticker: str,
        expected_date: str,
        *,
        lookback_days: int = 90,
        min_rows: int = _DEFAULT_MIN_ROWS,
        accepted_latest_date: Optional[str] = None,
    ) -> OhlcvResult:
        """Fetch per-ticker daily OHLCV and normalize it into an ``OhlcvResult``.

        ``expected_date`` is an explicit Asia/Seoul trading date (``YYYYMMDD``)
        passed to pykrx to avoid lookahead. ``accepted_latest_date`` names the
        last valid KRX trading day when ``expected_date`` is a natural closure.
        """

        from_date = self._lookback_start(expected_date, lookback_days)
        try:
            with _request_timeout(self._request_timeout_seconds):
                frame = self._stock.get_market_ohlcv(
                    from_date,
                    expected_date,
                    ticker,
                    adjusted=self._adjusted,
                )
        except _PykrxRequestTimeout as exc:
            return _unavailable(str(exc), expected_date=expected_date)
        except Exception as exc:  # noqa: BLE001 - normalize all vendor failures.
            return _unavailable(
                f"pykrx fetch failed: {type(exc).__name__}",
                expected_date=expected_date,
            )

        return _normalize_frame(
            frame,
            expected_date=expected_date,
            min_rows=min_rows,
            accepted_latest_date=accepted_latest_date,
            check_freshness=True,
        )

    def fetch_market_ohlcv(
        self,
        trading_date: str,
        *,
        market: str,
        min_rows: int = 1,
    ) -> OhlcvResult:
        """Fetch whole-market OHLCV for a trading date (screener input, D-05).

        Whole-market frames are indexed by ticker rather than date, so freshness
        is asserted by the caller-supplied ``trading_date`` argument rather than
        an index-date check.
        """

        try:
            with _request_timeout(self._request_timeout_seconds):
                frame = self._stock.get_market_ohlcv(
                    trading_date,
                    market=market,
                )
        except _PykrxRequestTimeout as exc:
            return _unavailable(str(exc), expected_date=trading_date)
        except Exception as exc:  # noqa: BLE001 - normalize all vendor failures.
            return _unavailable(
                f"pykrx market fetch failed: {type(exc).__name__}",
                expected_date=trading_date,
            )

        return _normalize_frame(
            frame,
            expected_date=trading_date,
            min_rows=min_rows,
            accepted_latest_date=None,
            check_freshness=False,
            check_index_is_date=False,
        )

    def fetch_market_rows(
        self,
        trading_date: str,
        *,
        progress: Optional[Callable[[str], None]] = None,
    ) -> Tuple[Mapping[str, Any], ...]:
        """Fetch whole-market data and compute technical indicators for liquid tickers.

        This delegates to `fetch_market_ohlcv` for allowed markets, filters out
        low-liquidity tickers to avoid fetching history for thousands of names,
        and then fetches lookback history and calculates technical indicators for
        the remaining candidates.
        """
        from trading_bot.config import Settings
        from trading_bot.indicators import calculate_technicals
        from trading_bot.data_models import IndicatorConfig

        settings = Settings()
        markets = settings.screener_markets
        min_trading_value = settings.screener_min_trading_value

        rows = []
        if progress is not None:
            progress(
                f"screening {trading_date} across {', '.join(markets)} "
                f"(min trading value {min_trading_value:,.0f} KRW)"
            )
        for market in markets:
            if progress is not None:
                progress(f"{market}: fetching whole-market OHLCV")
            ohlcv_res = self.fetch_market_ohlcv(trading_date, market=market)
            if (
                ohlcv_res.health.status is not SourceStatus.AVAILABLE
                or ohlcv_res.frame is None
            ):
                if progress is not None:
                    progress(
                        f"{market}: whole-market OHLCV unavailable "
                        f"({ohlcv_res.health.status.value})"
                    )
                continue

            frame = ohlcv_res.frame
            if progress is not None:
                progress(f"{market}: fetched {len(frame)} market rows")
            # Tickers are in the index. Columns include "거래대금".
            # Note: pykrx get_market_ohlcv returns "거래대금" in KRW.
            if "거래대금" not in frame.columns:
                if progress is not None:
                    progress(f"{market}: missing 거래대금 column; skipping market")
                continue

            # Filter frame by trading value
            liquid_frame = frame[frame["거래대금"] >= min_trading_value]
            tickers = liquid_frame.index.tolist()
            if progress is not None:
                progress(f"{market}: {len(tickers)} tickers passed liquidity floor")

            for index, ticker in enumerate(tickers, start=1):
                ticker_str = str(ticker)
                if progress is not None:
                    progress(
                        f"{market}: [{index}/{len(tickers)}] "
                        f"fetching history for {ticker_str}"
                    )

                # Fetch historical daily ohlcv (90 days lookup) for indicators
                history_res = self.fetch_daily_ohlcv(
                    ticker_str,
                    trading_date,
                    lookback_days=90,
                    min_rows=20,
                )

                if (
                    history_res.health.status is not SourceStatus.AVAILABLE
                    or history_res.frame is None
                ):
                    if progress is not None:
                        progress(
                            f"{market}: [{index}/{len(tickers)}] skipped {ticker_str} "
                            f"({history_res.health.status.value})"
                        )
                    continue

                # Compute technicals
                tech_res = calculate_technicals(history_res.frame, IndicatorConfig())
                if tech_res.health.status is not SourceStatus.AVAILABLE:
                    if progress is not None:
                        progress(
                            f"{market}: [{index}/{len(tickers)}] skipped {ticker_str} "
                            f"(indicators {tech_res.health.status.value})"
                        )
                    continue

                rows.append({
                    "ticker": ticker_str,
                    "market": market,
                    "state": "NORMAL",  # Default to normal
                    "trading_value": float(liquid_frame.loc[ticker, "거래대금"]),
                    "technicals": dict(tech_res.technicals),
                    "health": history_res.health,
                })
                if progress is not None:
                    progress(f"{market}: [{index}/{len(tickers)}] accepted {ticker_str}")

        if progress is not None:
            progress(f"built {len(rows)} screenable rows")
        return tuple(rows)

    @staticmethod
    def _lookback_start(expected_date: str, lookback_days: int) -> str:
        start = pd.Timestamp(expected_date) - pd.Timedelta(int(lookback_days), unit="D")
        return start.strftime("%Y%m%d")
