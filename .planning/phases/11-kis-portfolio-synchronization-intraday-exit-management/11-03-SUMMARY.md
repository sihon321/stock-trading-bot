---
phase: 11-kis-portfolio-synchronization-intraday-exit-management
plan: 03
subsystem: daily-portfolio-orchestration
tags: [kis, portfolio, llm-idempotency, mutation-lease, sqlite]
requires:
  - phase: 11-kis-portfolio-synchronization-intraday-exit-management
    provides: complete portfolio snapshots, daily evaluation ledger, and account mutation lease
provides:
  - deterministic held-first evaluation universe with dual provenance
  - trusted held-position prompt facts outside untrusted news
  - crash-safe once-per-KRX-day LLM evaluation and signal reuse
  - current snapshot, lease, broker, risk, sizing, and pre-POST replay gates
affects: [11-04-order-boundary, 11-05-intraday-watch, 11-06-operator-evidence]
tech-stack:
  added: []
  patterns: [held-first-union, canonical-input-first, lazy-provider-construction, lease-guarded-broker]
key-files:
  created:
    - tests/test_phase11_cli.py
  modified:
    - trading_bot/portfolio.py
    - trading_bot/prompts.py
    - trading_bot/cli.py
    - tests/test_portfolio.py
    - tests/test_prompts.py
key-decisions:
  - "Sort broker holdings by ticker, then retain screener rank for screened-only targets; overlap has one identity with HELD then SCREENED provenance."
  - "Persist the exact rendered prompt bytes before constructing the provider or recording any provider attempt."
  - "Replay a finalized signal through a capability-free local adapter while current lease, broker, quote, risk, sizing, freeze, duplicate, and session gates remain authoritative."
  - "Refresh complete KIS portfolio truth after held targets and use its observed cash for screened-only sizing without crediting local SELL projections."
patterns-established:
  - "A daily provider boundary is opened only by a durable STARTED evaluation whose canonical input already exists."
  - "The broker wrapper reasserts ACTIVE account ownership immediately before every POST, including replayed signals."
requirements-completed: [PORT-01, PORT-02, EXIT-01]
coverage:
  - id: D1
    description: "Broker holdings remain visible first, with overlap deduplicated and attributable to both HELD and SCREENED."
    requirement: PORT-02
    verification:
      - kind: unit
        ref: "tests/test_portfolio.py#test_snapshot_universe_sorts_holdings_then_preserves_screen_rank_and_overlap"
        status: pass
    human_judgment: false
  - id: D2
    description: "Held prompt facts are typed and rendered outside explicitly delimited untrusted news."
    requirement: PORT-02
    verification:
      - kind: unit
        ref: "tests/test_prompts.py#test_held_position_facts_render_outside_untrusted_news_as_fixed_fields"
        status: pass
    human_judgment: false
  - id: D3
    description: "Daily LLM evaluations are unique, crash-finalized, retry-bounded, and reused without another provider construction or call."
    requirement: EXIT-01
    verification:
      - kind: integration
        ref: "tests/test_phase11_cli.py"
        status: pass
    human_judgment: false
  - id: D4
    description: "Every new or reused signal remains subordinate to fresh portfolio truth and current lease/broker execution gates."
    requirement: PORT-01
    verification:
      - kind: integration
        ref: "python3 -m pytest -q tests/test_phase11_cli.py tests/test_cli.py tests/test_execution.py -x"
        status: pass
    human_judgment: false
duration: 14 min
completed: 2026-09-04
status: complete
---

# Phase 11 Plan 03: Held-First Daily Evaluation and Safe Signal Replay Summary

**Broker-authoritative held-first evaluation with immutable daily prompt identity, crash-safe LLM finalization, and lease-guarded current-state replay**

## Performance

- **Duration:** 14 min
- **Started:** 2026-09-04T06:58:11Z
- **Completed:** 2026-09-04T07:11:57Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Built a deterministic snapshot-aware universe that evaluates every holding before screened-only candidates, deduplicates overlap, and preserves ordered HELD/SCREENED provenance.
- Added six typed held-position facts to the trusted prompt region while retaining the explicit untrusted-news boundary and ticker-local DATA_INCOMPLETE/HOLD verdicts.
- Made canonical input durable before bounded provider attempts; same-day restarts reuse one final strict signal and abandoned STARTED rows recover to one LLM_UNAVAILABLE/HOLD.
- Wired normal `bot run` composition to fresh complete KIS portfolio snapshots, lazy LLM construction, account-scoped mutation ownership, post-held cash refresh, and immediate pre-POST ownership proof.

## Task Commits

1. **Task 1 RED: held-first portfolio and prompt contract** - `c0fe46f`
2. **Task 1 GREEN: held-first universe and trusted context** - `0a8bd14`
3. **Task 2 RED: durable daily orchestration contract** - `82a9067`
4. **Task 2 GREEN: once-daily signal reuse and current gates** - `8e1ca8b`
5. **Task 2 correctness: production portfolio safety composition** - `2774cb5`

## Files Created/Modified

- `trading_bot/portfolio.py` - Evaluation universe, held context, and ticker evidence verdicts.
- `trading_bot/prompts.py` - Fixed held-position facts in the trusted prompt region.
- `trading_bot/cli.py` - Snapshot/lease composition, durable daily evaluation, lazy provider, replay gates, and post-held cash refresh.
- `tests/test_portfolio.py` - Held-only, screened-only, overlap, account-incomplete, and ticker-local evidence coverage.
- `tests/test_prompts.py` - Six-field trusted-context and hostile-news separation coverage.
- `tests/test_phase11_cli.py` - Duplicate invocation, retry, crash recovery, rollover, replay lease, and cash-refresh integration coverage.

## Decisions Made

- Used one immutable `(KRX date, ticker)` ledger row as the sole provider-call authority; later callers cannot replace its canonical input.
- Wrapped the broker at the orchestration boundary so both new and reused signals prove active lease ownership at the final POST boundary without weakening existing broker quote/duplicate checks.
- Kept held target ordering independent of provider row order and kept screened-only ordering identical to screener rank.
- Treated observed post-held KIS cash as the only screened-candidate sizing input; no local SELL proceeds are projected.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Completed production composition after injected orchestration verification**
- **Found during:** Task 2 final verification
- **Issue:** The injected path proved daily uniqueness and replay safety, but an ordinary `bot run` did not yet construct the KIS portfolio reader, lazy provider, or account lease.
- **Fix:** Added production KIS snapshot composition, delayed provider construction until after durable input checks, and acquired/recovered/released the account-scoped mutation lease.
- **Files modified:** `trading_bot/cli.py`
- **Verification:** Focused 72-test plan suite and full 762-test repository suite pass.
- **Committed in:** `2774cb5`

**Total deviations:** 1 auto-fixed (1 Rule 2)
**Impact on plan:** The fix closes a required safety boundary and adds no strategy or scheduling scope.

## Issues Encountered

- The working tree contained extensive unrelated Phase 9/debug edits, including `trading_bot/cli.py`. Plan hunks were staged interactively and committed independently; all pre-existing edits remain unstaged and preserved.

## Verification

- Task 1 focused command: 16 passed.
- Task 2 focused command: 56 passed.
- Combined plan command: 72 passed.
- Full repository regression suite: 762 passed.
- Python bytecode compilation and `git diff --check` passed.

## Known Stubs

None.

## Threat Flags

None. The new broker/LLM boundaries are the planned T-11-08, T-11-02, T-11-09, and T-11-05 mitigations.

## Self-Check: PASSED

- All six created/modified plan files exist.
- All five task and corrective commits exist in git history.
- No tracked files were deleted.
- Every task acceptance suite, plan verification command, and full regression suite exits successfully.

## User Setup Required

None beyond the existing KIS account environment required by mutable commands.

## Next Phase Readiness

Ready for Plan 11-04 to bind fresh per-ticker broker observations and SELL lifecycle evidence to this daily signal boundary.
