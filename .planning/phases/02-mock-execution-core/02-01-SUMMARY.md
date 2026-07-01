---
phase: 02-mock-execution-core
plan: 01
subsystem: execution
tags: [signal-parser, fail-safe, stdlib-json, dataclass, import-boundary, tdd]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: "Decision enum and LLMSignal frozen dataclass in trading_bot/domain.py"
provides:
  - "trading_bot.signal_parser.parse_signal — the sole raw-JSON to LLMSignal boundary for Phase 2"
  - "SignalParseError(ValueError) as the fail-safe/no-trade signal for malformed input"
  - "Frozen ParsedSignal wrapper preserving canonical signal, raw input, and ignored-field diagnostics"
affects: [execution, risk, mock-broker, 02-02, 02-03]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Untrusted raw JSON validated at a single strict parser boundary; no repair path to a trade"
    - "Fail-closed via a dedicated ValueError subclass rather than returning partial objects"
    - "Import-boundary test asserts core module loads no KIS/LLM/pykrx/requests/httpx/adapter/config modules"

key-files:
  created:
    - trading_bot/signal_parser.py
    - tests/test_signal_parser.py
  modified: []

key-decisions:
  - "Parser raises SignalParseError (a ValueError subclass) on any malformed/schema-invalid input; execution maps it to HOLD/no-trade (D-01)."
  - "confidence validated as numeric in 0.0..1.0 inclusive; bool explicitly rejected since bool subclasses int (D-02)."
  - "Parser validates confidence range only; BUY/SELL execution thresholds stay in Plan 02-02 (D-03)."
  - "ParsedSignal exposes ignored extra field names as sorted, non-sensitive diagnostics that cannot alter the canonical LLMSignal (D-04)."

patterns-established:
  - "Single strict parse boundary: parse_signal(raw_input: str) -> ParsedSignal or raise; no defaulting, no repair."
  - "Import-boundary regression test for every pure core module."

requirements-completed: [EXEC-01]

coverage:
  - id: D1
    description: "Strict fail-safe signal parser: valid JSON object returns ParsedSignal wrapping a canonical LLMSignal; extra fields ignored (D-01, D-02)."
    requirement: "EXEC-01"
    verification:
      - kind: unit
        ref: "tests/test_signal_parser.py#test_valid_payload_returns_parsed_signal_with_canonical_llm_signal"
        status: pass
      - kind: unit
        ref: "tests/test_signal_parser.py#test_extra_fields_are_ignored_and_do_not_change_canonical_signal"
        status: pass
    human_judgment: false
  - id: D2
    description: "Malformed JSON, non-object JSON, missing fields, unknown decision, out-of-range/non-numeric confidence, and blank reason all raise SignalParseError (D-01, D-02)."
    requirement: "EXEC-01"
    verification:
      - kind: unit
        ref: "tests/test_signal_parser.py#test_invalid_payloads_raise_signal_parse_error"
        status: pass
    human_judgment: false
  - id: D3
    description: "Parser validates confidence range only and accepts in-range BUY/SELL confidence below execution thresholds (D-03)."
    requirement: "EXEC-01"
    verification:
      - kind: unit
        ref: "tests/test_signal_parser.py#test_parser_accepts_in_range_confidence_below_execution_thresholds"
        status: pass
    human_judgment: false
  - id: D4
    description: "ParsedSignal preserves raw input and exposes ignored field names as non-sensitive diagnostics; parser import loads no forbidden external/adapter/config modules (D-04, import boundary)."
    requirement: "EXEC-01"
    verification:
      - kind: unit
        ref: "tests/test_signal_parser.py#test_ignored_field_names_are_observable_as_diagnostics"
        status: pass
      - kind: unit
        ref: "tests/test_signal_parser.py#test_signal_parser_import_has_no_forbidden_module_side_effects"
        status: pass
    human_judgment: false

# Metrics
duration: 4min
completed: 2026-07-01
status: complete
---

# Phase 2 Plan 01: Fail-Safe Signal Parser Summary

**Strict stdlib-json signal parser (`parse_signal`) that turns untrusted raw JSON into a canonical `LLMSignal` or raises `SignalParseError`, with an import-boundary test proving the parser pulls in no KIS/LLM/pykrx/HTTP/adapter/config code.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-07-01T00:17:29Z
- **Completed:** 2026-07-01T00:19:27Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- `trading_bot/signal_parser.py`: `parse_signal` is the single raw-JSON → `LLMSignal` boundary for Phase 2, failing closed via `SignalParseError(ValueError)` on any malformed or schema-invalid input (D-01).
- Strict field/value validation with tolerant extras: required `decision`/`confidence`/`reason`, known `Decision` values only, numeric confidence in `0.0..1.0` inclusive (bool rejected), non-blank reason; unknown keys ignored (D-02).
- `ParsedSignal` frozen wrapper preserves the canonical `LLMSignal`, the exact raw input, and sorted ignored-field names as non-sensitive diagnostics that cannot mutate the signal (D-04).
- Parser validates confidence range only — BUY/SELL execution thresholds are deferred to Plan 02-02 (D-03) — and an import-boundary test proves `trading_bot.signal_parser` loads only `trading_bot` and `trading_bot.domain`.

## Task Commits

Each task was committed atomically (TDD red → green):

1. **Task 1: Parser contract (RED)** - `6ca9dae` (test)
2. **Task 1: Parser contract (GREEN)** - `80d5325` (feat)
3. **Task 2: Diagnostics + import boundary (tests)** - `5fdb8f0` (test)

_Task 2's implementation was already satisfied by the Task 1 parser, so it produced a test-only commit — see TDD Gate Compliance below._

## Files Created/Modified
- `trading_bot/signal_parser.py` - `SignalParseError`, frozen `ParsedSignal`, and `parse_signal`; stdlib `json` parsing with strict validation and fail-closed behavior.
- `tests/test_signal_parser.py` - 27 tests covering valid parse, extra-field tolerance, parametrized invalid payloads, D-03 range-only behavior, D-04 diagnostics, and the parser import boundary.

## Decisions Made
- `SignalParseError` subclasses `ValueError` so it is a domain error execution can catch and map to HOLD/no-trade without a bespoke exception hierarchy.
- Booleans are explicitly rejected for confidence because `bool` subclasses `int` and would otherwise pass a numeric check (e.g. `True` → `1.0`).
- `ignored_fields` is sorted and limited to non-required key names, keeping diagnostics deterministic and free of raw values that could leak sensitive content.

## Deviations from Plan

None - plan executed exactly as written. Task 2 required no implementation change because the Task 1 parser was built to the full D-01–D-04 contract; Task 2's added tests (diagnostics + import boundary) passed against the existing implementation.

## TDD Gate Compliance

- Task 1 followed a clean RED (`6ca9dae`, tests fail on missing module) → GREEN (`80d5325`, 22 passing) cycle.
- Task 2 is a test-only commit (`5fdb8f0`): the new D-04 diagnostics and import-boundary assertions passed against the Task 1 implementation without modification, so there was no separate GREEN commit for Task 2. This is expected — the parser already met the full contract — and no RED was fabricated for behavior that already existed.

## Issues Encountered
None during planned work.

## Deferred Issues

- `tests/test_config.py` fails to **collect** in this environment with `ModuleNotFoundError: No module named 'pydantic_core._pydantic_core'` — a pre-existing Phase 1 issue where the installed `pydantic_core` native extension does not match the running Python 3.14 interpreter. It is unrelated to this plan (Phase 2 parser is pure stdlib) and out of scope per the deviation scope boundary. The plan's target command `pytest tests/test_signal_parser.py` exits 0, as do `tests/test_domain.py` and `tests/test_ports.py`.

## Known Stubs
None - `parse_signal` is fully implemented and wired; no placeholder values or unwired data paths.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Parser boundary is ready for Plan 02-02 execution rules: execution can call `parse_signal`, catch `SignalParseError` → HOLD/no-trade, and apply BUY/SELL confidence thresholds on top of the validated `LLMSignal`.
- No blockers introduced by this plan.

## Self-Check: PASSED

- FOUND: trading_bot/signal_parser.py
- FOUND: tests/test_signal_parser.py
- FOUND: .planning/phases/02-mock-execution-core/02-01-SUMMARY.md
- FOUND commits: 6ca9dae (test), 80d5325 (feat), 5fdb8f0 (test)

---
*Phase: 02-mock-execution-core*
*Completed: 2026-07-01*
