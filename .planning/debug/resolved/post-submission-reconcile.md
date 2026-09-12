---
status: resolved
trigger: "2026-08-10 manual KIS MOCK soak run ended with RECONCILIATION_INCOMPLETE:POST_SUBMISSION after BUY order acknowledgement"
created: 2026-08-10
updated: 2026-08-10
---

## Symptoms

- Expected: after the KIS MOCK broker accepts the 017900 BUY order, the required POST_SUBMISSION reconciliation gathers complete broker truth and the designated soak run finalizes safely.
- Actual: the order was accepted with broker order ID 0000015632, then the run exited with `RECONCILIATION_INCOMPLETE:POST_SUBMISSION`; the campaign became FAILED with safety latch `D09_BROKER_TRUTH_DISAGREEMENT` and remained at 10/20 credited days.
- Error: `RECONCILIATION_INCOMPLETE:POST_SUBMISSION`.
- Timeline: 2026-08-10 10:08-10:09 KST during a manually initiated KIS MOCK campaign run after a passing preflight.
- Reproduction: run `.venv/bin/bot soak run --campaign-id soak-20260720-20d-v1` under the observed campaign state; do not repeat because the order was already accepted and broker truth is unresolved.

## Current Focus

reasoning_checkpoint:
  hypothesis: "The synchronous POST_SUBMISSION hook runs immediately after SUBMISSION_ACCEPTED and before KISBroker records its RECONCILED event, so local evidence is acceptance-only while the independent KIS snapshot may already show a terminal fill. Strict state equality then misclassifies normal ACCEPTED-to-FILLED progression as a contradiction, while absent local fill/position/cash values keep the comparison incomplete."
  confirming_evidence:
    - "The local audit contains SUBMISSION_ACCEPTED for broker order 0000015632 with requested_qty=109 and broker_status=ACCEPTED, but no RECONCILED event."
    - "The complete POST_SUBMISSION KIS snapshot contains the same broker order 0000015632 as FILLED with filled_qty=109, remaining_qty=0, and holding 017900 quantity=109."
    - "The persisted comparison reports requested quantity MATCHED, order state ORDER_STATE_CONTRADICTION, and local filled/remaining/holding/cash dimensions UNKNOWN."
    - "execute_designated invokes post_submission synchronously from the SUBMISSION_ACCEPTED event hook; KISBroker performs fill readback and emits RECONCILED only after that hook returns."
    - "compare_broker_truth requires exact order_state equality and marks any absent local comparison value UNKNOWN; the POST gate requires all dimensions non-UNKNOWN."
  falsification_test: "A unit/integration case with local SUBMISSION_ACCEPTED and a complete same-ID FILLED broker snapshot reproduces MISMATCHED/incomplete; moving the gate after RECONCILED or defining allowed monotonic state progression with sufficient baseline evidence should prevent the false contradiction."
  fix_rationale: "diagnose only; no fix authorized"
  blind_spots: "No new KIS mutation or order retry is permitted."
next_action: "resolved"

## Evidence

- timestamp: 2026-08-10T01:09:23Z; run 9718363d48a44dcda0ba38575c016034 ended COMPLETED_WITH_ERRORS after KIS MOCK accepted 017900 BUY 109 shares with broker order ID 0000015632.
- timestamp: 2026-08-10T01:08:59Z; complete KIS snapshot a49b03d8-ee72-41c8-a121-2bdf889d3c01 observed order 0000015632 as FILLED, filled 109, remaining 0, and holding quantity 109.
- timestamp: 2026-08-10T01:08:59Z; comparison 13bbd7e0-4720-44c9-a4e7-5115d53dd2ad was MISMATCHED with codes MATCHED|ORDER_NOT_FOUND|ORDER_NOT_FOUND|ORDER_STATE_CONTRADICTION|HOLDING_UNKNOWN|AVAILABLE_CASH_UNKNOWN.
- timestamp: 2026-08-10T01:08:59Z; local evidence at comparison time had requested_qty 109 and state ACCEPTED but filled_qty, remaining_qty, holding_quantity, and available_cash were absent.
- timestamp: 2026-08-10T01:09:01Z; the subsequent broker fill-readback path raised KisOrderError, so no local RECONCILED event was appended; the audit intentionally retains only the sanitized error type.
- timestamp: 2026-08-10; regression tests prove accepted acknowledgements wait for RECONCILED evidence, ambiguous acknowledgements reconcile immediately, failed fill readback flushes exactly one query-only POST reconciliation, and a failed reconciliation attempt is never retried.
- timestamp: 2026-08-10; comparison regression proves the same broker order may advance monotonically from local ACCEPTED to broker FILLED while missing acceptance-time fill fields are recorded as broker-observed rather than fabricated contradictions.
- timestamp: 2026-08-10; focused KIS/soak suite passed 60 tests; full suite excluding the unrelated collection-broken tests/test_soak_campaign.py passed 619 tests; compileall and git diff --check passed.

## Eliminated

- hypothesis: "The KIS snapshot could not find the accepted order."
  reason: "The snapshot contains the exact broker order ID 0000015632 and shows it fully filled."
- hypothesis: "DNS failure caused this reconciliation failure."
  reason: "Both authenticated daily-order and balance pages completed, and the snapshot completeness is COMPLETE."

## Resolution

- root_cause: "POST_SUBMISSION reconciliation is triggered synchronously on SUBMISSION_ACCEPTED, before KISBroker's fill readback can append RECONCILED evidence. The comparator treats local ACCEPTED versus broker FILLED as a hard contradiction and also requires local fill, remaining, holding, and cash values that acceptance-only evidence cannot contain. A normal fast fill therefore latches D09 and returns RECONCILIATION_INCOMPLETE even though the exact broker order is present and fully filled. The later fill-readback additionally raised KisOrderError, leaving the local evidence permanently at ACCEPTED for this run."
- fix: "Added a per-intent POST submission tracker: accepted acknowledgements reconcile after local RECONCILED evidence, ambiguous acknowledgements reconcile immediately, and accepted acknowledgements left pending by fill-readback failure receive one query-only reconciliation after the production cycle. Attempts are marked before callback invocation so an exception cannot trigger an internal retry. The comparator now represents complete broker-only fields as OBSERVED and accepts monotonic ACCEPTED-to-open/partial/terminal broker progression for the exact accepted order while preserving hard mismatch when the order is absent or known values contradict."
- verification: "New ordering, flush, no-retry, fast-fill progression, and missing-order regression tests pass. Focused KIS/soak suite: 60 passed. Full suite excluding pre-existing collection failure in tests/test_soak_campaign.py: 619 passed. Python compileall and git diff --check passed. No KIS request, order, retry, cancellation, or campaign-state mutation was performed while applying the fix."
- files_changed: "trading_bot/cli.py, trading_bot/soak_reconcile.py, tests/test_soak_cli.py, tests/test_soak_reconcile.py, .planning/debug/resolved/post-submission-reconcile.md"
