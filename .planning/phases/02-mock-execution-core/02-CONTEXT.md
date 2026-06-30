# Phase 2: Mock Execution Core - Context

**Gathered:** 2026-07-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 2 delivers the pure mock execution chain: fail-safe parsing of hand-written LLM signal payloads, deterministic execution rules, a rules-based risk net, and dry-run/mock-safe order decisions. It runs parse -> risk -> execute -> log with zero external calls and zero real financial risk.

This phase does not implement real KIS order placement, real broker idempotency, market data fetching, LLM provider calls, notifications, or the full operator CLI cycle. Those remain in later phases.

</domain>

<decisions>
## Implementation Decisions

### Signal Parser Behavior
- **D-01:** Malformed or schema-invalid signal input should raise an internal domain parse error. The execution chain must catch that error and convert it to HOLD/no-trade. No malformed or partial object may be repaired into a trade.
- **D-02:** Parser validation is strict for required fields and values but tolerant of extra JSON fields. Invalid cases include malformed JSON, missing required fields, unknown decision, confidence outside `0.0..1.0`, and empty reason. Extra fields are ignored.
- **D-03:** The parser only validates confidence range. BUY/SELL execution thresholds belong in the execution rules, not in parsing.
- **D-04:** Successful parsing should return a parsed wrapper rather than a bare `LLMSignal`. The wrapper should preserve the canonical `LLMSignal`, raw input, and non-sensitive diagnostics such as ignored extra fields or warnings.

### Execution and Risk Rules
- **D-05:** BUY and SELL use separate configurable confidence thresholds. Defaults should be `0.8` for BUY and `0.8` for SELL unless planning finds a stronger local default.
- **D-06:** BUY sizing should spend a configurable percentage of available cash, capped by a configurable maximum position value per ticker.
- **D-07:** Risk always wins over LLM actions. Stop-loss, take-profit, or kill-switch decisions suppress conflicting LLM actions and must be logged as overrides.
- **D-08:** Once the daily-loss threshold is breached, the kill switch blocks new BUY orders for the rest of the day while still allowing SELLs and risk exits.
- **D-09:** Stop-loss and take-profit evaluate current price against the position average price using configurable percentage thresholds.

### the agent's Discretion
The user did not delegate broad decisions wholesale. The planner may choose exact class/function names, diagnostic object shape, and test fixture organization consistent with the decisions above.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Scope
- `.planning/PROJECT.md` - Defines project purpose, safety posture, active requirements, and key pending decisions.
- `.planning/REQUIREMENTS.md` - Defines Phase 2 requirements `EXEC-01`, `EXEC-02`, `EXEC-03`, `EXEC-05`, `RISK-01`, `RISK-02`, and `RISK-03`.
- `.planning/ROADMAP.md` - Defines Phase 2 goal, success criteria, dependencies, and phase boundary.
- `.planning/STATE.md` - Captures current phase state and Phase 1 decisions carried forward.

### Prior Phase Decisions
- `.planning/phases/01-foundation/01-CONTEXT.md` - Locks typed settings, atomic mock/real selection, minimal domain models, `LLMSignal`, and synchronous semantic ports.

### Existing Code
- `trading_bot/domain.py` - Provides `Decision`, `OrderSide`, `Ticker`, `Money`, `Order`, `Position`, `DataContext`, and `LLMSignal`.
- `trading_bot/ports.py` - Provides synchronous `Broker`, `LLMProvider`, and `DataSource` Protocols.
- `trading_bot/config.py` - Provides `Settings`, `dry_run`, and active mock/real KIS selection.
- `tests/test_domain.py` - Captures current domain model expectations and import-safety constraints.
- `tests/test_ports.py` - Captures current port shape and no-adapter-import expectations.

### External Specs
No external specs - requirements are fully captured in the project planning documents and decisions above.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `LLMSignal` already captures the canonical strict signal fields: `decision`, `confidence`, and `reason`.
- `Decision`, `OrderSide`, `Order`, `Position`, `Money`, and `Ticker` are frozen dataclass/enum primitives suitable for the execution and risk core.
- `Settings.dry_run` exists and should feed Phase 2 dry-run behavior where needed.

### Established Patterns
- Domain objects are standard-library dataclasses/enums, not Pydantic models.
- Ports are synchronous, semantic, and adapter-free.
- Existing tests assert that domain and port imports do not pull in concrete adapters, HTTP clients, LLM SDKs, or settings side effects.

### Integration Points
- The parser should convert raw signal payloads into the existing `LLMSignal` shape via a wrapper result.
- Execution should consume the parsed signal, current price, positions, and config-like thresholds to produce deterministic mock/dry-run order decisions.
- Risk logic should stay pure and testable so later real broker and data adapters can reuse it safely.

</code_context>

<specifics>
## Specific Ideas

- Invalid signal parsing is an internal exception path, not a user-facing crash path.
- Ignored extra JSON fields may be recorded as diagnostics, but they must not affect execution.
- Risk overrides should be explicit in logs/audit output so the operator can see why an LLM action was suppressed.

</specifics>

<deferred>
## Deferred Ideas

None - discussion stayed within phase scope.

</deferred>

---

*Phase: 2-Mock Execution Core*
*Context gathered: 2026-07-01*
