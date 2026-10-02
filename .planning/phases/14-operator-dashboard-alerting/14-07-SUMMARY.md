---
phase: 14-operator-dashboard-alerting
plan: "07"
subsystem: reporting
tags: [saved-evidence, exports, csv, artifact-ownership, capability-isolation, tdd]
requires:
  - phase: 14-03
    provides: Pure replay/backtest contracts and strict saved validation
  - phase: 14-04
    provides: Independently registered saved Shadow proof catalog
  - phase: 14-05
    provides: Registered source settings and operational artifact ownership/audit store
  - phase: 14-06
    provides: Scalar sanitization, scope DTOs and bounded read-only owner transactions
  - phase: 14-13
    provides: Pure saved soak/calibration/readiness contracts and per-family capability gates
provides:
  - Eight-family registered saved report catalog and attributable metric/detail projections
  - Consistent Korean TXT, exact numeric JSON and spreadsheet-safe CSV adapters
  - Opaque owned, sealed, no-overwrite operational artifacts and safe generation audit
affects: [14-09, 14-10, 14-11, 14-12]
tech-stack:
  added: []
  patterns: [one-sanitized-projection, registered-server-facts, exact-decimal-json, directory-descriptor-publish]
key-files:
  created: [trading_bot/web_reports.py, tests/test_web_reports.py]
  modified: []
key-decisions:
  - "Requests select only registered family/resource/result/period/formats; approval, policy, path and execution inputs are structurally absent."
  - "Saved calibration requires attributable outcomes and recorded prices; readiness approvals are registered saved facts and cannot waive current campaign/freeze evidence."
  - "Artifact ownership metadata and success audit commit together; opaque IDs contain a random namespace and a 192-bit content seal."
requirements-completed: [FUT-03, UI-01, UI-02]
coverage:
  - id: D1
    description: Eight saved report families preserve exact selections, safe available/unavailable states and immutable source evidence.
    requirement: FUT-03
    verification:
      - kind: unit
        ref: tests/test_web_reports.py#test_projection_saved_families_same_selection_and_source_bytes
        status: pass
      - kind: unit
        ref: tests/test_web_reports.py#test_projection_registered_calibration_outcomes_and_readiness_saved_facts
        status: pass
    human_judgment: false
  - id: D2
    description: TXT/JSON/CSV preserve source scope, uncertainty, source precision and declared spreadsheet import safety.
    requirement: UI-01
    verification:
      - kind: unit
        ref: tests/test_web_reports.py#test_export_three_formats_exact_precision_scope_and_unknown
        status: pass
      - kind: unit
        ref: tests/test_web_reports.py#test_csv_formula_controls_fullwidth_neutralized
        status: pass
    human_judgment: false
  - id: D3
    description: Owned operational artifacts reject conflicts, unsafe paths, links, inode replacement, tampering and partial generation without trading capabilities.
    requirement: UI-02
    verification:
      - kind: integration
        ref: tests/test_web_reports.py#test_artifact_fresh_capability_generate_load_and_sanitized_exports
        status: pass
      - kind: unit
        ref: tests/test_web_reports.py#test_artifact_root_inode_swap_and_source_hardlink_rejected
        status: pass
    human_judgment: false
duration: 20min
completed: 2026-10-02
status: complete
---

# Phase 14 Plan 07: Saved Report Catalog and Safe Artifacts Summary

**여덟 저장 리포트 가족의 출처·범위·독립 분모를 정제된 단일 조회 결과로 연결하고, 정밀한 JSON·한국어 TXT·수식 방지 CSV를 소유자별 운영 파일로 생성합니다.**

## Performance

- Recorded start: 2026-10-02T03:40:25Z
- Final implementation verification: 2026-10-02T04:00:20Z
- Tasks: 2/2
- Source/test files: 2, plus this SUMMARY
- Main checkout; no branches/worktrees, owner stores, live services, passwords or deployment accessed.

## Accomplishments and API

- `ReportRequest(family, resource_id, result_id=None, start=None, end=None, formats=('txt','json','csv'))` is frozen and rejects extras, paths, commands, policy/approval inputs, incompatible dates and excess periods. Daily requires `start`; period requires inclusive `start`/`end`, capped by configured `export_days`. Other families retain their saved window.
- `SavedReportService(settings, store=None, clock=..., shadow_proof_catalog=None, calibration_proof_catalog=(), readiness_proof_catalog=())` exposes `catalog()`, `project(request)`, `generate_report(request, actor=...)` and `load_owned_artifact(artifact_id, actor=...)`.
- Catalog covers daily/period on audit resources; replay/backtest/shadow on matching owners; soak/readiness on soak resources; calibration on soak or calibration registration. Linked audit/soak/controller resources must have the same positive account hash and target, with one registered source per required owner.
- `SavedReportProjection` carries immutable scalar rows, exact source selection, envelope, metrics, facts, labels, diagnostics and period. `metric_detail(metric_id)` returns its constituent/excluded/UNKNOWN rows. Selection identity binds sanitized facts and constituents independently of output format/query timestamp. Daily state denominators remain distinct by run kind; raw candidate count is explicitly labeled `RAW_ROW_COUNT`.
- Backtest projects saved equity, drawdown, gross/net, cost/turnover, fill/intent/expiry/baseline constituents, original window/cost profile, coverage and modeling limitations. Shadow uses the existing `SavedShadowProofCatalog` and includes captured selected/excluded inventory, observations, valid comparisons, variant/model/prompt hashes, coverage, independent counts, UNKNOWN usage, ESTIMATED costs and limits. Raw prompt, provider response and source documents are never dumped.
- `SavedCalibrationProof` and `SavedReadinessFacts` are frozen server-registration inputs, with expected hashes anchored by registration. They introduce no source schema, store, evaluator or request-supplied approval mechanism. Calibration folds saved `VariantEvaluation` outcomes, checks normal-cycle/ticker and price links, and verifies metrics using recorded facts before calling the pure report builder. Missing outcomes/prices/provenance remain named UNKNOWN. Readiness uses saved checklist facts; current saved campaign/freeze/link evidence overrides stale positive counts and saved approvals cannot waive blockers.
- `serialize_report` creates one LF-normalized Korean TXT, strict JSON with exact Decimal number tokens and `allow_nan=False`, and `csv.writer` CSV. Structured metadata is not truncated through the scalar sanitizer. CSV text detects leading whitespace/control/full-width formulas, prefixes apostrophes, preserves identity columns as text and leaves typed negative numbers numeric. The embedded Excel/LibreOffice UTF-8 import profile requires text identity columns and disabled formula evaluation, and explicitly excludes arbitrary re-save/re-import safety claims.
- Projection/export caps are 10000 rows and 10 MiB, further bounded by settings. CSV scalar export rows are independently counted; bounds reject the whole artifact without dropping rows or changing totals.
- Generation authenticates the registered operator identity, audits ATTEMPTED, serializes before publishing, and writes only the fixed operational artifact root. Directory descriptors, `O_NOFOLLOW`, private modes, inode/path checks, exclusive temporary creation, fsync and no-overwrite hard-link publication prevent source-path writes and replacement. Opaque 64-character IDs combine a random namespace and a 192-bit payload seal.
- Ownership metadata and SUCCEEDED audit commit in one operational transaction. Failure removes only files/inodes created by that invocation, retains earlier files, publishes no partial metadata and audits FAILED without raw paths/errors. Download validates owner metadata, format/name, topology, single-link regular private inode, bounded read, inode continuity and content seal; it returns `OwnedArtifact.data`, never a caller-selected path.

## Task Commits

1. T1 RED: `123cce3` — test(14-07): define saved report catalog projection and capability gates
2. T1 GREEN: `9bbb1da` — feat(14-07): project eight registered saved report families without execution
3. T2 RED: `8eec2c1` — test(14-07): define safe bounded exports and owned atomic artifact gates
4. T2 GREEN: `09a9a79` — feat(14-07): export sealed owned saved reports with bounded safe formats

Normal Git hooks enabled. No tracked files deleted. Only assigned files were staged; shared planning state was preserved.

## Verification

Commands use `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` and each completed under 60 seconds.

| Selection | Result | Duration |
|---|---|---|
| `tests/test_web_reports.py` T1 RED | 6 failed / 11 errors; module missing | 0.07s |
| `tests/test_web_reports.py` T1 GREEN | 27 passed | 9.79s |
| `tests/test_web_reports.py -k 'export or csv or artifact or bounds'` T2 RED | 19 failed; serializers/artifact API missing | 2.51s |
| Same T2 selection after implementation and safety negatives | 22 passed / 27 deselected | 4.93s |
| `tests/test_web_reports.py tests/test_saved_backtest_evidence.py tests/test_shadow_saved_capabilities.py tests/test_saved_calibration_evidence.py tests/test_saved_soak_evidence.py --tb=short` final | 90 passed | 19.15s |

The final command includes all 49 new web report tests and established saved-family capability regressions. Fresh child import/call tests reject execution/config/source-writer/provider/network capabilities. The generation child runs all six ordinary saved families and all three formats under source-write tripwires and verifies source bytes after load/download. Calibration/readiness positive vectors use registered frozen saved facts and negative missing/forged/incomplete proof states. Sources, clocks, credentials and transports are synthetic, temporary and test-owned.

`git diff --check` passed. No new network endpoints, source schema changes, auth routes, raw source reads outside registered test inputs or execution capabilities were added. File generation is the planned threat boundary and is covered by root replacement, symlink, source hardlink, content tamper, overwrite conflict, partial failure, bounded output and owner negatives. Stub scan found no placeholder behavior blocking this plan.

## TDD Gate Compliance

Both tasks have committed RED before GREEN. Historical report IDs/schema/bytes and existing family implementations were preserved.

## Deviations from Plan

None. The registered calibration/readiness fact inputs provide the required saved provenance contract without adding source storage or evaluator capability. Parent owns STATE/ROADMAP/REQUIREMENTS/VALIDATION and phase completion.

## Issues Encountered

- Existing aggregate-only replay fixtures do not contain stage constituent facts. They are truthfully unavailable with `SAVED_REPLAY_METRIC_LINK_MISMATCH`; web-positive synthetic vectors record all stage booleans instead of inventing attribution or rewriting historical evidence.
- The shared capability probe interprets relative `openat`/`link` audit names against process cwd. Its generation child aligns cwd with the already-pinned test artifact root; a separate root-inode-swap test checks the real writer's descriptor containment.
- Setup actions remain in the operational audit. Generation assertions filter `REPORT_GENERATE`, preserving the existing setup history.

## User Setup Required

None for this plan. Existing saved calibration results need registered outcome/price provenance and readiness needs registered saved checklist facts to become available. No real-money promotion, freeze release or actual operator password was performed.

## Next Phase Readiness

14-09/10/11 can consume catalog/projections, bind authenticated actor values to generation/download calls, and serve `OwnedArtifact.data` under fixed content types. Missing saved proof remains a named UNKNOWN UI state. Browser/UI acceptance and full wave regression remain with the parent orchestrator.

## Self-Check: PASSED

Verified both created source/test files and this SUMMARY exist, all four task commits exist, final 90-test command passed, diff check is clean, and no tracked files were deleted. Shared STATE/ROADMAP/REQUIREMENTS/VALIDATION were not changed by this executor.
