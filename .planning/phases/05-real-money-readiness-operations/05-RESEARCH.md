# Phase 5: Real-Money Readiness & Operations - Research

**Researched:** 2026-07-02
**Domain:** KIS domestic-stock order placement, idempotent/reconciled execution, SQLite audit persistence, Discord notification, typer CLI + real-money gate
**Confidence:** HIGH (existing code, config, ports — all read); MEDIUM (KIS order-API mechanics — cross-confirmed from official portal + koreainvestment GitHub + multiple tutorials, not fetched from a single authenticated spec page)

## Summary

Phase 5 turns the proven parse → risk → execute chain into an operable, real-money-capable system. The single most dangerous surface is the KIS order POST; the CONTEXT.md deliberately defers the order-library decision (D-05) and the exact order-API mechanics to this research. The strongest recommendation of this document: **extend the existing Phase 3 direct-REST layer (`kis_auth` + `kis_quote`) with an order/query adapter rather than introduce `python-kis`.** The Phase 3 `KisTokenManager` is already the single, thread-safe, auto-refreshing, secret-redacting token path with the exact retry/backoff posture D-06/D-14 want; adding `python-kis` would create a second token path (violating D-05's hard constraint) and pull an unvetted third party into the order path with no offsetting benefit at this scale.

The KIS order model has a decisive consequence for D-06 idempotency: **KIS does NOT accept a client-supplied order reference or idempotency key.** The order-cash POST returns a broker-assigned `ODNO` (order number) + `KRX_FWDG_ORD_ORGNO`; dedup therefore *cannot* be enforced by KIS on a client key and MUST be inferred by querying broker truth (recent orders / balance) before every POST. This makes the "query-before-resubmit reconciliation" leg of D-06 the load-bearing control, and the deterministic client-generated ID a local audit/dedup tag rather than something KIS honors. The "never blind-retry a POST" rule follows directly: the order POST must be excluded from any tenacity retry, and any resend must first re-query fills/open-orders.

Persistence (two-table SQLite, D-09..D-11), notification (Discord webhook behind a `Notifier` port, D-12..D-14), and the typer CLI + layered gate (D-01..D-04, CFG-04) are largely decided and low-risk; the research confirms feasibility, flags the specific landmines (SQLite single-writer/WAL, Discord 30-msg/min webhook rate limit, `typer` not yet a dependency and its `rich`/`shellingham` transitive deps), and grounds each against the existing typed-`Settings`, port-and-factory, and fail-soft patterns already in the repo.

**Primary recommendation:** Extend the Phase 3 direct-REST KIS layer with an `order-cash` + `inquire-daily-ccld` + `inquire-balance` adapter reusing the shared `KisTokenManager`; wrap it in a `KISBroker` satisfying the existing `Broker` Protocol whose `place_order` does client-ID tagging + query-before-POST reconciliation + partial-fill readback, with the POST itself never retried. Add `typer`, a `sqlite_audit` writer, and a Discord `Notifier` port. Do NOT add `python-kis`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**CLI Trigger & Real-Money Gate (OPS-01, CFG-04)**
- **D-01:** CLI command surface is `bot run`, `bot screen` (preview the candidate universe), and `bot status` (positions/cash) — the richest of the three sketched surfaces, matching the CLAUDE.md `typer` CLI recommendation.
- **D-02:** One `bot run` evaluates the **full screened universe by default**, looping the LLM → risk → execute chain over every candidate ticker; `--ticker <code>` narrows to a single ticker for testing/manual control. Per-ticker error isolation is expected (one ticker's failure must not abort the whole run) — see D-13.
- **D-03:** `bot run` is **dry-run by default** in both mock and real modes: a bare invocation logs the would-be decision/order and places nothing. Placing orders requires an explicit `--execute` flag. (Reuses the Phase 2 dry-run / EXEC-05 behavior as the default; `--execute` opts into the live path.)
- **D-04:** Real-money promotion is **layered**: the existing atomic config gate (`TRADING_MODE=real` requires `CONFIRM_REAL_TRADING=yes`, Phase 1) PLUS a **per-invocation CLI confirmation flag** (e.g. `--live-confirm`) required on any real-mode execute run. Non-interactive/automatable, but forces a deliberate act on every real run, not just a persisted setting. The loud Phase 1 startup banner still prints the active mode.

**Real KIS Order Path — Idempotency & Reconciliation (EXEC-04)**
- **D-05:** **Library choice is deferred to research/planning.** The planner must compare (a) extending the existing Phase 3 direct-REST KIS layer (`kis_auth` shared token manager + httpx/tenacity posture) with order endpoints vs (b) introducing `python-kis` (CLAUDE.md's recommendation) — evaluated against the live KIS order-API docs and the existing code. The roadmap already flags KIS order params (TR_ID prefixes, hashkey, tick-size bands, market-hours codes) as needing API-specific verification before any real-money path. Whichever is chosen must NOT create a second, divergent auth/token path if the Phase 3 one can be reused.
- **D-06:** Idempotency is **defense-in-depth**: a deterministic client-generated order ID per (cycle, ticker, side) as the primary dedup key, PLUS a **query-before-resubmit reconciliation** — before (re)submitting any order the system queries KIS for account truth (recent orders/positions) and only POSTs if the intended order isn't already present. The system **never blind-retries an order POST**.
- **D-07:** **Partial fills are recorded AND reconciled**: after placing, query fill status; record filled-vs-requested quantity in the audit + notification, and update the tracked position to the actual filled quantity so the next cycle sees broker truth. **No auto-chase** within a cycle to complete an unfilled remainder — the operator reviews.
- **D-08:** Real orders are **limit orders at the current KIS real-time price** (respecting tick-size bands), consistent with the existing `Order.limit_price` field, PLUS a **market-hours / stale-data pre-flight guard** that fails safe to HOLD/skip if the market is closed or price data is stale (reusing Phase 3's stale-data fail-safe posture). No market orders.

**Persistent Audit Store (OPS-02)**
- **D-09:** SQLite schema is **two normalized tables**: a `runs` table (run_id, timestamp, trading mode, dry_run flag, …) linked to a `decisions` table (one row per ticker decision in the run).
- **D-10:** Persist **structured fields in SQLite** (the `CycleAuditEvent` fields + parsed signal + confidence + data snapshot + order outcome) with a **correlation ID pointing to the Phase 4 structlog line** that holds the raw prompt/response. No duplication of raw prompt/response.
- **D-11:** A **new persistence/writer module consumes the existing `CycleAuditEvent`** (plus signal/context/order) and writes to SQLite at a **configurable path** (default e.g. `./data/audit.db`, gitignored). `CycleAuditEvent` stays the in-memory shape — **no Phase 2 domain-type change**; the writer is the sink.

**Notifications (OPS-03)**
- **D-12:** Notifications go through a small **`Notifier` Protocol/port** (consistent with the Broker/DataSource/LLMProvider port pattern), with a **Discord webhook adapter** as the concrete v1 implementation. Config holds the Discord webhook URL. Cycle code stays channel-agnostic. Discord (not Telegram) is the chosen v1 channel; this satisfies OPS-03's intent (a notification channel), not a scope change. A Discord webhook is an `httpx` POST, so no new heavy dependency.
- **D-13:** Notification trigger is a **consolidated per-run summary** (each ticker's decision/order outcome in one message) PLUS an **immediate push on any cycle-level error/failure**. Implies per-ticker error isolation in the run loop.
- **D-14:** Notifications are **fail-soft with bounded retry**: best-effort delivery wrapped in a bounded tenacity retry; on final failure it logs and the cycle continues. A notification failure **never crashes or blocks** the trading cycle. The order path and audit store are authoritative; the push is best-effort.

### Claude's Discretion
The planner/researcher may choose: exact module and symbol names (CLI module, `KISBroker`, `Notifier`, the persistence/writer module and its function names, Discord adapter name); the KIS order library decision itself (D-05) and the resulting order-endpoint mechanics (TR_ID, hashkey, tick-size band math, market-hours codes) after verification; exact `typer` sub-command/flag naming (`--execute`, `--live-confirm`, `--ticker` are indicative); the precise SQLite column set and indexes within the two-table shape (D-09); the correlation-ID scheme linking SQLite ↔ structlog (D-10); the default DB path and gitignore entry; the Discord message format/embed shape; and tenacity retry counts/backoff for the order-path reconciliation and notification delivery (align with existing `kis_max_retries` / `kis_retry_backoff_seconds`).

### Deferred Ideas (OUT OF SCOPE)
- Scheduler / always-on intraday loop — explicitly out of scope for v1 (manual trigger only); future phase can add APScheduler/cron calling the existing CLI.
- Ensemble/consensus across both LLM providers (ENSEMBLE-01) — deferred.
- Auto-chasing partial fills (follow-up orders to complete an unfilled remainder) — deliberately excluded from v1 (D-07); operator reviews instead.
- Additional notification channels (Telegram, Slack, email) — the `Notifier` port makes these additive later; only the Discord adapter ships now.
- Interactive typed runtime confirmation for real runs — set aside in favor of the non-interactive `--live-confirm` flag (D-04) to keep runs automatable.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| OPS-01 | Operator triggers a full evaluation cycle on demand (manual CLI trigger; no scheduler in v1) | `typer` CLI surface (`bot run`/`bot screen`/`bot status`), `--ticker`, dry-run default; drives existing `screener.screen_candidates` → `data_source.build_context` → `run_llm_cycle` → `execute_signal_cycle`. See CLI + Gate section. |
| OPS-02 | Log every cycle's data context, LLM signal, risk decisions, and order outcome to a persistent, reviewable audit store | stdlib `sqlite3` two-table (`runs`→`decisions`) writer consuming `CycleAuditEvent`; correlation-ID link to the Phase 4 structlog line. See Persistence section. |
| OPS-03 | Push each cycle's decision and order outcome to the operator via a notification channel (e.g. Telegram; Discord per D-12) | `Notifier` Protocol + Discord webhook (`httpx` POST) adapter; consolidated per-run summary + fail-soft bounded-tenacity delivery. See Notifications section. |
| EXEC-04 | All orders route through KIS (mock first); idempotent — reconcile against broker truth before resubmitting, never blind-retry a POST, model partial fills | `KISBroker` on existing `Broker` port; order-cash POST (TR_ID `TTTC0802U`/`VTTC0802U` etc.), query-before-POST via `inquire-daily-ccld`/`inquire-balance`, POST excluded from retry, partial-fill readback (`tot_ccld_qty`/`rmn_qty`). See KIS Order Path sections. |
| CFG-04 | Default `mock`; switching to `real` requires an explicit, deliberate config change | Layered gate: existing `Settings` `TradingMode.MOCK` default + `confirm_real_trading` validator (Phase 1) PLUS per-invocation `--live-confirm` (D-04) PLUS dry-run default (D-03). See CLI + Gate section. |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

Directives extracted from `./.claude/CLAUDE.md` that the planner MUST honor (same authority as locked decisions):

- **KIS library:** `python-kis` (Soju06) is the *recommended* library, BUT D-05 explicitly defers this — see D-05 analysis below, which recommends the documented **direct KIS REST fallback** to avoid a second auth path. This does not contradict CLAUDE.md: CLAUDE.md itself lists "Direct KIS REST/websocket (`httpx`)" as the sanctioned alternative "if you want zero third-party trust in the order path."
- **Never use `mojito2`** (unmaintained since 2023, no mock support).
- **Config/secrets:** `pydantic-settings` + gitignored `.env`; typed `Settings`; secrets never in logs/reprs. New settings (audit DB path, Discord webhook URL, real-order params) follow this discipline.
- **Scheduling:** plain `typer` CLI for v1 — no scheduler (matches D-01, deferred AUTO-01).
- **Persistence:** SQLite via stdlib `sqlite3`.
- **Logging:** stdlib `logging` + `structlog` for structured JSON lines (the Phase 4 line is the raw-prompt/response home; D-10 correlates to it).
- **HTTP:** `httpx` (with timeouts) for any web call; wrap flaky network calls in `tenacity` backoff. Discord webhook = an `httpx` POST.
- **Strict JSON LLM contract:** unchanged from Phase 4 — Phase 5 does not touch the parser/signal path.
- **Do NOT** add `requests`, hardcode keys, or open a second KIS token path.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| CLI trigger / universe loop / gate | CLI orchestration (`bot` entrypoint) | Core (config gate) | `typer` app owns argument parsing, `--execute`/`--live-confirm` gating, per-ticker error isolation; delegates each ticker to existing cycle functions. |
| Real order placement | Adapter (`KISBroker`) behind `Broker` port | KIS REST (`kis_auth`/order adapter) | Network + idempotency + reconciliation live in the adapter; core `execution.py` calls only `broker.place_order(order) -> str`, unchanged. |
| Idempotency / reconciliation | Adapter (`KISBroker`) | KIS query endpoints | KIS has no server-side idempotency key, so dedup is a client concern implemented by querying broker truth. |
| Market-hours / stale pre-flight guard | Data/cycle orchestration | KIS quote adapter (staleness) | Reuses Phase 3 stale-data fail-safe; adds a KST clock/session check before the execute leg. |
| Audit persistence | Adapter/sink (`sqlite_audit` writer) | Core (`CycleAuditEvent` shape) | Writer consumes the frozen `CycleAuditEvent`; SQLite is a side sink, not a domain concern. |
| Notification push | Adapter (Discord `Notifier`) behind port | CLI orchestration | Channel-agnostic port; Discord webhook is an `httpx` POST; fail-soft so it never blocks trading. |
| Trade math / thresholds / parsing | Core (`execution`, `risk`, `signal_parser`) | — | FROZEN from Phases 2–4; Phase 5 adds no trade-math logic. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `typer` | 0.26.8 | CLI entrypoint (`bot run`/`screen`/`status`) | CLAUDE.md-recommended, type-hint driven, built on Click; the one new runtime dep this phase adds. Latest on PyPI, `requires-python >=3.10`. [CITED: pypi.org/pypi/typer/json] |
| `sqlite3` | stdlib | Two-table audit store (D-09) | Zero-ops, queryable, ships with Python; CLAUDE.md-locked. [VERIFIED: stdlib] |
| `httpx` | 0.28.1 (already pinned) | KIS order/query POSTs + Discord webhook POST | Already the KIS transport in `kis_quote`; Discord webhook is one more `httpx` POST — no new heavy dep. [VERIFIED: pyproject.toml] |
| `tenacity` | 9.1.4 (already pinned) | Bounded retry on query/notify legs (NOT on the order POST) | Already the retry lib in `kis_auth`/`kis_quote`/`llm_provider`; reuse the same posture. [VERIFIED: pyproject.toml] |
| `structlog` | 25.5.0 (already pinned) | Raw-record home; D-10 correlation target | Phase 4 already emits the reproducibility line; Phase 5 correlates, does not duplicate. [VERIFIED: pyproject.toml] |
| `pydantic-settings` | 2.11.0 (already pinned) | New typed settings (DB path, webhook URL, real-order params) | Same `Settings` discipline as Phases 1–4. [VERIFIED: pyproject.toml] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `rich` | transitive of `typer` | Colored CLI output / tables for `bot status` | Pulled in automatically by `typer>=0.12`; usable for the `bot status` positions/cash table. [CITED: pypi.org/pypi/typer/json — deps `rich>=13.8.0`, `shellingham>=1.3.0`, `annotated-doc>=0.0.2`] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Direct-REST order adapter (recommended) | `python-kis` (Soju06) | Introduces a second auth/token path (violates D-05 hard constraint), an unvetted third party in the order path, and duplicate secret handling — for zero benefit given the token/quote layer already exists. Re-evaluate only if the direct-REST order surface proves unexpectedly large. |
| `typer` | stdlib `argparse` | Zero new deps, but loses type-hint ergonomics and the `rich` `bot status` table; CLAUDE.md explicitly picks `typer`. Fallback if `typer`'s transitive deps are undesired. |
| Discord webhook | `discord.py` / a Discord bot | A full bot/gateway is massive overkill for one-way push; a webhook is a single `httpx` POST (D-12). |

**Installation:**
```bash
# add to pyproject.toml dependencies, then reinstall editable into the workspace userbase
# (matches the repo's PYTHONUSERBASE workflow)
# dependencies += "typer==0.26.8"
PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pip install --user -e .
```

**Version verification:**
- `typer==0.26.8` — latest on PyPI, `requires-python >=3.10` (repo floor is 3.10; local env is Python 3.14). [CITED: pypi.org/pypi/typer/json]
- `python-kis` — latest 2.x published 2025-10-13; **NOT recommended for this phase** (see D-05).
- Env probe (2026-07-02): neither `typer` nor `pykis` currently importable in `.python-userbase`; both would be new installs. [VERIFIED: local env probe]

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `typer` | PyPI | established (FastAPI org; latest republish 2026-06-26) | unknown (seam null) | github.com/fastapi/typer | SUS (`too-new`, `unknown-downloads`) | **Approved with checkpoint** — SUS is a metadata artifact (seam read a recent republish date + null download count); `typer` is the widely-used FastAPI CLI lib and CLAUDE.md-sanctioned. Planner MUST still gate the install behind a `checkpoint:human-verify` per protocol. |
| `python-kis` | PyPI | published 2025-10-13 | unknown (seam null) | none in PyPI metadata (repo is github.com/Soju06/python-kis) | SUS (`unknown-downloads`, `no-repository`) | **NOT INSTALLED** — recommendation is to not adopt `python-kis` this phase (D-05). If the planner overrides and selects it, a `checkpoint:human-verify` is mandatory. |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** `typer` (approved, planner adds `checkpoint:human-verify` before install); `python-kis` (not adopted).

*No `postinstall` scripts on either package (PyPI has no npm-style postinstall; verified `postinstall: null` in the seam signals). The SUS verdicts are download-count/metadata artifacts, not hallucination signals — both packages provably exist and are the intended libraries.*

## Architecture Patterns

### System Architecture Diagram

```
                 operator (terminal)
                        │
                 `bot run [--ticker C] [--execute] [--live-confirm]`
                        │
                        ▼
        ┌─────────────────────────────────┐
        │  CLI app (typer)  — NEW          │
        │  • load Settings, print banner   │
        │  • enforce layered gate (D-03/04)│
        │  • dry_run = not --execute       │
        └───────────────┬─────────────────┘
                        │  universe (or single --ticker)
                        ▼
        screener.screen_candidates ──► [ticker, ticker, …]
                        │
             per-ticker loop (error-isolated, D-02/D-13)
                        ▼
      data_source.build_context(ticker) ── stale/closed? ─► HOLD/skip (D-08 pre-flight guard)
                        │ DataContext
                        ▼
      run_llm_cycle(...) ── LLM → parse → risk → execute_signal_cycle
                        │            (dry_run flag threaded through)
                        │ ExecutionResult (+ CycleAuditEvent, order?)
                        ▼
        ┌───────────────┴───────────────┐
        │  broker = MockBroker | KISBroker (selected by TradingMode)  │
        │  KISBroker.place_order(order) -> str:   — NEW               │
        │    1. compute client_order_id(cycle,ticker,side)           │
        │    2. QUERY broker truth (inquire-daily-ccld / balance)    │
        │    3. if intended order already present → return its ODNO  │
        │    4. else POST order-cash (NOT retried)  → ODNO           │
        │    5. QUERY fills → read tot_ccld_qty / rmn_qty            │
        │    6. reconcile tracked position to filled qty (D-07)      │
        └───────────────┬───────────────┘
                        │ ExecutionResult (broker_order_id, fill qty)
                        ▼
        sqlite_audit.write(run_id, CycleAuditEvent, signal, ctx, order, correlation_id)  — NEW
                        │
             (accumulate per-ticker outcomes)
                        ▼
        Notifier.send(run_summary)  — Discord webhook, fail-soft (D-13/D-14)  — NEW
                        │  (best-effort; never blocks)
                        ▼
                 operator's Discord channel
```

### Recommended Project Structure
```
trading_bot/
├── cli.py             # NEW: typer app (bot run/screen/status), gate enforcement, per-ticker loop
├── kis_broker.py      # NEW: KISBroker (Broker port impl): place_order + reconcile; imports kis_order
├── kis_order.py       # NEW: direct-REST order/query adapter (order-cash, inquire-daily-ccld,
│                      #      inquire-balance, inquire-psbl-order) reusing KisTokenManager + hashkey
├── sqlite_audit.py    # NEW: two-table (runs→decisions) writer consuming CycleAuditEvent (D-09..D-11)
├── notifier.py        # NEW: DiscordNotifier adapter (httpx POST), fail-soft bounded tenacity (D-12..D-14)
├── ports.py           # EDIT: add Notifier Protocol (adapter-free, guarded by test_ports.py)
├── config.py          # EDIT: add audit_db_path, discord_webhook_url, real-order settings, tick policy
└── (execution.py, risk.py, signal_parser.py, llm_provider.py, data_source.py, screener.py — UNCHANGED)
```

### Pattern 1: Adapter behind an existing synchronous Protocol (`KISBroker`)
**What:** `KISBroker` satisfies `Broker` structurally (`get_position`, `place_order(order) -> str`) exactly like `MockBroker`. All network/idempotency/reconciliation logic hides behind the plain signature so `execution._finalize_cycle` (the *only* `place_order` caller) is untouched.
**When to use:** Always — the port must not change; core stays adapter-free (guarded by `tests/test_ports.py`, which forbids `kis` fragments in `ports.py`).
**Example:**
```python
# Grounded in trading_bot/mock_broker.py (the reference impl) and trading_bot/ports.py
class KISBroker:  # structural Broker; NOT importing from ports.py
    def __init__(self, *, order_adapter, account, tracked_positions=None):
        self._order = order_adapter          # kis_order.KisOrderAdapter (reuses KisTokenManager)
        self._account = account
        self._positions = dict(tracked_positions or {})

    def get_position(self, ticker):
        return self._positions.get(ticker.value)

    def place_order(self, order) -> str:
        # 1. deterministic client tag (audit/dedup only — KIS does NOT honor it)
        client_ref = self._client_ref(order)
        # 2. QUERY broker truth BEFORE any POST (D-06)
        existing = self._order.find_open_or_recent(order)
        if existing is not None:
            return existing.odno            # already placed; never re-POST
        # 3. POST order-cash — this call is NEVER wrapped in retry (D-06)
        odno = self._order.place(order)     # raises on transport failure; caller fails safe
        # 4/5. read fills, reconcile tracked position (D-07)
        fill = self._order.query_fill(odno)
        self._reconcile(order, fill)
        return odno
```

### Pattern 2: Two-table SQLite writer consuming the frozen `CycleAuditEvent`
**What:** A sink module opens SQLite, ensures schema, writes one `runs` row per invocation and one `decisions` row per ticker, storing structured fields + a `correlation_id` that matches the Phase 4 structlog `llm_signal_cycle` line. No change to `CycleAuditEvent`.
**When to use:** Once per ticker outcome (write inside the loop) plus a `runs` header at loop start.
**Example:**
```python
# Grounded in execution.CycleAuditEvent fields (ticker, parsed_decision, parse_error,
# risk_override, override_reason, final_action, order_reason, dry_run, broker_order_id)
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs(
  run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL,
  trading_mode TEXT NOT NULL, dry_run INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS decisions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL REFERENCES runs(run_id),
  ticker TEXT NOT NULL, final_action TEXT NOT NULL,
  parsed_decision TEXT, confidence REAL, parse_error TEXT,
  risk_override INTEGER NOT NULL, override_reason TEXT,
  order_reason TEXT, broker_order_id TEXT,
  requested_qty INTEGER, filled_qty INTEGER,
  current_price REAL, correlation_id TEXT, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_decisions_run ON decisions(run_id);
CREATE INDEX IF NOT EXISTS ix_decisions_ticker ON decisions(ticker);
"""

def connect(path):
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL;")   # tolerate reader while a run writes
    conn.executescript(SCHEMA)
    return conn
```

### Pattern 3: Fail-soft `Notifier` port + Discord webhook (mirrors Phase 3 fail-soft Naver news)
**What:** A `Notifier` Protocol in `ports.py`; a `DiscordNotifier` adapter POSTs `{"content": ...}` (or an embed) to the webhook URL via `httpx`, wrapped in a bounded tenacity retry; on final failure it logs and returns without raising, so the cycle continues (D-14).
**Example:**
```python
# ports.py — adapter-free (guarded by test_ports.py)
@runtime_checkable
class Notifier(Protocol):
    def send(self, summary: str) -> bool:   # True on delivery, False on give-up (never raises)
        ...
```

### Anti-Patterns to Avoid
- **Wrapping the order POST in tenacity retry.** A retried POST is a blind resubmit — the exact thing EXEC-04/D-06 forbid. Only the *query* legs (find-open-orders, query-fill, balance) may retry. The POST is single-shot; failure → fail safe, next cycle re-queries.
- **Trusting a client-generated ID as a KIS idempotency key.** KIS ignores it; dedup MUST come from querying broker truth (see State of the Art). The client ID is a local audit tag only.
- **Opening a second KIS token flow.** `KISBroker`/`kis_order` MUST consume the shared `KisTokenManager` (D-14 hard constraint); do not call `/oauth2/tokenP` anywhere else.
- **Pydantic-ifying `CycleAuditEvent` or letting SQLite/Discord leak into `ports.py`/`execution.py`.** Ports stay adapter-free (test-guarded); domain types stay stdlib frozen dataclasses.
- **Market orders / unsnapped limit prices.** D-08 mandates limit orders snapped to the valid tick band; an off-tick `ORD_UNPR` is rejected by KRX.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| KIS token issuance/refresh for orders | A second token manager in `kis_broker` | The existing `KisTokenManager` (`get_token()`, `app_key`, `app_secret`) | Thread-safe, auto-refresh, secret-redacted, retry-bounded already (D-14). A second path is the exact failure D-05 forbids. |
| Retry/backoff | Custom loops | `tenacity` (already used) with `kis_max_retries`/`kis_retry_backoff_seconds` — on QUERY legs only | Consistent posture; already the repo standard. |
| CLI parsing/help/flags | argparse boilerplate | `typer` | CLAUDE.md-locked; type-hint driven. |
| Audit persistence | CSV append + custom query code | stdlib `sqlite3` two-table schema | Queryable ("what happened in run X", "what did we decide on ticker Y"), zero-ops (D-09). |
| Discord delivery | A full Discord bot/gateway (`discord.py`) | An `httpx` POST to the webhook URL | One-way push needs a webhook, not a gateway (D-12). |
| Order hashkey | Hand-rolled hashing | KIS `/uapi/hashkey` endpoint with appkey/appsecret headers | KIS computes the hashkey server-side over the JSON body; you POST the body and echo the returned value in the `hashkey` header. [CITED: KIS portal] |

**Key insight:** Almost every hard part of this phase already has a repo-native solution (token manager, retry posture, port+factory pattern, structlog line, `CycleAuditEvent`). The genuinely *new* logic is narrow: the order/query REST calls, the query-before-POST reconciliation control flow, tick-size snapping, and the market-hours guard. Concentrate scrutiny there.

## Runtime State Inventory

> This is a feature phase, not a rename/refactor. Included lightly because Phase 5 introduces new persistent/live state.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | NEW SQLite audit DB (default `./data/audit.db`, D-11). No pre-existing store to migrate. | Create dir + gitignore entry; schema on first connect. |
| Live service config | NEW Discord webhook URL (a secret, lives in `.env`, not git). KIS mock/real credentials already in Phase 1 config. | Add `discord_webhook_url` typed setting; document `.env` key. |
| OS-registered state | None — no scheduler/cron/task registration (deferred AUTO-01). | None. |
| Secrets/env vars | NEW `.env` keys: `DISCORD_WEBHOOK_URL`; possibly real-order params. Existing `CONFIRM_REAL_TRADING`, `TRADING_MODE`, `KIS_REAL__*` unchanged. | Extend `Settings`, keep gitignored; redact from banner/logs. |
| Build artifacts | Adding `typer` changes installed deps → the workspace `.python-userbase` must be reinstalled (`pip install -e .`). | Reinstall step after `pyproject.toml` edit (matches MEMORY note: native ext must match Python 3.14 interpreter). |

## Common Pitfalls

### Pitfall 1: Blind-retrying the order POST (the cardinal EXEC-04 violation)
**What goes wrong:** A tenacity-wrapped `order-cash` POST that times out but actually succeeded on the server resubmits → duplicate real order.
**Why it happens:** Copy-pasting the Phase 3 `kis_quote` retry pattern (which is safe for idempotent GETs) onto the non-idempotent POST.
**How to avoid:** The POST is single-shot, never retried. Any resend path first re-queries `inquire-daily-ccld`/`inquire-balance` and only POSTs if the intended order is absent (D-06). Structure the code so the retry decorator physically cannot wrap `place`.
**Warning signs:** A `@retry` above the order-cash call; a test that asserts N POST attempts.

### Pitfall 2: Assuming KIS honors a client idempotency key
**What goes wrong:** Relying on the deterministic client ID to dedup at KIS → duplicates slip through because KIS never saw the key.
**Why it happens:** Idempotency-key APIs (Stripe-style) are the mental model; KIS is not one.
**How to avoid:** Treat the client ID as a *local audit tag only*; make broker-truth query the actual dedup gate. [CITED: KIS order-cash spec returns broker-assigned ODNO; no client-ref param]
**Warning signs:** Dedup logic that never issues a query before POST.

### Pitfall 3: Off-tick limit price rejected by KRX
**What goes wrong:** `ORD_UNPR` not on the valid tick band (e.g. 74,321 for a stock priced 70k–100k where tick is 100) → KRX rejects the order.
**Why it happens:** Passing the raw KIS real-time price straight into `limit_price`.
**How to avoid:** Snap `limit_price` down (BUY) / to the nearest valid tick using the 2023-reform band table (see Code Examples). [CITED: samsungpop tick table 2023-01-25]
**Warning signs:** KRX `rt_cd != 0` with a tick/price error message.

### Pitfall 4: Wrong TR_ID for mock vs real (or wrong domain)
**What goes wrong:** Using a real TR_ID (`TTTC…`) against the mock domain (or vice versa) → auth/permission error, or worse, a real order from a "mock" run.
**Why it happens:** TR_IDs differ only by a `T`/`V` prefix (`TTTC0802U` real-buy vs `VTTC0802U` mock-buy); easy to hard-code the wrong one.
**How to avoid:** Derive the TR_ID from `Settings.active_kis` (the atomic mock/real group already carries `tr_id_profile`) — never hard-code. The atomic group binding from Phase 1 is exactly the safety mechanism here. [CITED: KIS TR_ID prefixes]
**Warning signs:** A literal `TTTC0802U` in code not keyed off `trading_mode`.

### Pitfall 5: Market closed / stale price at execute time
**What goes wrong:** Placing (or trying to place) an order outside 09:00–15:30 KST or on a holiday → rejected or acts on stale price.
**Why it happens:** No pre-flight session check.
**How to avoid:** D-08 pre-flight guard: check KST clock against the regular session (09:00–15:30, Mon–Fri, non-holiday) AND reuse Phase 3 stale-data fail-safe; fail safe to HOLD/skip when closed/stale. [CITED: KRX regular session 09:00–15:30 KST]
**Warning signs:** Orders attempted with a timestamp outside session hours.

### Pitfall 6: SQLite writer concurrency / partial run
**What goes wrong:** A crash mid-run leaves a `runs` row without its `decisions`, or a locked DB if a reviewer has it open.
**Why it happens:** Default rollback-journal + long-held connection.
**How to avoid:** `PRAGMA journal_mode=WAL`, write each `decisions` row as the ticker completes (not one big transaction at end), commit per row so a crash preserves completed decisions. Single-writer only (no scheduler, so no concurrent writers — safe). [ASSUMED: standard sqlite guidance, matches D-09 intent]
**Warning signs:** `database is locked` errors; empty `decisions` for a completed run.

### Pitfall 7: Discord webhook rate limit / blocking
**What goes wrong:** Many messages → Discord 429; or a hung webhook blocks the cycle.
**Why it happens:** Per-ticker messages (D-13 avoids this with a *consolidated* summary) or an unbounded/blocking POST.
**How to avoid:** One consolidated per-run message (D-13); bounded tenacity + short `httpx` timeout; fail-soft on final failure (D-14). Discord webhooks allow ~30 requests/min per webhook. [ASSUMED: Discord documented webhook rate ~30/min; verify against current Discord docs]
**Warning signs:** 429 responses; cycle stalls on notify.

## Code Examples

### Tick-size snapping (D-08) — 2023 KRX reform bands
```python
# Source: KRX 2023-01-25 tick reform table [CITED: samsungpop.com notice MenuSeqNo=19236]
# Bands are [lower, tick); price < band upper uses that tick.
_TICK_BANDS = (
    (2_000, 1),
    (5_000, 5),
    (20_000, 10),
    (50_000, 50),
    (100_000, 100),   # 50k–100k -> 100
    (200_000, 100),   # 100k–200k -> 100
    (500_000, 500),
    (float("inf"), 1_000),
)

def snap_to_tick(price: float, *, side: str) -> int:
    for upper, tick in _TICK_BANDS:
        if price < upper:
            q = int(price // tick) * tick        # snap down to a valid tick
            if side == "SELL" and q < price:     # optional: nearest for SELL
                q += 0                            # keep down-snap for conservatism
            return q
    return int(price)
# NOTE for planner: confirm the exact 1,000–2,000 band tick (reform set it to 1 won)
# and whether SELL should round up vs down — a deliberate policy choice, mark [ASSUMED].
```

### KIS order request skeleton (grounded in kis_quote header pattern)
```python
# Source: KIS portal order-cash spec + existing trading_bot/kis_quote.py header pattern
# [CITED: apiportal.koreainvestment.com order-cash] [VERIFIED: kis_quote.py]
_ORDER_PATH = "/uapi/domestic-stock/v1/trading/order-cash"

def build_order_body(account, order, tick_price):
    return {
        "CANO": account.cano,            # account number (8)
        "ACNT_PRDT_CD": account.prdt,    # product code (2), usually "01"
        "PDNO": order.ticker.value,      # 6-digit code
        "ORD_DVSN": "00",                # 00 = limit order (지정가); D-08 = limit only
        "ORD_QTY": str(order.quantity),
        "ORD_UNPR": str(tick_price),     # snapped limit price
    }

def order_headers(token_manager, tr_id, hashkey):
    return {
        "content-type": "application/json",
        "authorization": f"Bearer {token_manager.get_token()}",
        "appkey": token_manager.app_key,
        "appsecret": token_manager.app_secret,
        "tr_id": tr_id,        # buy real TTTC0802U / mock VTTC0802U; sell real TTTC0801U / mock VTTC0801U
        "custtype": "P",
        "hashkey": hashkey,    # from POST /uapi/hashkey over the body
    }
# Response (rt_cd == "0"): output.ODNO (order number), output.KRX_FWDG_ORD_ORGNO,
# output.ORD_TMD (order time). Persist ODNO as broker_order_id.
```

### Query-before-POST reconciliation control flow (D-06/D-07)
```python
# Source: KIS inquire-daily-ccld (TR_ID TTTC8001R) + inquire-balance (TTTC8434R/VTTC8434R)
# [CITED: KIS portal inquire-daily-ccld, inquire-balance]
def place_reconciled(order_adapter, order) -> str:
    # 1. QUERY today's orders (retryable GET-style) for this PDNO/side
    open_or_recent = order_adapter.inquire_daily_ccld(pdno=order.ticker.value)
    match = _match_intended(open_or_recent, order)   # same ticker/side/qty today
    if match is not None:
        return match["odno"]                          # already placed → no POST (D-06)
    # 2. POST once, NOT retried (D-06)
    odno = order_adapter.order_cash(order)            # raises on failure; caller fails safe
    # 3. read fill status (D-07): tot_ccld_qty (filled) vs rmn_qty (remaining) vs ord_qty
    fill = order_adapter.inquire_daily_ccld(odno=odno)
    filled = int(fill.get("tot_ccld_qty", 0))
    # 4. reconcile tracked position to filled qty; record filled-vs-requested in audit + notify
    return odno
# Field names tot_ccld_qty / rmn_qty / ord_qty / odno are the KIS inquire-daily-ccld
# response fields. [CITED: KIS inquire-daily-ccld field set]
```

### typer CLI surface + layered gate (D-01..D-04, CFG-04)
```python
# Source: CLAUDE.md typer recommendation + existing config gate (config.py validate_safety_gates)
import typer
app = typer.Typer(help="Stock trading bot")

@app.command()
def run(
    ticker: str = typer.Option(None, help="Narrow to one 6-digit code (D-02)"),
    execute: bool = typer.Option(False, "--execute", help="Place orders (else dry-run, D-03)"),
    live_confirm: bool = typer.Option(False, "--live-confirm", help="Required for real execute (D-04)"),
):
    settings = Settings()                       # Phase 1 gate already fires here (real needs CONFIRM_REAL_TRADING)
    print(startup_banner(settings))             # loud mode banner (Phase 1)
    dry_run = not execute                        # dry-run default (D-03)
    if settings.trading_mode is TradingMode.REAL and execute and not live_confirm:
        raise typer.Exit("real execute requires --live-confirm")   # per-invocation gate (D-04)
    ...  # screener → per-ticker loop (error-isolated) → cycle → audit → notify
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `mojito2` for KIS | `python-kis` OR direct REST | mojito2 unmaintained since 2023 | Never use mojito2; this phase uses direct REST (D-05). |
| Pre-2023 tick bands (5/50/500 won steps) | 2023-reform bands (1/10/100 won for sub-bands) | 2023-01-25 | Tick snapping MUST use the new table or KRX rejects off-tick prices. [CITED] |
| Stripe-style client idempotency keys | KIS has none — dedup by querying broker truth | (always) | D-06's query-before-resubmit is the *only* real dedup; client ID is a local tag. [CITED] |

**Deprecated/outdated:**
- `mojito2`: unmaintained, no mock support — forbidden by CLAUDE.md.
- Assistant-prefill JSON forcing (Phase 4 concern, not this phase) — already handled.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | KIS order-cash response returns `ODNO` + `KRX_FWDG_ORD_ORGNO` + `ORD_TMD` and accepts **no** client idempotency key | KIS Order Path | If KIS *did* accept a client ref, D-06 could use it directly; but reconciliation-by-query is safe regardless — low risk. Planner should confirm on the KIS portal order-cash spec page. |
| A2 | `inquire-daily-ccld` (TTTC8001R) response exposes `tot_ccld_qty` / `rmn_qty` / `ord_qty` / `odno` for fill readback | Reconciliation | If field names differ, partial-fill readback (D-07) needs the correct names; verify against the portal response schema before implementing. |
| A3 | Mock balance/order TR_IDs use the `V…` prefix (`VTTC0802U`, `VTTC8434R`) mirroring real `T…` | Pitfall 4 | Wrong prefix → auth error (fails safe, not a wrong-money trade, because domain is also mock-bound). Derive from `active_kis.tr_id_profile`, do not hard-code. |
| A4 | Tick band 1,000–2,000 won = 1 won tick; SELL snap-down is acceptably conservative | Tick snapping | An off-by-one-band tick → KRX rejects (fails safe, no fill). Confirm band edges + SELL rounding policy. |
| A5 | KRX regular session is 09:00–15:30 KST, Mon–Fri, minus holidays; no reliable programmatic holiday feed assumed | Market-hours guard | Placing on a holiday → rejected (fails safe). A hard-coded holiday list or pykrx trading-day check may be needed; planner decides the closed-detection mechanism. |
| A6 | Discord webhook rate limit ~30 req/min; single consolidated message stays well under | Notifications | With one message/run, effectively zero risk; verify only if per-ticker messaging is ever added. |
| A7 | SQLite WAL + per-row commit is sufficient (single writer, no scheduler) | Persistence | Correct as long as AUTO-01 stays deferred; revisit if a scheduler is added. |
| A8 | `typer` SUS verdict is a metadata artifact, not a supply-chain risk | Package audit | Low — `typer` is the FastAPI CLI lib; planner still gates install behind `checkpoint:human-verify`. |

**If this table is empty:** it is not — 8 assumptions need planner/operator confirmation, all KIS-API-specific or policy choices. Every one fails *safe* (rejected order / no trade) if wrong, consistent with the phase's safety-first posture.

## Open Questions

1. **Does KIS accept any client order reference for idempotency?**
   - What we know: The order-cash spec returns a broker-assigned `ODNO`; no client-ref parameter is documented in the standard body (`CANO/ACNT_PRDT_CD/PDNO/ORD_DVSN/ORD_QTY/ORD_UNPR`).
   - What's unclear: Whether an undocumented/optional field exists.
   - Recommendation: Assume NO (A1); make broker-truth query the dedup gate. Safe either way.

2. **Exact fill-status field names on `inquire-daily-ccld`.**
   - What we know: The endpoint (TTTC8001R) returns per-order rows including `odno` and execution quantities.
   - What's unclear: Precise field spelling (`tot_ccld_qty` vs `ccld_qty`, `rmn_qty`).
   - Recommendation: Verify on the KIS portal response schema before coding the readback (A2). A `checkpoint:human-verify` on first real reconciliation is prudent.

3. **Closed-market / holiday detection mechanism.**
   - What we know: Regular session 09:00–15:30 KST; pykrx already knows trading days (Phase 3 uses `accepted_latest_date`).
   - What's unclear: Whether to reuse pykrx trading-day logic, a hard-coded holiday list, or a KIS session flag for the D-08 guard.
   - Recommendation: Reuse the Phase 3 trading-date machinery + a KST clock window; fail safe when uncertain.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `typer` | CLI (OPS-01) | ✗ (not installed) | — (0.26.8 on PyPI) | stdlib `argparse` (loses `rich` table) |
| `sqlite3` | Audit store (OPS-02) | ✓ (stdlib) | stdlib | — |
| `httpx` | KIS orders + Discord (EXEC-04/OPS-03) | ✓ (pinned 0.28.1) | 0.28.1 | — |
| `tenacity` | Query/notify retry | ✓ (pinned 9.1.4) | 9.1.4 | — |
| `structlog` | D-10 correlation | ✓ (pinned 25.5.0) | 25.5.0 | — |
| `python-kis` | (only if D-05 chose it) | ✗ | — (2.x on PyPI) | Direct REST (recommended) — no install needed |
| KIS mock (모의투자) account + creds | Real order path first target | operator-provided in `.env` | — | Cannot integration-test the live POST without it; unit-test with a fake client (like `kis_quote` tests) |
| Discord webhook URL | Notifications | operator-provided in `.env` | — | Notifier is fail-soft; absent URL → skip/log |

**Missing dependencies with no fallback:**
- KIS mock account credentials for any *live* order integration test — but the offline unit path (injectable fake HTTP client, as in `test_kis_quote.py`) covers all logic without them.

**Missing dependencies with fallback:**
- `typer` (install it; argparse fallback exists but CLAUDE.md picks typer).
- `python-kis` (not needed — direct REST is the recommendation).

## Validation Architecture

> `workflow.nyquist_validation: true` — section included.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest==8.4.2` |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (testpaths=`tests`, pythonpath=`.`) |
| Quick run command | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_kis_broker.py -x` |
| Full suite command | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` |

Existing pattern: adapters are tested fully offline via injected fake HTTP clients + deterministic clocks (`test_kis_quote.py`, `test_kis_auth.py`, `conftest.py` fakes). Phase 5 adapters MUST follow this — no live KIS calls in tests.

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EXEC-04 | Order POST never retried; blind-retry impossible | unit | `pytest tests/test_kis_broker.py::test_order_post_not_retried -x` | ❌ Wave 0 |
| EXEC-04 | Query-before-POST returns existing ODNO, no second POST | unit | `pytest tests/test_kis_broker.py::test_reconcile_skips_duplicate -x` | ❌ Wave 0 |
| EXEC-04 | Partial fill read back; tracked position = filled qty (D-07) | unit | `pytest tests/test_kis_broker.py::test_partial_fill_reconciled -x` | ❌ Wave 0 |
| EXEC-04 | KISBroker structurally satisfies `Broker` (like MockBroker) | unit | `pytest tests/test_kis_broker.py::test_kis_broker_is_broker -x` | ❌ Wave 0 |
| EXEC-04/D-08 | Off-tick price snapped to valid band; market-closed → HOLD | unit | `pytest tests/test_kis_broker.py::test_tick_snap_and_market_guard -x` | ❌ Wave 0 |
| CFG-04/D-04 | Real execute without `--live-confirm` refuses | unit | `pytest tests/test_cli.py::test_real_execute_requires_live_confirm -x` | ❌ Wave 0 |
| OPS-01/D-02/D-13 | Per-ticker failure isolated; run continues | unit | `pytest tests/test_cli.py::test_ticker_error_isolation -x` | ❌ Wave 0 |
| OPS-01/D-03 | Bare `bot run` places nothing (dry-run default) | unit | `pytest tests/test_cli.py::test_dry_run_default_no_orders -x` | ❌ Wave 0 |
| OPS-02/D-09 | Two-table write; runs↔decisions link queryable | unit | `pytest tests/test_sqlite_audit.py::test_two_table_write -x` | ❌ Wave 0 |
| OPS-02/D-10 | Correlation ID stored, matches structlog line | unit | `pytest tests/test_sqlite_audit.py::test_correlation_id -x` | ❌ Wave 0 |
| OPS-03/D-13 | One consolidated summary per run | unit | `pytest tests/test_notifier.py::test_consolidated_summary -x` | ❌ Wave 0 |
| OPS-03/D-14 | Notify failure never raises/blocks cycle | unit | `pytest tests/test_notifier.py::test_fail_soft -x` | ❌ Wave 0 |
| ports | `Notifier` added but `ports.py` stays adapter-free | unit | `pytest tests/test_ports.py -x` | ✅ (extend existing) |

### Sampling Rate
- **Per task commit:** the relevant new `tests/test_*.py -x`
- **Per wave merge:** full suite `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q`
- **Phase gate:** full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_kis_broker.py` — covers EXEC-04 (no-retry POST, reconcile, partial fill, tick snap, market guard, Broker conformance)
- [ ] `tests/test_kis_order.py` — covers order-cash body/headers/TR_ID selection + fill parsing with a fake HTTP client (mirror `test_kis_quote.py`)
- [ ] `tests/test_cli.py` — covers CFG-04/OPS-01 gate + error isolation + dry-run default
- [ ] `tests/test_sqlite_audit.py` — covers OPS-02 two-table write + correlation ID (use `:memory:` or tmp_path DB)
- [ ] `tests/test_notifier.py` — covers OPS-03 consolidated summary + fail-soft (fake `httpx` client)
- [ ] `tests/test_ports.py` — extend to assert `Notifier` is a runtime-checkable adapter-free Protocol
- [ ] Framework install: `typer==0.26.8` into `.python-userbase` (reinstall `-e .`)

## Security Domain

> `security_enforcement: true`, `security_asvs_level: 1`. Included. This phase touches the real-money order path — highest-stakes surface in the system.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Reuse `KisTokenManager` (single auto-refreshed token path); bearer token never logged/repr'd (existing redaction). No second token path (D-14). |
| V3 Session Management | no | No user sessions; the KIS bearer token is the only session-like artifact, managed centrally. |
| V4 Access Control | yes | Real-money authorization is the *layered gate*: `TRADING_MODE=real` + `CONFIRM_REAL_TRADING=yes` (Settings validator) + `--live-confirm` + `--execute` (D-03/D-04). Three independent acts before a real order. |
| V5 Input Validation | yes | KIS response validation (mirror `kis_quote`: `rt_cd`, field presence, numeric checks) before trusting fills/positions; treat all KIS output as untrusted, fail safe on malformed. Scraped-news untrusted-input boundary already handled Phase 4 (unchanged). |
| V6 Cryptography | yes | Do NOT hand-roll the KIS hashkey — obtain it from the KIS `/uapi/hashkey` endpoint. Secrets (`app_key`, `app_secret`, tokens, `DISCORD_WEBHOOK_URL`) held as `SecretStr`, redacted from banner/logs/reprs (existing pattern). |
| V7 Error Handling & Logging | yes | Fail-soft notifier + fail-safe order path: errors → HOLD/skip, never a crash or a blind retry. Audit store is the tamper-evident system-of-record (append-only writes). Never log secrets in the SQLite audit or Discord message. |

### Known Threat Patterns for KIS order path + SQLite + Discord

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Duplicate real order from POST retry | Tampering / (financial) DoS | POST never retried; query-before-resubmit (D-06). |
| Mock TR_ID used against real domain (or vice versa) | Elevation of Privilege | Derive TR_ID from atomic `active_kis` group; loud startup banner; layered gate. |
| Secret leak (appkey/secret/token/webhook URL) into logs, audit DB, or Discord message | Information Disclosure | `SecretStr` + existing redaction; audit writer stores only non-secret fields; Discord message contains decisions/outcomes, never credentials. |
| Malformed/hostile KIS response treated as truth (e.g. fake fill) | Spoofing / Tampering | Validate `rt_cd` + fields before trusting (mirror `kis_quote`); fail safe. |
| Prompt injection via scraped news reaching the order | Tampering | Out of scope for Phase 5 changes — handled at the Phase 4 boundary (`<untrusted_news>` delimiters); LLM remains proposer-only, deterministic rules own trade math. |
| Discord webhook as an exfiltration/DoS channel | Information Disclosure / DoS | Fail-soft bounded retry; short timeout; message content is decisions only; webhook URL is a secret. |
| Audit-store repudiation ("bot traded without record") | Repudiation | Every cycle written to SQLite (OPS-02) with correlation ID to the raw structlog line (D-10); write per-ticker so a crash preserves completed records. |

## Sources

### Primary (HIGH confidence)
- Existing repo code (read this session): `trading_bot/kis_auth.py`, `kis_quote.py`, `ports.py`, `execution.py`, `mock_broker.py`, `config.py`, `domain.py`, `llm_provider.py`, `data_source.py`, `screener.py`, `tests/test_ports.py`, `tests/conftest.py`, `pyproject.toml`, `.planning/config.json` — grounds all "existing code" claims. [VERIFIED]
- `.claude/CLAUDE.md`, CONTEXT.md (D-01..D-14), REQUIREMENTS.md, STATE.md — locked decisions/constraints. [VERIFIED]
- pypi.org/pypi/typer/json — `typer` 0.26.8, `requires-python >=3.10`, deps rich/shellingham/annotated-doc. [CITED]

### Secondary (MEDIUM confidence — cross-confirmed across ≥2 sources)
- KIS order TR_IDs (`TTTC0802U`/`VTTC0802U` buy, `TTTC0801U`/`VTTC0801U` sell), `order-cash` endpoint, hashkey requirement, `ORD_DVSN`/`ORD_QTY`/`ORD_UNPR` body — apiportal.koreainvestment.com + github.com/koreainvestment/open-trading-api + wikidocs.net/163499 + multiple tutorials. [CITED]
- Balance `inquire-balance` (TTTC8434R/VTTC8434R), daily fills `inquire-daily-ccld` (TTTC8001R), buyable `inquire-psbl-order` (TTTC8908R), revise/cancel-able `inquire-psbl-rvsecncl` (TTTC8036R) — KIS portal + wikidocs.net/239689. [CITED]
- 2023-01-25 KRX tick-size reform bands — samsungpop.com notice MenuSeqNo=19236. [CITED]
- KRX regular session 09:00–15:30 KST, no lunch break — tradinghours.com/markets/krx + newtrading.io. [CITED]

### Tertiary (LOW confidence — mark for validation)
- Exact `inquire-daily-ccld` fill field spellings (`tot_ccld_qty`/`rmn_qty`) — inferred from KIS conventions; verify on portal (A2). [ASSUMED]
- Discord webhook ~30 req/min — general knowledge; verify current Discord docs (A6). [ASSUMED]

## Metadata

**Confidence breakdown:**
- Existing-code integration (ports, token reuse, CycleAuditEvent, factory pattern): HIGH — all files read this session.
- Standard stack (typer/sqlite3/httpx/tenacity/structlog): HIGH — pins verified in pyproject.toml, typer confirmed on PyPI.
- D-05 recommendation (direct REST over python-kis): HIGH — grounded in the actual `kis_auth`/`kis_quote` code and the D-14 hard constraint.
- KIS order-API mechanics (TR_IDs, endpoints, hashkey, tick bands, session): MEDIUM — cross-confirmed across official portal + koreainvestment GitHub + multiple tutorials, but not fetched from a single authenticated spec page; exact response field spellings LOW (A1/A2).
- Persistence/notification/CLI: HIGH design confidence, low risk.

**Research date:** 2026-07-02
**Valid until:** 2026-08-01 for KIS mechanics (verify tick bands / TR_IDs / field names against the live portal before implementing the real POST); 2026-08-01 for typer version.
