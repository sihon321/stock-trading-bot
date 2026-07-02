# Phase 5: Real-Money Readiness & Operations - Context

**Gathered:** 2026-07-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 5 makes the proven parse → risk → execute chain operable and real-money-capable. It delivers: (1) a manual `typer` CLI that triggers a full evaluation cycle on demand across the screened candidate universe (OPS-01); (2) a persistent, reviewable SQLite audit store for every cycle (OPS-02); (3) a fail-soft notification push of each run's outcome (OPS-03); (4) an idempotent, reconciled real `KISBroker` order path behind the existing `Broker` port (EXEC-04); and (5) the deliberate, gated promotion from mock to real money (CFG-04).

This phase does NOT add a scheduler/always-on loop (out of scope — v1 is manual trigger), ensemble/consensus across LLM providers (deferred ENSEMBLE-01), backtesting, portfolio optimization, non-KR markets, or any change to the risk engine / confidence gates / signal parser (those are frozen from Phases 2–4). The LLM remains a proposer only; the deterministic rules layer still owns all trade math. The `KISBroker` satisfies the same synchronous `Broker` Protocol as `MockBroker` — no port rewrite. Mock remains the default target; real money is reachable only through the layered gate below.

</domain>

<decisions>
## Implementation Decisions

### CLI Trigger & Real-Money Gate (OPS-01, CFG-04)
- **D-01:** CLI command surface is `bot run`, `bot screen` (preview the candidate universe), and `bot status` (positions/cash) — the richest of the three sketched surfaces, matching the CLAUDE.md `typer` CLI recommendation.
- **D-02:** One `bot run` evaluates the **full screened universe by default**, looping the LLM → risk → execute chain over every candidate ticker; `--ticker <code>` narrows to a single ticker for testing/manual control. Per-ticker error isolation is expected (one ticker's failure must not abort the whole run) — see D-13.
- **D-03:** `bot run` is **dry-run by default** in both mock and real modes: a bare invocation logs the would-be decision/order and places nothing. Placing orders requires an explicit `--execute` flag. (Reuses the Phase 2 dry-run / EXEC-05 behavior as the default; `--execute` opts into the live path.)
- **D-04:** Real-money promotion is **layered**: the existing atomic config gate (`TRADING_MODE=real` requires `CONFIRM_REAL_TRADING=yes`, Phase 1) PLUS a **per-invocation CLI confirmation flag** (e.g. `--live-confirm`) required on any real-mode execute run. Non-interactive/automatable, but forces a deliberate act on every real run, not just a persisted setting. The loud Phase 1 startup banner still prints the active mode.

### Real KIS Order Path — Idempotency & Reconciliation (EXEC-04)
- **D-05:** **Library choice is deferred to research/planning.** The planner must compare (a) extending the existing Phase 3 direct-REST KIS layer (`kis_auth` shared token manager + httpx/tenacity posture) with order endpoints vs (b) introducing `python-kis` (CLAUDE.md's recommendation) — evaluated against the live KIS order-API docs and the existing code. The roadmap already flags KIS order params (TR_ID prefixes, hashkey, tick-size bands, market-hours codes) as needing API-specific verification before any real-money path. Whichever is chosen must NOT create a second, divergent auth/token path if the Phase 3 one can be reused.
- **D-06:** Idempotency is **defense-in-depth**: a deterministic client-generated order ID per (cycle, ticker, side) as the primary dedup key, PLUS a **query-before-resubmit reconciliation** — before (re)submitting any order the system queries KIS for account truth (recent orders/positions) and only POSTs if the intended order isn't already present. The system **never blind-retries an order POST**.
- **D-07:** **Partial fills are recorded AND reconciled**: after placing, query fill status; record filled-vs-requested quantity in the audit + notification, and update the tracked position to the actual filled quantity so the next cycle sees broker truth. **No auto-chase** within a cycle to complete an unfilled remainder — the operator reviews.
- **D-08:** Real orders are **limit orders at the current KIS real-time price** (respecting tick-size bands), consistent with the existing `Order.limit_price` field, PLUS a **market-hours / stale-data pre-flight guard** that fails safe to HOLD/skip if the market is closed or price data is stale (reusing Phase 3's stale-data fail-safe posture). No market orders.

### Persistent Audit Store (OPS-02)
- **D-09:** SQLite schema is **two normalized tables**: a `runs` table (run_id, timestamp, trading mode, dry_run flag, …) linked to a `decisions` table (one row per ticker decision in the run). Mirrors the universe-per-run model and makes both "what happened in run X" and "what did we decide on ticker Y" queryable.
- **D-10:** Persist **structured fields in SQLite** (the `CycleAuditEvent` fields + parsed signal + confidence + data snapshot + order outcome) with a **correlation ID pointing to the Phase 4 structlog line** that holds the raw prompt/response. Keeps the DB lean while remaining fully traceable to the reproducible raw record — the structlog line stays the home of raw prompt/response (no duplication).
- **D-11:** A **new persistence/writer module consumes the existing `CycleAuditEvent`** (plus signal/context/order) and writes to SQLite at a **configurable path** (default e.g. `./data/audit.db`, gitignored). `CycleAuditEvent` stays the in-memory shape — **no Phase 2 domain-type change**; the writer is the sink.

### Notifications (OPS-03)
- **D-12:** Notifications go through a small **`Notifier` Protocol/port** (consistent with the Broker/DataSource/LLMProvider port pattern), with a **Discord webhook adapter** as the concrete v1 implementation. Config holds the Discord webhook URL. Cycle code stays channel-agnostic so Telegram/Slack/email can be added later without touching cycle logic. **Divergence note:** REQUIREMENTS.md OPS-03 names Telegram as the *example* ("e.g. Telegram"); the operator chose Discord as the actual v1 channel — this satisfies OPS-03's intent (a notification channel), it is not a scope change. A Discord webhook is an `httpx` POST, so no new heavy dependency.
- **D-13:** Notification trigger is a **consolidated per-run summary** (each ticker's decision/order outcome in one message) PLUS an **immediate push on any cycle-level error/failure**. Avoids per-ticker spam while still alerting on failures. (This implies per-ticker error isolation in the run loop — a failing ticker is captured and reported, not fatal.)
- **D-14:** Notifications are **fail-soft with bounded retry**: best-effort delivery wrapped in a bounded tenacity retry (aligned with the Phase 3 KIS retry posture); on final failure it logs and the cycle continues. A notification failure **never crashes or blocks** the trading cycle — mirrors Phase 3's fail-soft Naver news. The order path and audit store are authoritative; the push is best-effort.

### Claude's Discretion
The planner/researcher may choose: exact module and symbol names (CLI module, `KISBroker`, `Notifier`, the persistence/writer module and its function names, Discord adapter name); the KIS order library decision itself (D-05) and the resulting order-endpoint mechanics (TR_ID, hashkey, tick-size band math, market-hours codes) after verification; exact `typer` sub-command/flag naming (`--execute`, `--live-confirm`, `--ticker` are indicative); the precise SQLite column set and indexes within the two-table shape (D-09); the correlation-ID scheme linking SQLite ↔ structlog (D-10); the default DB path and gitignore entry; the Discord message format/embed shape; and tenacity retry counts/backoff for the order-path reconciliation and notification delivery (align with existing `kis_max_retries` / `kis_retry_backoff_seconds`).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Scope & Requirements
- `.planning/PROJECT.md` — Project purpose, safety-first posture, mock-first / gated-real-money promotion, the three-pipeline architecture, and the "never place an order the rules don't justify" core value.
- `.planning/REQUIREMENTS.md` — Phase 5 requirements: `OPS-01` (manual CLI trigger, no scheduler), `OPS-02` (persist data context, LLM signal, risk decisions, order outcome to a reviewable store), `OPS-03` (push each cycle's decision/order outcome via a notification channel — Telegram is the example; Discord chosen per D-12), `EXEC-04` (idempotent KIS orders, reconcile against broker truth, never blind-retry, model partial fills), `CFG-04` (default mock; real requires a deliberate config change).
- `.planning/ROADMAP.md` — Phase 5 goal, success criteria, dependency on Phase 4, and the **research hint**: "KIS order params (TR_ID prefixes, hashkey, tick-size bands, market-hours codes) and the reconciliation/idempotency flow need API-specific verification before any real-money path."
- `.claude/CLAUDE.md` — Locked stack: `typer` CLI; `structlog`; SQLite via stdlib `sqlite3`; `python-kis` as the *recommended* order library (but see D-05 — decision deferred; direct KIS REST is the documented fallback). Also the mock (모의투자) account guidance and the "What NOT to use" list.
- `.planning/STATE.md` — Current phase state (Phase 5, verifying) and accumulated project decisions.

### Prior Phase Decisions
- `.planning/phases/01-foundation/01-CONTEXT.md` — Typed `Settings`, atomic KIS mock/real binding, `TradingMode` (defaults MOCK), `confirm_real_trading` gate, the loud startup banner, and the `Broker` Protocol skeleton. The Phase 5 real gate (D-04) layers onto this; `KISBroker` implements this port.
- `.planning/phases/02-mock-execution-core/02-CONTEXT.md` — `CycleAuditEvent` shape (D-11 persists this), the dry-run behavior (D-03 default), `MockBroker` reference implementation, and the fail-safe/HOLD discipline the whole cycle preserves.
- `.planning/phases/03-data-pipeline/03-CONTEXT.md` — Shared KIS token manager + retry/backoff posture (reuse candidate for D-05), stale-data fail-safe (reused by D-08), and the fail-soft Naver-news pattern that D-14 mirrors for notifications.
- `.planning/phases/04-llm-agent/04-CONTEXT.md` — The structlog reproducibility line (D-10 correlates SQLite to it), `run_llm_cycle` / `build_llm_provider` wiring the CLI drives, and the LLM-as-proposer boundary.

### Existing Code
- `trading_bot/ports.py` — `Broker` Protocol (`get_position`, `place_order(order) -> str`). `KISBroker` must satisfy it structurally; add a `Notifier` Protocol here (D-12) keeping ports adapter-free (guarded by `tests/test_ports.py`).
- `trading_bot/mock_broker.py` — `MockBroker` reference impl of `Broker`; template for `KISBroker`'s interface (not its network/idempotency logic).
- `trading_bot/execution.py` — `execute_signal_cycle`, `CycleAuditEvent`, `ExecutionResult` (`broker_order_id` already threaded for live orders). The audit writer (D-11) consumes `CycleAuditEvent`; the CLI drives this cycle per ticker.
- `trading_bot/llm_provider.py` — `run_llm_cycle` / `build_llm_provider` — the per-ticker cycle entry point the CLI orchestrates over the universe.
- `trading_bot/data_source.py` — `MarketDataSource.build_context` (data per ticker) and the `build_data_source` factory pattern to mirror for `KISBroker`/`Notifier` construction.
- `trading_bot/screener.py` — the volatility-breakout screener producing the candidate universe `bot run` / `bot screen` iterate over.
- `trading_bot/kis_auth.py`, `trading_bot/kis_quote.py` — the existing direct-REST KIS token manager + price adapter; the reuse candidate in the D-05 order-path decision.
- `trading_bot/config.py` — `Settings`, `TradingMode`, `confirm_real_trading`, `kis_max_retries`, `kis_retry_backoff_seconds`, the atomic `kis_active_credentials`. Extend with: audit DB path, Discord webhook URL, and any real-order settings.
- `pyproject.toml` — deps currently include `structlog`, `httpx`, `tenacity` (Discord webhook + REST reuse need no new heavy dep). `typer` is NOT yet a dependency and must be added; `python-kis` would be added only if D-05 selects it. `sqlite3` is stdlib.
- `tests/test_ports.py` — import-boundary guard: keep concrete adapters/SDK clients out of core/port modules (applies to `KISBroker` and the Discord notifier).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `Broker` Protocol + `MockBroker`: `KISBroker` is a new adapter on the same synchronous port — no port rewrite, `MockBroker` stays the default target.
- `CycleAuditEvent` / `ExecutionResult` already capture the per-cycle record incl. `broker_order_id`; the SQLite writer consumes these without changing the domain type (D-11).
- `kis_auth` shared, auto-refreshed token manager + `kis_quote` httpx/tenacity adapter from Phase 3 — the reuse candidate for the order path (D-05), avoiding a second auth path.
- Phase 3's stale-data fail-safe and fail-soft Naver-news patterns are the templates for D-08 (market-hours/stale pre-check) and D-14 (fail-soft notifications).
- `build_data_source` factory (inject collaborators) is the pattern for constructing `KISBroker` and the Discord `Notifier` for offline/testable wiring.
- Phase 4 structlog reproducibility line is the raw-prompt/response home; SQLite links to it by correlation ID (D-10).

### Established Patterns
- Ports are synchronous, semantic, adapter-free Protocols; concrete adapters opt-in via factories. Add `Notifier` the same way.
- Domain types are stdlib frozen dataclasses/enums; only config uses Pydantic. Do not Pydantic-ify `CycleAuditEvent`.
- Fail-safe/fail-soft is uniform: bad/absent input → HOLD or skip, never a crash; non-critical side channels (news, notifications) degrade gracefully and never block trading.
- Config is typed `Settings` with atomic mode binding; new settings (DB path, Discord webhook, real-order params) follow the same typed, gitignored-secret discipline.

### Integration Points
- CLI (`bot run`) → screener (universe) → per-ticker: `data_source.build_context` → `run_llm_cycle` (LLM → parse → risk) → `execute_signal_cycle` (MockBroker or KISBroker) → audit writer (SQLite) → per-run Discord summary.
- Real path only engages when `TRADING_MODE=real` + `CONFIRM_REAL_TRADING=yes` + per-invocation confirm flag + `--execute` all hold (D-03, D-04).
- `KISBroker.place_order` wraps client-order-ID dedup + query-before-resubmit reconciliation + partial-fill reconcile (D-06, D-07) behind the plain `Broker.place_order(order) -> str` signature.

</code_context>

<specifics>
## Specific Ideas

- Safety is layered and deliberate: dry-run default (D-03) + config gate + per-invocation confirm flag (D-04) means no real order is ever placed without three explicit, independent acts. This is the operator's stated priority — err toward *not* trading.
- The order POST is the single most dangerous operation in the whole system; the operator explicitly wants defense-in-depth idempotency (client ID **and** reconcile) rather than trusting either mechanism alone (D-06) — the analog of the Phase 4 "double-validate the signal" stance.
- The audit store is the reviewable system of record; raw prompt/response stay in structlog and are reachable by correlation ID rather than duplicated (D-10) — lean DB, full traceability.
- Discord (not Telegram) is the chosen channel, behind a swappable `Notifier` port so the choice is reversible without touching cycle code (D-12).

</specifics>

<deferred>
## Deferred Ideas

- Scheduler / always-on intraday loop — explicitly out of scope for v1 (manual trigger only); a future phase can add APScheduler/cron calling the existing CLI.
- Ensemble/consensus across both LLM providers (ENSEMBLE-01) — deferred; the switchable single provider stands.
- Auto-chasing partial fills (follow-up orders to complete an unfilled remainder) — deliberately excluded from v1 (D-07); operator reviews instead.
- Additional notification channels (Telegram, Slack, email) — the `Notifier` port makes these additive later; only the Discord adapter ships now.
- Interactive typed runtime confirmation for real runs — considered and set aside in favor of the non-interactive `--live-confirm` flag (D-04) to keep runs automatable.

None outside scope — discussion stayed within Phase 5 boundaries.

</deferred>

---

*Phase: 5-Real-Money Readiness & Operations*
*Context gathered: 2026-07-02*
