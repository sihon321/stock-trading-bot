from __future__ import annotations

from datetime import date, datetime

import pytest

from trading_bot.audit_models import ReasonCode
from trading_bot.market_cycle import (
    CalendarState,
    KST,
    MarketCycleEvidence,
    MarketSession,
)
from trading_bot.preflight import (
    AuditHealthEvidence,
    MockTargetEvidence,
    PreflightCode,
    PreflightState,
    UnresolvedOrderEvidence,
    UnresolvedOrderScan,
    evaluate_preflight,
    render_preflight,
)


def _market(*, executable: bool = True, unknown: bool = False) -> MarketCycleEvidence:
    return MarketCycleEvidence(
        observed_at_kst=datetime(2026, 7, 14, 9, 10, tzinfo=KST),
        trading_date=date(2026, 7, 14),
        calendar_state=CalendarState.UNKNOWN if unknown else CalendarState.TRADING_DAY,
        session=MarketSession.UNKNOWN if unknown else MarketSession.CONTINUOUS,
        executable=executable,
        reason="calendar unavailable" if unknown else "continuous trading",
    )


def _evaluate(
    *,
    mock: MockTargetEvidence | Exception = MockTargetEvidence(True, "mock"),
    audit: AuditHealthEvidence | Exception = AuditHealthEvidence(True, 3, True, True),
    market: MarketCycleEvidence | Exception = _market(),
    unresolved: UnresolvedOrderScan | Exception = UnresolvedOrderScan(True, ()),
):
    def reader(value):
        if isinstance(value, Exception):
            raise value
        return value

    return evaluate_preflight(
        lambda: reader(mock),
        lambda: reader(audit),
        lambda: reader(market),
        lambda: reader(unresolved),
    )


def test_all_pass_checks_are_typed_visible_and_executable() -> None:
    result = _evaluate()

    assert result.global_executable is True
    assert result.frozen_tickers == {}
    assert [check.state for check in result.checks] == [
        PreflightState.PASS,
        PreflightState.PASS,
        PreflightState.PASS,
        PreflightState.PASS,
    ]
    rendered = render_preflight(result)
    assert "MOCK_TARGET_CONFIRMED" in rendered
    assert "AUDIT_HEALTHY" in rendered
    assert "KRX_SESSION_OPEN" in rendered
    assert "UNRESOLVED_SCAN_CLEAR" in rendered
    assert "실행 가능: 예" in rendered


@pytest.mark.parametrize(
    ("overrides", "code", "state"),
    [
        ({"mock": MockTargetEvidence(False, "real")}, PreflightCode.MOCK_TARGET_BLOCKED, PreflightState.BLOCK),
        ({"mock": MockTargetEvidence(None, None)}, PreflightCode.MOCK_TARGET_BLOCKED, PreflightState.UNKNOWN),
        ({"audit": AuditHealthEvidence(False, 3, False, False)}, PreflightCode.AUDIT_UNHEALTHY, PreflightState.BLOCK),
        ({"audit": AuditHealthEvidence(None, None, None, None)}, PreflightCode.AUDIT_UNHEALTHY, PreflightState.UNKNOWN),
        ({"market": _market(executable=False)}, PreflightCode.KRX_SESSION_BLOCKED, PreflightState.BLOCK),
        ({"market": _market(executable=False, unknown=True)}, PreflightCode.KRX_SESSION_BLOCKED, PreflightState.UNKNOWN),
        ({"unresolved": UnresolvedOrderScan(False, ())}, PreflightCode.UNRESOLVED_SCAN_UNKNOWN, PreflightState.UNKNOWN),
    ],
)
def test_block_or_unknown_global_check_fails_closed(overrides, code, state) -> None:
    result = _evaluate(**overrides)

    check = next(item for item in result.checks if item.code is code)
    assert check.state is state
    assert check.stops_run is True
    assert result.global_executable is False


@pytest.mark.parametrize("source", ["mock", "audit", "market", "unresolved"])
def test_reader_exception_becomes_sanitized_unknown(source: str) -> None:
    result = _evaluate(**{source: RuntimeError("secret provider body")})

    assert result.global_executable is False
    unknown = next(check for check in result.checks if check.state is PreflightState.UNKNOWN)
    assert unknown.stops_run is True
    assert "secret" not in render_preflight(result)
    assert all("exception" not in key.lower() for key in unknown.facts)


@pytest.mark.parametrize("ticker", [None, ""])
def test_unattributed_unresolved_order_blocks_globally(ticker: str | None) -> None:
    result = _evaluate(
        unresolved=UnresolvedOrderScan(
            True,
            (UnresolvedOrderEvidence(ticker, ReasonCode.AMBIGUOUS_SUBMISSION, "intent-1"),),
        )
    )

    assert result.global_executable is False
    assert result.frozen_tickers == {}
    check = next(item for item in result.checks if item.code is PreflightCode.UNRESOLVED_SCAN_UNKNOWN)
    assert check.state is PreflightState.UNKNOWN


@pytest.mark.parametrize(
    "reason",
    [ReasonCode.AMBIGUOUS_SUBMISSION, ReasonCode.DUPLICATE_ORDER],
)
def test_confirmed_unresolved_order_freezes_only_affected_ticker(reason: ReasonCode) -> None:
    result = _evaluate(
        unresolved=UnresolvedOrderScan(
            True,
            (UnresolvedOrderEvidence("005930", reason, "intent-1"),),
        )
    )

    assert result.global_executable is True
    assert result.frozen_tickers == {"005930": reason}
    assert "000660" not in result.frozen_tickers
    freeze = next(
        item for item in result.checks
        if item.code is PreflightCode.TICKER_FROZEN_UNRESOLVED_ORDER
    )
    assert freeze.ticker == "005930"
    assert freeze.stops_run is False
    assert "로컬 감사 증거" in freeze.explanation_ko


def test_preflight_evidence_is_immutable() -> None:
    result = _evaluate()

    with pytest.raises(TypeError):
        result.frozen_tickers["005930"] = ReasonCode.DUPLICATE_ORDER  # type: ignore[index]
    with pytest.raises(TypeError):
        result.checks[0].facts["target"] = "real"  # type: ignore[index]
