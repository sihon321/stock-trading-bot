---
phase: 15-unattended-scheduling-service-resilience
plan: "13"
subsystem: infra
tags: [typer, launchd, sqlite, owner-login, restart-budget, mock-safety]
requires:
  - phase: 15-03
    provides: Protected service journal and narrow expectation writer contracts
  - phase: 15-05
    provides: Revisioned request-only controls and typed service resume validation
  - phase: 15-06
    provides: Protected mock credentials and receipt-gated composition
  - phase: 15-10
    provides: Concrete account runtime, bounded recovery and observer expectation production
  - phase: 15-12
    provides: Descriptor-based CLI/web request ports and attributable replay contracts
provides:
  - Explicit protected service CLI with disabled setup, offline replay and manual receipt transport
  - Concrete mock runtime binding with primary audit, owned activation, fresh bounded account recovery and submission authority
  - Durable pre-worker restart admission and independently supervised owner GUI observer
affects: [15-14, phase-verification, operator-runbook]
tech-stack:
  added: []
  patterns: [lazy capability construction, preacquired concrete leader, narrow expectation SQL allowlist, protected idempotent attention request transport]
key-files:
  created: [trading_bot/service_cli.py, trading_bot/service_launchd.py, tests/test_service_cli.py, tests/test_service_launchd.py]
  modified: [pyproject.toml, trading_bot/service_activation.py, trading_bot/service_runtime.py, trading_bot/service_store.py, trading_bot/alert_cli.py, docs/operator-runbook.md]
key-decisions:
  - "Worker construction follows durable OS leadership and restart admission; unexpected exits persist UNEXPECTED_EXIT before releasing ownership."
  - "Receipt capture shares owned saved-evidence validation and never enables mode, clears freezes or grants activation."
  - "The independent observer uses protected secret-free registration, read-only control/session evidence and an expectation-only SQL writer."
  - "Explicit attention resets retain controls/history and require 600 seconds plus current owned activation and bounded account recovery."
requirements-completed: []
coverage:
  - id: D1
    description: Request-only CLI, protected disabled setup, verified receipt transport and concrete runtime binding
    requirement: AUTO-02
    verification:
      - kind: integration
        ref: tests/test_service_cli.py#test_request_only_revision_replay_and_restriction
        status: pass
      - kind: integration
        ref: tests/test_service_cli.py#test_real_composition_root_binds_concrete_account_and_audit
        status: pass
      - kind: integration
        ref: tests/test_service_cli.py#test_receipt_capture_shared_saved_checks_do_not_grant_activation
        status: pass
    human_judgment: false
  - id: D2
    description: Durable restart accounting, protected GUI lifecycle and independent expectation production
    requirement: FUT-04
    verification:
      - kind: integration
        ref: tests/test_service_launchd.py#test_actual_runtime_tick_crash_retains_unexpected_generation_and_budget
        status: pass
      - kind: integration
        ref: tests/test_service_launchd.py#test_attention_reset_requires_elapsed_window_and_fresh_owned_recovery
        status: pass
      - kind: integration
        ref: tests/test_service_launchd.py#test_narrow_expectation_writer_denies_all_other_table_writes
        status: pass
      - kind: integration
        ref: tests/test_service_launchd.py#test_registered_observer_produces_midnight_without_trading_or_general_writes
        status: pass
    human_judgment: false
  - id: D3
    description: Actual owner GUI login/logout, sleep/wake, installed agent removal and phone controls
    verification: []
    human_judgment: true
    rationale: Fake launchctl, temporary journals and offline collaborators cannot prove current Mac GUI supervision or phone access; authorized installation and owner review remain pending.
duration: 264min
completed: 2026-10-05
status: complete
---

# Phase 15 Plan 13: Protected Service CLI and Owner Login Supervision Summary

**Request-only service commands and concrete mock runtime binding with durable restart admission, verified reset transport and a separate expectation-writing GUI observer.**

## Performance

- Duration: approximately 264 minutes wall time from first RED, including the usage interruption; this is not uninterrupted execution time.
- Started: 2026-10-04T21:14:28+09:00 (first RED commit).
- Completed: 2026-10-05T01:38:00+09:00.
- Tasks: 2; implementation/test/config/document files: 10.

## Accomplishments

- Registered `bot-service` and direct module invocation with all declared commands. Disabled setup creates distinct protected stores, PAUSED controls and no receipt. Read/control/render/offline paths construct no trading settings, credentials, broker/provider or OS lifecycle process.
- Bound enabled mock execution to actual ServiceRuntime and AccountTradingBinding, primary SQLite audit, SubmissionAuthority, OwnedActivationCheck, fresh broker/quote/snapshot/reconciliation and bounded account lease work. Protected fixed `accepted-profile.json` and strict `service-policy.json` supply explicit policy/evidence without dotenv or credential graph defaults. Missing receipt or unverified actual Codex single-shot denies before trading construction.
- Rendered fixed service/observer labels with absolute protected paths and conditional KeepAlive. Explicit lifecycle checks GUI ownership and both file/label collisions before mutation; stop preserves the observer, removal preserves all journals/config/controls/history. No actual agents were installed or operated.
- Reserved restart admission before worker construction. Initial run plus three automatic restart attempts are counted durably even across constructor/tick crashes; subsequent admission exits cleanly in MANUAL_ATTENTION, including after the window until an explicit validated reset. Clock reversal fails closed. Overnight IDLE and next-day fresh activation/recovery behavior are unchanged.
- Bound the separate observer to protected secret-free registration, exact-date session/control readers, bounded owner GUI print evidence and a settings-only expectation writer. Its SQL authorizer permits expectation/expectation-health insertion and denies other table mutations/schema changes. It continues expectation ticks at midnight without trading jobs and reports unavailable trading source evidence as UNKNOWN.

## Task Commits

1. Task 1 RED: `d7d451b` — request-only CLI and disabled setup tests (six expected missing-module failures).
2. Task 1 GREEN: `13d5931` — concrete protected mock runtime and explicit CLI (49 required tests passed; 91 related tests passed).
3. Task 2 RED: `57ba229` — durable launcher and separate observer tests (six expected missing implementation failures).
4. Task 2 GREEN: `1457fc6` — admitted service, reset validation and independent GUI observer.

Both tasks have ordered test/feat gates; normal repository commit hooks were used.

## Verification

- Final `.venv/bin/python -m pytest tests/test_service_launchd.py tests/test_service_store.py tests/test_service_cli.py tests/test_service_activation.py tests/test_alert_cli.py tests/test_alert_observer.py -q`: **103 passed in 4.06s**.
- Earlier related recovery/schedule/alerts/health/controls/composition regression: **159 passed in 23.85s**. Parent performs the phase wave/full regression after this plan.
- Python compilation and `git diff --check` passed. No files deleted; no blocking stubs found in changed sources.
- All checks used injected/offline collaborators, fake launchctl and temporary owner-protected stores. No live KIS, paid LLM, Discord, production reads/migrations, package installation or actual approval capture occurred.

## Files Created/Modified

- `service_cli.py`, `test_service_cli.py`, `pyproject.toml`: declared commands, narrow requests, protected setup/receipt transport, offline replay and production binder.
- `service_launchd.py`, `test_service_launchd.py`: pure plist rendering, explicit lifecycle, GUI observation, pre-worker admission, crash persistence and reset/observer boundaries.
- `service_activation.py`: shared owned saved-receipt validation without weakening full unattended activation.
- `service_runtime.py`: concrete admitted leader, typed fresh resume callbacks and truthful unexpected-exit close semantics.
- `service_store.py`, `alert_cli.py`: settings-only expectation writer with SQL allowlist and independent producer composition.
- `docs/operator-runbook.md`: fixed paths, explicit fields, lifecycle commands, restart/reset semantics and remaining operator gates.

## Decisions Made

- CLI and authenticated web requests share the descriptor factory, installation scope, revision and immutable request replay contract. The configured web owner actor must match `local-owner-uid-<uid>` for owner-only resume; mismatches remain OWNER_REQUIRED without changing prior history.
- The reset request is owner-protected canonical transport, with consumed IDs retained in fixed history. It cannot reset attention until 600 seconds and current owned activation plus fresh bounded recovery are validated by the service. PAUSED/KILLED controls and evidence remain retained.
- GUI print is a bounded evidence adapter, not a stable machine API assumption. Missing, contradictory or failed registration remains UNKNOWN; disabled/status/render paths never run it.

## Deviations from Plan

1. **[Rule 2 — Missing critical functionality; parent-approved narrow extension] Concrete production binding.** Plan-only injectable factories would not provide operational account authority. Added the actual primary audit, protected mock composition, BACWork recovery, snapshots/reconciliation, quote freshness and OwnedActivationCheck binding in the owned CLI; extended runtime solely to accept its already-admitted concrete leader and typed resume callbacks. Commits `13d5931`, `1457fc6`.
2. **[Rule 2 — Validation boundary; parent-approved narrow extension] Shared receipt capture validation.** Factored existing saved acceptance/campaign/profile/source/checkpoint checks into `validate_receipt_capture`; capture skips only active-mode/current-safety/existing-receipt requirements and returns no trading authority. Full activation validation remains unchanged. Commit `13d5931`.
3. **[Rule 2 — Least authority; parent-approved narrow extension] Independent observer writer.** Added settings-only ExpectationWriter construction without ServiceJournal initialize/general-writer capability; SQL allowlist and missing-source behavior are verified. Commit `1457fc6`.
4. **[Rule 1 — Critical exit boundary; parent-approved narrow extension] Unexpected runtime crashes.** Default clean shutdown would classify tick failures as clean, bypassing restart accounting. Added `stop(clean_stop=False)` persistence for unexpected exits while preserving explicit SIGTERM stop semantics and the original exception. Actual-runtime crash tests prove initial plus exactly three automatic admissions and later denial. Commit `1457fc6`.
5. **[Rule 1 — Current clock validation] GUI observation timestamp.** Final lifecycle validation exposed microsecond-future evidence against OwnerLoginProbe's observation start. The adapter now uses the exact bounded observation start timestamp; real-clock fake lifecycle and injected-clock probe checks pass. Commit `1457fc6`.
6. **Execution continuity.** Usage interruption after Task 1 RED left partial source changes. The owner's explicit October 5 resume continued those changes, preserved `d7d451b`, and completed the existing two tasks without restarting or reverting work. Missing `uv` on the resumed shell was handled with existing `.venv/bin/python`; nothing was installed.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: local-evidence-transport | service_cli.py, service_launchd.py | Fixed protected policy/profile/reset/history files add local trust boundaries; strict models, derived paths, owner permissions, exclusive canonical writes and current owned validation constrain them. |
| threat_flag: sqlite-authorizer | service_store.py | Observer opens an existing protected journal in narrowly writable mode; schema ownership and SQL table/action allowlist deny general service mutations. |

## Remaining Gates and Limits

- Actual Phase 09-08 named checkpoint approvals remain absent, 000660 remains frozen, and actual Codex 0.144.6 single-shot support remains unverified. The production root fails closed; fixtures do not constitute approvals or promotion.
- Actual GUI login/logout/sleep/wake and installed lifecycle, Korean desktop/phone controls and configured private phone access remain human acceptance work. No manual result is claimed. Phase requirements remain unchecked until independent phase verification.
- Saved daily loss uses the first complete same-day equity snapshot as its conservative reference; absent usable baseline denies BUY. Sleep/logout/outage cannot create missing availability or authorize catch-up after deadlines.

## Self-Check: PASSED

All four created files and six modified files exist. Commits `d7d451b`, `13d5931`, `57ba229`, and `1457fc6` exist in main history; no tracked deletions or uncommitted implementation files remain after GREEN. Ordered RED/GREEN gates and canonical output were verified before tracking updates.
