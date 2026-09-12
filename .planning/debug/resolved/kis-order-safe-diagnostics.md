---
status: resolved
trigger: "Preserve safe KIS order failure diagnostics and verify them with tests"
created: 2026-08-11
updated: 2026-08-11
---

## Symptoms

- Expected: ambiguous order evidence preserves enough bounded KIS diagnostics to distinguish timeout, HTTP failure, provider rejection, invalid JSON, and missing order ID without storing credentials or raw responses.
- Actual: every order-path failure was persisted only as `{"error_type":"KisOrderError"}`, so the exact cause of the v4 ambiguity could not be recovered.
- Error: run `f6c8e4070d3d41938fb1b2618eee0919`, intent `bbaf35f7-91c1-4bfd-b752-d653db76706a`, submission `10aec94a-cff5-4da5-beec-e75e8bf8f6fc` persisted only `KisOrderError`.
- Timeline: observed during the 2026-08-11 KIS mock soak run.
- Reproduction: make `place_order_cash` raise a bounded KIS order failure after `SUBMISSION_ATTEMPTED` and inspect the resulting `SUBMISSION_AMBIGUOUS.detail_json`.

## Current Focus

- hypothesis: confirmed; `KISBroker.place_order` discarded all structured failure context and stored only the exception class name.
- test: regression coverage exercises bounded diagnostic category, stage, HTTP status, `rt_cd`, and `msg_cd`, and excludes provider prose, response data, and credentials.
- expecting: complete.
- next_action: none.

## Evidence

- timestamp: 2026-08-11T13:00:00+09:00; audit event 28 records `SUBMISSION_AMBIGUOUS` with only `{"error_type":"KisOrderError"}`.
- timestamp: 2026-08-11T13:00:00+09:00; the exception occurred about 29 ms after `SUBMISSION_ATTEMPTED`, so a five-second order timeout is not established.
- timestamp: 2026-08-11T13:05:00+09:00; GET-only reconciliation separately persisted `DAILY_QUERY_TIMEOUT`, while balance later completed, proving the POST and query failures are distinct.
- timestamp: 2026-08-11T13:14:39+09:00; live GET-only RESUME again produced `DAILY_QUERY_TIMEOUT|BALANCE_COMPLETE`; no order POST or retry was made and the 009830 freeze remained UNKNOWN.
- timestamp: 2026-08-11T13:16:00+09:00; focused KIS/auth/broker tests passed (57), soak-adjacent tests passed (79), and the broad collection excluding the unrelated broken fixture passed (694).

## Resolution

- root_cause: "KisOrderError carried only human-readable text, while KISBroker persisted only the exception class. This erased whether failure occurred during hashkey acquisition or the order POST and erased bounded HTTP/provider response codes."
- fix: "KisOrderError now exposes an allowlisted scalar safe_diagnostics contract with failure category/stage plus optional HTTP status, rt_cd, and msg_cd. Order and hashkey paths classify their failures, and SUBMISSION_AMBIGUOUS evidence persists only those bounded fields alongside error_type. Provider prose, raw bodies, request data, and credentials remain excluded."
- verification: "4 new tests passed after failing before the implementation; 57 KIS/auth/broker tests, 79 soak-adjacent tests, and 694 broad tests excluding the unrelated collection-broken test_soak_campaign.py passed. compileall and git diff --check passed. Live GET-only RESUME made no order mutation and truthfully retained DAILY_QUERY_TIMEOUT|BALANCE_COMPLETE."
- files_changed: "trading_bot/kis_order.py, trading_bot/kis_broker.py, tests/test_kis_order.py, tests/test_kis_broker.py"
