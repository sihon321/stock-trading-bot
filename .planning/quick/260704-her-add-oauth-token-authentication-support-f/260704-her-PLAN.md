---
phase: quick-260704-her
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - trading_bot/config.py
  - trading_bot/llm_provider.py
  - .env.example
  - tests/test_config.py
  - tests/test_llm_provider.py
autonomous: true
requirements:
  - QUICK-OAUTH-01
must_haves:
  truths:
    - "The Claude provider authenticates successfully when only ANTHROPIC_AUTH_TOKEN is set (no ANTHROPIC_API_KEY)."
    - "The Claude provider still authenticates when only ANTHROPIC_API_KEY is set (existing behavior preserved)."
    - "When LLM_PROVIDER=claude and neither ANTHROPIC_API_KEY nor ANTHROPIC_AUTH_TOKEN is set, Settings construction fails with an error naming BOTH env vars."
    - "OpenAI provider still requires only OPENAI_API_KEY (unchanged)."
    - "build_llm_provider constructs anthropic.Anthropic with auth_token + the oauth-2025-04-20 beta header when an auth token is configured and no client is injected."
    - "The auth token is never leaked in repr, startup banner, or logs (SecretStr redaction preserved)."
    - "The client-injection path (tests inject a fake client) is untouched and existing tests stay green."
  artifacts:
    - trading_bot/config.py
    - trading_bot/llm_provider.py
    - .env.example
    - tests/test_config.py
    - tests/test_llm_provider.py
  key_links:
    - "config.anthropic_auth_token -> build_llm_provider auth_token selection"
    - "build_llm_provider -> anthropic.Anthropic(auth_token=..., default_headers={anthropic-beta: oauth-2025-04-20})"
    - "SecretStr redaction -> startup_banner / repr / structlog cycle log (no token leakage)"
---

<objective>
Add OAuth bearer-token authentication for the Claude (Anthropic) LLM provider as an alternative to the existing API-key auth, without removing API-key support.

Purpose: Support Claude Code / `ant auth login` OAuth tokens (e.g. `sk-ant-oat01-...`) so the bot can run under either credential type. OAuth tokens set `Authorization: Bearer <token>` (via the SDK's `auth_token=` argument) and require the beta header `anthropic-beta: oauth-2025-04-20` on `/v1/messages` requests. API key and auth token are mutually exclusive at the HTTP layer, so exactly one is selected.

Output: A new `anthropic_auth_token` config field, relaxed Claude-provider validation (either credential accepted), auth-token-aware client construction in `build_llm_provider`, updated `.env.example`, and tests covering both credential paths plus the neither-set failure and no-secret-leakage.
</objective>

<execution_context>
@/Users/user/workspace/stock-trading-bot/.claude/gsd-core/workflows/execute-plan.md
@/Users/user/workspace/stock-trading-bot/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.claude/CLAUDE.md
@trading_bot/config.py
@trading_bot/llm_provider.py
@tests/test_config.py
@tests/test_llm_provider.py
@tests/conftest.py
</context>

<design_decisions>
Precedence (must be implemented consistently in config validation AND client construction):
- When BOTH ANTHROPIC_AUTH_TOKEN and ANTHROPIC_API_KEY are set for the Claude provider, the AUTH TOKEN takes precedence. Rationale: setting an OAuth token is the explicit newer-intent credential, and the SDK/API rejects sending both auth headers simultaneously, so the code must pick exactly one — never pass both to `anthropic.Anthropic(...)`.
- Config validation for LLM_PROVIDER=claude passes when AT LEAST ONE of the two is set.
- Do not touch the OpenAI branch: it still requires OPENAI_API_KEY only.

Exposure to build_llm_provider:
- Keep the existing `active_llm_api_key` property (used by the OpenAI path and the Claude api-key fallback path).
- Expose the auth token to `build_llm_provider` via a dedicated read of the raw optional field `settings.anthropic_auth_token` (an `Optional[SecretStr]`). `build_llm_provider` checks it first and, when present, builds the auth-token client; otherwise it falls back to the api-key client exactly as today. This keeps `active_llm_api_key` semantics unchanged (it only ever returns an API key).

Secret safety:
- `anthropic_auth_token` is a `SecretStr`, so repr/str already redact it. Do NOT add any new code path that prints, logs, or formats the token's plaintext. The startup banner already prints "Secrets: REDACTED" and no per-field secret; leave it that way (do not add the token to the banner).
</design_decisions>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add anthropic_auth_token config field and relax Claude-provider validation</name>
  <files>trading_bot/config.py, tests/test_config.py</files>
  <behavior>
    - With LLM_PROVIDER=claude and only ANTHROPIC_AUTH_TOKEN set (ANTHROPIC_API_KEY unset): Settings() constructs successfully and settings.anthropic_auth_token.get_secret_value() returns the token.
    - With LLM_PROVIDER=claude and only ANTHROPIC_API_KEY set (ANTHROPIC_AUTH_TOKEN unset): Settings() still constructs (existing behavior) and active_llm_api_key returns the api key.
    - With LLM_PROVIDER=claude and NEITHER set: Settings() raises ValidationError, and the diagnostic string contains BOTH the literal ANTHROPIC_API_KEY and the literal ANTHROPIC_AUTH_TOKEN.
    - With LLM_PROVIDER=openai and no OPENAI_API_KEY: still raises, diagnostic names OPENAI_API_KEY (unchanged). The claude-neither error must not affect the openai branch.
    - No secret leakage: repr(settings) and startup_banner(settings) contain neither the api key nor the auth token plaintext (add the auth-token sentinel to the leakage assertions).
  </behavior>
  <action>
Add field `anthropic_auth_token: Optional[SecretStr] = None` to `Settings` (env var ANTHROPIC_AUTH_TOKEN), placed next to `anthropic_api_key`.

Relax `_require_selected_llm_key`: the method currently returns the selected SecretStr AND doubles as the validator. Keep it returning a SecretStr for the api-key/openai callers, but change the CLAUDE branch so validation passes when EITHER `anthropic_api_key` OR `anthropic_auth_token` is set. Concretely: in the CLAUDE branch, if `anthropic_api_key` is set return it; else if `anthropic_auth_token` is set, the credential requirement is satisfied but there is no API key to return — return handling here must not raise, yet `active_llm_api_key` should never be called on the auth-token-only path (build_llm_provider reads `anthropic_auth_token` directly). Implement this cleanly: split responsibilities so the model validator enforces "at least one claude credential" (call a small internal check that raises when neither is set), and keep `active_llm_api_key` returning the api key only. Recommended shape: introduce a private `_require_selected_llm_credentials()` used by `validate_safety_gates` that, for CLAUDE, raises only when BOTH `anthropic_api_key` and `anthropic_auth_token` are None; keep `active_llm_api_key`/`_require_selected_llm_key` for the api-key + openai return path. Ensure `active_llm_api_key` is not invoked during validation for the auth-token-only case (it currently is invoked indirectly via `_require_selected_llm_key` inside `validate_safety_gates`; rewire the validator to the new credentials check so an auth-token-only claude config does not trip the missing-api-key error).

Update the CLAUDE missing-credential error message so it names BOTH `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` (e.g. "LLM_PROVIDER=claude requires ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN for the active provider"). Leave the OPENAI error message unchanged.

Do not modify `startup_banner` (it already redacts). Do not add the token to any log or banner line.

In tests/test_config.py: add "ANTHROPIC_AUTH_TOKEN" to the ENV_KEYS tuple (so set_base_env clears it between tests). Add "anthropic-auth-token-secret" to SECRET_VALUES so leakage assertions cover it. Add tests: (a) claude works with only the auth token — set LLM_PROVIDER=claude, delete ANTHROPIC_API_KEY, set ANTHROPIC_AUTH_TOKEN, assert Settings() constructs and anthropic_auth_token secret matches; (b) claude still works with only api key (an assertion that with only ANTHROPIC_API_KEY set and auth token unset it constructs — extend or mirror test_claude_provider_requires_only_anthropic_key); (c) claude fails when NEITHER is set — delete both, assert ValidationError whose diagnostic contains both var names and leaks no secret; (d) no auth-token leakage — construct with the auth token set and assert_no_secret_leaked(repr(settings), startup_banner(settings)).
  </action>
  <verify>
    <automated>python -m pytest tests/test_config.py -x -q</automated>
  </verify>
  <done>
All test_config.py tests pass. Settings accepts a claude config with only the auth token, only the api key, and rejects claude with neither (error names both ANTHROPIC_API_KEY and ANTHROPIC_AUTH_TOKEN). OpenAI validation unchanged. No secret (api key or auth token) appears in repr or banner.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Build auth-token anthropic client in build_llm_provider with oauth beta header</name>
  <files>trading_bot/llm_provider.py, tests/test_llm_provider.py</files>
  <behavior>
    - When settings.llm_provider is CLAUDE, no client injected, and settings.anthropic_auth_token is set: build_llm_provider constructs anthropic.Anthropic(auth_token=<token>, default_headers={"anthropic-beta": "oauth-2025-04-20"}) and does NOT pass api_key.
    - When CLAUDE, no client injected, auth_token unset but api_key set: constructs anthropic.Anthropic(api_key=<api_key>) as today (no default_headers/auth_token).
    - When both auth_token and api_key are set: auth_token wins (constructs the auth-token client; api_key not passed).
    - Client-injection path is untouched: passing client=<fake> never triggers SDK import or credential reads (existing test_injected_client_does_not_surface_active_api_key stays green).
    - The returned provider is still a ClaudeLLMProvider wired with model/temperature/retries from settings.
  </behavior>
  <action>
In `build_llm_provider`, inside the `settings.llm_provider is LLMProviderName.CLAUDE` branch, only when `client is None`: read `settings.anthropic_auth_token`. If it is not None, `import anthropic` and construct `client = anthropic.Anthropic(auth_token=settings.anthropic_auth_token.get_secret_value(), default_headers={"anthropic-beta": "oauth-2025-04-20"})`. Otherwise keep the existing `client = anthropic.Anthropic(api_key=settings.active_llm_api_key.get_secret_value())` fallback. This gives auth_token precedence. Do NOT pass both `api_key` and `auth_token` to the constructor on any path. Leave the OpenAI branch and the ClaudeLLMProvider wiring (model/temperature/max_retries/retry_backoff) unchanged. Do not log or print the token value.

Define the beta header value as a module-level constant near EMIT_SIGNAL_TOOL (e.g. `ANTHROPIC_OAUTH_BETA_HEADER = "oauth-2025-04-20"`) and reference it in the default_headers dict so the test can assert against the same source of truth.

In tests/test_llm_provider.py: add a test that, with settings from make_settings(llm_provider=LLMProviderName.CLAUDE, anthropic_auth_token=SecretStr("test-oauth-token"), anthropic_api_key=None) and NO injected client, calls build_llm_provider and verifies the constructed anthropic client received auth_token=the token and default_headers containing "anthropic-beta": "oauth-2025-04-20", and did NOT receive api_key. Because build_llm_provider does `import anthropic` lazily, monkeypatch the constructed client by patching `anthropic.Anthropic` (import the anthropic module inside the test or use unittest.mock.patch("anthropic.Anthropic")) with a fake that records its kwargs; assert on the recorded kwargs. Keep the interpreter-laziness test green by not importing anthropic at module top level in the production code (it already imports lazily). Add a second assertion path (or a sibling test) confirming that with only anthropic_api_key set and auth token None, the recorded kwargs contain api_key and NOT auth_token/default_headers. Note make_settings currently sets both anthropic_api_key and openai_api_key by default, so pass anthropic_auth_token and explicitly set anthropic_api_key where the test needs a specific combination.
  </action>
  <verify>
    <automated>python -m pytest tests/test_llm_provider.py -x -q</automated>
  </verify>
  <done>
All test_llm_provider.py tests pass, including the new auth-token construction test (auth_token + oauth-2025-04-20 beta header, no api_key) and the api-key fallback assertion. Existing injected-client and lazy-import tests remain green.
  </done>
</task>

<task type="auto">
  <name>Task 3: Document ANTHROPIC_AUTH_TOKEN in .env.example and run full suite</name>
  <files>.env.example</files>
  <action>
Read the current .env.example first (it lives in a restricted directory; use the editor's read-before-edit). Add an `ANTHROPIC_AUTH_TOKEN=` entry near the existing `ANTHROPIC_API_KEY` line, with a comment documenting it as an ALTERNATIVE to ANTHROPIC_API_KEY for the Claude provider (OAuth bearer token, e.g. from `ant auth login` / Claude Code, format like `sk-ant-oat01-...`), and note that when both are set the auth token takes precedence. Leave the value blank (placeholder) — never commit a real token. Do not remove or alter the existing ANTHROPIC_API_KEY documentation.

Then run the full test suite to confirm nothing else regressed.
  </action>
  <verify>
    <automated>python -m pytest -q</automated>
  </verify>
  <done>
.env.example documents ANTHROPIC_AUTH_TOKEN as an alternative to ANTHROPIC_API_KEY with precedence noted and a blank placeholder. Full `pytest` suite passes green.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| env/.env -> Settings | OAuth bearer token and API key enter the process as untrusted config; must be typed as SecretStr and never echoed. |
| Settings -> anthropic.Anthropic | Selected credential is placed in an HTTP auth header (x-api-key OR Authorization: Bearer); only one may be sent. |
| Settings -> logs/banner/repr | Diagnostics and structured logs must never render the token/key plaintext. |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-quick-01 | Information Disclosure | anthropic_auth_token in repr/banner/logs | high | mitigate | Field is SecretStr (auto-redacted); no new code path prints the token; leakage assertion extended with the auth-token sentinel in tests/test_config.py. |
| T-quick-02 | Tampering / Spoofing | anthropic.Anthropic auth header selection | medium | mitigate | Never pass both api_key and auth_token; auth-token path adds the required oauth-2025-04-20 beta header; explicit precedence (auth_token wins) enforced identically in config validation and client construction. |
| T-quick-03 | Denial of Service (fail-open) | Claude-provider credential validation | medium | mitigate | Model validator fails closed when neither claude credential is set; error names both env vars so the operator cannot silently run credential-less. |
| T-quick-SC | Tampering | npm/pip/cargo installs | low | accept | No new dependencies; `anthropic` SDK already pinned in the stack. No package installs in this plan, so no legitimacy checkpoint required. |
</threat_model>

<verification>
- `python -m pytest -q` passes (full suite green).
- Claude provider constructs with only ANTHROPIC_AUTH_TOKEN, only ANTHROPIC_API_KEY, and fails with neither (error names both vars).
- OpenAI provider behavior unchanged.
- build_llm_provider passes auth_token + `anthropic-beta: oauth-2025-04-20` header when the auth token is set and no client injected; never passes both credentials.
- No token/key plaintext in repr, startup banner, or structlog cycle logs.
- Client-injection path and lazy-SDK-import behavior preserved.
- (Optional, only if tooling is later added) ruff/mypy are not configured in pyproject.toml, so they are not gates for this change; `pytest` is the hard gate.
</verification>

<success_criteria>
- OAuth bearer-token auth is a working alternative to the API key for the Claude provider, with API-key auth fully preserved.
- Exactly one auth credential reaches the SDK; auth_token takes precedence when both are set, consistently in config and client construction.
- The oauth-2025-04-20 beta header accompanies the auth-token client.
- No secret leakage; fail-closed when the claude provider has no credential.
- Full test suite green.
</success_criteria>

<output>
Create `.planning/quick/260704-her-add-oauth-token-authentication-support-f/260704-her-SUMMARY.md` when done.
</output>
