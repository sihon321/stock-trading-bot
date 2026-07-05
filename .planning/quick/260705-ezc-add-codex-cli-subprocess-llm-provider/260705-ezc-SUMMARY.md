---
quick_id: 260705-ezc
slug: add-codex-cli-subprocess-llm-provider
description: Add Codex CLI subprocess LLM provider
date: 2026-07-05
status: complete
commit: a22a615
---

# Quick Task 260705-ezc: Summary

## What changed

Added **`CodexCLIProvider`** — a third `LLMProvider` implementation that invokes
the locally installed Codex CLI via `subprocess` (`codex exec [args] "<prompt>"`)
instead of an HTTP API call. It sits alongside the existing `ClaudeLLMProvider`
and `OpenAILLMProvider` and is selectable with `LLM_PROVIDER=codex_cli`.

- **`trading_bot/config.py`**
  - New enum member `LLMProviderName.CODEX_CLI = "codex_cli"`.
  - New settings: `codex_cli_binary` (default `"codex"`), `codex_cli_model`
    (optional → passed as `--model` only when set), `codex_cli_temperature`
    (advisory/log-only), `codex_cli_timeout_seconds`, `codex_cli_extra_args`.
  - `_require_selected_llm_credentials` returns early for the Codex path (no API
    key handled by the project — the CLI holds its own login).
  - `codex_cli_timeout_seconds` added to the positive-value validator.

- **`trading_bot/llm_provider.py`**
  - `CodexCLIProvider.generate_signal` builds one combined prompt
    (`SYSTEM_PROMPT` + `render_prompt` + strict JSON-only instruction), runs it
    through the shared `_call_provider_with_retry` helper with an **injectable
    subprocess runner** (defaults to `subprocess.run`), then extracts a single
    JSON object from stdout and re-validates through `_finalize`/`parse_signal`.
  - `_extract_json_object` / `_last_json_object` pull the signal out of noisy or
    code-fenced CLI output (string-aware brace scan); no JSON → `LLMProviderError`
    → HOLD / no trade.
  - Non-zero exit / timeout / missing binary are retried (bounded) and mapped to
    a fail-safe `LLMProviderError`; one secret-free `llm_signal_cycle` log line
    is emitted per call.
  - `build_llm_provider` gains an optional `runner=` param and routes
    `CODEX_CLI` to the new provider.

- **`tests/test_llm_provider.py`** — 11 new tests (`FakeCodexRunner` stub so no
  real process is spawned).

## Verification

- `pytest tests/test_llm_provider.py tests/test_config.py` → pass (69).
- Full suite → **322 passed**.

## Follow-ups (out of scope, not committed)

- `.env.example` is under a permission-denied path; document the new env vars
  there when accessible: `LLM_PROVIDER=codex_cli`, `CODEX_CLI_BINARY`,
  `CODEX_CLI_MODEL`, `CODEX_CLI_TIMEOUT_SECONDS`, `CODEX_CLI_EXTRA_ARGS`.
- If the local Codex setup prompts for approval non-interactively, set
  `CODEX_CLI_EXTRA_ARGS` (e.g. `--skip-git-repo-check`) rather than changing code.

## Commit

- `a22a615` — feat(quick-260705-ezc): add Codex CLI subprocess LLM provider
