---
status: resolved
trigger: "2026-07-30 mock soak run became UNKNOWN because the pre-submit KIS order lookup raised KisOrderError"
created: 2026-07-30
updated: 2026-07-30
---

## Symptoms

- Expected: a KIS MOCK-only soak run either obtains sufficient reconciliation evidence to credit a valid run, or preserves a precise, fail-closed terminal record without creating an unexplained UNKNOWN.
- Actual: run `7fa992110eab4c579e5d58c1bc399b5d` ended `COMPLETED_WITH_ERRORS`; 051900 has `EXECUTION_ERROR / KIS_UNAVAILABLE` and its reconciliation comparison is UNKNOWN.
- Error: `KisOrderError` occurs after `INTENT_CREATED` and before `DUPLICATE_CHECKED`; no order POST was attempted.
- Timeline: first observed during the 2026-07-30 09:32 KST mock soak run.
- Reproduction: execute the permitted mock-only soak run when the query-before-POST KIS daily-order lookup is unavailable.

## Current Focus

- hypothesis: the pre-submit duplicate lookup leaves a new order intent in a state that terminal reconciliation cannot classify safely when KIS availability fails.
- next_action: isolate the lookup failure path with a regression test and determine the correct fail-closed accounting behavior.

## Evidence

- timestamp: 2026-07-30T09:33:07+09:00; comparison `6a58c2e3-83aa-490a-a68d-bf41bfd78b01` records `ORDER_NOT_FOUND|ORDER_STATE_UNKNOWN|HOLDING_UNKNOWN|AVAILABLE_CASH_UNKNOWN` for the 051900 intent.

## Resolution

- root_cause: `KisOrderAdapter`'s ordinary order-query methods used quote-style parameters and the generic `output` response key. KIS domestic order and balance queries require the account parameters and return their respective `output1` and `output2` fields. The live recheck then identified a second parser defect: textual order-status fields such as `ord_stat_name` matched the overly broad numeric-field heuristic, causing a valid KIS response to be rejected as unavailable. A third defect allowed a post-submission reconciliation failure raised from the order-event hook to leave the mutable run RUNNING. Finally, `soak resume` selected only orphan `INTENT_CREATED` intents and skipped `SUBMISSION_AMBIGUOUS` intents, so it could not create their required ticker freezes.
- fix: pass the broker account through all daily-order, balance, and fill-read paths; send the documented order-query parameters; parse `output1` / `output2` (including list-form balance summaries); validate balance availability before permitting a new order; exempt textual status/code fields from numeric parsing; defer a post-submission reconciliation error until the decision run has completed its terminal audit writes; include ambiguous submissions in read-only resume reconciliation and freeze them on unknown broker truth.
- verification: `pytest tests/test_soak_cli.py tests/test_soak_reconcile.py tests/test_soak_proof.py tests/test_kis_order.py tests/test_kis_broker.py -q` — 58 passed. A read-only KIS MOCK resume then produced durable `AMBIGUITY` freezes for both 000660 and 051900. The broader collection remains blocked by the pre-existing `CandidateReportRow.reason_detail` error in `tests/test_soak_campaign.py`.
- files_changed: `trading_bot/kis_order.py`, `trading_bot/kis_broker.py`, `tests/test_kis_order.py`, `tests/test_kis_broker.py`.
