---
phase: 04-llm-agent
plan: 01
subsystem: config
tags: [llm, settings, dependencies, anthropic, openai, structlog]

requires:
  - phase: 03-data-pipeline
    provides: DataContext and source-policy settings patterns consumed by Phase 4 LLM plans
provides:
  - Approved and installed exact LLM runtime dependency pins
  - Settings fields for Anthropic/OpenAI model IDs, temperatures, and LLM retry controls
  - Config tests for defaults, environment overrides, and fail-closed retry validation
affects: [04-llm-agent, llm-provider, reproducibility]

tech-stack:
  added: [anthropic==0.115.1, openai==2.44.0, structlog==25.5.0]
  patterns: [workspace PYTHONUSERBASE install, pydantic-settings validation, TDD config extension]

key-files:
  created:
    - .planning/phases/04-llm-agent/04-01-SUMMARY.md
  modified:
    - pyproject.toml
    - trading_bot/config.py
    - tests/test_config.py

key-decisions:
  - "Approved pins used: anthropic==0.115.1, openai==2.44.0, structlog==25.5.0."
  - "Settings.openai_model defaults to gpt-4.1."
  - "Settings.anthropic_temperature remains 0.0 for reproducibility logging/config symmetry, but the Anthropic adapter must omit temperature from requests; OpenAI sends temperature=0.0."
  - "Homebrew Python 3.14 is required for the workspace .python-userbase verification commands in this checkout."

patterns-established:
  - "LLM Settings: non-secret model and temperature pins live beside provider API-key selection in Settings."
  - "LLM Retry Policy: dedicated llm_max_retries and llm_retry_backoff_seconds fail closed independently of KIS retry controls."

requirements-completed: [LLM-02]

coverage:
  - id: D1
    description: "Pinned and installed approved Anthropic, OpenAI, and structlog runtime dependencies in the workspace userbase."
    requirement: LLM-02
    verification:
      - kind: other
        ref: 'PATH="/opt/homebrew/bin:$PATH" PYTHONUSERBASE="$PWD/.python-userbase" python3 -c "import anthropic, openai, structlog; print(anthropic.__version__, openai.__version__, structlog.__version__)"'
        status: pass
      - kind: unit
        ref: 'PATH="/opt/homebrew/bin:$PATH" PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q'
        status: pass
    human_judgment: false
  - id: D2
    description: "Settings expose config-overridable Anthropic/OpenAI model IDs, temperatures, and dedicated LLM retry controls."
    requirement: LLM-02
    verification:
      - kind: unit
        ref: 'tests/test_config.py#test_phase4_llm_defaults_are_deterministic'
        status: pass
      - kind: unit
        ref: 'tests/test_config.py#test_phase4_llm_fields_accept_environment_overrides'
        status: pass
      - kind: unit
        ref: 'tests/test_config.py#test_phase4_non_positive_llm_retry_values_fail_closed'
        status: pass
      - kind: unit
        ref: 'tests/test_config.py#test_phase4_llm_temperature_zero_is_valid'
        status: pass
    human_judgment: false

duration: 29min
completed: 2026-07-02
status: complete
---

# Phase 04 Plan 01: LLM Dependency and Settings Summary

**Approved LLM SDK pins plus config-driven model, temperature, and retry controls for Phase 4 provider adapters.**

## Performance

- **Duration:** 29 min
- **Started:** 2026-07-02T03:29:37Z
- **Completed:** 2026-07-02T03:58:20Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments

- Added approved runtime pins: `anthropic==0.115.1`, `openai==2.44.0`, and corrected `structlog==25.5.0`.
- Installed the approved packages into the workspace `.python-userbase` and verified imports under Homebrew Python 3.14.
- Extended `Settings` with `anthropic_model`, `anthropic_temperature`, `openai_model`, `openai_temperature`, `llm_max_retries`, and `llm_retry_backoff_seconds`.
- Added config tests for defaults, environment overrides, fail-closed LLM retry controls, and valid zero temperatures.

## Approval Notes

- Task 1 approval was provided before execution for `anthropic==0.115.1`, `openai==2.44.0`, `Settings.openai_model = "gpt-4.1"`, and the D-07 temperature divergence.
- The initially approved `structlog==26.1.0` was unavailable from the configured PyPI index. Execution stopped twice at the mandated package checkpoint without leaving partial production changes.
- The operator then approved `structlog==25.5.0`; Task 2 resumed with that corrected exact pin.
- D-07 handling is unchanged: keep `Settings.anthropic_temperature = 0.0` for reproducibility logging/config symmetry, omit temperature from Anthropic requests, and send `temperature=0.0` to OpenAI.

## Task Commits

Each task was committed atomically:

1. **Task 1: Approve dependency pins, OpenAI model ID, and D-07 divergence** - checkpoint approval supplied by operator before execution
2. **Task 2: Pin and install LLM runtime dependencies** - `85094f0` (chore)
3. **Task 3 RED: Add failing tests for LLM settings** - `c5b31bf` (test)
4. **Task 3 GREEN: Add LLM settings pins and retry policy** - `6221ac3` (feat)

**Plan metadata:** committed separately during close-out.

## Files Created/Modified

- `pyproject.toml` - Added exact approved Anthropic/OpenAI/structlog runtime pins.
- `trading_bot/config.py` - Added Phase 4 LLM model/temperature fields and dedicated retry validation.
- `tests/test_config.py` - Added Phase 4 Settings coverage for defaults, overrides, fail-closed retries, and zero temperatures.
- `.planning/phases/04-llm-agent/04-01-SUMMARY.md` - Captures plan completion, approvals, deviations, and verification evidence.

## Decisions Made

- Used corrected operator-approved `structlog==25.5.0` because `structlog==26.1.0` was not available from the configured package index.
- Kept `openai_model` default as `gpt-4.1`.
- Kept Anthropic temperature advisory/log-only and OpenAI temperature transmitted, per the approved D-07 divergence.
- Used Homebrew Python 3.14 by prepending `/opt/homebrew/bin` to `PATH` for verification, matching the project’s Python 3.14 `.python-userbase` convention.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Corrected unavailable structlog pin after human verification**
- **Found during:** Task 2
- **Issue:** `structlog==26.1.0` was not available from the configured PyPI index; pip listed versions only through `25.5.0`.
- **Fix:** Stopped at checkpoint as required, received operator approval for `structlog==25.5.0`, and used that corrected exact pin.
- **Files modified:** `pyproject.toml`
- **Verification:** Import/version check printed `0.115.1 2.44.0 25.5.0`; full suite passed.
- **Committed in:** `85094f0`

**2. [Rule 3 - Blocking] Reconciled workspace userbase with Python 3.14**
- **Found during:** Task 2 verification
- **Issue:** The default `/usr/bin/python3` was Apple Python 3.9, which installed/imported incompatible compiled wheels in `.python-userbase`.
- **Fix:** Reinstalled the approved pins and transitive dependencies with Homebrew Python 3.14 using the workspace-local `PYTHONUSERBASE`; verification commands used `PATH="/opt/homebrew/bin:$PATH"` so `python3` resolved to 3.14.3.
- **Files modified:** `.python-userbase` runtime environment only
- **Verification:** Import/version check, config tests, and full suite passed under Python 3.14.
- **Committed in:** Not applicable; runtime environment repair only.

---

**Total deviations:** 2 auto-fixed/checkpoint-handled blocking issues.
**Impact on plan:** No scope expansion. The dependency set changed only after explicit operator approval, and the runtime repair aligned verification with the plan’s Python 3.14 convention.

## Issues Encountered

- Initial and retried installs for `structlog==26.1.0` failed because that exact version was unavailable from the configured package index.
- Homebrew Python required `--break-system-packages` with `--user` for the workspace-local install due to PEP 668.
- The default shell `python3` resolved to Apple Python 3.9; all passing verification used Homebrew Python 3.14.

## Verification

- `grep -nE '"(anthropic|openai|structlog)==' pyproject.toml` - PASS
- `PATH="/opt/homebrew/bin:$PATH" PYTHONUSERBASE="$PWD/.python-userbase" python3 -c "import anthropic, openai, structlog; print(anthropic.__version__, openai.__version__, structlog.__version__)"` - PASS, output `0.115.1 2.44.0 25.5.0`
- `PATH="/opt/homebrew/bin:$PATH" PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_config.py -x` - PASS, `28 passed`
- `PATH="/opt/homebrew/bin:$PATH" PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` - PASS, `245 passed`

## Known Stubs

None.

## Threat Flags

None - new package and Settings trust boundaries were already covered in the plan threat model.

## User Setup Required

None - no external service configuration required for this plan.

## Next Phase Readiness

Plans 04-03 and 04-04 can consume the new Settings fields and installed SDK/logging packages. The Anthropic adapter must omit temperature from requests while still logging `settings.anthropic_temperature`; the OpenAI adapter can send `settings.openai_temperature`.

## Self-Check: PASSED

- Found `.planning/phases/04-llm-agent/04-01-SUMMARY.md`.
- Found task commits `85094f0`, `c5b31bf`, and `6221ac3`.
- Verified no tracked file deletions in task commits.

---
*Phase: 04-llm-agent*
*Completed: 2026-07-02*
