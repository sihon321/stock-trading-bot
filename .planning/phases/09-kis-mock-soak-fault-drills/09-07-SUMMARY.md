---
phase: 09-kis-mock-soak-fault-drills
plan: 07
subsystem: soak-reporting
tags: [sqlite, read-only, evidence-provenance, cli, operator-runbook]
requires:
  - phase: 09-kis-mock-soak-fault-drills
    provides: eligible-day campaign accounting, durable reconciliation/freezes, authenticated proof ambiguity, and controller-gated fault drills
provides:
  - exact-schema triple-store read-only campaign and drill projection
  - deterministic Korean rendering with independently reconciling evidence dimensions
  - live-runtime-free bot soak status command
  - mechanically tested authenticated campaign, fault, recovery, and external completion runbook
affects: [09-08-phase-verification, phase-10-promotion-evidence, operator-operations]
tech-stack:
  added: []
  patterns: [mode-ro query-only transactions, exact owner schemas, fail-closed cross-store references, provenance-separated denominators]
key-files:
  created: [trading_bot/soak_reporting.py, tests/test_soak_reporting.py]
  modified: [trading_bot/cli.py, docs/operator-runbook.md, tests/test_soak_cli.py, tests/test_operator_runbook.py]
key-decisions:
  - "Read each evidence owner in its own stable mode=ro/query_only transaction and never claim a cross-database atomic snapshot."
  - "Downgrade missing or contradictory primary/controller links to UNKNOWN instead of omitting them or preserving a persisted PASS."
  - "Keep CONTROLLED_INJECTION, KIS_OBSERVED, and SYNTHETIC drill denominators separate from eligible-day and availability accounting."
  - "Make soak status require the canonical existing triple and construct no KIS, LLM, data, or order collaborator."
requirements-completed: [SOAK-02, SOAK-03, SOAK-04]
coverage:
  - id: D1
    description: "Campaign, reconciliation, freeze, drill, availability, and permanent-safety dimensions remain independently visible and byte preserving."
    requirement: SOAK-02
    verification:
      - kind: integration
        ref: "tests/test_soak_reporting.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "Authenticated ambiguity and cross-store contradictions remain frozen/non-credit or UNKNOWN rather than becoming success."
    requirement: SOAK-03
    verification:
      - kind: integration
        ref: "tests/test_soak_reporting.py#test_missing_cross_store_link_fails_closed_as_unknown and docs/operator-runbook.md"
        status: pass
    human_judgment: false
  - id: D3
    description: "All immutable fault registry commands, recovery owners, provenance exclusions, and external gates are mechanically bound to the runbook."
    requirement: SOAK-04
    verification:
      - kind: integration
        ref: "tests/test_operator_runbook.py tests/test_soak_cli.py"
        status: pass
    human_judgment: false
duration: 10 min
completed: 2026-07-20
status: complete
---

# Phase 9 Plan 7: Soak Evidence Reporting and Operator Runbook Summary

**Exact-schema read-only reporting now exposes independently reconciling campaign, broker, freeze, and provenance evidence while a tested Korean procedure preserves the authenticated 000660 ambiguity as frozen and non-credit.**

## Performance

- **Duration:** 10 min
- **Started:** 2026-07-20T01:09:17Z
- **Completed:** 2026-07-20T01:19:28Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Added frozen campaign, reconciliation, freeze, drill, and aggregate report contracts with deterministic Korean rendering and stable English evidence codes.
- Validated three pairwise-distinct regular SQLite owners by exact user version, table set, and column set before opening one `mode=ro`/`query_only` stable transaction per store; no `ATTACH`, migrations, or writes are used.
- Resolved persisted run/ticker/order and controller links against their owning stores, downgrading missing or contradictory evidence to explicit `UNKNOWN` rather than omission or success.
- Kept designated, credited, non-credit, availability, permanent safety, reconciliation, active freeze, CONTROLLED_INJECTION, KIS_OBSERVED, and SYNTHETIC dimensions separate with reconciling denominators.
- Routed `bot soak status` through only the read-only repository, builder, and renderer, with no construction of KIS, LLM, pykrx, broker, or mutable campaign collaborators.
- Extended the Korean runbook with exact authenticated campaign order, all ten registry-derived fault commands, ambiguity/partial-fill freeze handling, controller → primary audit → soak recovery, D-22 review, and real external one-day/20-day gates.

## Task Commits

Each TDD task was committed as a failing contract followed by its passing implementation:

1. **Task 1: Strictly read-only campaign and drill report** — `5562dc8` (test), `457c560` (feat), `54971c5` (exact-schema safety fix)
2. **Task 2: Status wiring and complete Korean runbook** — `8ca8743` (test), `ec58cd0` (feat)

## Files Created/Modified

- `trading_bot/soak_reporting.py` — triple-store validation, stable read transactions, cross-ID checks, evidence projections, and Korean renderer.
- `tests/test_soak_reporting.py` — byte preservation, exact schema, denominator, provenance separation, active freeze, and orphan-link contracts.
- `trading_bot/cli.py` — live-runtime-free `bot soak status` composition.
- `docs/operator-runbook.md` — authenticated compatibility/campaign procedure, all fault commands, freeze/recovery order, external gates, and scope fences.
- `tests/test_soak_cli.py` — status isolation and report delegation contract.
- `tests/test_operator_runbook.py` — registry, command-order, recovery-owner, checkpoint, ambiguity, and prohibition contracts.

## Decisions Made

- Each SQLite owner gets an independent stable read transaction. The report validates links across the resulting observations but explicitly does not claim cross-database atomicity.
- Persisted PASS is not authoritative when its referenced controller contract, primary run, ticker, or order intent is absent or contradictory; the rendered claim becomes `UNKNOWN`.
- Controlled drills, authenticated KIS observations, and synthetic evidence always retain separate required/passed/failed/unknown denominators and never combine into one success count.
- The canonical status report fails closed when any evidence owner is missing or unsupported. It never creates the missing database as a side effect of inspection.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Enforced exact column schemas for soak and controller owners**
- **Found during:** Final Task 1 acceptance review
- **Issue:** Initial implementation validated exact primary-audit columns but only exact table sets for the soak and controller owners, leaving additive column drift undetected.
- **Fix:** Added complete canonical column sets for every soak and controller table and a regression test that rejects additive controller drift.
- **Files modified:** `trading_bot/soak_reporting.py`, `tests/test_soak_reporting.py`
- **Verification:** Focused 54-test plan suite and full 579-test repository suite pass.
- **Commit:** `54971c5`

---

**Total deviations:** 1 auto-fixed missing-critical safety issue.
**Impact on plan:** Strengthened the specified exact-schema fail-closed boundary without changing evidence, broker authority, campaign accounting, or external behavior.

## Issues Encountered

- The repository virtual environment does not include a `ruff` executable, so no package was installed or substituted. Python byte compilation and all pytest verification passed.
- The current workspace has no `data/soak-controller.db`. A live `bot soak status` check therefore exited `2` with `evidence database does not exist` and did not create it. This truthfully exposes the external controller-evidence blocker rather than weakening the triple-store contract.

## Authentication Gates

None. No KIS request, credential use, broker query, or order mutation occurred.

## Known Stubs

None. Empty collections in the implementation are transient accumulators, not UI or report placeholders.

## User Setup Required

- Before a complete live triple-store status can render, the controller store must exist as authentic Phase 9 controller evidence (normally created by a controller-gated fault drill). Do not create synthetic controller evidence to satisfy this check.
- The existing `000660` proof ambiguity remains `FROZEN` and non-credit; do not resubmit or release it without same-subject determinate terminal broker evidence.

## Next Phase Readiness

- Phase 09 verification can audit one deterministic report surface for all campaign, reconciliation, freeze, and fault dimensions without activating live dependencies.
- The operator procedure distinguishes deterministic test coverage from the remaining authenticated/elapsed-day external checkpoints.
- Phase 10 can consume separately denominated evidence without treating drill success, synthetic fixtures, or the ambiguous proof as eligible soak credit.

## Self-Check: PASSED

- All six planned files exist and commits `5562dc8`, `457c560`, `8ca8743`, `ec58cd0`, and `54971c5` are present.
- Plan verification passed: 54 tests across soak reporting, soak CLI, operator runbook, and Phase 8 reporting regression.
- Full repository regression passed: 579 tests.
- Python byte compilation passed for the package and changed tests.
- Live status against the incomplete current triple failed closed without creating or mutating the missing controller store.
- Pre-existing edits in `tests/test_market_cycle.py`, `tests/test_pykrx_adapter.py`, `trading_bot/data_source.py`, `trading_bot/pykrx_adapter.py`, and `.planning/debug/` were not staged, modified, or reverted.

---
*Phase: 09-kis-mock-soak-fault-drills*
*Completed: 2026-07-20*
