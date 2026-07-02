---
phase: 05-real-money-readiness-operations
plan: 03
subsystem: operations
tags: [sqlite, audit, discord, notifier, tenacity, pytest]

requires:
  - phase: 04-llm-agent
    provides: LLM cycle structlog line used as the correlation target
  - phase: 05-real-money-readiness-operations
    provides: Settings audit/Discord fields and Notifier port from Plan 05-01
provides:
  - Two-table SQLite audit writer with WAL and per-decision commits
  - Fail-soft Discord notifier with bounded retry and no-op fallback
  - Offline tests for audit persistence and notification behavior
affects: [phase-05-cli, operations, audit, notifications]

tech-stack:
  added: []
  patterns:
    - stdlib sqlite3 side-channel writer consuming frozen domain events structurally
    - injected httpx-compatible client with bounded tenacity retry and fail-soft return

key-files:
  created:
    - trading_bot/sqlite_audit.py
    - trading_bot/notifier.py
  modified:
    - tests/test_sqlite_audit.py
    - tests/test_notifier.py

key-decisions:
  - "SQLite stores structured decision fields plus correlation_id only; raw prompt/response remain in structlog."
  - "Discord delivery is a side channel: bounded retry, non-secret warning log, and False on final failure."

patterns-established:
  - "Audit writes start with a runs row and add one committed decisions row per ticker."
  - "Notifier construction returns NoopNotifier when DISCORD_WEBHOOK_URL is absent."

requirements-completed: [OPS-02, OPS-03]

coverage:
  - id: D1
    description: "Two-table SQLite audit writer persists run headers and per-ticker decisions queryable by run and ticker."
    requirement: OPS-02
    verification:
      - kind: unit
        ref: "tests/test_sqlite_audit.py#test_two_table_write"
        status: pass
      - kind: unit
        ref: "tests/test_sqlite_audit.py#test_correlation_id"
        status: pass
    human_judgment: false
  - id: D2
    description: "Discord notifier sends one consolidated per-run summary and fails soft after bounded retry."
    requirement: OPS-03
    verification:
      - kind: unit
        ref: "tests/test_notifier.py#test_consolidated_summary"
        status: pass
      - kind: unit
        ref: "tests/test_notifier.py#test_fail_soft"
        status: pass
      - kind: unit
        ref: "tests/test_notifier.py#test_missing_webhook_builds_noop_notifier"
        status: pass
    human_judgment: false

duration: 5min
completed: 2026-07-02
status: complete
---

# Phase 05 Plan 03: SQLite Audit and Discord Notifier Summary

**SQLite audit persistence and fail-soft Discord notification side channels are now implemented and covered by offline tests.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-07-02T13:58:58Z
- **Completed:** 2026-07-02T14:03:37Z
- **Tasks:** 2 completed
- **Files modified:** 4

## Accomplishments

- Added `trading_bot/sqlite_audit.py` with `runs` and `decisions` tables, WAL setup, run/ticker indexes, correlation IDs, and per-decision commits.
- Added `trading_bot/notifier.py` with `DiscordNotifier`, `NoopNotifier`, `build_notifier`, and `format_run_summary`.
- Replaced Wave 0 scaffolds with offline tests proving run/ticker queryability, no prompt/response DB columns, consolidated notification delivery, fail-soft retry behavior, and secret redaction from message/log/repr surfaces.

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: SQLite audit behavior tests** - `afa8e02` (test)
2. **Task 2 RED: Discord notifier behavior tests** - `7d70485` (test)
3. **Task 1 GREEN: SQLite audit writer** - `a2a246d` (feat)
4. **Task 2 GREEN: Discord notifier** - `b81deac` (feat)

_Note: TDD tasks produced RED and GREEN commits. No separate refactor commit was needed._

## Files Created/Modified

- `trading_bot/sqlite_audit.py` - Opens/configures the audit database, creates the normalized schema, writes run headers, and commits each per-ticker decision row.
- `trading_bot/notifier.py` - Implements the Discord webhook notifier, no-op fallback, factory, and consolidated run summary formatter.
- `tests/test_sqlite_audit.py` - Covers normalized writes, run/ticker queries, correlation ID persistence, no raw prompt/response columns, and frozen event consumption.
- `tests/test_notifier.py` - Covers one webhook POST per run, fail-soft retry exhaustion, no configured webhook fallback, and no webhook secret in messages/logs/repr.

## Decisions Made

- Kept the audit writer structural: it reads `CycleAuditEvent` attributes and does not import, mutate, or re-type the frozen dataclass.
- Made `correlation_id` required on decision writes so callers cannot silently lose the structlog traceability link.
- Used the Phase 5 Homebrew Python interpreter (`/opt/homebrew/bin/python3.14`) for verification because generic `python3` resolves to Apple Python 3.9 in this shell and cannot import the installed pytest dependency set.

## Deviations from Plan

None - plan executed as written.

## Issues Encountered

- The literal `python3` verification command failed before collection under Apple Python 3.9 because installed dependencies require newer typing APIs. The Phase 5 project decision already established `/opt/homebrew/bin/python3.14`; targeted and full-suite verification passed with that interpreter and the required `PYTHONUSERBASE`.

## Known Stubs

None.

## Threat Flags

None - the new SQLite persistence and Discord webhook surfaces were already covered by the plan threat model.

## Verification

- `PYTHONUSERBASE="$PWD/.python-userbase" /opt/homebrew/bin/python3.14 -m pytest -q tests/test_sqlite_audit.py tests/test_notifier.py -x` - 5 passed
- `PYTHONUSERBASE="$PWD/.python-userbase" /opt/homebrew/bin/python3.14 -m pytest -q` - 298 passed, 4 skipped
- `CycleAuditEvent` definition unchanged; `trading_bot/execution.py` was not modified.

## User Setup Required

None for automated verification. Real Discord delivery still requires setting `DISCORD_WEBHOOK_URL` in the local environment before the CLI plan wires notifications into a run.

## Next Phase Readiness

Plan 05-04 can wire the CLI run loop to `sqlite_audit.start_run`, `sqlite_audit.write_decision`, and `format_run_summary`/`Notifier.send`. The side channels are fail-soft and testable with injected clients.

## Self-Check: PASSED

- Found `trading_bot/sqlite_audit.py`
- Found `trading_bot/notifier.py`
- Found `tests/test_sqlite_audit.py`
- Found `tests/test_notifier.py`
- Found commits `afa8e02`, `7d70485`, `a2a246d`, `b81deac`

---
*Phase: 05-real-money-readiness-operations*
*Completed: 2026-07-02*
