# Pitfalls Research

**Domain:** v1.1 operational confidence for a safety-first Korean-market automated trading bot
**Researched:** 2026-07-11
**Confidence:** MEDIUM overall — HIGH for findings derived from the current code; MEDIUM for ecosystem findings cross-checked against current primary documentation through the GSD research seam

This research is deliberately narrower than the v1.0 pitfall survey. It covers mistakes introduced while adding runbooks, point-in-time replay, KIS mock-account soak testing, SQLite reports, and data-driven risk review. The objective is evidence for promotion, not a relaxation of the real-money gate.

## Recommended Roadmap Order

1. **Phase 1 — Evidence Contract & Operational Baseline:** make every attempted ticker and run terminal state auditable; wire freshness and cumulative risk state correctly; create the runbook skeleton and safety invariants.
2. **Phase 2 — Point-in-Time Replay:** reuse the production screener and execution policy with deterministic, dated inputs and a scenario matrix; explicitly exclude live LLM calls and broker side effects.
3. **Phase 3 — KIS Mock Soak & Fault Injection:** exercise the actual KIS mock domain/account, reconciliation, restart, timeout, throttling, partial-fill, and duplicate-order paths over N trading days.
4. **Phase 4 — Review Reports & Runbook Drills:** generate snapshot-consistent daily reports, reconcile them to broker truth, and rehearse abort/recovery procedures.
5. **Phase 5 — Risk Calibration & Promotion Review:** analyze frozen replay/soak evidence on untouched time windows, recommend policy changes in shadow mode, and strengthen—not bypass—the real-money checklist.

The order is safety-critical. Replay, soak, and reports cannot establish confidence until the audit record distinguishes attempted, failed, incomplete, duplicate-suppressed, submitted, partially filled, and reconciled outcomes.

## Critical Pitfalls

### Pitfall 1: Calling an in-memory run a “KIS mock-account soak” (HIGH)

**What goes wrong:**
The soak reports many successful mock cycles but never exercises KIS authentication, mock REST limits, order queries, order POSTs, fill readback, or broker state. The evidence supports only local execution logic.

**Why it happens:**
In the current `trading_bot/cli.py`, `_build_broker()` returns `MockBroker` whenever `trading_mode` is `mock`. Therefore even `bot run --execute` in mock mode does not construct `KISBroker`. KIS account configuration is currently required only for real mode. The labels “mock,” “dry-run,” and “KIS mock” are easy to conflate.

**How to avoid:**
- Model two independent axes: **broker backend** (`local`, `kis`) and **KIS environment** (`mock`, `real`). Keep `real` separately gated by the existing confirmation controls.
- Require the KIS mock account number and mock credentials for a KIS soak; print backend, environment, account suffix, and dry-run/execute state in the banner and audit run header.
- Keep local `MockBroker` for deterministic unit/replay tests, but never count those runs toward KIS soak acceptance.
- Define soak acceptance in trading sessions and actual KIS API interactions, not merely process invocations.

**Warning signs:**
- Mock soak produces `MOCK-N` IDs or no KIS order IDs.
- No KIS query/POST latency, rate-limit, auth, or fill-readback events appear.
- The mock account UI balance and holdings do not change after an “executed” soak order.

**Specific tests/checks:**
- Composition test: `backend=kis`, `environment=mock`, `execute=true` constructs `KISBroker` with mock domain/TR IDs and never loads real credentials.
- Negative test: missing mock account descriptor aborts before screening or LLM invocation.
- End-to-end smoke: one tiny mock order appears in KIS inquiry results and is linked to one local intent/audit row.

**Phase to address:** Phase 1 establishes the explicit backend/environment contract; Phase 3 proves it against KIS mock.

---

### Pitfall 2: Collecting soak data before fixing incomplete and misattributed audit records (HIGH)

**What goes wrong:**
Reports undercount failures, mark partial runs as healthy, or attach a previous ticker's fill quantity to a later HOLD/error. Subsequent calibration treats corrupted denominators as evidence.

**Why it happens:**
- `runs` has no `completed_at`, terminal status, expected/attempted candidate count, policy version, or error count.
- Per-ticker exceptions in `run_cycle()` are returned and notified but are not inserted into `decisions` or a failure table.
- `KISBroker.last_reconciliation` is mutable broker-global state. The CLI reads it after every cycle without checking ticker/order ID and the broker does not clear it for a HOLD or duplicate-suppressed order. A later decision can inherit stale `requested_qty`/`filled_qty`.
- Each row commits independently, so a process crash leaves a plausible run header plus a prefix of decisions.

**How to avoid:**
- Version and migrate the audit schema before collecting milestone evidence.
- Give every run a lifecycle (`STARTED`, `COMPLETED`, `COMPLETED_WITH_ERRORS`, `ABORTED`) and counts for screened, attempted, succeeded, failed, skipped, and unresolved.
- Persist one terminal outcome for every attempted ticker, including data-build and provider errors. Never infer “no error” from a missing row.
- Return reconciliation as part of that ticker's immutable execution result. At minimum, clear broker-global reconciliation before each order attempt and accept it only when ticker and broker order ID match.
- Store policy/config version, replay/soak mode, data as-of time, model/prompt identity or fixture ID, and a reason taxonomy.

**Warning signs:**
- `screened_count != success_count + failure_count + skipped_count`.
- A HOLD has nonzero `filled_qty`, or a row's ticker differs from reconciliation ticker.
- Runs have headers but no explicit terminal state.
- Error notifications exist with no corresponding database outcome.

**Specific tests/checks:**
- Crash after ticker N: run is `ABORTED`/incomplete and excluded from clean-run metrics.
- First ticker partially fills; second HOLDs: second row must have null order/fill fields.
- Data-source and LLM exceptions each produce a persisted failure outcome with redacted diagnostics.
- Database invariant query fails CI if terminal run counts do not reconcile exactly.

**Phase to address:** Phase 1, before replay or soak data is accepted.

---

### Pitfall 3: Treating same-bar historical replay as point-in-time evidence (MEDIUM)

**What goes wrong:**
Replay uses a day's closing OHLCV to screen and signal, then assumes execution at that same close. Results embed information unavailable at decision time. A current ticker universe can also omit delisted or formerly ineligible names, creating survivorship and universe leakage.

**Why it happens:**
Daily DataFrames make all columns look simultaneously available, while reference date and actual availability time are different concepts. Reusing today's screener against historical dates does not itself guarantee point-in-time membership or point-in-time source behavior.

**How to avoid:**
- Define one explicit decision epoch (for example, after D close) and an execution convention (for example, D+1 open/next available quote). Do not infer it inside adapters.
- Attach `event_time`, `available_at`, source, adjusted/unadjusted policy, and fixture version to every replay input.
- Build each date's universe from information available on that date; include delisted/suspended histories or label the replay scope as incapable of measuring survivorship effects.
- Freeze raw inputs before replay. Network calls, current news, current ticker metadata, and wall-clock “today” are forbidden.
- Add conservative fill assumptions and report gate behavior separately from P&L. Backtest-lite is primarily a policy-path validator.

**Warning signs:**
- Signal timestamp and fill timestamp are identical despite close-derived indicators.
- Replaying the same fixture later changes results without a code/config version change.
- Every historical ticker is still listed today.
- A future-bar edit changes an earlier decision.

**Specific tests/checks:**
- **Future mutation test:** alter all bars after epoch T; decisions through T must be byte-identical.
- **Boundary test:** a signal based on D close cannot execute before D+1's first allowed price.
- **Clock/network test:** replay fails if code reads wall-clock time or opens HTTP/KIS/LLM connections.
- **Universe test:** membership snapshots differ across dates and exclusions carry explicit reasons.

**Phase to address:** Phase 2.

---

### Pitfall 4: Fixture overfitting that proves only the happy BUY path (HIGH)

**What goes wrong:**
A fixed `BUY, 0.95` fixture drives every replay. The implementation is tuned until that fixture passes, while HOLD, SELL, malformed signals, threshold boundaries, risk overrides, stale inputs, and no-position cases remain untested. Reported “trade rate” is then mostly a property of the fixture.

**Why it happens:**
The current CLI tests center on a provider returning a qualified 0.95 BUY. A single fixture is deterministic and cheap, but cannot represent a policy surface or validate the LLM.

**How to avoid:**
- State the limited claim precisely: fixture replay validates screener/execution/risk/audit plumbing, not model quality or profitability.
- Use a versioned scenario matrix generated independently of the historical outcomes.
- Include values immediately below, at, and above every threshold; malformed strict JSON; BUY/SELL/HOLD; held/unheld; zero sizing; risk override; daily-loss block; stale data; and provider failure.
- Keep golden expectations for invariants, not for a preferred number of trades. Add mutation testing so changing `>=` to `>` or bypassing risk precedence fails.

**Warning signs:**
- All replay decisions have the same action/confidence/reason.
- Acceptance is “produced N BUYs” instead of branch and invariant coverage.
- Changing the fixture changes the risk recommendation more than changing market data.

**Specific tests/checks:**
- Table-driven thresholds at `0.799`, `0.800`, and `0.801` for the default 0.8 gate.
- SELL without a position stays HOLD; risk SELL overrides a high-confidence BUY.
- Invalid JSON and extra/typed-wrong fields produce HOLD and zero broker calls.
- Mutation test kills removed freshness, risk-precedence, dry-run, and confidence comparisons.

**Phase to address:** Phase 2.

---

### Pitfall 5: Duplicate prevention that both suppresses legitimate orders and misses real duplicates (HIGH)

**What goes wrong:**
After an ambiguous timeout the bot posts twice, or it incorrectly suppresses a later legitimate order because an earlier order had the same ticker/side/quantity. Day boundaries, partial fills, cancellation/replacement, pagination, price changes, and restart state make either failure possible.

**Why it happens:**
KIS does not provide a client idempotency key in this project. Current reconciliation matches same-day rows by ticker, side, and quantity; price, session, local intent identity, order state, and complete pagination are not part of the match. If broker side is missing, the code accepts the row. The current local client reference is not persisted or sent to KIS.

**How to avoid:**
- Persist a unique local order intent **before** POST with policy version, run/ticker, side, quantity, snapped limit price, session date, and state.
- Keep POST single-shot. A timeout/connection loss after sending becomes `UNKNOWN`, never `FAILED_SAFE_TO_RETRY`.
- Reconcile UNKNOWN intents against complete broker truth, including paginated order/fill results and order state. Do not auto-resubmit while ambiguity remains.
- Distinguish duplicate suppression from successful submission in result/audit models; a found order must refresh reconciliation rather than leave old state.
- Require operator resolution or a proven not-found observation window before any resend.

**Warning signs:**
- Two same-shape fills seconds apart.
- Duplicate suppression returns an order ID but has no matching immutable reconciliation record.
- Query results are truncated or pagination fields are ignored.
- A second intentional order at a different price is silently suppressed.

**Specific tests/checks:**
- Fault injection: server accepts POST, client loses response; restart and retry must issue zero second POSTs.
- Query unavailable before POST: fail closed with zero POSTs.
- Existing order with same quantity but different side/price/session must not be treated as the same intent.
- Partial fill plus rerun reconciles remaining quantity without submitting the original full order again.
- Duplicate query spans multiple pages; match appears only on a later page.

**Phase to address:** Intent state/schema in Phase 1; exhaustive KIS mock verification in Phase 3.

---

### Pitfall 6: Stale data checks that exist in name but are not connected to order preflight (HIGH)

**What goes wrong:**
The soak “tests stale data” at a data adapter but an order still reaches the broker, or a replay compares dates while ignoring intraday quote age. A false-positive freshness check creates an unjustified order.

**Why it happens:**
`KISBroker` defaults `data_fresh` to a function that always returns `True`, and `build_kis_broker()` does not inject a freshness predicate. Freshness exists in the data pipeline, but the order adapter has no immutable evidence tying the order to the exact validated context. Calendar date alone does not establish quote freshness.

**How to avoid:**
- Carry a validated `DataFreshnessEvidence`/as-of record into the execution result and broker preflight; never use an always-true production default.
- Separate daily-bar freshness, live-quote age, expected KRX session date, and market-calendar status.
- Check freshness immediately before POST, not only before LLM generation; an expired context must force HOLD/abort.
- Record the measured age and accepted cutoff in the audit row.

**Warning signs:**
- Production KIS broker is constructed without a freshness dependency.
- Reports say only `fresh=true` and omit source timestamps/cutoffs.
- Long LLM/API delays do not trigger revalidation.

**Specific tests/checks:**
- Advance an injectable clock between context creation and order submission; zero POST after cutoff.
- Weekend/holiday, pre-open prior-close, delayed OHLCV, and stale live quote each have explicit expected outcomes.
- Broker construction fails closed if no production freshness policy is supplied.

**Phase to address:** Phase 1, exercised again in Phase 3.

---

### Pitfall 7: Risk controls are “calibrated” while their runtime state is fictitious (HIGH)

**What goes wrong:**
Threshold analysis recommends looser BUY criteria while the actual daily-loss breaker, available cash, holdings, or fills were never represented correctly. A policy appears safe in replay/soak but is evaluated under impossible account state.

**Why it happens:**
The current CLI creates `DailyLossState(realized_loss=0.0, ...)` separately for every ticker. For a non-local broker, `_available_cash()` fabricates a value from configuration when no `cash` property exists. KIS positions are only local `tracked_positions`, not automatically hydrated from broker balance. These shortcuts are incompatible with portfolio/day-level calibration.

**How to avoid:**
- Hydrate cash, positions, realized P&L, open orders, and session loss from broker/audit truth once per run; update the shared state after each fill.
- Pass one cumulative daily-loss state through all tickers and across restarts for the KST trading day.
- Separate “policy simulation capital” from “broker available cash,” label it in replay, and never substitute one for the other in soak/live.
- Block policy calibration until state-reconciliation invariants pass.

**Warning signs:**
- Daily realized loss is always zero in audit evidence.
- Every ticker sees the same synthetic available cash after earlier fills.
- KIS account holdings differ from execution-core positions.

**Specific tests/checks:**
- First ticker crosses daily-loss threshold; later BUYs are blocked while risk SELLs remain allowed.
- Restart mid-day reconstructs the same kill-switch state.
- Partial fill updates cash/position before the next ticker's sizing.
- Broker/account snapshot and report totals reconcile within explicit tolerances.

**Phase to address:** Phase 1; broker-truth soak proof in Phase 3.

---

### Pitfall 8: Treating LLM self-reported confidence as a calibrated probability (MEDIUM)

**What goes wrong:**
The team interprets `confidence=0.8` as an 80% chance of success, lowers the threshold after a small favorable sample, or tunes stop-loss/take-profit and confidence on the same replay used to report improvement. The resulting policy is overfit and less safe.

**Why it happens:**
The JSON field is schema-valid but has no inherent probabilistic semantics. Outcomes are delayed, regime-dependent, selected by the screener, and censored by HOLD/no-fill decisions. Small soak samples make confidence bins unstable. Current audit rows do not define a labeled prediction horizon or realized outcome.

**How to avoid:**
- Call it a model score until empirical calibration is demonstrated.
- Predefine outcome labels and horizons (for example, executable return after costs over N sessions), treatment of no-fill/cancelled orders, and which decisions enter each analysis.
- Freeze a development window, tune on it, and evaluate once on a later untouched time window. Never random-split time series.
- Show sample counts and uncertainty per confidence bin; use reliability curves alongside action rate, drawdown, turnover, rejection/no-fill rate, and worst-case outcomes.
- Change one policy family at a time and run recommendations in **shadow mode** first. Require explicit human approval and preserve the real-money confirmation gate.

**Warning signs:**
- Report says “80% confidence means 80% win rate” without calibration evidence.
- The same days select and validate the new threshold.
- A recommendation is based on a handful of trades or omits HOLD/no-fill decisions.
- Calibration automatically rewrites `.env` or production settings.

**Specific tests/checks:**
- Analysis refuses datasets lacking policy version, outcome horizon, or minimum sample counts.
- Time-ordered holdout is immutable and later than the tuning window.
- Every recommendation includes old/new policy, expected effect, uncertainty, evidence window, and rollback trigger.
- Policy application remains a separate, deliberate action; real mode still requires all existing gates.

**Phase to address:** Phase 5 only, after Phases 1–4 produce trustworthy evidence.

## Moderate Pitfalls

### Pitfall 9: Reports that look complete but hide denominator and timezone errors (HIGH)

**What goes wrong:**
Daily summaries omit failed candidates, group UTC timestamps into the wrong Korean trading day, count duplicate suppression as a fill, or compare runs generated under different policies as if homogeneous.

**Prevention:**
- Persist `trading_date_kst` explicitly; do not derive it with `substr(created_at)` on UTC text.
- Define report denominators and a mutually exclusive outcome taxonomy.
- Include incomplete runs, errors, stale-data skips, duplicate-suppressed orders, UNKNOWN submissions, partial fills, and notification failures.
- Partition/annotate by policy, prompt/model or fixture, code/schema version, backend, KIS environment, and dry-run state.
- Reconcile totals mechanically from run headers to ticker outcomes to broker order IDs.

**Phase to address:** Schema in Phase 1; presentation and reconciliation in Phase 4.

### Pitfall 10: Multi-query reports do not use one SQLite snapshot (MEDIUM)

**What goes wrong:**
Header totals and detail rows disagree because writes commit between report queries. Copying only `audit.db` while WAL is active can omit committed data.

**Prevention:**
- Generate each report on a separate connection inside one explicit read transaction so all queries share one WAL snapshot.
- Keep report transactions bounded; close promptly to avoid checkpoint starvation.
- Use SQLite backup APIs or a quiesced/checkpointed copy. Never treat the main `.db` file alone as a complete WAL-mode backup.
- Add busy timeout and report a clear “snapshot unavailable” error rather than silently returning partial output.

**Phase to address:** Phase 4.

### Pitfall 11: Soak duration substitutes for adversarial coverage (MEDIUM)

**What goes wrong:**
The bot runs for N quiet days and passes without ever encountering a timeout, rate limit, malformed response, restart, duplicate, stale quote, partial fill, or market closure.

**Prevention:**
- Define a coverage matrix in addition to N trading days: auth refresh, KIS `EGW00201`, query timeout, POST ambiguous timeout, malformed JSON, stale data, market closed, duplicate, partial/no fill, process crash, notification failure, and database busy/disk error.
- Inject failures at exact boundaries and retain evidence linking each drill to expected fail-safe behavior.
- Track consecutive clean sessions separately from completed fault drills.

**Phase to address:** Phase 3.

### Pitfall 12: The runbook documents commands but not decisions and abort conditions (MEDIUM)

**What goes wrong:**
The operator can copy commands but cannot tell whether the market date is valid, whether the bot is using local vs KIS mock, whether an UNKNOWN order exists, or whether it is safe to rerun. Stale instructions become more dangerous than no instructions.

**Prevention:**
- For `bot screen`, `bot run`, and `bot status`, document preconditions, expected banner/output, evidence location, explicit abort criteria, diagnosis, safe mitigation, broker-truth verification, and post-run checks.
- Make “do not rerun after ambiguous order submission until reconciled” prominent.
- Include KST session/holiday handling and mock API throttling guidance.
- Version the runbook with CLI/config schema and execute drills from a clean shell; broken steps fail milestone verification.

**Phase to address:** Skeleton in Phase 1; drills and finalization in Phase 4.

### Pitfall 13: Mock fills are reported as evidence of live execution quality (MEDIUM)

**What goes wrong:**
Promotion claims use mock fill rate, slippage, or P&L as if it predicts real queue position and market impact.

**Prevention:**
- State that paper/mock validates software behavior, broker integration, and operational controls—not live execution economics.
- Keep fill-model assumptions and broker environment visible in every report.
- Treat unrealistic immediate/full fills as simulator behavior; promotion requires conservative limits and a separately approved minimal-capital live observation stage if the owner later chooses one.

**Phase to address:** Phase 3 reports limitation; Phase 5 promotion checklist enforces it.

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Reuse `MockBroker` as “KIS mock” | No credentials/network | Zero evidence for KIS integration | Unit tests and deterministic replay only |
| One fixture signal | Cheap deterministic replay | Fixture overfitting; false branch coverage | Only as one case in a scenario matrix |
| Add report SQL without schema versioning | Fast first report | Old/new rows become semantically incomparable | Never for calibration evidence |
| Infer failure from missing rows | No failure schema | Clean-looking incomplete reports | Never |
| Keep mutable `last_reconciliation` on broker | Easy CLI access | Cross-ticker fill attribution | Never in persisted evidence |
| Tune all risk knobs together | Finds an attractive historical result | Multiple-testing overfit; no causal attribution | Never for promotion |
| Auto-apply recommendations | Convenient | Unsafe policy drift without review | Never |
| Copy only `audit.db` in WAL mode | Simple backup | Missing committed WAL transactions | Never while WAL may be active |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| KIS mock | Assume mock and real have identical operational behavior | Exercise mock limits and error codes, but label simulator limitations and retain real gate |
| KIS order inquiry | Query only first result page or match by ticker/qty | Exhaust pagination; match durable intent attributes and broker state |
| KIS order POST | Retry on timeout | Mark UNKNOWN, query broker truth, never blind-resubmit |
| pykrx replay | Fetch “historical” data live during replay | Freeze dated inputs with availability metadata and hashes |
| Execution core | Reimplement thresholds in replay/report code | Import the same pure execution/risk policy used by production |
| SQLite | Run totals/details as unrelated autocommit queries | One explicit read transaction on a separate connection |
| CLI/runbook | Use `mock` to imply dry-run, local broker, and KIS VTS at once | Display and audit each axis independently |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Burst mock API calls | `EGW00201`, missing candidates, long retries | Shared rate limiter, bounded backoff, checkpoint/resume | Full-universe or repeated fault/soak runs |
| Row-by-row report queries | Slow daily report; long WAL reader | Set-based SQL, indexes on trading date/status/order ID | Weeks of per-ticker decisions |
| Long report transaction | WAL growth, checkpoint starvation | Snapshot quickly; render after rows are materialized | Report kept open while soak writes continue |
| Recompute replay features per policy sweep | Slow tuning encourages tiny samples | Cache immutable feature snapshots; vary pure policy only | Many dates × thresholds × tickers |

## Security and Safety Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Reports/runbooks expose account IDs, credentials, raw provider errors, or prompts | Credential/privacy leak | Allowlisted fields, account suffix only, centralized redaction |
| Replay fixture/news text treated as trusted instructions | Prompt/data poisoning | Untrusted-data boundary, frozen/sanitized inputs, no live LLM in backtest-lite |
| “Calibration” modifies production settings | Silent safety weakening | Signed/versioned recommendation artifact plus explicit human application |
| Promotion checklist becomes a boolean flag | Gate bypass without evidence | Evidence-linked checklist with immutable run/report IDs and unresolved-order check |

## UX Pitfalls

| Pitfall | Operator Impact | Better Approach |
|---------|-----------------|-----------------|
| Ambiguous word “mock” | Operator cannot tell local simulation from KIS VTS | Banner columns: backend, environment, account suffix, dry-run/execute |
| Green summary despite ticker failures | False confidence | `COMPLETED_WITH_ERRORS`, visible denominator, nonzero exit code where appropriate |
| Raw exception text as no-trade reason | Triage is slow and may leak data | Stable reason codes plus redacted detail/correlation ID |
| Report mixes replay, local mock, KIS mock, and real | Invalid comparisons | Separate sections/filters and prominent provenance |
| Runbook says “retry” after timeout | Duplicate-order risk | State-specific recovery flow beginning with broker inquiry |

## “Looks Done But Isn't” Checklist

- [ ] **KIS soak:** Orders and inquiries reached the KIS mock account; local `MockBroker` runs are not counted.
- [ ] **Run completeness:** Every screened/attempted ticker has one terminal outcome and every run has a terminal status.
- [ ] **Stale data:** Freshness is rechecked at broker preflight with an injected clock and zero POST on expiry.
- [ ] **Duplicate safety:** Accepted-then-timeout plus restart produces no second POST.
- [ ] **Replay:** Future-data mutation cannot alter earlier signals; no network/wall-clock access occurs.
- [ ] **Fixture breadth:** Boundary, HOLD, SELL, malformed, risk override, stale, error, and zero-size branches are covered.
- [ ] **Reports:** Totals equal details from one SQLite snapshot and group by explicit KST trading date.
- [ ] **Reconciliation:** No HOLD/error row can inherit another ticker's fill data.
- [ ] **Calibration:** Development and evaluation windows are time-ordered and disjoint; sample counts/uncertainty are shown.
- [ ] **Policy safety:** Recommendations are shadow-only until explicit approval; current real-money confirmation remains enforced.
- [ ] **Promotion:** No incomplete run, UNKNOWN order intent, unreconciled broker position, or unresolved critical drill remains.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Soak used local broker | MEDIUM | Relabel evidence as local; configure KIS mock backend; restart acceptance window |
| Audit provenance is incomplete/corrupt | HIGH | Quarantine affected data; migrate schema; rerun replay/soak from a clean evidence boundary |
| Ambiguous order timeout | MEDIUM | Freeze new orders; persist UNKNOWN; query complete broker truth; reconcile manually before resuming |
| Duplicate order actually filled | HIGH | Stop trading; reconcile cash/positions/orders; record incident; risk-manage through approved manual procedure, never an automatic compensating trade |
| Look-ahead found | HIGH | Invalidate affected replay results; fix availability model; rerun all dependent calibration |
| Misleading report published | MEDIUM | Withdraw it; fix snapshot/denominator/provenance; regenerate with correction note |
| Unsafe policy recommendation | MEDIUM | Keep old policy active; discard contaminated window; pre-register new analysis and use a later holdout |
| Runbook drill fails | LOW | Keep phase unverified; update command/diagnosis/recovery steps; repeat drill from clean state |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Local mock mistaken for KIS mock | Phase 1 / Phase 3 | Composition test plus broker-visible mock order/inquiry |
| Incomplete/misattributed audits | Phase 1 | Count invariants, crash test, cross-ticker reconciliation test |
| Stale data reaches POST | Phase 1 / Phase 3 | Injected-clock stale test with zero POST |
| Fictitious daily risk/account state | Phase 1 / Phase 3 | Cross-ticker/restart kill-switch and broker reconciliation |
| Look-ahead/survivorship leakage | Phase 2 | Future mutation, no-network, dated-universe checks |
| Fixture overfitting | Phase 2 | Scenario/mutation coverage across all policy branches |
| Duplicate/ambiguous orders | Phase 1 / Phase 3 | Accepted-then-timeout/restart and pagination drills |
| Quiet-days-only soak | Phase 3 | N sessions plus completed fault-coverage matrix |
| Misleading/inconsistent reports | Phase 4 | One-snapshot reconciliation and timezone golden tests |
| Stale runbook | Phase 4 | Clean-shell drills for normal, abort, and ambiguous-order paths |
| Uncalibrated confidence/overfit policy | Phase 5 | Later untouched window, bin counts/uncertainty, shadow recommendation |
| Mock fills treated as live proof | Phase 5 | Promotion checklist explicitly limits claims and preserves real gate |

## Promotion Must Remain Blocked If

- Any order intent remains `UNKNOWN`, any broker/local position differs, or any duplicate-order drill fails.
- Stale data can reach `place_order_cash`, or freshness evidence is missing from an executed decision.
- A report cannot reconcile run totals, ticker outcomes, broker IDs, and partial fills exactly.
- The KIS mock soak did not use the KIS mock backend across the required trading sessions and fault matrix.
- Risk recommendations were selected and evaluated on the same time window, lack outcome definitions, or auto-apply.
- The runbook has not been executed successfully for startup validation, API failure, ambiguous POST, stale data, and safe shutdown.

## Sources

- Current project code and tests: `trading_bot/cli.py`, `sqlite_audit.py`, `execution.py`, `kis_broker.py`, `kis_order.py`, `config.py`, `tests/test_kis_broker.py`, and `tests/test_cli.py` — HIGH.
- [Korea Investment & Securities Open API official sample repository](https://github.com/koreainvestment/open-trading-api) — mock/real separation and lower mock REST limits (`EGW00201`) — MEDIUM after verified web retrieval.
- [Alpaca paper-trading documentation](https://docs.alpaca.markets/us/v1.4.2/docs/paper-trading) — simulator omissions including market impact, latency slippage, queue position, and liquidity assumptions — MEDIUM after cross-check.
- [Interactive Brokers paper-account limitations](https://www.interactivebrokers.com/campus/glossary-terms/paper-trading-account/) — simulated top-of-book fills and behavior differences — MEDIUM after cross-check.
- [CFA Institute Research Foundation, Investment Model Validation](https://rpc.cfainstitute.org/sites/default/files/-/media/documents/article/rf-brief/investment-model-validation.pdf) — point-in-time universe, survivorship, look-ahead, and time-ordered out-of-sample validation — MEDIUM after verified web retrieval.
- [scikit-learn probability-calibration guide](https://scikit-learn.org/stable/modules/calibration.html) — independent calibration data, reliability interpretation, and limits of aggregate probability scores — MEDIUM via official docs fallback.
- [SQLite isolation documentation](https://www.sqlite.org/isolation.html) and [WAL documentation](https://www.sqlite.org/wal.html) — snapshot isolation, reader/writer behavior, checkpoint starvation, and WAL backup hazards — MEDIUM via official docs fallback.
- [Google SRE incident-management guide](https://sre.google/resources/practices-and-processes/incident-management-guide/) — actionable detection, current playbooks, drills, response, and learning — MEDIUM after verified web retrieval.

---
*Pitfalls research for: Stock Trading Bot v1.1 Mock Soak & Replay Validation*
*Researched: 2026-07-11*
