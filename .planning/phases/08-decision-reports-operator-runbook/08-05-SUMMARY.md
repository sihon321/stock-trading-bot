---
phase: 08-decision-reports-operator-runbook
plan: 05
subsystem: documentation
tags: [operator-runbook, korean, safety, documentation-contract, pytest]

requires:
  - phase: 08-decision-reports-operator-runbook
    provides: Read-only reports, report CLI, shared preflight, and notification attribution from plans 08-01 through 08-04
provides:
  - Korean fixed-time manual operating procedure with evidence-based completion gate
  - Seven-category failure triage matrix and parent-linked safe recovery checklists
  - Mechanical documentation contract and completed Phase 8 Nyquist validation map
affects: [09-mock-soak, operator-operations, RUN-01, RUN-02, REP-01, REP-02]

tech-stack:
  added: []
  patterns: [executable documentation contract, stable-code operational playbook, evidence-gated manual recovery]

key-files:
  created:
    - docs/operator-runbook.md
    - tests/test_operator_runbook.py
  modified:
    - .planning/phases/08-decision-reports-operator-runbook/08-VALIDATION.md

key-decisions:
  - "일일 운영은 08:50 status, 09:05 screen, 09:10 run, 즉시 daily report의 수동 순서이며 모든 terminal·ticker·order·notification 증거 검토 전에는 완료가 아니다."
  - "재실행은 주문 미제출과 감사 건강성이 입증된 뒤에만 새 run_id와 --parent-run-id를 사용하며, ambiguous/duplicate 주문은 티커 동결과 reconciliation 없이는 재개하지 않는다."

patterns-established:
  - "운영 문서의 시간, 명령, 표 열, 장애 집합, 금지선은 strict set/count 기반 pytest 계약으로 고정한다."
  - "전역 감사 불확실성, 티커별 주문 불확실성, fail-soft 알림 실패를 서로 다른 중단 범위로 문서화한다."

requirements-completed: [RUN-01, RUN-02, REP-01, REP-02]

coverage:
  - id: D1
    description: "한국어 런북이 고정된 수동 KST 순서와 terminal·ticker·order·notification 증거 기반 완료 판정을 제공한다."
    requirement: RUN-01
    verification:
      - kind: integration
        ref: "tests/test_operator_runbook.py#test_manual_schedule_contract; test_daily_completion_contract"
        status: pass
    human_judgment: false
  - id: D2
    description: "일곱 장애의 정확한 코드와 여섯 대응 필드, parent-linked 재실행, 티커 동결, reconciliation, 감사/알림 경계를 기계적으로 고정한다."
    requirement: RUN-02
    verification:
      - kind: integration
        ref: "tests/test_operator_runbook.py#test_failure_matrix_is_bijective_and_complete; test_recovery_prohibitions_and_resolution_contract; test_scope_fences"
        status: pass
      - kind: integration
        ref: ".venv/bin/python -m pytest -q tests/test_operator_runbook.py tests/test_preflight.py tests/test_reporting.py tests/test_report_cli.py tests/test_sqlite_audit.py tests/test_cli.py tests/test_replay.py tests/test_notifier.py (135 passed)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Phase 8 전체 요구사항과 threat map의 실행 상태를 실제 targeted/full-suite 결과로 승인 완료한다."
    requirement: REP-02
    verification:
      - kind: integration
        ref: ".venv/bin/python -m pytest -q (471 passed)"
        status: pass
    human_judgment: false

duration: 4min
completed: 2026-07-14
status: complete
---

# Phase 8 Plan 5: Korean Operator Runbook Summary

**실제 CLI·stable evidence 어휘에 결박된 한국어 수동 운영 절차와 일곱 장애의 fail-closed 복구 계약을 제공한다.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-07-14T01:59:00+09:00
- **Completed:** 2026-07-14T02:07:00+09:00
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- 08:50 `bot status`, 09:05 `bot screen`, 09:10 `bot run`, 즉시 `bot report daily`의 수동 절차와 증거 기반 완료 판정을 한국어로 발행했다.
- STALE_DATA부터 AUDIT_FAILURE까지 정확히 일곱 장애에 증상/코드, 중단 범위, 확인 증거, 금지 행동, 안전한 다음 조치, 해결 기준을 모두 제공했다.
- 자동 재실행·blind resubmission·정책 변경·실계좌 승격 금지와 parent-linked retry, affected-ticker freeze, reconciliation 경계를 pytest 문서 계약으로 고정했다.
- Phase 8 targeted 135개와 전체 471개 테스트 통과 후 `08-VALIDATION.md`의 모든 task와 Nyquist 승인을 green으로 마감했다.

## Task Commits

Each task was committed atomically:

1. **Task 1: Contract-test the complete operator procedure and failure catalog** - `79940c8` (test, RED)
2. **Task 2: Write the Korean runbook and close Phase 8 validation** - `98ceb08` (docs, GREEN)

## Files Created/Modified

- `docs/operator-runbook.md` - 고정 일일 순서, 보고서 판독, 완료 gate, 장애표와 단계별 복구 절차.
- `tests/test_operator_runbook.py` - 정확한 표 구조·집합·코드·금지선을 검증하는 documentation contract.
- `.planning/phases/08-decision-reports-operator-runbook/08-VALIDATION.md` - 08-01-01부터 08-05-02까지 실제 green 결과와 승인 상태.

## Decisions Made

- 런북은 실제 구현이 제공하는 로컬 미해결 주문 스캔과 Phase 9의 인증된 KIS broker truth 확인을 명확히 구분한다.
- 알림 전송 실패는 거래 결과를 바꾸지 않지만 direct report review 전에는 일일 완료로 판정하지 않는다.
- 장애 복구는 이전 실행의 불변 증거를 보존하는 새 `run_id`와 `--parent-run-id`만 허용한다.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Test Bug] parent linkage 계약을 옵션 조각 대신 실제 전체 명령으로 검증**
- **Found during:** Task 2 targeted contract run
- **Issue:** RED 테스트가 `` `--parent-run-id <이전-run_id>` `` 옵션 조각만 요구해 실제 실행 가능한 명령을 작성한 런북을 거부했다.
- **Fix:** 실제 인터페이스인 `` `bot run --parent-run-id <이전-run_id>` `` 전체 명령을 정확히 검증하도록 수정했다.
- **Files modified:** `tests/test_operator_runbook.py`
- **Verification:** `tests/test_operator_runbook.py` 5 passed; targeted Phase 8 suite 135 passed.
- **Committed in:** `98ceb08`

---

**Total deviations:** 1 auto-fixed (1 test bug)
**Impact on plan:** 검증을 실제 CLI 인터페이스에 더 강하게 결박했으며 구현 범위는 바뀌지 않았다.

## Issues Encountered

None. 대상 회귀와 전체 회귀가 모두 통과했다.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 9는 이 런북의 전역 중단/티커 동결 경계를 유지하면서 인증된 KIS 모의계좌 주문·미체결·체결 조회 및 fault drill을 추가할 수 있다.
- Phase 8의 REP-01, REP-02, RUN-01, RUN-02는 자동 검증 증거를 갖췄고 미해결 blocker는 없다.

## Self-Check: PASSED

- `docs/operator-runbook.md`, `tests/test_operator_runbook.py`, `08-VALIDATION.md`, `08-05-SUMMARY.md` 존재 확인.
- Task commits `79940c8`, `98ceb08` 존재 확인.
- 계약 테스트 5 passed, Phase 8 targeted 135 passed, 전체 471 passed.

---
*Phase: 08-decision-reports-operator-runbook*
*Completed: 2026-07-14*
