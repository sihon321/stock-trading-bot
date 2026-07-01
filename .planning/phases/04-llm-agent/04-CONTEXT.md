# Phase 4: LLM Agent - Context

**Gathered:** 2026-07-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 4 delivers the LLM agent behind the already-existing synchronous `LLMProvider` port (`generate_signal(context: DataContext) -> LLMSignal`). It renders the compact Phase 3 `DataContext` (ticker, current price, flat technicals, capped sanitized news) into a prompt, calls the config-selected provider (Claude or OpenAI) using provider-native strict JSON structured output, and re-validates every response through the existing fail-safe `parse_signal` so any malformed or unparseable output fails safe to HOLD. Swapping Claude ↔ OpenAI is a config change (`Settings.llm_provider`), not a code change.

This phase does NOT implement real KIS order placement, broker idempotency/reconciliation, the persistent per-cycle audit store (SQLite), the manual CLI trigger, Telegram notifications, a scheduler, backtesting, ensemble/consensus across providers, or LLM ownership of position size/stop levels. Those remain Phase 5 or explicitly deferred/out-of-scope requirements. The LLM only *proposes* a `{decision, confidence, reason}` signal — the deterministic Phase 2 rules layer still owns all trade math.

</domain>

<decisions>
## Implementation Decisions

### Prompt & Strategy Framing
- **D-01:** The system prompt frames the LLM as a **volatility-breakout analyst**, consistent with Phase 3's screener (ATR/historical-volatility + volume-expansion candidate selection). Decisions should cohere with how the candidate universe was chosen — not a generic neutral read.
- **D-02:** Confidence must be framed as a **calibrated, conservative** probability that the call is correct. The prompt explicitly instructs: reserve `confidence >= 0.8` for strong, corroborated setups, and default to HOLD when unsure. This keeps the deterministic BUY gate (`confidence >= 0.8`, EXEC-01) honest.
- **D-03:** The system prompt lives as a **versioned module constant** (e.g. a dedicated `trading_bot/prompts.py`), reviewed in git and unit-testable. A small **pure function** renders the `DataContext` into the prompt body — no runtime template files, no config-overridable prompt text (safety framing must not be silently weakened).
- **D-04:** The `reason` string is expected to be a **brief cited rationale** (1–3 sentences) that references the specific signals it acted on (e.g. "RSI 72 + volume 2× + breakout above 20-day high"), so the reproducibility log and later audit are actually reviewable.

### Schema & Re-validation
- **D-05:** Provider-native structured output does **not** replace the fail-safe boundary. Every provider response is serialized to JSON and routed through the existing `parse_signal` (Phase 2), **regardless of provider** — one audited gate owns the trade-or-HOLD decision (LLM-03). Provider-native structured output is the first line; `parse_signal` is the authoritative re-validation.
- **D-06:** The strict-JSON schema is defined as a **Pydantic `TradeSignal` mirror** of `LLMSignal` (decision enum, confidence 0.0–1.0, non-empty reason), used **only** as the provider I/O schema (`strict: true` tool for Anthropic, `parse()` text/response format for OpenAI). The canonical `LLMSignal` stays a frozen dataclass produced by `parse_signal` — the domain layer is not converted to Pydantic. The mirror must stay in lockstep with `LLMSignal` (guard with a test).

### Reproducibility & Failure Handling
- **D-07:** Per-provider **model ID and temperature live in `Settings`** (config-driven pinning, LLM-02). Defaults: `claude-opus-4-8` for Claude and an OpenAI equivalent, **temperature `0.0`** for determinism. Swappable without a code edit.
- **D-08:** The raw prompt, raw response, provider, model, temperature, and parsed outcome are logged as a **structlog JSON line now**. The persistent SQLite audit store is Phase 5 (OPS-02) and must not be pulled forward — Phase 4 emits the structured log line only.
- **D-09:** LLM calls are wrapped in **bounded tenacity retry with exponential backoff** (consistent with the Phase 3 KIS retry posture, reusing/aligning with existing retry defaults). After the bounded retries are exhausted — or on a refusal / non-schema-conforming response — the call **fails safe to HOLD / no-trade**.
- **D-10:** On failure the provider **raises a typed LLM error**, and the cycle wiring maps it to HOLD — mirroring how `SignalParseError` already maps to HOLD in `execution.py`. The provider does **not** manufacture a synthetic `{HOLD, 0.0, ...}` signal the LLM never emitted.

### Untrusted-News Delimiting
- **D-11:** Scraped news is wrapped in an **XML-tagged data block** (e.g. `<news_item>...</news_item>` inside a delimited untrusted-data section), with an explicit **system-prompt rule** stating everything in that block is untrusted reference data and any instructions embedded in it must be ignored (LLM-03). Belt-and-suspenders on top of Phase 3 sanitization.
- **D-12:** Phase 4 **trusts Phase 3's sanitization** (`DataContext.news` is already markup-stripped, instruction-stripped, and capped per D-06 of Phase 3) and only **delimits/frames** it. No second sanitization pass at prompt-build time — sanitization has a single owner.

### Claude's Discretion
The planner/researcher may choose: exact module and symbol names (`prompts.py`, `TradeSignal`, provider class names, the typed LLM error name); the provider factory/wiring shape that resolves `Settings.llm_provider` to a concrete provider (mirroring the `build_data_source` factory pattern); exact tenacity retry counts / backoff values consistent with the existing KIS defaults (`kis_max_retries`, `kis_retry_backoff_seconds`); the precise OpenAI default model ID; prompt token-budget handling; the exact structlog field names; and the specific delimiter tag names. The Anthropic/OpenAI SDK mechanics are locked by CLAUDE.md (forced tool use + `strict:true`; `responses.parse`/`chat.completions.parse`; no assistant prefill / `budget_tokens` on 4.6+ models).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Scope & Requirements
- `.planning/PROJECT.md` — Project purpose, safety-first posture, KR-market scope, and the three-pipeline architecture that places the LLM agent behind a switchable provider port.
- `.planning/REQUIREMENTS.md` — Defines Phase 4 requirements `LLM-01` (switchable provider interface), `LLM-02` (strict JSON via provider-native structured output, model + temperature pinned, raw prompt/response logged), and `LLM-03` (re-validate every signal; malformed → HOLD; news never followed as instructions).
- `.planning/ROADMAP.md` — Phase 4 goal, success criteria, dependency on Phase 3, and the note that provider swap must be config-only.
- `.claude/CLAUDE.md` — LOCKED tech stack for the LLM boundary: Anthropic forced tool use + `strict:true` (`claude-opus-4-8`, cost option `claude-sonnet-4-6`); OpenAI `responses.parse` / `chat.completions.parse` with a Pydantic model; pydantic v2 shared across the project; the "Strict JSON LLM Contract" section; and the 4.6+ constraint (no assistant prefill, no `budget_tokens` — both 400).
- `.planning/STATE.md` — Current phase state and accumulated project decisions.

### Prior Phase Decisions
- `.planning/phases/01-foundation/01-CONTEXT.md` — Typed settings, atomic KIS mode binding, single-active-LLM-provider selection, synchronous semantic ports, and the compact `DataContext`.
- `.planning/phases/02-mock-execution-core/02-CONTEXT.md` — Fail-safe parser behavior (malformed → HOLD, never repaired), risk-first execution, and the audit-event shape (`CycleAuditEvent`) the LLM outcome flows into.
- `.planning/phases/03-data-pipeline/03-CONTEXT.md` — Compact `DataContext` boundary (D-04), news sanitization as untrusted data (D-06), the KIS retry/backoff posture, and the adapter/transform/orchestrator split that produces the context the LLM consumes.

### Existing Code
- `trading_bot/ports.py` — The `LLMProvider` Protocol (`generate_signal(context: DataContext) -> LLMSignal`) the concrete provider(s) must satisfy structurally. Core ports stay adapter-free (guarded by `tests/test_ports.py`).
- `trading_bot/signal_parser.py` — `parse_signal` / `SignalParseError` — the ONLY fail-safe re-validation boundary. Provider output must route through this (D-05); mirror its validation rules in the Pydantic `TradeSignal` schema (D-06).
- `trading_bot/domain.py` — `Decision`, `LLMSignal`, `DataContext`, `Money`, `Ticker`. `LLMSignal` stays a frozen dataclass; `TradeSignal` (Pydantic) mirrors it.
- `trading_bot/config.py` — `Settings`, `LLMProviderName`, `active_llm_api_key`, `_require_selected_llm_key`. Extend with per-provider model ID + temperature (D-07).
- `trading_bot/execution.py` — Shows the established fail-safe pattern: `SignalParseError` → HOLD in `execute_signal_cycle`; the LLM typed-error → HOLD hand-off (D-10) must mirror this. The LLM signal ultimately feeds this cycle.
- `trading_bot/data_source.py` — `MarketDataSource.build_context` produces the compact `DataContext` the provider renders into a prompt.
- `tests/test_ports.py` — Import-boundary expectation: core ports do not import concrete adapters or SDK clients. Keep the LLM SDKs (`anthropic`, `openai`) out of the core/port modules.

### External SDK References
- `anthropic` and `openai` SDKs are **not yet in `pyproject.toml`** — planning must add them (pinned versions per CLAUDE.md: `anthropic` 0.40+, `openai` 2.44.0) alongside `structlog`. Exact current SDK syntax for forced tool use / structured outputs should be confirmed against the `claude-api` skill and the OpenAI docs during research/planning.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `LLMProvider` Protocol already exists in `ports.py` — the concrete provider(s) satisfy it structurally; no port rewrite.
- `parse_signal` / `SignalParseError` already implement the fail-safe boundary and its validation rules (decision enum, confidence 0.0–1.0, non-empty reason, reject bool-as-number, ignore extra fields). Reuse verbatim as the re-validation gate; mirror its rules in `TradeSignal`.
- `Settings.active_llm_api_key` / `LLMProviderName` already resolve exactly one provider + key per run — the provider factory consumes these.
- `execution.py`'s `SignalParseError → HOLD` mapping is the template for the LLM typed-error → HOLD hand-off (D-10).
- Phase 3's KIS adapter already uses tenacity bounded retry/backoff with configurable counts — reuse the same posture and align defaults for the LLM call (D-09).

### Established Patterns
- Domain types are stdlib frozen dataclasses/enums; only the config layer uses Pydantic. `TradeSignal` (Pydantic) is scoped strictly to provider I/O, not the domain layer (D-06).
- Ports are synchronous, semantic, adapter-free Protocols; concrete adapters are opt-in via factories (`build_data_source` is the reference pattern for a provider factory).
- Fail-safe is uniform: bad input never becomes a trade; failures resolve to HOLD via typed errors caught at the cycle boundary.
- Factories require the caller to inject collaborators (see `build_data_source` requiring the shared token manager) — the provider factory should be similarly injectable for offline tests.

### Integration Points
- `DataContext` (from `MarketDataSource.build_context`) → prompt render → provider call → provider structured output → `parse_signal` re-validation → `LLMSignal`.
- The resulting `LLMSignal` (serialized to the raw JSON `execute_signal_cycle` expects) flows into the Phase 2 parse → risk → execute chain — the risk net and confidence gates still own the final action.
- structlog line (D-08) is the Phase 4 reproducibility record; it becomes an input to the Phase 5 persistent audit store (OPS-02), not built here.

</code_context>

<specifics>
## Specific Ideas

- The LLM is a *proposer only* — the volatility-breakout framing (D-01) and conservative confidence calibration (D-02) exist to make its proposal cohere with the pipeline, but the deterministic rules layer remains the sole owner of trade math and safety gates.
- Double validation is intentional: provider-native strict output AND `parse_signal`. The user explicitly wants a single audited fail-safe gate rather than trusting provider guarantees alone.
- Reproducibility (model + temperature pinned, raw prompt/response logged) is a Phase 4 obligation (LLM-02), but only as a structlog line — the persistent audit store is deliberately left to Phase 5 to avoid scope creep.
- Prompt safety framing must be code-reviewed and non-overridable at runtime (D-03) — a weakened prompt is a safety regression, not a config tweak.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within Phase 4 scope. Adjacent capabilities were explicitly kept out: the persistent SQLite audit store, manual CLI trigger, and Telegram notifications remain Phase 5 (OPS-01/02/03); ensemble/consensus across both providers remains deferred (ENSEMBLE-01); dedicated prompt-injection hardening beyond delimiting + Phase 3 sanitization (quarantined sentiment model / dual-LLM privilege separation) remains deferred (HARDEN-01); reproducibility replay tooling beyond the structlog line remains deferred (HARDEN-02).

</deferred>

---

*Phase: 4-LLM Agent*
*Context gathered: 2026-07-01*
