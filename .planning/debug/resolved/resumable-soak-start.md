---
status: resolved
trigger: "Make soak start safely resumable after an incomplete GET-only STARTUP gate so the already-created v4 campaign can complete without creating another campaign ID."
created: 2026-08-11
updated: 2026-08-11T11:57:06+09:00
---

## Symptoms

- Expected: `soak start` either completes STARTUP and controller bootstrap, or a later invocation with the exact same immutable campaign policy and identity safely retries only the GET-only STARTUP gate; drift, prior run/order evidence, or terminal campaign state must fail closed.
- Actual: `soak start` commits the ACTIVE campaign and identity receipt before STARTUP reconciliation. A bounded balance timeout then raises `RECONCILIATION_INCOMPLETE:STARTUP`, but rerunning the same campaign ID hits the unique campaign insert and cannot finish initialization.
- Error: v4 snapshot `21d178c0-6fd5-4e0e-a059-c0b2b3b5e556` is `STARTUP/INCOMPLETE` with `DAILY_COMPLETE|BALANCE_QUERY_TIMEOUT`; campaign remains ACTIVE with 0 days, no latch, no freezes, and no controller bootstrap completion.
- Timeline: Reproduced on 2026-08-11 while creating `soak-20260811-20d-v4` after fixing resume campaign scope.
- Reproduction: Invoke `soak start` with an accepted profile and inject an incomplete STARTUP broker snapshot after campaign/receipt persistence, then invoke the same start command again.

## Current Focus

reasoning_checkpoint:
  hypothesis: "The start orchestration has no create-or-validate-resume contract: `create_campaign` is insert-only and `persist_receipt` is insert-only even when an exact immutable partial initialization already exists."
  confirming_evidence:
    - "`_orchestrate_soak_start` always invokes `SoakCampaignService.start_campaign` before reconciliation."
    - "`start_campaign` delegates to an unconditional INSERT, and the identity callback delegates to another unconditional INSERT; the persisted incomplete STARTUP campaign therefore fails at its unique campaign key before a retry can query broker truth."
    - "The recorded v4 state is ACTIVE with zero days, latches, freezes, or attributed intent/order evidence and has only an INCOMPLETE STARTUP snapshot."
  falsification_test: "If an exact-policy campaign with one matching receipt and only incomplete STARTUP snapshots still cannot append a new STARTUP snapshot and bootstrap, or if any drift/mutable evidence reaches the reconciliation callback, the hypothesis or fix is wrong."
  fix_rationale: "A persistence-level create-or-validate gate can distinguish first creation from the sole safe retry state and reject every drift or mutation before external reconciliation; an idempotent exact receipt validator preserves the single append-only receipt."
  blind_spots: "Live KIS is intentionally untested; verification is offline and uses fake GET-only reconciliation. Controller bootstrap has no campaign completion marker, so a prior COMPLETE STARTUP is rejected rather than inferred resumable."
  next_action: "resolved"

## Evidence

- timestamp: 2026-08-11T02:43:48Z; v4 campaign and identity receipt were committed before STARTUP finished.
- timestamp: 2026-08-11T02:44:23Z; v4 STARTUP persisted INCOMPLETE with `DAILY_COMPLETE|BALANCE_QUERY_TIMEOUT`, and the CLI exited with `RECONCILIATION_INCOMPLETE:STARTUP`.
- timestamp: 2026-08-11; v4 remains ACTIVE with 0/20, no designated runs, no safety latch, no freezes, and one incomplete startup snapshot.
- timestamp: 2026-08-11; `_orchestrate_soak_start` unconditionally calls insert-only `start_campaign` and `persist_receipt` before the startup gate.
- timestamp: 2026-08-11T11:50:00+09:00; checked: new regression tests before implementation; found: six tests failed because `create_or_resume_campaign` did not exist; implication: the prior code reproduced the absence of any partial-start continuation contract.
- timestamp: 2026-08-11T11:55:00+09:00; checked: exact retry, policy/identity drift, missing identity, terminal/day/intent/comparison/complete-snapshot blockers; found: only the exact ACTIVE campaign with exclusively incomplete STARTUP snapshots was admitted, and campaign/receipt counts remained one; implication: unsafe reuse now fails before reconciliation while evidence remains append-only.
- timestamp: 2026-08-11T11:56:00+09:00; checked: offline orchestration with fake reconciliation and a POST callback that raises; found: first STARTUP remained incomplete, exact retry appended a complete snapshot and bootstrapped once, drift did not invoke reconciliation, and POST was never reached; implication: the continuation is GET-only and idempotent at the intended boundary.
- timestamp: 2026-08-11T11:57:00+09:00; checked: affected store/CLI/reconciliation/reporting tests; found: 79 passed in 1.86s and `git diff --check` passed; implication: adjacent reconciliation/reporting behavior remains green.
- timestamp: 2026-08-11T11:57:00+09:00; checked: broader campaign test collection; found: pre-existing dirty-worktree fixture omits newly required `CandidateReportRow.reason_detail`; implication: full campaign-module verification is blocked by unrelated user changes, not this fix.
- timestamp: 2026-08-11T02:59:20Z; operator-authorized retry of the exact v4 campaign/profile appended a COMPLETE STARTUP snapshot and returned `campaign_state=ACTIVE`; campaign and identity receipt counts both remained exactly one.
- timestamp: 2026-08-11T02:59:20Z; v4 status reported ACTIVE, 0/20, no safety latch, no active freeze, and cross-store UNKNOWN 0; no order-capable path was invoked.

## Eliminated

- hypothesis: "v4 already has mutable order activity and must be abandoned."
  reason: "It has zero designated runs, no intent attribution, no order comparison, no freeze, and only one GET-only STARTUP snapshot."

## Resolution

- root_cause: "`soak start` persisted campaign and receipt before STARTUP, but both persistence operations were insert-only. An incomplete STARTUP therefore left a safe partial campaign that the same command could never re-enter; no guard existed to distinguish that exact partial state from unsafe campaign reuse."
- fix: "Added a create-or-validate campaign path that permits only an exact pristine incomplete STARTUP retry, added an append-or-exactly-validate identity receipt path, wired soak start through both, and added offline fail-closed regression coverage."
- verification: "Affected offline suite: 79 passed in 1.87s; compileall passed; git diff --check passed. Full `test_soak_campaign.py` collection remains blocked by the pre-existing missing `reason_detail` fixture field. Live GET-only verification successfully resumed the same v4 ID, retained one campaign and one receipt, appended COMPLETE STARTUP evidence, bootstrapped, and left the campaign ACTIVE with no latch or freeze."
- files_changed: ["trading_bot/soak_store.py", "trading_bot/soak_campaign.py", "trading_bot/cli.py", "tests/test_soak_store.py", "tests/test_soak_cli.py"]
