---
phase: 04-llm-agent
plan: 03
subsystem: llm-provider
tags: [llm, anthropic, openai, structlog, tenacity, structured-output]

requires:
  - phase: 04-llm-agent
    provides: "04-01 approved anthropic==0.115.1, openai==2.44.0, structlog==25.5.0, model defaults, and LLM retry settings"
  - phase: 04-llm-agent
    provides: "04-02 SYSTEM_PROMPT, PROMPT_VERSION, render_prompt, and TradeSignal provider schema"
provides:
  - "ClaudeLLMProvider using strict forced emit_signal tool use with Anthropic sampling parameters omitted"
  - "OpenAILLMProvider using chat.completions.parse with response_format=TradeSignal and temperature transmitted"
  - "Shared serialize-to-json then parse_signal re-validation, bounded tenacity retry, LLMProviderError fail-safe, and structlog llm_signal_cycle logging"
affects: [04-llm-agent, llm-provider, cycle-wiring, reproducibility]

tech-stack:
  added: []
  patterns: [forced tool use, openai parse structured output, parse_signal fail-safe, shared retry helper, structlog reproducibility line]

key-files:
  created:
    - trading_bot/llm_provider.py
    - tests/test_llm_provider.py
    - tests/conftest.py
    - .planning/phases/04-llm-agent/04-03-SUMMARY.md
  modified: []

key-decisions:
  - "Claude adapter stores temperature for reproducibility logging only and omits temperature, top_p, and top_k from Anthropic requests."
  - "OpenAI adapter calls client.chat.completions.parse with response_format=TradeSignal and sends temperature=0.0 by default."
  - "Both adapters serialize provider-native structured output to raw JSON and call parse_signal before returning LLMSignal."
  - "OpenAI parse signature was confirmed from installed openai==2.44.0 before implementation."

patterns-established:
  - "Provider Finalize Gate: provider output is converted to JSON-compatible dict data, json.dumps is applied, and parse_signal remains the only LLMSignal authority."
  - "Shared Retry Wrapper: both adapters call _call_provider_with_retry with tenacity reraise=True, stop_after_attempt(max_retries), wait_exponential(multiplier=retry_backoff_seconds), and _TransientLLMError."
  - "Reproducibility Log: each generate_signal call emits exactly one llm_signal_cycle event with provider, model, temperature, prompt_version, prompt, response, and outcome."

requirements-completed: [LLM-01, LLM-02, LLM-03]

coverage:
  - id: D1
    description: "Claude adapter sends strict forced emit_signal tool requests, omits unsupported sampling parameters, and revalidates tool output through parse_signal."
    requirement: LLM-02
    verification:
      - kind: unit
        ref: 'PATH="/opt/homebrew/bin:$PATH" PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_llm_provider.py -x'
        status: pass
      - kind: unit
        ref: 'PATH="/opt/homebrew/bin:$PATH" PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_ports.py -x'
        status: pass
    human_judgment: false
  - id: D2
    description: "OpenAI adapter uses chat.completions.parse with TradeSignal, sends temperature, guards refusals and None parsed outputs, and revalidates through parse_signal."
    requirement: LLM-02
    verification:
      - kind: unit
        ref: 'PATH="/opt/homebrew/bin:$PATH" PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_llm_provider.py tests/test_prompts.py tests/test_trade_signal.py -x'
        status: pass
    human_judgment: false
  - id: D3
    description: "Both adapters share fail-safe LLMProviderError behavior, bounded retry, and one secret-free structlog llm_signal_cycle event per generate_signal call."
    requirement: LLM-03
    verification:
      - kind: unit
        ref: 'tests/test_llm_provider.py#test_claude_retries_are_bounded_and_success_after_transient_failure'
        status: pass
      - kind: unit
        ref: 'tests/test_llm_provider.py#test_openai_retries_are_bounded'
        status: pass
      - kind: unit
        ref: 'tests/test_llm_provider.py#test_claude_logs_one_secret_free_cycle_event_on_success_and_error'
        status: pass
      - kind: unit
        ref: 'tests/test_llm_provider.py#test_openai_logs_one_secret_free_cycle_event'
        status: pass
    human_judgment: false

duration: 5min
completed: 2026-07-02
status: complete
---

# Phase 04 Plan 03: LLM Provider Adapter Summary

**Claude and OpenAI provider adapters with strict structured output, parse_signal re-validation, bounded retry, and reproducibility logging.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-07-02T04:08:31Z
- **Completed:** 2026-07-02T04:13:32Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Added `ClaudeLLMProvider` with forced `emit_signal` tool use, top-level `strict: True`, no Anthropic sampling parameters in the request, block iteration for `tool_use`, and fail-safe handling for refusals or missing tool output.
- Added `OpenAILLMProvider` using `client.chat.completions.parse(model=..., temperature=..., response_format=TradeSignal, messages=[system,user])`, with fail-safe refusal and `None` parsed guards.
- Added shared retry, JSON serialization, `parse_signal` re-validation, `LLMProviderError`, and one `llm_signal_cycle` structlog event per call.
- Added offline fake SDK client coverage for request shape, schema lockstep, valid parse paths, malformed output, refusals, retry exhaustion/success, and secret-free logs.

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Claude provider adapter tests** - `f1f58d9` (test)
2. **Task 1 GREEN: Claude LLM provider adapter** - `e927069` (feat)
3. **Task 2 RED: OpenAI provider adapter tests** - `6a3af00` (test)
4. **Task 2 GREEN: OpenAI LLM provider adapter** - `1f0ad84` (feat)

**Plan metadata:** committed separately during close-out.

## Files Created/Modified

- `trading_bot/llm_provider.py` - New provider adapter module containing `LLMProviderError`, `_TransientLLMError`, `EMIT_SIGNAL_TOOL`, `ClaudeLLMProvider`, `OpenAILLMProvider`, shared retry, finalize, serialization, and log helpers.
- `tests/test_llm_provider.py` - Offline provider adapter tests covering Claude and OpenAI request shape, strict schema, parse re-validation, fail-safe error paths, retry, and reproducibility logging.
- `tests/conftest.py` - `make_data_context`, `FakeAnthropicClient`, `FakeOpenAIClient`, and fake response builders.
- `.planning/phases/04-llm-agent/04-03-SUMMARY.md` - Completion record, verification evidence, and parse signature resolution.

## Decisions Made

- Anthropic `temperature` remains stored and logged but is not sent to `client.messages.create`; the request also omits `top_p` and `top_k`.
- OpenAI structured output uses `chat.completions.parse` rather than `responses.parse`, matching the plan and installed SDK surface.
- The adapters do not fabricate synthetic HOLD signals; every refusal, malformed output, missing structured output, or retry exhaustion raises `LLMProviderError`.

## OpenAI Parse Signature

Confirmed before Task 2 implementation with:

`PATH="/opt/homebrew/bin:$PATH" PYTHONUSERBASE="$PWD/.python-userbase" python3 -c "import inspect, openai; client = openai.OpenAI(api_key='sk-test'); parse = client.chat.completions.parse; print(openai.__version__); print(parse); print(inspect.signature(parse))"`

Result: `openai==2.44.0`; `OpenAI().chat.completions.parse` exists and accepts `messages`, `model`, `response_format`, and `temperature`. The printed signature starts:

`(*, messages: Iterable[ChatCompletionMessageParam], model: Union[str, ChatModel], ... response_format: type[ResponseFormatT] | Omit = <openai.Omit object ...>, ... temperature: Optional[float] | Omit = <openai.Omit object ...>, ... timeout: float | httpx.Timeout | None | NotGiven = NOT_GIVEN) -> ParsedChatCompletion[ResponseFormatT]`

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Git staging/commit required escalated execution because the managed sandbox could not create `.git/index.lock`. Commits were made with explicit file lists only.

## Verification

- `PATH="/opt/homebrew/bin:$PATH" PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_llm_provider.py -x` - PASS, `14 passed`
- `PATH="/opt/homebrew/bin:$PATH" PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_ports.py -x` - PASS, `7 passed`
- `PATH="/opt/homebrew/bin:$PATH" PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_llm_provider.py tests/test_prompts.py tests/test_trade_signal.py -x` - PASS, `24 passed`
- `PATH="/opt/homebrew/bin:$PATH" PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` - PASS, `269 passed`

## Known Stubs

None. Stub-pattern scan found only internal empty response accumulator variables and fake-client call lists, not user-facing or incomplete behavior.

## Threat Flags

None - all new provider-output, retry, prompt logging, and prompt-injection surfaces were covered by the plan threat model and have tests.

## User Setup Required

None - no external service configuration required for this plan. Tests use injected fake SDK clients only.

## Next Phase Readiness

Plan 04-04 can wire the factory and cycle boundary to these adapters. The shared adapter inputs are stable: constructor parameters are `client`, `model`, `temperature`, `max_retries`, and `retry_backoff_seconds`; factory code should lazy-import SDK clients and pass the active settings values into these constructors.

## Self-Check: PASSED

- Found `trading_bot/llm_provider.py`, `tests/test_llm_provider.py`, `tests/conftest.py`, and `.planning/phases/04-llm-agent/04-03-SUMMARY.md`.
- Found task commits `f1f58d9`, `e927069`, `6a3af00`, and `1f0ad84`.
- Verified no tracked file deletions in task commits.

---
*Phase: 04-llm-agent*
*Completed: 2026-07-02*
