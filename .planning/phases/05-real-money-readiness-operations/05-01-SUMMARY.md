---
phase: 05-real-money-readiness-operations
plan: 01
subsystem: operations-foundation
tags: [typer, settings, notifier, pytest, kis, sqlite, discord]
requires:
  - phase: 04-llm-agent
    provides: switchable LLM cycle and fail-safe execution chain
provides:
  - typer dependency installed in the workspace userbase
  - adapter-free Notifier Protocol
  - operations Settings fields for audit DB, Discord webhook, and order timeout
  - Wave 0 downstream test scaffolds for KIS order, KIS broker, SQLite audit, notifier, and CLI
affects: [05-real-money-readiness-operations, kis-order, audit, notifier, cli]
tech-stack:
  added: [typer==0.26.8]
  patterns: [SecretStr webhook config, adapter-free Protocols, import-gated Wave 0 test scaffolds]
key-files:
  created:
    - tests/test_kis_order.py
    - tests/test_kis_broker.py
    - tests/test_sqlite_audit.py
    - tests/test_notifier.py
    - tests/test_cli.py
  modified:
    - pyproject.toml
    - trading_bot/ports.py
    - trading_bot/config.py
    - .gitignore
    - tests/test_ports.py
    - tests/test_config.py
key-decisions:
  - "Only typer==0.26.8 was added; python-kis remains excluded per the approved direct-REST order path."
  - "Workspace verification uses /opt/homebrew/bin/python3.14 ahead of /usr/bin/python3 because Typer 0.26.8 requires Python >=3.10."
  - "Wave 0 scaffolds collect exact downstream test names while import-gating missing modules until later plans implement them."
patterns-established:
  - "Notifier Protocol mirrors existing synchronous semantic ports and remains adapter-free."
  - "Discord webhook URL is stored as SecretStr and excluded from startup_banner's allowlist."
requirements-completed: [OPS-01, OPS-02, OPS-03, EXEC-04, CFG-04]
coverage:
  - id: D1
    description: "Approved typer==0.26.8 dependency added and importable; python-kis not added."
    requirement: OPS-01
    verification:
      - kind: unit
        ref: "env PATH=\"/opt/homebrew/bin:$PATH\" PYTHONUSERBASE=\"$PWD/.python-userbase\" python3 -c \"import typer; print(typer.__version__)\""
        status: pass
    human_judgment: false
  - id: D2
    description: "Settings exposes audit DB path, SecretStr Discord webhook, and positive order timeout without banner leakage."
    requirement: OPS-02
    verification:
      - kind: unit
        ref: "tests/test_config.py"
        status: pass
    human_judgment: false
  - id: D3
    description: "Notifier Protocol is runtime-checkable, synchronous, and adapter-free."
    requirement: OPS-03
    verification:
      - kind: unit
        ref: "tests/test_ports.py"
        status: pass
    human_judgment: false
  - id: D4
    description: "Wave 0 test scaffolds collect downstream KIS order, broker, audit, notifier, and CLI test names."
    requirement: EXEC-04
    verification:
      - kind: unit
        ref: "tests/test_kis_order.py tests/test_kis_broker.py tests/test_sqlite_audit.py tests/test_notifier.py tests/test_cli.py --collect-only"
        status: pass
    human_judgment: false
duration: 40min
completed: 2026-07-02
status: complete
---

# Phase 05 Plan 01: Foundation Summary

**Real-money operations foundation with Typer installed, SecretStr operations settings, an adapter-free Notifier port, and downstream Wave 0 test targets.**

## Performance

- **Duration:** 40 min
- **Started:** 2026-07-02T12:53:00Z
- **Completed:** 2026-07-02T13:33:44Z
- **Tasks:** 5 completed
- **Files modified:** 11

## Accomplishments

- Added the approved `typer==0.26.8` dependency and verified it imports from the workspace userbase; `python-kis` was not added.
- Added `Notifier` as a runtime-checkable, synchronous, adapter-free Protocol.
- Extended `Settings` with `audit_db_path`, `discord_webhook_url: Optional[SecretStr]`, and `order_timeout_seconds`, with redaction and positive validation coverage.
- Added `data/` to `.gitignore` for the default SQLite audit DB directory.
- Created Wave 0 scaffold tests for KIS order, KIS broker, SQLite audit, notifier, and CLI work planned in 05-02 through 05-04.

## Task Commits

1. **Task 2: Add typer dependency and reinstall the workspace** - `7f15c4e` (feat)
2. **Task 3 RED: Add Notifier expectations** - `4328e19` (test)
3. **Task 3 GREEN: Add Notifier Protocol** - `6a0df85` (feat)
4. **Task 4 RED: Add operations settings expectations** - `1a10253` (test)
5. **Task 4 GREEN: Add operations settings** - `5851263` (feat)
6. **Task 5: Scaffold Wave 0 operations tests** - `60836d8` (test)

## Files Created/Modified

- `pyproject.toml` - Added `typer==0.26.8`.
- `trading_bot/ports.py` - Added `Notifier` Protocol.
- `trading_bot/config.py` - Added audit DB path, Discord webhook secret, and order timeout settings.
- `.gitignore` - Added `data/`.
- `tests/test_ports.py` - Added Notifier structural and synchronous checks.
- `tests/test_config.py` - Added operations settings, webhook redaction, and order timeout validation tests.
- `tests/test_kis_order.py` - Added KIS order adapter scaffold tests.
- `tests/test_kis_broker.py` - Added KIS broker scaffold tests.
- `tests/test_sqlite_audit.py` - Added SQLite audit scaffold tests.
- `tests/test_notifier.py` - Added notifier scaffold tests.
- `tests/test_cli.py` - Added CLI scaffold tests.

## Decisions Made

- Followed the approved checkpoint: added only `typer==0.26.8`; did not add `python-kis`.
- Used `/opt/homebrew/bin/python3.14` for installation and verification because `/usr/bin/python3` is Python 3.9 and cannot install Typer 0.26.8.
- Kept Wave 0 scaffolds import-gated so the full foundation suite remains green while downstream modules are absent; the tests fail once the target module exists until downstream behavior is implemented.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Default `python3` resolved to Python 3.9**
- **Found during:** Task 2
- **Issue:** `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pip install --user -e .` used Xcode Python 3.9, hit legacy editable-install permission errors, and then could not resolve `typer==0.26.8` because that version requires Python >=3.10.
- **Fix:** Re-ran the workspace editable install with `/opt/homebrew/bin/python3.14` and pip's userbase-compatible `--break-system-packages` flag required by Homebrew Python's PEP 668 policy.
- **Files modified:** `pyproject.toml`
- **Verification:** `env PATH="/opt/homebrew/bin:$PATH" PYTHONUSERBASE="$PWD/.python-userbase" python3 -c "import typer; print(typer.__version__)"` printed `0.26.8`.
- **Committed in:** `7f15c4e`

---

**Total deviations:** 1 auto-fixed (Rule 3).
**Impact on plan:** The requested dependency and import state were achieved; verification commands must put `/opt/homebrew/bin` first on PATH in this environment.

## Issues Encountered

- Homebrew Python requires `--break-system-packages` even for a workspace `PYTHONUSERBASE` user install. The install target remained `.python-userbase`, not a system site-packages directory.

## Known Stubs

The following are intentional Wave 0 pending markers. They do not block this plan because downstream plans implement the modules they reference.

| File | Lines | Reason |
|------|-------|--------|
| `tests/test_kis_order.py` | 16-18 | Import-gated pending marker for 05-02 `trading_bot.kis_order`. |
| `tests/test_kis_broker.py` | 11-13 | Import-gated pending marker for 05-02 `trading_bot.kis_broker`. |
| `tests/test_sqlite_audit.py` | 9-11 | Import-gated pending marker for 05-03 `trading_bot.sqlite_audit`. |
| `tests/test_notifier.py` | 20-22 | Import-gated pending marker for 05-03 `trading_bot.notifier`. |
| `tests/test_cli.py` | 11-13 | Import-gated pending marker for 05-04 `trading_bot.cli`. |

## Authentication Gates

None.

## Threat Flags

None. The supply-chain and Discord secret surfaces were already in the plan threat model and were mitigated by the approved package gate plus SecretStr/redaction tests.

## Verification

- `env PATH="/opt/homebrew/bin:$PATH" PYTHONUSERBASE="$PWD/.python-userbase" python3 -c "import typer; print(typer.__version__)"` -> `0.26.8`
- `env PATH="/opt/homebrew/bin:$PATH" PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_ports.py -x` -> 8 passed
- `env PATH="/opt/homebrew/bin:$PATH" PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_config.py -x` -> 31 passed
- `env PATH="/opt/homebrew/bin:$PATH" PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_kis_order.py tests/test_kis_broker.py tests/test_sqlite_audit.py tests/test_notifier.py tests/test_cli.py --collect-only` -> 17 tests collected
- `env PATH="/opt/homebrew/bin:$PATH" PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` -> 280 passed, 17 skipped

## User Setup Required

Discord webhook setup is still required before 05-03/05-04 can deliver real notifications: create a Discord incoming webhook and provide `DISCORD_WEBHOOK_URL` in the environment. This plan only adds the typed secret field.

## Next Phase Readiness

05-02 can implement `trading_bot.kis_order` and `trading_bot.kis_broker` against existing scaffold test names. The Notifier Protocol and settings fields are ready for 05-03, and Typer is installed for 05-04.

## Self-Check: PASSED

- Key files exist: `pyproject.toml`, `trading_bot/ports.py`, `trading_bot/config.py`, `.gitignore`, `tests/test_ports.py`, `tests/test_config.py`, `tests/test_kis_order.py`, `tests/test_kis_broker.py`, `tests/test_sqlite_audit.py`, `tests/test_notifier.py`, `tests/test_cli.py`.
- Task commits found: `7f15c4e`, `4328e19`, `6a0df85`, `1a10253`, `5851263`, `60836d8`.

---
*Phase: 05-real-money-readiness-operations*
*Completed: 2026-07-02*
