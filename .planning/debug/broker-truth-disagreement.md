---
status: resolved
trigger: "Determine whether the 2026-08-28 soak campaign failed merely because mock orders did not fill, or because broker truth contradicted local evidence"
created: 2026-08-28
updated: 2026-08-28
---

## Symptoms

- Expected: accepted but unfilled KIS mock orders remain safely reconcilable and do not irreversibly fail the campaign merely for being unfilled.
- Actual: run `38fbc207331e47bcb146cff7e83d147a` ended `COMPLETED_WITH_ERRORS`; campaign `soak-20260818-20d-v1` latched `D09_BROKER_TRUTH_DISAGREEMENT` and stayed at 7/20 credited days.
- Error: two accepted orders (`361610` order `0000028985`, 59 shares; `004490` order `0000029033`, 14 shares) reconciled locally as `PARTIAL` with zero filled and all shares unfilled, followed by a broker-truth disagreement latch.
- Timeline: first observed during the 2026-08-28 KST soak run after an earlier abandoned run was recovered as interrupted.
- Reproduction: inspect the persisted primary-audit and soak comparison evidence for run `38fbc207331e47bcb146cff7e83d147a`; do not place or retry any order.

## Current Focus

- hypothesis: confirmed — D-09 was a false-positive semantic status mismatch (`PARTIAL` versus `NO_FILL`) for the same zero-fill quantities, not an actual quantity or order-visibility contradiction.
- test: completed read-only correlation of primary order events, soak snapshots, comparisons, and the safety-latch event for the exact run and order IDs.
- expecting: satisfied — both mismatch rows contain `MATCHED|MATCHED|MATCHED|ORDER_STATE_CONTRADICTION|...`, complete snapshots contain the expected orders as `NO_FILL`, and later fill progression compares as `MATCHED`.
- next_action: resolved — start a new immutable campaign only after operator review of the verified fix.
- reasoning_checkpoint:
  hypothesis: strict state-string equality in `compare_broker_truth` converts equivalent zero-fill representations (`PARTIAL` local, `NO_FILL` snapshot) into a campaign-failing mismatch.
  confirming_evidence:
    - primary events 52 and 58 persist `filled_qty=0`, all quantity unfilled, and `broker_status=PARTIAL`.
    - comparisons 62 and 64 persist three matched quantity codes and only `ORDER_STATE_CONTRADICTION`; their complete snapshot rows persist the corresponding order as `NO_FILL` with identical quantities.
    - later comparisons 63, 65, and 66 accept monotonic fill progression as `MATCHED`, showing there was no substantive broker/local quantity contradiction.
  falsification_test: any incident comparison showing `ORDER_NOT_FOUND`, incomplete broker truth, or requested/filled/remaining quantity contradiction would disprove the status-vocabulary-only cause; none does.
  fix_rationale: no fix is applied in diagnose-only mode; a future fix should compare semantic order states or share one normalization policy rather than require exact labels for quantity-equivalent zero-fill states.
  blind_spots: no live KIS query was performed by design; conclusions rely on the append-only persisted primary and soak evidence for this run.
- tdd_checkpoint:

## Evidence

- timestamp: 2026-08-28T12:54:42+09:00; run `38fbc207331e47bcb146cff7e83d147a` finalized `COMPLETED_WITH_ERRORS`; campaign status reported `FAILED` with safety code `D09_BROKER_TRUTH_DISAGREEMENT`.
- timestamp: 2026-08-28T12:54:42+09:00; both accepted orders had local `RECONCILED` events with `filled_qty=0`, `unfilled_qty=requested_qty`, and broker status `PARTIAL`.
- timestamp: 2026-08-28; checked `.planning/debug/knowledge-base.md`; found no entry with two or more overlapping identifiers from this incident. The sole entry concerns reserved STARTUP/RESUME sentinels and cross-store `UNKNOWN`, so it is not a qualifying known-pattern match.
- timestamp: 2026-08-28; repository search found the `BROKER_TRUTH_DISAGREEMENT` enum in `trading_bot/soak_campaign.py` and the only application latch call in `trading_bot/cli.py:732`. The run ID and both broker order IDs occur only in this debug file, implying their detailed evidence is in non-text/ignored persistence. A separate active session, `.planning/debug/partial-fill-progression.md`, reports the same D-09 family and must be tested as a candidate rather than assumed equivalent.
- timestamp: 2026-08-28; read the complete campaign service and the CLI reconciliation/latch path. For every intent in the run, the CLI appends the comparator result and irreversibly calls `record_safety_breach(... BROKER_TRUTH_DISAGREEMENT ...)` only when `comparison.verdict` is `MISMATCHED`; zero fills are not directly tested by the latch predicate.
- timestamp: 2026-08-28; the related active debug session records direct prior evidence that local `PARTIAL` `0/166` followed by broker `PARTIAL` `93/73` and `FILLED` `166/0` emitted `FILLED_QTY_CONTRADICTION` and `REMAINING_QTY_CONTRADICTION`. This supports, but does not prove for the current run, the temporal dual-source hypothesis. Common-pattern scan maps the symptom to State Management (`dual source of truth`) and Data Shape/API Contract (status/quantity semantics), not to zero-as-falsy or an async broker mutation.
- timestamp: 2026-08-28; read `trading_bot/soak_reconcile.py` completely. The current comparator explicitly accepts monotonic local `PARTIAL` progression when the later broker state is `PARTIAL` or terminal and quantities move forward, so the previously recorded partial-fill progression defect is not sufficient under current code. Separately, `_order_status` derives `NO_FILL` for `filled=0, remaining>0`, while `compare_broker_truth` otherwise requires exact `order_state` equality and emits `ORDER_STATE_CONTRADICTION` on a vocabulary mismatch.
- timestamp: 2026-08-28; read-only primary-audit query found events 52 and 58 for intents `394aef87-b590-4c08-94af-60d23d5c9614` and `f153ed57-e65b-4f0b-993e-3c62b0bf6586`: both are `RECONCILED` with their expected broker order IDs, `filled_qty=0`, `unfilled_qty=requested_qty`, and `broker_status=PARTIAL`.
- timestamp: 2026-08-28; read-only soak query found comparison 62 for order `0000028985` and comparison 64 for order `0000029033`, both `MISMATCHED` with `MATCHED|MATCHED|MATCHED|ORDER_STATE_CONTRADICTION|BROKER_OBSERVED|BROKER_OBSERVED`. Their linked complete POST_SUBMISSION snapshots record identical requested/filled/remaining quantities but status `NO_FILL`.
- timestamp: 2026-08-28; the first false mismatch at `2026-08-28T03:53:01.593585+00:00` was immediately followed by `SAFETY_FAILURE_LATCHED` with `D09_BROKER_TRUTH_DISAGREEMENT`. Subsequent comparisons observed order `0000028985` filled at `03:53:51Z` and both orders filled by PRE_FINALIZE at `03:54:51Z`; those progression comparisons were `MATCHED`, but the campaign latch was irreversible.

## Eliminated

- hypothesis: zero fills alone trigger D-09.
  evidence: the latch site tests only `comparison.verdict is MISMATCHED`; zero quantity is not a latch predicate, and all requested/filled/remaining dimensions matched in the incident rows.
  timestamp: 2026-08-28
- hypothesis: broker truth omitted either order or contradicted its quantities.
  evidence: both snapshots were COMPLETE, both order IDs were present, and comparison codes show requested, filled, and remaining quantities all MATCHED.
  timestamp: 2026-08-28
- hypothesis: the already-known `PARTIAL -> later PARTIAL/FILLED` quantity-progression defect caused this incident.
  evidence: current code permits monotonic partial-fill progression, and the later filled snapshots produced `MATCHED`; the irreversible latch was created earlier on the `PARTIAL` versus `NO_FILL` state label only.
  timestamp: 2026-08-28

## Resolution

- root_cause: `compare_broker_truth` treats local and broker order-state labels as exact immutable strings. The local KIS reconciliation persisted zero-fill accepted orders as `PARTIAL`, while `_order_status` normalized the same broker quantities (`filled=0`, `remaining=requested`) as `NO_FILL`. That vocabulary-only difference emitted `ORDER_STATE_CONTRADICTION`, made each comparison `MISMATCHED`, and the first mismatch irreversibly latched `D09_BROKER_TRUTH_DISAGREEMENT` even though all quantity dimensions agreed and later broker snapshots showed valid fills.
- fix: KIS broker evidence now emits `NO_FILL` for zero-filled orders with remaining quantity, and broker comparison treats legacy quantity-equivalent `PARTIAL`/`NO_FILL` zero-fill evidence as compatible. Monotonic progression and true quantity regressions retain their existing safety checks.
- verification: `pytest tests/test_kis_broker.py tests/test_soak_reconcile.py -q` — 31 passed; soak/CLI regression set — 119 passed; full suite — 731 passed. No broker call or order mutation was performed during verification.
- files_changed: `trading_bot/kis_broker.py`, `trading_bot/soak_reconcile.py`, `tests/test_kis_broker.py`, `tests/test_soak_reconcile.py`
