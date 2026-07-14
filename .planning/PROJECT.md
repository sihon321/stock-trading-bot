# Stock Trading Bot (KR / LLM-driven)

## What This Is

A personal, Korean-market automated trading bot that turns collected market data into
trading decisions via an LLM. It runs as three pipelines: a **data pipeline** (daily market
data + technical indicators via `pykrx`, real-time prices via the KIS API, and financial news
scraped from Naver Finance), an **LLM agent pipeline** (feeds the data as context to a
switchable LLM provider — Claude or OpenAI — which must emit a strict JSON trading signal),
and a **trading execution pipeline** (parses the signal and places orders through the KIS API).
Built for the owner's own use, safety-first: it validates against the KIS mock (모의투자)
account before ever touching real money.

## Core Value

Given fresh market data, the bot produces a trustworthy, machine-checkable trading signal and
acts on it through KIS — without placing an order the rules don't justify.

## Current Milestone: v1.1 Mock Soak & Replay Validation

**Goal:** Prove, through repeated KIS mock-account operation over days to weeks, that the bot can
run safely each day and that every order or hold decision can be explained and reproduced.

**Target features:**
- Runbook and daily-cycle documentation for `bot run`, `bot screen`, and `bot status`, including
  fixed market-session timing and failure triage.
- Backtest-lite replay over historical OHLCV through screener, fixture signal, and execution gates
  before spending real LLM calls.
- N-day KIS mock-account soak testing that records every cycle to the audit DB and exercises duplicate
  order, API failure, stale data, and timeout paths.
- Human-readable decision review reports from SQLite audit history, grouped by date with candidates,
  LLM decisions, confidence, order outcomes, and no-trade reasons.
- Data-driven risk policy calibration for confidence threshold, position cap, stop-loss/take-profit,
  plus a stronger real-money promotion checklist.

## Requirements

### Validated

_Milestone v1.0 complete — all requirements shipped and verified. IDs trace to `.planning/REQUIREMENTS.md`._

- [x] EVID-01: every mutable run records a terminal lifecycle state, KST date, run kind, target, policy snapshot, and provenance — Phase 6
- [x] EVID-02: every attempted screen/run ticker records exactly one normalized terminal outcome — Phase 6
- [x] EVID-03: order intent, submission, ambiguity, duplicate suppression, and reconciliation remain attributable to ticker and run — Phase 6
- [x] EVID-04: executable cycles enforce and record KRX session, completed-bar cutoff, and pre-submit quote freshness — Phase 6
- [x] RUN-01/RUN-02: Korean fixed-session operator runbook defines preflight, execution, evidence review, failure triage, and safe recovery — Phase 8
- [x] REP-01/REP-02: SQLite audit history and replay evidence produce deterministic daily, period, and replay decision reports with explicit denominators and unknown states — Phase 8

- [x] CFG-01: typed gitignored settings load KIS and LLM secrets without leaking them to logs — Phase 1
- [x] CFG-02: trading mode atomically selects mock or real KIS credentials, endpoint, and TR_ID — Phase 1
- [x] CFG-03: exactly one active LLM provider is selected per run — Phase 1
- [x] CFG-04: defaults to `mock`; switching to `real` requires an explicit, deliberate config change — Phase 5
- [x] DATA-01/02: daily OHLCV + technical indicators via `pykrx`, fail-safe to HOLD on bad frames — Phase 3
- [x] DATA-03: real-time price via the KIS API through a shared auto-refreshed token — Phase 3
- [x] DATA-04: per-ticker Naver Finance news scrape with sanitization + graceful degradation — Phase 3
- [x] DATA-05: daily market screen selects candidate tickers for the cycle — Phase 3
- [x] LLM-01: collected data context fed to a switchable Claude/OpenAI provider interface — Phase 4
- [x] LLM-02/03: strict JSON `{"decision","confidence","reason"}`, schema-revalidated, fail-safe to HOLD — Phase 4
- [x] EXEC-01: BUY only when `decision=="BUY"` AND `confidence >= 0.8` — Phase 2
- [x] EXEC-02: BUY sizing as a configurable % of available capital, bounded by a max-position cap — Phase 2
- [x] EXEC-03: SELL on `decision=="SELL"` (confidence threshold) for held positions — Phase 2
- [x] EXEC-04: orders route through KIS (mock first), idempotent — reconciles before resubmitting, never blind-retries a POST — Phase 5
- [x] EXEC-05: dry-run mode logs the would-be decision/order without placing it — Phase 2
- [x] RISK-01: rules-based stop-loss / take-profit net evaluates held positions independent of the LLM — Phase 2
- [x] RISK-02: on conflict, the risk net takes precedence over the LLM signal — Phase 2
- [x] RISK-03: daily-loss kill switch halts new trading once the loss threshold is breached — Phase 2
- [x] OPS-01: operator triggers a full evaluation cycle on demand (manual CLI, no scheduler) — Phase 5
- [x] OPS-02: every cycle's data context, LLM signal (incl. confidence), risk decisions, and order outcome persist to a reviewable audit store — Phase 5
- [x] OPS-03: each cycle's decision and order outcome pushed to the operator via a notification channel — Phase 5

### Active

- [ ] Historical replay can run screener + fixture signal + execution gate without live LLM calls to
  evaluate whether BUY policy is too strict or too loose.
- [ ] Mock-account soak workflow supports repeated dry-run/mock execution with audit persistence and
  observable handling for duplicate orders, API failures, stale data, and timeouts.
- [ ] Risk policy and real-money promotion readiness can be reviewed from collected replay/soak data.

### Out of Scope

- Intraday polling / always-on loop — v1 is manual-trigger only; revisit if needed
- Ensemble/consensus across both LLMs — switchable single provider for v1; ensemble is a later option
- Non-Korean markets — KIS + pykrx are KR-specific by design
- Portfolio optimization / multi-strategy allocation — single-signal execution for v1

## Context

- **Market:** Korean equities. Data via `pykrx` (KRX daily data + indicators) and the
  KIS (한국투자증권) Open API for real-time prices and order execution.
- **News:** Naver Finance per-ticker news pages as the scraping source.
- **LLM:** Provider is switchable via config — Anthropic (Claude) and OpenAI both supported,
  one active at a time. Output contract is a strict JSON object, no markdown fences.
- **Safety posture:** Mock account first, dry-run capability, and a rules-based stop-loss/
  take-profit net that does not depend on the LLM. The bot must never place an order the
  explicit rules don't justify.
- **Usage:** Personal tool, run manually per evaluation cycle via the `bot run/screen/status` Typer CLI.
- **Shipped state (v1.0):** ~11,272 LOC Python across 48 modules with 22 test files. Stack in
  use: `pydantic` / `pydantic-settings`, `pykrx` + `ta`, direct KIS REST over `httpx`,
  `anthropic` / `openai` behind one provider port, `typer` CLI, SQLite audit store, `structlog`,
  and fail-soft Discord notifications. Real-money path exists but is gated behind an explicit,
  confirmed `TRADING_MODE=real` promotion; the bot defaults to the mock (모의투자) account.

## Constraints

- **Tech stack**: Python — required by `pykrx` and the KIS API boilerplate.
- **Data source**: Korea-only (pykrx + KIS) — the bot is KR-market specific.
- **LLM output**: Must be strict JSON `{"decision","confidence","reason"}`, no markdown — the
  execution pipeline parses it programmatically and unparseable output must fail safe (no trade).
- **Account safety**: KIS mock (모의투자) account is the first target; real-money promotion is a
  deliberate, gated step.
- **Execution gate**: A BUY requires `confidence >= 0.8`; lower-confidence or HOLD signals never trade.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Mock account first, real money later | Validate logic with zero capital risk before going live | ✓ Shipped — Phase 5 gated real-money promotion behind `TRADING_MODE=real` + `CONFIRM_REAL_TRADING` |
| Switchable LLM provider (Claude/OpenAI), not ensemble | Simpler v1; one provider at a time, swap via config | ✓ Shipped — Phase 4 provider port |
| Daily screening for the trading universe | Surface candidates dynamically rather than a fixed list | ✓ Shipped — Phase 3 screener |
| Manual trigger (no scheduler) for v1 | Keep the operator in the loop while logic is unproven | ✓ Shipped — Phase 5 typer CLI (`bot run/screen/status`) |
| % -of-capital sizing with max-position cap | Scales with account size while bounding single-trade risk | ✓ Shipped — Phase 2 |
| Rules-based stop-loss/take-profit on top of LLM SELL | Safety net independent of LLM judgment | ✓ Shipped — Phase 2 risk net (takes precedence on conflict) |
| Strict JSON LLM contract, fail-safe on parse error | Programmatic execution requires deterministic, parseable signals | ✓ Shipped — Phase 4 structured output, HOLD on parse failure |
| D-05: extend direct-REST KIS layer, not adopt `python-kis` | Zero third-party trust in the order path; reuse the shared token manager | ✓ Shipped — Phase 5 `kis_order.py` + `KISBroker` |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-07-14 after completing Phase 8 — Decision Reports & Operator Runbook*
