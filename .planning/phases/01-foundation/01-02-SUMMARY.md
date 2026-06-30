---
phase: 01-foundation
plan: 02
subsystem: foundation
tags: [python, pydantic-settings, pydantic, pytest, config, secrets, safety]
requires:
  - phase: 01-01
    provides: [package skeleton, approved dependency pins, env template]
provides:
  - Typed `Settings` runtime configuration object
  - Atomic mock/real `KisCredentialGroup` selection through `active_kis`
  - Selected-provider LLM API key resolution through `active_llm_api_key`
  - Real-trading confirmation gate for `TRADING_MODE=real`
  - Non-secret startup safety banner
  - Focused config safety unit tests
affects: [foundation, config, downstream-adapters, phase-02, phase-04, phase-05]
tech-stack:
  added: []
  patterns:
    - Pydantic `BaseSettings` with `.env` and nested env delimiter loading
    - Pydantic `SecretStr` for secret-bearing fields
    - Startup banners built from allowlisted non-secret fields only
key-files:
  created:
    - trading_bot/config.py
    - tests/test_config.py
  modified:
    - tests/test_config.py
key-decisions:
  - "Selected LLM provider secrets are validated during `Settings()` construction so missing active secrets fail closed at startup."
  - "KIS mock and real credentials are exposed as complete groups; future adapters should consume `settings.active_kis` rather than independent active fields."
  - "Python 3.9-compatible `Optional[...]` annotations are used instead of PEP 604 unions to avoid adding an extra typing backport dependency."
patterns-established:
  - "Config code may expose secret values only through explicit `SecretStr` accessors used by downstream adapters, never through banners or logging helpers."
  - "Real trading requires both `TRADING_MODE=real` and `CONFIRM_REAL_TRADING=yes`."
requirements-completed: [CFG-01, CFG-02, CFG-03]
coverage:
  - id: D1
    description: "`Settings` loads grouped KIS and LLM secrets from env using typed Pydantic settings while secret-bearing fields remain redacted in repr/banner/log text."
    requirement: CFG-01
    verification:
      - kind: unit
        ref: "PYTHONUSERBASE=.python-userbase python3 -m pytest tests/test_config.py -q"
        status: pass
    human_judgment: false
  - id: D2
    description: "`Settings.active_kis` selects one complete mock or real `KisCredentialGroup`, and real mode fails startup unless confirmed."
    requirement: CFG-02
    verification:
      - kind: unit
        ref: "PYTHONUSERBASE=.python-userbase python3 -m pytest tests/test_config.py -q"
        status: pass
    human_judgment: false
  - id: D3
    description: "`Settings.active_llm_api_key` resolves exactly the selected Claude or OpenAI provider secret and missing active provider keys fail closed."
    requirement: CFG-03
    verification:
      - kind: unit
        ref: "PYTHONUSERBASE=.python-userbase python3 -m pytest tests/test_config.py -q"
        status: pass
    human_judgment: false
  - id: D4
    description: "`startup_banner(settings)` reports mode, KIS label, LLM provider, dry-run state, confirmation state, and redaction status without secret values."
    requirement: CFG-01
    verification:
      - kind: unit
        ref: "PYTHONUSERBASE=.python-userbase python3 -m pytest tests/test_config.py -q"
        status: pass
      - kind: other
        ref: "PYTHONUSERBASE=.python-userbase python3 -m compileall trading_bot"
        status: pass
    human_judgment: false
duration: 3min
completed: 2026-06-30
status: complete
---

# Phase 01 Plan 02: Typed Settings and Config Safety Summary

**Typed Pydantic settings with secret redaction, atomic KIS mode binding, selected LLM provider validation, and a non-secret startup banner**

## Performance

- **Duration:** 3 min
- **Started:** 2026-06-30T14:05:17Z
- **Completed:** 2026-06-30T14:08:04Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Added `trading_bot.config.Settings` with `.env` support, nested KIS credential groups, typed trading/LLM enums, and `SecretStr` fields.
- Implemented `active_kis`, real-mode confirmation, and selected-provider LLM key validation so unsafe or incomplete active configuration fails closed.
- Added a startup safety banner and focused pytest coverage proving secret redaction, mode selection, provider selection, and actionable non-secret failures.

## Task Commits

Each task was committed atomically:

1. **Task 1: Write failing config safety tests** - `148e22d` (test)
2. **Task 2: Implement typed settings and startup banner** - `62b6b2f` (feat)

## Files Created/Modified

- `trading_bot/config.py` - Defines `TradingMode`, `LLMProviderName`, `KisCredentialGroup`, `Settings`, `active_kis`, `active_llm_api_key`, and `startup_banner`.
- `tests/test_config.py` - Covers secret redaction, grouped KIS selection, real-mode confirmation, selected-provider LLM validation, and banner content.

## Decisions Made

- Selected LLM provider keys are validated during `Settings()` construction, not only when the property is later accessed, to match the phase's fail-closed startup posture.
- Optional inactive provider secrets remain optional at the raw settings level, so `LLM_PROVIDER=claude` does not require `OPENAI_API_KEY` and `LLM_PROVIDER=openai` does not require `ANTHROPIC_API_KEY`.
- Python 3.9-compatible `Optional[...]` annotations were used because the local Python runtime is 3.9.6 and the existing approved dependencies do not include `eval_type_backport`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Replaced PEP 604 optional annotations for Python 3.9 compatibility**
- **Found during:** Task 2 (Implement typed settings and startup banner)
- **Issue:** Pydantic could not evaluate `SecretStr | None` on the local Python 3.9 runtime without an additional `eval_type_backport` dependency.
- **Fix:** Replaced those annotations with `Optional[SecretStr]`, preserving behavior without adding packages.
- **Files modified:** `trading_bot/config.py`
- **Verification:** `PYTHONUSERBASE=.python-userbase python3 -m pytest tests/test_config.py -q` and `PYTHONUSERBASE=.python-userbase python3 -m compileall trading_bot` passed.
- **Committed in:** `62b6b2f`

**2. [Rule 2 - Missing Critical Functionality] Tightened selected LLM secret validation to startup**
- **Found during:** Task 2 (Implement typed settings and startup banner)
- **Issue:** The initial RED test expected a missing selected LLM key to fail only when `active_llm_api_key` was accessed, but the phase decisions require selected active secrets to fail closed at startup.
- **Fix:** Kept the implementation's `Settings()` startup validation and updated the test to assert a non-secret `ValidationError` for the missing selected provider key.
- **Files modified:** `tests/test_config.py`, `trading_bot/config.py`
- **Verification:** `PYTHONUSERBASE=.python-userbase python3 -m pytest tests/test_config.py -q` passed.
- **Committed in:** `62b6b2f`

**Total deviations:** 2 auto-fixed (Rule 3 compatibility, Rule 2 fail-closed startup validation)
**Impact on plan:** The changes preserve the planned API while strengthening startup safety and avoiding unapproved dependency expansion.

## Issues Encountered

- `ctx7` was not installed, so Context7 documentation lookup could not run. Implementation followed the already-approved phase research and verified behavior against the installed approved dependency versions.
- Existing unrelated local GSD files were already modified or untracked before this plan's changes; they were left unstaged unless updated by state tooling.

## Auth Gates

None.

## Known Stubs

None. The optional `anthropic_api_key` and `openai_api_key` raw fields are intentional because only the selected provider secret is required.

## User Setup Required

None for this plan. Local verification commands on this machine should continue to use `PYTHONUSERBASE=.python-userbase` unless a replacement project-local environment is created.

## Next Phase Readiness

Future KIS and LLM adapters can consume `Settings.active_kis` and `Settings.active_llm_api_key` as the stable config boundary. Plan 01-03 can add domain models and port Protocols without concrete adapter imports.

## Self-Check: PASSED

- Found summary file: `.planning/phases/01-foundation/01-02-SUMMARY.md`
- Found task commits: `148e22d`, `62b6b2f`
- Found created files: `trading_bot/config.py`, `tests/test_config.py`
- Verification passed: `PYTHONUSERBASE=.python-userbase python3 -m pytest tests/test_config.py -q`
- Verification passed: `PYTHONUSERBASE=.python-userbase python3 -m compileall trading_bot`

---
*Phase: 01-foundation*
*Completed: 2026-06-30*
