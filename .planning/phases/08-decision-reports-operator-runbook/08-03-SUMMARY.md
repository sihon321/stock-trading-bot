---
phase: 08-decision-reports-operator-runbook
plan: 03
subsystem: cli
tags: [typer, reporting, atomic-write, offline, path-safety]

requires:
  - phase: 08-decision-reports-operator-runbook
    provides: Read-only daily, period, and replay reporting domain from plan 08-02
provides:
  - Credential-free nested daily, period, and replay report commands
  - Strict KST date/range validation and bounded fail-closed diagnostics
  - Byte-identical terminal/file delivery with atomic conflict-safe persistence
affects: [08-05-operator-runbook, REP-01, REP-02]

tech-stack:
  added: []
  patterns: [thin offline Typer controller, render-once delivery, atomic idempotent text writer]

key-files:
  created:
    - trading_bot/report_cli.py
    - tests/test_report_cli.py
  modified:
    - trading_bot/config.py
    - trading_bot/cli.py
    - tests/test_cli.py

key-decisions:
  - "보고 명령은 자격 증명 검증 Settings와 분리된 audit_db_path 전용 ReportSettings만 사용한다."
  - "터미널과 파일은 하나의 LF 정규화 UTF-8 payload를 공유하며 기존 파일의 다른 바이트는 덮어쓰지 않는다."

patterns-established:
  - "Report controllers validate operator input, delegate all aggregation to reporting.py, and never construct live collaborators."
  - "Report output rejects traversal, symbolic-link components, non-regular targets, and content conflicts before atomic replacement."

requirements-completed: [REP-01, REP-02]

coverage:
  - id: D1
    description: "자격 증명 없이 daily, period, replay 보고 명령을 발견하고 실행하며 strict 날짜·replay 검증을 reporting domain에 위임한다."
    requirement: REP-01
    verification:
      - kind: integration
        ref: "tests/test_report_cli.py#test_daily_and_period_are_offline_and_use_lightweight_default_path; test_replay_report_is_offline_and_uses_reporting_domain; tests/test_cli.py#test_report_group_is_discoverable_once_with_exact_nested_commands"
        status: pass
    human_judgment: false
  - id: D2
    description: "보고 문서를 터미널과 파일에 동일한 UTF-8 바이트로 전달하고 위험하거나 충돌하는 경로는 원자적으로 거부한다."
    requirement: REP-02
    verification:
      - kind: integration
        ref: "tests/test_report_cli.py#test_terminal_and_saved_report_are_byte_identical_and_idempotent; test_report_writer_rejects_conflicts_symlinks_nonregular_and_escaping_paths"
        status: pass
      - kind: integration
        ref: ".venv/bin/python -m pytest -q tests/test_reporting.py tests/test_report_cli.py tests/test_cli.py tests/test_replay.py (86 passed)"
        status: pass
    human_judgment: false

duration: 6min
completed: 2026-07-14
status: complete
---

# Phase 8 Plan 3: Offline Report CLI Summary

**읽기 전용 보고 도메인을 자격 증명 없는 Typer 명령으로 노출하고 동일 문서를 터미널과 원자적 파일 출력에 바이트 단위로 전달한다.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-07-13T16:38:16Z
- **Completed:** 2026-07-13T16:43:49Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- `bot report daily`, `period`, `replay` 명령과 strict `YYYY-MM-DD`/기간 검증을 추가하고 live runtime 구성 없이 기존 보고 모델을 호출한다.
- 전용 `ReportSettings`로 감사 DB 경로만 읽어 KIS·LLM 자격 증명이 없는 환경에서도 보고 명령을 실행한다.
- 한 번 렌더링한 LF 정규화 UTF-8 문서를 그대로 출력·저장하고, 동일 내용 재실행은 허용하되 traversal·심볼릭 링크·비정규 파일·충돌 내용은 거부한다.

## Task Commits

Each TDD task was committed atomically as RED then GREEN:

1. **Task 1 RED: 오프라인 보고 명령 계약** - `e78f016` (test)
2. **Task 1 GREEN: 자격 증명 없는 report sub-application** - `5f090cf` (feat)
3. **Task 2 RED: nested discovery와 terminal/file 전달 계약** - `73f2925` (test)
4. **Task 2 GREEN: 상위 등록과 원자적 텍스트 출력** - `404cfbf` (feat)

## Files Created/Modified

- `trading_bot/config.py` - 감사 DB 경로만 갖는 `ReportSettings`.
- `trading_bot/report_cli.py` - 세 보고 명령, 날짜 검증, bounded diagnostics, 안전한 atomic writer.
- `trading_bot/cli.py` - `report_app`을 정확히 한 번 등록하는 composition root.
- `tests/test_report_cli.py` - offline/default path, validation, renderer delegation, byte equality, path safety 회귀 테스트.
- `tests/test_cli.py` - 상위 명령 발견성과 기존 명령 무회귀 검증.

## Decisions Made

- `ReportSettings`는 `Settings`를 상속하거나 생성하지 않고 동일한 `.env` 규약만 공유해 보고 경로와 거래 자격 증명 경계를 분리했다.
- 출력 payload는 CRLF/CR을 LF로 정규화하고 정확히 한 개의 trailing newline을 보장한 뒤 terminal과 writer가 공유한다.
- 출력 경로의 모든 기존 구성요소에서 symbolic link를 거부하고, 같은 바이트가 있는 파일만 idempotent 성공으로 취급한다.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Test Bug] Rich help 테이블의 장식 문자를 고려하지 않은 명령 추출 수정**
- **Found during:** Task 2 GREEN
- **Issue:** 초기 테스트가 help 행이 명령 이름으로 바로 시작한다고 가정했지만 Typer Rich 출력은 행 앞에 테이블 경계 문자를 포함했다.
- **Fix:** 실제 사용자 출력에서 테이블 경계 다음의 명령 이름을 추출하도록 테스트를 조정했다.
- **Files modified:** `tests/test_cli.py`
- **Verification:** `tests/test_report_cli.py tests/test_cli.py` 24 passed
- **Committed in:** `404cfbf`

---

**Total deviations:** 1 auto-fixed (1 test bug)
**Impact on plan:** 실제 CLI 동작이나 계약은 바꾸지 않고 테스트가 실제 Typer 렌더링을 정확히 해석하게 했다.

## Issues Encountered

None. 계획 범위 86개 테스트와 전체 440개 회귀 테스트가 모두 통과했다.

## User Setup Required

None - report commands are offline and use the existing audit/replay files.

## Next Phase Readiness

- Phase 08-05 runbook에서 세 보고 명령과 `--output` 사용법을 실제 인터페이스로 문서화할 수 있다.
- Phase 08-04 live preflight/notification attribution과 독립적인 read-only 보고 경계가 유지된다.
- 미해결 blocker는 없다.

## Self-Check: PASSED

- 생성/수정 대상 5개 파일과 `08-03-SUMMARY.md` 존재 확인.
- Task commits `e78f016`, `5f090cf`, `73f2925`, `404cfbf` 존재 확인.
- 계획 범위 86개 및 전체 440개 테스트 통과.

---
*Phase: 08-decision-reports-operator-runbook*
*Completed: 2026-07-14*
