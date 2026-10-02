---
phase: 14-operator-dashboard-alerting
plan: "13"
subsystem: reporting
tags: [python, sqlite, calibration, readiness, soak, evidence, capability-boundary, pytest]
requires:
  - phase: 14-03
    provides: Pure replay DTO/canonical bytes and drift-checked immutable owner schema contracts
provides:
  - Pure calibration policy DTOs, deterministic catalog and advisory judgments
  - Saved calibration and readiness builders without replay execution or trading configuration imports
  - Three-owner saved soak reader with shared schema aliases and retained strict provenance checks
  - Independent fresh-child import, network and source-write gates for each saved report family
affects: [14-06, 14-07, web-evidence, saved-report-readers]
tech-stack:
  added: []
  patterns: [pure-evidence-contracts, identical-compatibility-reexports, independent-child-tripwires]
key-files:
  created:
    - trading_bot/calibration_evidence.py
    - tests/test_saved_calibration_evidence.py
    - tests/test_saved_soak_evidence.py
  modified:
    - trading_bot/calibration.py
    - trading_bot/calibration_reporting.py
    - trading_bot/promotion_readiness.py
    - trading_bot/soak_reporting.py
key-decisions:
  - Preserve original calibration imports as aliases to the identical pure DTOs/functions while evaluate_variants keeps the production replay implementation.
  - Import query schema declarations directly from evidence_contracts, retaining existing private schema/version names as aliases.
  - Install independent import hooks and socket/file/SQLite-write tripwires before each saved report family import; construct owner fixtures only in the parent process.
requirements-completed: [UI-02, FUT-03]
coverage:
  - id: D1
    description: Saved calibration judgments retain catalog, materiality, ranking and identical legacy exports without execution imports.
    requirement: UI-02
    verification:
      - kind: integration
        ref: tests/test_saved_calibration_evidence.py#test_pure_judgment_in_fresh_child_from_saved_rows
        status: pass
      - kind: unit
        ref: tests/test_saved_calibration_evidence.py#test_legacy_calibration_exports_are_identical_and_catalog_is_frozen
        status: pass
    human_judgment: false
  - id: D2
    description: Saved calibration and readiness preserve frozen IDs, rendered bytes, denominators and fail-closed schema/UNKNOWN checks.
    requirement: FUT-03
    verification:
      - kind: integration
        ref: tests/test_saved_calibration_evidence.py#test_saved_calibration_load_build_render_in_fresh_child
        status: pass
      - kind: integration
        ref: tests/test_saved_calibration_evidence.py#test_calibration_owner_schema_rejected_in_fresh_child
        status: pass
      - kind: integration
        ref: tests/test_saved_calibration_evidence.py#test_readiness_build_render_in_own_fresh_child
        status: pass
    human_judgment: false
  - id: D3
    description: Saved soak reads retain exact three-owner validation, provenance-separated accounting, strict link checks and read-only capability.
    requirement: UI-02
    verification:
      - kind: integration
        ref: tests/test_saved_soak_evidence.py#test_soak_load_build_render_in_fresh_child_preserves_links
        status: pass
      - kind: integration
        ref: tests/test_saved_soak_evidence.py#test_soak_owner_schema_fail_closed_in_fresh_child
        status: pass
      - kind: integration
        ref: tests/test_saved_soak_evidence.py#test_soak_missing_inode_alias_and_shared_schema_contracts
        status: pass
    human_judgment: false
duration: 9min
completed: 2026-10-02
status: complete
---

# Phase 14 Plan 13: Saved Calibration, Readiness and Soak Isolation Summary

**보정·준비도·soak 저장 보고서가 실행·거래 설정·가변 저장소를 가져오지 않으면서 기존 ID, 분모, 스키마와 UNKNOWN 링크 검증을 유지하도록 증거 경계를 분리했습니다.**

## Performance

- Started: 2026-10-02T01:16:53Z
- Implementation verification completed: 2026-10-02T01:25:11Z
- Tasks: 3/3
- Implementation/test files: 7
- No package installation, external service calls or owner database access.

## Accomplishments and Interface Contracts

- `calibration_evidence.py` contains the unchanged frozen policy, variant, source-count, metric, evaluation and judgment DTOs; materiality constants; ordered catalog; validation; and lexicographic risk/exposure/opportunity reduction. Its only project dependency is pure `replay_evidence.ReplayOutcome`.
- `calibration.py` re-exports the same class/function objects, including private candidate/risk helpers. `evaluate_variants(scenarios, variants)` retains its shipped production `run_replay_scenarios` path, one-field policy changes, identity coverage and exposure arithmetic. Existing evaluation regressions still pass.
- `ReadOnlyCalibrationEvidenceRepository(primary, soak).load(campaign_id)`, `build_calibration_report(evidence, evaluations, source_identities=...)`, and `render_calibration_report(report)` retain their signatures and canonical ID document. Missing saved evaluations raise instead of invoking evaluation. Shared primary/soak declarations replace mutable-owner and soak-reporting imports without changing validation or grade/exclusion arithmetic.
- `build_readiness_assessment(evidence, policy_snapshot=..., rollback_ack=..., kill_ack=..., manual_approval=...)` and rendering remain unchanged except for the pure canonical-bytes import. All nine checks remain mandatory; UNKNOWN, active freezes and cross-store uncertainty block even with manual approval. Historical ambiguity remains a warning with source-bound identity. This advisory DTO grants no execution or promotion authority.
- `ReadOnlySoakRepository(primary, soak, controller).load(campaign_id)`, `build_soak_report(repo, campaign_id)` and rendering retain their interfaces. `_PRIMARY_SCHEMA`, `_SOAK_SCHEMA`, `_CONTROLLER_SCHEMA`, `SCHEMA_VERSION` and owner version names alias pure contracts. Primary table subset with exact consumed columns, exact soak/controller tables/columns, independent transactions, `mode=ro`/`query_only`, distinct regular paths/inodes, parameterized campaign values and all existing attribution/release checks remain intact.
- Each family executes in its own clean `python -B` child. Before any project import, hooks deny replay/calibration execution, trading config, brokers/providers, source stores/controllers and mutation leases. Socket audit events and connection/address-resolution calls fail; file writes/mutations fail; SQLite connections require read-only URIs and use an authorizer permitting only SELECT/read/transaction/query-only/schema inspection. The child reconstructs saved metrics directly and never evaluates a scenario. Parent fixtures use temporary owner stores, including independent Phase 11 primary tables.
- Tests compare database bytes, versions, full sqlite_master inventories and logical dumps before/after both positive and rejected reads. Soak valid links credit an ambiguity resolution; forged primary intent, snapshot, controller drill and release pointers remain UNKNOWN or active freezes. Controlled, KIS-observed and synthetic denominators stay separate.

## Task Commits

1. Task 1 RED: `d8230fe` — `test(14-13): add saved calibration judgment capability gates`
2. Task 1 GREEN: `46cd536` — `feat(14-13): isolate pure calibration evidence and advisory judgments`
3. Task 2 RED: `acf7c46` — `test(14-13): add saved calibration and readiness import-call gates`
4. Task 2 GREEN: `b7e7c3d` — `feat(14-13): keep saved calibration and readiness outside execution graph`
5. Task 3 RED: `4aa881b` — `test(14-13): add isolated saved soak owner and provenance gates`
6. Task 3 GREEN: `2d5a4ea` — `feat(14-13): use pure owner schemas for saved soak reporting`

Normal Git hooks remained enabled. Main checkout/branch unchanged. No tracked file deletion.

## Verification

All commands below use `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` and complete under 60 seconds.

| Selection | Result | Duration |
|---|---|---|
| `tests/test_saved_calibration_evidence.py` before T1 | 2 failed, 2 passed; pure evidence module absent | 0.39s |
| `tests/test_saved_calibration_evidence.py tests/test_calibration.py` after T1 | 24 passed | 0.85s |
| `tests/test_saved_calibration_evidence.py` before T2 | 13 failed, 4 passed; child rejects calibration/replay execution imports | 1.31s |
| `tests/test_saved_calibration_evidence.py tests/test_calibration_reporting.py tests/test_promotion_readiness.py tests/test_report_cli.py` after T2 | 48 passed | 2.69s |
| `tests/test_saved_soak_evidence.py --tb=line` before T3 | 15 failed; child rejects mutable controller import | 1.04s |
| `tests/test_saved_soak_evidence.py tests/test_soak_reporting.py` after T3 | 44 passed | 2.62s |

Frozen vectors captured before their respective production rewiring:

- Policy catalog canonical SHA-256: `69c54b1500d054cce561f6d45bf41179a8f6083eb9e6d535f81ab7bf789c6262`.
- Calibration ID: `21fbfeb3ea35609a0cf85df1c6b9a6cd112363ffca3d2150a3964b6df7d2a19c`; TXT SHA-256: `dde4ef760eff8c04e5df394a89390880fb92cc6e6b795f01bbdfef5f23e82f79`.
- Calibration source vector: 3 eligible days, 1 normal, 1 excluded and 1 UNKNOWN cycle. Saved evaluation denominator 3, risk-first selected `BUY_CONFIDENCE_085`, risk delta -1, exposure delta -100000 KRW and opportunity delta -1.
- Readiness ID: `19cfe199f4ac5a933eea4cb674826c1fc23a64fc3f1a2e7e7f0e6b17e143c6c9`.
- Soak TXT SHA-256: `be50512fb818b1b297a6dec996785a443e9139cac0be399f0928fd8915b13453`.

`git diff --check` passed. Source scans found no placeholders, new network/auth surfaces, schema migration changes or added execution authority. Only temporary fixtures were read/written. Historical source hash/canonical procedures and CLI execution API remain unchanged; full-wave regression belongs to the parent.

## TDD Gate Compliance

Each task has a committed failing RED before passing GREEN. Pure/legacy identity, saved load/build/render, UNKNOWN, forged-link and strict schema gates retain their checks. Child processes never import test infrastructure or mutable fixture writers.

## Deviations from Plan

None. Parent explicitly owns STATE/ROADMAP/REQUIREMENTS/VALIDATION updates and phase completion; this executor preserved the existing dirty STATE and did not stage or modify shared planning state.

## Issues Encountered

The first T2 probe replaced `socket.socket` with a function, which conflicted with Python 3.14's lazy `Path.as_uri()` urllib/SSL class import. The probe now rejects socket audit events plus connection/address-resolution calls, preserving stdlib class imports while still denying network use. Fixture SQLite context managers were changed to explicit `closing` so parent connections do not leave open WAL/SHM handles; source inventories and directory comparisons remain strict. Both corrections are confined to the planned tests and all T2 gates passed afterward.

## User Setup Required

None.

## Next Phase Readiness

14-06/14-07 may reuse these saved builders after this plan's passing per-family capability gates. They must supply stored attributable evaluations and approvals, preserving unavailable/UNKNOWN when facts are absent. No schema owner, migration or source database changed.

## Self-Check: PASSED

Verified all seven implementation/test files and this SUMMARY exist. Git confirms all six RED/GREEN task commits. Required focused verification passed, `git diff --check` is clean, and no tracked files were deleted. Only the SUMMARY remains to be committed; the existing dirty STATE is preserved outside this executor's commits.
