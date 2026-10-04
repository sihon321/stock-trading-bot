---
phase: 15-unattended-scheduling-service-resilience
plan: "08"
subsystem: trading-execution
tags: [kis, sqlite, flock, submission-authority, fail-closed]
requires:
  - phase: 15-02
    provides: Registered controller topology and global restrictive-request journal
  - phase: 15-05
    provides: Authoritative market session and fresh observation contracts
  - phase: 15-06
    provides: Owned unattended activation evidence and explicit offline capability
  - phase: 15-07
    provides: Registered worker composition and account mutation bindings
provides:
  - Durable one-shot admission serialized with effective restrictive request acceptance
  - Concrete final HTTP POST entry with current controls, lease, session, freshness and evidence checks
  - Guard propagation through daily, saved, intraday, proof and designated soak roots
affects: [15-09, 15-10, 15-11, 15-12, 15-13, 15-14, phase-16]
tech-stack:
  added: []
  patterns: [independent committed journals, shared global flock across bounded transport, exact-order single-use capability]
key-files:
  created: [trading_bot/submission_authority.py]
  modified: [trading_bot/kis_broker.py, trading_bot/mock_broker.py, trading_bot/kis_order.py, trading_bot/exit_manager.py, trading_bot/cli.py, trading_bot/config.py, trading_bot/service_composition.py, trading_bot/soak_proof.py, tests/test_service_controls.py, tests/test_service_authority.py, tests/test_cli.py, tests/test_exit_manager.py, tests/test_kis_broker.py, tests/test_kis_order.py, tests/test_soak_cli.py]
key-decisions:
  - "FinalPostEntry binds one exact adapter/account/order/prepared request to a live admission flock and independently rechecks committed primary evidence immediately before HTTP POST."
  - "Token and hashkey preparation happen before the global flock; the lock spans bounded single POST and terminal evidence without an open SQLite transaction."
  - "Manual and proof submissions retain original approvals and IDs while using shared restrictive controls without requiring an unattended activation receipt."
  - "Known historical ticker freezes remain applicable without an identity receipt; only independently validated same-subject release can discharge them."
patterns-established:
  - "Production mutation requires exact concrete authority and actual mutation lease; opaque callbacks or verdict flags cannot grant final transport permission."
  - "Admission and primary attempt commits are independent; partial or UNKNOWN evidence permanently consumes the attempt rather than restoring replay permission."
requirements-completed: []
coverage:
  - id: D1
    description: Accepted restrictions and final admission are serialized across processes
    requirement: AUTO-01
    verification:
      - kind: integration
        ref: tests/test_service_controls.py#test_final_authority_spawned_control_post_ordering
        status: pass
      - kind: integration
        ref: tests/test_service_controls.py#test_final_authority_consumes_partial_unknown_intent
        status: pass
    human_judgment: false
  - id: D2
    description: Every named money-moving root shares pause BUY and kill SELL restrictions
    requirement: AUTO-02
    verification:
      - kind: integration
        ref: tests/test_service_authority.py#test_all_final_money_paths_share_effective_restrictions
        status: pass
      - kind: integration
        ref: tests/test_service_authority.py#test_actual_proof_context_preserves_ids_and_requires_no_service_receipt
        status: pass
    human_judgment: false
  - id: D3
    description: Concrete final HTTP entry denies stale or unbound mutation while preserving scoped freeze restrictions
    requirement: FUT-04
    verification:
      - kind: integration
        ref: tests/test_service_authority.py#test_actual_http_entry_after_preparation_is_guarded
        status: pass
      - kind: integration
        ref: tests/test_service_authority.py#test_historical_proof_freeze_without_identity_is_scoped_and_retained
        status: pass
      - kind: unit
        ref: tests/test_service_authority.py#test_raw_credential_capable_adapter_denies_opaque_authority_before_preparation
        status: pass
    human_judgment: false
duration: 224min
completed: 2026-10-04
status: complete
---

# Phase 15 Plan 08: Serialized Final Submission Authority Summary

**Every money-moving root now carries a durable one-shot admission through the actual KIS HTTP POST boundary, with restrictive controls and current owned evidence checked under the same global flock.**

## Performance

- **Duration:** 224 minutes elapsed, including an interrupted worker turn and authorized continuation.
- **Started:** 2026-10-04T06:08:58Z
- **Completed:** 2026-10-04T09:52:47Z
- **Tasks:** 2/2
- **Source/test files:** 16, including one new source module.

## Accomplishments

- `SubmissionAuthority.admit` commits unique admission before independently committed primary attempt evidence. It reads registered primary, soak and controller journals, actual account lease, authoritative session, fresh whole-account snapshot and quote, effective pending/applied controls, unresolved same-subject intent, campaign freeze and safety latch. Partial commit, crash and ambiguous transport remain consumed and block replay.
- `FinalPostEntry` binds the adapter, account, order, snapped price and immutable prepared request to a live retained flock. It rechecks current clock/date/session, lease, controls, committed attempt and saved safety immediately before `_client.post`. Arbitrary truth callbacks and synthetic activation verdicts cannot supply this permission. The POST is single-shot and bounded; no SQLite transaction spans transport.
- Token/hashkey preparation and market truth refresh run outside the global flock. Accepted restrictive requests and admission are ordered by the shared lock. During an earlier in-flight attempt, bounded request wait reports unavailable rather than falsely acknowledging acceptance.
- Daily new/saved BUY, manual wrappers, intraday exits, direct KIS, designated mock/soak, and original proof workflows carry the concrete guard. Missing or corrupt registered control configuration denies mutation while inquiry/reconciliation remains available. Proof submissions preserve original campaign/run/intent/submission IDs and accounting; collecting approval evidence does not require the unattended receipt it will help establish.
- PAUSE denies BUY and allows otherwise-safe held risk SELL; KILL denies both. The historical `000660` freeze is retained even without an identity receipt, while an otherwise-safe `005930` SELL remains possible. No freeze release, recall, cancellation, liquidation or promotion was performed.

## Task Commits

1. **Task 1 RED:** `bed42cf` — `test(15-08): specify serialized final order admission` (10 expected missing-module failures).
2. **Task 1 GREEN:** `a1ed05e` — `feat(15-08): serialize final POST with durable one-shot admissions` (53 controls tests; controls plus mock tests 68 passed).
3. **Task 2 RED:** `9523ad8` — `test(15-08): require final authority on all money-moving roots` (three expected failures: missing settings reference, permissive mock root, missing composition binding).
4. **Task 2 GREEN:** `a224f51` — `feat(15-08): guard every money-moving root at actual POST entry`.

All task commits used ordinary hooks on the existing main checkout. No prior commits were reset or rolled back.

## Verification

- Final relevant regression run: **243 passed in 16.27s**, covering `tests/test_service_controls.py`, `tests/test_service_authority.py`, `tests/test_kis_broker.py`, `tests/test_exit_manager.py`, `tests/test_cli.py`, `tests/test_soak_cli.py`, `tests/test_kis_order.py`, `tests/test_service_composition.py`, `tests/test_soak_proof.py`, and `tests/test_phase11_cli.py`.
- After six final boundary regressions were added, the authority suite passed **47 tests in 3.53s**. These include historical identity-less freeze preservation, safe other-ticker held SELL, raw adapter opaque authority rejection before preparation, and rejection of real, absent or opaque legacy collaborators. Across the two final runs, **249 distinct tests** were covered; unchanged suites were not redundantly rerun.
- Multi-process barriers cover restrictive request first, after primary attempt, and inside fake POST. Additional checks cover mutable-callback controls, committed attempt readback, stale clock/session/quote/lease, partial journal persistence, UNKNOWN consumption, and no open transaction during transport.
- Compilation of all nine touched source modules and `git diff --check` passed. No tracked files were deleted. Source stub scan found no TODO/FIXME/placeholder implementation preventing the plan goal.
- Checks used fake broker/provider collaborators and temporary journals. An earlier inherited soak fixture constructed its external data reader; that unintended constructor side effect was identified and replaced with an explicit fake constructor before the final regression. No live KIS, paid LLM, Discord, production database operation, service installation, or actual approval was performed.

## Files Created/Modified

- `trading_bot/submission_authority.py` — shared concrete admission, owned activation reading, final HTTP capability and proof submission context.
- `trading_bot/kis_broker.py`, `trading_bot/mock_broker.py` — guarded final mutation, attempt readback and terminal evidence.
- `trading_bot/kis_order.py` — immutable request preparation and exact actual HTTP entry seam; explicit fake-only legacy construction.
- `trading_bot/cli.py`, `trading_bot/config.py`, `trading_bot/exit_manager.py` — protected configuration reference and all capable root/exit wiring.
- `trading_bot/service_composition.py` — typed authority binding and owned unattended evidence reader.
- `trading_bot/soak_proof.py` — original proof attempt/transport wrapped in the concrete context with IDs/accounting preserved.
- `tests/test_service_controls.py`, `tests/test_service_authority.py` — process races, partial persistence, root/control matrix, proof identity, final entry and scoped freeze regressions.
- `tests/test_cli.py`, `tests/test_exit_manager.py`, `tests/test_kis_broker.py`, `tests/test_kis_order.py`, `tests/test_soak_cli.py` — explicit no-credential fixture capability and narrow signature compatibility; substantive existing assertions retained.

## Decisions Made

- Use exact concrete `SubmissionAuthority`, actual `MutationLease` and owned readers at trust boundaries. Production adapters cannot be admitted by arbitrary callback truth.
- Hold one installation-global flock across admission, independently committed attempt, final transport check, one bounded POST and terminal/UNKNOWN evidence. Cross-journal non-atomicity fails closed; a consumed admission is never restored for replay.
- Reuse both historical suffix and current suffix/product account hashes through independently bound actual account identity. Do not rewrite legacy proof identities.
- Initial unattended activation retains its conservative known-freeze rejection. Final submission checks the specific ticker independently; known unrelated ticker freeze alone does not prohibit otherwise-safe held risk reduction.
- Explicit fake-only legacy capability rejects actual token managers, actual HTTP clients, absent collaborators and opaque objects. Production default remains concrete-entry-required.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Connected the original proof transport and typed service composition.**
- **Found during:** Task 2 root inspection.
- **Issue:** The actual proof primary attempt/POST lived outside the named CLI files; a CLI-only guard could miss it or alter attribution. Production worker composition also required concrete authority propagation.
- **Fix:** Parent approved narrow ownership of `trading_bot/soak_proof.py` and `trading_bot/service_composition.py`. Added concrete proof context around original attempt/transport and used the existing typed binding to pass authority. Manual/proof gates remain independent of unattended acceptance.
- **Verification:** Original proof/composition/soak suites and full proof pause/kill identity matrix passed.
- **Committed in:** `a224f51`.

**2. [Rule 2 - Missing Critical] Refined the actual HTTP entry after token/hashkey preparation.**
- **Found during:** Task 2 final transport review.
- **Issue:** Guarding a high-level adapter call alone left preparation delay before `_client.post`; truth needed rechecking at actual network entry.
- **Fix:** Parent approved `trading_bot/kis_order.py`. Added exact-order `FinalPostEntry`, immutable prepared request and final committed-evidence checks immediately before HTTP POST; preparation moved outside the shared flock. Consumed admission remains consumed when this final check fails.
- **Verification:** Fake actual HTTP tests prove preparation outside flock, retained transport lock, zero POST after 11-second delay and raw opaque-entry rejection.
- **Committed in:** `a224f51`.

**3. [Rule 3 - Blocking] Made old fixtures explicitly represent no-credential offline authority.**
- **Found during:** Task 2 relevant legacy suites.
- **Issue:** Old fake adapters and roots implicitly relied on a permissive mutation constructor. Their absence of real credentials needed explicit provenance under the new default.
- **Fix:** Parent approved the five extra fixture files listed above. Used fake-only adapter constructors and temporary typed authority, accepted the new authority keyword, and isolated the inherited external data constructor. Real or opaque token/client collaborators are rejected.
- **Verification:** Existing substantive assertions and final negative capability tests pass.
- **Committed in:** `a224f51`.

**Extra owned files:** `trading_bot/soak_proof.py`, `trading_bot/service_composition.py`, `trading_bot/kis_order.py`, `tests/test_exit_manager.py`, `tests/test_kis_broker.py`, `tests/test_cli.py`, `tests/test_soak_cli.py`, `tests/test_kis_order.py`. No new dependencies or schema tables were introduced.

## Issues Encountered

- The worker turn was interrupted after both RED commits and Task 1 GREEN. The user authorized continuation; existing commits and 16-file Task 2 work were preserved, reviewed and completed without restart or rollback.
- Historical proof campaigns may lack identity receipts. Their known frozen ticker restrictions remain applicable conservatively; shipped same-subject release validation is required to discharge a freeze.

## TDD Gate Compliance

Both tasks have RED commits followed by GREEN commits in git history. Task 1 and Task 2 expectations failed for the intended missing behavior before their implementations. No missing RED/GREEN gate.

## User Setup Required

None for this implementation. No external setup or manual check was executed or claimed successful.

## Next Phase Readiness

- The next plan can integrate account-lease runtime scheduling using the shared concrete final authority. Parent will run the whole-wave regression before further plans.
- Actual 09-08 approvals remain absent. Original unresolved `000660` freeze remains intact. Installed Codex 0.144.6 single-shot behavior is still unproven, so production unattended activation remains closed.
- Service target remains strictly mock; original explicit manual real-money gates were not promoted. FUT-04/AUTO-01/AUTO-02 requirement completion is deferred to the final whole-phase verifier.

## Self-Check: PASSED

- All 16 source/test files exist; the new authority module is present.
- Commits `bed42cf`, `a1ed05e`, `9523ad8` and `a224f51` exist in preserved main history.
- The canonical summary is written at the plan output path. Focused verification passed; no implementation stub or unexpected tracked deletion remains.

---
*Phase: 15-unattended-scheduling-service-resilience*
*Completed: 2026-10-04*
