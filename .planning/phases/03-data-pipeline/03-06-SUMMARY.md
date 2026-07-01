---
phase: 03-data-pipeline
plan: 06
subsystem: data-pipeline
tags: [datasource, orchestrator, source-health, fail-safe, force-hold, skip-candidate, port-boundary, phase3-wave3]
requires:
  - phase: 03-02
    provides: "PykrxOhlcvAdapter (daily OHLCV, source-health) and calculate_technicals pure indicator transform"
  - phase: 03-03
    provides: "screen_candidates / build_screener_config pure screener (DATA-05)"
  - phase: 03-04
    provides: "KisTokenManager (shared token) and KisQuoteAdapter current-price adapter"
  - phase: 03-05
    provides: "NaverNewsAdapter compliance-gated fail-soft sanitized news"
provides:
  - "MarketDataSource: thin synchronous DataSource orchestrator composing OHLCV, indicators, KIS price, and Naver news"
  - "DataSourceConfig: point-in-time expected_date/accepted_latest_date/indicator policy inputs"
  - "DataSourceResult: rich internal action/audit outcome kept out of DataContext"
  - "NoContextError: fail-closed exception when policy forbids building a context"
  - "build_data_source / build_data_source_config: production wiring factories"
  - "Hardened tests/test_ports.py fresh-interpreter adapter-free boundary check"
affects: [04-llm-agent, 05-execution, prompt-assembly, cycle-orchestration]
tech-stack:
  added: []
  patterns: [thin-orchestrator, hybrid-freshness-policy, injected-adapters, fail-closed-no-context, source-health-guard, fresh-interpreter-boundary-test]
key-files:
  created:
    - trading_bot/data_source.py
    - tests/test_data_source.py
  modified:
    - tests/test_ports.py
key-decisions:
  - "MarketDataSource composes source adapters + pure transforms without re-implementing any of their logic (D-13)"
  - "Each required source is guarded sequentially; first non-AVAILABLE health resolves the whole pass to SKIP_CANDIDATE (candidate) or FORCE_HOLD (holding) via resolve_data_action (D-01)"
  - "Naver news is optional and fail-soft: an unavailable news source degrades to empty news and never blocks context (D-06)"
  - "build_context() (Protocol method) treats the ticker as a CANDIDATE and raises NoContextError rather than fabricating a zero/default-price DataContext (threat T-03-06-T)"
  - "DataContext stays compact (ticker/current_price/technicals/news only); all source health/audit lives on DataSourceResult (D-04, threat T-03-06-I)"
  - "build_data_source refuses to construct a KIS quote adapter itself — the caller must inject one built from the shared KisTokenManager so no second token flow is opened (D-14)"
patterns-established:
  - "Thin orchestrator: sequence typed adapter/transform results, apply policy, emit compact context — no vendor logic in the orchestrator"
  - "Source-health guard: one _guard helper resolves health->action, emits visible warning + audit event, and short-circuits the pass"
  - "Fresh-interpreter import test: subprocess re-imports ports.py in a clean sys.modules to prove no adapter leaks past in-process pollution"
requirements-completed: [DATA-01, DATA-02, DATA-03, DATA-04, DATA-05]
coverage:
  - id: D1
    description: "Healthy OHLCV + indicators + KIS price + sanitized news produce a compact DataContext with only ticker/current_price/technicals/news"
    requirement: "DATA-01"
    verification:
      - kind: integration
        ref: "tests/test_data_source.py#test_healthy_sources_produce_compact_context, test_context_carries_no_source_metadata_fields"
        status: pass
    human_judgment: false
  - id: D2
    description: "Missing/stale OHLCV or unavailable KIS price for a HOLDING resolves to FORCE_HOLD with typed audit + visible warning and no tradeable context"
    requirement: "DATA-01"
    verification:
      - kind: integration
        ref: "tests/test_data_source.py#test_stale_ohlcv_holding_forces_hold, test_unavailable_price_holding_forces_hold, test_build_context_raises_on_no_context_for_holding"
        status: pass
    human_judgment: false
  - id: D3
    description: "Bad OHLCV/indicators/price for a CANDIDATE resolves to SKIP_CANDIDATE before any candidate output"
    requirement: "DATA-05"
    verification:
      - kind: integration
        ref: "tests/test_data_source.py#test_unavailable_ohlcv_candidate_is_skipped, test_unavailable_indicators_candidate_is_skipped, test_unavailable_price_candidate_is_skipped"
        status: pass
    human_judgment: false
  - id: D4
    description: "Naver news failure degrades to empty news but still builds a valid context (fail-soft)"
    requirement: "DATA-04"
    verification:
      - kind: integration
        ref: "tests/test_data_source.py#test_news_failure_continues_with_empty_news"
        status: pass
    human_judgment: false
  - id: D5
    description: "screen_daily_candidates composes the pykrx adapter + pure screener, hard-excluding unsafe tickers before ranking"
    requirement: "DATA-05"
    verification:
      - kind: integration
        ref: "tests/test_data_source.py#test_screen_daily_candidates_composes_screener"
        status: pass
    human_judgment: false
  - id: D6
    description: "Core ports.py stays adapter-free and synchronous after Phase 3 modules exist; MarketDataSource structurally satisfies DataSource"
    requirement: "DATA-03"
    verification:
      - kind: unit
        ref: "tests/test_ports.py#test_ports_stay_adapter_free_in_fresh_interpreter, test_market_data_source_structurally_satisfies_data_source, test_market_data_source_satisfies_datasource_protocol"
        status: pass
    human_judgment: false
metrics:
  duration: ~12m
  completed: 2026-07-01
status: complete
---

# Phase 3 Plan 06: DataSource Orchestrator Summary

**Thin synchronous `MarketDataSource` wires pykrx OHLCV, pure indicators, KIS price, and sanitized Naver news behind the existing `DataSource` port, emitting a compact `DataContext` only when hybrid freshness policy permits — otherwise SKIP_CANDIDATE / FORCE_HOLD with typed audit and visible warnings.**

## Performance

- **Duration:** ~12 min
- **Completed:** 2026-07-01
- **Tasks:** 2 (both TDD)
- **Files modified:** 3 (2 created, 1 modified)

## Accomplishments
- `MarketDataSource` composes the four Wave 1–2 components in fixed order (OHLCV → indicators → KIS price → news) without re-implementing any adapter/transform logic (D-13).
- Hybrid freshness policy (D-01): the first non-AVAILABLE required source short-circuits the pass to `SKIP_CANDIDATE` (candidate) or `FORCE_HOLD` (holding), emitting a visible `DATA WARNING` and a `DataSourceAuditEvent` (D-03).
- Fail-closed `build_context()` raises `NoContextError` rather than returning a zero/default-price context, so bad data can never influence a trade (threat T-03-06-T).
- `DataContext` stays compact — a test asserts its fields are exactly `{ticker, current_price, technicals, news}` (D-04, threat T-03-06-I).
- `screen_daily_candidates` composes the pykrx market adapter with the pure screener for DATA-05.
- Hardened `tests/test_ports.py` with a fresh-interpreter subprocess import check proving `ports.py` pulls in no concrete adapters or external providers (threat T-03-06-E), plus a structural `DataSource` conformance assertion for `MarketDataSource`.

## Task Commits

Each task was committed atomically (TDD: test → feat):

1. **Task 1 (RED): failing integration tests** - `44240f4` (test)
2. **Task 1 (GREEN): implement MarketDataSource orchestrator** - `f4cc62c` (feat)
3. **Task 2: harden port boundary + conformance checks** - `f3db1e8` (test)

**Plan metadata:** (docs commit follows)

## Files Created/Modified
- `trading_bot/data_source.py` - `DataSourceConfig`, `DataSourceResult`, `MarketDataSource`, `NoContextError`, `build_data_source_config`, `build_data_source`. The thin orchestrator + production wiring factories.
- `tests/test_data_source.py` - 13 offline integration tests using fake adapters only; covers compact context, candidate skip, holding force-hold, unavailable OHLCV/indicators/price, news fail-soft, audit fields, console warnings, and screener composition.
- `tests/test_ports.py` - Added fresh-interpreter adapter-free boundary test and structural `MarketDataSource`/`DataSource` conformance test.

## Decisions Made
- `build_context()` treats the ticker as a CANDIDATE and fails closed via `NoContextError`; richer role-aware audit outcomes are exposed through `build_context_result(ticker, ticker_role)`.
- `build_data_source` deliberately refuses to auto-construct a KIS quote adapter — the caller owning the shared `KisTokenManager` must inject it, honoring the single-token-flow decision (D-14).
- Adapters and the indicator transform are injected via constructor so tests substitute fakes and no live vendor calls occur.

## Deviations from Plan
None - plan executed exactly as written. All Rules 1–4 untriggered.

## Issues Encountered
None. The `tests/test_ports.py` in-process boundary check is weakened once sibling tests import `data_source`/`kis_quote`; rather than weaken safety, a subprocess fresh-interpreter check was added to prove the boundary robustly.

## Threat Flags
None found — no new network endpoints, auth paths, file access, or schema at trust boundaries beyond those already registered in the plan's `<threat_model>`. All four registered threats (T-03-06-T/R/I/E) are mitigated and test-covered.

## User Setup Required
None - no external service configuration required for this plan.

## Next Phase Readiness
- Phase 3 data pipeline is complete: pykrx OHLCV, indicators, screener, KIS real-time price, and sanitized optional Naver news are composed behind a synchronous `DataSource` boundary with typed fail-safe outcomes.
- Phase 4 (LLM agent) can consume `MarketDataSource.build_context` / `build_context_result` for prompt assembly; the compact `DataContext` is prompt-ready and source metadata is isolated on `DataSourceResult`.
- Full suite green: 240 passed.

## Self-Check: PASSED

- `trading_bot/data_source.py` - FOUND
- `tests/test_data_source.py` - FOUND
- `.planning/phases/03-data-pipeline/03-06-SUMMARY.md` - FOUND
- Commits `44240f4`, `f4cc62c`, `f3db1e8` - FOUND

---
*Phase: 03-data-pipeline*
*Completed: 2026-07-01*
