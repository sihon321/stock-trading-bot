"""Pure-transform tests for the daily volatility-breakout screener (DATA-05).

These mirror ``tests/test_risk.py`` and ``tests/test_execution.py``: deterministic,
network-free, and fail-safe. The screener must hard-exclude unhealthy, illiquid,
suspended/halted, stale, and bad-data tickers BEFORE ranking, rank survivors by
volatility-breakout readiness (ATR/historical volatility and a liquidity floor
first, then volume expansion and momentum), cap the result at
``screener_max_candidates``, restrict to configured markets, propagate the
asserted trading date, and emit ``SKIP_CANDIDATE`` audit events for exclusions
(D-03, D-07, D-08, D-09, D-10, D-11, D-12).

No pykrx / HTTP calls occur here — the screener is a pure transform over
already-fetched, already-validated inputs (D-13).
"""

import dataclasses
import importlib
import sys

import pytest

from trading_bot.config import Settings
from trading_bot.data_models import (
    DataSourceAuditEvent,
    SourceHealth,
    SourceStatus,
)
from trading_bot.screener import (
    ScreenerCandidate,
    ScreenerConfig,
    ScreenerResult,
    build_screener_config,
    screen_candidates,
    score_volatility_breakout,
)

_TRADING_DATE = "20260630"


def _settings(**overrides: object) -> Settings:
    base = dict(
        kis_mock=dict(
            domain="https://mock.example",
            app_key="mock-app-key",
            app_secret="mock-app-secret",
            tr_id_profile="mock-profile",
            label="MOCK",
        ),
        kis_real=dict(
            domain="https://real.example",
            app_key="real-app-key",
            app_secret="real-app-secret",
            tr_id_profile="real-profile",
            label="REAL",
        ),
        anthropic_api_key="anthropic-key",
    )
    base.update(overrides)
    return Settings(**base)


def _config(**overrides: object) -> ScreenerConfig:
    defaults = dict(
        max_candidates=20,
        markets=("KOSPI", "KOSDAQ"),
        min_trading_value=1_000_000_000.0,
        min_volume_ratio=1.0,
        excluded_states=("HALTED", "DELISTING", "ADMIN"),
    )
    defaults.update(overrides)
    return ScreenerConfig(**defaults)


def _healthy(ticker: str) -> SourceHealth:
    return SourceHealth(
        source="pykrx",
        status=SourceStatus.AVAILABLE,
        reason="ok",
        observed_date=_TRADING_DATE,
        expected_date=_TRADING_DATE,
    )


def _row(
    ticker: str,
    *,
    market: str = "KOSPI",
    state: str = "NORMAL",
    trading_value: float = 5_000_000_000.0,
    health: SourceHealth = None,
    atr_14: float = 5.0,
    historical_volatility: float = 0.03,
    volume_ratio: float = 1.5,
    rsi_14: float = 55.0,
    sma_short: float = 105.0,
    sma_long: float = 100.0,
) -> dict:
    """Build one screener input row as a plain mapping."""
    technicals = {
        "atr_14": atr_14,
        "historical_volatility": historical_volatility,
        "volume_ratio": volume_ratio,
        "rsi_14": rsi_14,
        "sma_short": sma_short,
        "sma_long": sma_long,
    }
    return dict(
        ticker=ticker,
        market=market,
        state=state,
        trading_value=trading_value,
        technicals=technicals,
        health=health if health is not None else _healthy(ticker),
    )


# --- Config -----------------------------------------------------------------


def test_screener_dataclasses_are_frozen_and_typed() -> None:
    config = _config()
    candidate = ScreenerCandidate(
        ticker="005930",
        market="KOSPI",
        score=1.0,
        trading_value=5_000_000_000.0,
        technicals={"atr_14": 5.0},
    )
    result = ScreenerResult(
        trading_date=_TRADING_DATE,
        candidates=(candidate,),
        audit_events=(),
    )

    assert dataclasses.is_dataclass(config)
    assert dataclasses.is_dataclass(candidate)
    assert dataclasses.is_dataclass(result)
    with pytest.raises(dataclasses.FrozenInstanceError):
        candidate.score = 2.0  # type: ignore[misc]


def test_build_screener_config_uses_settings_not_hardcoded_policy() -> None:
    settings = _settings(
        screener_max_candidates=7,
        screener_markets=("KOSPI",),
        screener_min_trading_value=2_000_000_000.0,
        screener_min_volume_ratio=1.25,
        screener_excluded_states=("HALTED", "ADMIN"),
    )

    config = build_screener_config(settings)

    assert config.max_candidates == 7
    assert config.markets == ("KOSPI",)
    assert config.min_trading_value == 2_000_000_000.0
    assert config.min_volume_ratio == 1.25
    assert config.excluded_states == ("HALTED", "ADMIN")


# --- Hard exclusions before ranking -----------------------------------------


def test_unhealthy_source_is_excluded_before_ranking() -> None:
    unhealthy = _row(
        "000001",
        health=SourceHealth(
            source="pykrx",
            status=SourceStatus.STALE,
            reason="stale",
            observed_date="20260626",
            expected_date=_TRADING_DATE,
        ),
    )
    healthy = _row("005930")

    result = screen_candidates(_TRADING_DATE, [unhealthy, healthy], _config())

    tickers = [c.ticker for c in result.candidates]
    assert "000001" not in tickers
    assert "005930" in tickers
    assert any(
        e.ticker == "000001" and e.action == "SKIP_CANDIDATE"
        for e in result.audit_events
    )


def test_low_liquidity_below_trading_value_floor_is_excluded() -> None:
    illiquid = _row("000002", trading_value=100_000_000.0)
    liquid = _row("005930", trading_value=9_000_000_000.0)

    result = screen_candidates(_TRADING_DATE, [illiquid, liquid], _config())

    tickers = [c.ticker for c in result.candidates]
    assert "000002" not in tickers
    assert "005930" in tickers
    assert any(e.ticker == "000002" for e in result.audit_events)


def test_low_volume_ratio_is_excluded() -> None:
    quiet = _row("000003", volume_ratio=0.4)
    active = _row("005930", volume_ratio=2.0)

    result = screen_candidates(_TRADING_DATE, [quiet, active], _config())

    tickers = [c.ticker for c in result.candidates]
    assert "000003" not in tickers
    assert "005930" in tickers


@pytest.mark.parametrize("state", ["HALTED", "DELISTING", "ADMIN"])
def test_suspended_halted_excluded_states_are_removed(state: str) -> None:
    flagged = _row("000004", state=state)
    normal = _row("005930", state="NORMAL")

    result = screen_candidates(_TRADING_DATE, [flagged, normal], _config())

    tickers = [c.ticker for c in result.candidates]
    assert "000004" not in tickers
    assert "005930" in tickers
    assert any(e.ticker == "000004" for e in result.audit_events)


def test_bad_or_missing_technicals_are_excluded() -> None:
    bad = _row("000005")
    bad["technicals"] = {"atr_14": float("nan"), "historical_volatility": 0.03,
                         "volume_ratio": 1.5}
    empty = _row("000006")
    empty["technicals"] = {}
    good = _row("005930")

    result = screen_candidates(_TRADING_DATE, [bad, empty, good], _config())

    tickers = [c.ticker for c in result.candidates]
    assert "000005" not in tickers
    assert "000006" not in tickers
    assert "005930" in tickers


# --- Market restriction ------------------------------------------------------


def test_configurable_market_list_restricts_universe() -> None:
    kospi = _row("005930", market="KOSPI")
    kosdaq = _row("035720", market="KOSDAQ")
    konex = _row("099999", market="KONEX")

    config = _config(markets=("KOSPI",))
    result = screen_candidates(_TRADING_DATE, [kospi, kosdaq, konex], config)

    tickers = [c.ticker for c in result.candidates]
    assert tickers == ["005930"]
    assert {e.ticker for e in result.audit_events} == {"035720", "099999"}


# --- Cap ---------------------------------------------------------------------


def test_configurable_max_candidates_caps_results() -> None:
    rows = [
        _row(f"{i:06d}", historical_volatility=0.01 * i, atr_14=float(i))
        for i in range(1, 11)
    ]
    config = _config(max_candidates=3)

    result = screen_candidates(_TRADING_DATE, rows, config)

    assert len(result.candidates) == 3


# --- Ranking -----------------------------------------------------------------


def test_ranking_prioritizes_volatility_and_liquidity_over_momentum() -> None:
    # High volatility + liquidity, modest momentum.
    breakout = _row(
        "AAAAAA",
        atr_14=12.0,
        historical_volatility=0.08,
        trading_value=9_000_000_000.0,
        volume_ratio=2.5,
        rsi_14=52.0,
        sma_short=101.0,
        sma_long=100.0,
    )
    # Strong momentum but low volatility and lower liquidity.
    momentum = _row(
        "BBBBBB",
        atr_14=1.0,
        historical_volatility=0.005,
        trading_value=1_500_000_000.0,
        volume_ratio=1.1,
        rsi_14=85.0,
        sma_short=140.0,
        sma_long=100.0,
    )

    result = screen_candidates(_TRADING_DATE, [momentum, breakout], _config())

    assert [c.ticker for c in result.candidates] == ["AAAAAA", "BBBBBB"]
    assert result.candidates[0].score > result.candidates[1].score


def test_score_volatility_breakout_is_pure_and_monotonic_in_volatility() -> None:
    low = score_volatility_breakout(
        {"atr_14": 2.0, "historical_volatility": 0.01, "volume_ratio": 1.2,
         "rsi_14": 55.0, "sma_short": 101.0, "sma_long": 100.0},
        trading_value=5_000_000_000.0,
        config=_config(),
    )
    high = score_volatility_breakout(
        {"atr_14": 10.0, "historical_volatility": 0.09, "volume_ratio": 1.2,
         "rsi_14": 55.0, "sma_short": 101.0, "sma_long": 100.0},
        trading_value=5_000_000_000.0,
        config=_config(),
    )

    assert high > low


# --- Date propagation --------------------------------------------------------


def test_trading_date_is_propagated_to_result_and_audits() -> None:
    excluded = _row("000009", trading_value=1.0)
    included = _row("005930")

    result = screen_candidates(_TRADING_DATE, [excluded, included], _config())

    assert result.trading_date == _TRADING_DATE
    for event in result.audit_events:
        assert event.expected_date == _TRADING_DATE


def test_audit_events_use_skip_candidate_action_and_are_typed() -> None:
    excluded = _row("000010", state="HALTED")

    result = screen_candidates(_TRADING_DATE, [excluded], _config())

    assert result.candidates == ()
    assert len(result.audit_events) == 1
    event = result.audit_events[0]
    assert isinstance(event, DataSourceAuditEvent)
    assert event.action == "SKIP_CANDIDATE"
    assert event.ticker == "000010"


# --- Import boundary (pure transform, no vendor / network) -------------------


def test_screener_import_has_no_forbidden_side_effects() -> None:
    before_import = set(sys.modules)
    importlib.import_module("trading_bot.screener")

    loaded = set(sys.modules) - before_import
    for prefix in ("pykrx", "httpx", "requests", "anthropic", "openai"):
        assert prefix not in loaded
    forbidden_local = [
        name
        for name in loaded
        if name.startswith("trading_bot.")
        and any(frag in name for frag in ("pykrx", "adapter", "kis", "naver"))
    ]
    assert forbidden_local == []
