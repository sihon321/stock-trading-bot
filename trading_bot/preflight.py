"""Typed fail-closed operator preflight shared by status and mutable runs."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import TypeVar

from .audit_models import ReasonCode
from .market_cycle import CalendarState, MarketCycleEvidence, MarketSession

Scalar = str | int | float | bool | None
T = TypeVar("T")


class PreflightState(StrEnum):
    PASS = "PASS"
    BLOCK = "BLOCK"
    UNKNOWN = "UNKNOWN"


class PreflightCode(StrEnum):
    MOCK_TARGET_CONFIRMED = "MOCK_TARGET_CONFIRMED"
    MOCK_TARGET_BLOCKED = "MOCK_TARGET_BLOCKED"
    AUDIT_HEALTHY = "AUDIT_HEALTHY"
    AUDIT_UNHEALTHY = "AUDIT_UNHEALTHY"
    KRX_SESSION_OPEN = "KRX_SESSION_OPEN"
    KRX_SESSION_BLOCKED = "KRX_SESSION_BLOCKED"
    UNRESOLVED_SCAN_CLEAR = "UNRESOLVED_SCAN_CLEAR"
    UNRESOLVED_SCAN_UNKNOWN = "UNRESOLVED_SCAN_UNKNOWN"
    TICKER_FROZEN_UNRESOLVED_ORDER = "TICKER_FROZEN_UNRESOLVED_ORDER"


@dataclass(frozen=True)
class MockTargetEvidence:
    confirmed: bool | None
    target: str | None


@dataclass(frozen=True)
class AuditHealthEvidence:
    healthy: bool | None
    schema_version: int | None
    integrity_ok: bool | None
    writable: bool | None


@dataclass(frozen=True)
class UnresolvedOrderEvidence:
    ticker: str | None
    reason_code: ReasonCode
    order_intent_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "reason_code", ReasonCode(self.reason_code))
        if self.reason_code not in {
            ReasonCode.AMBIGUOUS_SUBMISSION,
            ReasonCode.DUPLICATE_ORDER,
        }:
            raise ValueError("unresolved order reason must be ambiguous or duplicate")


@dataclass(frozen=True)
class UnresolvedOrderScan:
    complete: bool
    entries: tuple[UnresolvedOrderEvidence, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", tuple(self.entries))


@dataclass(frozen=True)
class PreflightCheck:
    code: PreflightCode
    state: PreflightState
    explanation_ko: str
    facts: Mapping[str, Scalar]
    stops_run: bool
    ticker: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", PreflightCode(self.code))
        object.__setattr__(self, "state", PreflightState(self.state))
        normalized: dict[str, Scalar] = {}
        for key, value in self.facts.items():
            if not isinstance(key, str) or not key or len(key) > 64:
                raise ValueError("preflight fact keys must be bounded strings")
            if value is not None and not isinstance(value, (str, int, float, bool)):
                raise TypeError("preflight facts must contain normalized scalar values")
            normalized[key] = value
        object.__setattr__(self, "facts", MappingProxyType(normalized))


@dataclass(frozen=True)
class PreflightResult:
    checks: tuple[PreflightCheck, ...]
    global_executable: bool
    frozen_tickers: Mapping[str, ReasonCode]

    def __post_init__(self) -> None:
        object.__setattr__(self, "checks", tuple(self.checks))
        frozen = {
            ticker: ReasonCode(reason)
            for ticker, reason in self.frozen_tickers.items()
        }
        object.__setattr__(self, "frozen_tickers", MappingProxyType(frozen))


def _read(reader: Callable[[], T]) -> tuple[T | None, bool]:
    try:
        return reader(), True
    except Exception:
        # Provider payloads and raw exception text must never cross this boundary.
        return None, False


def evaluate_preflight(
    mock_target_reader: Callable[[], MockTargetEvidence],
    audit_health_reader: Callable[[], AuditHealthEvidence],
    market_cycle_reader: Callable[[], MarketCycleEvidence],
    unresolved_order_reader: Callable[[], UnresolvedOrderScan],
) -> PreflightResult:
    """Evaluate every D-11 prerequisite without mutating trading evidence."""

    checks: list[PreflightCheck] = []

    mock, available = _read(mock_target_reader)
    if not available or mock is None or mock.confirmed is None:
        checks.append(_unknown(PreflightCode.MOCK_TARGET_BLOCKED, "모의투자 대상 신원을 확인할 수 없습니다.", "mock_target"))
    elif mock.confirmed and mock.target == "mock":
        checks.append(_check(PreflightCode.MOCK_TARGET_CONFIRMED, PreflightState.PASS, "모의투자 대상이 확인되었습니다.", {"target": "mock"}))
    else:
        checks.append(_check(PreflightCode.MOCK_TARGET_BLOCKED, PreflightState.BLOCK, "모의투자 대상이 아니므로 실행을 중단합니다.", {"target": mock.target or "unconfirmed"}, stops_run=True))

    audit, available = _read(audit_health_reader)
    if not available or audit is None or audit.healthy is None:
        checks.append(_unknown(PreflightCode.AUDIT_UNHEALTHY, "감사 저장소 상태를 확인할 수 없습니다.", "audit"))
    elif audit.healthy and audit.integrity_ok is True and audit.writable is True:
        checks.append(_check(
            PreflightCode.AUDIT_HEALTHY,
            PreflightState.PASS,
            "감사 스키마, 무결성, 쓰기 가능 상태가 확인되었습니다.",
            {"schema_version": audit.schema_version, "integrity_ok": True, "writable": True},
        ))
    else:
        checks.append(_check(
            PreflightCode.AUDIT_UNHEALTHY,
            PreflightState.BLOCK,
            "감사 증거를 안전하게 보존할 수 없어 실행을 중단합니다.",
            {"schema_version": audit.schema_version, "integrity_ok": audit.integrity_ok, "writable": audit.writable},
            stops_run=True,
        ))

    market, available = _read(market_cycle_reader)
    if (
        not available
        or market is None
        or market.calendar_state is CalendarState.UNKNOWN
        or market.session is MarketSession.UNKNOWN
    ):
        checks.append(_unknown(PreflightCode.KRX_SESSION_BLOCKED, "KRX 거래일 또는 장 상태를 확인할 수 없습니다.", "krx_session"))
    elif market.executable:
        checks.append(_check(
            PreflightCode.KRX_SESSION_OPEN,
            PreflightState.PASS,
            "KRX 연속매매 시간이 확인되었습니다.",
            {"trading_date": market.trading_date.isoformat(), "session": market.session.value, "policy_version": market.policy_version},
        ))
    else:
        checks.append(_check(
            PreflightCode.KRX_SESSION_BLOCKED,
            PreflightState.BLOCK,
            "현재 KRX 장 상태에서는 실행할 수 없습니다.",
            {"trading_date": market.trading_date.isoformat(), "session": market.session.value, "policy_version": market.policy_version},
            stops_run=True,
        ))

    frozen: dict[str, ReasonCode] = {}
    scan, available = _read(unresolved_order_reader)
    if not available or scan is None or not scan.complete:
        checks.append(_unknown(PreflightCode.UNRESOLVED_SCAN_UNKNOWN, "미해결 주문의 로컬 감사 증거를 완전하게 확인할 수 없습니다.", "unresolved_orders"))
    elif any(not entry.ticker for entry in scan.entries):
        checks.append(_unknown(PreflightCode.UNRESOLVED_SCAN_UNKNOWN, "미해결 주문 증거의 티커 귀속을 확인할 수 없습니다.", "unresolved_orders"))
    else:
        checks.append(_check(
            PreflightCode.UNRESOLVED_SCAN_CLEAR,
            PreflightState.PASS,
            "미해결 주문 증거 스캔이 완료되었습니다.",
            {"unresolved_count": len(scan.entries), "scope": "local_audit_only"},
        ))
        for entry in scan.entries:
            assert entry.ticker is not None
            frozen[entry.ticker] = entry.reason_code
            checks.append(_check(
                PreflightCode.TICKER_FROZEN_UNRESOLVED_ORDER,
                PreflightState.BLOCK,
                "로컬 감사 증거에 미해결 주문이 있어 이 티커만 동결합니다. KIS 원장은 아직 확인하지 않았습니다.",
                {"reason_code": entry.reason_code.value, "order_intent_id": entry.order_intent_id, "scope": "local_audit_only"},
                stops_run=False,
                ticker=entry.ticker,
            ))

    global_executable = not any(
        check.stops_run and check.state is not PreflightState.PASS
        for check in checks
    )
    return PreflightResult(tuple(checks), global_executable, frozen)


def _unknown(code: PreflightCode, explanation: str, source: str) -> PreflightCheck:
    return _check(
        code,
        PreflightState.UNKNOWN,
        explanation,
        {"source": source, "available": False},
        stops_run=True,
    )


def _check(
    code: PreflightCode,
    state: PreflightState,
    explanation: str,
    facts: Mapping[str, Scalar],
    *,
    stops_run: bool = False,
    ticker: str | None = None,
) -> PreflightCheck:
    return PreflightCheck(code, state, explanation, facts, stops_run, ticker)


def render_preflight(result: PreflightResult) -> str:
    """Render stable codes, Korean explanations, and allowlisted scalar facts."""

    lines = ["안전 사전 점검", f"실행 가능: {'예' if result.global_executable else '아니오'}"]
    for check in result.checks:
        scope = f" ticker={check.ticker}" if check.ticker else ""
        facts = " ".join(f"{key}={check.facts[key]}" for key in sorted(check.facts))
        lines.append(f"[{check.state.value}] {check.code.value}{scope} - {check.explanation_ko} ({facts})")
    return "\n".join(lines)


__all__ = [
    "AuditHealthEvidence",
    "MockTargetEvidence",
    "PreflightCheck",
    "PreflightCode",
    "PreflightResult",
    "PreflightState",
    "UnresolvedOrderEvidence",
    "UnresolvedOrderScan",
    "evaluate_preflight",
    "render_preflight",
]
