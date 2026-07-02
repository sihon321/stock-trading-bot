---
phase: 05-real-money-readiness-operations
plan: 04
subsystem: operations
tags: [typer, cli, dry-run, kis, sqlite, notifier]
requires:
  - phase: 05-real-money-readiness-operations
    provides: KISBroker, SQLite audit writer, and fail-soft Discord notifier
provides:
  - Typer CLI app with bot run, bot screen, and bot status
  - Dry-run default with per-invocation real-money confirmation gate
  - Per-ticker universe loop with error isolation, audit writes, and consolidated notification
affects: [operations, real-money-readiness, cli]
tech-stack:
  added: []
  patterns:
    - Injectable CLI composition root
    - Layered real-money gate
    - Fail-soft immediate plus consolidated notifications
key-files:
  created:
    - trading_bot/cli.py
  modified:
    - pyproject.toml
    - tests/test_cli.py
key-decisions:
  - "The CLI core is exposed as an injectable run_cycle function, with Typer commands kept as thin wrappers."
  - "Real-mode broker construction requires a caller-owned KisTokenManager and a caller-provided KIS account descriptor."
  - "Cycle-level notification failures remain fail-soft even when an injected notifier raises."
patterns-established:
  - "Manual run orchestration resolves default collaborators lazily, while tests inject fakes for offline coverage."
  - "Per-ticker exceptions are converted to outcome records and immediate error sends without aborting the run."
requirements-completed: [OPS-01, CFG-04]
coverage:
  - id: D1
    description: "Manual Typer CLI exposes bot run, bot screen, and bot status with a bot console entry point."
    requirement: OPS-01
    verification:
      - kind: unit
        ref: "tests/test_cli.py#test_real_execute_requires_live_confirm"
        status: pass
      - kind: other
        ref: "PYTHONUSERBASE=\"$PWD/.python-userbase\" /opt/homebrew/bin/python3.14 -c \"from trading_bot.cli import app; print(app)\""
        status: pass
    human_judgment: false
  - id: D2
    description: "bot run is dry-run by default and refuses real execute without --live-confirm."
    requirement: CFG-04
    verification:
      - kind: unit
        ref: "tests/test_cli.py#test_real_execute_requires_live_confirm"
        status: pass
      - kind: unit
        ref: "tests/test_cli.py#test_dry_run_default_no_orders"
        status: pass
    human_judgment: false
  - id: D3
    description: "Full-universe run supports --ticker narrowing, per-ticker error isolation, SQLite audit writes, and notifier summary/error sends."
    requirement: OPS-01
    verification:
      - kind: unit
        ref: "tests/test_cli.py#test_ticker_error_isolation"
        status: pass
      - kind: unit
        ref: "tests/test_cli.py#test_ticker_option_narrows_universe"
        status: pass
      - kind: unit
        ref: "tests/test_cli.py#test_immediate_error_push"
        status: pass
    human_judgment: false
  - id: D4
    description: "Real-mode broker selection routes through KISBroker wiring with one shared token manager."
    requirement: CFG-04
    verification:
      - kind: unit
        ref: "tests/test_cli.py#test_real_broker_uses_shared_token_manager"
        status: pass
    human_judgment: false
duration: 35min
completed: 2026-07-02
status: complete
---

# Phase 05 Plan 04: Operator CLI Summary

**Manual Typer operator CLI with dry-run/live-confirm safety gates, universe-loop orchestration, SQLite audit writes, and fail-soft notifications**

## Performance

- **Duration:** 35 min
- **Started:** 2026-07-02T13:37:00Z
- **Completed:** 2026-07-02T14:12:34Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Added `trading_bot/cli.py` with `app`, `bot run`, `bot screen`, and `bot status`.
- Registered `[project.scripts] bot = "trading_bot.cli:app"`.
- Implemented dry-run-by-default execution, real-mode `--execute` refusal without `--live-confirm`, full screened-universe runs, `--ticker` narrowing, per-ticker error isolation, SQLite audit writes, MockBroker/KISBroker selection, and immediate error plus consolidated summary notification sends.

## Task Commits

1. **RED: CLI safety and run-loop tests** - `5102a95` (test)
2. **Task 1: Typer app with layered real-money gate** - `36f1fe4` (feat)
3. **Task 2: Universe loop, broker selection, audit, and notifier coverage** - `d80e3e0` (test)

## Files Created/Modified

- `trading_bot/cli.py` - Typer app, injectable run-cycle core, collaborator construction, safety gate, universe loop, audit writes, and notifier sends.
- `pyproject.toml` - `bot` console entry point.
- `tests/test_cli.py` - Offline CLI tests for gate refusal, dry-run default, ticker narrowing, error isolation, broker selection, and notification behavior.

## Decisions Made

- The command wrappers stay thin; `run_cycle` is the testable composition root.
- Real KIS broker default construction fails closed unless the caller supplies `KIS_ACCOUNT_CANO` or an injected `KisOrderAccount`; no placeholder account values are invented.
- The default production runtime constructs one shared `KisTokenManager` and passes it into the quote adapter and real broker factory.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Real broker account descriptor remains fail-closed**
- **Found during:** Task 2
- **Issue:** `Settings` contains KIS credential groups but no CANO/product-code account descriptor. Constructing a live `KISBroker` with dummy account values would be unsafe.
- **Fix:** CLI real-broker construction requires an injected `KisOrderAccount` or `KIS_ACCOUNT_CANO` from the environment; otherwise it raises before broker construction.
- **Files modified:** `trading_bot/cli.py`, `tests/test_cli.py`
- **Verification:** `tests/test_cli.py#test_real_broker_uses_shared_token_manager`
- **Committed in:** `36f1fe4`, `d80e3e0`

**2. [Rule 3 - Blocking] Used the workspace Python 3.14 interpreter for verification**
- **Found during:** Task 1 RED verification
- **Issue:** Bare `python3` resolves to Apple Python 3.9 in this environment, which cannot import dependencies installed for Python >=3.10.
- **Fix:** Verification used `PYTHONUSERBASE="$PWD/.python-userbase" /opt/homebrew/bin/python3.14 ...`, matching the Phase 05 recorded interpreter.
- **Files modified:** None
- **Verification:** CLI import and full suite passed.
- **Committed in:** N/A

**Total deviations:** 2 auto-fixed (Rule 2: 1, Rule 3: 1)
**Impact on plan:** Safety behavior is stricter; no scope expansion beyond required real-money fail-closed wiring.

## Issues Encountered

- The expected TDD RED failure was `ModuleNotFoundError: No module named 'trading_bot.cli'`.
- The first bare `python3` pytest attempt failed because Python 3.9 lacked `typing.TypeAlias`; verification was rerun with Python 3.14.

## Verification

- `PYTHONUSERBASE="$PWD/.python-userbase" /opt/homebrew/bin/python3.14 -m pytest -q tests/test_cli.py -x` -> 6 passed.
- `PYTHONUSERBASE="$PWD/.python-userbase" /opt/homebrew/bin/python3.14 -c "from trading_bot.cli import app; print(app)"` -> passed.
- `PYTHONUSERBASE="$PWD/.python-userbase" /opt/homebrew/bin/python3.14 -m pytest -q` -> 304 passed.

## Known Stubs

None.

## Threat Flags

None. The CLI introduces the planned operator and broker-selection boundary, with the planned dry-run default, config gate, per-invocation `--live-confirm`, and shared-token KIS broker wiring mitigations.

## User Setup Required

For real-mode broker construction outside injected tests, set `KIS_ACCOUNT_CANO` and optionally `KIS_ACCOUNT_PRODUCT_CODE` in the runtime environment. Real execution still also requires `TRADING_MODE=real`, `CONFIRM_REAL_TRADING=yes`, `--execute`, and `--live-confirm`.

## Next Phase Readiness

Phase 05 is complete. The bot now has manual operation, data/LLM/execution wiring, idempotent KIS order readiness, SQLite audit persistence, and fail-soft notification coverage. Live KIS mock/real verification remains manual because it requires valid KIS credentials, account identifiers, market-session timing, and external network access.

## Self-Check: PASSED

- Found summary file: `.planning/phases/05-real-money-readiness-operations/05-04-SUMMARY.md`
- Found task commits: `5102a95`, `36f1fe4`, `d80e3e0`
- Verified files: `trading_bot/cli.py`, `pyproject.toml`, `tests/test_cli.py`

---
*Phase: 05-real-money-readiness-operations*
*Completed: 2026-07-02*
