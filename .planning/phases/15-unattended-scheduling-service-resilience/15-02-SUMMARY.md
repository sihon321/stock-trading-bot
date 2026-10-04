---
phase: 15-unattended-scheduling-service-resilience
plan: "02"
subsystem: execution
tags: [krx, sessions, intraday, fail-closed, offline-tests]
requires:
  - phase: 15-01
    provides: Immutable SessionEvidence contracts and shared offline clocks/session fixtures
provides:
  - Protected reviewed exact-date exchange session loader and refreshable provider
  - Unified market and intraday classification with absolute order/watch cutoffs
affects: [15-04, 15-08, 15-09, 15-10, 15-13]
tech-stack:
  added: []
  patterns: [owner-local bounded JSON authority, exact-date session review, injected shared policy]
key-files:
  created: [trading_bot/session_evidence.py, tests/test_service_sessions.py]
  modified: [trading_bot/market_cycle.py, trading_bot/data_source.py, trading_bot/intraday.py]
key-decisions:
  - "SessionEvidenceProvider re-reads owner-protected exact-date authority; a service policy refreshes current calendar observations rather than caching UNKNOWN indefinitely."
  - "Intraday phase classification preserves absolute 15:20 POST and 15:30 termination limits, including delayed opening, early close, missing authority and overnight wake."
  - "Shared SessionEvidence field names remain canonical; JSON date/content_hash aliases are normalized with conflicts rejected."
requirements-completed: []
coverage:
  - id: D1
    description: Exact-date reviewed session authority rejects stale, contradictory, synthetic and unprotected inputs
    requirement: AUTO-01
    verification:
      - kind: unit
        ref: tests/test_service_sessions.py#test_invalid_or_stale_notice_is_unknown
        status: pass
      - kind: unit
        ref: tests/test_service_sessions.py#test_contradictory_calendar_and_notices_fail_closed
        status: pass
      - kind: unit
        ref: tests/test_service_sessions.py#test_owner_local_bounds_and_symlinks
        status: pass
    human_judgment: false
  - id: D2
    description: Current UNKNOWN calendar/session observations can refresh only from new positive evidence
    verification:
      - kind: unit
        ref: tests/test_service_sessions.py#test_policy_refreshes_current_unknown_calendar_with_same_saved_session
        status: pass
      - kind: unit
        ref: tests/test_service_sessions.py#test_new_positive_notice_refreshes_unknown_without_cached_authority
        status: pass
    human_judgment: false
  - id: D3
    description: Intraday uses shared authority and absolute cutoffs with no delayed or overnight submission permission
    verification:
      - kind: unit
        ref: tests/test_service_sessions.py#test_intraday_uses_shared_session_authority
        status: pass
      - kind: unit
        ref: tests/test_service_sessions.py#test_session_rechecked_after_slow_quote_before_post
        status: pass
      - kind: unit
        ref: tests/test_service_sessions.py#test_watch_midnight_rollover_terminates_previous_day
        status: pass
    human_judgment: false
duration: 4min
completed: 2026-10-04
status: complete
---

# Phase 15 Plan 02: Authoritative Session Evidence Summary

**검토된 정확한 날짜의 KRX 세션 증거를 시장 정책과 장중 감시에 연결하고 지연 개장에도 15:20 주문 제한과 15:30 종료를 유지한다.**

## Performance

- Recorded execution interval: 2026-10-04T03:33:14Z–2026-10-04T03:37:34Z, 4min. Initial context discovery preceded the recorded task clock.
- Tasks: 2/2. Implementation/test files: 5.

## Accomplishments

- `load_session_evidence(path, requested_date, clock)`는 단일 공지 또는 `{"sessions": [...]}`의 최대 64KiB/366개 JSON을 읽는다. 공유 `SessionEvidence` 모델, 소유자 전용 권한, 일반 파일, symlink 금지, 중복 JSON 필드 및 중복 날짜, 정확한 effective/observed 날짜, 미래 관찰/검토 금지, SHA256 형식 및 검토자/공지/KRX HTTPS 출처를 검증한다. 누락·상충·synthetic 입력은 거래 시각 없는 UNKNOWN이다. digest는 소유자 검토의 기록이며 외부 페이지를 조회하거나 원문 진위를 새로 확인했다는 주장을 하지 않는다.
- `SessionEvidenceProvider(path, clock).for_date(day)` 및 callable API는 저장된 증거를 재읽는다. `MarketCyclePolicy(..., session_evidence_provider=...)`는 해당 날짜의 긍정적인 calendar와 일치하는 세션만 사용한다. `ObservedKRXCalendar.refresh(day)`는 UNKNOWN/현재 날짜를 한 번 재관찰하고 확정된 과거 캐시는 보존한다. 서비스용 정책은 refresh가 제공되면 호출한다.
- `session_phase_at`, `run_intraday_check`, `run_intraday_watch`는 선택적인 `policy`를 공유한다. PRE_OPEN은 PREFLIGHT_READ_ONLY, UNKNOWN/휴일은 RECOVERY_ONLY, 확인된 연속 거래만 ACTIVE이다. 조기 폐장과 15:20은 RECONCILE_ONLY, 15:30과 감시 날짜 rollover는 TERMINAL이다. 주입 정책 경로는 시세 조회 이후 제출 직전에 세션을 다시 확인한다. 계좌 lease의 작업별 수명주기는 15-09에 남겨 두었다.

## Task Commits

| Task | Stage | Commit | Verification |
|---|---|---|---|
| 1 | RED | bf0d0bb | 27 expected failures / existing 46 passed |
| 1 | GREEN | 5d978f0 | 76 passed; authority and calendar refresh |
| 2 | RED | c31e3e8 | 19 expected policy API failures / 92 passed |
| 2 | GREEN | 7fb5425 | 111 passed; shared phases/cutoffs/wake |

## Verification

- Task 1 command: `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_service_sessions.py tests/test_market_cycle.py` → **76 passed in 0.34s**.
- Final required focused command (duplicate paths in plan-level verification deduplicated): `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_service_sessions.py tests/test_market_cycle.py tests/test_intraday.py` → **111 passed in 0.59s**.
- Acceptance criteria pass: normal/delayed reviewed dates, stale/missing/contradictory authority, calendar UNKNOWN refresh, completed-bar and inclusive ten-second quote regressions, 08:50/09:00/09:19:59/10:00/15:19:59/15:20/15:30 boundaries, early close, slow-quote cutoff, midnight/wake.
- `git diff --check` passed. Normal commit hooks ran; no unexpected tracked deletion or generated untracked output.
- All inputs were injected or temporary offline files. No dependency install/download, production database open/migration, broker/market/Discord/paid-provider calls, service install or launchctl execution occurred.

## Files Created/Modified

- `trading_bot/session_evidence.py`: protected exact-date saved authority loader/provider and explicit UNKNOWN.
- `trading_bot/market_cycle.py`: shared date/session dependency and effective opening/closing bounds.
- `trading_bot/data_source.py`: bounded UNKNOWN/current-date calendar refresh.
- `trading_bot/intraday.py`: injected policy phase transitions, cutoff recheck and old-date watch termination.
- `tests/test_service_sessions.py`: 49 offline session/refresh/intraday proofs; existing shared fixture owner remains unchanged.

## Decisions Made

- 날짜별 저장 증거를 매번 읽고 현재 calendar를 refresh해 장기 서비스의 UNKNOWN 고착을 방지한다. boolean KIS witness는 특별 세션 시각을 대신하지 못한다.
- 공유 모델의 `trading_date_kst`/`source_hash`를 유지하면서 계획의 JSON `date`/`content_hash`도 충돌 없이 허용한다.
- 기존 독립 정상 세션 호출은 호환된다. 모든 운영 mutable composition의 필수 주입/최종 권한 연결은 15-08/09의 책임이다.

## Deviations from Plan

None — both planned tasks implemented within declared ownership. `tests/test_market_cycle.py` needed no edits; its existing completed-bar/quote/calendar regressions passed unchanged. No new architecture, dependency or schema migration was introduced.

## Issues Encountered

None. RED failures were deliberate missing module/refresh/policy APIs; there were no collection or syntax failures.

## Known Stubs

None preventing this plan's goal. UNKNOWN identity/digest sentinels and absent bounds intentionally confer no authority; synthetic fixture evidence does not supply production review or approval.

## External Activation Blockers

- Both Phase 09-08 task 1/task 2 human approvals remain absent; unattended trading activation remains closed.
- 000660 remains frozen until same-subject determinate terminal broker evidence. This work neither submits nor releases it.
- Real-money service remains prohibited; Phase 16 promotion is a separate deliberate gate.
- Reviewed current exact-date production notices and later production policy wiring remain activation inputs. Tests do not authenticate KRX source content or claim macOS owner-login/wake/private-device acceptance.
- AUTO-01/FUT-04/AUTO-02 remain pending for subsequent plans and final phase verification; `requirements-completed` is empty.

## User Setup Required

None for offline implementation; no live service activation performed.

## Next Plan Readiness

15-03 can continue against existing shared contracts. Scheduling, submission authority and bounded service composition can consume the provider and policy APIs above while retaining approval/freeze gates.

## Self-Check: PASSED

- All five implementation/test paths exist; SUMMARY written to the canonical phase path.
- All four RED/GREEN commit objects were verified with `git cat-file -t`.
- Required focused checks and acceptance matrix passed. No requirement completion or external acceptance is inferred.
