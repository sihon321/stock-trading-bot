---
phase: 01-foundation
plan: 03
subsystem: foundation
tags: [python, dataclasses, enum, protocol, pytest, ports, domain]
requires:
  - phase: 01-01
    provides: [package skeleton, pytest configuration, local dependency setup]
  - phase: 01-02
    provides: [typed settings layer, config safety boundaries]
provides:
  - Stdlib enum/dataclass domain models for decisions, orders, positions, tickers, money, data context, and LLM signals
  - Runtime-checkable synchronous Protocol ports for broker, LLM provider, and data source adapters
  - Focused tests proving construction, import cleanliness, structural typing, and adapter absence
affects: [foundation, phase-02, phase-03, phase-04, phase-05]
tech-stack:
  added: []
  patterns:
    - Frozen stdlib dataclasses for core domain contracts
    - String-valued enums for machine-checkable decisions and order sides
    - Runtime-checkable structural Protocols over domain types
key-files:
  created:
    - trading_bot/domain.py
    - trading_bot/ports.py
    - tests/test_domain.py
    - tests/test_ports.py
  modified:
    - tests/test_domain.py
    - tests/test_ports.py
key-decisions:
  - "Domain objects use stdlib enums and frozen dataclasses, keeping the core free of Pydantic and settings imports."
  - "Ports remain synchronous semantic Protocols so future adapters can satisfy them structurally without inheritance."
  - "LLMSignal captures the strict JSON signal shape now while fail-safe parsing remains deferred to later execution/LLM phases."
patterns-established:
  - "Domain and port modules must not import config, vendor SDKs, concrete adapters, or execution modules."
  - "Future concrete adapters should implement Broker, LLMProvider, and DataSource structurally over domain types."
requirements-completed: [CFG-01, CFG-02, CFG-03]
coverage:
  - id: D1
    description: "Decision, OrderSide, Ticker, Money, Order, Position, DataContext, and LLMSignal exist as dependency-light stdlib domain contracts."
    requirement: CFG-01
    verification:
      - kind: unit
        ref: "PYTHONUSERBASE=.python-userbase python3 -m pytest tests/test_domain.py tests/test_ports.py -q"
        status: pass
      - kind: other
        ref: "PYTHONUSERBASE=.python-userbase python3 -m compileall trading_bot"
        status: pass
    human_judgment: false
  - id: D2
    description: "LLMSignal exposes the strict decision, confidence, and reason contract needed by later parser and provider phases."
    requirement: CFG-03
    verification:
      - kind: unit
        ref: "tests/test_domain.py#test_llm_signal_matches_strict_json_contract_shape"
        status: pass
    human_judgment: false
  - id: D3
    description: "Broker, LLMProvider, and DataSource are runtime-checkable synchronous Protocols using domain types and no concrete adapters."
    requirement: CFG-02
    verification:
      - kind: unit
        ref: "tests/test_ports.py"
        status: pass
      - kind: other
        ref: "python3 -c import boundary command for domain and ports"
        status: pass
    human_judgment: false
duration: 2min
completed: 2026-06-30
status: complete
---

# Phase 01 Plan 03: Domain Models and Semantic Ports Summary

**Stdlib domain contracts and runtime-checkable synchronous ports for future broker, data, and LLM adapters**

## Performance

- **Duration:** 2 min
- **Started:** 2026-06-30T14:11:33Z
- **Completed:** 2026-06-30T14:13:51Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Added `trading_bot.domain` with string-valued `Decision` and `OrderSide` enums plus frozen dataclasses for `Ticker`, `Money`, `Order`, `Position`, `DataContext`, and `LLMSignal`.
- Added `trading_bot.ports` with runtime-checkable synchronous `Broker`, `LLMProvider`, and `DataSource` Protocols over the domain types.
- Added focused tests proving domain construction, strict LLM signal shape, structural Protocol compatibility, synchronous methods, and import boundaries without config or concrete adapter side effects.

## Task Commits

Each task was committed atomically:

1. **Task 1: Write failing domain and port shape tests** - `683b858` (test)
2. **Task 2: Implement stdlib domain models and synchronous Protocol ports** - `45304cc` (feat)

## Files Created/Modified

- `trading_bot/domain.py` - Defines dependency-light domain enums and frozen dataclasses.
- `trading_bot/ports.py` - Defines semantic synchronous Protocols for future broker, LLM, and data adapters.
- `tests/test_domain.py` - Covers domain imports, construction, LLM signal shape, and adapter-free import behavior.
- `tests/test_ports.py` - Covers runtime-checkable structural Protocol behavior and synchronous port methods.

## Decisions Made

- Kept domain models in stdlib dataclasses/enums rather than Pydantic, matching D-09 and preventing settings/model validation dependencies from leaking into core types.
- Used `@runtime_checkable` Protocols so fake and future concrete adapters can be checked structurally at runtime without inheriting base classes.
- Represented `DataContext` as ticker, current price, technical indicators, and news, which is enough for later data and LLM phases without importing those adapters now.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed full-suite import-boundary test isolation**
- **Found during:** Task 2 (Implement stdlib domain models and synchronous Protocol ports)
- **Issue:** Focused tests passed, but full pytest failed because import-boundary assertions treated `trading_bot.config` loaded by earlier config tests as a new domain/ports import side effect.
- **Fix:** Changed those assertions to compare module import deltas instead of global process state.
- **Files modified:** `tests/test_domain.py`, `tests/test_ports.py`
- **Verification:** `PYTHONUSERBASE=.python-userbase python3 -m pytest -q` passed.
- **Committed in:** `45304cc`

**Total deviations:** 1 auto-fixed (Rule 1 test isolation bug)
**Impact on plan:** No product scope changed; the fix made the new tests reliable when run in the full project suite.

## Issues Encountered

- The focused RED test run failed as intended because `trading_bot.domain` and `trading_bot.ports` did not exist yet.
- A source scan for stub patterns found `news=[]` only in a fake test data source; this is intentional test data, not a production stub.

## Auth Gates

None.

## Known Stubs

None.

## User Setup Required

None. Local verification on this machine should continue to use `PYTHONUSERBASE=.python-userbase` unless a replacement project-local environment is established.

## Next Phase Readiness

Phase 2 can now build the mock execution core against stable `Order`, `Position`, `LLMSignal`, and `Broker` contracts. Later data and LLM phases can implement `DataSource` and `LLMProvider` without changing the foundation boundary.

## Self-Check: PASSED

- Found task commits: `683b858`, `45304cc`
- Found created files: `trading_bot/domain.py`, `trading_bot/ports.py`, `tests/test_domain.py`, `tests/test_ports.py`
- Verification passed: `PYTHONUSERBASE=.python-userbase python3 -m pytest tests/test_domain.py tests/test_ports.py -q`
- Verification passed: `PYTHONUSERBASE=.python-userbase python3 -m pytest -q`
- Verification passed: `PYTHONUSERBASE=.python-userbase python3 -m compileall trading_bot`

---
*Phase: 01-foundation*
*Completed: 2026-06-30*
