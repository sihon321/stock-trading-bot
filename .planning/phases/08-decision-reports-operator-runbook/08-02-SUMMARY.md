---
phase: 08-decision-reports-operator-runbook
plan: 02
subsystem: reporting
tags: [sqlite, replay, read-only, deterministic-rendering, evidence-integrity]

requires:
  - phase: 08-decision-reports-operator-runbook
    provides: SQLite v3 append-only notification evidence from plan 08-01
  - phase: 07-deterministic-replay-validation
    provides: Canonical replay identity, explicit-denominator funnels, and normalized JSON
provides:
  - Read-only daily and inclusive-period SQLite evidence projections with explicit lifecycle and notification states
  - Strict replay identity/cardinality validation, stable-ID deduplication, and compatibility-bounded aggregation
  - Deterministic summary-first Korean daily/period renderers and non-profitability replay renderer
affects: [08-03-report-cli, 08-05-operator-runbook, REP-01, REP-02]

tech-stack:
  added: []
  patterns: [SQLite URI mode=ro snapshot, normalized-row Python reduction, verified-before-aggregate replay evidence]

key-files:
  created:
    - trading_bot/reporting.py
    - tests/test_reporting.py
  modified: []

key-decisions:
  - "Run lifecycle, ticker completeness, execution target, reconciliation, and notification delivery remain separate report dimensions."
  - "Replay compatibility is defined by fixture schema, canonical policy, and scenario/input basis; stable result identity remains independently verified and attributable."
  - "FINAL_SUMMARY delivery state is derived from the latest run-scoped attempt by insertion ID, never by timestamp."

patterns-established:
  - "Reporting opens only an existing regular SQLite file with mode=ro and query_only, validates schema capability, and reads one explicit transaction."
  - "Replay files are strictly parsed, identity-verified, cardinality-checked, deduplicated, then grouped; no funnel is consumed before validation."
  - "Daily and period summaries are derived from the same immutable candidate rows rendered in full detail."

requirements-completed: [REP-01, REP-02]

coverage:
  - id: D1
    description: "SQLite 감사 증거를 변경하지 않고 실행 수명주기, 처리 순서, preview 차이, 티커/실행 알림 귀속, 명시적 분모를 일일·기간 보고 모델로 투영한다."
    requirement: REP-01
    verification:
      - kind: integration
        ref: "tests/test_reporting.py -k 'daily or period or readonly or reconciliation or run_lifecycle or zero_candidates or final_summary_notification'"
        status: pass
    human_judgment: false
  - id: D2
    description: "Replay 결과 ID와 funnel 무결성을 검증하고 중복을 제거한 뒤 호환 증거만 집계하며, 모든 보고서를 결정적으로 렌더링한다."
    requirement: REP-02
    verification:
      - kind: integration
        ref: "tests/test_reporting.py#test_replay_identity_is_verified_and_duplicate_ids_count_once; test_replay_malformed_funnel_fails_before_aggregation; test_replay_compatibility_groups_only_identical_basis_and_explains_mismatch; test_daily_period_and_replay_renderers_are_summary_first_and_deterministic"
        status: pass
      - kind: integration
        ref: ".venv/bin/python -m pytest -q tests/test_reporting.py tests/test_sqlite_audit.py tests/test_replay.py (77 passed)"
        status: pass
    human_judgment: false

duration: 10min
completed: 2026-07-14
status: complete
---

# Phase 8 Plan 2: Read-Only Decision and Replay Reports Summary

**SQLite 실행·티커·알림 증거와 replay JSON을 변경 없이 검증해 명시적 분모와 호환성 경계를 갖춘 결정적 보고서로 투영한다.**

## Performance

- **Duration:** 10 min
- **Started:** 2026-07-13T16:24:43Z
- **Completed:** 2026-07-13T16:34:11Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- 기존 정규화 테이블을 각각 조회하고 Python에서 안정 ID로 축약해 one-to-many 이벤트가 후보 수를 증식시키지 않는 read-only 일일·기간 보고 모델을 구현했다.
- 완료·오류완료·실패·중단·실행중·알 수 없는 수명주기와 zero-candidate 실행을 보존하고, 티커 알림과 run-scoped FINAL_SUMMARY 알림을 분리했다.
- Replay JSON을 strict 구조·stable ID·funnel cardinality 순으로 검증하고, 중복 ID는 한 번만 세며 호환 signature별로만 집계했다.
- 요약을 먼저, 모든 후보 상세를 뒤에 출력하는 결정적 Korean text renderer와 필수 비수익성 문구를 제공했다.

## Task Commits

Each TDD task was committed atomically as RED then GREEN:

1. **Task 1 RED: read-only SQLite report behavior** - `05b3b2e` (test)
2. **Task 1 GREEN: daily/period evidence projection** - `eb3ad19` (feat)
3. **Task 2 RED: replay validation and renderer behavior** - `78c3c64` (test)
4. **Task 2 GREEN: compatibility aggregation and deterministic rendering** - `ae34261` (feat)

## Files Created/Modified

- `trading_bot/reporting.py` - 불변 보고 계약, read-only SQLite repository, replay 검증/집계, 결정적 renderer.
- `tests/test_reporting.py` - 수명주기·순서·귀속·분모·무변경·replay identity/호환성·렌더링 회귀 테스트.

## Decisions Made

- 증거 완전성은 거래 성공 여부와 분리했다. 정상 terminal outcome은 no-trade나 execution error도 증거가 완전할 수 있지만, FAILED/INTERRUPTED/RUNNING 실행은 run-level INCOMPLETE로 유지한다.
- Preview는 같은 KST 거래일·같은 target의 가장 가까운 이전 SCREEN만 RUN과 연결하며, 이후 또는 다른 target의 screen은 결합하지 않는다.
- Replay 호환 signature에는 fixture schema, canonical policy, scenario/OHLCV/raw-signal hashes, initial state, evaluation time, trading date를 포함한다. Git revision은 각 stable ID에 남지만 같은 입력 기반의 집계를 불필요하게 분리하지 않는다.
- 원본 경로와 진단은 bounded label로만 렌더링하고 provider payload, exception body, credential 자료는 보고 모델에 포함하지 않는다.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Test Bug] 누락 수명주기 fixture가 NOT NULL 스키마와 충돌한 문제 수정**
- **Found during:** Task 1 GREEN
- **Issue:** 초기 RED 테스트가 `runs.status = NULL`을 쓰려 했지만 v3 스키마는 status를 NOT NULL로 보장한다.
- **Fix:** 실제로 가능한 legacy/unrecognized status 값을 사용해 동일한 UNKNOWN 투영 경계를 검증했다.
- **Files modified:** `tests/test_reporting.py`
- **Verification:** `tests/test_reporting.py` 15 passed
- **Committed in:** `eb3ad19`

**2. [Rule 1 - Test Bug] non-finite fixture의 canonical ID 재계산 시도가 strict serializer에서 먼저 실패한 문제 수정**
- **Found during:** Task 2 전체 검증
- **Issue:** Infinity가 canonical JSON 자체로 표현 불가능한데 테스트가 변조 후 stable ID 재계산을 시도했다.
- **Fix:** cardinality/unknown-field 변조는 ID를 재계산해 내부 검증까지 도달시키고, non-finite 변조는 strict JSON parser 경계에서 거부되도록 분리했다.
- **Files modified:** `tests/test_reporting.py`
- **Verification:** 계획 범위 77 passed, 전체 회귀 431 passed
- **Committed in:** `ae34261`

---

**Total deviations:** 2 auto-fixed (2 test bugs)
**Impact on plan:** 테스트 fixture만 실제 저장/직렬화 계약에 맞췄으며 보고 기능 범위나 안전 경계는 변경하지 않았다.

## Issues Encountered

None. 계획 범위 77개 테스트와 전체 431개 회귀 테스트가 모두 통과했다.

## User Setup Required

None - report core is offline and uses only existing SQLite/replay files.

## Next Phase Readiness

- Phase 08-03은 `build_*_report`와 `render_*_report`를 thin Typer subcommands에 연결할 수 있다.
- CLI는 동일 renderer 문자열을 terminal과 atomic file output에 전달하면 D-04를 만족할 수 있다.
- 미해결 blocker는 없다.

## Self-Check: PASSED

- `trading_bot/reporting.py`, `tests/test_reporting.py`, `08-02-SUMMARY.md` 존재 확인.
- Task commits `05b3b2e`, `eb3ad19`, `78c3c64`, `ae34261` 존재 확인.
- `.venv/bin/python -m pytest -q tests/test_reporting.py tests/test_sqlite_audit.py tests/test_replay.py` → 77 passed.
- `.venv/bin/python -m pytest -q` → 431 passed.

---
*Phase: 08-decision-reports-operator-runbook*
*Completed: 2026-07-14*
