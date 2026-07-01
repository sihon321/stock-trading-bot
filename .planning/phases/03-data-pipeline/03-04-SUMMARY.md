---
phase: 03-data-pipeline
plan: 04
subsystem: api
tags: [kis, httpx, tenacity, oauth-token, current-price, source-health, secret-redaction]

# Dependency graph
requires:
  - phase: 03-01
    provides: KIS token TTL/rate-limit manual decisions and Settings KIS controls
  - phase: 03-02
    provides: SourceHealth/SourceStatus source-health types and normalization convention
provides:
  - Shared cached KIS token manager (KisTokenManager) with refresh margin, bounded retry/backoff, min-interval throttle, and runtime expiry parsing
  - build_kis_auth_config(settings) sourcing credentials from Settings.active_kis only
  - KIS current-price adapter (KisQuoteAdapter/KisQuoteResult) returning Money(KRW) or typed UNAVAILABLE health
  - KisAuthError carrying a normalized UNAVAILABLE SourceHealth
affects: [03-05, 03-06, phase-05-execution]

# Tech tracking
tech-stack:
  added: [httpx, tenacity]
  patterns:
    - "Shared cached token manager reused by all KIS adapters (D-14)"
    - "Injectable HTTP client + monotonic clock for fully offline adapter tests"
    - "Bounded tenacity retry over an internal transient-error marker; terminal errors fail closed"
    - "Vendor/transport failures normalized to UNAVAILABLE SourceHealth (D-15)"
    - "Credential/token redaction from reprs, health reasons, and exceptions (T-03-04-I)"

key-files:
  created:
    - trading_bot/kis_auth.py
    - trading_bot/kis_quote.py
    - tests/test_kis_auth.py
    - tests/test_kis_quote.py
  modified: []

key-decisions:
  - "Token expiry derived at runtime from expires_in (fallback access_token_token_expired), never a hard-coded TTL"
  - "Retry only transient transport/HTTP-status failures; malformed JSON/missing-token/invalid-expiry/bad-price fail closed immediately"
  - "Quote adapter sources app key/secret via the shared token manager, keeping Settings.active_kis the single credential source"
  - "min_interval throttle and stop_after_attempt(max_retries) prevent a retry storm (T-03-04-D)"

patterns-established:
  - "Pattern: shared KIS infrastructure - one token manager instance owns cache/refresh/lock for Phase 3 quotes and Phase 5 orders"
  - "Pattern: typed unavailable result - price is None unless health is AVAILABLE, so a bad quote can never be a tradeable Money(0)"

requirements-completed: [DATA-03]

coverage:
  - id: D1
    description: "Shared cached KIS token manager: caches token until refresh margin, issues one refresh across repeated pre-expiry calls, refreshes inside the margin window, bounds retries, and normalizes token failures to UNAVAILABLE without leaking secrets."
    requirement: "DATA-03"
    verification:
      - kind: unit
        ref: "tests/test_kis_auth.py (18 tests: caching, refresh margin, bounded retry, malformed/HTTP/expiry normalization, secret redaction)"
        status: pass
    human_judgment: false
  - id: D2
    description: "KIS current-price adapter consuming the shared token manager: valid response -> Money(KRW); missing/nonnumeric/zero/negative/rt_cd-fail/HTTP-error/throttle/auth-unavailable -> typed UNAVAILABLE; correct endpoint/TR-ID/ticker mapping; no order/hashkey/broker surface."
    requirement: "DATA-03"
    verification:
      - kind: unit
        ref: "tests/test_kis_quote.py (25 tests: endpoint/TR-ID/ticker mapping, token reuse, price validation, failure normalization, bounded retry, no-order-surface, secret redaction)"
        status: pass
    human_judgment: false
  - id: D3
    description: "KIS app secrets and access tokens never appear in reprs, health reasons, exceptions, logs, or test diagnostics."
    requirement: "DATA-03"
    verification:
      - kind: unit
        ref: "tests/test_kis_auth.py#test_no_secret_leaks_in_repr_or_health_or_exceptions, tests/test_kis_quote.py#test_no_secret_leaks_in_result_or_repr"
        status: pass
    human_judgment: false

# Metrics
duration: 14min
completed: 2026-07-01
status: complete
---

# Phase 3 Plan 04: KIS Auth + Current-Price Adapter Summary

**Shared cached KIS token manager (runtime expiry, refresh margin, bounded retry, secret redaction) plus a fail-safe current-price adapter that returns Money(KRW) or a typed UNAVAILABLE SourceHealth via direct KIS REST over httpx.**

## Performance

- **Duration:** ~14 min
- **Started:** 2026-07-01
- **Completed:** 2026-07-01
- **Tasks:** 2 (both TDD)
- **Files modified:** 4 created

## Accomplishments
- `KisTokenManager` caches the KIS access token until a configurable refresh margin ahead of the runtime-discovered expiry, serializes refreshes behind a lock, and issues exactly one token across repeated pre-expiry calls (D-02/D-14).
- All token failure modes (transient transport, HTTP >=400/throttle, malformed JSON, missing access_token, missing/invalid expiry, exhausted bounded retries) normalize to a `KisAuthError` carrying an `UNAVAILABLE` `SourceHealth` (D-15).
- `KisQuoteAdapter` fetches the domestic-stock current price (`inquire-price`, TR ID `FHKST01010100`, market div `J`) using the shared token manager for auth, validates a 6-digit ticker and a numeric positive price before building `Money(amount, "KRW")`, and normalizes every bad/throttled/auth-unavailable case to a typed unavailable result.
- App key/secret and the access token are redacted from reprs, health reasons, and exceptions, proven by tests seeded with known secret strings (T-03-04-I).

## Task Commits

Each task was committed atomically (TDD red -> green):

1. **Task 1: shared KIS token manager** - `af4cc7b` (test), `0c0f6b8` (feat)
2. **Task 2: KIS current-price quote adapter** - `0edb92a` (test), `2ab3af2` (feat)

_The Task 2 feat commit also added `app_key`/`app_secret` accessors to `KisTokenManager` so the quote adapter reads credentials from the single shared source rather than a separate field._

## Files Created/Modified
- `trading_bot/kis_auth.py` - `KisToken`, `KisAuthConfig`, `KisTokenManager`, `KisAuthError`, `build_kis_auth_config`; cached token with refresh margin, bounded tenacity retry, min-interval throttle, runtime expiry parsing, secret redaction.
- `trading_bot/kis_quote.py` - `KisQuoteAdapter`, `KisQuoteResult`; read-only current-price path with response validation and typed unavailable normalization.
- `tests/test_kis_auth.py` - 18 offline tests (fake HTTP client + monotonic clock).
- `tests/test_kis_quote.py` - 25 offline tests (fake token manager + fake HTTP client).

## Decisions Made
- **Runtime expiry over hard-coded TTL:** `_parse_expiry` prefers numeric `expires_in`, falls back to the `access_token_token_expired` wall-clock string, and fails closed if neither is usable — matching the research warning against hard-coded KIS token TTL.
- **Retry only the transient:** an internal `_TransientAuthError`/`_TransientQuoteError` marker gates tenacity retries; terminal problems (malformed JSON, missing token, invalid expiry, bad price) fail closed immediately rather than burning retries.
- **Single credential source:** the quote adapter reads `app_key`/`app_secret` from the shared token manager (which is built from `Settings.active_kis`), so no independent active-credential field is introduced (D-14).

## Deviations from Plan

None - plan executed exactly as written. The `app_key`/`app_secret` accessor added to `KisTokenManager` during Task 2 is a within-plan consequence of "use `KisTokenManager` for auth and never issue tokens directly in the quote adapter" (the KIS quote endpoint requires appkey/appsecret headers), keeping `Settings.active_kis` the only credential source.

## Issues Encountered
- Initial quote implementation left the KIS `appkey` header empty (adapter had a separate unused param) and the module docstring literally contained the word "hashkey", tripping the header-presence and no-order-surface tests. Resolved by sourcing credentials from the shared token manager and rewording the docstring. Caught by TDD before commit; final `feat` commit is green.

## User Setup Required
None - no live KIS calls are made in this plan; all tests are offline with injected fakes. Real KIS usage requires the operator-recorded `.env` KIS credentials and the manual portal verification already captured in `03-MANUAL-DECISIONS.md`.

## Next Phase Readiness
- Plan 03-06 can wire `KisQuoteResult.price` into `DataContext.current_price` once source-health policy resolves AVAILABLE.
- Phase 5 KIS broker/order calls can reuse the same `KisTokenManager` instance instead of opening a second token flow (D-14).
- No blockers.

## Self-Check: PASSED

All four artifact files exist and all four task commits (`af4cc7b`, `0c0f6b8`, `0edb92a`, `2ab3af2`) are present in git history.
