---
phase: quick-260728-d3r
plan: 01
subsystem: soak-calendar
tags: [python, kis, mock, krx, preflight, fail-closed]
requires:
  - phase: 09-kis-mock-soak-fault-drills
    provides: Mock-only soak composition root and fail-closed KRX session policy
provides:
  - Authenticated mock-only KIS calendar witness normalized to true, false, or unavailable
  - Current-day-only pykrx lag resolution for KIS mock soak market classification
affects: [soak-admission, market-cycle, mock-isolation]
tech-stack:
  added: []
  patterns:
    - "Untrusted broker calendar evidence requires one exact requested-date row and an explicit opnd_yn value."
    - "Optional current-day witnesses are accepted only as exact bool values and otherwise preserve UNKNOWN."
key-files:
  created: []
  modified:
    - trading_bot/kis_order.py
    - trading_bot/data_source.py
    - trading_bot/cli.py
    - tests/test_kis_order.py
    - tests/test_market_cycle.py
    - tests/test_soak_cli.py
key-decisions:
  - "The CTCA0903R witness is available only through the mock adapter profile and uses GET without hashkey or order submission."
  - "Only current-day empty-OHLCV evidence can consult the witness; historical empty data remains closed and ambiguous data remains UNKNOWN."
requirements-completed: [QUICK-KRX-SOAK-PREFLIGHT-01]
coverage:
  - id: D1
    description: Mock calendar responses normalize only explicit requested-date open or closed evidence.
    requirement: QUICK-KRX-SOAK-PREFLIGHT-01
    verification:
      - kind: unit
        ref: tests/test_kis_order.py#test_mock_calendar_witness_normalizes_explicit_open_and_closed_days
        status: pass
      - kind: unit
        ref: tests/test_kis_order.py#test_mock_calendar_witness_fails_closed_for_unavailable_or_ambiguous_responses
        status: pass
    human_judgment: false
  - id: D2
    description: Only a current-day pykrx lag plus explicit mock evidence can admit the continuous KRX session.
    requirement: QUICK-KRX-SOAK-PREFLIGHT-01
    verification:
      - kind: unit
        ref: tests/test_market_cycle.py#test_observed_calendar_uses_only_explicit_current_day_mock_witness_for_pykrx_lag
        status: pass
      - kind: integration
        ref: tests/test_soak_cli.py#test_soak_runtime_wires_only_its_selected_mock_adapter_as_calendar_witness
        status: pass
    human_judgment: false
duration: 20min
completed: 2026-07-28
status: complete
---

# Quick Task 260728-d3r: KRX Market Session Preflight Unknown Summary

**A mock-only, authenticated KIS calendar witness now resolves same-day pykrx OHLCV lag while every malformed, failed, or ambiguous response remains fail-closed UNKNOWN.**

## Performance

- **Duration:** 20 min
- **Completed:** 2026-07-28T00:35:04Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Added a read-only `CTCA0903R` calendar query that validates exactly one requested-date `opnd_yn` record and returns only `True`, `False`, or `None`.
- Extended `ObservedKRXCalendar` with a cached, optional current-day witness that catches provider exceptions and rejects non-boolean values.
- Wired the witness solely from the selected soak mock adapter; ordinary preflight construction remains pykrx-only.

## Task Commits

1. **Task 1: Add a normalized, read-only KIS mock trading-calendar witness** - `b301ac2` (feat)
2. **Task 2: Use the mock calendar witness only to resolve same-day pykrx lag in soak admission** - `1ad1ec9` (fix)

## Verification

- `.venv/bin/python -m pytest tests/test_kis_order.py -q` — 10 passed.
- `.venv/bin/python -m pytest tests/test_market_cycle.py tests/test_soak_cli.py tests/test_preflight.py -q` — 54 passed.
- `.venv/bin/python -m pytest tests/test_cli.py -q` — 21 passed.
- `git diff --check -- trading_bot/kis_order.py trading_bot/data_source.py trading_bot/cli.py tests/test_kis_order.py tests/test_market_cycle.py tests/test_soak_cli.py` — passed.
- `.venv/bin/python -m pytest -q` — blocked at collection by the pre-existing unrelated `CandidateReportRow.reason_detail` mismatch in `tests/test_soak_campaign.py`; no unrelated files were changed.

## Decisions Made

- The calendar method refuses the real adapter profile before making any request, and never calls hashkey or POST-capable code.
- Calendar fallback is limited to a current KST date whose pykrx evidence specifically indicates empty/no OHLCV; general provider failures remain unknown.

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None.

## Next Phase Readiness

Mock soak admission can proceed during a confirmed continuous KRX session despite current-day daily-OHLCV lag, without weakening the ordinary preflight, real-money isolation, or active ambiguity freeze.

## Self-Check: PASSED

- Task commits `b301ac2` and `1ad1ec9` exist in git history.
- All six planned source and test files exist.
- Unrelated dirty paths remain unstaged and unmodified by this task.
