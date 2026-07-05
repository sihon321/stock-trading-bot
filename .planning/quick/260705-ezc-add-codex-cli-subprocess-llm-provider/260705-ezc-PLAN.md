---
quick_id: 260705-ezc
slug: add-codex-cli-subprocess-llm-provider
description: Add Codex CLI subprocess LLM provider
date: 2026-07-05
status: complete
---

# Quick Task 260705-ezc: Add Codex CLI subprocess LLM provider

## Goal

Add a third LLM provider that drives the **Codex CLI via `subprocess`**
(`codex exec [args] "<prompt>"`) alongside the existing API-based Claude and
OpenAI adapters. Codex returns free-form agent text rather than a
schema-guaranteed structured output, so the provider must prompt for a bare JSON
signal and re-validate it through the existing fail-safe `parse_signal` boundary
(unparseable output → `LLMProviderError` → HOLD / no trade).

## Task

**Files:**
- `trading_bot/config.py`
- `trading_bot/llm_provider.py`
- `tests/test_llm_provider.py`

**Action:**
1. `config.py` — add `LLMProviderName.CODEX_CLI = "codex_cli"`; add settings
   `codex_cli_binary`, `codex_cli_model` (optional → `--model` only when set),
   `codex_cli_temperature` (advisory/log-only), `codex_cli_timeout_seconds`,
   `codex_cli_extra_args`. Treat the Codex path as needing **no API key** (the
   CLI holds its own login) in `_require_selected_llm_credentials`, and add
   `codex_cli_timeout_seconds` to the positive-value validator.
2. `llm_provider.py` — add `CodexCLIProvider` with an **injectable subprocess
   runner** (defaults to `subprocess.run`); build one combined prompt
   (`SYSTEM_PROMPT` + rendered candidate + strict JSON-only instruction), run it
   with the shared retry/backoff helper, extract a single JSON object from
   stdout (`_extract_json_object` / `_last_json_object`, string-aware brace
   scan), re-validate via `_finalize`/`parse_signal`, and emit one secret-free
   audit log line. Wire the Codex branch into `build_llm_provider` (new optional
   `runner=` param).
3. `tests/test_llm_provider.py` — add coverage: build selection, no-API-key
   build, argv construction (model + extra args + prompt last), pure JSON,
   noisy/fenced JSON extraction, no-JSON fail-safe, non-zero exit + bounded
   retry, transient-then-success, malformed-signal re-validation, single log
   line.

**Verify:** `pytest tests/test_llm_provider.py tests/test_config.py` and the full
suite pass.

**Done:** Full suite green (322 tests); `codex_cli` selectable via
`LLM_PROVIDER=codex_cli`; unparseable CLI output fails safe to HOLD.

## must_haves

- **truths:**
  - Codex output is re-validated through `parse_signal`; unparseable → HOLD.
  - No Codex API key is handled by the project; the CLI authenticates itself.
  - The subprocess runner is injectable so tests never spawn a real process.
- **artifacts:**
  - `CodexCLIProvider` in `trading_bot/llm_provider.py`.
  - `LLMProviderName.CODEX_CLI` + `codex_cli_*` settings in `trading_bot/config.py`.
- **key_links:**
  - `build_llm_provider` routes `CODEX_CLI` → `CodexCLIProvider`.
  - Provider satisfies the `LLMProvider` protocol (sync `generate_signal`).
