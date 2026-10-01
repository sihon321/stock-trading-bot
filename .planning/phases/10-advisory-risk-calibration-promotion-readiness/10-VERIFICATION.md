---
phase: 10-advisory-risk-calibration-promotion-readiness
verified: 2026-10-01T03:37:00Z
status: gaps_found
score: 21/24 must-haves verified
behavior_unverified: 0
overrides_applied: 0
gaps:
  - truth: "Operators can generate calibration and readiness assessments from the current supported audit database."
    status: failed
    reason: "Both read-only repositories require an exact whole-database table set and reject the independently owned Phase 11 portfolio tables in the current audit DB."
    artifacts:
      - path: trading_bot/calibration_reporting.py
        issue: "ReadOnlyCalibrationEvidenceRepository._validate rejects extra portfolio-owned tables."
      - path: trading_bot/soak_reporting.py
        issue: "ReadOnlySoakRepository._validate_primary rejects the same supported database; readiness depends on this reader."
    missing:
      - "Validate primary-owned tables and their versions without rejecting separately versioned supported portfolio tables. Continue rejecting incompatible owned columns and versions."
      - "Integration regressions using an audit DB initialized with both primary and Phase 11 portfolio schemas for calibration, soak status, and readiness."
  - truth: "D-19: Determinately resolved historical ambiguity remains visible as warnings in the readiness command."
    status: failed
    reason: "The reducer supports historical warnings, but readiness_command always sets resolved_historical_ambiguity=0, so operator-visible warnings cannot be produced from real historical evidence."
    artifacts:
      - path: trading_bot/report_cli.py
        issue: "readiness_command hardcodes resolved_historical_ambiguity instead of deriving it from append-only reconciled history."
    missing:
      - "Derive resolved historical ambiguity from complete same-subject terminal evidence without treating active ambiguity as resolved."
      - "Behavioral readiness CLI tests for active ambiguity BLOCKED and resolved historical ambiguity warning-only, including deterministic identity and unchanged input bytes."
---

# Phase 10 Verification

**Goal:** Operators can make an evidence-informed, explicitly manual decision about policy changes and real-money readiness without granting validation tools execution authority.

**Status:** gaps_found. The implementation has substantial passing offline coverage, but current database compatibility and historical-warning propagation prevent full goal completion.

**Scope:** Initial final verification of all four executed plans against current HEAD (`git log -1` subject: `feat(11): complete mock soak lifecycle controls`), requirements CAL-01–CAL-04, production code, tests, and operator runbook. Performed inline through the gsd-execute-phase verification path. No live service, order, configuration mutation, or campaign update was invoked.

## Observable Truths

The denominator comprises all 21 D-numbered truths in Plans 10-01, 10-02, and 10-04, plus the three Plan 10-03 CLI truths. Passing fixture/domain behavior is distinguished from failure with current production evidence.

| Truth | Status | Evidence |
| --- | --- | --- |
| D-01: Short mock samples carry INSUFFICIENT_EVIDENCE and cannot justify promotion | VERIFIED | `test_calibration_report_renders_exact_deltas_uncertainty_and_no_application`; credited-day readiness gate blocks short samples. |
| D-02: Abnormal cycles and reconciliation risks stay outside normal denominators | VERIFIED | `test_evidence_keeps_abnormal_and_broken_runs_out_of_normal_denominator`, `test_denominator_uses_eligible_days_not_decision_or_drill_rows`. |
| D-03: Confidence candidates are exactly 0.75/0.80/0.85 | VERIFIED | `test_catalog_is_exact_ordered_and_one_field_at_a_time`. |
| D-04: Multi-field variants are rejected | VERIFIED | `test_variant_rejects_mismatched_field_multiple_changes_and_bad_ids`. |
| D-05: Calibration cannot mutate settings, environment, broker, or evidence | VERIFIED | Input-byte preservation, query-only readers, and constructor/AST capability tests. |
| D-06: Position candidates are KRW 500,000/1,000,000/1,500,000 | VERIFIED | Exact catalog test. |
| D-07: Stop-loss candidates are 3/5/7 percent | VERIFIED | Exact catalog and production-boundary tests. |
| D-08: Take-profit candidates are 5/10/15 percent | VERIFIED | Exact catalog and production-boundary tests. |
| D-09: BUY and SELL confidence variants are independent | VERIFIED | Catalog uses separate policy fields; declared-key-only counterfactual test. |
| D-10: Baseline is retained and exactly one field changes | VERIFIED | `test_counterfactual_changes_only_declared_policy_key_before_production_replay`. |
| D-11: Risk-first judgment exposes exposure/opportunity/trigger differences | VERIFIED | `test_risk_first_judgment_precedes_exposure_and_opportunity_tiebreaks`. |
| D-12: Candidate selection remains provisional and advisory | VERIFIED | Judgment/report tests and mandatory advisory renderer wording. |
| D-13: Counts, baseline deltas, grades, excluded and unknown evidence are explicit | VERIFIED | Denominator and report-rendering behavioral tests. |
| D-14: Immaterial or worse differences retain baseline | VERIFIED | Materiality and materially-worse-candidate tests. |
| D-15: Calibration makes no profitability or statistical-certainty claim | VERIFIED | Renderer warning and report tests; metrics are action/exposure deltas. |
| CLI-1: Credential-free calibration produces an advisory comparison | FAILED | Fixture CLI test passes, but current supported runtime DB is rejected by the production reader (Gap 1). |
| CLI-2: Terminal/file bytes are deterministic and conflict-safe | VERIFIED | `test_calibration_terminal_file_and_inputs_are_byte_identical`, output conflict/symlink/path tests. |
| CLI-3: Calibration has no trading/settings/live-service capability | VERIFIED | `test_calibration_controller_has_no_live_or_policy_mutation_seam`. |
| D-16: Incomplete Phase 9 evidence cannot grant promotion readiness | VERIFIED | Pure reducer blocks credited days below target, safety failures, uncertainty and freezes. Current stored 16/20 sample cannot pass the credited-day gate. |
| D-17: Manual acknowledgements cannot waive objective failures | VERIFIED | Parameterized `test_each_objective_gate_blocks_and_manual_approval_cannot_waive`. |
| D-18: Operator receives evidence-linked READY/BLOCKED without real-mode activation | FAILED | Reducer behaves correctly, but readiness CLI cannot consume current runtime DB (Gap 1); bounded input failure grants no authority. |
| D-19: Active ambiguity blocks and resolved history remains warning-only | FAILED | Reducer test passes; readiness CLI hardcodes historical count to zero (Gap 2). |
| D-20: Assessment identity is deterministic and snapshot-bound | VERIFIED | Snapshot/acknowledgement identity test; canonical hash includes normalized evidence, policy, checks, and acknowledgements. |
| D-21: Nine-gate checklist and runbook keep actual promotion manual | VERIFIED | Reducer gate list, command discovery, and Phase 10 operator-runbook contract tests. |

## Artifacts and Key Links

| Artifact/link | Finding |
| --- | --- |
| `calibration.py` → `run_replay_scenarios` | Substantive immutable catalog and evaluator; behavioral test confirms only declared policy keys change before production replay. |
| `calibration_reporting.py` → primary/soak SQLite | Uses `mode=ro`, `query_only`, per-owner transactions and normalized evidence. Exact whole-database table validation is incompatible with Phase 11's independently owned tables. |
| `report_cli.calibration_command` → strict fixture loader → evaluator → report → `_deliver` | Fully wired and fixture-tested; blocked on current primary schema. |
| `promotion_readiness.py` → normalized evidence → nine checks → canonical SHA-256 | Pure reducer, no filesystem/settings/KIS/order capability. Any BLOCK/UNKNOWN produces BLOCKED. |
| `report_cli.readiness_command` → calibration and soak readers → reducer | Wired but current schema is rejected. Historical ambiguity count is not propagated. |
| `docs/operator-runbook.md` → CLI/test contracts | Documents all nine gates, current upstream blockers, snapshot invalidation and separate manual real-mode procedure. Historical-warning wording exceeds the CLI implementation. |

## Executed Verification

| Check | Result |
| --- | --- |
| `.venv/bin/python -m pytest -q tests/test_calibration.py tests/test_calibration_reporting.py tests/test_promotion_readiness.py tests/test_report_cli.py tests/test_operator_runbook.py tests/test_cli.py` | **86 passed in 2.26s** |
| `.venv/bin/python -m pytest -q` | **815 passed in 21.00s**, no exclusions or collection errors |
| Direct read-only calibration repository load, campaign `soak-20260902-20d-v1` | **FAILED:** `RuntimeError: unsupported primary audit schema tables` |
| Direct read-only soak report input used by readiness, same campaign | **FAILED:** `RuntimeError: unsupported primary audit schema tables` |

Runtime reproduction constructs only `ReadOnlyCalibrationEvidenceRepository(Path('data/audit.db'), Path('data/soak.db')).load(campaign_id)` and `build_soak_report(ReadOnlySoakRepository(Path('data/audit.db'), Path('data/soak.db'), Path('data/soak-controller.db')), campaign_id)`. Both fail before rendering or mutable collaboration.

The primary DB contains 15 additional independently owned Phase 11 tables, including `portfolio_schema_metadata`, `portfolio_snapshots`, `daily_evaluations`, `mutation_leases`, `transition_states`, and `watch_iterations`. Both readers compare the complete table set for equality against primary-only tables. No credential or broker payload was read into this report.

The historical `10-04-SUMMARY.md` collection defect in `tests/test_soak_campaign.py` no longer reproduces. Full-suite success here supersedes that historical testing limitation, but does not supersede the two current integration gaps.

## Requirement Coverage

| Requirement | Result | Reason |
| --- | --- | --- |
| CAL-01 | PARTIAL | Variant domain/fixture reporting passes; current operator calibration command fails schema validation. |
| CAL-02 | PARTIAL | Counts/deltas/warnings pass fixture tests; current runtime report is unavailable. |
| CAL-03 | PARTIAL | Fail-closed reducer and checklist pass; current readiness input fails and resolved history warnings are omitted. |
| CAL-04 | SATISFIED | Read-only capability boundary and absence of trading/settings authority are preserved, including on failure. |

All four requirement IDs in the plans are mapped to REQUIREMENTS.md. A green suite alone does not prove integration with the evolved runtime schema: existing report fixtures initialize the primary-only schema, and there is no end-to-end readiness CLI behavioral test covering these two gaps.

## Acceptance and Next Action

No human verification is needed to explain these deterministic failures. Close both gaps with implementation and behavioral integration coverage, then rerun Phase 10 verification. Suggested workflow: `$gsd-plan-phase 10 --gaps` followed by `$gsd-execute-phase 10 --gaps-only`.

Phase 9's 20-day external acceptance remains independently incomplete. Completing this advisory phase must not grant real-money authority or waive that acceptance.
