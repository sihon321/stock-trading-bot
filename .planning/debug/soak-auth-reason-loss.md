---
status: resolved
trigger: "KIS mock soak preflight collapses every token acquisition failure into AUTH_UNAVAILABLE"
created: 2026-08-13
updated: 2026-08-13
---

## Symptoms

- Expected: a failed KIS mock token acquisition remains fail-closed while persisting a bounded, non-secret category that distinguishes timeout, transport, HTTP auth/rate-limit/server, and malformed token responses.
- Actual: both daily-order and balance reconciliation persist only `AUTH_UNAVAILABLE`, even though `KisAuthError.health.reason` contains a more precise normalized cause.
- Error: `DAILY_AUTH_UNAVAILABLE|BALANCE_AUTH_UNAVAILABLE` during PRE_RUN; the same credentials succeeded several minutes later after refreshing the process-independent token cache.
- Timeline: observed on 2026-08-13 at 10:43 KST; retry completed authenticated GET preflight at 10:49 KST.
- Reproduction: make `KisTokenManager.get_token()` raise any `KisAuthError` and call a paged KIS order or balance query.

## Current Focus

- hypothesis: `KisOrderAdapter._query_pages` catches `KisAuthError` without inspecting its bounded health reason and always returns `AUTH_UNAVAILABLE`.
- test: inject representative token timeout, transport, HTTP status, and malformed-response failures and assert the paged envelope preserves only allowlisted reason codes.
- expecting: reconciliation persists the precise bounded code and still returns INCOMPLETE with zero pages and no broker mutation.
- next_action: resolved

## Evidence

- timestamp: 2026-08-13T01:43:31Z; PRE_RUN persisted `DAILY_AUTH_UNAVAILABLE|BALANCE_AUTH_UNAVAILABLE` with zero pages.
- timestamp: 2026-08-13T01:49:16Z; the same campaign and credentials persisted PRE_RUN `COMPLETE` with one daily and one balance page after the token cache was refreshed.
- timestamp: 2026-08-13; `KisOrderAdapter._query_pages` catches `KisAuthError` and unconditionally returns `AUTH_UNAVAILABLE`.
- timestamp: 2026-08-13; 67 focused auth/order/reconciliation tests passed after adding typed bounded auth diagnostics.
- timestamp: 2026-08-13; 127 adjacent auth/order/soak tests passed; 705 unaffected repository tests passed with only the pre-existing collection-broken `tests/test_soak_campaign.py` excluded.
- timestamp: 2026-08-13; `compileall` and `git diff --check` passed; repository-managed `ruff` was unavailable.

## Resolution

- root_cause: "KisTokenManager retained a normalized failure reason in KisAuthError.health, but KisOrderAdapter._query_pages discarded the exception and always returned AUTH_UNAVAILABLE. This erased the distinction between timeout, transport, HTTP authentication, rate limiting, generic HTTP failure, and malformed token responses."
- fix: "KisAuthError now carries a bounded reason_code. Token issuance classifies failures into AUTH_TIMEOUT, AUTH_TRANSPORT_ERROR, AUTH_HTTP_AUTH_ERROR, AUTH_HTTP_RATE_LIMITED, AUTH_HTTP_ERROR, or AUTH_RESPONSE_INVALID, and paged order/balance queries preserve that code in their incomplete envelope and reconciliation snapshot."
- verification: "67 focused and 127 adjacent tests passed; 705 unaffected repository tests passed with only the pre-existing test_soak_campaign.py collection failure excluded. compileall and git diff --check passed."
- files_changed: "trading_bot/kis_auth.py, trading_bot/kis_order.py, tests/test_kis_auth.py, tests/test_kis_order.py, tests/test_soak_reconcile.py"
