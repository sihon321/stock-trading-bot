---
phase: 11-kis-portfolio-synchronization-intraday-exit-management
plan: 01
subsystem: portfolio-truth
tags: [kis, portfolio, sqlite, reconciliation, llm-idempotency]
requires:
  - phase: 09-kis-mock-soak-fault-drills
    provides: paginated KIS inquiry and touched-scope reconciliation contracts
  - phase: 06-audit-evidence-cycle-boundaries
    provides: append-only normalized audit evidence conventions
provides:
  - strict whole-account KIS portfolio snapshot and cancellation contracts
  - held-first daily evaluation target union
  - independently versioned portfolio and evaluation evidence schema
  - once-daily canonical LLM evaluation identity with crash-finalized HOLD
affects: [11-02-mutation-lease, 11-03-exit-manager, 11-04-intraday-orchestration]
tech-stack:
  added: []
  patterns: [frozen-domain-contracts, begin-immediate-migrations, append-only-events, unique-daily-identity]
key-files:
  created:
    - trading_bot/portfolio.py
    - trading_bot/portfolio_store.py
    - tests/test_portfolio.py
    - tests/test_portfolio_store.py
  modified:
    - trading_bot/kis_order.py
    - trading_bot/audit_models.py
key-decisions:
  - "Keep Phase 11 whole-account projection separate from the existing Phase 9 touched projection."
  - "Version Phase 11 tables through a dedicated metadata owner so they coexist with the primary audit schema."
  - "The first committed canonical input wins for a KRX date/ticker; later invocations reuse its evaluation identity."
requirements-completed: [PORT-01, PORT-02, EXIT-01, EXIT-02]
duration: 8 min
completed: 2026-09-04
status: complete
coverage:
  - deliverable: "Complete account-scoped KIS snapshot with explicit cancellation, fill, holding, and divergence facts"
    verification:
      - kind: test
        ref: "tests/test_portfolio.py"
        status: pass
      - kind: command
        ref: "python3 -m pytest -q tests/test_portfolio.py tests/test_kis_order.py tests/test_soak_reconcile.py -x"
        status: pass
    human_judgment: false
  - deliverable: "Append-only snapshot and once-daily evaluation persistence with crash recovery"
    verification:
      - kind: test
        ref: "tests/test_portfolio_store.py"
        status: pass
      - kind: command
        ref: "python3 -m pytest -q tests/test_portfolio_store.py tests/test_sqlite_audit.py -x"
        status: pass
    human_judgment: false
---

# Phase 11 Plan 01: Portfolio Truth and Evaluation Foundation Summary

**Fresh whole-account KIS normalization with explicit cancel/fill state, plus an append-only SQLite ledger that enforces one canonical LLM evaluation per KRX date and ticker**

## Performance

- **Duration:** 8 min
- **Started:** 2026-09-04T06:36:53Z
- **Completed:** 2026-09-04T06:44:39Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Added strict account-scoped portfolio contracts that distinguish complete empty truth from incomplete pages, malformed numerics, contradictory order state, and unattributable local order risk.
- Preserved every broker holding/order/fill independently of Phase 9 touched references, including original-order, cancellation, rejection, remaining, orderable, cash, and total-evaluation facts.
- Added held-first HELD/SCREENED union semantics without duplicate daily evaluation targets.
- Added independently versioned snapshot, evaluation, watch, and transition tables with immediate commits, database uniqueness, sanitized evidence, transactional rollback, and idempotent unavailable-HOLD recovery.

## Task Commits

1. **Task 1 RED: whole-account contract tests** - `eff54af`
2. **Task 1 GREEN: account portfolio normalization** - `9da6a0b`
3. **Task 2 RED: persistence contract tests** - `1caa471`
4. **Task 2 GREEN: immutable portfolio/evaluation ledger** - `b0c4af6`

## Files Created/Modified

- `trading_bot/portfolio.py` - Frozen account snapshot, order-state, divergence, and held-first target contracts.
- `trading_bot/portfolio_store.py` - Phase 11 migrations plus snapshot/evaluation append and recovery APIs.
- `trading_bot/kis_order.py` - Expanded scalar allowlist for original-order, cancellation, and rejection evidence.
- `trading_bot/audit_models.py` - Stable daily evaluation status and event vocabulary.
- `tests/test_portfolio.py` - Whole-account completeness, cancellation conflict, origin-date, and union safety matrix.
- `tests/test_portfolio_store.py` - Migration rollback, commit visibility, uniqueness, sanitization, and recovery coverage.

## Decisions Made

- Kept the Phase 11 account projection separate from `collect_broker_snapshot()` so the shipped Phase 9 touched/campaign scope remains unchanged.
- Used `portfolio_schema_metadata` rather than the audit database's global `PRAGMA user_version`, allowing both schema owners to evolve independently.
- Made the unique `(trading_date_kst, ticker)` row immutable: duplicate callers reuse the first canonical input instead of replacing it.
- Terminal evaluation events conditionally transition `STARTED` to `FINALIZED`; recovery uses the same path to append exactly one `LLM_UNAVAILABLE/HOLD`.

## Deviations from Plan

None - plan executed as specified while preserving pre-existing uncommitted KIS and Phase 9 work.

## Issues Encountered

None.

## Verification

- Task 1 focused suite: 52 passed.
- Task 2 focused suite: 20 passed.
- Combined plan suite: 72 passed.
- Full repository regression suite: 742 passed.
- Python bytecode compilation passed for all modified production modules.
- Snapshot tests retain zero POST attempts.

## Known Stubs

None.

## Self-Check: PASSED

- All four created files exist.
- All four RED/GREEN task commits exist in git history.
- No tracked files were deleted.
- Every plan verification and acceptance test exits successfully.

## Next Phase Readiness

Ready for Plan 11-02 to bind account-scoped mutation leases to these snapshot and evaluation identities.
