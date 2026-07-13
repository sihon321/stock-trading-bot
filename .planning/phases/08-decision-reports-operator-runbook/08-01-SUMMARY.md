---
phase: 08-decision-reports-operator-runbook
plan: 01
subsystem: database
tags: [sqlite, audit, notifications, migration, append-only]

requires:
  - phase: 06-audit-evidence-cycle-boundaries
    provides: Versioned SQLite lifecycle, ticker outcome, and append-only order evidence
provides:
  - Provider-neutral immutable notification delivery evidence contracts
  - Additive transactional SQLite schema v3 migration for notification attempts
  - Immediately committed append-only notification attempt persistence API
affects: [08-02-reporting, 08-04-preflight-notification-attribution, RUN-02]

tech-stack:
  added: []
  patterns: [sanitized scalar evidence, append-only insertion identity, transactional additive migration]

key-files:
  created: []
  modified:
    - trading_bot/audit_models.py
    - trading_bot/sqlite_audit.py
    - tests/test_sqlite_audit.py

key-decisions:
  - "Notification failure categories are bounded uppercase stable codes; arbitrary exception text never crosses the evidence boundary."
  - "Notification attempt time is timezone-aware and persisted as ISO 8601 while integer insertion IDs remain the authoritative attempt order."

patterns-established:
  - "Notification evidence is immutable, scalar-only, and rejects webhook, body, message, exception, credential, token, and provider payload fields."
  - "Every delivery attempt is a new immediately committed row; prior attempts are never overwritten."

requirements-completed: [REP-01, REP-02, RUN-02]

coverage:
  - id: D1
    description: "기존 v1/v2 감사 DB를 행 손실 없이 알림 증거를 포함한 스키마 v3로 원자적으로 마이그레이션한다."
    requirement: REP-01
    verification:
      - kind: integration
        ref: "tests/test_sqlite_audit.py#test_v1_migrates_to_v3_idempotently_without_row_loss; test_v2_migration_preserves_normalized_evidence; test_migration_failure_rolls_back_and_reopen_retries"
        status: pass
    human_judgment: false
  - id: D2
    description: "알림 시도는 민감정보 없이 실행과 티커에 귀속되어 삽입 순서대로 append-only 저장된다."
    requirement: RUN-02
    verification:
      - kind: integration
        ref: "tests/test_sqlite_audit.py#test_append_notification_attempt_is_ordered_append_only_and_committed; test_invalid_notification_evidence_leaves_no_partial_row"
        status: pass
    human_judgment: false

duration: 4min
completed: 2026-07-14
status: complete
---

# Phase 8 Plan 1: Notification Evidence Summary

**스키마 v3와 불변 알림 계약으로 실패를 포함한 모든 전달 시도를 민감정보 없이 실행별 append-only 증거로 보존한다.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-07-13T16:16:48Z
- **Completed:** 2026-07-13T16:20:08Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- `NotificationKind`, `NotificationDeliveryStatus`, frozen `NotificationAttempt` 계약과 민감정보 차단 경계를 추가했다.
- v1/v2 감사 DB의 기존 실행·결정·티커 결과·주문 이벤트를 보존하는 트랜잭션형 SQLite v3 마이그레이션을 구현했다.
- 실행 귀속, enum 재검증, 바인딩 SQL, 즉시 커밋, 안정적인 삽입 ID를 갖춘 `append_notification_attempt()`를 제공했다.

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: 알림 증거 및 마이그레이션 회귀 테스트** - `548c0b0` (test)
2. **Task 1 GREEN: 알림 증거 계약과 스키마 v3** - `f0449af` (feat)
3. **Task 2 RED: append-only 저장 API 회귀 테스트** - `94f5801` (test)
4. **Task 2 GREEN: 알림 시도 저장 API** - `9e5e7dc` (feat)

## Files Created/Modified

- `trading_bot/audit_models.py` - 알림 종류/전달 상태 enum, 불변 시도 계약, 민감 필드 및 크기 검증.
- `trading_bot/sqlite_audit.py` - 스키마 v3 테이블/인덱스 마이그레이션과 append-only writer.
- `tests/test_sqlite_audit.py` - v1/v2 보존, 실패 롤백/재시도, 입력 검증, 순서/커밋 회귀 테스트.

## Decisions Made

- `failure_category`는 최대 64자의 대문자 stable code로 제한해 원시 예외 문장이 저장되지 않게 했다.
- 알림 상세는 기존 scalar-only sanitizer를 재사용하고 알림 경계에서 키 64자, 문자열 값 512자로 추가 제한했다.
- `observed_at`은 timezone-aware `datetime`만 허용하고 ISO 8601로 저장하되, 동률 가능성이 있는 시간 대신 정수 `id`를 정렬 기준으로 유지했다.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Test Bug] v2 롤백 검증이 v1 보존 테스트에 잘못 배치된 문제 수정**
- **Found during:** Task 2 전체 SQLite 회귀 실행
- **Issue:** 주입 실패 블록이 v1 fixture 테스트에 들어가 v2 `user_version` 기대와 충돌했다.
- **Fix:** 실패 주입과 롤백 검증을 실제 v2 fixture 마이그레이션 테스트로 이동했다.
- **Files modified:** `tests/test_sqlite_audit.py`
- **Verification:** `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_sqlite_audit.py` → 15 passed
- **Committed in:** `9e5e7dc`

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** 검증 배치만 바로잡았으며 구현 범위나 증거 계약은 변경하지 않았다.

## Issues Encountered

- 로컬 Python user base에 `ruff`가 없어 선택적 lint 명령은 실행하지 못했다. 계획의 필수 pytest 검증은 모두 통과했다.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 08-02의 read-only 보고서가 `notification_attempts`를 조회해 전달 성공·실패·비활성 상태를 사실대로 표시할 수 있다.
- Phase 08-04는 현재 notifier 결과를 이 writer에 귀속시키기만 하면 되며, 거래 결과의 fail-soft 의미는 바뀌지 않는다.

## Self-Check: PASSED

- 수정 대상 3개 파일과 `08-01-SUMMARY.md` 존재 확인.
- Task commit `548c0b0`, `f0449af`, `94f5801`, `9e5e7dc` 존재 확인.
- `tests/test_sqlite_audit.py` 전체 15개 테스트 통과.

---
*Phase: 08-decision-reports-operator-runbook*
*Completed: 2026-07-14*
