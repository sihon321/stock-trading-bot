# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 — MVP

**Shipped:** 2026-07-03
**Phases:** 5 | **Plans:** 21 | **Commits:** 150

### What Was Built
- A safety-first KR LLM trading bot: data pipeline (pykrx OHLCV + indicators + screener, KIS
  price, sanitized Naver news) → switchable Claude/OpenAI provider → deterministic risk/execution
  core → idempotent reconciled KISBroker, all behind a mock-first, gated real-money promotion.
- An LLM-independent risk net (stop-loss/take-profit + daily-loss kill switch) that overrides
  conflicting LLM signals, plus a fail-safe parser where any unparseable output ⇒ HOLD.
- A manual Typer CLI (`bot run/screen/status`) with dry-run default, SQLite per-cycle audit, and
  fail-soft Discord notifications.

### What Worked
- **Ports-before-adapters ordering.** Introducing each Protocol (Broker, LLMProvider, DataSource)
  before its first concrete adapter meant no later phase had to rewrite an earlier one.
- **Risk-first, LLM-last sequencing.** Building the fully testable execution core (Phase 2) with
  zero external deps before attaching real data (Phase 3) and the LLM (Phase 4) kept every trade
  decision provable against hand-written signals — the LLM plugged into an already-proven chain.
- **Wave-based parallelization** within phases kept independent plans moving concurrently while
  respecting real dependencies (e.g. Phase 3 Wave 2 fanned out screener/price/news adapters).

### What Was Inefficient
- **A requirement slipped a phase.** OPS-02 (persist LLM confidence to the audit store) needed a
  dedicated gap-closure plan (05-05) after Phase 5's main waves — the confidence field wasn't
  threaded through `ExecutionResult` to the SQLite `decisions.confidence` column the first time.
- **A library deprecation surfaced late.** A pandas 2.3.3 generic-unit `Timedelta`
  DeprecationWarning blocked a Phase 3 plan (Rule 3), costing rework that earlier dependency
  verification could have caught.

### Patterns Established
- **Atomic mode binding for safety-critical config** — mock/real KIS credentials + domain + TR_ID
  swap together; no independent setter exists, so a partial swap can never trade real money.
- **Fail-safe defaults everywhere** — bad data ⇒ SKIP_CANDIDATE / FORCE_HOLD; unparseable signal ⇒
  HOLD; scrape failure ⇒ "no news" and continue. The safe path is the default path.
- **Query-before-POST idempotency** in the order path — reconcile against broker truth before
  resubmitting; never blind-retry an order POST.

### Key Lessons
1. Verify requirement-to-write-site traceability *within* the phase that owns the requirement —
   OPS-02 proved a requirement can be "implemented" in spirit while a column stays unwritten.
2. Pin and smoke-test data-lib versions early; transitive deprecations (pandas) can block a plan
   mid-phase if only discovered at execution time.
3. Sequencing safety/risk logic before the probabilistic component (the LLM) pays off — the
   deterministic net is testable, and the LLM becomes a suppressible input rather than an authority.

### Cost Observations
- Model mix: predominantly opus (adaptive profile).
- Notable: the zero-external-dep Phase 2 core made the highest-risk logic the cheapest to test.

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Plans | Key Change |
|-----------|--------|-------|------------|
| v1.0 | 5 | 21 | Baseline — ports-before-adapters, risk-first sequencing, wave parallelization |

### Cumulative Quality

| Milestone | Test Files | LOC (Python) | Requirements Shipped |
|-----------|-----------|--------------|----------------------|
| v1.0 | 22 | ~11,272 | 23/23 |

### Top Lessons (Verified Across Milestones)

1. _(pending second milestone for cross-validation)_
