---
phase: 14-operator-dashboard-alerting
plan: "03"
subsystem: reporting
tags: [python, sqlite, replay, backtest, evidence, import-boundary, pytest]
requires:
  - phase: 07-deterministic-replay
    provides: Canonical replay identity and policy-path evidence
  - phase: 12-full-portfolio-backtesting-market-friction-modeling
    provides: Saved modeled ledger integrity and strict backtest reporting
provides:
  - Capability-free replay DTOs and unchanged canonical evidence identities
  - Immutable owner-specific read schema declarations with temporary migration drift gates
  - Backtest DTOs and saved ledger validation without engine or execution imports
affects: [14-04, 14-05, 14-13, web-evidence, saved-report-readers]
tech-stack:
  added: []
  patterns: [pure-evidence-contracts, compatibility-reexports, fresh-subprocess-capability-tripwires]
key-files:
  created:
    - trading_bot/evidence_contracts.py
    - trading_bot/replay_evidence.py
    - trading_bot/backtest_evidence.py
    - tests/test_evidence_contracts.py
    - tests/test_saved_backtest_evidence.py
  modified:
    - trading_bot/replay.py
    - trading_bot/reporting.py
    - trading_bot/backtest_engine.py
    - trading_bot/backtest_reporting.py
key-decisions:
  - Retain original replay/engine import names as aliases to the identical extracted DTOs and helpers.
  - Distinguish AUDIT_REPORT_SCHEMA's narrow daily-report subset from PRIMARY_REPORT_SCHEMA's existing soak-reader primary capabilities.
  - Keep Phase 11 ownership in portfolio_schema_metadata with owner phase11 and version 3, independent of primary PRAGMA user_version.
  - Include backtest_evidence in future named source-byte code hashes without altering stored artifacts or the hash procedure.
patterns-established:
  - Schema readers import immutable declarations; parent-process temporary migrators test owner drift without granting reader write capabilities.
  - Saved backtest validation folds recorded transitions and recomputes metrics without evaluation or policy execution.
requirements-completed: [UI-02, FUT-03]
coverage:
  - id: D1
    description: Replay reporting imports only pure evidence and preserves frozen canonical identity.
    requirement: UI-02
    verification:
      - kind: integration
        ref: tests/test_evidence_contracts.py#test_reporting_fresh_import_has_no_execution_or_writer_capability
        status: pass
      - kind: unit
        ref: tests/test_evidence_contracts.py#test_replay_exports_and_frozen_utf8_identity
        status: pass
    human_judgment: false
  - id: D2
    description: Owner versions and consumed schema columns match temporary migrated owners.
    verification:
      - kind: integration
        ref: tests/test_evidence_contracts.py#test_contracts_match_temporary_owner_migrations
        status: pass
      - kind: unit
        ref: tests/test_evidence_contracts.py#test_reader_rejects_schema_drift_and_keeps_shared_contract
        status: pass
    human_judgment: false
  - id: D3
    description: Backtest saved reads retain immutable IDs and strict forged-evidence rejection without evaluation capability.
    requirement: FUT-03
    verification:
      - kind: integration
        ref: tests/test_saved_backtest_evidence.py#test_saved_loader_and_renderer_have_no_evaluation_capability
        status: pass
      - kind: unit
        ref: tests/test_saved_backtest_evidence.py#test_rehashed_self_consistent_forgery_is_rejected
        status: pass
      - kind: unit
        ref: tests/test_saved_backtest_evidence.py#test_future_code_identity_covers_moved_evidence
        status: pass
    human_judgment: false
duration: 5min
completed: 2026-10-02
status: complete
---

# Phase 14 Plan 03: Pure Saved Evidence Contracts Summary

**Replay·백테스트 저장 보고서가 실행 엔진 없이 기존 ID, UTF-8 canonical bytes, 원장·비용·coverage 무결성을 검증하도록 증거 계약을 분리했습니다.**

## Performance

- Recorded start: 2026-10-02T00:25:05Z
- Verification completed: 2026-10-02T00:29:58Z
- Tasks: 2/2
- Implementation/test files: 9
- Existing pytest only; no dependency installation or external service calls.

## Accomplishments

- `replay_evidence.py` holds the original frozen DTOs, bounded exceptions/constants, canonical normalization and result identity, funnel and expectation helpers. Execution, manifest Git discovery, market construction and file writing remain in `replay.py`; compatibility exports resolve to the same objects.
- `reporting.py` imports pure replay/schema contracts. A fresh child blocks execution, brokers, providers, trading config, mutation leases and owner writers before imports and still imports reporting successfully.
- `evidence_contracts.py` defines immutable primary/soak/controller/portfolio schema capabilities. Primary audit is version 3, soak version 2, controller version 1, Phase 11 portfolio metadata version 3 under owner `phase11`. The narrow `AUDIT_REPORT_SCHEMA` retains existing report acceptance; broader `PRIMARY_REPORT_SCHEMA` matches the existing soak reader. Soak/controller declarations retain exact owner schemas; primary/portfolio capabilities use subsets.
- `backtest_evidence.py` holds unchanged `DecisionEvidence`, `BacktestRun`, and `checked_float`. `backtest_reporting.py` retains its existing strict saved ledger/corporate-action/fill-cost/source/cardinality checks and metric recomputation, importing DTOs without the engine.
- Saved backtest load/render succeeds in a fresh child with engine/execution imports blocked and evaluator calls replaced by tripwires. Historical synthetic code identity and frozen result identity remain unchanged, and saved file bytes are identical after reading.
- Source-byte hash procedure is unchanged; future `code_identity()` covers the new backtest evidence module. Replay default relevant-path coverage already includes all `trading_bot` files. Old manifests and saved hashes are never rewritten.

## Task Commits

1. Task 1 RED: `e201b4e` — `test(14-03): add replay import and owner schema drift gates`
2. Task 1 GREEN: `5b99d31` — `feat(14-03): isolate saved replay contracts and owner schema declarations`
3. Task 2 RED: `643c41f` — `test(14-03): add saved backtest capability and forgery gates`
4. Task 2 GREEN: `b446fc3` — `feat(14-03): isolate backtest evidence without weakening saved integrity`

Normal Git hooks were enabled for every commit. No branch/worktree change; no tracked file deletion.

## Verification

All commands used `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` and completed under 60 seconds.

| Selection | Result | Duration |
|---|---|---|
| `tests/test_evidence_contracts.py` before implementation | 7 failed; child rejected existing `sqlite_audit` writer import and new contracts were absent | 0.33s |
| `tests/test_evidence_contracts.py tests/test_reporting.py tests/test_replay.py` after T1 | 73 passed | 1.06s |
| `tests/test_saved_backtest_evidence.py` before T2 implementation | 3 failed, 3 passed; child rejected engine import, new DTO module absent, source coverage regression failed | 0.93s |
| `tests/test_saved_backtest_evidence.py tests/test_backtest_reporting.py` after T2 | 20 passed | 2.28s |
| `tests/test_evidence_contracts.py tests/test_saved_backtest_evidence.py tests/test_reporting.py tests/test_backtest_reporting.py tests/test_backtest_engine.py` final | 66 passed | 4.08s |

Frozen replay result ID: `9bed5e5f217b5eb53831ff55c8ac93c761300e0e219f276ba5f7c1550170dceb`.
Frozen backtest result ID with historical `f` code identity: `6cb3f5a5d90fe30f8483f9d5cdfc74671739afa18d615621de17e91198db80fb`.
Both were captured before their corresponding production extraction.

`git diff --check` passed. Stub/threat scans found no new placeholder behavior, network endpoints, schema changes, credentials or writer capability. Migration tests use in-memory stores only; saved fixtures use pytest temporary paths. No owner's database was read or written.

## TDD Gate Compliance

Both tasks have committed RED before GREEN. Negative fresh-child capability tests fail at the actual pre-existing imports, and T2 source coverage fails before the new module is included. Existing forged-evidence checks remain green throughout.

## Deviations from Plan

None. The parent owns STATE/ROADMAP/REQUIREMENTS changes and full wave regression; this executor did not mutate or commit those files. Requirement metadata lists this plan's assigned IDs and does not claim completion of the entire web phase.

## Issues Encountered

The one-time extraction helper initially rejected `frozenset(...)` and unrelated enum assignments while reading AST declarations. It was restricted to the named schema declarations and corrected before GREEN. Intermediate focused verification retained 67 existing passing tests; no runtime implementation defect or owner migration change resulted.

## User Setup Required

None for this plan. The separately pending 14-01 package verification remains independent.

## Next Phase Readiness

14-13 can alias its consumer-local schemas to these shared declarations and rewire saved soak/calibration/readiness consumers. Those consumer rewrites and early family gates remain 14-13's responsibility. Web/report readers may now consume replay/backtest evidence contracts; remaining Phase 14 work and full wave verification belong to the orchestrator.

## Self-Check: PASSED

Verified all five created implementation/test files and this SUMMARY exist. Git confirms all four RED/GREEN task commits exist. Final focused verification passed; no tracked files were deleted. Existing dirty STATE remains outside this executor's commits.
