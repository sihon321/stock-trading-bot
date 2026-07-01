# Phase 3: Data Pipeline - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md - this log preserves the alternatives considered.

**Date:** 2026-07-01
**Phase:** 3-Data Pipeline
**Areas discussed:** Safety path, Data shape, Screener policy, Adapter boundaries, Screener detail

---

## Safety Path

| Option | Description | Selected |
|--------|-------------|----------|
| Fail closed per ticker | Mark ticker unusable and force HOLD/no action. | |
| Skip ticker, continue cycle | Drop ticker from candidate set and continue. | |
| Use last valid trading day | Allow prior-session OHLCV for natural closures. | |
| Other | Hybrid behavior by ticker state. | yes |

**User's choice:** Hybrid policy: skip bad new screener candidates, freeze/HOLD existing holdings and log an alert, and use last valid trading day for holidays/weekends.
**Notes:** This avoids entering new positions on bad data while still making existing-holding monitoring explicitly safe.

| Option | Description | Selected |
|--------|-------------|----------|
| Shared cached token, fail soft on throttle | One token manager; fail soft on throttle/token failure. | |
| Shared cached token, bounded retry | One token manager with small retry/backoff before fail-soft. | yes |
| Strict no-retry | Surface unavailable immediately. | |

**User's choice:** Shared cached token with bounded retry/backoff.
**Notes:** Aggressive retry is not desired; unavailable price should fall into safety policy after bounded attempts.

| Option | Description | Selected |
|--------|-------------|----------|
| Structured audit event only | Record ticker/source/reason/date/action. | |
| Audit event plus console warning | Record structured event and print warning. | yes |
| Minimal reason string | Attach only a simple reason. | |

**User's choice:** Structured audit event plus console warning.
**Notes:** Phase 5 notifications remain out of scope.

---

## Data Shape

| Option | Description | Selected |
|--------|-------------|----------|
| Keep compact, add metadata | Keep compact fields and add source metadata separately. | |
| Richer typed context | Add OHLCV, indicator objects, typed news, and source health to DataContext. | |
| Adapter result plus compact context | Keep rich internal adapter data but compact DataContext. | yes |

**User's choice:** Adapter result plus compact context.
**Notes:** The LLM boundary should remain token-efficient.

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal trend/momentum | Moving averages plus RSI. | |
| Trend/momentum/volume | Moving averages, RSI, volume ratio, and momentum. | |
| Broader technical pack | Add MACD, Bollinger Bands, volatility, and more. | |
| Other | Tailored volatility-breakout baseline. | yes |

**User's choice:** Moving averages, RSI, volatility metrics such as ATR or historical volatility, and volume ratios. Skip MACD and Bollinger Bands for now.
**Notes:** The user wants exactly the metrics needed for volatility breakout strategies without bloating `DataContext`.

| Option | Description | Selected |
|--------|-------------|----------|
| Short sanitized snippets | Capped title/date/source snippets as strings. | |
| Headline-only | Sanitized titles only. | |
| Structured internally, rendered compactly | Typed adapter news, compact sanitized strings in DataContext. | yes |

**User's choice:** Structured internally, rendered compactly.
**Notes:** News remains untrusted data and must be sanitized before it reaches prompt-facing context.

---

## Screener Policy

| Option | Description | Selected |
|--------|-------------|----------|
| Liquidity plus momentum | Filter liquid names, rank by price/volume momentum. | |
| Volatility breakout readiness | Liquid names with ATR/historical volatility and volume expansion. | yes |
| Large-cap safety first | Prefer large liquid names; momentum secondary. | |

**User's choice:** Volatility breakout readiness.
**Notes:** The screener should align with the intended volatility-breakout execution direction.

| Option | Description | Selected |
|--------|-------------|----------|
| Small shortlist | Top 5 to 10 tickers. | |
| Medium shortlist | Top 20 to 30 tickers. | |
| Configurable cap | Default small but expose `screener_max_candidates`. | yes |

**User's choice:** Configurable cap.
**Notes:** The user corrected an earlier answer and selected configurable cap.

| Option | Description | Selected |
|--------|-------------|----------|
| KOSPI only | Simpler, generally more liquid. | |
| KOSPI + KOSDAQ | Broader universe with liquidity floor. | |
| Configurable markets | Default KOSPI + KOSDAQ, allow restrictions later. | yes |

**User's choice:** Configurable markets.
**Notes:** The user corrected an earlier answer and selected configurable markets.

---

## Adapter Boundaries

| Option | Description | Selected |
|--------|-------------|----------|
| Source adapters plus orchestrator | Separate pykrx/KIS/Naver modules and one orchestrator. | |
| One combined data adapter | One concrete adapter owns everything. | |
| Adapters plus pure transforms | Source adapters, pure transforms, thin DataSource orchestrator. | yes |

**User's choice:** Adapters plus pure transforms.
**Notes:** This preserves testability and keeps source failure modes isolated.

| Option | Description | Selected |
|--------|-------------|----------|
| Shared KIS infrastructure | Reusable token manager for price now and broker later. | yes |
| Price-only for now | Keep narrow and refactor in Phase 5. | |
| Interface first, implementation narrow | Define shape now, wire only price use. | |

**User's choice:** Shared KIS infrastructure.
**Notes:** This matches the roadmap requirement for a shared token manager.

| Option | Description | Selected |
|--------|-------------|----------|
| At adapter boundary | Adapters normalize source-specific failures. | yes |
| In the DataSource orchestrator | Centralize failure normalization in orchestrator. | |
| Mixed | Adapters normalize obvious failures, orchestrator handles policy. | |

**User's choice:** At adapter boundary.
**Notes:** The orchestrator should receive typed unavailable/stale/source-health results.

---

## Screener Detail

| Option | Description | Selected |
|--------|-------------|----------|
| Volume expansion first | Volume ratio primary; volatility/momentum break ties. | |
| Volatility plus liquidity first | Volatility and liquidity primary; volume/momentum rank within. | yes |
| Balanced score | Configurable weighted combination. | |

**User's choice:** Volatility plus liquidity first.
**Notes:** ATR/historical volatility and liquidity floor are primary.

| Option | Description | Selected |
|--------|-------------|----------|
| Hard exclude | Exclude low-liquidity, suspended, halted, or bad-data tickers. | |
| Score penalty | Keep but penalize ranking. | |
| Configurable exclusion | Hard exclude by default with configurable floors/states. | yes |

**User's choice:** Configurable exclusion.
**Notes:** Hard exclude by default, configurable for liquidity floors and ticker states.

| Option | Description | Selected |
|--------|-------------|----------|
| Policy only | Lock inputs and constraints; planner chooses thresholds/weights. | yes |
| Configurable weights now | Require explicit config weights in Phase 3. | |
| Fixed formula now | Define deterministic weighted score before planning. | |

**User's choice:** Policy only.
**Notes:** Exact thresholds and formulas should follow pykrx/KRX research.

## the agent's Discretion

- Exact module, class, dataclass, and enum names.
- Exact KIS bounded retry count and refresh-margin defaults.
- Exact indicator implementation details and screener thresholds after research.
- Exact shape of typed adapter health/result objects.

## Deferred Ideas

None.
