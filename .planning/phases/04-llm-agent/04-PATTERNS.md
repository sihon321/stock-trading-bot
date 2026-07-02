# Phase 4: LLM Agent - Pattern Map

**Mapped:** 2026-07-02
**Files analyzed:** 8 (3 new modules, 2 modified, 3 new test files) + `pyproject.toml`
**Analogs found:** 8 / 8

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `trading_bot/llm_provider.py` (NEW) | adapter + factory | request-response | `trading_bot/data_source.py` (factory) + `trading_bot/kis_quote.py` (network adapter + retry) | role-match (two analogs) |
| `trading_bot/prompts.py` (NEW) | utility / pure transform | transform | `trading_bot/indicators.py` (pure `str->float` transform, no I/O) | role-match |
| `trading_bot/trade_signal.py` (NEW) | model (Pydantic I/O schema) | transform | `trading_bot/config.py` (`KisCredentialGroup` `BaseModel`) + `trading_bot/domain.py` (`LLMSignal` mirror source) | role-match |
| `trading_bot/config.py` (MODIFY) | config | — | itself — existing `Settings` fields + `kis_max_retries`/`kis_retry_backoff_seconds` block | exact (extend in place) |
| `pyproject.toml` (MODIFY) | config | — | existing pinned deps (`tenacity`, `pydantic`) | exact |
| `tests/test_llm_provider.py` (NEW) | test | request-response | `tests/test_kis_quote.py` (fake injected client, records request kwargs) | role-match |
| `tests/test_prompts.py` (NEW) | test | transform | `tests/test_indicators.py` | role-match |
| `tests/test_trade_signal.py` (NEW) | test | transform | `tests/test_signal_parser.py` (round-trip through `parse_signal`) | role-match |

Domain (`domain.py`) and port (`ports.py`) are **unchanged**: `LLMSignal` stays a frozen dataclass (D-06); the `LLMProvider` Protocol already exists (`ports.py:23-29`).

## Pattern Assignments

### `trading_bot/llm_provider.py` (adapter + factory, request-response)

**Analog A — factory shape:** `trading_bot/data_source.py` `build_data_source` (lines 302-355)
**Analog B — network adapter + retry + injectable client:** `trading_bot/kis_quote.py` `KisQuoteAdapter` (lines 70-146)

**Injectable-factory pattern** — mirror `build_data_source`. Note `build_data_source` (lines 307-334) makes each collaborator an injectable kwarg defaulting to `None`, constructs the real one only when omitted. Do the SAME with `client=None`, and use a **lazy import inside the branch** to keep the SDK off the import path (Pitfall 3 / `test_ports.py` guard):

```python
# analog: data_source.py:302-334 (injectable-with-None-default + lazy import)
def build_llm_provider(settings: Settings, *, client=None) -> LLMProvider:
    if settings.llm_provider is LLMProviderName.CLAUDE:
        if client is None:
            import anthropic  # lazy — keeps SDK off ports import path
            client = anthropic.Anthropic(
                api_key=settings.active_llm_api_key.get_secret_value())
        return ClaudeLLMProvider(client=client, model=settings.anthropic_model,
                                 temperature=settings.anthropic_temperature)
    if client is None:
        import openai
        client = openai.OpenAI(api_key=settings.active_llm_api_key.get_secret_value())
    return OpenAILLMProvider(client=client, model=settings.openai_model,
                             temperature=settings.openai_temperature)
```
Use `settings.active_llm_api_key.get_secret_value()` (config.py:134-138) — resolves the one active key; `.get_secret_value()` confined to the client constructor (CFG-01).

**Retry pattern** (D-09) — copy `kis_quote.py:135-145` **verbatim in shape**: a nested `@retry`-decorated `_attempt()` inside a method, with an internal transient-marker exception class (`kis_quote.py:42-43`):

```python
# analog: kis_quote.py:42-43 + 135-145
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

class _TransientLLMError(Exception):
    """Internal marker for retryable transient LLM-call failures."""

def _call_with_retry(self, system_prompt, user_body):
    @retry(
        reraise=True,                                   # surface typed error to HOLD boundary
        stop=stop_after_attempt(self._max_retries),
        wait=wait_fixed(self._retry_backoff_seconds),
        retry=retry_if_exception_type(_TransientLLMError),
    )
    def _attempt():
        try:
            return self._raw_call(system_prompt, user_body)
        except Exception as exc:                        # map transient API/transport -> retryable
            raise _TransientLLMError(str(exc)) from exc
    return _attempt()
```
`reraise=True` (kis_quote.py:137) is load-bearing: on exhaustion the typed error surfaces to the cycle boundary rather than tenacity's `RetryError`. `kis_quote.py` uses `wait_fixed`; D-09 permits `wait_exponential` — planner's discretion.

**Re-validation gate (D-05)** — every provider serializes to JSON and routes through `parse_signal` (signal_parser.py:47). Never return the provider's parsed object directly:
```python
import json
from trading_bot.signal_parser import parse_signal, SignalParseError

def _finalize(self, raw_input_obj: dict) -> LLMSignal:
    try:
        parsed = parse_signal(json.dumps(raw_input_obj))
    except SignalParseError as exc:
        raise LLMProviderError(f"provider output failed re-validation: {exc}") from exc
    return parsed.signal
```

**Typed-error class (D-10)** — model `LLMProviderError` on the `SignalParseError` role (signal_parser.py:23-28): a named subclass whose docstring states callers must treat it as HOLD / no-trade. Do NOT manufacture a synthetic `{HOLD,0.0}` signal.

**Anthropic adapter** — forced tool use + `strict:true`, `tool_choice={"type":"tool","name":"emit_signal"}`, and **omit `temperature`** (Pitfall 1: 4.6+/4.8 models 400 on temperature/top_p/top_k). See RESEARCH.md Code Examples §1 for the `EMIT_SIGNAL_TOOL` dict. Iterate `response.content` selecting `block.type == "tool_use"`; guard `response.stop_reason == "refusal"` -> `LLMProviderError` (Pitfall 6).

**OpenAI adapter** — `client.chat.completions.parse(response_format=TradeSignal, temperature=self.temperature)` (temperature IS valid here). Guard `message.refusal` and `message.parsed is None` -> `LLMProviderError` (Pitfall 5). See RESEARCH.md Code Examples §2.

**Repr redaction** — mirror `kis_quote.py:111-112`: a `__repr__` that shows only non-secret fields (model, provider), never the client/key.

---

### `trading_bot/prompts.py` (utility, pure transform)

**Analog:** `trading_bot/indicators.py` — a pure, no-I/O, no-SDK module returning plain data (technicals keys defined at indicators.py:115-120). `prompts.py` is the same shape: versioned constant + pure function, unit-testable like `indicators.py`, no SDK import (stays green under `test_ports.py`).

**Technicals keys to render (D-04)** — the exact keys the render function must surface so the LLM can cite them (from indicators.py:115-120, flowing into `DataContext.technicals`):
```
sma_short, sma_long, rsi_14, atr_14, historical_volatility, volume_ratio
```

**DataContext shape consumed** (domain.py:59-66): `ticker: Ticker`, `current_price: Money`, `technicals: Mapping[str,float]`, `news: Sequence[str]`.

**Pattern:** module-level `SYSTEM_PROMPT` constant (D-01 volatility-breakout framing, D-02 calibrated confidence, D-11 untrusted-news ignore rule) + pure `render_prompt(context: DataContext) -> str`. News delimiting per RESEARCH.md Pattern 5 (`<untrusted_news><news_item>…`). No config-overridable prompt text (D-03); no second sanitization pass (D-12).

---

### `trading_bot/trade_signal.py` (model, Pydantic I/O schema)

**Analog A — Pydantic model in this project:** `trading_bot/config.py` `KisCredentialGroup` (lines 26-33) — the established `pydantic.BaseModel` shape.
**Analog B — the shape being mirrored:** `trading_bot/domain.py` `LLMSignal` (lines 69-75) and `Decision` (lines 10-15).

**Pattern** (D-06) — a `BaseModel` with `model_config = {"extra": "forbid"}` (→ `additionalProperties: false` in JSON schema, needed for Anthropic strict) mirroring the three `LLMSignal` fields, reusing the domain `Decision` enum:
```python
from pydantic import BaseModel
from trading_bot.domain import Decision

class TradeSignal(BaseModel):
    model_config = {"extra": "forbid"}
    decision: Decision
    confidence: float
    reason: str
```
No re-implemented validation — `parse_signal` is the authority (bool-as-number rejection at signal_parser.py:103, 0.0-1.0 range at :108, non-empty reason at :117). Provider I/O only; do NOT convert the domain `LLMSignal` to Pydantic.

---

### `trading_bot/config.py` (config, MODIFY — extend in place)

**Analog:** the existing retry-defaults block (config.py:85-88) and the LLM key resolver (config.py:140-152).

Add per-provider model ID + temperature fields (D-07) alongside the existing `llm_provider`/`anthropic_api_key`/`openai_api_key` fields (config.py:47-49). Default `anthropic_model = "claude-opus-4-8"`, temperature `0.0` (checkpoint the OpenAI model ID — Assumption A1). Optionally add dedicated `llm_max_retries=3` / `llm_retry_backoff_seconds=1.0` mirroring `kis_max_retries`/`kis_retry_backoff_seconds` (config.py:87-88). If new positive-int fields are added, register them in `_require_positive_source_policy` (config.py:106-124). Keep temperature validation loose (Claude ignores it; only OpenAI sends it — Pitfall 1).

---

### Test files

**`tests/test_llm_provider.py`** — analog `tests/test_kis_quote.py`: inject a **fake SDK client** via `build_llm_provider(settings, client=fake)`, record request kwargs, return canned structured outputs / refusals / malformed shapes. No network, no API key. Assert Claude request omits `temperature` and sets `tool_choice=emit_signal`; assert OpenAI sends `temperature=0.0`; assert malformed/refusal/None-parsed -> `LLMProviderError`; assert retry exhaustion (fake raising transient N times) -> typed error.

**`tests/test_prompts.py`** — analog `tests/test_indicators.py`: assert all six technicals keys present, price present, news wrapped in `<untrusted_news>`, `SYSTEM_PROMPT` contains the ignore-instructions rule.

**`tests/test_trade_signal.py`** — analog `tests/test_signal_parser.py`: field-name lockstep `set(TradeSignal.model_fields) == {f.name for f in dataclasses.fields(LLMSignal)}`; round-trip `TradeSignal.model_dump(mode="json")` through `parse_signal` equals the source `LLMSignal` (D-06 guard, Pitfall 4).

## Shared Patterns

### Fail-safe typed error → HOLD (D-10)
**Source:** `trading_bot/signal_parser.py:23-28` (`SignalParseError` class) + `trading_bot/execution.py:247-263` (catch → HOLD `_finalize_cycle`)
**Apply to:** `llm_provider.py` (`LLMProviderError` class) and the cycle wiring that calls `generate_signal`.
The template: `execute_signal_cycle` catches `SignalParseError` and returns `ExecutionAction.HOLD` with `parse_error=str(exc)` — never a partial order. The LLM boundary mirrors this: `LLMProviderError` at the cycle boundary → HOLD, no synthetic signal.
```python
# execution.py:248-263
try:
    parsed = parse_signal(raw_signal)
except SignalParseError as exc:
    return _finalize_cycle(..., action=ExecutionAction.HOLD, order=None,
                           parse_error=str(exc), ...)
```

### Injectable collaborator factory (LLM-01)
**Source:** `trading_bot/data_source.py:302-355` (`build_data_source`)
**Apply to:** `build_llm_provider`.
Each collaborator is an injectable kwarg defaulting to `None`; the real one is constructed from `Settings` only when omitted — enables offline tests with fakes.

### Bounded tenacity retry (D-09)
**Source:** `trading_bot/kis_quote.py:42-43, 135-145`
**Apply to:** both provider adapters' call path.
Internal transient-marker exception + `@retry(reraise=True, stop=stop_after_attempt(...), wait=..., retry=retry_if_exception_type(_Transient...))`. `reraise=True` surfaces the typed error to the HOLD boundary.

### Import-boundary guard (LLM-01)
**Source:** `tests/test_ports.py:116-144` (`test_ports_stay_adapter_free_in_fresh_interpreter`)
**Apply to:** all new modules. `FORBIDDEN_MODULE_PREFIXES` (test_ports.py:10-16 and the subprocess list at :129) already includes `anthropic` and `openai`. Keep SDK imports **only** inside `llm_provider.py`, lazy-imported inside the factory branch — never in `ports.py`, `domain.py`, `config.py`, `signal_parser.py`, `prompts.py`, or `trade_signal.py`.

### Secret handling (CFG-01)
**Source:** `trading_bot/config.py:134-138` (`active_llm_api_key`) + `startup_banner` redaction (:155-169) + `kis_quote.py:111-112` (`__repr__` redaction)
**Apply to:** `llm_provider.py`. `.get_secret_value()` only at the client constructor; the structlog reproducibility line (D-08) carries prompt/response/signal, never the key.

## No Analog Found

None. Every new file has a strong in-repo analog. Two seams need a `checkpoint:human-verify` (per RESEARCH.md) but are pattern-covered:
- **Temperature-400 on Claude 4.6+** contradicts D-07's literal wording — Anthropic adapter omits `temperature` (Pitfall 1).
- **OpenAI model ID + exact `parse()` signature** unverified (Assumptions A1/A2) — gate the model ID; the fake-client test catches signature drift.
- **New dependency pins** (`anthropic`, `openai`, `structlog`) — project's established human dependency-lock gate.

`structlog` reproducibility logging (D-08) has no prior in-repo usage (it is a new dependency); follow RESEARCH.md Pattern 4 (one `log.info("llm_signal_cycle", ...)` line).

## Metadata

**Analog search scope:** `trading_bot/`, `tests/`
**Files scanned:** ports.py, domain.py, signal_parser.py, config.py, data_source.py, kis_quote.py, execution.py, indicators.py, test_ports.py (+ directory listings)
**Pattern extraction date:** 2026-07-02
