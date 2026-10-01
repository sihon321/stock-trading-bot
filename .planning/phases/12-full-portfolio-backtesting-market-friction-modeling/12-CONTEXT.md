# Phase 12: Full Portfolio Backtesting & Market Friction Modeling - Context

**Gathered:** 2026-10-01
**Status:** Ready for planning
**Decision authority:** User selected all four discussion areas (`1,2,3,4`) and then explicitly instructed `다 권장으로 셋팅해줘`. The recommendations below are accepted defaults; there were no separate answers for each item.

<domain>
## Phase Boundary

An offline chronological Korean equity portfolio backtest using frozen market/universe/calendar/signal/cost inputs, one account ledger, modeled limit-order fills and reproducible gross/net reports. This is modeled strategy evidence, not live profitability proof or trading authorization. Historical LLM calls belong to Phase 13; web UI, scheduling and real-money activation belong to Phases 14–16.
</domain>

<decisions>
## Implementation Decisions

### Historical data and universe
- **D-01:** Default requested interval is three calendar years ending on the bundle's latest completed KRX session, with explicit start/end overrides. Persist resolved dates in the manifest; never resolve using the wall clock or silently shorten unavailable history. Handle leap-day subtraction explicitly. Report actual coverage and warm-up separately; insufficient requested coverage prevents a complete-evidence verdict.
- **D-02:** Use frozen KOSPI/KOSDAQ ordinary-share point-in-time membership and trading status with effective/known timestamps. Held tickers remain in the review universe. A fixed allowlist is an explicit limited-universe mode and must carry a survivorship limitation. No runtime network, KIS, LLM, pykrx or Naver access.
- **D-03:** Use daily unadjusted tradable OHLCV and versioned corporate-action events with known/effective times. Calculate indicator inputs with only then-known adjustment events; never mix retrospectively adjusted prices with raw execution prices. Splits/dividends/delistings require explicit ledger treatment. Missing required actions, calendar, prices or membership block new orders and invalidate complete-evidence claims; preserve held inventory and disclose unavailable valuation rather than inventing fills or zero prices.
- **D-04:** Use versioned frozen strict JSON signals with availability timestamps. Missing/malformed signals produce attributable HOLD. Reuse shipped screener, signal parser, thresholds, sizing and risk precedence; do not generate or optimize a new strategy.

### Chronological execution
- **D-05:** A decision at completed session t close may first create an execution opportunity on session t+1. No same-bar hindsight fills. Daily-close evaluation is the baseline; do not claim reconstruction of the live intraday watch worker from daily bars.
- **D-06:** Use one deterministic cash/holdings/open-intent ledger across sessions and tickers. Process existing fills/corporate actions/settlement, then held-position reviews, then screened-only candidates with stable ticker/rank tie-breaking. Reserve buy cash and sell quantity; no overlapping capital use, negative cash, short selling, leverage, or overselling.
- **D-07:** Baseline limit is frozen at the decision price using side-aware valid tick rounding. Model adverse-slippage opening fills only if the modeled price respects the limit and observed bar. A later daily-range touch is not proof of a fill. Daily volume caps are explicitly approximate ex-post execution evidence, never decision inputs; no fill at zero volume, suspension or single-price limit lock without explicit tradability proof.
- **D-08:** Bound per-symbol per-session aggregate fill volume, not independently per order. Baseline participation cap is 1% of observed session volume; stress cap is 0.5%. Allocate capacity deterministically, allow partial fills, expire unfilled residual at modeled session end, and require a fresh later decision for a new intent. No hidden automatic remainder retry.
- **D-09:** Maintain settled cash, reserved cash and pending settlement independently. Baseline uses an explicit conservative T+2 KRX-session sell-proceeds availability rule; same-session sale proceeds do not fund a BUY. Freeze this policy in the manifest and label its difference from broker-specific buying power. Realized costs/losses and end-of-day unrealized holdings are tracked separately; daily loss gate reuses the shipped semantics.
- **D-10:** Re-evaluate held stop-loss/take-profit at available daily decision observations using shipped risk rules; risk takes precedence over conflicting fixture signals. No intra-bar high/low path inference. With daily bars, any exit intention follows the same next-session timing policy.

### Market friction
- **D-11:** Cost profile is strict and versioned with effective date ranges, market, source/review metadata, fee on both sides, sell-only transaction tax and applicable surtax. Do not use today's tax rate across historical dates or infer a tax exemption. Unsupported market/date is a hard input error. No fixed brokerage fee may be presented as the owner's actual tariff.
- **D-12:** Baseline synthetic modeling defaults: commission 1.5 bps each side and adverse slippage 10 bps; stress: commission 3 bps and adverse slippage 25 bps. Label both as modeling assumptions. Taxes and tick sizes require separately reviewed date-effective source records. Report rounding and all cost components; use deterministic decimal money arithmetic.
- **D-13:** Gross is an attribution view over the same net-executed quantity/timing path, adding back explicit modeled cost/slippage drag. Net ledger always governs sizing/capacity. Do not run a zero-cost strategy with different fills and label that its gross counterpart. Compare baseline and stress independently with linked scenario identities.

### Reports and artifacts
- **D-14:** Produce deterministic machine-readable JSON evidence plus Korean terminal/text reports containing resolved date range, coverage/exclusions, equity curve, total modeled return, maximum drawdown, daily exposure, turnover, realized/unrealized P&L, fills/nonfills and cost breakdown. Include an optional frozen same-period index buy-and-hold benchmark; missing benchmark is visibly unavailable, not synthesized.
- **D-15:** Hash normalized input content, policy, cost/settlement/fill versions and relevant code identity into result identity. Exclude wall-clock timestamps, absolute local paths and presentation/output location. Same inputs reproduce trades, curves and ID; preserve source hashes and explicit unknowns.
- **D-16:** Provide credential-free `bot backtest run <bundle>`, with date/profile/output options and `bot report backtest <result>` for validated saved evidence. Runtime backtest/report commands cannot mutate live audit/soak/settings, start workers or acquire order capabilities. Output is idempotent/conflict-safe; malformed inputs fail with bounded sanitized diagnostics. Every report labels simulated results and data/model limitations and cannot grant promotion authority.

### Agent Discretion

Choose class/module/reason-code names, strict bundle schema, documentation details, test fixtures and bounded input sizes consistent with the existing frozen dataclass/Pydantic, decimal money, deterministic JSON, Typer and safe report writer patterns. Recommendations are defaults, not a claim that a complete three-year historical bundle already exists.
</decisions>

<canonical_refs>
## Canonical References

- `.planning/ROADMAP.md` — Phase 12 four success criteria and Phase 13 boundary.
- `.planning/REQUIREMENTS.md` — FUT-01.
- `.planning/PROJECT.md` — safety and KR-only scope.
- `.planning/phases/11-kis-portfolio-synchronization-intraday-exit-management/11-CONTEXT.md` — held-first universe, no duplicate/oversell authority and live intraday boundaries.
- `.planning/phases/10-advisory-risk-calibration-promotion-readiness/10-CONTEXT.md` — advisory-only, no policy mutation/promotion.
- `docs/operator-runbook.md` — existing manual operation and read-only reporting.
- `trading_bot/replay.py`, `trading_bot/execution.py`, `trading_bot/risk.py`, `trading_bot/screener.py`, `trading_bot/indicators.py`, `trading_bot/report_cli.py` — reuse and isolation contracts.
- No user-provided external spec. Date-effective market-rule references are documented in `12-RESEARCH.md` after primary-source review.
</canonical_refs>

<code_context>
## Existing Code Insights

- Replay has frozen fixtures, cutoff rejection, production screening/execution and content-addressed evidence. It resets account state per scenario and does not supply a multi-day portfolio ledger.
- MockBroker is immediate paper execution with full/no-fill variants and no cost/settlement/liquidity model; retain its shipped behavior and add a dedicated simulation adapter.
- Execution core has parse/risk/size gates and a dry-run path that produces an order without submission. Any random intent IDs must be normalized/replaced deterministically at the simulation boundary.
- Report CLI has lightweight settings, safe output delivery and strict result loading; extend this surface without constructing the live CLI runtime.
</code_context>

<specifics>
## Specific Ideas

Three-year default plus explicit shorter-period overrides; baseline and stress profiles; transparent incomplete coverage. No automatic historical downloader is required in this offline phase.
</specifics>

<deferred>
## Deferred Ideas

Historical live LLM shadow evaluations (Phase 13), responsive web dashboard (Phase 14), unattended scheduler (Phase 15), real-money pilot (Phase 16). Intraday historical reconstruction, account-specific margin/buying-power simulation and strategy optimization require additional scope.
</deferred>
