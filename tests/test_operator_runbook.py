from __future__ import annotations

from pathlib import Path


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
        ("09:10", "`bot run`"),
        ("즉시", "`bot report daily`"),
    ]
    section = _section(_text(), "일일 수동 운영 절차")
    assert "운영자가 직접 실행하는 수동 절차" in section
    assert "예약 실행이나 스케줄링이 아니다" in section
    assert "09:05 화면은 미리보기" in section
    assert "09:10 실행은 후보를 새로 선별" in section


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
    assert "`--parent-run-id <이전-run_id>`" in section
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
