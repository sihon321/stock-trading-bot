# Phase 1: Foundation - Context

**Gathered:** 2026-06-30
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 1 delivers the safety-first Python foundation for the trading bot: a typed settings layer that loads gitignored secrets safely, atomically selects the mock or real KIS environment, exposes a loud non-secret startup safety summary, and defines the minimal domain models and semantic port Protocols later phases will build on. It does not implement concrete KIS, LLM, data, broker, or execution adapters.

</domain>

<decisions>
## Implementation Decisions

### Config and Mode Safety
- **D-01:** Use one typed `Settings` object for runtime configuration. It should load app mode, KIS credentials, active LLM provider, risk defaults where needed, and logging/safety flags from environment.
- **D-02:** Secret handling must fail closed. Required secrets for the selected active mode/provider must be validated at startup, secret fields must use redacted/secret-safe representations where practical, and tests must assert secrets do not leak through repr or logs.
- **D-03:** Represent KIS mock and real configuration as separate credential groups. Selecting `trading_mode` chooses one whole group, including domain and TR_ID policy, so endpoint, app key, app secret, and TR_ID cannot be mixed independently.
- **D-04:** Real trading mode requires a second explicit confirmation environment flag such as `CONFIRM_REAL_TRADING=yes`. `trading_mode=real` without that confirmation must fail startup.

### Domain Model and Port Boundaries
- **D-05:** Start with minimal core domain models: `Decision`, `Order`, `Position`, and small value objects such as `Ticker` or `Money` only if useful during planning.
- **D-06:** Include a typed LLM signal model now for the strict JSON contract: `decision`, `confidence`, and `reason`. Phase 1 defines the shared type; fail-safe parsing and enforcement happen in later phases.
- **D-07:** Define narrow semantic Protocols instead of adapter-shaped/vendor-shaped interfaces. Initial ports should represent business actions such as broker position lookup/order placement, LLM signal generation, and data context retrieval.
- **D-08:** Keep port contracts synchronous first. The v1 bot is manually triggered, and async should be introduced later only if concrete adapters need it.
- **D-09:** Use Pydantic for settings/env validation and standard-library dataclasses/enums for domain objects unless later implementation pressure justifies Pydantic domain models.

### Startup Behavior and Operator Feedback
- **D-10:** Print a safety summary startup banner containing active trading mode, KIS environment label, active LLM provider, dry-run setting if present, and whether real-trading confirmation is active. Secrets must always be redacted.
- **D-11:** Configuration failures should be actionable but non-secret. Errors may name the missing or invalid environment variable and active mode/provider context, but must never print secret values.
- **D-12:** Create a clear package skeleton for the foundation, such as `trading_bot/config.py`, `trading_bot/domain.py`, `trading_bot/ports.py`, plus tests.
- **D-13:** Phase 1 tests must be safety-focused unit tests covering settings loading, missing secrets failing closed, real mode requiring confirmation, secret redaction, domain model imports, and Protocol import/type shape.

### the agent's Discretion
No decisions were delegated wholesale to the agent. The planner may choose exact class, enum, and environment variable names consistent with the decisions above.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Scope
- `.planning/PROJECT.md` — Defines the project purpose, safety posture, constraints, and key decisions.
- `.planning/REQUIREMENTS.md` — Defines Phase 1 requirements `CFG-01`, `CFG-02`, and `CFG-03`; also notes `CFG-04` for mock-default/real-promotion safety.
- `.planning/ROADMAP.md` — Defines Phase 1 goal, success criteria, and phase boundaries.

### External Specs
No external specs — requirements are fully captured in the project planning documents and decisions above.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- No application source files exist yet. Phase 1 is expected to create the initial Python package skeleton.

### Established Patterns
- No existing Python package or test pattern exists yet. The planner should establish a simple, testable project layout rather than conforming to prior code.

### Integration Points
- Future phases will attach concrete KIS, pykrx/Naver, broker, and LLM adapters behind the semantic ports created in this phase.

</code_context>

<specifics>
## Specific Ideas

- Real mode should require both `trading_mode=real` and a deliberate confirmation flag.
- The startup banner is an operator sanity check, not a debug dump.
- Secret-related failures should identify variable names without printing values.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 1-Foundation*
*Context gathered: 2026-06-30*
