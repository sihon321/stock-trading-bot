# Phase 12 Research

Researched: 2026-10-01. Scope: FUT-01. Method: inline code inspection and primary-source review; no delegated agents. All defaults are authorized by 12-CONTEXT.md.

## Implementation recommendation

Build a separate credential-free chronological simulator. Existing replay resets MockBroker per scenario and cannot provide portfolio continuity. Keep shipped replay and MockBroker contracts. Reuse calculate_technicals, screen_candidates, evaluate_signal_action/build_order_intent and evaluate_position_risk/blocks_new_buy through narrow adapters; do not instantiate live runtime, exit coordinator or KIS broker. Production Money.amount is float: use Decimal internally for simulation money, strict decimal-string persistence and a checked finite float bridge only to existing pure functions. Reconcile money exclusively in Decimal; bridge precision and rounding have explicit tests.

Bundle v1 is one bounded JSON document containing schema/version, calendar, raw OHLCV, membership/status, corporate actions, frozen signals, policy, reviewed cost/tick records, optional benchmark and source metadata. Require availability/effective timestamps. Split decision-visible and execution-only views: next-session open/volume can model fills but must never enter screening or risk at prior close. No downloader, live LLM or external API is required.

Daily bars cannot establish queue position or intraday order of prices. Conservative opening-only limit fills, aggregate participation caps and explicit no-fill reasons expose this limitation. Suspensions, missing observations and unresolved delistings keep holdings and unknown valuation; complete results require requested coverage, warm-up, required actions and ledger reconciliation. Synthetic fixtures test behavior; they do not establish actual three-year historical performance.

## Primary market-rule sources and uncertainty

- KRX settlement rules: https://regulation.krx.co.kr/contents/RGL/03/03010100/RGL03010100T1.jsp — official stock settlement description identifies T+2. Conservative sell-proceeds availability is a model policy, not proof of the owner's account buying power. Count frozen exchange sessions, not calendar days.
- KRX KOSDAQ auction rules: https://regulation.krx.co.kr/contents/RGL/03/03020205/RGL03020205.jsp — price/time priority supports explicitly declining to infer queue execution from daily OHLCV.
- Korea Investment channel fee guidance: https://advisor.koreainvestment.com/main/customer/guide/_static/TF04ae010000.jsp?tab=3 — account/channel fee differences mean baseline 1.5bps and stress 3bps are assumptions, not verified account fees.
- Securities Transaction Tax Act Enforcement Decree: https://www.law.go.kr/법령/증권거래세법시행령 — authoritative basis for effective tax rules. Browser extraction did not establish a complete historical rate table. Do not hardcode unverified rates. Require reviewed input records per market/date, with separate transaction-tax and surtax components and source/review metadata. Synthetic test rates must be marked synthetic and must not pass as reviewed real-market coverage.

Tick rules also require dated reviewed records covering every simulated order. No current tick table is assumed to apply to the whole requested history. Missing/overlapping rules are input errors. External history/rate curation is an evidence prerequisite; implementing an offline loader does not prove such data already exists.

## Architecture and contracts

1. backtest_models/backtest_inputs: strict versioned types, normalized hashes, three-calendar-year window, coverage, guarded views.
2. backtest_costs/backtest_fills: date-effective commission/tax/tick lookup, Decimal cost attribution and aggregate deterministic opening fills.
3. backtest_ledger: one account; cash reservation, pending T+2 proceeds, sell reservation, partial fills, expiry and corporate actions.
4. backtest_engine: chronological held-first shared gates, stable IDs, next-session intent timing, unknown evidence handling.
5. backtest_reporting: reconciled gross/net curves, drawdown/exposure/turnover, strict saved evidence and Korean reporting.
6. backtest_cli + existing cli/report_cli registration: isolated offline commands, safe output and failure handling.

## Pitfalls to prevent

Look-ahead through revised membership, action adjustments or signal timestamps; floating monetary drift; random UUIDs in result identity; independent liquidity caps per order; immediate sale-proceeds reuse; full-book mark-to-zero on missing price; adjusting execution prices retrospectively; treating missing fixture signals as permission to bypass existing parser/risk precedence; trusting saved hashes without revalidation; hashing output paths or wall clock; changing live/replay contracts to fit simulation.

## Validation Architecture

Existing pytest infrastructure and .venv Python need no new framework. Every task creates its own meaningful tests in the same commit, with shared fixtures introduced in 12-01. Cover controlled prefix invariance, cost/tick boundary dates, oversell/cash reservation, T+2 across holidays, corporate actions, risk parity, aggregate partial capacity, output tamper detection and offline capability tripwires. Compare shuffled equivalent inputs and distinct output locations. Fixtures include complete explicit short windows, deliberately incomplete default-three-year requests and synthetic-rule limitations. No credentials or real order submission.

Quick feedback is each task's focused pytest command; run accumulated backtest tests per wave and the full suite at final integration. Existing baseline is 828 passing tests from the previous implementation turn; this planning turn does not rerun or claim new implementation tests. See 12-VALIDATION.md for pending task mapping.

## Cross-plan data contracts

Canonical bundle top-level fields: schema_version, calendar, bars, membership, trading_status, corporate_actions, signals, policy, cost_rules, tick_rules, benchmark, sources. Policy includes initial_cash (Decimal string, default modeling amount 10000000 KRW), initial_positions (default empty; supplied quantity/average cost with known timestamp), requested-universe mode and shipped strategy/risk parameters. Initial conditions are identity inputs, not inferred from live accounts.

Backtest models own shared immutable records before consumers are built. OpenIntent fields: intent_id, ticker, side, quantity, remaining_quantity, limit_price, decision_session, eligible_session, reserved_cash, reserved_quantity. FillEvidence fields: intent_id, session, quantity, reference_price, executed_price, commission, sell_tax, surtax, slippage_drag, reason, rule_ids. SessionEvidence fields: session, settled_cash, reserved_cash, pending_cash, holdings, net_equity, gross_equity, coverage_status, unknowns. Monetary fields use Decimal internally/strings on disk; equity is nullable only with explicit unknown reason. Ledger owns operational state and returns these records; engine returns BacktestRun containing manifest plus ordered records; reporting wraps and validates those same records without rerunning decisions.

Cost/tick effective records include market, effective_start/end (half-open), known_at, source, reviewed_at, synthetic and rule_id. Tick records additionally cover price bands without gaps/overlap and expose valid grid rounding across bands. Availability cutoff applies to these records as to market data. Baseline/stress override synthetic commission/slippage/participation assumptions only; tax/tick lookup remains independently sourced and dated.

Missing/malformed frozen signal is an attributable HOLD before risk evaluation, matching execute_signal_cycle parse-failure order. A valid HOLD or conflicting valid BUY can be overridden by the shipped held risk rule. Tests must distinguish these cases and must not imply parse-failure risk behavior was changed in production.
