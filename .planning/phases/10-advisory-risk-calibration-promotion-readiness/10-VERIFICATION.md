---
phase: 10-advisory-risk-calibration-promotion-readiness
verified: 2026-10-01T03:45:37Z
status: passed
score: 24/24 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 21/24
  gaps_closed:
    - Current calibration and readiness readers accept the independently owned Phase 11 audit tables while validating all primary-owned tables, columns, and versions.
    - Readiness displays resolved historical ambiguity only after valid same-subject terminal release evidence and retains active or invalidly released freezes as blockers.
  gaps_remaining: []
  regressions: []
---

# Phase 10 Final Verification

**Goal:** Operators can make an evidence-informed, explicitly manual decision about policy changes and real-money readiness without granting validation tools execution authority.

**Status:** passed after gap closure in commit `4e70abf`. This verifies the advisory implementation, not permission to use real money or acceptance of Phase 9.

## Observable Truths

All 21 D-numbered truths in Plans 10-01, 10-02 and 10-04, and the three CLI truths in Plan 10-03 are verified (24 total).

| Truths | Count | Behavioral evidence |
| --- | --- | --- |
| D-01–D-02: short-sample warning and provenance-separated normal/abnormal denominators | 2 | Calibration rendering, excluded/broken-cycle and eligible-day denominator tests. |
| D-03–D-10: exact independent BUY/SELL confidence, position, stop/take catalogs; one-field immutable variants and preserved baseline | 8 | Exact catalog, invalid variants, production-boundary and declared-key-only counterfactual tests; read-only input byte preservation. |
| D-11–D-15: risk-first provisional judgment, visible counts/deltas, immaterial baseline retention, no profitability claim | 5 | Judgment/materiality/report identity and rendering tests. |
| CLI-1–CLI-3: credential-free calibration, identical terminal/file bytes, no execution capability | 3 | Calibration CLI tests run with both primary-only and Phase 11 shared audit schemas; constructor/AST traps and path/conflict/input-byte tests. |
| D-16–D-18: objective failure blocks despite manual acknowledgement; readiness is an evidence-linked assessment | 3 | Nine-gate reducer matrix plus real readiness CLI/database/replay-loader composition. Current short campaign remains BLOCKED. |
| D-19: active ambiguity blocks, valid resolved history is warning-only | 1 | Both comparison and ambiguity-observation terminal releases tested, plus mismatched subjects, nonterminal evidence, missing primary intent and broken pointers; readiness CLI transitions ORDERS_RESOLVED from BLOCK to PASS and displays historical warning. |
| D-20: deterministic identity bound to evidence/policy/acknowledgements | 1 | Reducer identity tests; repeated readiness CLI output matches saved bytes and changes across active/resolved evidence. |
| D-21: nine-check runbook preserves separate manual promotion boundary | 1 | Gate-list, CLI discovery and operator-runbook tests. |

## Fixes and Key Links

- `ReadOnlyCalibrationEvidenceRepository._validate` accepts independently owned extra tables only for the primary audit owner. Its primary version and exact owned-column validation remain required; soak schema validation remains exact.
- `ReadOnlySoakRepository._validate_primary` applies the same owned-table rule. It never initializes or migrates a database during inspection.
- `build_soak_report` loads frozen/released transitions and terminal proof within the existing read-only transaction. Release proof must reference the original transition, match campaign/ticker/order intent/freeze kind, be determinate and terminal, and resolve to primary evidence. Invalid releases retain the freeze and add cross-store UNKNOWN.
- `SoakReport.resolved_historical_ambiguity` counts validated ambiguity releases and feeds `readiness_command`, whose canonical assessment includes this evidence and renders warning-only historical cases.
- Active freezes, short campaigns and other objective gates still block; historical warnings never waive those gates.

## Executed Verification

| Check | Result |
| --- | --- |
| `.venv/bin/python -m pytest -q tests/test_soak_reporting.py tests/test_calibration.py tests/test_calibration_reporting.py tests/test_report_cli.py tests/test_promotion_readiness.py tests/test_operator_runbook.py tests/test_cli.py` | 116 passed in 3.06s |
| `.venv/bin/python -m pytest -q` | 828 passed; no collection exclusions |
| Current `data/audit.db` + `data/soak.db` calibration repository load | PASS |
| Current audit/soak/controller read-only report load, campaign `soak-20260902-20d-v1` | PASS: 16 credited days, zero active campaign freezes, zero cross-store UNKNOWN |
| Runtime database bytes before/after both production reads | Unchanged |
| `git diff --check` | PASS |

New regression tests exercise both independently owned schemas in one audit file, rejection of incompatible owned columns, ten valid/corrupt release cases, and real readiness CLI composition with strict replay parsing, actual SQLite readers, evaluator, reducer and output writer. The CLI test makes no live-service calls and verifies evidence bytes remain unchanged.

## Requirements Coverage

| Requirement | Status | Evidence |
| --- | --- | --- |
| CAL-01 | SATISFIED | Immutable variant domain, production replay, calibration CLI over shared audit schema. |
| CAL-02 | SATISFIED | Explicit counts/deltas/evidence grades and warnings; current evidence is readable again. |
| CAL-03 | SATISFIED | Fail-closed nine-gate reducer, active/resolved ambiguity CLI behavior, snapshot identity and manual runbook. |
| CAL-04 | SATISFIED | Read-only capability boundary, byte preservation and no trading/settings authority. |

No human verification items or unresolved Phase 10 gaps remain. The initial findings are retained in Git commit `90c455d` and resolved debug session `phase10-report-gaps.md`.

Phase 9 still requires its own 20 eligible-day external acceptance and controlled recovery proof. No runtime campaign counters, settings, credentials, orders, or real-money permissions were changed by this work.
