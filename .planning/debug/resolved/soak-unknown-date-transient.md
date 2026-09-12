---
status: resolved
trigger: "Fix intermittent SOAK_RUN_NOT_ADMITTED:UNKNOWN_DATE when an immediate mock-only preflight confirms the current KRX trading day"
created: 2026-08-31
updated: 2026-08-31
---

## Symptoms

- Expected: an authenticated KIS mock calendar query should reliably confirm the current KRX trading day during the continuous session, while unavailable evidence remains fail-closed.
- Actual: the first `bot soak run` at 09:20 KST returned `SOAK_RUN_NOT_ADMITTED:UNKNOWN_DATE`; two immediate `bot soak preflight` invocations at 09:21 both returned `KRX_SESSION_OPEN`.
- Error: intermittent `UNKNOWN_DATE` before production execution; campaign state and credit remain unchanged.
- Timeline: reproduced on 2026-08-31 and previously observed as a one-shot failure followed by success on retry.
- Reproduction: invoke `bot soak run --campaign-id soak-20260828-20d-v1` during the confirmed continuous session when same-day pykrx is inconclusive and the first calendar witness attempt is unavailable.

## Current Focus

- hypothesis: confirmed. One semantically unavailable KIS calendar response was normalized to `None` and returned immediately, even though an independent request one minute later produced exact open-day evidence.
- test: deterministic first-response wrong-date payload followed by an exact requested-date `Y` payload.
- expecting: the read-only calendar adapter retries within its existing bounded query budget and returns `True` only after exact evidence.
- next_action: none.
- reasoning_checkpoint: the historical raw provider response was intentionally not persisted, so its exact unavailable subtype cannot be recovered; the local failure mechanism and missing retry boundary are confirmed.
- tdd_checkpoint: regression test fails on the previous implementation and passes after the bounded semantic retry.

## Evidence

- timestamp: 2026-08-31T09:20+09:00; soak run returned `SOAK_RUN_NOT_ADMITTED:UNKNOWN_DATE` after successful KRX login.
- timestamp: 2026-08-31T09:21+09:00; two immediate mock-only preflights both returned `KRX_SESSION_OPEN` for 2026-08-31.

## Eliminated

## Resolution

- root_cause: `KisOrderAdapter.fetch_trading_day()` delegated transport/HTTP retry to `_fetch_query_body()`, but a 200/JSON KIS payload with provider error, missing requested-date row, ambiguous rows, or invalid `opnd_yn` normalized to `None` after one request. `ObservedKRXCalendar` then cached that unavailable witness as current-day UNKNOWN, causing soak admission to fail despite the date being open.
- fix: moved the calendar witness onto a dedicated bounded loop using the adapter's existing `max_retries` and backoff. Both transient request failures and semantically unavailable payloads are retried. Only a built-in exact boolean from one requested-date `Y/N` row is accepted; exhaustion still returns `None` and fails closed. Order POST behavior is untouched.
- verification: `pytest -q tests/test_kis_order.py -k calendar_witness` => 4 passed; full `pytest -q` => 732 passed; live mock-only `bot soak preflight --campaign-id soak-20260828-20d-v1` => execution possible with `KRX_SESSION_OPEN` for 2026-08-31. Ruff is not installed in the project virtualenv, so no separate Ruff invocation was possible.
- files_changed: `trading_bot/kis_order.py`, `tests/test_kis_order.py`, `.planning/debug/soak-unknown-date-transient.md`.
