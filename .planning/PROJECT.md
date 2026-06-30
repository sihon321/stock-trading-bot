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

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Data pipeline: fetch daily OHLCV + technical indicators via `pykrx`
- [ ] Data pipeline: fetch real-time prices via the KIS API
- [ ] Data pipeline: scrape per-ticker financial news from Naver Finance (네이버 금융)
- [ ] Daily screening selects candidate tickers from the market (e.g. volume/momentum via `pykrx`)
- [ ] LLM agent: feed collected data as context to a switchable provider (Claude or OpenAI)
- [ ] LLM agent: enforce strict JSON output `{"decision","confidence","reason"}` with no markdown
- [ ] Execution: parse signal; BUY when `decision=="BUY"` and `confidence >= 0.8`
- [ ] Execution: position sizing as a % of available capital, with a max-position cap
- [ ] Execution: SELL on LLM `decision=="SELL"` (confidence threshold) for held positions
- [ ] Execution: automatic stop-loss / take-profit safety net independent of the LLM
- [ ] Run against the KIS mock (모의투자) account first; promote to real money only after validation
- [ ] Manual trigger runs a full evaluation cycle on demand
- [ ] Dry-run mode: log the would-be decision/order without placing it
- [ ] Log every cycle's data context, LLM signal, and order outcome for review

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
- **Usage:** Personal tool, run manually per evaluation cycle.

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
| Mock account first, real money later | Validate logic with zero capital risk before going live | — Pending |
| Switchable LLM provider (Claude/OpenAI), not ensemble | Simpler v1; one provider at a time, swap via config | — Pending |
| Daily screening for the trading universe | Surface candidates dynamically rather than a fixed list | — Pending |
| Manual trigger (no scheduler) for v1 | Keep the operator in the loop while logic is unproven | — Pending |
| % -of-capital sizing with max-position cap | Scales with account size while bounding single-trade risk | — Pending |
| Rules-based stop-loss/take-profit on top of LLM SELL | Safety net independent of LLM judgment | — Pending |
| Strict JSON LLM contract, fail-safe on parse error | Programmatic execution requires deterministic, parseable signals | — Pending |

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
*Last updated: 2026-06-30 after initialization*
