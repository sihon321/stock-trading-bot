# Phase 4: LLM Agent - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-01
**Phase:** 4-LLM Agent
**Areas discussed:** Prompt & strategy framing, Schema & re-validation, Reproducibility & failures, Untrusted-news delimiting

---

## Prompt & Strategy Framing

| Option | Description | Selected |
|--------|-------------|----------|
| Breakout-aligned | LLM framed as a volatility-breakout analyst, consistent with Phase 3's screener | ✓ |
| Neutral analyst | Balanced technical read, no strategy bias | |
| Minimal | Bare-bones "here's the data, emit a signal" | |

**User's choice:** Breakout-aligned

| Option | Description | Selected |
|--------|-------------|----------|
| Calibrated + conservative | Confidence = probability call is right; reserve ≥0.8 for corroborated setups; default HOLD when unsure | ✓ |
| Calibrated only | Calibrated probability, no conservative-bias instruction | |
| No guidance | 0–1 confidence, no calibration framing | |

**User's choice:** Calibrated + conservative

| Option | Description | Selected |
|--------|-------------|----------|
| Versioned module constant | System prompt as a git-reviewed module constant + pure DataContext-render function | ✓ |
| External template file | Prompt in a runtime-loaded template file | |
| Config-overridable | Module default overridable via Settings/env | |

**User's choice:** Versioned module constant

| Option | Description | Selected |
|--------|-------------|----------|
| Brief cited rationale | 1–3 sentences citing specific signals (e.g. RSI/volume/breakout) | ✓ |
| Free-form short | Short justification, no structure | |
| You decide | Planning chooses phrasing guidance | |

**User's choice:** Brief cited rationale

**Notes:** The LLM is a proposer only; the deterministic rules layer still owns all trade math. Breakout framing keeps the proposal coherent with how candidates were screened; conservative calibration keeps the `confidence >= 0.8` BUY gate honest.

---

## Schema & Re-validation

| Option | Description | Selected |
|--------|-------------|----------|
| Always re-parse (double) | Serialize provider output and route through existing parse_signal regardless of provider | ✓ |
| Trust provider, validate lightly | Rely on provider structured output; parse_signal only on error | |

**User's choice:** Always re-parse (double)

| Option | Description | Selected |
|--------|-------------|----------|
| Pydantic mirror of LLMSignal | Pydantic TradeSignal as provider I/O schema only; canonical LLMSignal stays a frozen dataclass | ✓ |
| Hand-written JSON schema | Raw json_schema dict for both providers, no Pydantic model | |
| You decide | Planning picks the representation | |

**User's choice:** Pydantic mirror of LLMSignal

**Notes:** One audited fail-safe gate (parse_signal) owns the trade-or-HOLD decision; provider-native strict output is the first line only. The Pydantic mirror must stay in lockstep with LLMSignal (guard with a test).

---

## Reproducibility & Failures

| Option | Description | Selected |
|--------|-------------|----------|
| Settings, temp 0, opus/gpt pinned | Per-provider model ID + temperature in Settings; default claude-opus-4-8 / OpenAI equiv, temp 0.0 | ✓ |
| Module constants | Hardcoded model/temperature constants | |
| You decide | Planning chooses config surface + defaults | |

**User's choice:** Settings, temp 0, opus/gpt pinned

| Option | Description | Selected |
|--------|-------------|----------|
| structlog JSON line now | Log provider/model/temp/raw prompt/raw response/parsed outcome; defer SQLite audit to Phase 5 | ✓ |
| Return in a result object | Attach raw prompt/response to result; caller logs | |
| Lightweight file append | Append to a local JSONL file separate from Phase 5 DB | |

**User's choice:** structlog JSON line now

| Option | Description | Selected |
|--------|-------------|----------|
| Bounded retry then HOLD | tenacity bounded exponential backoff; still-failing → HOLD/no-trade | ✓ |
| No retry, immediate HOLD | Any error/unparseable output → HOLD, no retry | |
| You decide | Planning sets retry counts consistent with KIS defaults | |

**User's choice:** Bounded retry then HOLD

| Option | Description | Selected |
|--------|-------------|----------|
| Raise typed error → caller HOLDs | Provider raises typed LLM error; cycle maps to HOLD (mirrors SignalParseError) | ✓ |
| Return HOLD LLMSignal | Provider returns synthetic {HOLD, 0.0, reason} | |
| You decide | Planning chooses the fail-safe hand-off | |

**User's choice:** Raise typed error → caller HOLDs

**Notes:** Retry posture aligns with the Phase 3 KIS adapter. No manufactured signal the LLM never emitted — failures surface as typed errors caught at the cycle boundary.

---

## Untrusted-News Delimiting

| Option | Description | Selected |
|--------|-------------|----------|
| XML tags + explicit data-only rule | Wrap news in delimited tags; system rule says the block is untrusted data and any instructions inside must be ignored | ✓ |
| Delimiters only | Wrap in delimiters, rely on Phase 3 sanitization otherwise | |
| You decide | Planning chooses delimiter/framing | |

**User's choice:** XML tags + explicit data-only rule

| Option | Description | Selected |
|--------|-------------|----------|
| Trust Phase 3, delimit only | DataContext.news already sanitized; Phase 4 only delimits/frames it | ✓ |
| Defensive re-sanitize | Re-strip/escape news again at prompt-build time | |

**User's choice:** Trust Phase 3, delimit only

**Notes:** Belt-and-suspenders on top of Phase 3 sanitization (single sanitization owner).

---

## Claude's Discretion

- Exact module/symbol names (`prompts.py`, `TradeSignal`, provider class names, typed LLM error name).
- Provider factory/wiring shape resolving `Settings.llm_provider` (mirror `build_data_source`).
- Exact tenacity retry counts / backoff values (align with existing KIS defaults).
- Precise OpenAI default model ID, prompt token-budget handling, structlog field names, delimiter tag names.

## Deferred Ideas

None — discussion stayed within Phase 4 scope. Adjacent capabilities kept out: persistent SQLite audit store, manual CLI trigger, Telegram notifications (Phase 5 OPS-01/02/03); ensemble/consensus (ENSEMBLE-01); dedicated prompt-injection hardening beyond delimiting + Phase 3 sanitization (HARDEN-01); reproducibility replay tooling beyond the structlog line (HARDEN-02).
