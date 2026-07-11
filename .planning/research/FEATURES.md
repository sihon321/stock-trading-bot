# Feature Research

**Domain:** Operational validation for a personal Korean-market LLM trading bot
**Milestone:** v1.1 Mock Soak & Replay Validation
**Researched:** 2026-07-11
**Confidence:** MEDIUM

## Research Boundary

This milestone should prove that the shipped v1.0 system is repeatable, observable, fail-safe, and reviewable. It should not add a new strategy, an always-on scheduler, a realistic portfolio backtester, or automatic real-money promotion.

The two validation modes have different jobs:

- **Backtest-lite replay** proves deterministic policy mechanics using historical daily inputs and frozen fixture signals. It does not prove LLM quality, fill realism, or profitability.
- **KIS mock-account soak** proves live adapter behavior, operator discipline, order idempotency/reconciliation, persistence, and safe degradation across real trading days. It does not prove live-market slippage or strategy profitability.

That distinction is a table-stakes product behavior. Reports and promotion checks must never merge the two evidence classes or overstate what either one proves.

## Existing Implementation Dependencies

| Existing seam | v1.1 leverage | Gap that must be closed |
|---|---|---|
| `cli.run_cycle` is injectable and Typer commands are thin | Reuse one orchestration path for soak and test doubles | Add explicit run lifecycle/status and persist ticker errors instead of returning them only in memory |
| `screen_daily_candidates(trading_date)` accepts an explicit date | Good base for point-in-time replay | Historical market rows must be frozen/as-of; replay must not fetch a live KIS quote or news |
| CLI defaults `expected_date` to today's KST date | Freshness is explicit in the data layer | A tradable intraday cycle may not yet have today's completed daily bar; define the session/cutoff contract instead of equating run date with latest allowed OHLCV date |
| `screen_candidates` has deterministic score ordering and ticker tie-break | Enables byte-stable replay results | Persist the full candidate funnel, including exclusions, not only final decisions |
| `execute_signal_cycle` is deterministic and adapter-free | Reuse the exact confidence/risk/sizing/dry-run gates in replay | Capture policy version/snapshot so old decisions remain reproducible after settings change |
| SQLite has `runs` and `decisions`, run/correlation/order IDs | Good report base | Add trading date, run kind, completion status, end time, policy/fixture provenance, error rows/events, and preferably broker reconciliation fields |
| `TRADING_MODE=mock` currently constructs in-memory `MockBroker` | Useful for unit tests and offline replay | This is not a KIS 모의투자 soak. Add an explicit KIS-paper broker path using mock credentials/domain/TR IDs while keeping real mode impossible without existing confirmation gates |
| `_daily_loss_state()` currently starts at zero each invocation | Existing kill-switch API can be reused | Soak/reporting need broker/audit-derived daily realized loss; otherwise the daily loss control is not being operationally exercised |
| `DataContext` contains compact current inputs only | Keeps LLM boundary small | Replay fixtures need separate provenance: as-of timestamp/date, input hash, fixture ID, and code/prompt/policy versions |

## Feature Landscape

### Table Stakes (v1.1 Must Have)

| Feature | Why Expected | Complexity | Acceptance-testable behavior |
|---|---|---:|---|
| **Canonical run lifecycle record** | A soak day cannot pass if the process started but silently died or skipped persistence | MEDIUM | Every invocation writes `STARTED`, then exactly one terminal state (`COMPLETED`, `COMPLETED_WITH_ERRORS`, `FAILED`, `REFUSED`), with KST trading date, UTC timestamps, run kind, mode, dry-run/execute state, candidate/attempt/success/error counts, and non-secret policy version |
| **Persist every terminal ticker outcome** | Reports and failure rates are wrong if exceptions exist only in CLI memory | MEDIUM | Success, HOLD, skip, parse failure, stale-data block, timeout, API error, duplicate suppression, and order ambiguity each produce a queryable row/event linked by `run_id` and `correlation_id`; no attempted ticker disappears from SQLite |
| **KRX session and data-cutoff contract** | Fixed clock times are unsafe unless every input has a declared as-of rule | MEDIUM | Each run binds `session_date`, `decision_at`, latest allowed completed daily bar, quote maximum age, and allowed order window; preflight rejects a future/incomplete daily bar, an unexpectedly old bar, or an order attempt outside the configured window |
| **Operator daily-cycle runbook** | Manual operation is only safe if timing, preflight, postflight, and triage are unambiguous | LOW | Runbook names KST market-session windows; documents `status → screen → run → report`; distinguishes dry-run, in-memory mock, KIS paper execution, and real mode; includes stop conditions, rerun rules, DB/log locations, broker reconciliation, and incident escalation |
| **Executable preflight/postflight checks** | Documentation alone cannot detect wrong mode, stale data, missing account state, or an unfinished prior run | MEDIUM | Preflight fails closed on non-trading day/date mismatch, wrong broker/environment binding, missing credentials/account, stale required data, unresolved prior ambiguous order, or unavailable audit DB; postflight verifies run terminal state and broker-vs-audit order/position consistency |
| **Point-in-time backtest-lite replay** | Historical replay must not use information that was unavailable at the decision date | HIGH | Given an explicit date range and frozen historical rows, each date uses trailing data only, respects indicator warm-up, performs no trade during warm-up, screens the as-of universe, and never calls KIS, Naver, or an LLM |
| **Versioned fixture-signal input** | Replay must be cheap, deterministic, and independent of provider drift/cost | MEDIUM | Fixture schema contains date, ticker, strict signal JSON, fixture-set version, and input provenance; missing/invalid fixtures fail to HOLD or a clearly reported replay error; the same fixture set and policy produce identical ordered decisions and hashes |
| **Production-gate parity in replay** | A separate replay rule implementation would validate the wrong system | MEDIUM | Replay invokes the shipped parser, confidence gates, risk precedence, sizing, and dry-run boundary; tests prove no broker mutation and no network/LLM calls; replay records would-be order and no-trade reason |
| **Replay manifest and summary** | Results need enough provenance to reproduce and compare | MEDIUM | Every replay records date range, eligible KRX dates, fixture/data hashes, code revision, policy snapshot/version, initial cash/positions, counts by decision/final action/no-trade reason, and deterministic output ID |
| **Explicit KIS-paper broker path** | In-memory `MockBroker` cannot validate KIS authentication, rate limits, POST ambiguity, readback, or reconciliation | HIGH | Operator can choose KIS 모의투자 without enabling real credentials/domain/TR IDs; startup banner names both `broker=kis-paper` and `trading_mode=mock`; real endpoint use remains blocked by existing confirmation controls |
| **N-eligible-day soak campaign** | Merely running several times is not evidence of operational stability | HIGH | A campaign manifest defines target eligible KRX days, policy/code version, allowed broker, required daily steps, and pass criteria; progress counts completed eligible days, not weekends/holidays; any safety-invariant breach resets or invalidates the clean-day streak |
| **Soak invariants and failure budget** | Promotion requires objective criteria, not a subjective “looked fine” judgment | MEDIUM | Zero real-endpoint attempts, unjustified orders, duplicate orders, blind POST retries, missing terminal outcomes, or unreconciled ambiguous orders are allowed; availability failures may be tolerated only within a declared budget and must fail safe to no new order |
| **Fault-path drills** | Rare safety paths may never occur naturally during an N-day soak | HIGH | Deterministic tests/drills cover stale OHLCV/quote, LLM timeout/malformed output, KIS read timeout, ambiguous order POST, duplicate rerun, partial fill, notification failure, audit write failure, and interrupted run; each has an expected persisted outcome and broker-mutation assertion |
| **Daily decision report from SQLite** | Human review needs one compact, reproducible explanation of what happened | MEDIUM | `report --date` renders deterministic Markdown/text from canonical DB data, grouped by run and ticker, with candidate funnel, signal/confidence, final action, risk override, would-be/order/fill outcome, errors, no-trade reason, and unresolved anomalies |
| **Campaign/period report** | One-day reports cannot establish soak readiness | MEDIUM | `report --from/--to` shows eligible/completed/missed days, run success rate, ticker outcome counts, confidence bands, no-trade reasons, API/timeout/error rates, duplicate suppression, reconciliation exceptions, and current clean-day streak |
| **Policy snapshot and comparison** | Threshold changes otherwise make historical evidence irreproducible | MEDIUM | Every run/replay stores normalized non-secret values for buy/sell confidence, cash fraction, position cap, stop-loss, take-profit, and daily-loss threshold plus a policy ID/hash; reports compare named policies without mutating history |
| **Risk calibration worksheet, not auto-tuning** | Small samples and uncalibrated LLM self-scores do not justify autonomous optimization | HIGH | For frozen evidence, compare a small predeclared grid of policy candidates and report trade coverage, rejected/accepted counts, exposure/order-size distribution, risk-trigger counts, and forward outcome bands where available; no candidate is automatically activated |
| **Real-money promotion checklist** | Paper success alone does not establish live fill quality or profitability | MEDIUM | Promotion remains manual and requires clean soak criteria, zero unresolved severity-high incidents, reviewed daily/period reports, policy freeze, rollback/kill procedure, secret/config check, tiny-size live pilot plan, and explicit acknowledgement of paper-fill limitations |

### Differentiators (High Value, Not Required for Core v1.1)

| Feature | Value Proposition | Complexity | Notes |
|---|---|---:|---|
| **Replay/soak parity diff** | Shows whether the same date/ticker/policy reached different final actions and why | HIGH | Compare decision path and gate reason, not P&L; differences should be attributable to fixture vs live inputs, broker state, or adapter outcome |
| **Tamper-evident provenance chain** | Makes a result defensible months later | MEDIUM | Hash normalized input fixture, policy, prompt/model metadata where relevant, and rendered report; useful for personal audit without enterprise infrastructure |
| **Candidate-funnel quality report** | Explains “why no trades?” before changing risk thresholds | MEDIUM | Counts universe → data-valid → screener survivor → LLM BUY/SELL/HOLD → execution-qualified → ordered; separates screener strictness from confidence-gate strictness |
| **One-command evidence bundle** | Simplifies incident review and promotion review | MEDIUM | Export report plus redacted run manifest, policy snapshot, relevant structured logs, and reconciliation rows; exclude secrets and raw untrusted news by default |
| **Metamorphic safety tests** | Proves invariants across broad generated inputs | HIGH | Examples: lowering confidence cannot create a BUY; reducing cash cannot increase quantity; dry-run never mutates broker; risk SELL cannot be overridden by LLM BUY |
| **Shadow policy comparison** | Evaluates candidate thresholds without changing mock orders | MEDIUM | Current policy remains authoritative; alternative policies produce counterfactual would-be actions only and are clearly labeled |

### Anti-Features (Explicitly Do Not Build in v1.1)

| Feature | Why Requested | Why Problematic | Alternative |
|---|---|---|---|
| **Full portfolio backtester with P&L claims** | Appears to prove strategy quality | Requires realistic fills, fees, slippage, corporate actions, point-in-time universe, cash/position lifecycle, and intraday ordering; daily OHLCV cannot resolve stop-vs-target order within a bar | Backtest-lite only for screener/gate mechanics and sensitivity counts |
| **Historical replay with live LLM calls** | Seems closer to production reasoning | Model knowledge can leak future events, provider/model drift destroys reproducibility, and cost/latency obscure gate validation | Frozen strict fixture signals; separately assess live LLM behavior during forward soak |
| **Treat `confidence=0.8` as 80% win probability** | Makes threshold selection feel statistical | LLM self-confidence is not calibrated; small soak samples cannot establish reliability | Treat confidence as ordinal evidence; show score bands and empirical outcomes with sample counts and uncertainty |
| **Automatic threshold/stop optimization** | Promises objective best settings | Encourages overfitting and silent policy drift; stop/take optimization on daily bars is especially ambiguous | Predeclared manual comparison, holdout/forward evidence, policy versioning, human approval |
| **Auto-promotion from mock to real** | Removes operator friction | Paper fills differ from live execution and mock success cannot prove profitability or market impact | Explicit checklist, policy freeze, manual confirmation, tiny-size live pilot |
| **Always-on scheduler or intraday polling** | Makes the bot feel automated | Expands failure surface before manual daily operation is proven and conflicts with current milestone scope | Keep manual KST runbook; revisit only after a clean soak |
| **Strategy expansion during soak** | More signals might produce more data | Invalidates the baseline and makes defects/calibration changes impossible to attribute | Freeze strategy/prompt/policy per campaign; restart evidence after material changes |
| **Web dashboard first** | Attractive visibility | Adds auth, hosting, and UI scope while SQLite-to-Markdown/CSV meets personal review needs | Deterministic CLI reports and optional CSV export |
| **Store raw prompts/news/API payloads in SQLite reports** | Maximum forensic detail | Increases secret, personal-data, prompt-injection, and retention risk; duplicates structured logs | Store bounded structured fields, hashes, versions, health statuses, and correlation IDs; keep redacted logs separate |
| **Count weekends, retries, or multiple same-day runs as soak days** | Reaches N faster | Measures invocations rather than independent market-day operation | Count one reviewed, terminal, eligible KRX day per campaign day; retain extra runs as diagnostics |
| **Use in-memory `MockBroker` results as KIS soak evidence** | Easy and already available | Does not exercise KIS transport, credentials, rate limits, order ambiguity, fills, or broker truth | Label it offline simulation; require the explicit KIS-paper path for broker soak |

## Feature Dependencies

```text
[Audit schema + migration + run lifecycle]
    ├──requires──> [Persist every ticker terminal outcome]
    ├──enables───> [Daily/period reports]
    ├──enables───> [Soak campaign scoring]
    └──enables───> [Promotion evidence]

[Policy snapshot/version]
    ├──enables───> [Deterministic replay]
    ├──enables───> [Calibration comparison]
    └──enables───> [Replay/soak parity diff]

[Frozen point-in-time data + fixture signals]
    └──requires──> [Replay runner using production parser/risk/execution gates]
                         └──enables───> [Replay manifest + sensitivity report]

[Explicit KIS-paper broker path]
    └──requires──> [Preflight + reconciliation + ambiguity handling]
                         └──enables───> [N-day soak campaign]
                                              └──enables───> [Promotion checklist]

[Fault-path drills] ──complements──> [Natural N-day soak]
[KRX session/data-cutoff contract] ──requires-before──> [Fixed daily runbook timing]
[In-memory MockBroker] ──conflicts-as-evidence-with──> [KIS-paper soak claim]
[Strategy/prompt changes mid-campaign] ──invalidate──> [Clean comparable soak streak]
```

### Dependency Notes

- **Audit foundation comes first.** Reports, soak pass/fail, and calibration all become misleading if failed attempts are absent or runs have no terminal state.
- **Replay and soak should share policy/execution code, not data adapters.** Replay must be network-free and point-in-time; soak must use live KIS paper adapters and broker state.
- **KIS paper is a separate broker choice from in-memory mock.** Keep both, but label them unambiguously in startup output, audit rows, and reports.
- **Fault drills do not need to wait N days.** Build deterministic injected failures before the natural soak so expected safe outcomes are known in advance.
- **Calibration depends on immutable evidence.** A material code, prompt, model, data, or policy change starts a new cohort/campaign; do not blend incompatible runs.
- **Forward outcome labels are optional for operational readiness.** They are required before making claims about confidence quality or risk-return, but not to prove fail-safe mechanics.

## Recommended v1.1 Scope

### Launch With (P1)

- [ ] Audit schema migration with run lifecycle, run kind, trading date, policy provenance, and persisted error/no-trade outcomes
- [ ] Deterministic daily and period CLI reports
- [ ] KRX session/data-cutoff contract covering completed daily bars, quote freshness, and order window
- [ ] KST manual runbook plus executable preflight/postflight checks
- [ ] Offline point-in-time replay with frozen fixture signals and zero network/LLM calls
- [ ] Explicit, safely bound KIS-paper broker path distinct from `MockBroker`
- [ ] N-eligible-day soak campaign manifest, invariants, clean-streak accounting, and broker reconciliation
- [ ] Deterministic fault-path drills for duplicate, timeout, stale-data, API ambiguity, partial-fill, interruption, and persistence failure
- [ ] Versioned policy comparison and manual promotion checklist

### Add After Core Evidence Works (P2)

- [ ] Candidate-funnel report and shadow-policy comparison
- [ ] Replay/soak decision-path parity diff
- [ ] One-command redacted evidence bundle
- [ ] Forward outcome labeling and confidence-band reliability view after enough observations exist

### Defer Beyond v1.1 (P3)

- [ ] Full portfolio/P&L backtester with transaction-cost and fill models
- [ ] Automated calibration or policy optimizer
- [ ] Web dashboard
- [ ] Scheduler/always-on loop
- [ ] Real-money automation beyond a separately approved tiny-size pilot

## Feature Prioritization Matrix

| Feature | Safety/Operator Value | Implementation Cost | Priority |
|---|---:|---:|---:|
| Audit completeness + run lifecycle | HIGH | MEDIUM | P1 |
| KRX session/data-cutoff contract | HIGH | MEDIUM | P1 |
| Daily-cycle runbook + checks | HIGH | MEDIUM | P1 |
| Point-in-time fixture replay | HIGH | HIGH | P1 |
| Explicit KIS-paper broker path | HIGH | HIGH | P1 |
| N-day soak campaign + invariants | HIGH | HIGH | P1 |
| Fault-path drills | HIGH | HIGH | P1 |
| Daily/period reports | HIGH | MEDIUM | P1 |
| Policy snapshot + manual comparison | HIGH | MEDIUM | P1 |
| Promotion checklist | HIGH | LOW | P1 |
| Candidate funnel | MEDIUM | MEDIUM | P2 |
| Replay/soak parity diff | MEDIUM | HIGH | P2 |
| Evidence bundle | MEDIUM | MEDIUM | P2 |
| Full P&L backtester | LOW for this milestone | HIGH | P3 |
| Dashboard/scheduler | LOW for this milestone | HIGH | P3 |

## Acceptance Behavior Catalog

These behaviors are suitable for downstream requirements and UAT:

1. **Network isolation:** replay fails the test if KIS, Naver, Anthropic/OpenAI, or Codex subprocess adapters are invoked.
2. **Determinism:** two replays with identical data, fixtures, initial state, and policy produce the same ordered decisions, reasons, quantities, and result hash.
3. **Point-in-time discipline:** a date D replay cannot read bars, universe membership, labels, or fixtures first available after D's declared decision cutoff.
4. **Session cutoff:** an operational run cannot use an incomplete future daily bar or place an order outside its declared KRX window; its audit record distinguishes session date from latest completed OHLCV date.
5. **Warm-up safety:** insufficient trailing bars cause a recorded skip/HOLD and never an order.
6. **Gate parity:** threshold boundary values, sizing, risk override, and daily-loss behavior match production execution tests exactly.
7. **Mode binding:** KIS paper execution can never select the real domain, app credentials, account, or order TR ID; startup and audit identify the selected broker/environment.
8. **No blind retry:** an ambiguous KIS order POST leads to reconciliation; rerunning the same intent cannot submit a duplicate.
9. **Fail-safe degradation:** stale data, malformed signals, timeouts, unavailable account truth, and audit persistence failures produce no new order.
10. **Audit completeness:** `attempted_tickers = terminal_decision_rows + terminal_error/skip_rows` for every completed run.
11. **Report reproducibility:** report output for an unchanged DB and options is stable and totals reconcile to source rows.
12. **Soak day eligibility:** only one reviewed terminal campaign result per open KRX day advances the clean streak.
13. **Campaign invalidation:** a safety-invariant breach or material unversioned change prevents promotion and resets/ends the clean cohort.
14. **Calibration restraint:** comparison output includes observation counts and coverage; it cannot write active settings or claim self-confidence is a probability.
15. **Promotion restraint:** passing replay and soak never toggles real mode; real promotion still requires deliberate external configuration and confirmation.

## Sources

### Primary / Official

- [FINRA Regulatory Notice 15-09 — algorithm testing, pilot deployment, heightened monitoring, reconciliation, and records](https://www.finra.org/rules-guidance/notices/15-09) — MEDIUM confidence after cross-check
- [FCA multi-firm review of algorithmic trading controls — simulated stress testing and calibrated pre/post-trade controls](https://www.fca.org.uk/publications/multi-firm-reviews/algorithmic-trading-controls-high-level-observations) — MEDIUM confidence after cross-check
- [SEC Rule 613 Consolidated Audit Trail — lifecycle linkage, identifiers, and synchronized timestamps](https://www.sec.gov/about/divisions-offices/division-trading-markets/rule-613-consolidated-audit-trail) — MEDIUM confidence after cross-check
- [17 CFR §38.552 — sequential source records and analyzable transaction history](https://www.law.cornell.edu/cfr/text/17/38.552) — MEDIUM confidence after cross-check
- [Korea Investment & Securities official Open Trading API repository — separate paper environment and official backtester](https://github.com/koreainvestment/open-trading-api) — MEDIUM confidence
- [IBKR official paper-trading limitations — simulator behavior can differ from exchange behavior](https://www.interactivebrokers.com/campus/glossary-terms/paper-trading-account/) — MEDIUM confidence; used only as cross-broker evidence of simulation limits
- [QuantConnect point-in-time precomputed prediction guidance — trailing-only inputs and frozen prediction reproducibility](https://www.quantconnect.com/docs/v2/writing-algorithms/importing-data/streaming-data/precomputed-ml-predictions) — MEDIUM confidence
- [QuantConnect live/backtest reconciliation — lookahead, data normalization, timing, and corporate-action divergence](https://www.quantconnect.com/docs/v2/writing-algorithms/live-trading/reconciliation) — MEDIUM confidence
- [QuantConnect warm-up guidance — prepare indicators and prohibit trades during warm-up](https://www.quantconnect.com/docs/v2/writing-algorithms/historical-data/warm-up-periods) — MEDIUM confidence
- [scikit-learn probability calibration guide — reliability interpretation and disjoint calibration data](https://scikit-learn.org/stable/modules/calibration.html) — MEDIUM confidence

### Project Evidence

- `.planning/PROJECT.md`, `.planning/MILESTONES.md`, `.planning/STATE.md`
- `trading_bot/cli.py`, `trading_bot/sqlite_audit.py`, `trading_bot/execution.py`, `trading_bot/screener.py`, `trading_bot/data_source.py`, `trading_bot/domain.py`

## Confidence Notes and Open Questions

- **HIGH confidence in code dependencies:** conclusions about current SQLite fields, exception persistence, explicit trading dates, deterministic execution, and `MockBroker` selection come directly from the repository.
- **MEDIUM confidence in ecosystem recommendations:** GSD confidence classification for cross-checked websearch evidence is MEDIUM even when the underlying pages are official.
- Confirm exact KIS mock-account order restrictions, rate limits, supported order types, and reconciliation endpoints against the authenticated KIS developer portal during implementation; public repository evidence is not sufficient for exact operational limits.
- Choose the operational session contract before fixing runbook clock times. The current `expected_date=today` behavior must be reconciled with when a completed pykrx daily bar is actually available and when KIS accepts the intended order type.
- Define N and the allowed availability-failure budget during requirements. Recommendation: use consecutive eligible KRX days and zero tolerance for safety-invariant breaches, but do not invent a statistically meaningful profitability claim from a short personal soak.
- Decide the forward outcome definition before any confidence calibration claim (for example, fixed D+1/D+5 close return or barrier event). Keep this out of the operational pass gate unless enough independent observations are collected.

---
*Feature research for: Stock Trading Bot v1.1 Mock Soak & Replay Validation*
*Researched: 2026-07-11*
