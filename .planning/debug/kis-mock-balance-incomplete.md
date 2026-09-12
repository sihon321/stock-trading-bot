---
status: awaiting_human_verify
trigger: "KIS MOCK soak preflight persists an incomplete balance summary and leaves a cross-store UNKNOWN that blocks subsequent campaign runs"
created: 2026-08-03
updated: 2026-08-03
---

## Symptoms

- Expected: a KIS MOCK-only preflight either gathers complete balance evidence or records a fail-closed result that remains cross-store attributable and does not permanently block later eligible campaign dates without a real unresolved order.
- Actual: the 2026-07-31 preflight persisted snapshot `1f661694-faa0-4cdf-8b26-41aae2095baa` as `PRE_RUN` / `INCOMPLETE` with `DAILY_COMPLETE|BALANCE_SUMMARY_INCOMPLETE`; no primary audit run exists for its generated run ID, yielding `cross-store UNKNOWN=1`.
- Error: no order, submission, or real endpoint was invoked; the campaign status consequently fails its required `cross-store UNKNOWN == 0` gate.
- Timeline: observed from the 2026-07-31 09:30 KST automation; campaign remains ACTIVE with 6/20 credited dates and 000660 ambiguity freeze preserved.
- Reproduction: invoke the KIS MOCK-only `bot soak preflight` when the KIS balance summary cannot be normalized completely.

## Current Focus

reasoning_checkpoint:
  hypothesis: "A PRE_RUN reconciliation with no local order evidence uses a future execution run ID before run_cycle creates its primary audit row; reporting therefore classifies the snapshot as cross-store UNKNOWN even though it is a campaign-scoped read-only preflight observation."
  confirming_evidence:
    - "_orchestrate_soak_run calls PRE_RUN reconciliation before execute_designated, while run_cycle creates the primary runs row only inside execute_designated."
    - "The PRE_RUN reconciliation always persists its snapshot with the supplied run_id, and _valid_snapshot_reference requires a primary run for PRE_RUN snapshots."
    - "The recorded incomplete snapshot has no primary audit run and no order/submission was invoked."
  falsification_test: "If a no-local-evidence PRE_RUN snapshot is persisted with a dedicated campaign-scoped run identity, the report must retain INCOMPLETE completeness but report cross_store_unknown == 0; a normal PRE_RUN snapshot using an arbitrary absent primary run must remain UNKNOWN."
  fix_rationale: "Use a dedicated, fixed campaign-scoped identity only when PRE_RUN has no local intent/ticker evidence, then explicitly recognize only that exact no-ticker representation in the read-only report. This preserves fail-closed incompleteness and keeps all run-bound snapshots subject to primary-run validation."
  blind_spots: "Historic orphaned rows remain truthful UNKNOWN and are not rewritten; this correction prevents new orphans without retroactively changing evidence."
verification_plan:
  original_symptom: "A no-order PRE_RUN snapshot with incomplete balance data must remain INCOMPLETE without becoming cross-store UNKNOWN."
  regression_guards:
    - "Arbitrary PRE_RUN run IDs without primary audit rows remain cross-store UNKNOWN."
    - "PRE_RUN observations with local intent/ticker evidence retain their supplied run ID and therefore require a primary audit link."
    - "No order, cancellation, modification, retry, proof request, or freeze transition is exercised by tests."
next_action: "Have the operator run the normal KIS MOCK-only campaign preflight/run workflow when authorized and confirm that an incomplete no-order balance observation is reported as INCOMPLETE without increasing cross-store UNKNOWN."

## Evidence

- timestamp: 2026-08-03T00:32:00Z; campaign status reported reconciliation COMPLETE=34/INCOMPLETE=2/UNKNOWN=3/TOTAL=39 and cross-store UNKNOWN=1.
- timestamp: 2026-08-03T00:32:00Z; the incomplete PRE_RUN snapshot holds run ID d8f4cd79493d465392ae5c3f80a52639, absent from primary audit runs, and detail `DAILY_COMPLETE|BALANCE_SUMMARY_INCOMPLETE`.
- timestamp: 2026-08-03T00:48:00Z; `_orchestrate_soak_run` invokes PRE_RUN reconciliation before `execute_designated`, while `run_cycle` creates the primary audit `runs` row only after execution begins.
- timestamp: 2026-08-03T00:48:00Z; `_build_soak_runtime.reconcile` persists every snapshot with the caller-supplied run ID, and reporting treats PRE_RUN as run-bound, so a pre-execution snapshot with a future ID is correctly downgraded to cross-store UNKNOWN.
- timestamp: 2026-08-03T00:53:00Z; new regression test failed before the correction: a `PRE_RUN`/`INCOMPLETE` snapshot with run ID `preflight` was counted as UNKNOWN=1 and cross_store_unknown=1.
- timestamp: 2026-08-03T00:55:00Z; targeted soak reporting, CLI, and reconciliation tests passed (47 tests), including campaign-scoped incomplete preflight attribution and ordinary orphan PRE_RUN rejection.
- timestamp: 2026-08-03T00:58:00Z; offline suite excluding unrelated collection-broken `tests/test_soak_campaign.py` passed: 611 tests. The excluded module cannot collect because `CandidateReportRow` now requires `reason_detail`, a pre-existing unrelated test mismatch.
- timestamp: 2026-08-03T00:58:00Z; `git diff --check` passed. No KIS endpoints or order/cancel/modify/retry/proof paths were invoked; no freeze transition was requested.
- timestamp: 2026-08-03T01:05:00Z; regression found: treating every PRE_RUN snapshot as campaign-scoped `preflight` invalidated existing run-bound PRE_RUN snapshots and raised cross-store UNKNOWN from 1 to 12.
- timestamp: 2026-08-03T01:08:00Z; corrected `_valid_snapshot_reference` so only a no-ticker PRE_RUN with run ID `preflight` is campaign-scoped; all other PRE_RUN snapshots delegate to primary-audit validation. Focused reporting/CLI tests passed (37), and read-only status returned cross-store UNKNOWN=1 (COMPLETE=34/INCOMPLETE=2/UNKNOWN=3/TOTAL=39).

## Resolution

- root_cause: "PRE_RUN snapshots are persisted with a future execution run ID before the primary audit run exists; no-order read-only preflight evidence is therefore incorrectly represented as run-bound and fails cross-store attribution."
- fix: "No-order PRE_RUN reconciliation now uses fixed identity `preflight`; reporting accepts only that exact no-ticker PRE_RUN representation, while all other PRE_RUN snapshots require primary-audit validation."
- verification: "47 initial focused soak tests and 611 tests with the unrelated collection-broken test_soak_campaign excluded passed. After the PRE_RUN scope regression correction, 37 reporting/CLI tests passed and read-only campaign status returned cross-store UNKNOWN=1. Diff whitespace check passed."
- files_changed: "trading_bot/cli.py, trading_bot/soak_models.py, trading_bot/soak_reporting.py, tests/test_soak_cli.py, tests/test_soak_reporting.py"
