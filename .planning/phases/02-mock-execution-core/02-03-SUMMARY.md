---
phase: 02-mock-execution-core
plan: 03
subsystem: execution
tags: [mock-broker, paper-account, dry-run, side-effect-gate, audit-log, import-boundary, tdd, integration-tests]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: "Order/OrderSide/Position/Ticker/Money domain types and the synchronous Broker Protocol"
  - phase: 02-mock-execution-core (Plan 02-01)
    provides: "parse_signal / SignalParseError / ParsedSignal — the raw-JSON to LLMSignal boundary"
  - phase: 02-mock-execution-core (Plan 02-02)
    provides: "risk.py (stop-loss/take-profit + daily-loss kill switch) and execution.py (execute_signal_cycle building order intents, no place_order)"
provides:
  - "trading_bot.mock_broker.MockBroker — deterministic in-memory paper account satisfying the Broker Protocol (BUY/SELL cash+position accounting, volume-weighted entry, MOCK-N order IDs)"
  - "trading_bot.execution dry-run side-effect gate: execute_signal_cycle gains a dry_run flag and _finalize_cycle centralizes the only Broker.place_order call, gated before the broker (EXEC-05)"
  - "CycleAuditEvent / ExecutionResult carry dry_run status and broker_order_id evidence for the per-cycle audit"
  - "Full Phase 2 parse -> risk -> execute -> log integration coverage across EXEC-01/02/03/05 and RISK-01/02/03"
affects: [phase-03, cli-cycle, kis-adapter, audit-persistence]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "In-memory paper broker: mutate cash/positions/order-history only through explicit place_order; reject invalid orders (non-positive qty, insufficient cash, oversell) with no mutation"
    - "Dry-run side-effect gate lives at the execution boundary, not inside the broker: _finalize_cycle is the single place_order call site, gated by `not dry_run and order is not None`"
    - "dry_run defaults to True (safety-first, mirrors Settings.dry_run) so any caller that omits the flag cannot place a live order"
    - "Cross-module import-boundary regression test spanning parser/risk/execution/mock_broker"

key-files:
  created:
    - trading_bot/mock_broker.py
    - tests/test_mock_broker.py
  modified:
    - trading_bot/execution.py
    - tests/test_execution.py

key-decisions:
  - "dry_run is a parameter of execute_signal_cycle defaulting to True; the gate lives in execution.py (_finalize_cycle) before Broker.place_order, never inside MockBroker (EXEC-05)."
  - "MockBroker volume-weights the average entry price on repeated BUYs and preserves entry price on partial SELLs; a full SELL removes the position entirely."
  - "MockBroker rejects invalid orders (qty <= 0, currency mismatch, insufficient cash for BUY, oversell for SELL) by raising ValueError with zero state mutation."
  - "MockBroker order IDs are deterministic sequential strings (MOCK-1, MOCK-2, ...) so integration tests can assert exact IDs."
  - "Deterministic order IDs and cash accounting keyed on order.quantity * limit_price.amount; no external calls, no config/KIS/LLM/HTTP imports."

patterns-established:
  - "Side-effect gate at the boundary: the broker mutation decision is made by the orchestrator, so tests prove zero place_order calls and zero mutation on dry runs."
  - "Paper account as a pure in-memory Broker implementation reusable by any future execution test."

requirements-completed: [EXEC-01, EXEC-02, EXEC-03, EXEC-05, RISK-01, RISK-02, RISK-03]

coverage:
  - id: D1
    description: "MockBroker satisfies the synchronous Broker Protocol, returns seeded positions without external calls, and both methods are non-coroutine."
    verification:
      - kind: unit
        ref: "tests/test_mock_broker.py#test_mock_broker_satisfies_broker_protocol"
        status: pass
      - kind: unit
        ref: "tests/test_mock_broker.py#test_mock_broker_methods_are_synchronous"
        status: pass
      - kind: unit
        ref: "tests/test_mock_broker.py#test_get_position_returns_seeded_position_without_external_calls"
        status: pass
    human_judgment: false
  - id: D2
    description: "MockBroker place_order gives deterministic unique IDs and mutates only in-memory cash/positions/history: BUY debits cash + volume-weights entry, SELL credits cash + trims/removes position."
    verification:
      - kind: unit
        ref: "tests/test_mock_broker.py#test_consecutive_orders_return_deterministic_unique_ids"
        status: pass
      - kind: unit
        ref: "tests/test_mock_broker.py#test_buy_increases_position_and_reduces_cash"
        status: pass
      - kind: unit
        ref: "tests/test_mock_broker.py#test_repeated_buys_average_the_entry_price"
        status: pass
      - kind: unit
        ref: "tests/test_mock_broker.py#test_sell_reduces_position_and_increases_cash"
        status: pass
      - kind: unit
        ref: "tests/test_mock_broker.py#test_full_sell_removes_the_position"
        status: pass
    human_judgment: false
  - id: D3
    description: "MockBroker fails closed: invalid quantity and oversell raise ValueError and leave state unchanged; import boundary loads no forbidden modules (T-02-09/T-02-10)."
    verification:
      - kind: unit
        ref: "tests/test_mock_broker.py#test_invalid_quantity_raises_and_does_not_mutate_state"
        status: pass
      - kind: unit
        ref: "tests/test_mock_broker.py#test_selling_more_than_held_raises_and_does_not_mutate_state"
        status: pass
      - kind: unit
        ref: "tests/test_mock_broker.py#test_mock_broker_import_has_no_forbidden_side_effects"
        status: pass
    human_judgment: false
  - id: D4
    description: "EXEC-05: dry-run BUY/SELL/risk-exit compute and log the would-be order but perform zero place_order calls and zero broker mutation (cash, positions, and order history unchanged before/after)."
    requirement: "EXEC-05"
    verification:
      - kind: integration
        ref: "tests/test_execution.py#test_dry_run_skips_broker_place_order_and_logs_intent"
        status: pass
      - kind: integration
        ref: "tests/test_execution.py#test_dry_run_leaves_mock_broker_state_unchanged_for_sell"
        status: pass
      - kind: integration
        ref: "tests/test_execution.py#test_dry_run_risk_exit_records_override_and_places_nothing"
        status: pass
      - kind: integration
        ref: "tests/test_execution.py#test_integration_exec_05_dry_run_vs_live_same_decision_different_effect"
        status: pass
    human_judgment: false
  - id: D5
    description: "Non-dry-run mock execution places exactly one order via place_order, records the deterministic broker_order_id, and mutates broker state only through place_order; HOLD places nothing."
    requirement: "EXEC-05"
    verification:
      - kind: integration
        ref: "tests/test_execution.py#test_live_run_places_buy_and_mutates_only_via_place_order"
        status: pass
      - kind: integration
        ref: "tests/test_execution.py#test_live_run_hold_places_no_order"
        status: pass
    human_judgment: false
  - id: D6
    description: "EXEC-01/02/03: valid at-threshold BUY produces a mock BUY sized by capped cash fraction; below-threshold BUY holds; held-position SELL at threshold sells in full; SELL without position holds; malformed signal fails closed to HOLD."
    requirement: "EXEC-01"
    verification:
      - kind: integration
        ref: "tests/test_execution.py#test_integration_exec_01_valid_buy_signal_produces_mock_buy"
        status: pass
      - kind: integration
        ref: "tests/test_execution.py#test_integration_exec_01_below_threshold_buy_does_not_trade"
        status: pass
      - kind: integration
        ref: "tests/test_execution.py#test_integration_exec_02_buy_sizing_respects_percent_and_cap"
        status: pass
      - kind: integration
        ref: "tests/test_execution.py#test_integration_exec_03_held_position_sell_produces_mock_sell"
        status: pass
      - kind: integration
        ref: "tests/test_execution.py#test_integration_exec_03_sell_without_position_does_not_trade"
        status: pass
      - kind: integration
        ref: "tests/test_execution.py#test_integration_malformed_signal_becomes_hold_no_trade"
        status: pass
    human_judgment: false
  - id: D7
    description: "RISK-01/02/03: stop-loss sells a held position without an LLM SELL; take-profit overrides and suppresses a same-ticker LLM BUY with logged override reason; daily-loss breach blocks new BUY while allowing SELL exits."
    requirement: "RISK-01"
    verification:
      - kind: integration
        ref: "tests/test_execution.py#test_integration_risk_01_stop_loss_sells_without_llm_sell"
        status: pass
      - kind: integration
        ref: "tests/test_execution.py#test_integration_risk_02_risk_suppresses_conflicting_llm_buy"
        status: pass
      - kind: integration
        ref: "tests/test_execution.py#test_integration_risk_03_daily_loss_blocks_buy_allows_exits"
        status: pass
    human_judgment: false
  - id: D8
    description: "T-02-10: parser, risk, execution, and mock_broker import no KIS/LLM/pykrx/requests/httpx or adapter-like local modules."
    verification:
      - kind: unit
        ref: "tests/test_execution.py#test_phase2_core_modules_import_no_forbidden_dependencies"
        status: pass
      - kind: unit
        ref: "tests/test_mock_broker.py#test_mock_broker_import_has_no_forbidden_side_effects"
        status: pass
    human_judgment: false

# Metrics
duration: 4min
completed: 2026-07-01
status: complete
---

# Phase 2 Plan 03: MockBroker, Dry-Run Side-Effect Gate, and Phase 2 Integration Summary

**Deterministic in-memory `MockBroker` paper account plus a dry-run side-effect gate in `execute_signal_cycle` (branching before `Broker.place_order`) — proving zero broker calls and zero mutation on dry runs — completed by full parse -> risk -> execute -> log integration coverage across every Phase 2 requirement.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-07-01T00:33:26Z
- **Completed:** 2026-07-01T00:37:40Z
- **Tasks:** 3
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments
- `trading_bot/mock_broker.py`: `MockBroker` satisfies the existing synchronous `Broker` Protocol with deterministic `MOCK-N` order IDs. BUY debits cash and volume-weights the average entry price; SELL credits cash and trims (or removes) the held position. Invalid orders — non-positive quantity, currency mismatch, insufficient cash, oversell — raise `ValueError` with zero state mutation. Imports only `trading_bot.domain`.
- `trading_bot/execution.py`: `execute_signal_cycle` gains a `dry_run` flag (default `True`, safety-first). A new `_finalize_cycle` helper is the single `Broker.place_order` call site, gated by `not dry_run and order is not None` — the gate lives at the execution boundary, never inside `MockBroker` (EXEC-05). `CycleAuditEvent` and `ExecutionResult` now carry `dry_run` status and `broker_order_id` so every cycle's audit records whether an order was placed and its broker ID.
- Full Phase 2 integration coverage: parse -> risk -> execute -> log exercised end-to-end for BUY, SELL, malformed input, stop-loss/take-profit risk exit, risk-override suppression of a conflicting LLM BUY, daily-loss kill switch, and dry-run vs live parity — with a cross-module import-boundary guard over parser/risk/execution/mock_broker.
- Targeted Phase 2 subset: 81 passed. Full suite: 101 passed (up from 72 baseline). Both plan verify commands exit 0.

## Task Commits

Each task was committed atomically (TDD red -> green):

1. **Task 1: MockBroker (RED)** - `875230e` (test)
2. **Task 1: MockBroker (GREEN)** - `899e6cf` (feat)
3. **Task 2: Dry-run gate + audit chain (RED)** - `2a59c48` (test)
4. **Task 2: Dry-run gate + audit chain (GREEN)** - `170fa1e` (feat)
5. **Task 3: Full Phase 2 integration verification** - `84e5808` (test)

## Files Created/Modified
- `trading_bot/mock_broker.py` - `MockBroker` in-memory paper account: `cash`/`order_history` properties, `get_position`, `place_order`, and private `_apply_buy`/`_apply_sell` with fail-closed validation.
- `trading_bot/execution.py` - Added `dry_run` param and `_finalize_cycle` side-effect gate; extended `CycleAuditEvent` (`dry_run`, `broker_order_id`) and `ExecutionResult` (`broker_order_id`). All prior return paths route through the single gated `place_order` call site.
- `tests/test_mock_broker.py` - 13 tests: Protocol conformance, synchronous methods, deterministic IDs, BUY/SELL accounting, averaging, full-sell removal, fail-closed invalid/oversell, import boundary.
- `tests/test_execution.py` - Added Task 2 dry-run/live tests (5) and Task 3 integration + cross-module boundary tests (13); existing 11 tests unchanged and still green.

## Decisions Made
- `dry_run` defaults to `True` on `execute_signal_cycle`. This keeps every pre-existing 02-02 test (which uses a `RecordingBroker` whose `place_order` raises) green unchanged, and matches `Settings.dry_run: bool = True` — a caller must opt in to live placement, so an omitted flag can never place a live order.
- The gate was implemented as a single `_finalize_cycle` helper rather than repeating the `place_order` branch in each of the four return paths (parse-fail, risk-exit, kill-switch, normal). This guarantees exactly one call site, which is what makes "zero place_order on dry run" provable and auditable.
- `MockBroker` volume-weights the average entry price on repeated BUYs (so audit/position data is meaningful for future risk evaluation) and preserves the entry price on partial SELLs.

## Deviations from Plan

None - plan executed exactly as written. All three tasks followed a clean RED -> GREEN TDD cycle. No bugs, missing critical functionality, or blocking issues required deviation rules. No package installs were attempted (T-02-SC honored: stdlib/domain + pytest only).

## TDD Gate Compliance

- Task 1: RED `875230e` (module-missing collection failure) -> GREEN `899e6cf` (13 passing).
- Task 2: RED `2a59c48` (5 failing dry-run tests, TypeError on unknown `dry_run` kwarg) -> GREEN `170fa1e`.
- Task 3: `84e5808` adds integration tests over already-green behavior (verification task); each Task-3 assertion passed on first run because Tasks 1-2 already implemented the exercised behavior. Task 1 and Task 2 each have a `test(...)` commit preceding their `feat(...)` commit.

## Issues Encountered
None. The Python 3.14 / pydantic native-extension environment is repaired; the full suite imports and runs cleanly.

## Known Stubs
None. `MockBroker` and the dry-run gate are fully implemented and wired. Phase 2 is complete: the parse -> risk -> execute -> log chain runs end-to-end against hand-written signals with zero external calls and zero real financial risk.

## User Setup Required
None - no external service configuration required. `MockBroker` is in-memory and needs no credentials; `dry_run` defaults to safe.

## Next Phase Readiness
- Phase 2 is demonstrably mock-safe, dry-run safe, adapter-free, and covered end-to-end by pytest.
- A future CLI/cycle can wire `execute_signal_cycle` with `dry_run=Settings.dry_run` and a `MockBroker` (or a real KIS adapter satisfying the same `Broker` Protocol) without touching the decision core.
- The `broker_order_id` and `CycleAuditEvent` fields are ready to feed the SQLite per-cycle audit log planned for a later phase.
- No blockers introduced.

## Self-Check: PASSED

- FOUND: trading_bot/mock_broker.py
- FOUND: tests/test_mock_broker.py
- FOUND: trading_bot/execution.py (modified)
- FOUND: tests/test_execution.py (modified)
- FOUND commits: 875230e, 899e6cf, 2a59c48, 170fa1e, 84e5808
- Targeted Phase 2 subset: 81 passed. Full suite: 101 passed. Both verify commands exit 0.

---
*Phase: 02-mock-execution-core*
*Completed: 2026-07-01*
