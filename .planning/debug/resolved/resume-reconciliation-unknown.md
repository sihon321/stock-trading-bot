---
status: resolved
trigger: "Phase 09-08 recovery/reporting evidence retained three cross-store UNKNOWN references after controlled interruption and audit-failure drills"
created: 2026-07-20T13:50:20+09:00
updated: 2026-07-20T14:08:00+09:00
---

# Resume reconciliation reported as unknown

## Symptoms

- expected_behavior: Query-only soak recovery and controlled audit-failure recovery produce internally consistent durable evidence that the read-only report can reconcile without treating recovery sentinels as missing primary runs.
- actual_behavior: The interruption recovery completed, but its sentinel `run_id="resume"` was reported as a cross-store `UNKNOWN`; the audit-failure recovery failed closed with `RECONCILIATION_INCOMPLETE:RESUME`, and the final report retained three cross-store `UNKNOWN` references.
- error_messages: `RECONCILIATION_INCOMPLETE:RESUME`; final status `COMPLETE=2`, `INCOMPLETE=0`, `UNKNOWN=3`, cross-store `UNKNOWN=3`.
- timeline: First observed on 2026-07-20 during Phase 09 Plan 08 after the sole designated mock run completed and ten controlled drills passed.
- reproduction: For campaign `soak-20260720-20d-v1`, execute the controlled interruption and audit-failure drills, use only the documented query-only `bot soak resume` recovery path, then inspect `bot soak status`; recovery references using the `resume` sentinel appear as missing primary run links.

## Current Focus

- hypothesis: Confirmed and human-verified: campaign-scoped STARTUP/RESUME operation identifiers require snapshot-stage-aware validation rather than unconditional primary-run foreign-key validation.
- test: Human verified the corrected read-only report in the original operator workflow.
- expecting: Resolved session is archived and only the verified source, regression test, and debug artifact are committed.
- next_action: Commit this resolved session, then commit the knowledge-base entry with the GSD commit helper.
- reasoning_checkpoint:
    hypothesis: Campaign-scoped STARTUP/RESUME operation identifiers are persisted in `soak_snapshots.run_id`, but the generic reporter validator interprets them as primary audit foreign keys; therefore it overrides genuine COMPLETE/INCOMPLETE evidence with UNKNOWN.
    confirming_evidence:
      - The live five-row snapshot set maps exactly to the reported COMPLETE=2/UNKNOWN=3: only the three `startup`/`resume` sentinel rows are rejected.
      - The writer always supplies literal `startup`/`resume` for those stages, while the reader rejects any non-null ID absent from `primary.runs` without inspecting stage.
      - The incomplete RESUME row carries direct broker evidence `DAILY_AUTH_UNAVAILABLE|BALANCE_AUTH_UNAVAILABLE`, proving it should be INCOMPLETE rather than UNKNOWN.
    falsification_test: If a temporary report with matching STARTUP/RESUME sentinels already classifies by completeness, or if making validation stage-aware causes an orphan PRE_RUN snapshot to stop being UNKNOWN, the hypothesis/fix is wrong.
    fix_rationale: A snapshot-specific validator can recognize only the exact reserved operation ID for its matching campaign-scoped stage and otherwise delegate to the existing strict primary-reference validator, correcting ownership semantics without weakening run/comparison/drill integrity checks or reconciliation gates.
    blind_spots: No migration of the overloaded `run_id` column is attempted; historical rows using any campaign-scoped identifier other than the shipped lowercase stage sentinel will remain UNKNOWN by design. External KIS behavior is not retested because the fix is read-only reporting logic.
- tdd_checkpoint:

## Evidence

- timestamp: 2026-07-20T13:51:47+09:00
  checked: `.planning/debug/knowledge-base.md`
  found: No debug knowledge base exists.
  implication: There is no known-pattern candidate to prioritize; investigation proceeds from the persisted symptom evidence and common bug-pattern scan.
- timestamp: 2026-07-20T13:52:32+09:00
  checked: Project skill indexes under `.agents/skills/`
  found: The review namespace routes debugging to `gsd-debug`; no project-specific `rules/*.md` files or additional implementation constraints apply to this bug.
  implication: Continue under the active persistent GSD debug protocol.
- timestamp: 2026-07-20T13:54:11+09:00
  checked: Repository-wide fixed-string search for `resume`, `RECONCILIATION_INCOMPLETE`, cross-store links, and `UNKNOWN`
  found: `_orchestrate_soak_resume` calls `_require_soak_reconciliation(runtime, ReconciliationStage.RESUME, "resume")`; the read-only report explicitly validates soak/controller cross-IDs against primary audit rows; focused tests cover resume gating and missing-link UNKNOWN independently.
  implication: The literal call-site argument is a high-probability identity-contract mismatch and must be traced through persistence before changing behavior.
- timestamp: 2026-07-20T13:56:08+09:00
  checked: `_orchestrate_soak_start`, `_orchestrate_soak_resume`, `_build_soak_runtime.reconcile`, and `soak_reporting._valid_primary_reference`
  found: STARTUP passes `startup` and RESUME passes `resume`; `reconcile` embeds that argument in `SnapshotCampaign`, persists the resulting snapshot before evaluating completeness, and `_valid_primary_reference` rejects every non-null `run_id` absent from `primary.runs` without considering reconciliation stage.
  implication: A complete campaign-scoped startup/resume snapshot is structurally guaranteed to report cross-store UNKNOWN unless a coincidental primary run has the sentinel ID. The audit-failure gate still requires separate evidence because reporter validity does not control `_reconciliation_complete`.
- timestamp: 2026-07-20T13:58:02+09:00
  checked: Live `data/audit.db` and `data/soak.db` rows for campaign `soak-20260720-20d-v1`
  found: Primary runs contain the designated run but no `startup`/`resume` IDs. The five snapshots are STARTUP sentinel COMPLETE, PRE_RUN primary COMPLETE, PRE_FINALIZE primary COMPLETE, RESUME sentinel COMPLETE, and RESUME sentinel INCOMPLETE with reason `DAILY_AUTH_UNAVAILABLE|BALANCE_AUTH_UNAVAILABLE`. There are no comparison rows for the campaign.
  implication: The final COMPLETE=2/INCOMPLETE=0/UNKNOWN=3 is deterministically caused by cross-link validation running before completeness classification. Correct stage-aware classification would be COMPLETE=3/INCOMPLETE=1/UNKNOWN=0, while the audit-failure command should remain fail-closed.
- timestamp: 2026-07-20T13:59:41+09:00
  checked: Full focused tests and `ReconciliationStage` model
  found: Reporting tests cover a missing drill run/controller link but contain no STARTUP/RESUME snapshot contract. CLI tests verify resume ordering and fail-closed behavior but do not assert the `run_id` argument or subsequent report classification. The stage enum distinguishes STARTUP/RESUME from run-scoped PRE_RUN/POST_SUBMISSION/PRE_FINALIZE.
  implication: The regression gap is specifically stage-aware identity validation; CLI fail-closed semantics can remain unchanged.
- timestamp: 2026-07-20T14:01:22+09:00
  checked: Exact live read-only `bot soak status` and focused reporting baseline
  found: Live output reproduced `COMPLETE=2/INCOMPLETE=0/UNKNOWN=3`, `cross-store UNKNOWN=3`; all existing reporting tests passed 7/7.
  implication: The bug is reproducible without mutation and has no existing regression coverage.
- timestamp: 2026-07-20T14:02:47+09:00
  checked: New isolated stage-ownership regression test before production changes
  found: The test failed as predicted with COMPLETE=0, INCOMPLETE=0, UNKNOWN=4, and cross-store UNKNOWN=4; it expected 2/1/1 and cross-store UNKNOWN=1.
  implication: The regression directly reproduces the generic-validator defect and simultaneously proves the orphan PRE_RUN control remains distinguishable.
- timestamp: 2026-07-20T14:03:51+09:00
  checked: The same isolated regression after adding `_valid_snapshot_reference`
  found: The test passed 1/1.
  implication: Exact STARTUP/RESUME sentinels now classify by broker completeness while the orphan PRE_RUN remains fail-closed UNKNOWN.
- timestamp: 2026-07-20T14:05:07+09:00
  checked: Exact live read-only status plus focused reporting, CLI, and reconciliation suites
  found: Live output changed from 2/0/3 to COMPLETE=4, INCOMPLETE=1, UNKNOWN=0, TOTAL=5 with cross-store UNKNOWN=0; focused suites passed 34/34. The earlier predicted COMPLETE=3 was an arithmetic error: there are two run-scoped complete rows plus two campaign-scoped complete rows.
  implication: Original false UNKNOWN symptom is resolved on unchanged durable databases, genuine audit-auth incompleteness remains visible, and adjacent fail-closed behavior passes.
- timestamp: 2026-07-20T14:05:49+09:00
  checked: Worktree status, scoped diff, and whitespace validation
  found: Only the two intended code/test files plus the new debug session file are changed; `git diff --check` passes. Four regression tuple rows need formatter-compatible wrapping.
  implication: The patch is minimal and does not overlap unrelated user changes.
- timestamp: 2026-07-20T14:06:48+09:00
  checked: Full repository suite, bytecode compilation, lint availability, and final whitespace checks
  found: Full suite passed 581/581; `compileall` passed; `git diff --check` passed. Ruff is not installed in `.venv`, so its check could not run.
  implication: The fix passes all available automated regression and syntax checks; only required human workflow confirmation remains.
- timestamp: 2026-07-20T14:07:00+09:00
  checked: Human verification checkpoint
  found: The operator confirmed the original reporting issue is fixed in the real workflow.
  implication: The debug session can be marked resolved and archived without further runtime activity.
- timestamp: 2026-07-20T14:08:00+09:00
  checked: Verified source/test commit
  found: Commit `910d1f4` contains only `trading_bot/soak_reporting.py` and `tests/test_soak_reporting.py`.
  implication: The functional fix and its regression coverage are committed independently from planning artifacts.

## Eliminated

## Resolution

- root_cause: `soak_reporting._valid_primary_reference` unconditionally treats `soak_snapshots.run_id` as a foreign key to `primary.runs`, although STARTUP and RESUME persist reserved campaign-operation sentinels (`startup`, `resume`) in that field. The validator runs before completeness classification, so it masks both complete and genuinely incomplete broker evidence as cross-store UNKNOWN.
- fix: Added `_valid_snapshot_reference`, which recognizes only exact matching `startup`/STARTUP and `resume`/RESUME campaign-scoped snapshot identities and delegates every run-scoped snapshot to the existing strict primary-reference validation. Added a regression test covering complete and incomplete campaign-scoped evidence plus an orphan PRE_RUN control.
- verification: Isolated regression passed; exact live read-only report now shows COMPLETE=4/INCOMPLETE=1/UNKNOWN=0 and cross-store UNKNOWN=0 on the original five persisted snapshots; focused soak reporting/CLI/reconciliation tests pass 34/34; full repository suite passes 581/581; compileall and git diff whitespace checks pass. Ruff is unavailable in the project environment. Human verification confirmed the fix in the original operator workflow.
- files_changed: [`trading_bot/soak_reporting.py`, `tests/test_soak_reporting.py`]
