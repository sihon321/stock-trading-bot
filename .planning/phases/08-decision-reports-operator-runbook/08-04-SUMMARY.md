---
phase: 08-decision-reports-operator-runbook
plan: 04
subsystem: cli
tags: [preflight, sqlite, notifications, fail-closed, operator-safety]

requires:
  - phase: 08-decision-reports-operator-runbook
    provides: SQLite v3 notification evidence and read-only scoped reporting from plans 08-01 through 08-03
  - phase: 06-audit-evidence-cycle-boundaries
    provides: KRX session evidence, terminal ticker outcomes, and append-only order events
provides:
  - Shared typed PASS/BLOCK/UNKNOWN preflight rendered by status and enforced before run mutation
  - Global fail-closed gating plus determinate affected-ticker-only unresolved-order freezes
  - Exactly-once candidate error and run summary notification evidence with fail-soft transport
affects: [08-05-operator-runbook, 09-mock-soak, RUN-01, RUN-02, REP-02]

tech-stack:
  added: []
  patterns: [typed immutable preflight evidence, rollback-only audit probe, scoped append-only delivery evidence]

key-files:
  created:
    - trading_bot/preflight.py
    - tests/test_preflight.py
  modified:
    - trading_bot/cli.py
    - tests/test_cli.py
    - tests/test_notifier.py
    - tests/test_reporting.py

key-decisions:
  - "전역 실행 가능 여부는 stops_run이 설정된 전역 점검만 결정하며, 확정된 미해결 주문은 해당 티커만 동결한다."
  - "알림 transport 결과와 감사 증거 저장을 분리해 transport 실패는 거래 결과를 바꾸지 않지만 증거 저장 실패는 호출자에게 전파한다."
  - "Phase 8 unresolved-order 점검은 로컬 append-only 증거만 축약하며 인증된 KIS 원장 확인을 주장하지 않는다."

patterns-established:
  - "status와 run은 동일한 PreflightResult 계약을 사용하고 run은 스키마 생성·복구·실행 시작 전에 전역 차단 코드를 소비한다."
  - "IMMEDIATE_ERROR는 후보 ticker, FINAL_SUMMARY는 NULL ticker로 한 번만 저장하고 read-only 보고가 각 범위로만 투영한다."

requirements-completed: [RUN-01, RUN-02, REP-02]

coverage:
  - id: D1
    description: "모의투자 대상, 감사 건강성, KRX 세션, 미해결 주문을 타입화된 PASS/BLOCK/UNKNOWN으로 평가하고 불확실성은 실행 전면을 차단한다."
    requirement: RUN-01
    verification:
      - kind: integration
        ref: "tests/test_preflight.py; tests/test_cli.py#test_global_unknown_preflight_has_zero_run_mutation"
        status: pass
    human_judgment: false
  - id: D2
    description: "귀속이 확정된 ambiguous/duplicate 주문은 해당 티커의 LLM·브로커 변이만 막고 같은 실행의 다른 티커는 계속 처리한다."
    requirement: RUN-02
    verification:
      - kind: integration
        ref: "tests/test_preflight.py#test_confirmed_unresolved_order_freezes_only_affected_ticker; tests/test_cli.py#test_frozen_ticker_skips_candidate_mutation_while_sibling_completes"
        status: pass
    human_judgment: false
  - id: D3
    description: "후보 즉시 오류와 실행 최종 요약 알림을 전달·실패·비활성 상태 모두 정확한 범위에 한 번 저장하고 보고서에 누수 없이 투영한다."
    requirement: REP-02
    verification:
      - kind: integration
        ref: "tests/test_reporting.py#test_cli_produced_notification_rows_project_to_exact_scope; tests/test_cli.py#test_notification_evidence_write_failure_is_fail_closed"
        status: pass
      - kind: integration
        ref: ".venv/bin/python -m pytest -q (466 passed)"
        status: pass
    human_judgment: false

duration: 8min
completed: 2026-07-14
status: complete
---

# Phase 8 Plan 4: Shared Preflight and Notification Attribution Summary

**하나의 불변 preflight 결과가 실행 전역 차단과 티커별 주문 동결을 구분하고, 모든 알림 시도를 후보 또는 실행 범위에 정확히 한 번 보존한다.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-07-13T16:49:43Z
- **Completed:** 2026-07-13T16:57:51Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- `PreflightState`, stable `PreflightCode`, 불변 점검/결과 모델과 Korean renderer를 추가해 D-11의 모든 증거를 명시적으로 표시한다.
- 지원 스키마·quick check·foreign key·rollback-only 쓰기 가능성을 확인하고, 전역 불확실성은 run lifecycle mutation 이전에 종료한다.
- 로컬 order event를 축약해 귀속 가능한 ambiguous/duplicate 티커만 동결하고 형제 티커는 기존 실행 수명주기를 계속한다.
- 즉시 오류는 해당 후보 ticker로, 최종 요약은 NULL ticker로 전달·실패·비활성 결과를 append-only 저장하고 기존 보고 범위로 검증했다.

## Task Commits

Each TDD task was committed atomically as RED then GREEN:

1. **Task 1 RED: fail-closed preflight safety contract** - `aac84f0` (test)
2. **Task 1 GREEN: typed preflight evaluator and renderer** - `9d16d2f` (feat)
3. **Task 2 RED: CLI gate and notification attribution contract** - `1105770` (test)
4. **Task 2 GREEN: shared run gate and durable delivery outcomes** - `3764a5e` (feat)

## Files Created/Modified

- `trading_bot/preflight.py` - typed immutable evidence inputs, checks, aggregate result, evaluator, renderer.
- `trading_bot/cli.py` - production preflight readers, zero-mutation global gate, per-ticker freeze, scoped notification persistence.
- `tests/test_preflight.py` - PASS/BLOCK/UNKNOWN, exception sanitization, attribution, immutability, rollback-only audit probe.
- `tests/test_cli.py` - zero-mutation gate, sibling progress, status rendering, evidence-write failure regressions.
- `tests/test_notifier.py` - delivered/failed/disabled verdict classification.
- `tests/test_reporting.py` - CLI producer-to-read-only projection and exact scope/count regressions.

## Decisions Made

- `PreflightResult.global_executable`은 전역 점검의 `stops_run`만 축약한다. 티커 동결 점검은 BLOCK 상태를 표시하지만 전역 실행 가능성을 낮추지 않는다.
- 감사 건강성은 기존 DB를 `mode=rw`로 열고 `BEGIN IMMEDIATE` 안의 zero-row UPDATE를 rollback해 실행 행이나 임시 증거를 만들지 않고 검증한다.
- 알림 adapter의 `True`, `False`, `NoopNotifier`, 예외를 각각 DELIVERED, FAILED, DISABLED, FAILED stable evidence로 정규화한다.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. 계획 범위 89개 테스트와 전체 466개 회귀 테스트가 모두 통과했다.

## User Setup Required

None - no new dependency or external service configuration required.

## Next Phase Readiness

- Phase 08-05 runbook은 실제 `bot status` preflight 코드와 전역 차단/티커 동결 의미를 그대로 문서화할 수 있다.
- Phase 9는 로컬 증거 경계 뒤에서 인증된 KIS 주문·미체결·체결 조회 및 reconciliation 절차를 추가할 수 있다.
- 미해결 blocker는 없다.

## Self-Check: PASSED

- 생성/수정 대상 6개 파일과 `08-04-SUMMARY.md` 존재 확인.
- Task commits `aac84f0`, `9d16d2f`, `1105770`, `3764a5e` 존재 확인.
- 계획 범위 89개 테스트와 전체 466개 테스트 통과.

---
*Phase: 08-decision-reports-operator-runbook*
*Completed: 2026-07-14*
