from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from trading_bot.market_cycle import KST, MarketCyclePolicy, MarketSession
from trading_bot.soak_drills import FAULT_REGISTRY
from trading_bot.soak_models import FaultName
from trading_bot.preflight import (
    AuditHealthEvidence,
    MockTargetEvidence,
    PreflightCode,
    PreflightState,
    UnresolvedOrderScan,
    evaluate_preflight,
)


RUNBOOK = Path(__file__).resolve().parents[1] / "docs" / "operator-runbook.md"

FAILURE_TYPES = {
    "STALE_DATA",
    "API_FAILURE",
    "LLM_TIMEOUT",
    "AMBIGUOUS_SUBMISSION",
    "DUPLICATE_ORDER",
    "NOTIFICATION_FAILURE",
    "AUDIT_FAILURE",
}
TRIAGE_COLUMNS = [
    "장애 유형",
    "증상/코드",
    "중단 범위",
    "확인 증거/명령",
    "금지 행동",
    "안전한 다음 조치",
    "해결 기준",
]


def _text() -> str:
    return RUNBOOK.read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    marker = f"## {heading}\n"
    assert text.count(marker) == 1, f"missing or duplicate section: {heading}"
    body = text.split(marker, 1)[1]
    return body.split("\n## ", 1)[0]


def _table(section: str) -> tuple[list[str], list[dict[str, str]]]:
    lines = [line.strip() for line in section.splitlines() if line.strip().startswith("|")]
    assert len(lines) >= 2, "section must contain a Markdown table"

    def cells(line: str) -> list[str]:
        return [cell.strip() for cell in line.strip("|").split("|")]

    header = cells(lines[0])
    separator = cells(lines[1])
    assert len(separator) == len(header)
    assert all(set(cell) <= {"-", ":"} and "-" in cell for cell in separator)
    rows = []
    for line in lines[2:]:
        values = cells(line)
        assert len(values) == len(header), f"wrong column count: {line}"
        rows.append(dict(zip(header, values, strict=True)))
    return header, rows


def test_manual_schedule_contract() -> None:
    header, rows = _table(_section(_text(), "일일 수동 운영 절차"))

    assert header == ["KST", "수동 명령", "목적", "완료 조건"]
    assert [(row["KST"], row["수동 명령"]) for row in rows] == [
        ("08:50", "`bot status`"),
        ("09:05", "`bot screen`"),
        ("09:10 직전", "`bot status`"),
        ("09:10", "`bot run`"),
        ("즉시", "`bot report daily`"),
    ]
    section = _section(_text(), "일일 수동 운영 절차")
    assert "운영자가 직접 실행하는 수동 절차" in section
    assert "예약 실행이나 스케줄링이 아니다" in section
    assert "09:05 화면은 미리보기" in section
    assert "09:10 실행은 후보를 새로 선별" in section


def test_schedule_semantics_match_market_cycle_and_preflight() -> None:
    class ConfirmedTradingDayCalendar:
        def is_trading_day(self, day: date) -> bool:
            return True

        def previous_trading_day(self, day: date) -> date:
            return date.fromordinal(day.toordinal() - 1)

    policy = MarketCyclePolicy(ConfirmedTradingDayCalendar())
    observations = {
        "readiness": datetime(2026, 7, 14, 8, 50, tzinfo=KST),
        "execution": datetime(2026, 7, 14, 9, 10, tzinfo=KST),
    }
    cycles = {name: policy.classify(observed_at) for name, observed_at in observations.items()}

    def preflight(cycle_name: str):
        return evaluate_preflight(
            lambda: MockTargetEvidence(confirmed=True, target="mock"),
            lambda: AuditHealthEvidence(
                healthy=True,
                schema_version=3,
                integrity_ok=True,
                writable=True,
            ),
            lambda: cycles[cycle_name],
            lambda: UnresolvedOrderScan(complete=True, entries=()),
        )

    readiness = preflight("readiness")
    execution = preflight("execution")
    readiness_checks = {check.code: check for check in readiness.checks}
    execution_checks = {check.code: check for check in execution.checks}

    assert cycles["readiness"].session is MarketSession.PRE_OPEN
    assert cycles["readiness"].executable is False
    assert readiness_checks[PreflightCode.KRX_SESSION_BLOCKED].state is PreflightState.BLOCK
    assert readiness.global_executable is False
    for code in (
        PreflightCode.MOCK_TARGET_CONFIRMED,
        PreflightCode.AUDIT_HEALTHY,
        PreflightCode.UNRESOLVED_SCAN_CLEAR,
    ):
        assert readiness_checks[code].state is PreflightState.PASS

    assert cycles["execution"].session is MarketSession.CONTINUOUS
    assert cycles["execution"].executable is True
    assert execution_checks[PreflightCode.KRX_SESSION_OPEN].state is PreflightState.PASS
    assert all(check.state is PreflightState.PASS for check in execution.checks)
    assert execution.global_executable is True

    _, schedule = _table(_section(_text(), "일일 수동 운영 절차"))
    rows = {(row["KST"], row["수동 명령"]): row for row in schedule}
    readiness_row = rows[("08:50", "`bot status`")]
    execution_row = rows[("09:10 직전", "`bot status`")]
    assert "PRE_OPEN" in readiness_row["완료 조건"]
    assert "KRX_SESSION_BLOCKED" in readiness_row["완료 조건"]
    assert "`BLOCK`" in readiness_row["완료 조건"]
    assert "실행 가능: 아니오" in readiness_row["완료 조건"]
    assert "CONTINUOUS" in execution_row["완료 조건"]
    assert "KRX_SESSION_OPEN" in execution_row["완료 조건"]
    assert "`PASS`" in execution_row["완료 조건"]
    assert "실행 가능: 예" in execution_row["완료 조건"]


def test_daily_completion_contract() -> None:
    section = _section(_text(), "완료 판정")
    required = {
        "실행 상태가 `COMPLETED` 또는 `COMPLETED_WITH_ERRORS`인 terminal 실행",
        "시도한 각 티커에 정확히 하나의 terminal outcome",
        "모든 주문 또는 no-trade 증거와 stable reason code 검토",
        "`AMBIGUOUS_SUBMISSION`이 없거나 장애 대응 절차로 공식 이관",
        "알림 실패 시 `bot report daily` 직접 검토",
    }
    bullets = {
        line.removeprefix("- [ ] ").strip()
        for line in section.splitlines()
        if line.startswith("- [ ] ")
    }
    assert bullets == required


def test_failure_matrix_is_bijective_and_complete() -> None:
    header, rows = _table(_section(_text(), "장애 대응표"))

    assert header == TRIAGE_COLUMNS
    assert len(rows) == len(FAILURE_TYPES)
    assert {row["장애 유형"] for row in rows} == FAILURE_TYPES
    assert all(all(row[column] for column in TRIAGE_COLUMNS) for row in rows)

    codes = {
        "STALE_DATA": {"STALE_OHLCV", "STALE_QUOTE"},
        "API_FAILURE": {"KIS_UNAVAILABLE"},
        "LLM_TIMEOUT": {"LLM_TIMEOUT"},
        "AMBIGUOUS_SUBMISSION": {"AMBIGUOUS_SUBMISSION", "SUBMISSION_AMBIGUOUS"},
        "DUPLICATE_ORDER": {"DUPLICATE_ORDER", "DUPLICATE_CHECKED"},
        "NOTIFICATION_FAILURE": {"TRANSPORT_EXCEPTION", "TRANSPORT_FAILED"},
        "AUDIT_FAILURE": {"AUDIT_UNHEALTHY", "UNKNOWN", "BLOCK"},
    }
    for row in rows:
        assert codes[row["장애 유형"]] <= set(row["증상/코드"].replace("`", "").split(", "))


def test_recovery_prohibitions_and_resolution_contract() -> None:
    section = _section(_text(), "단계별 복구 체크리스트")

    for failure in FAILURE_TYPES:
        assert section.count(f"### {failure}\n") == 1
    assert "자동 재실행 금지" in section
    assert "blind resubmission 금지" in section
    assert "`bot run --parent-run-id <이전-run_id>`" in section
    assert "감사 증거가 정상이고 주문 제출 가능성이 없음이 확인된 경우에만" in section
    assert "영향받은 티커만 동결" in section
    assert "KIS 주문·미체결·체결 증거" in section
    assert "`RECONCILED` reconciliation 증거를 append-only로 추가" in section
    assert "기존 `order_intent_id`에 연결하고 재제출하지 않는다" in section
    assert "감사 불확실성은 신규 거래 전체 중단" in section
    assert "알림 전송 실패는 거래 결과를 바꾸지 않는 fail-soft" in section
    assert "자격 증명, webhook, 원시 payload, 전체 예외 본문을 복사하지 않는다" in section


def test_scope_fences() -> None:
    section = _section(_text(), "운영 범위와 금지선")
    fences = {
        "예약 실행·스케줄러·무인 자동 재실행",
        "자동 주문 재제출과 blind resubmission",
        "정책·설정 자동 변경",
        "수익성·투자성과 주장",
        "실계좌 전환 또는 자동 승격",
        "Phase 9 KIS 모의계좌 soak·장애 주입 실행",
    }
    bullets = {
        line.removeprefix("- ").strip()
        for line in section.splitlines()
        if line.startswith("- ")
    }
    assert bullets == fences

    text = _text()
    forbidden_authorizations = {
        "자동으로 다시 실행한다",
        "응답이 없으면 주문을 다시 제출한다",
        "보고 결과로 정책을 자동 변경한다",
        "실계좌를 자동으로 활성화한다",
        "replay 수익률",
    }
    assert not any(phrase in text for phrase in forbidden_authorizations)


def test_phase9_command_order_and_external_gates_are_exact() -> None:
    header, rows = _table(_section(_text(), "Phase 9 인증 운영 순서"))
    assert header == ["순서", "명령", "gate", "실패 exit"]
    assert [row["순서"] for row in rows] == [str(index) for index in range(1, 9)]
    commands = [row["명령"].strip("`") for row in rows]
    assert commands == [
        "bot soak start --campaign-id <campaign_id> --probe-only --fixture <compat.json>",
        "bot soak start --campaign-id <campaign_id> --accepted-profile <compat.json>",
        "bot status",
        "bot soak status --campaign-id <campaign_id>",
        "bot soak run --campaign-id <campaign_id> --run-id <run_id>",
        "bot soak status --campaign-id <campaign_id>",
        "bot soak resume --campaign-id <campaign_id>",
        "bot soak status --campaign-id <campaign_id>",
    ]
    assert all(row["실패 exit"] == "`2`" for row in rows)
    section = _section(_text(), "Phase 9 외부 완료 gate")
    assert "1일" in section and "20 eligible days" in section
    assert "실제 외부 KIS 모의계좌 확인" in section
    assert "CONTROLLED_INJECTION" in section and "KIS_OBSERVED" in section
    assert "synthetic evidence는 대체할 수 없다" in section


def test_every_fault_registry_command_and_recovery_owner_is_documented_once() -> None:
    section = _section(_text(), "Phase 9 fault drill 명령")
    slugs = {
        FaultName.STALE_DATA: "stale-data",
        FaultName.MALFORMED_LLM: "malformed-llm",
        FaultName.LLM_TIMEOUT: "timed-out-llm",
        FaultName.KIS_API_FAILURE: "kis-api-failure",
        FaultName.ACCEPTED_THEN_TIMEOUT: "accepted-then-timeout",
        FaultName.THROTTLING: "throttling",
        FaultName.PARTIAL_OR_NO_FILL: "partial-or-no-fill",
        FaultName.INTERRUPTION: "interruption",
        FaultName.NOTIFICATION_FAILURE: "notification-failure",
        FaultName.AUDIT_FAILURE: "audit-failure",
    }
    assert set(slugs) == set(FAULT_REGISTRY)
    for slug in slugs.values():
        command = f"bot soak drill {slug} --campaign-id <campaign_id>"
        assert section.count(command) == 1
    recovery = _section(_text(), "Phase 9 저장소 백업과 복구 순서")
    for owner in ("primary audit", "soak", "controller"):
        assert recovery.count(owner) >= 1
    for path in ("data/audit.db", "data/soak.db", "data/soak-controller.db"):
        assert recovery.count(path) >= 1
    assert (
        recovery.index("1. controller")
        < recovery.index("2. primary audit")
        < recovery.index("3. soak")
    )
    assert "query-only" in recovery
    assert "D-22" in recovery


def test_phase9_freeze_and_scope_contract_is_explicit() -> None:
    section = _section(_text(), "Phase 9 ambiguity와 동결")
    assert "000660" in section
    assert "FROZEN" in section and "non-credit" in section
    assert "D-13" in section and "재제출하지 않는다" in section
    assert "partial/no-fill" in section
    assert "same-subject determinate terminal broker evidence" in section

    fences = _section(_text(), "Phase 9 범위 금지선")
    for phrase in (
        "스케줄링",
        "실계좌 promotion",
        "정책 자동 변경",
        "자동 재제출",
        "수익성 주장",
        "새 전략",
    ):
        assert fences.count(phrase) == 1


def test_phase10_readiness_is_complete_manual_and_currently_blocked() -> None:
    section = _section(_text(), "Phase 10 실거래 승격 준비도")
    for code in (
        "REPLAY_VERIFIED", "SOAK_ACCEPTED", "REPORTS_COMPLETE", "ORDERS_RESOLVED",
        "CALIBRATION_VALID", "POLICY_FROZEN", "ROLLBACK_ACK", "KILL_ACK",
        "MANUAL_APPROVAL",
    ):
        assert section.count(code) == 1
    for option in (
        "--replay-result", "--calibration-fixture", "--audit-db", "--soak-db",
        "--controller-db", "--campaign-id", "--policy-snapshot",
        "--rollback-ack", "--kill-ack", "--manual-approval",
    ):
        assert option in section
    assert "현재 Phase 9 미완료·안전 실패" in section
    assert "BLOCKED" in section and "READY" in section
    for boundary in (
        "설정을 쓰거나", "주문 제출·재제출", "예약 실행", "Phase 9 waiver",
        "정책 자동 변경", "수익성 주장", "별도 수동 절차",
    ):
        assert boundary in section


def test_phase11_intraday_commands_timing_and_shutdown_are_exact() -> None:
    section = _section(_text(), "Phase 11 인트라데이 운영")
    for command in (
        "bot run",
        "bot intraday check",
        "bot intraday watch --interval-seconds 60",
        "bot status",
    ):
        assert command in section
    for phrase in (
        "60초 기본값이자 최솟값",
        "09:00",
        "15:20",
        "15:30",
        "PREFLIGHT_READ_ONLY",
        "ACTIVE",
        "RECONCILE_ONLY",
        "STOPPING",
        "TERMINAL",
        "Ctrl-C",
        "신규 POST 중단 → 제출 intent reconciliation → terminal 증거 저장 → lease 해제",
        "LLM을 만들거나 호출하지 않는다",
    ):
        assert phrase in section


def test_phase11_recovery_codes_and_prohibitions_are_explicit() -> None:
    section = _section(_text(), "Phase 11 안전 경계와 복구")
    for code in (
        "ACCOUNT_DATA_INCOMPLETE",
        "LEASE_BUSY",
        "LEASE_LOST",
        "ORDER_AMBIGUOUS",
        "LONG_OPEN_ORDER",
        "TRANSPORT_FAILED",
        "AUDIT_EVIDENCE_FAILED",
        "INFO",
        "WARNING",
        "CRITICAL",
    ):
        assert code in section
    for prohibition in (
        "백그라운드 scheduler/service 금지",
        "자동 취소 금지",
        "시장가 주문 금지",
        "공격적 price chasing 금지",
        "blind retry/resubmission 금지",
        "로컬 잔여수량 계산 금지",
        "실계좌 자동 승격 금지",
    ):
        assert prohibition in section
    assert "OPEN/PARTIAL SELL은 reconciliation-only" in section
    assert "현재 KIS 원장" in section


def test_phase11_authenticated_mock_uat_is_manual_and_sanitized() -> None:
    section = _section(_text(), "Phase 11 인증 모의계좌 UAT")
    for phrase in (
        "KIS 모의투자 자격 증명",
        "모든 pagination 페이지가 COMPLETE",
        "보유수량",
        "주문가능수량",
        "평균단가",
        "주문",
        "체결",
        "예수금",
        "partial-fill",
        "cancel",
        "자동화 테스트를 대체하지 않는다",
        "sanitized evidence",
    ):
        assert phrase in section
