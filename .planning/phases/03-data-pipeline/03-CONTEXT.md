# Phase 3: Data Pipeline - Context

**Gathered:** 2026-07-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 3 delivers the real Korean-market data pipeline behind the existing synchronous `DataSource` boundary. It fetches daily OHLCV via pykrx, computes the baseline technical indicators needed for volatility-breakout screening, selects a daily candidate universe, fetches real-time KIS prices through a shared token manager, and fetches/sanitizes Naver Finance news. The output is a compact typed `DataContext` suitable for the later LLM phase, with source health and fail-safe behavior explicit enough that bad data cannot create a new trade.

This phase does not implement LLM provider calls, prompt construction, real KIS order placement, broker idempotency, notifications, a scheduler, backtesting, or portfolio optimization. Those remain in later phases or deferred requirements.

</domain>

<decisions>
## Implementation Decisions

### Safety Path
- **D-01:** Daily OHLCV freshness follows a hybrid policy by ticker state. For screener/new candidates, bad, empty, stale, or unusable data skips the ticker. For portfolio/existing holdings, bad data fails closed by freezing actions and forcing HOLD while recording the problem. For holidays/weekends or natural market closures, the pipeline may gracefully fall back to the last valid KRX trading day instead of treating the closure as an error.
- **D-02:** KIS real-time price access must use one shared cached token manager with bounded retry/backoff. If token refresh, throttling, or price fetch still fails after the bounded retry policy, the price is unavailable and safety policy applies rather than retrying aggressively.
- **D-03:** Whenever Phase 3 skips or freezes a ticker due to missing/stale/unavailable source data, it should record a structured audit event and also print a visible console warning during the run. The event should include ticker, source, reason, observed date/time, expected trading date when applicable, and action taken such as `SKIP_CANDIDATE` or `FORCE_HOLD`.

### Data Shape
- **D-04:** Concrete adapters may return rich internal typed results, but the public LLM-facing `DataContext` should remain compact. Keep the boundary oriented around ticker, current price, flat technical values, and capped sanitized news strings; source metadata and health can live in adapter/orchestration results rather than bloating the prompt context.
- **D-05:** The baseline indicator set should be tailored for volatility-breakout workflows without becoming a full technical-analysis pack. Include moving averages, RSI, volatility metrics such as ATR or historical volatility, and volume ratios. Do not require MACD or Bollinger Bands in Phase 3 unless research/planning finds a narrow reason.
- **D-06:** Naver news should stay structured internally, but render into `DataContext.news` only as capped sanitized strings. Sanitization must strip markup and prompt-like instructions so scraped news remains untrusted data for Phase 4.

### Screener Policy
- **D-07:** The daily screener should optimize for volatility-breakout readiness: liquid names with sufficient ATR/historical volatility and volume expansion. This is preferred over generic momentum-only or large-cap-only ranking.
- **D-08:** Candidate universe breadth should be configurable, with a setting such as `screener_max_candidates`. Default to a small operator-reviewable shortlist, but do not hard-code that as the only possible cap.
- **D-09:** Market inclusion should be configurable, defaulting to KOSPI + KOSDAQ with liquidity floors and the ability to restrict markets later.

### Screener Detail
- **D-10:** Screener ranking should treat ATR/historical volatility and a liquidity floor as primary inputs. Volume expansion and recent momentum rank within the surviving set.
- **D-11:** Low-liquidity, suspended, halted, or bad-data tickers should be hard-excluded before ranking by default. Liquidity floors and excluded ticker states should be configurable.
- **D-12:** Lock screener policy and safety constraints now, not exact thresholds or score weights. The planner/researcher should choose concrete thresholds and formulas after checking current pykrx/KRX behavior and data quality.

### Adapter Boundaries
- **D-13:** Split Phase 3 into source adapters plus pure transforms plus a thin `DataSource` orchestrator. pykrx, KIS token/price, and Naver news should be source-specific adapters; indicator calculation, screener scoring/filtering, and news sanitization should be pure/testable transforms.
- **D-14:** The KIS token manager should be built as shared KIS infrastructure now. Phase 3 price calls consume it first, and Phase 5 broker/order calls should be able to reuse it instead of creating a second token flow.
- **D-15:** Source-specific failures should be normalized at each adapter boundary. pykrx/KIS/Naver adapters convert vendor exceptions, empty frames, bad DOM, throttles, token failures, and source-specific bad data into typed unavailable/stale/source-health results so the orchestrator applies policy consistently.

### the agent's Discretion
The planner may choose exact module names, dataclass names, enum names, retry counts, refresh-margin defaults, indicator implementation details, and screener threshold defaults consistent with the decisions above. Exact scoring formulas and thresholds are intentionally left for planning/research after validating current pykrx/KRX/KIS behavior.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Scope
- `.planning/PROJECT.md` - Defines the project purpose, safety posture, KR-market scope, and data-pipeline role.
- `.planning/REQUIREMENTS.md` - Defines Phase 3 requirements `DATA-01`, `DATA-02`, `DATA-03`, `DATA-04`, and `DATA-05`.
- `.planning/ROADMAP.md` - Defines Phase 3 goal, success criteria, dependency on Phase 2, and research hints for KIS token TTL/rate limits, pykrx adjusted-price behavior, and Naver DOM instability.
- `.planning/STATE.md` - Captures current phase state and accumulated project decisions.

### Prior Phase Decisions
- `.planning/phases/01-foundation/01-CONTEXT.md` - Locks typed settings, atomic KIS mock/real configuration, synchronous semantic ports, and compact `DataContext`.
- `.planning/phases/02-mock-execution-core/02-CONTEXT.md` - Locks fail-safe parser behavior, risk-first execution, dry-run safety, and existing execution audit expectations.

### Existing Code
- `trading_bot/domain.py` - Provides `Ticker`, `Money`, `DataContext`, and related domain types used by data and execution.
- `trading_bot/ports.py` - Provides the synchronous `DataSource` Protocol that Phase 3 must satisfy.
- `trading_bot/config.py` - Provides `Settings`, grouped active KIS config via `active_kis`, and safety defaults.
- `trading_bot/execution.py` - Shows how current price, ticker, and broker state feed the execution cycle and fail-safe outcomes.
- `tests/test_ports.py` - Captures the import-boundary expectation that core ports do not import concrete adapters, pykrx, KIS, Naver, requests, or HTTP clients.

### External Specs
No external specs were provided during discussion. Current KIS API details, pykrx data behavior, and Naver Finance DOM behavior must be verified during research/planning before implementation.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `DataContext` already exists with `ticker`, `current_price`, flat `technicals`, and `news`. Phase 3 should preserve this as the compact LLM boundary while allowing richer adapter/orchestration internals.
- `DataSource.build_context(ticker)` is already a synchronous Protocol method. The concrete Phase 3 orchestrator should satisfy it structurally.
- `Settings.active_kis` already returns an atomic KIS credential group. KIS price/token code should consume that group rather than independent active fields.
- `ExecutionResult` and `CycleAuditEvent` already model safety-oriented audit data. Phase 3 should use similarly structured data-source audit events for skip/freeze decisions.

### Established Patterns
- Domain types are standard-library frozen dataclasses/enums rather than Pydantic models.
- Ports are synchronous, semantic Protocols and remain adapter-free.
- Existing tests guard core modules from importing pykrx, KIS, Naver, HTTP clients, or future concrete adapters.
- Phase 2 kept parser/risk/execution logic pure and testable where possible; Phase 3 transforms should follow the same pattern.

### Integration Points
- A concrete data-source orchestrator should build compact `DataContext` objects consumed by the future LLM provider.
- KIS price lookup must provide the `current_price` used by later execution/risk cycles.
- Screener output defines the candidate ticker universe for the manual evaluation cycle planned later.
- Data-source unavailability must resolve to `SKIP_CANDIDATE` or `FORCE_HOLD` policy before bad data can influence a BUY.

</code_context>

<specifics>
## Specific Ideas

- The user specifically wants volatility-breakout readiness reflected in both indicators and screener policy.
- Keep `DataContext` token-efficient for the LLM; rich source payloads are useful internally but should not automatically expand the prompt-facing object.
- Natural market closures should not produce noisy failures; last valid trading day fallback is acceptable for holidays/weekends.
- Alerts in Phase 3 mean structured audit plus console warning. Full notifications remain Phase 5 scope.

</specifics>

<deferred>
## Deferred Ideas

None - discussion stayed within Phase 3 scope. Exact KIS retry defaults, token refresh margin, screener thresholds, and ranking formula are intentionally deferred to research/planning within this phase, not to a later capability.

</deferred>

---

*Phase: 3-Data Pipeline*
*Context gathered: 2026-07-01*
