# Phase 13: Historical LLM Shadow Evaluation & Model Governance - Context

**Gathered:** 2026-10-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver FUT-02 and GOV-01: optionally call an LLM against frozen historical inputs and compare its observations with Phase 12 fixture signals, with bounded cost, resumable execution and attributable immutable evidence. Preserve deterministic replay as the canonical baseline. Shadow commands have no broker/configuration-write capability; applying a model or prompt is a separate manual policy decision. Dashboard, scheduling and real-money promotion belong to later phases.

</domain>

<decisions>
## Implementation Decisions

### Historical evaluation samples and inputs
- **D-01:** Default to at most 100 unique date/ticker evaluation units, deterministically stratified across the resolved Phase 12 interval, tickers, fixture BUY/HOLD/SELL, held/screened provenance and risk-trigger cases. Freeze the selected IDs, sampling algorithm/version and seed before calls; disclose missing strata and actual counts. Do not silently expand to the full three-year universe. Explicit operator overrides may enlarge the sample within a separately frozen budget.
- **D-02:** Build one immutable decision-time snapshot per unit from frozen historical sources using Phase 12 effective/known timestamps. Price, shipped indicators, membership, news and simulated held-position facts must be available at that cutoff. No current market/news/KIS queries, future labels, future corporate actions or account credentials in prompts. Missing optional historical news is visibly unavailable; missing required market/position evidence makes the unit ineligible with an explicit exclusion reason.
- **D-03:** Use holdings, cash, reservations and risk state from the canonical fixture replay at the decision cutoff for every compared variant. Held context is simulated and must not be described as a real historical broker snapshot. Keep the original fixture signal immutable and attributable. Invalid/missing fixtures remain visible as fail-safe baseline cases and must not enter valid-signal agreement denominators.
- **D-04:** Freeze the original fixture bundle, replay result, sampled inputs and source hashes. Show requested versus available dates, coverage, exclusions, missing news and hindsight limitations. A present-day model may have learned later events even when its prompt is time-bounded; label historical shadow results as potentially knowledge-contaminated advisory evidence, never a leakage-free historical forecast.

### Model and prompt comparison
- **D-05:** Default to one explicitly identified provider/model and the shipped prompt contract; allow an explicitly frozen comparison set with a conservative maximum of two model/prompt variants by default. All variants receive the same selected units and canonical portfolio snapshots. Run once per unit/variant by default; explicit repetitions have distinct identities and count toward the shared budget. No model search, prompt optimization or automatic winner deployment.
- **D-06:** Freeze system and rendered prompt content, template/version/hash, strict TradeSignal schema/version/hash, model identifier, requested generation settings and provider-specific rendering before dispatch. Record returned model identifiers separately when exposed; unknown settings or backend versions stay unknown rather than inferred. Prompt comparisons change one named factor at a time and expose provider-specific contract differences.
- **D-07:** Revalidate every returned decision/confidence/reason using the shipped strict parser. Preserve distinct SUCCESS, MALFORMED, REFUSAL, PROVIDER_ERROR, TIMEOUT/UNKNOWN and excluded/not-dispatched outcomes. A failed output has an attributable fail-safe no-action projection; never fabricate a successful HOLD signal or hide failures within agreement rates.
- **D-08:** Shadow execution may access only dedicated LLM credentials and frozen inputs, with no broker, live cycle, live audit writes, trading lease, settings/environment writes or policy promotion capability. Existing live provider adapters are patterns, not permission to reuse their coupled execution/retry/audit behavior. Enable Codex CLI only if enforceable isolation removes tools/file-write/trade capability and attributable model/budget facts are adequate; a prompt asking it not to write files is insufficient. Unsupported variants stop or are explicitly excluded, never silently substituted.

### Budgets, interruptions and resume
- **D-09:** Default shared run limits are 100 dispatched attempts, 200,000 aggregate input/output/reasoning tokens, USD 5 modeled spend and concurrency 1, including retries and all variants. Require a frozen run manifest with explicit finite limits and generation output ceilings before paid calls; user overrides are explicit and frozen. Record any non-USD cost in its native currency and use only a sourced, frozen conversion when enforcing a USD cap.
- **D-10:** Reserve a conservative per-call token/cost upper bound before dispatch using an attributable dated pricing record and all applicable billable dimensions. Check consumed plus outstanding reserved budgets, not completed calls alone. Stop before a call that cannot fit; unavailable pricing, unbounded usage or inadequate model attribution blocks paid dispatch. Distinguish actual provider usage/cost facts from estimates; absence is UNKNOWN, never zero. USD 5 is a planning assumption, not a claim of a guaranteed provider invoice cap.
- **D-11:** Default to one dispatched attempt per unit/variant with no automatic retry after dispatch. Timeouts, disconnects, interrupted in-flight calls and other uncertain responses retain a charged/reserved upper bound and an UNKNOWN outcome; resume must not blindly repeat them. A separately explicit retry has a new attempt identity, consumes remaining budget and retains the original evidence. Before-dispatch local validation failures do not consume a provider attempt.
- **D-12:** Persist an attributable dispatch intent before each provider call and finalized outcome afterward. On interruption stop new dispatches and preserve completed, pending and uncertain records. Resume only against identical inputs, sampling, prompt/schema, model/settings, pricing and limits; skip finalized units and freeze unresolved ones. Changed conditions require a new linked run rather than rewriting old evidence. Checkpoints/artifacts are immutable or append-only, conflict-safe and bounded; report PARTIAL/BUDGET_EXHAUSTED/INTERRUPTED honestly.

### Reports and manual governance
- **D-13:** Produce validated machine-readable evidence and a Korean CLI/text report. Show coverage and counts per provider/model/prompt, decision agreement/confusion matrix, confidence/action changes, malformed/refusal/error/unknown rates, usage and estimated/actual/unknown costs. Give explicit denominators for valid paired signals and for every attempted/eligible/excluded unit; rare risk cases remain separately visible.
- **D-14:** Compare both the raw signal and the action after shipped confidence, sizing and deterministic risk gates against the exact same baseline portfolio snapshot. Preserve parse-failure precedence and distinguish blocked BUY, HOLD, risk SELL and other reason codes. Report hypothetical actions as non-executable; baseline fixtures and portfolio replay remain canonical. Do not present sparse paired samples as a complete alternative portfolio return path.
- **D-15:** Agreement with a fixture is consistency evidence, not correctness or profitability. Default report judgment is descriptive and advisory, with NO_MEANINGFUL_DIFFERENCE or INSUFFICIENT_EVIDENCE when appropriate; expose the counts/materiality rule. Do not rank a model as safe to deploy based solely on agreement, small samples or lower cost, and do not claim calibrated confidence, statistical certainty or real-money readiness.
- **D-16:** Bind each output and report to immutable input/prompt/schema/provider/model identities, usage/pricing facts, validation outcome, code revision plus relevant code content hash and run/attempt identities. Frozen inputs do not make live model outputs deterministic: preserve the actual observed output, and distinguish repeat observations from offline report regeneration. Model/prompt promotion remains an outside, manual policy decision referring to this evidence; commands cannot approve, deploy, edit trading policy or relax Phase 9/10/11 safety gates.

### Agent Discretion

The user selected all four areas (`1,2,3,4`) and then explicitly instructed `다 권장으로 맞혀줘` (use recommended defaults for everything). D-01 selects the presented recommended option; D-02 through D-16 are agent-selected defaults under that delegation, not individually answered questions. Choose names, strict evidence/checkpoint schemas, deterministic sampling allocation, finite per-input/output bounds, timeout, materiality/evidence grading and report layout during research/planning while retaining these boundaries. Verify official current provider usage, pricing and isolation contracts before enabling a live adapter; no current prices/model IDs are asserted here. The defaults authorize design choices, not a paid evaluation run during discussion or implementation.

</decisions>

<canonical_refs>
## Canonical References

Downstream agents MUST read these before planning or implementing. No additional external spec/ADR was supplied in the discussion.

- `.planning/ROADMAP.md` — Phase 13 scope and four success criteria.
- `.planning/REQUIREMENTS.md` — FUT-02 and GOV-01 boundaries.
- `.planning/PROJECT.md` — Project value, strict signals and mock-first safety.
- `.planning/phases/10-advisory-risk-calibration-promotion-readiness/10-CONTEXT.md` — Read-only advisory evaluation, denominators and promotion boundaries.
- `.planning/phases/11-kis-portfolio-synchronization-intraday-exit-management/11-CONTEXT.md` — Daily evaluation, held context, risk and execution authority boundaries.
- `.planning/phases/12-full-portfolio-backtesting-market-friction-modeling/12-CONTEXT.md` — Time-visible historical data, frozen baseline and portfolio semantics.
- `.planning/phases/12-full-portfolio-backtesting-market-friction-modeling/12-VERIFICATION.md` — Verified Phase 12 evidence and limitations.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `trading_bot/backtest_inputs.py`: `decision_view` and frozen historical cutoff views.
- `trading_bot/backtest_engine.py`: canonical fixture replay, manifest and relevant source-content identity.
- `trading_bot/backtest_models.py`: strict frozen bundle/result and simulation evidence.
- `trading_bot/backtest_reporting.py`: validated saved evidence, Korean reports and safe output writes.
- `trading_bot/prompts.py`: deterministic `render_prompt`, held-position context, `PROMPT_VERSION` and untrusted-news delimiting.
- `trading_bot/trade_signal.py` and `trading_bot/signal_parser.py`: strict three-field signal validation.
- `trading_bot/llm_provider.py`: Claude, OpenAI and Codex CLI response handling patterns; current adapters couple retry/logging and return signals without a dedicated shadow usage/cost envelope.
- `trading_bot/execution.py` and `trading_bot/risk.py`: shipped gates and precedence; reuse only pure/read-only decision semantics without granting execution capability.

### Established Patterns
Frozen inputs, effective/known timestamps, explicit unknowns, stable content hashes, strict JSON, bounded diagnostics and conflict-safe artifacts. Never infer a successful HOLD from a provider failure. Keep historical simulations and advisory reports outside live state.

### Integration Points
Add a separate shadow-evaluation entry point consuming saved replay evidence and immutable snapshots. Provider-specific network access occurs only in an explicitly requested evaluation run. Sampling and report regeneration remain offline. Do not call `run_llm_cycle`, instantiate the broker or reuse live settings/audit/lease paths. CLI providers require structural isolation beyond prompt instructions.

</code_context>

<specifics>
## Specific Ideas

The user chose all four areas and delegated all remaining preferences to recommended defaults. Start with a reproducible representative sample and the shipped prompt; compare every variant using the same canonical state. Surface current-model hindsight contamination and incomplete cost/model facts explicitly.

</specifics>

<deferred>
## Deferred Ideas

None introduced by the user. Roadmap boundaries retain dashboard (Phase 14), scheduled automation (Phase 15) and controlled real-money promotion (Phase 16). Automatic prompt optimization, model deployment and full alternative portfolio-performance claims are outside this discussion.

</deferred>

---

*Phase: 13-historical-llm-shadow-evaluation-model-governance*
*Context gathered: 2026-10-01*
