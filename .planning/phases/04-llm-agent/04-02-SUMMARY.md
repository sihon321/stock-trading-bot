---
phase: 04-llm-agent
plan: 02
subsystem: llm-contract
tags: [llm, prompts, pydantic, structured-output, prompt-injection]

requires:
  - phase: 03-data-pipeline
    provides: DataContext with ticker, price, technicals, and sanitized news
  - phase: 02-mock-execution-core
    provides: parse_signal fail-safe validation boundary and LLMSignal domain type
provides:
  - Versioned SYSTEM_PROMPT and deterministic DataContext render_prompt contract
  - XML-delimited untrusted_news/news_item prompt data block
  - Strict TradeSignal pydantic provider I/O mirror of LLMSignal
affects: [04-llm-agent, llm-provider, prompt-rendering, structured-output]

tech-stack:
  added: []
  patterns: [pure prompt transform, XML untrusted-data delimiting, pydantic provider schema mirror]

key-files:
  created:
    - trading_bot/prompts.py
    - trading_bot/trade_signal.py
    - tests/test_prompts.py
    - tests/test_trade_signal.py
    - .planning/phases/04-llm-agent/04-02-SUMMARY.md
  modified: []

key-decisions:
  - "PROMPT_VERSION starts at string literal \"1\"."
  - "Prompt news delimiter tags are <untrusted_news> and <news_item>."
  - "TradeSignal forbids extra fields but leaves confidence range, bool rejection, and non-empty reason validation to parse_signal."

patterns-established:
  - "Prompt Contract: SYSTEM_PROMPT is a git-reviewed module constant and render_prompt is pure, deterministic, SDK-free, and config-free."
  - "Untrusted News Delimiting: news items pass through verbatim inside <untrusted_news>/<news_item> blocks; empty news renders an explicit no-news marker."
  - "Provider I/O Mirror: TradeSignal is a pydantic schema mirror kept in field-name lockstep with the LLMSignal dataclass."

requirements-completed: [LLM-02, LLM-03]

coverage:
  - id: D1
    description: "Versioned volatility-breakout SYSTEM_PROMPT and deterministic DataContext rendering with all six technical keys."
    requirement: LLM-02
    verification:
      - kind: unit
        ref: 'PATH="/opt/homebrew/bin:$PATH" PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_prompts.py -x'
        status: pass
    human_judgment: false
  - id: D2
    description: "News is XML-delimited as untrusted reference data and embedded instructions remain inside the data block only."
    requirement: LLM-03
    verification:
      - kind: unit
        ref: 'tests/test_prompts.py#test_news_items_are_wrapped_inside_one_untrusted_news_block_verbatim'
        status: pass
    human_judgment: false
  - id: D3
    description: "TradeSignal strict pydantic provider schema mirrors LLMSignal and round-trips through parse_signal."
    requirement: LLM-03
    verification:
      - kind: unit
        ref: 'PATH="/opt/homebrew/bin:$PATH" PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_trade_signal.py -x'
        status: pass
      - kind: unit
        ref: 'PATH="/opt/homebrew/bin:$PATH" PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_ports.py -x'
        status: pass
    human_judgment: false

duration: 6min
completed: 2026-07-02
status: complete
---

# Phase 04 Plan 02: Prompt and Trade Signal Contract Summary

**Versioned volatility-breakout prompt rendering plus a strict provider I/O schema mirror for LLM signal adapters.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-07-02T03:59:55Z
- **Completed:** 2026-07-02T04:05:12Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Added `trading_bot/prompts.py` with `PROMPT_VERSION = "1"`, a non-overridable `SYSTEM_PROMPT`, and deterministic `render_prompt(DataContext)`.
- Rendered ticker, current price, currency, sorted technicals, and news inside `<untrusted_news>` with each item in `<news_item>`.
- Added `trading_bot/trade_signal.py` with `TradeSignal`, a pydantic provider I/O schema that forbids extras and stays in field-name lockstep with `LLMSignal`.
- Added unit coverage for prompt framing, untrusted-news containment, deterministic rendering, schema strictness, and parse_signal round-trip.

## Task Commits

Each task was committed atomically:

1. **TDD RED: Prompt and TradeSignal contract tests** - `6e94881` (test)
2. **Task 1 GREEN: Versioned system prompt and pure DataContext render** - `bfeec27` (feat)
3. **Task 2 GREEN: TradeSignal pydantic mirror with lockstep guard** - `35b8e8d` (feat)

**Plan metadata:** committed separately during close-out.

_Note: The RED commit contains both TDD task test files; the GREEN implementation commits remain separated by task._

## Files Created/Modified

- `trading_bot/prompts.py` - Versioned system prompt constant and pure deterministic DataContext renderer.
- `trading_bot/trade_signal.py` - Strict pydantic provider I/O mirror of `LLMSignal`.
- `tests/test_prompts.py` - Prompt framing, rendering, untrusted-news, and determinism coverage.
- `tests/test_trade_signal.py` - Field lockstep, strict schema, enum, and parse_signal round-trip coverage.
- `.planning/phases/04-llm-agent/04-02-SUMMARY.md` - Plan completion record and verification evidence.

## Decisions Made

- `PROMPT_VERSION` is the string literal `"1"`.
- The outer untrusted data delimiter is `<untrusted_news>` and each item uses `<news_item>`.
- Empty news renders `(no news available)` inside the `<untrusted_news>` block.
- `TradeSignal` intentionally does not duplicate parser validation; `parse_signal` remains the single audited authority.

## Deviations from Plan

None from shipped functionality. Process note: the TDD RED commit combined both task test files before implementation; GREEN commits were still kept per task.

## Issues Encountered

None.

## Verification

- `PATH="/opt/homebrew/bin:$PATH" PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_prompts.py -x` - PASS, `6 passed`
- `PATH="/opt/homebrew/bin:$PATH" PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_trade_signal.py -x` - PASS, `4 passed`
- `PATH="/opt/homebrew/bin:$PATH" PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_prompts.py tests/test_trade_signal.py -x` - PASS, `10 passed`
- `PATH="/opt/homebrew/bin:$PATH" PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_ports.py -x` - PASS, `7 passed`

## Known Stubs

None.

## Threat Flags

None - the new prompt-injection and schema-drift surfaces were already covered by the plan threat model and have automated mitigations.

## User Setup Required

None - no external service configuration required for this plan.

## Next Phase Readiness

Plan 04-03 can consume `SYSTEM_PROMPT`, `render_prompt`, and `TradeSignal` directly when building provider adapters. Adapter tests should assert the delimiter names `<untrusted_news>` and `<news_item>` and prompt version `"1"`.

## Self-Check: PASSED

- Found `trading_bot/prompts.py`, `trading_bot/trade_signal.py`, `tests/test_prompts.py`, `tests/test_trade_signal.py`, and `.planning/phases/04-llm-agent/04-02-SUMMARY.md`.
- Found task commits `6e94881`, `bfeec27`, and `35b8e8d`.
- Verified no tracked file deletions in task commits.

---
*Phase: 04-llm-agent*
*Completed: 2026-07-02*
