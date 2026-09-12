---
status: resolved
trigger: "Fix the active soak campaign safety gap where a SUBMISSION_ACCEPTED order with failed fill readback and incomplete POST_SUBMISSION reconciliation is not selected by resume and is not frozen."
created: 2026-08-11
updated: 2026-08-11
---

## Symptoms

- Expected: An accepted order whose local fill readback or POST_SUBMISSION broker query is incomplete must remain blocked from resubmission, be selected by query-only resume, and become releasable only after same-subject determinate terminal broker evidence is recorded.
- Actual: Run `30cefe5839394e2e97762a1f6aba9c3c` accepted KIS mock order `0000015678` for ticker `009830`, then POST_SUBMISSION returned UNKNOWN. Campaign `soak-20260811-20d-v3` remains ACTIVE with no active ticker freeze, and the current RESUME selector excludes the multi-event accepted-but-unreconciled intent.
- Error: `RECONCILIATION_INCOMPLETE:POST_SUBMISSION`; snapshot reason `DAILY_QUERY_UNAVAILABLE|BALANCE_COMPLETE`.
- Timeline: Reproduced on 2026-08-11 during the first designated run of the new campaign.
- Reproduction: Execute a KIS mock soak BUY that reaches `SUBMISSION_ACCEPTED`, then make the broker fill readback and POST daily-order query unavailable before a terminal local reconciliation event is recorded.

## Current Focus

hypothesis: "Confirmed: accepted-without-local-reconciliation was missing from both RESUME classification and UNKNOWN freeze creation."
test: "Self-verification is complete across POST_SUBMISSION, RESUME, strict terminal comparison release, durable no-refreeze, adjacent suites, compilation, and diff checks."
expecting: "Operator GET-only RESUME on the affected campaign either records determinate terminal broker truth and resolves the intent, or retains an active REMAINING_ORDER freeze when broker truth is still incomplete."
next_action: "resolved"

## Evidence

- timestamp: 2026-08-11T01:06:30Z; primary audit recorded `SUBMISSION_ACCEPTED` for intent `c8f58098-c87b-4617-b257-30eb8955eec4`, ticker `009830`, broker order `0000015678`, requested quantity 27.
- timestamp: 2026-08-11T01:07:57Z; POST_SUBMISSION snapshot `307a86a3-5ecb-4471-b861-6b2d9e4df01f` was INCOMPLETE with `DAILY_QUERY_UNAVAILABLE|BALANCE_COMPLETE`; comparison verdict was UNKNOWN.
- timestamp: 2026-08-11T01:07:57Z; the same balance snapshot observed holding `009830` quantity 27 at average price 36135.185, but no terminal order-row evidence was available.
- timestamp: 2026-08-11; campaign status remained ACTIVE, credited 0/20, safety latch NONE, and active freezes 0.
- timestamp: 2026-08-11; checked debug knowledge base before resuming; found no prior entry with two or more overlapping accepted/unresolved/freeze error keywords, so no known-pattern diagnosis was promoted.
- timestamp: 2026-08-11; checked git status; found substantial uncommitted changes in cli, reconciliation, KIS, reporting, models, and focused tests, so those changes are treated as the investigation baseline and will not be reverted.
- timestamp: 2026-08-11; inspected `_build_soak_runtime.reconcile`; RESUME HAVING selects only a single INTENT_CREATED history or any history containing SUBMISSION_AMBIGUOUS, so INTENT_CREATED+SUBMISSION_ATTEMPTED+SUBMISSION_ACCEPTED is excluded.
- timestamp: 2026-08-11; inspected the UNKNOWN comparison branch; `freeze_ticker` is reached only when the primary event set contains SUBMISSION_AMBIGUOUS, so a persisted UNKNOWN comparison for a certain acceptance creates no ticker freeze.
- timestamp: 2026-08-11; inspected `transition_freeze`; COMPARISON release already requires MATCHED, `remaining_order_terminal=1`, and exact campaign/ticker/order_intent subject equality, providing the needed safe release primitive.
- timestamp: 2026-08-11; common-pattern scan classifies this as an invalid state transition/dual-source-of-truth gap: the accepted primary state and UNKNOWN soak comparison exist, but unresolved classification never maps that combination into the durable freeze state.
- timestamp: 2026-08-11; the new offline regression failed before the fix at the expected assertion: accepted-only UNKNOWN reconciliation returned no active freeze.
- timestamp: 2026-08-11; after the fix, the regression passed through UNKNOWN -> REMAINING_ORDER frozen -> same-subject terminal MATCHED COMPARISON -> RELEASED, then confirmed a later unavailable RESUME did not recreate the freeze and no POST method was called.
- timestamp: 2026-08-11; focused soak CLI/reconciliation/store suite passed 49 tests; adjacent KIS broker/order/reporting suite passed 40 tests.
- timestamp: 2026-08-11; full offline suite excluding the pre-existing collection-broken tests/test_soak_campaign.py passed 665 tests; the excluded module still raises CandidateReportRow.__init__ missing reason_detail before test execution.
- timestamp: 2026-08-11; Python compileall and git diff --check passed; Ruff is not installed in the project virtual environment, so no Ruff result is claimed.
- timestamp: 2026-08-11; parametrized regression passed both initial stages: POST_SUBMISSION immediately froze the accepted-unresolved intent, and RESUME repaired the same historic missing-freeze state; both released only after terminal MATCHED comparison evidence and never called the adapter POST method.
- timestamp: 2026-08-11; final focused soak CLI/reconciliation/store suite passed 50 tests; compileall and git diff --check passed afterward.
- timestamp: 2026-08-11T01:26:02Z; operator-authorized GET-only RESUME selected accepted intent `c8f58098-c87b-4617-b257-30eb8955eec4`, persisted UNKNOWN because daily-order truth remained unavailable, and created active `REMAINING_ORDER` freeze `06074cd7-8f92-4cd5-824f-93a69ae3f372` for ticker `009830` without any POST.
- timestamp: 2026-08-11T01:26:02Z; campaign status remained ACTIVE with no safety latch, reported cross-store UNKNOWN 0, and showed `009830` among active freezes, confirming fail-closed containment of the live symptom.

## Eliminated

- hypothesis: "The order was never submitted."
  reason: "Primary audit contains SUBMISSION_ATTEMPTED and SUBMISSION_ACCEPTED with broker order ID 0000015678."

## Resolution

- root_cause: "RESUME only selected orphan INTENT_CREATED histories or histories containing SUBMISSION_AMBIGUOUS, and UNKNOWN reconciliation only created freezes for SUBMISSION_AMBIGUOUS. An acknowledged order whose fill readback never appended RECONCILED/BROKER_OBSERVED was therefore excluded from recovery and never mapped to a durable freeze, despite its accepted primary evidence and UNKNOWN soak comparison."
- fix: "Classify SUBMISSION_ACCEPTED histories without a later RECONCILED/BROKER_OBSERVED event as unresolved; skip them only after the same campaign/ticker/intent has a durable terminal MATCHED comparison; create a REMAINING_ORDER freeze on UNKNOWN; and release that freeze through the existing COMPARISON transition after terminal MATCHED evidence."
- verification: "Offline regression passes for both original POST_SUBMISSION and historic RESUME entry points: UNKNOWN creates a REMAINING_ORDER freeze, terminal same-subject MATCHED COMPARISON releases it, a later unavailable RESUME does not recreate it, and adapter POST count remains zero. Focused soak suite: 50 passed. Adjacent KIS broker/order/reporting: 40 passed. Full suite excluding the pre-existing collection-broken tests/test_soak_campaign.py: 665 passed. Python compileall and git diff --check passed; Ruff was unavailable. Operator-authorized live GET-only RESUME then reproduced incomplete broker truth and correctly created a durable REMAINING_ORDER freeze for 009830 with no POST, satisfying the human-verification checkpoint."
- files_changed: "trading_bot/cli.py, tests/test_soak_cli.py, .planning/debug/accepted-unresolved-resume.md"
