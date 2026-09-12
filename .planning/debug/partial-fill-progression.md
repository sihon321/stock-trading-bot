---
status: investigating
trigger: "Soak run latches D09_BROKER_TRUTH_DISAGREEMENT when an accepted mock order progresses from an initial partial observation to later partial or filled broker truth."
created: 2026-08-18
updated: 2026-08-18
---

## Symptoms

- Expected: broker fill progress after an initial reconciliation remains valid when quantities move monotonically toward the requested quantity and the order state advances.
- Actual: order `0000029848` for `001210` recorded local `filled=0`, `remaining=166`, then broker snapshots observed `93/73/PARTIAL` and `166/0/FILLED`; reconciliation marked the later observations as contradictions and latched D09.
- Error: `D09_BROKER_TRUTH_DISAGREEMENT` and `campaign is not active`.
- Timeline: 2026-08-18 mock soak run `soak-run-20260818-01`.
- Reproduction: compare local `PARTIAL` reconciliation evidence with a complete broker snapshot showing a later partial fill or terminal fill for the same order.

## Current Focus

- hypothesis: `compare_broker_truth` permits only local `ACCEPTED` evidence to progress, so a later broker observation after a local `PARTIAL` observation is classified as a contradiction.
- test: add regression coverage for monotonic `PARTIAL -> PARTIAL` and `PARTIAL -> FILLED` progress, preserving failures for reverse or excessive quantities.
- expecting: legitimate fill progress is `OBSERVED`/matched and does not latch D09; contradictory broker truth remains mismatched.
- next_action: implement the constrained progression rule and run focused reconciliation tests.

## Evidence

- timestamp: 2026-08-18T03:56:47Z; local `RECONCILED` event for `001210` recorded filled=0, unfilled=166, status=PARTIAL.
- timestamp: 2026-08-18T03:56:55Z; complete broker snapshot for the same order recorded filled=93, remaining=73, status=PARTIAL.
- timestamp: 2026-08-18T03:59:21Z; complete broker snapshot for the same order recorded filled=166, remaining=0, status=FILLED.
- timestamp: 2026-08-18T03:56:55Z; the comparator emitted FILLED_QTY_CONTRADICTION and REMAINING_QTY_CONTRADICTION, latching D09.
