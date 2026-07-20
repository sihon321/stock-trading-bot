---
status: resolved
trigger: "bot soak status cannot run before the first drill because data/soak-controller.db is created only by the drill path"
created: 2026-07-20T11:20:12+09:00
updated: 2026-07-20T12:58:26+09:00
---

# Soak controller bootstrap ordering

## Symptoms

- expected_behavior: Starting an authenticated active SOAK campaign initializes the independent controller journal so `bot soak status` can verify all three stores before any controlled drill.
- actual_behavior: `bot soak start` creates the campaign but not `data/soak-controller.db`; the read-only status command exits 2 until a drill creates the controller, contradicting the pre-drill status gate.
- error_messages: `evidence database does not exist: data/soak-controller.db`
- timeline: Discovered while executing Phase 09 Plan 08 on 2026-07-20, after Plans 09-05 through 09-07 were complete.
- reproduction: With primary audit and soak stores present but no controller DB, start an active campaign and run `bot soak status --campaign-id <campaign_id>` before the first drill.

## Current Focus

- hypothesis: Confirmed — successful campaign start now bootstraps the canonical empty controller journal before the first read-only status check.
- test: Operator executed one explicitly authorized KIS MOCK start followed by read-only status for campaign `soak-20260720-20d-v1` and compared controller hashes before and after status.
- expecting: Campaign is ACTIVE, pre-drill status succeeds, controller schema is canonical and empty, and status does not mutate the controller file.
- next_action: Archive the human-verified debug session and commit only the resolved debug artifact.
- reasoning_checkpoint:
    hypothesis: "The missing pre-drill controller is caused by campaign start never invoking the schema initializer; status cannot compensate because it is strictly read-only, and drill initialization occurs too late."
    confirming_evidence:
      - "Static call tracing shows `build_drill_runtime` is the only pre-existing production caller of `connect_controller`; `soak_start_command` only validates its path."
      - "An isolated active-campaign reproduction raises exactly `evidence database does not exist: .../controller.db` and the read-only repository leaves the path absent."
      - "Phase 09-05's unopened-controller rule conflicts with Phase 09-08's required status-before-drill ordering."
    falsification_test: "If the unmodified successful campaign-start orchestration created a canonical controller file, or if status could read a missing controller without mutating it, this hypothesis would be false; both observations are contradicted by source and reproduction."
    fix_rationale: "A dedicated schema-only open/close bootstrap invoked by successful start supplies the missing producer at the lifecycle boundary while preserving status read-only behavior and keeping drill contract/fault capabilities exclusively in the drill composition."
    blind_spots: "No broker-facing end-to-end start will be run; verification uses injected collaborators and temporary databases, so production KIS authentication behavior remains covered only by the existing campaign-start tests."
- tdd_checkpoint:

## Evidence

- timestamp: 2026-07-20T11:22:46+09:00
  checked: `.planning/debug/knowledge-base.md`
  found: No debug knowledge base exists yet.
  implication: There is no prior known-pattern shortcut; test the initialization-order hypothesis directly.
- timestamp: 2026-07-20T11:23:19+09:00
  checked: Repository status and symbol search across CLI, controller, campaign, and tests.
  found: The only pre-existing worktree change is this untracked debug record. `connect_controller` appears in CLI runtime construction and drill runtime paths, while `soak_start_command` references the controller path without an obvious controller connection.
  implication: The source layout supports the initialization-order hypothesis, but complete call-path reading is required before confirming it.
- timestamp: 2026-07-20T11:25:43+09:00
  checked: Complete start/status/drill composition, controller migration, campaign service, reporting repository, tests, and Phase 09 lifecycle contracts.
  found: `soak_start_command` validates the controller path but never opens it; `build_drill_runtime` calls `connect_controller` only after requiring an active campaign; `ReadOnlySoakRepository` resolves all three paths with `strict=True`, opens them with SQLite `mode=ro`, and intentionally never creates/migrates. Plan 09-05 explicitly kept the controller unopened by ordinary campaign commands, while Plan 09-08 orders `bot soak status` before any drill.
  implication: The observed failure is a deterministic initialization-order contract conflict. Fixing status to create the store would violate its read-only guarantee; campaign start must own the empty bootstrap.
- timestamp: 2026-07-20T11:28:08+09:00
  checked: Isolated temporary-database reproduction with canonical primary audit and soak schemas, an active campaign, and no controller file.
  found: Before status the controller did not exist; `ReadOnlySoakRepository` raised `FileNotFoundError: evidence database does not exist: .../controller.db`; afterward the controller still did not exist.
  implication: The original issue is reliably reproduced and confirms a missing producer, not a reporting mutation or path-resolution defect.
- timestamp: 2026-07-20T11:30:25+09:00
  checked: Minimal implementation and deterministic regression coverage.
  found: Added `bootstrap_controller_journal` as a schema-only connect/close abstraction, injected it into `_SoakRuntime`, and ordered it after successful STARTUP reconciliation but before campaign status load. The regression exercises real temporary primary/soak/controller schemas, asserts all drill tables stay empty, then invokes the real read-only CLI status path and checks the controller bytes are unchanged.
  implication: The fix targets the missing lifecycle producer without moving mutation into status or exposing a fault port outside drills.
- timestamp: 2026-07-20T11:31:29+09:00
  checked: Focused pytest and requested lint availability.
  found: `tests/test_soak_cli.py`, `tests/test_soak_drills.py`, and `tests/test_soak_reporting.py` pass 48/48. `.venv/bin/ruff` is not installed, so the configured Ruff check could not execute from the project environment.
  implication: The original issue and adjacent controller/drill/reporting contracts are green; use available compile/diff checks and the full suite for remaining verification while recording the lint-tool limitation.
- timestamp: 2026-07-20T11:33:20+09:00
  checked: Full pytest, Python byte-compilation, whitespace/error diff check, final source/test diff, and worktree scope.
  found: The full suite passes 580/580 in 16.90s; changed Python files compile successfully; `git diff --check` passes; the only source/test changes are `trading_bot/cli.py`, `trading_bot/soak_controller.py`, and `tests/test_soak_cli.py`, plus this debug record. The final diff adds no controller contract preparation, commit token, fault port, campaign accounting, freeze mutation, or status write.
  implication: Self-verification is complete and regression risk is bounded; broker-facing end-to-end confirmation remains intentionally delegated to the operator.
- timestamp: 2026-07-20T11:35:45+09:00
  checked: Atomic source/test commit and post-commit worktree state.
  found: Commit `1a9e046` contains exactly the three verified source/test files. The only remaining worktree item is this untracked active debug record.
  implication: Implementation is durably committed; the debug record correctly remains active until human verification per protocol.
- timestamp: 2026-07-20T12:47:57+09:00
  checked: Approved live-verification prerequisites for campaign `soak-20260720-20d-v1` before any state-changing command.
  found: Mock-only configuration resolved to `https://openapivts.koreainvestment.com:29443`, profile `official-example-v1`, canonical paths `data/audit.db`, `data/soak.db`, and `data/soak-controller.db`, with the profile allowlisted. The primary and soak DB files exist and the controller DB remains absent. The attempted read-only campaign uniqueness inspection failed before returning rows: `sqlite3 -readonly data/soak.db` reported `Error: unable to open database file`.
  implication: The authorization required fail-closed behavior on any prerequisite failure. No `bot soak start`, authenticated GET, status command, controller bootstrap, order, drill, or Phase 09 artifact mutation was performed; live human verification remains incomplete.
- timestamp: 2026-07-20T12:53:23+09:00
  checked: Operator-approved application/Python read-only prerequisite for campaign `soak-20260720-20d-v1`.
  found: `.venv/bin/python` opened `data/audit.db` and `data/soak.db` with SQLite URI `mode=ro` and `PRAGMA query_only=ON`; query-only was 1 for both, primary user_version was 3, soak user_version was 2, total campaign count was 1, exact target campaign count was 0, the accepted fixture matched `ACCEPTED`/`KIS_OBSERVED`/`official-example-v1`/`kis-mock-compat-v1`, and `data/soak-controller.db` remained absent.
  implication: The earlier `/usr/bin/sqlite3` prerequisite failure was a CLI-specific false negative. Durable inspection proves the authorized campaign ID is absent, so exactly one campaign-start attempt is permitted.
- timestamp: 2026-07-20T12:54:20+09:00
  checked: The single authorized application start attempt for `soak-20260720-20d-v1`.
  found: `.venv/bin/bot soak start --campaign-id soak-20260720-20d-v1 --accepted-profile tests/fixtures/kis_mock/accepted-profile.json` emitted the sanitized MOCK identity receipt, then exited 2. Runtime construction attempted KRX calendar access and failed with `HTTPSConnectionPool(host='data.krx.co.kr', port=443): Max retries exceeded` caused by `NameResolutionError`; no `campaign_state=ACTIVE` success marker was emitted.
  implication: This is an external failure under the explicit no-retry boundary. No second start, application status, drill, run, proof order, order, cancel, modify, freeze mutation, or real-account endpoint may be invoked; only read-only durable-state inspection remains.
- timestamp: 2026-07-20T12:55:02+09:00
  checked: Application/Python read-only durable state immediately after the failed single start attempt.
  found: `.venv/bin/python` reopened `data/soak.db` with SQLite URI `mode=ro` and `PRAGMA query_only=ON`; soak user_version remains 2, total campaign count remains 1, and target campaign/identity-receipt/snapshot counts are all 0. `data/soak-controller.db` remains absent.
  implication: The failed start committed none of the target campaign, receipt, reconciliation snapshot, or controller-bootstrap state. The authorized mutation attempt is exhausted, application status is inapplicable because the target campaign/controller do not exist, and live verification remains incomplete.
- timestamp: 2026-07-20T12:58:26+09:00
  checked: Operator-approved bounded live verification for campaign `soak-20260720-20d-v1` after network access was restored.
  found: One KIS MOCK `bot soak start` succeeded with sanitized identity `target=mock`, `domain_class=KIS_MOCK_VTS`, and `profile_version=official-example-v1`; campaign state is ACTIVE and `data/soak-controller.db` exists. The first `bot soak status` succeeded before any run or drill and reported ACTIVE SOAK, eligible `0/20`, designated runs `0`, availability `0/2`, safety latch `NONE`, zero active campaign freezes, and zero drill denominators. Controller SHA-256 was `7dd16f303f27393aa7e2e57bba3d9b89ef1adffe0c87e605f20476bdb8a84f92` both before and after status. Read-only inspection found `user_version=1`, `journal_mode=wal`, `synchronous=2 (FULL)`, and zero rows in all four drill tables. No order POST, cancel, modify, `soak run`, or drill occurred.
  implication: Human verification confirms the original pre-drill bootstrap failure is resolved in the real KIS MOCK workflow, status remains non-mutating, and the empty controller journal preserves all bounded safety constraints.

## Eliminated

- hypothesis: `bot soak status` should lazily create or migrate the missing controller journal.
  evidence: `ReadOnlySoakRepository` is explicitly designed and tested to open all stores with `mode=ro` and `PRAGMA query_only=ON`; mutating status would weaken a deliberate safety contract.
  timestamp: 2026-07-20T11:25:43+09:00
- hypothesis: A missing controller path in configuration causes the failure.
  evidence: `SoakSettings` always carries `controller_db_path`, validates it as part of the canonical pairwise-distinct topology, and passes it to both start-time validation and status reporting.
  timestamp: 2026-07-20T11:25:43+09:00

## Resolution

- root_cause: Campaign start implemented Plan 09-05's deliberate controller non-open rule, while controller creation was deferred to Plan 09-06's drill-only runtime even though Plan 09-08 requires read-only triple-store status before the first drill. Consequently no successful pre-drill lifecycle path created/migrated `controller_db_path`, and status correctly failed closed on the missing file.
- fix: Added a schema-only `bootstrap_controller_journal` open/close operation and injected it into successful campaign-start orchestration after STARTUP reconciliation and before status load. Added regression coverage proving the journal is canonical and empty, no submission/freeze path is reached, and the first real CLI status remains read-only.
- verification: Focused soak CLI/controller/reporting tests pass 48/48; full repository suite passes 580/580; compileall and git diff whitespace checks pass. Regression confirms version-1 WAL schema, zero rows in all four drill tables, successful immediate CLI status, and byte-preserving controller reads. Ruff was unavailable because it is not installed in the project environment. Operator live verification then confirmed one bounded KIS MOCK start created ACTIVE campaign `soak-20260720-20d-v1` and the canonical empty controller journal; the first pre-drill status succeeded, all drill counts remained zero, and the controller SHA-256 was identical before and after status. No run, drill, order, cancel, modify, freeze mutation, or real-account action occurred.
- files_changed: [trading_bot/soak_controller.py, trading_bot/cli.py, tests/test_soak_cli.py]
