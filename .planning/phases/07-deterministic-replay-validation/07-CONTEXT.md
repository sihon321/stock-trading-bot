# Phase 7: Deterministic Replay Validation - Context

**Gathered:** 2026-07-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Build a deterministic, offline replay path that feeds frozen historical inputs through the shipped candidate-selection, raw-signal parser, risk, sizing, and execution-gate logic. It proves reproducibility, boundary coverage, and policy-path behavior without contacting an LLM, KIS, Naver, pykrx, or the wall clock. This phase does not implement profitability backtesting, human-readable reports, broker-specific soak behavior, policy calibration, or automatic policy changes.

</domain>

<decisions>
## Implementation Decisions

### Scenario and fixture design
- **D-01:** Use a mixed fixture structure. Focused single-purpose cases are the default; add full-day, multi-ticker scenarios only where interactions between candidates or state materially matter.
- **D-02:** The initial catalog must cover the complete Phase 7 requirement set: BUY threshold boundaries, HOLD, SELL, malformed signals, stale data, stop-loss/take-profit overrides, daily-loss BUY blocking, sizing boundaries, and look-ahead rejection.
- **D-03:** Store explicit raw JSON signals for each ticker and evaluation point. Replay must pass them through the production parser rather than storing only pre-validated signal objects.
- **D-04:** OHLCV fixtures include the indicator warm-up period through the fixed evaluation date. Any attempt to access later data must fail immediately through an explicit future-access guard.

### Replay state progression
- **D-05:** Support two state modes. Focused cases start from their own explicit initial state; steps inside a full-day scenario carry cash, positions, and daily-loss state forward in order.
- **D-06:** Apply each fixture-defined deterministic fill immediately after its step so later tickers observe updated state.
- **D-07:** Phase 7 models complete fill and no fill only. Partial fills, ambiguous submissions, broker reconciliation, and restart recovery remain Phase 9 scope.
- **D-08:** Process multi-ticker scenarios in production screener-rank order, breaking equal scores by ascending ticker code.

### Manifest and stable result identity
- **D-09:** The manifest records hashes for the scenario, OHLCV, and raw-signal fixtures; the complete policy snapshot; code revision; initial cash, positions, and daily-loss state; fixed evaluation time and trading date; and fixture schema version.
- **D-10:** Compute stable result identity from both deterministic manifest inputs and ordered normalized outcomes. Identical inputs that produce different outcomes must yield different identities and expose nondeterminism.
- **D-11:** Represent code state with the Git commit plus a content hash of relevant tracked changes, allowing reproducible evidence from a dirty worktree without pretending it equals the clean commit.
- **D-12:** Include fixture-fixed evaluation time in deterministic identity. Keep actual invocation time, duration, and output path as observational metadata excluded from the stable identity.

### Operator output and policy comparison
- **D-13:** Default CLI output shows the stable result ID, scenario-level BUY/HOLD/SELL and blocked counts, and verification status. Expand ticker-level detail only for failed checks or differences from expected outcomes.
- **D-14:** Persist the complete manifest, ordered outcomes, and verification checks as normalized JSON. Human-readable daily and period reporting remains Phase 8 scope.
- **D-15:** Compare BUY-policy strictness as a gate funnel with explicit denominators: evaluated, selected, BUY-signaled, confidence-qualified, risk-qualified, validly sized, and order-eligible. Show HOLD, SELL, and blocked-reason counts with explicit denominators as well.
- **D-16:** CLI and JSON must state that replay validates policy paths rather than profitability. Do not generate P&L, return, win-rate, Sharpe, or similar performance metrics.

### Agent Discretion
- Choose fixture file layout, schema serialization details, CLI command/flag names, normalized JSON field names, hashing algorithm, and output-directory conventions consistent with the existing Python/Typer patterns.
- Define additional focused cases when needed to prove the locked requirements, provided they remain within deterministic policy-path validation.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone scope and locked requirements
- `.planning/PROJECT.md` — Core value, safety posture, v1.1 validation goal, and explicit exclusions for full backtesting and automation.
- `.planning/REQUIREMENTS.md` — REPLAY-01 through REPLAY-04 and the boundary against live LLM replay, profitability backtesting, reports, soak, and calibration.
- `.planning/ROADMAP.md` — Phase 7 goal, success criteria, Phase 6 dependency, and downstream phase boundaries.
- `.planning/STATE.md` — Evidence-first milestone constraints and accumulated implementation decisions.
- `.planning/phases/06-audit-evidence-cycle-boundaries/06-CONTEXT.md` — Stable run/ticker/order evidence semantics, timing boundaries, freshness policy, and downstream attribution requirements established for replay consumers.

### Existing production contracts
- `trading_bot/screener.py` — Pure offline candidate selection, stable score ordering, explicit trading date, and exclusion evidence.
- `trading_bot/signal_parser.py` — Canonical raw-signal validation and fail-safe malformed-signal behavior.
- `trading_bot/execution.py` — Production parser-to-risk-to-sizing-to-execution-gate path and dry-run boundary.
- `trading_bot/risk.py` — Pure stop-loss, take-profit, and daily-loss BUY-blocking rules.
- `trading_bot/audit_models.py` — Stable terminal outcomes, reason codes, failed stages, and normalized evidence contracts.
- `trading_bot/cli.py` — Existing configuration projection, candidate iteration, terminal-outcome conversion, and Typer integration patterns.
- `tests/test_screener.py` — Existing deterministic screener fixtures and boundary coverage patterns.
- `tests/test_execution.py` — Existing parser, threshold, risk precedence, sizing, HOLD/SELL, and no-side-effect integration expectations.

No external specifications were identified; project planning files and production contracts above are canonical.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `screen_candidates` and `ScreenerResult`: already form a pure, network-free screening boundary with stable `(-score, ticker)` ordering and explicit exclusion events.
- `run_decision_cycle`, `evaluate_signal_action`, and `build_order_intent`: provide the shipped raw-parser, risk-precedence, confidence, sizing, and execution decisions required by replay.
- `RiskConfig`, `DailyLossState`, and `evaluate_position_risk`: immutable explicit inputs allow state to be injected without settings or wall-clock access.
- `TickerOutcome`, `ReasonCode`, and `FailedStage`: provide the normalized vocabulary for ordered replay outcomes and blocked reasons.
- Existing tests in `tests/test_screener.py` and `tests/test_execution.py`: provide network-free fixture builders and established boundary cases to reuse.

### Established Patterns
- Decision-critical transforms are synchronous, immutable, and adapter-free; clocks and external collaborators are injected at boundaries.
- Unsafe or malformed input fails closed to exclusion or HOLD with machine-checkable evidence.
- Screener ordering is already deterministic: descending score with ticker-code tie-breaking.
- Typer is the operator interface; structured evidence remains provider-neutral and excludes raw provider payloads and secrets.

### Integration Points
- Add a replay-specific CLI entry point beside existing commands, but construct offline fixture adapters rather than calling `build_runtime`, which creates live KIS, pykrx, Naver, LLM, and wall-clock dependencies.
- Project frozen scenario data into the existing screener and execution configuration types instead of duplicating decision rules.
- Convert each step into an ordered normalized replay outcome compatible with Phase 6 reason and stage semantics, then feed those outcomes into the manifest/result-ID and gate-funnel layers.
- Keep normalized replay JSON separate from Phase 8 human-readable reporting and from Phase 9 broker-facing SQLite soak evidence.

</code_context>

<specifics>
## Specific Ideas

- A dirty worktree is allowed, but its relevant tracked changes must affect the recorded code-state hash.
- Future OHLCV access must be an observable hard failure, not merely prevented by convention.
- Policy comparison should reveal exactly where potential BUYs are filtered, while refusing to imply investment performance.

</specifics>

<deferred>
## Deferred Ideas

- Partial fills, ambiguous submissions, broker reconciliation, duplicate reruns, and restart recovery remain Phase 9 mock-soak scope.
- Human-readable daily and period reports remain Phase 8 scope.
- Profitability backtesting is outside v1.1; advisory policy calibration remains Phase 10 scope.

</deferred>

---

*Phase: 7-Deterministic Replay Validation*
*Context gathered: 2026-07-11*
