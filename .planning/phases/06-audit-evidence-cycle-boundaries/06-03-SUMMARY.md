---
phase: 06-audit-evidence-cycle-boundaries
plan: 03
subsystem: execution
tags: [kis, sqlite, audit, idempotency, reconciliation]
requires:
  - phase: 06-01
    provides: Versioned append-only order_events schema and normalized audit models
  - phase: 06-02
    provides: Run lifecycle and exactly-one ticker outcome boundary
provides:
  - Durable UUID order-intent and submission identities
  - Append-only normalized KIS order evidence
  - Typed ambiguous-submission terminalization and cross-run reconciliation
affects: [06-04, phase-7-replay, phase-8-reporting, phase-9-soak]
tech-stack:
  added: []
  patterns: [synchronous evidence sink, single-shot POST, origin-observer attribution]
key-files:
  created: []
  modified: [trading_bot/kis_broker.py, trading_bot/execution.py, trading_bot/cli.py]
key-decisions:
  - "A transport failure after the single KIS POST is always ambiguous, never automatically retried."
  - "Only normalized scalar broker facts cross the append-only evidence boundary."
patterns-established:
  - "Order evidence sink: broker transitions synchronously append OrderEvent records."
  - "Reconciliation attribution: origin_run_id remains stable while observer_run_id identifies later inquiry."
requirements-completed: [EVID-01, EVID-02, EVID-03, EVID-04]
coverage:
  - id: D1
    description: Append-only intent, submission, acceptance, duplicate, and reconciliation chain
    requirement: EVID-03
    verification:
      - kind: integration
        ref: tests/test_kis_broker.py#test_append_only_evidence_has_stable_intent_and_distinct_submission
        status: pass
    human_judgment: false
  - id: D2
    description: Single-shot ambiguous POST and later dual-run broker observation
    requirement: EVID-04
    verification:
      - kind: integration
        ref: tests/test_kis_broker.py#test_ambiguous_evidence_is_single_shot_and_later_observation_links_runs
        status: pass
      - kind: integration
        ref: tests/test_cli.py#test_ambiguous_submission_becomes_terminal_ticker_outcome
        status: pass
    human_judgment: false
duration: 12min
completed: 2026-07-11
status: complete
---

# Phase 6 Plan 03: Append-only Order Evidence Summary

**KIS 주문의 의도부터 모호한 제출과 후속 조정까지 단일 append-only 증거 체인으로 추적합니다.**

## Performance

- **Duration:** 12 min
- **Completed:** 2026-07-11
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- 실행 경계에서 주문 의도 UUID를 만들고 실제 POST마다 별도 제출 UUID를 발급합니다.
- 중복 확인, 제출 시도, 접수, 체결 조회를 정규화된 불변 이벤트로 남깁니다.
- 불확실한 POST는 한 번만 시도한 뒤 typed ambiguity로 종료하고, 후속 조회는 원 실행과 관찰 실행을 함께 연결합니다.

## Task Commits

1. **Task 06-03-01: Emit append-only intent and submission evidence** - `6ab1f85`
2. **Task 06-03-02: Terminalize ambiguous submissions and link later reconciliation** - `3f0c70d`

## Files Created/Modified

- `trading_bot/kis_broker.py` - evidence sink, identities, ambiguity, reconciliation entry point
- `trading_bot/execution.py` - money-moving boundary에서 intent와 run context 전달
- `trading_bot/llm_provider.py` - 실행 run attribution 전달
- `trading_bot/ports.py` - 선택적 주문 증거 context를 허용하는 broker protocol
- `trading_bot/cli.py` - SQLite sink 연결과 ambiguous terminal outcome
- `tests/test_kis_broker.py` - 불변 체인, single POST, dual-run reconciliation 검증
- `tests/test_cli.py` - ambiguous ticker terminalization 검증

## Decisions Made

- POST 응답이 불확실하면 원인 예외 본문을 저장하지 않고 식별자와 오류 유형만 저장합니다.
- `last_reconciliation`은 호환용 최신 요약으로 유지하지만 감사 진실은 append-only 이벤트입니다.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] 실행 run attribution을 LLM wrapper와 Broker protocol에 전달**
- **Issue:** 계획 파일 목록만 수정하면 실행 경계에서 생성한 intent에 실제 run ID를 전달할 수 없었습니다.
- **Fix:** `llm_provider.py`와 `ports.py`의 호환 가능한 선택 인자를 추가했습니다.
- **Verification:** 전체 351개 테스트 통과
- **Committed in:** `6ab1f85`

## Issues Encountered

None.

## User Setup Required

None.

## Next Phase Readiness

Plan 06-04가 주문 직전 시세와 시장 세션 증거를 같은 실행/주문 경계에 연결할 수 있습니다.

## Self-Check: PASSED

- Task commits exist: `6ab1f85`, `3f0c70d`
- Full suite: 351 passed
- No raw KIS response or exception body is persisted

---
*Phase: 06-audit-evidence-cycle-boundaries*
*Completed: 2026-07-11*
