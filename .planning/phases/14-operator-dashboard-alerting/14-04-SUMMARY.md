---
phase: 14-operator-dashboard-alerting
plan: "04"
subsystem: reporting
tags: [shadow, saved-evidence, provenance, capability-isolation, tdd]
requires:
  - phase: 14-03
    provides: Pure backtest DTOs and saved ledger verification
  - phase: 14-02
    provides: Standalone capability probe and isolated operator sources
provides:
  - Registered saved Shadow inventory, action and journal proof verification without evaluation
  - Typed UNKNOWN for saved results lacking attributable inventory and action provenance
  - Pure saved load/render/write APIs with strict execution preparation retained
affects: [14-06, 14-07, 14-11, 14-12]
tech-stack:
  added: []
  patterns: [immutable proof registration, saved ledger transition arithmetic, fresh-interpreter capability tripwires]
key-files:
  created: [trading_bot/shadow_evidence.py, tests/test_saved_shadow_evidence.py, tests/test_shadow_saved_capabilities.py]
  modified: [trading_bot/shadow_runner.py, trading_bot/shadow_reporting.py, trading_bot/shadow_inputs.py, tests/test_shadow_reporting.py, tests/test_shadow_cli.py, tests/operator_fixtures.py, tests/test_operator_fixtures.py]
key-decisions:
  - "Saved v1 JSON cannot establish full inventory/pre-decision/action provenance; require independently registered proof hashes or return UNKNOWN."
  - "Keep creation proof outside serialized result identity and attach it only after strict preparation and canonical action projection."
  - "Preserve evaluator checks on preparation/runner paths; saved APIs only fold recorded facts and arithmetic."
requirements-completed: [FUT-03, UI-01, UI-02]
coverage:
  - id: D1
    description: Saved proof hashes, source/baseline/account/sampling/journal/action links reject forged evidence
    requirement: FUT-03
    verification:
      - kind: unit
        ref: tests/test_saved_shadow_evidence.py
        status: pass
    human_judgment: false
  - id: D2
    description: Saved Shadow load/render/write forbid preparation, runner, engine, providers and trading configuration
    requirement: UI-02
    verification:
      - kind: integration
        ref: tests/test_shadow_saved_capabilities.py
        status: pass
    human_judgment: false
  - id: D3
    description: Korean advisory reports preserve denominators, UNKNOWN usage and ESTIMATED costs with strict creation safeguards
    requirement: UI-01
    verification:
      - kind: unit
        ref: tests/test_shadow_reporting.py and tests/test_shadow_inputs.py
        status: pass
    human_judgment: false
duration: 15min
completed: 2026-10-02
status: complete
---

# Phase 14 Plan 04: Saved Shadow Integrity Summary

**등록된 원본 증거 해시와 저장된 원장·표본·행동·저널을 대조해 Shadow 보고서를 평가기 없이 검증하고, 출처가 부족한 자료는 명시적인 UNKNOWN으로 처리합니다.**

## Performance

- Duration: 15 minutes
- Completed: 2026-10-02T01:13:26Z
- Tasks: 2/2
- Source/test files created or modified: 10
- Main checkout; no branch/worktree changes; parent-owned dirty STATE preserved.

## Accomplishments

- `ShadowExecution` now lives in `shadow_evidence`; runner retains the same export. Registered proofs anchor original spec/run, frozen bundle/baseline/source/news/code, full unit inventory, recorded comparison actions and journal/observation hashes.
- Saved verification revalidates baseline ledger/metrics, folds original transitions to compare pre-decision cash/holdings/reservations/loss, checks cutoff-safe source rows/news, deterministic sampling/coverage and exact comparison/usage/cost metrics. It never generates missing policy actions, reruns indicators/backtests, prepares inputs or dispatches providers.
- `_checked_result`, saved load/render/write use the pure verifier. Preparation still reruns original frozen sources and rejects self-consistent fabricated snapshots; runner still checks present creation code before dispatch. Historical saved code hashes remain original values.
- A strict execution build attaches its already-proven inventory/actions as a non-serialized creation catalog for immediate writer/renderer compatibility. Deserialization drops this local fact; historical JSON alone cannot claim VERIFIED.
- Fresh child processes import/load/render/write registered evidence under import, network, process, source-SQL and filesystem tripwires without shared credential conftest. Malformed/unsupported saved evidence remains rejected/UNKNOWN; sources are byte-identical afterward.

## Task Commits

1. Task 1 RED: `faec69f` — test(14-04): define saved Shadow proof and forgery gates
2. Task 1 GREEN: `12751c1` — feat(14-04): validate registered saved Shadow provenance without evaluation
3. Task 2 RED: `93611e4` — test(14-04): forbid evaluator capabilities in saved Shadow APIs
4. Task 2 GREEN: `a34c0ae` — feat(14-04): isolate saved Shadow reporting and preserve creation safeguards

Both required RED/GREEN gates exist. RED first failed for missing `shadow_evidence`, and second failed for `FORBIDDEN_IMPORT` through the coupled reporting graph.

## Verification

All commands use temporary synthetic sources/fake providers; no owner database, KIS, live LLM, Discord, credentials or source migration was accessed.

- `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_saved_shadow_evidence.py` — 13 passed in 4.95s.
- `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_saved_shadow_evidence.py tests/test_shadow_runner.py` — 22 passed in 6.92s.
- `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_shadow_reporting.py tests/test_shadow_saved_capabilities.py tests/test_shadow_inputs.py --tb=short` — 21 passed in 8.06s.
- Final combined compatibility selection: `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_saved_shadow_evidence.py tests/test_shadow_saved_capabilities.py tests/test_shadow_reporting.py tests/test_shadow_inputs.py tests/test_shadow_runner.py tests/test_shadow_cli.py tests/test_operator_fixtures.py --tb=short` — **68 passed in 27.31s**, exit 0.
- `git diff --check` — passed. No tracked files deleted and no generated untracked files remain.

Acceptance: registered proof validates with evaluator functions patched to fail; cash/baseline/source/input/selection/coverage/metric/cost/journal rehash vectors never become VERIFIED; stored canonical identity and historical code identity survive; original preparation forgery, current-code mismatch, budget/retry/crash and bounded file-output protections remain covered. Full suite is owned by the parent at the wave boundary.

## Saved Report Service Interface

`validate_saved_shadow_result(result, proof_catalog=None)` returns `VerifiedSavedShadow(result, metrics, comparisons, status="VERIFIED")` or `SavedShadowUnavailable`; invalid/tampered evidence raises bounded `ShadowInputError`.

`SavedShadowUnavailable` is also a `ShadowInputError`, with `status="UNKNOWN"`, `code="SAVED_SHADOW_PROVENANCE_UNAVAILABLE"`, `predicates`, `spec_id` and `run_id`. Missing proof names `UNIT_INVENTORY`, `PRE_DECISION_FACTS` and `RECORDED_ACTIONS`. Saved loaders/renderers/writers raise this diagnostic, so the service can display a named unavailable resource.

Trusted resource registration supplies `SavedShadowProofCatalog((RegisteredShadowProof(spec_id=..., run_id=..., expected_hash=..., document_json=...), ...))`. The expected hash/identity must come from independent trusted immutable registration, never from an uploaded/rehashed result or proof. A proof records the full original observer inventory and the original policy-projected comparisons; arithmetic validation does not pretend these can be manufactured from missing historical facts.

`load_shadow_result(path, *, proof_catalog=None)`, `render_shadow_report(result, *, proof_catalog=None)` and `write_shadow_result(result, output, *, proof_catalog=None)` support that catalog. Serialization, schema version and result/spec hashing remain unchanged. Build-time `_creation_proof_catalog` is an ephemeral compatibility fact only; it does not get serialized or become an implicit global cache.

Test fixtures expose `OperatorSources.shadow_proof_catalog`, a saved `paths["shadow_proof"]` companion and `probe_registry()["shadow_proofs"]` containing separately trusted expected hashes/IDs/path. No new production source writes or schema migrations were added.

## Decisions Made

- v1 saved results do not contain sufficient complete inventory and action provenance; retain explicit UNKNOWN instead of deleting original integrity predicates.
- Separate immediate strict creation proof from historical saved proof registration without changing canonical artifacts.
- Keep full preparation/evaluator validation at the execution boundary and use only recorded decisions/fills on saved paths.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Existing shared writer lazily acquired trading configuration.**
- Found during: Task 2 fresh-process write probe.
- Issue: `backtest_reporting._write_evidence_bytes` imports `report_cli._validated_output_parent`, which imports credential-bearing `config`.
- Fix: Local pure Shadow no-overwrite writer retains regular/symlink/size checks, fsync, temporary cleanup and atomic link/conflict behavior; no edits to the backtest owner.
- Files: `trading_bot/shadow_reporting.py`, fresh-capability tests.
- Verification: Fresh-process saved load/render/write and existing idempotent/conflict/symlink tests pass.
- Commit: `a34c0ae`.

**2. [Rule 2 - Missing Critical] Align legacy CLI and synthetic fixtures with the explicit proof boundary.**
- Found during: Task 2 compatibility review; parent expressly expanded ownership.
- Issue: Tests formerly treated v1 JSON alone as sufficient verified evidence, although it omits full inventory/actions.
- Fix: CLI saved-report tests now expect bounded unavailable exit 2 without proof; creation/resume/retry tests use explicitly captured strict catalogs. Fixtures persist separately registered proof documents and the fixture regression passes its catalog explicitly.
- Files: `tests/test_shadow_cli.py`, `tests/operator_fixtures.py`, `tests/test_operator_fixtures.py`.
- Verification: Included in final 68-pass combined selection.
- Commit: `a34c0ae`.

No production CLI changes were needed. Its existing safe error handling reports `SAVED_SHADOW_PROVENANCE_UNAVAILABLE` and does not create an output for unsupported historical evidence. Paid command creation still writes/renders its strict local result normally.

## Issues Encountered

No unresolved blocking issues. Legacy stored result files require independent original proof registration; this intentional UNKNOWN limitation cannot be removed by rehashing or running an evaluator in the reporting process.

## User Setup Required

None for this offline implementation. No external services or paid acceptance were used.

## Next Phase Readiness

- SavedReportService can consume the explicit catalog/status interfaces above and show named UNKNOWN for unsupported historical resources.
- The **backtest shared writer still has the lazy `report_cli -> config` dependency** outside this plan. 14-07 must use pure build/render/serialization and its separately owned operational-artifact writer; do not call that shared source-oriented writer from web/observer.
- Parent owns STATE/ROADMAP/REQUIREMENTS/VALIDATION updates and full regression. Phase requirements remain subject to whole-phase verification; this summary records only the plan's contribution.
- Stub scan found no TODO/FIXME/placeholder or blocking unwired implementation. No new endpoint/auth/source database surface was introduced.

## Self-Check: PASSED

All 10 source/test files exist. `git cat-file -e <hash>^{commit}` verified all four RED/GREEN commits. Final focused suite exited 0 with 68 passing tests. SUMMARY is saved on disk and committed separately; parent planning files remain untouched.
