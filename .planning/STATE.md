---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
current_phase: 0
status: Awaiting next milestone
stopped_at: Completed 05-04-PLAN.md
last_updated: "2026-07-03T02:42:13.424Z"
last_activity: 2026-07-05
last_activity_desc: "Completed quick task 260705-ezc: Add Codex CLI subprocess LLM provider"
progress:
  total_phases: 5
  completed_phases: 5
  total_plans: 21
  completed_plans: 21
  percent: 100
paused_at: null
current_phase_name: real-money-readiness-operations
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-03)

**Core value:** Given fresh market data, the bot produces a trustworthy, machine-checkable trading signal and acts on it through KIS — without placing an order the rules don't justify.
**Current focus:** Planning next milestone (v1.0 shipped 2026-07-03)

## Current Position

Phase: Milestone v1.0 complete
Plan: —
Status: Awaiting next milestone
Last activity: 2026-07-04 — Completed quick task 260704-her: Add OAuth token authentication support for the Claude (Anthropic) LLM provider

## Performance Metrics

**Velocity:**

- Total plans completed: 24
- Average duration: 3 min
- Total execution time: 0.15 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1. Foundation | 3 | 9 min | 3 min |
| 01 | 3 | - | - |
| 02 | 3 | - | - |
| 03 | 6 | - | - |
| 04 | 4 | - | - |
| 05 | 5 | - | - |

**Recent Trend:**

- Last 5 plans: 01-01 (4 min), 01-02 (3 min), 01-03 (2 min)
- Trend: started

| Phase 01-foundation P03 | 2min | 2 tasks | 4 files |
| Phase 02 P01 | 4 | 2 tasks | 2 files |
| Phase 02 P03 | 4min | 3 tasks | 4 files |
| Phase 03 P01 | 6m | 2 tasks | 3 files |
| Phase 03 P02 | ~10m | 2 tasks | 5 files |
| Phase 03 P03 | ~3m | 1 tasks | 2 files |
| Phase 03 P04 | 14min | 2 tasks | 4 files |
| Phase 03 P05 | ~8m | 1 tasks | 2 files |
| Phase 04 P01 | 29min | 3 tasks | 4 files |
| Phase 04 P02 | 6min | 2 tasks | 5 files |
| Phase 04-llm-agent P03 | 5min | 2 tasks | 4 files |
| Phase 04-llm-agent P04 | 4min | 2 tasks | 4 files |
| Phase 05-real-money-readiness-operations P01 | 40min | 5 tasks | 11 files |
| Phase 05-real-money-readiness-operations P02 | 5min | 3 tasks | 4 files |
| Phase 05-real-money-readiness-operations P03 | 5min | 2 tasks | 4 files |
| Phase 05-real-money-readiness-operations P04 | 35min | 2 tasks | 3 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Phase 1]: Single typed `Settings` object with fail-closed secret validation.
- [Phase 1]: Mock and real KIS credential groups are selected atomically by `trading_mode`.
- [Phase 1]: Real trading mode requires a second explicit confirmation flag.
- [Phase 1]: Use minimal domain models, a typed LLM signal contract, and synchronous semantic Protocols.
- [Phase 01 Plan 01]: Dependency lock-in used exactly the human-approved pydantic-settings, pydantic, and pytest versions.
- [Phase 01 Plan 01]: Workspace-local PYTHONUSERBASE dependency setup is used because Apple system Python blocked editable installs.
- [Phase 01-foundation]: [Phase 01 Plan 02]: Selected LLM provider secrets are validated during Settings() construction so missing active secrets fail closed at startup.
- [Phase 01-foundation]: [Phase 01 Plan 02]: KIS mock and real credentials are exposed as complete groups; future adapters should consume settings.active_kis rather than independent active fields.
- [Phase 01-foundation]: [Phase 01 Plan 02]: Python 3.9-compatible Optional annotations are used instead of PEP 604 unions to avoid adding an extra typing backport dependency.
- [Phase 01-foundation]: [Phase 01 Plan 03]: Domain objects use stdlib enums and frozen dataclasses, keeping the core free of Pydantic and settings imports.
- [Phase 01-foundation]: [Phase 01 Plan 03]: Ports remain synchronous semantic Protocols so future adapters can satisfy them structurally without inheritance.
- [Phase 01-foundation]: [Phase 01 Plan 03]: LLMSignal captures the strict JSON signal shape now while fail-safe parsing remains deferred to later execution/LLM phases.
- [Phase ?]: [Phase 02 Plan 01]: parse_signal is the single strict raw-JSON to LLMSignal boundary; SignalParseError (a ValueError) fails closed to HOLD/no-trade and never repairs partial input.
- [Phase ?]: [Phase 02 Plan 01]: Parser validates confidence range 0.0..1.0 only (bool rejected); BUY/SELL execution thresholds deferred to Plan 02-02.
- [Phase ?]: [Phase 02 Plan 01]: ParsedSignal exposes ignored extra-field names as sorted non-sensitive diagnostics that cannot mutate the canonical LLMSignal.
- [Phase ?]: D-05: BUY/SELL confidence thresholds are independent Settings fields defaulting 0.8; execution gate uses >=.
- [Phase ?]: D-06: BUY sizing = floor(min(cash*buy_cash_fraction, max_position_value)/price); zero/non-positive price yields no order.
- [Phase ?]: D-07/RISK-02: Risk SELL overrides conflicting same-ticker LLM action; CycleAuditEvent records override reason. Broker.place_order deferred to 02-03.
- [Phase ?]: Dry-run gate lives in execution._finalize_cycle before Broker.place_order; dry_run defaults True (EXEC-05).
- [Phase ?]: MockBroker is a pure in-memory Broker: deterministic MOCK-N IDs, volume-weighted entry, fail-closed on invalid/oversell with zero mutation.
- [Phase ?]: Phase 3 source policy: pykrx adjusted prices (ohlcv_adjusted=True); Naver scraping disabled by default; KIS mock rate 0.5s/3 retries/1.0s backoff/600s refresh margin; Python floor raised to >=3.10
- [Phase ?]: pykrx OHLCV validated (schema/monotonic date/min rows/finite positive prices/nonneg volume/freshness) before AVAILABLE; natural-closure fallback via accepted_latest_date; vendor exceptions normalized to typed results (D-01/D-15)
- [Phase ?]: Indicators (sma/rsi/atr/historical_volatility/volume_ratio) fail closed to UNAVAILABLE with empty technicals on NaN warm-up rather than zero-valued signals (D-05)
- [Phase ?]: Screener hard-excludes unsafe tickers before ranking; volatility+liquidity dominate over momentum in ranking (D-07/D-10/D-11, plan 03-03)
- [Phase 04]: [Phase 04 Plan 01]: Approved LLM dependency pins are anthropic==0.115.1, openai==2.44.0, and corrected structlog==25.5.0.
- [Phase 04]: [Phase 04 Plan 01]: OpenAI model default is gpt-4.1; Anthropic temperature remains advisory/log-only and must be omitted from Anthropic requests.
- [Phase 04]: [Phase 04 Plan 02]: PROMPT_VERSION starts at string literal "1" and prompt news delimiter tags are <untrusted_news> and <news_item>.
- [Phase 04]: [Phase 04 Plan 02]: TradeSignal forbids extra fields but leaves confidence range, bool rejection, and non-empty reason validation to parse_signal.
- [Phase 04]: [Phase 04 Plan 03]: Claude adapter omits Anthropic sampling parameters but logs configured temperature; OpenAI adapter sends temperature through chat.completions.parse.
- [Phase 04]: [Phase 04 Plan 03]: Both LLM adapters serialize provider-native structured output and revalidate through parse_signal before returning LLMSignal.
- [Phase 04]: [Phase 04 Plan 03]: Installed openai==2.44.0 parse signature confirmed response_format and temperature support on chat.completions.parse.
- [Phase 04]: [Phase 04 Plan 04]: LLM provider selection is centralized in build_llm_provider; swapping Claude and OpenAI is a Settings.llm_provider change.
- [Phase 04]: [Phase 04 Plan 04]: run_llm_cycle maps LLMProviderError to audited HOLD with zero broker interaction and re-serializes successful signals through execute_signal_cycle.
- [Phase 05]: [Phase 05 Plan 01]: Only typer==0.26.8 was added; python-kis remains excluded per the approved direct-REST order path.
- [Phase 05]: [Phase 05 Plan 01]: Workspace verification uses /opt/homebrew/bin/python3.14 ahead of /usr/bin/python3 because Typer 0.26.8 requires Python >=3.10.
- [Phase 05]: [Phase 05 Plan 01]: Wave 0 scaffolds collect exact downstream test names while import-gating missing modules until later plans implement them.
- [Phase 05-real-money-readiness-operations]: [Phase 05 Plan 02]: KIS order-cash POST remains outside tenacity retry; only broker-truth query legs retry.
- [Phase 05-real-money-readiness-operations]: [Phase 05 Plan 02]: KISBroker requires a caller-provided KisOrderAccount and shared KisTokenManager; it does not open a second token flow.
- [Phase 05-real-money-readiness-operations]: [Phase 05 Plan 03]: SQLite audit stores structured decision fields plus correlation_id only; raw prompt/response remain in structlog.
- [Phase 05-real-money-readiness-operations]: [Phase 05 Plan 03]: Discord delivery is fail-soft with bounded retry and returns False on final failure.
- [Phase 05-real-money-readiness-operations]: [Phase 05 Plan 04]: CLI run orchestration is injectable; Typer commands stay thin wrappers over `run_cycle`.
- [Phase 05-real-money-readiness-operations]: [Phase 05 Plan 04]: Real KIS broker CLI construction requires one caller-owned shared `KisTokenManager` and a real account descriptor; no dummy live account values are invented.
- [Phase 05-real-money-readiness-operations]: [Phase 05 Plan 04]: Cycle-level failures send an immediate fail-soft notification and are also included in the single end-of-run consolidated summary.

### Pending Todos

None yet.

### Blockers/Concerns

None yet.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260704-her | Add OAuth token authentication support for the Claude (Anthropic) LLM provider, alongside the existing API-key auth | 2026-07-04 | 36eb806 | [260704-her-add-oauth-token-authentication-support-f](./quick/260704-her-add-oauth-token-authentication-support-f/) |
| 260705-ezc | Add Codex CLI subprocess LLM provider | 2026-07-05 | a22a615 | [260705-ezc-add-codex-cli-subprocess-llm-provider](./quick/260705-ezc-add-codex-cli-subprocess-llm-provider/) |

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-07-02T14:12:34Z
Stopped at: Completed 05-04-PLAN.md
Resume file: None

## Operator Next Steps

- Start the next milestone with /gsd-new-milestone
