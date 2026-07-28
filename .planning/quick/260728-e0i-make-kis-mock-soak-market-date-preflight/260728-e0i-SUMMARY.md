---
phase: quick-260728-e0i
plan: 01
subsystem: market-calendar
tags: [pykrx, kis-mock, preflight, fail-closed, tdd]
requires:
  - phase: quick-260728-d3r
    provides: mock-only KIS calendar witness and current-day empty-OHLCV handling
provides:
  - Current-day pykrx uncertainty resolution through exact boolean mock-calendar evidence
  - Bounded UNKNOWN provenance propagated into market-cycle evidence
affects: [KIS mock soak, market preflight, observed calendar]
tech-stack:
  added: []
  patterns:
    - Cache calendar state and safe diagnostic provenance together by date
    - Allowlist optional diagnostic capability values at the policy boundary
key-files:
  created: []
  modified:
    - trading_bot/data_source.py
    - trading_bot/market_cycle.py
    - tests/test_market_cycle.py
key-decisions:
  - "Only type(value) is bool from the preselected mock witness can resolve current-day pykrx uncertainty."
  - "Unknown calendar provenance is limited to two stable allowlisted codes and never includes provider text."
requirements-completed: [QUICK-KIS-MOCK-SOAK-CALENDAR-RESILIENCE-01]
coverage:
  - id: D1
    description: Current-day pykrx exceptions, unavailable results, malformed results, and missing OHLCV use exact mock witness booleans only.
    requirement: QUICK-KIS-MOCK-SOAK-CALENDAR-RESILIENCE-01
    verification:
      - kind: unit
        ref: tests/test_market_cycle.py#test_observed_calendar_uses_exact_witness_for_every_current_day_pykrx_uncertainty
        status: pass
    human_judgment: false
  - id: D2
    description: Unresolved observed-calendar diagnostics remain bounded and market evidence remains non-executable.
    requirement: QUICK-KIS-MOCK-SOAK-CALENDAR-RESILIENCE-01
    verification:
      - kind: unit
        ref: tests/test_market_cycle.py#test_market_policy_propagates_allowlisted_observed_calendar_diagnostic
        status: pass
      - kind: integration
        ref: .venv/bin/python -m pytest tests/test_market_cycle.py tests/test_kis_order.py tests/test_soak_cli.py tests/test_preflight.py -q
        status: pass
    human_judgment: false
duration: 5min
completed: 2026-07-28
status: complete
---

# Phase quick-260728-e0i Plan 01: KIS Mock Soak Market-Date Preflight Summary

**Current-day pykrx uncertainty now resolves only through exact mock-calendar booleans, with bounded fail-closed UNKNOWN evidence carried into market preflight.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-07-28T01:06:00Z
- **Completed:** 2026-07-28T01:11:53Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Consulted the existing selected mock-calendar witness exactly once for every inconclusive current-day pykrx outcome, including exceptions and malformed responses.
- Cached final calendar state alongside a safe UNKNOWN diagnostic, retaining historical closure and source-failure semantics.
- Propagated only allowlisted diagnostics through `MarketCyclePolicy`; invalid, missing, or raising accessors retain `calendar unavailable` and blocked execution.

## Task Commits

1. **Task 1: Resolve all current-day pykrx uncertainty only through exact mock-calendar evidence** - `4274cb8` (feat)
2. **Task 2: Carry bounded calendar diagnostics into fail-closed market evidence without changing preflight authority** - `270b114` (fix)

## Files Created/Modified

- `trading_bot/data_source.py` - composite current-day calendar resolution, bounded provenance, and per-date caching.
- `trading_bot/market_cycle.py` - defensive allowlisted diagnostic handoff for UNKNOWN dates.
- `tests/test_market_cycle.py` - table-driven witness, caching, diagnostic, and policy fallback coverage.

## Decisions Made

- Exact built-in booleans are the sole evidence allowed to resolve a current-day pykrx uncertainty.
- Provider and exception data never crosses into calendar diagnostics; only stable source-level codes do.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The full suite cannot collect because the pre-existing `tests/test_soak_campaign.py` constructs `CandidateReportRow` without its required `reason_detail` argument. This task did not modify the related reporting files.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

The KIS mock soak can distinguish current-day pykrx uncertainty from unavailable mock-witness evidence without weakening preflight, real-target isolation, order prohibition, or the 000660 freeze.

## Self-Check: PASSED

- Found committed implementation and test files.
- Found task commits `4274cb8` and `270b114` in git history.
