---
phase: 02-mock-execution-core
plan: 02
subsystem: execution
tags: [risk-engine, execution-rules, kill-switch, stop-loss, take-profit, pydantic-settings, dataclass, import-boundary, tdd]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: "Decision/OrderSide/Money/Order/Position/Ticker domain types, Broker Protocol, and Settings"
  - phase: 02-mock-execution-core (Plan 02-01)
    provides: "parse_signal / SignalParseError / ParsedSignal — the raw-JSON to LLMSignal boundary"
provides:
  - "trading_bot.config Settings execution/risk defaults (BUY/SELL thresholds, cash fraction, max position value, stop/take pct, daily-loss threshold)"
  - "trading_bot.risk — pure evaluate_position_risk (stop_loss/take_profit) and blocks_new_buy kill switch"
  - "trading_bot.execution — evaluate_signal_action, build_order_intent, execute_signal_cycle with risk-first ordering and CycleAuditEvent override evidence"
affects: [02-03, mock-broker, dry-run, cli-cycle]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure risk functions: explicit value-object inputs, no LLMSignal/settings/broker/network/logging dependency"
    - "Risk-first orchestration: parse-fail -> risk exit -> LLM action -> daily-loss kill switch -> order intent (no broker mutation)"
    - "Immutable CycleAuditEvent records parse diagnostics + risk override reason for repudiation-resistant audit"
    - "Import-boundary regression test per core module (no KIS/LLM/pykrx/HTTP/adapter imports)"

key-files:
  created:
    - trading_bot/risk.py
    - trading_bot/execution.py
    - tests/test_risk.py
    - tests/test_execution.py
  modified:
    - trading_bot/config.py
    - tests/test_config.py

key-decisions:
  - "BUY and SELL confidence thresholds are independent Settings fields both defaulting 0.8 (D-05); confidence gate is >= threshold."
  - "BUY sizing = floor(min(cash * buy_cash_fraction, max_position_value) / price); non-positive price or zero rounded quantity yields no order (D-06)."
  - "Risk is evaluated before LLM action; a risk SELL overrides a conflicting same-ticker LLM BUY/HOLD and records risk_override + override_reason (D-07/RISK-02)."
  - "Daily-loss kill switch (blocks_new_buy) gates new BUYs only; SELLs and risk exits remain allowed (D-08/RISK-03)."
  - "Stop-loss/take-profit evaluate fractional move against Position.average_price; non-positive entry/current price holds safely instead of trading (D-09/RISK-01)."
  - "execute_signal_cycle consumes Broker read-only (get_position); place_order is never called in this plan — that boundary lands in 02-03."

patterns-established:
  - "Pure risk net: risk.py imports only stdlib and trading_bot.domain; no settings, ports, parser, or execution import."
  - "Risk-first execution ordering with explicit audit event carrying override evidence."

requirements-completed: [EXEC-01, EXEC-02, EXEC-03, RISK-01, RISK-02, RISK-03]

coverage:
  - id: D1
    description: "Settings exposes independent BUY/SELL confidence thresholds (default 0.8), cash fraction, max position value, stop/take percentages, and daily-loss threshold with env overrides (D-05/D-06/D-08/D-09)."
    requirement: "EXEC-01"
    verification:
      - kind: unit
        ref: "tests/test_config.py#test_execution_and_risk_defaults_are_deterministic"
        status: pass
      - kind: unit
        ref: "tests/test_config.py#test_execution_and_risk_fields_accept_environment_overrides"
        status: pass
    human_judgment: false
  - id: D2
    description: "Pure stop-loss/take-profit risk net emits SELL against average price without any LLMSignal, and holds safely on no position/zero quantity/non-positive prices (RISK-01/D-09)."
    requirement: "RISK-01"
    verification:
      - kind: unit
        ref: "tests/test_risk.py#test_stop_loss_breach_emits_sell_without_llm_signal"
        status: pass
      - kind: unit
        ref: "tests/test_risk.py#test_take_profit_breach_emits_sell_without_llm_signal"
        status: pass
      - kind: unit
        ref: "tests/test_risk.py#test_non_positive_prices_hold_safely_rather_than_trade"
        status: pass
    human_judgment: false
  - id: D3
    description: "Daily-loss kill switch blocks new BUYs after breach while allowing SELL/risk exits (RISK-03/D-08)."
    requirement: "RISK-03"
    verification:
      - kind: unit
        ref: "tests/test_risk.py#test_daily_loss_kill_switch_only_gates_buys_not_risk_exits"
        status: pass
      - kind: unit
        ref: "tests/test_execution.py#test_daily_loss_breach_blocks_buy_but_allows_sell"
        status: pass
    human_judgment: false
  - id: D4
    description: "BUY requires Decision.BUY and confidence >= BUY threshold (EXEC-01/D-05)."
    requirement: "EXEC-01"
    verification:
      - kind: unit
        ref: "tests/test_execution.py#test_buy_requires_buy_decision_and_threshold"
        status: pass
    human_judgment: false
  - id: D5
    description: "BUY quantity uses cash fraction capped by max position value and current price (EXEC-02/D-06)."
    requirement: "EXEC-02"
    verification:
      - kind: unit
        ref: "tests/test_execution.py#test_buy_sizing_uses_cash_percent_and_max_cap"
        status: pass
      - kind: unit
        ref: "tests/test_execution.py#test_buy_sizing_zero_or_negative_price_yields_no_order"
        status: pass
    human_judgment: false
  - id: D6
    description: "SELL requires Decision.SELL, confidence >= SELL threshold, and an existing held position (EXEC-03/D-05)."
    requirement: "EXEC-03"
    verification:
      - kind: unit
        ref: "tests/test_execution.py#test_sell_requires_position_and_threshold"
        status: pass
      - kind: unit
        ref: "tests/test_execution.py#test_sell_order_intent_uses_full_held_quantity"
        status: pass
    human_judgment: false
  - id: D7
    description: "Parser failure is caught at the execution boundary and becomes HOLD/no-order with no broker mutation (D-01)."
    requirement: "EXEC-01"
    verification:
      - kind: unit
        ref: "tests/test_execution.py#test_parser_failure_becomes_hold_no_order"
        status: pass
    human_judgment: false
  - id: D8
    description: "Risk SELL overrides a conflicting same-ticker LLM BUY and records override evidence in ExecutionResult and CycleAuditEvent (RISK-02/D-07)."
    requirement: "RISK-02"
    verification:
      - kind: unit
        ref: "tests/test_execution.py#test_risk_override_suppresses_llm_action"
        status: pass
    human_judgment: false
  - id: D9
    description: "Core modules import no KIS/LLM/pykrx/HTTP/adapter code; risk.py additionally imports no settings/ports/parser/execution (import boundary)."
    requirement: "RISK-01"
    verification:
      - kind: unit
        ref: "tests/test_risk.py#test_risk_import_has_no_forbidden_module_side_effects"
        status: pass
      - kind: unit
        ref: "tests/test_execution.py#test_execution_import_has_no_forbidden_external_or_adapter_side_effects"
        status: pass
      - kind: unit
        ref: "tests/test_config.py#test_config_import_has_no_execution_or_risk_module_side_effects"
        status: pass
    human_judgment: false

# Metrics
duration: 4min
completed: 2026-07-01
status: complete
---

# Phase 2 Plan 02: Rules Risk Engine and Deterministic Execution Core Summary

**Pure LLM-independent risk net (stop-loss/take-profit + daily-loss kill switch) plus a risk-first execution decision core that gates BUY/SELL on configurable confidence thresholds, sizes BUYs by capped cash fraction, converts parser failures to HOLD, and lets risk exits override conflicting LLM actions with audit evidence — all without any broker mutation.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-07-01T00:26:01Z
- **Completed:** 2026-07-01T00:29:46Z
- **Tasks:** 3
- **Files modified:** 6 (4 created, 2 modified)

## Accomplishments
- `trading_bot/config.py`: added seven deterministic execution/risk fields to `Settings` — `buy_confidence_threshold`/`sell_confidence_threshold` (both default 0.8), `buy_cash_fraction`, `max_position_value`, `stop_loss_pct`, `take_profit_pct`, `daily_loss_threshold` — with independent env overrides and no new config system (D-05/D-06/D-08/D-09).
- `trading_bot/risk.py`: pure `evaluate_position_risk` emits SELL with reason `stop_loss`/`take_profit` against `Position.average_price`, and holds safely on no position, zero quantity, or non-positive prices; `blocks_new_buy` arms the daily-loss kill switch as a BUY-only gate (RISK-01/RISK-03/D-08/D-09). Imports only stdlib + `trading_bot.domain`.
- `trading_bot/execution.py`: `evaluate_signal_action` gates BUY/SELL on decision + confidence threshold, `build_order_intent` sizes BUY by `floor(min(cash*fraction, max_cap)/price)` and SELL by full held quantity, and `execute_signal_cycle` orchestrates parse-fail → risk → LLM action → kill switch, letting a risk SELL override a conflicting LLM action with a `CycleAuditEvent` recording the override reason (EXEC-01/02/03, RISK-02, D-01/D-07).
- `Broker` is consumed read-only via `get_position`; `place_order` is never called in this plan (the dry-run/side-effect boundary lands in 02-03). Import-boundary tests confirm no KIS/LLM/pykrx/HTTP/adapter imports.

## Task Commits

Each task was committed atomically (TDD red → green):

1. **Task 1: Execution/risk settings defaults (RED)** - `83fc65e` (test)
2. **Task 1: Execution/risk settings defaults (GREEN)** - `4c00656` (feat)
3. **Task 2: Pure risk decisions (RED)** - `f9ccadf` (test)
4. **Task 2: Pure risk decisions (GREEN)** - `b0eb04d` (feat)
5. **Task 3: Execution rules + risk override (RED)** - `42060f3` (test)
6. **Task 3: Execution rules + risk override (GREEN)** - `0972131` (feat)

## Files Created/Modified
- `trading_bot/config.py` - Added execution/risk `Settings` fields with defaults and env overrides; existing safety gates, KIS grouping, LLM-key validation, and secret redaction unchanged.
- `trading_bot/risk.py` - `RiskAction`/`RiskConfig`/`DailyLossState`/`RiskDecision` and pure functions `evaluate_position_risk` + `blocks_new_buy`.
- `trading_bot/execution.py` - `ExecutionAction`/`ExecutionConfig`/`ExecutionResult`/`CycleAuditEvent` and functions `evaluate_signal_action`, `build_order_intent`, `execute_signal_cycle`.
- `tests/test_config.py` - Added defaults, env-override, and config import-boundary tests; extended `ENV_KEYS` cleanup so new fields do not leak across tests.
- `tests/test_risk.py` - 14 tests: frozen/enum shape, stop-loss/take-profit, safe-hold edge cases, daily-loss kill switch, import boundary.
- `tests/test_execution.py` - 11 tests: threshold gates, sizing cap, SELL position requirement, parser fail-safe, risk override audit, daily-loss BUY block/SELL allow, import boundary.

## Decisions Made
- Confidence gate uses `>=` so `confidence == threshold` qualifies (matches CLAUDE.md "BUY requires confidence >= 0.8").
- Chose local defaults for the fields the plan left to discretion: `buy_cash_fraction=0.1`, `max_position_value=1_000_000`, `stop_loss_pct=0.05`, `take_profit_pct=0.10`, `daily_loss_threshold=500_000` — conservative values consistent with a safety-first personal bot; all are env-overridable.
- `build_order_intent` returns `None` (no order) when a qualified action rounds to zero quantity or hits a non-positive price; `execute_signal_cycle` then downgrades the final action to HOLD with a "no valid order quantity" reason so no empty order can leak downstream.
- `blocks_new_buy` accepts `RiskConfig` for signature symmetry/future thresholds but arms solely on daily-loss state, keeping the kill switch a pure function of the cycle input.

## Deviations from Plan

None - plan executed exactly as written. All three tasks followed a clean RED → GREEN TDD cycle; no bugs, missing critical functionality, or blocking issues required deviation rules.

## TDD Gate Compliance

- Task 1: RED `83fc65e` (2 failing config tests) → GREEN `4c00656`.
- Task 2: RED `f9ccadf` (module-missing collection failure) → GREEN `b0eb04d` (14 passing).
- Task 3: RED `42060f3` (module-missing collection failure) → GREEN `0972131` (11 passing).

Each behavior-adding task has a `test(...)` commit preceding its `feat(...)` commit.

## Issues Encountered
None during planned work. The Python 3.14 / pydantic native-extension environment noted in Plan 02-01 as a deferred issue is repaired in this environment — `trading_bot.config` and pydantic `Settings` import correctly and the full suite is green.

## Known Stubs
None - `risk.py` and `execution.py` are fully implemented and wired. The only intentional deferral is broker mutation: `execute_signal_cycle` builds order intents but never calls `Broker.place_order`, matching the plan's explicit boundary for 02-03 (dry-run/mock-broker integration). This is documented, not a stub.

## User Setup Required
None - no external service configuration required. New settings fields have safe defaults and require no `.env` changes to run.

## Next Phase Readiness
- Plan 02-03 can wire `execute_signal_cycle`'s order intent into `MockBroker.place_order` behind the `dry_run` gate, reusing `ExecutionResult.order` and `CycleAuditEvent` for the audit log.
- Risk-first ordering and override evidence are in place; 02-03 completes the side-effect boundary and dry-run short-circuit.
- No blockers introduced.

## Self-Check: PASSED

- FOUND: trading_bot/risk.py
- FOUND: trading_bot/execution.py
- FOUND: tests/test_risk.py
- FOUND: tests/test_execution.py
- FOUND: trading_bot/config.py (modified)
- FOUND commits: 83fc65e, 4c00656, f9ccadf, b0eb04d, 42060f3, 0972131
- Plan-target subset: 63 passed. Full suite: 72 passed.

---
*Phase: 02-mock-execution-core*
*Completed: 2026-07-01*
