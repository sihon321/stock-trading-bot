---
phase: 04-llm-agent
plan: 04
subsystem: llm-agent
tags: [llm-provider, factory, execution-cycle, fail-safe-hold, tdd]
requires:
  - phase: 04-03
    provides: ClaudeLLMProvider and OpenAILLMProvider adapters with LLMProviderError and parse_signal re-validation
provides:
  - build_llm_provider(settings, *, client=None) with lazy SDK imports and injected-client support
  - run_llm_cycle(provider, context, *, broker, available_cash, execution_config, risk_config, daily_loss_state, dry_run=True)
  - LLMProviderError to audited HOLD mapping with zero broker interaction
  - Provider-signal serialization into the unchanged execute_signal_cycle parse -> risk -> execute chain
affects: [phase-05-cli-trigger, phase-05-audit-store, llm-provider, execution-core]
tech-stack:
  added: []
  patterns:
    - Injectable factory with real SDK construction only when client is omitted
    - Provider failure maps to audited HOLD without synthetic LLMSignal construction
    - Provider success re-enters execute_signal_cycle as raw JSON for authoritative parsing
key-files:
  created:
    - .planning/phases/04-llm-agent/04-04-SUMMARY.md
  modified:
    - trading_bot/llm_provider.py
    - tests/test_llm_provider.py
    - tests/conftest.py
key-decisions:
  - "LLM provider selection is centralized in build_llm_provider; swapping Claude and OpenAI is a Settings.llm_provider change."
  - "Injected fake clients bypass active_llm_api_key.get_secret_value(); real SDK clients are the only code paths that surface API keys."
  - "run_llm_cycle catches only LLMProviderError and returns an audited HOLD without broker.get_position or broker.place_order."
  - "Successful provider signals are serialized to raw JSON and delegated to execute_signal_cycle so parse_signal, risk, sizing, and dry-run gates remain authoritative."
patterns-established:
  - "Factory pattern mirrors build_data_source: injectable collaborator defaults to None and real construction is lazy."
  - "LLM boundary failure pattern mirrors SignalParseError: typed error to HOLD with audit evidence and no order."
requirements-completed: [LLM-01, LLM-03]
coverage:
  - id: D1
    description: "build_llm_provider selects Claude or OpenAI adapters from Settings while keeping SDK imports lazy and injected clients secret-free."
    requirement: LLM-01
    verification:
      - kind: unit
        ref: "tests/test_llm_provider.py#test_build_llm_provider_selects_adapter_from_settings_value"
        status: pass
      - kind: unit
        ref: "tests/test_llm_provider.py#test_llm_provider_import_keeps_sdks_lazy_in_fresh_interpreter"
        status: pass
      - kind: unit
        ref: "tests/test_llm_provider.py#test_injected_client_does_not_surface_active_api_key"
        status: pass
    human_judgment: false
  - id: D2
    description: "run_llm_cycle maps LLMProviderError to audited HOLD with zero broker interaction."
    requirement: LLM-03
    verification:
      - kind: unit
        ref: "tests/test_llm_provider.py#test_error_maps_to_hold"
        status: pass
    human_judgment: false
  - id: D3
    description: "Successful LLM signals flow through the unchanged parse -> risk -> execute core under dry-run."
    requirement: LLM-03
    verification:
      - kind: integration
        ref: "tests/test_llm_provider.py#test_claude_run_llm_cycle_flows_into_dry_run_execution_chain"
        status: pass
      - kind: integration
        ref: "tests/test_llm_provider.py#test_run_llm_cycle_serializes_signal_for_execution_revalidation"
        status: pass
    human_judgment: false
duration: 4min
completed: 2026-07-02
status: complete
---

# Phase 04 Plan 04: LLM Factory and Cycle Wiring Summary

**Switchable Claude/OpenAI factory plus fail-safe LLM cycle wiring into the proven execution core**

## Performance

- **Duration:** 4 min
- **Started:** 2026-07-02T04:16:57Z
- **Completed:** 2026-07-02T04:20:39Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Added `build_llm_provider(settings, *, client=None) -> LLMProvider`, selecting Claude/OpenAI from `Settings.llm_provider` while keeping `anthropic` and `openai` imports lazy.
- Added `run_llm_cycle(provider, context, *, broker, available_cash, execution_config, risk_config, daily_loss_state, dry_run=True) -> ExecutionResult`.
- Proved LLM provider failures return audited HOLD with no `broker.get_position` or `broker.place_order` interaction.
- Proved successful fake-client BUY signals serialize back to raw JSON and pass through `execute_signal_cycle` for parser, risk, sizing, and dry-run enforcement.

## Task Commits

1. **Task 1 RED: factory tests** - `f9f229f` (`test`)
2. **Task 1 GREEN: factory implementation** - `c566530` (`feat`)
3. **Task 2 RED: cycle wiring tests** - `46c9f2d` (`test`)
4. **Task 2 GREEN: cycle wiring implementation** - `530fd6c` (`feat`)

## Files Created/Modified

- `trading_bot/llm_provider.py` - Added `build_llm_provider` and `run_llm_cycle` while preserving lazy SDK imports and adapter behavior.
- `tests/test_llm_provider.py` - Added factory, import-boundary, secret-confinement, failure-to-HOLD, dry-run chain, and re-validation tests.
- `tests/conftest.py` - Added `make_settings(**overrides)` with offline KIS credential groups and test LLM secrets.
- `.planning/phases/04-llm-agent/04-04-SUMMARY.md` - This execution summary.

## run_llm_cycle Contract

Signature:

```python
def run_llm_cycle(
    provider: LLMProvider,
    context: DataContext,
    *,
    broker: Broker,
    available_cash: float,
    execution_config: ExecutionConfig,
    risk_config: RiskConfig,
    daily_loss_state: DailyLossState,
    dry_run: bool = True,
) -> ExecutionResult:
```

Audit conventions:

- On `LLMProviderError`, returns `ExecutionAction.HOLD`, `order=None`, `reason="llm provider failed; fail-safe HOLD"`, and `audit.parse_error` prefixed with `llm_provider_error:`.
- The failure path does not call `broker.get_position` or `broker.place_order`.
- On success, the provider `LLMSignal` is serialized as `{"decision","confidence","reason"}` JSON and delegated to `execute_signal_cycle`.
- Dry-run behavior, broker placement, sizing, confidence gates, risk precedence, and parse validation remain owned by `execution.py`.

## Decisions Made

- Followed the existing `build_data_source` injectable collaborator pattern for `build_llm_provider`.
- Confined `.get_secret_value()` to real-client construction branches only.
- Kept `execution.py` unchanged; LLM cycle wiring lives in `llm_provider.py` and depends inward on public execution/risk types.
- Returned direct HOLD `ExecutionResult` on provider failure instead of fabricating a synthetic HOLD signal.

## Verification

- `PATH="/opt/homebrew/bin:$PATH" PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_llm_provider.py -x` -> `21 passed in 0.21s`
- `PATH="/opt/homebrew/bin:$PATH" PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_ports.py -x` -> `7 passed in 0.30s`
- `PATH="/opt/homebrew/bin:$PATH" PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` -> `276 passed in 12.82s`

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## Known Stubs

None. Stub-pattern scan found only intentional test recording lists and local adapter response-string initialization, not product placeholders.

## Threat Flags

None. The new factory secret boundary and LLM-to-execution boundary were both declared in the plan threat model and covered by tests.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Phase 5 can call `build_llm_provider(settings)` and `run_llm_cycle(...)` from the manual CLI trigger. The audit shape records provider failures as HOLD and preserves dry-run/order evidence from `execute_signal_cycle`.

## Self-Check: PASSED

- Summary file exists at `.planning/phases/04-llm-agent/04-04-SUMMARY.md`.
- Task commits exist: `f9f229f`, `c566530`, `46c9f2d`, `530fd6c`.
- Required files exist and tests passed.

---
*Phase: 04-llm-agent*
*Completed: 2026-07-02*
