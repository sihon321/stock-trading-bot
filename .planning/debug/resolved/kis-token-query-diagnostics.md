---
status: resolved
trigger: "Fix KIS mock order-query false unavailability caused by per-process token issuance and loss of bounded transport diagnostics."
created: 2026-08-11
updated: 2026-08-11T02:00:00+09:00
---

## Symptoms

- Expected: Separate safe CLI commands reuse a still-valid KIS mock access token without needless issuance, and a failed GET records a bounded non-secret reason that distinguishes authentication, HTTP/provider, timeout, and parsing failures.
- Actual: A direct authenticated daily-order GET returned `rt_cd=0` and one order row, while a new process seconds later returned `AUTH_UNAVAILABLE`; soak reconciliation previously persisted only `QUERY_UNAVAILABLE`, hiding the actual transport cause.
- Error: `DAILY_QUERY_UNAVAILABLE|BALANCE_COMPLETE` during GET-only `soak resume`; immediate subsequent public query reproduced `AUTH_UNAVAILABLE` after a successful direct query in a separate process.
- Timeline: Observed on 2026-08-11 while reconciling KIS mock order `0000015678` for ticker `009830`.
- Reproduction: Run one process that obtains a KIS token and successfully performs the daily-order GET, then start another CLI process within seconds; separately force transport/HTTP failures through `_query_pages` and observe the generic `QUERY_UNAVAILABLE` reason.

## Current Focus

hypothesis: "The root cause is fixed and self-verified offline; live mock confirmation is needed to prove a token issued by one CLI process is accepted and reused by the next KIS GET workflow."
test: "Run two separate read-only mock CLI workflows close together and inspect only POST count/cache permissions and the bounded reconciliation reason—not cache contents or credentials."
expecting: "The first process may issue one token and creates the cache; the second process makes no token POST, completes its GET using the cached token, and any failure reports a category such as AUTH_UNAVAILABLE, QUERY_TIMEOUT, QUERY_TRANSPORT_ERROR, QUERY_HTTP_AUTH_ERROR, QUERY_HTTP_ERROR, PROVIDER_ERROR, or PARSE_ERROR."
next_action: "resolved"

## Evidence

- timestamp: 2026-08-11; direct GET returned `rt_cd=0`, KIS message `모의투자 조회가 완료되었습니다`, `output1` list with one row, and terminal continuation header `E`.
- timestamp: 2026-08-11; a fresh process invoking `query_daily_ccld_pages` seconds later returned `INCOMPLETE/AUTH_UNAVAILABLE` with zero pages and rows.
- timestamp: 2026-08-11; `KisTokenManager` stores the token only in `self._token`; no process-independent cache exists.
- timestamp: 2026-08-11; `_query_pages` catches `_TransientOrderQueryError` and persists only `QUERY_UNAVAILABLE`, discarding its already-bounded exception category.
- timestamp: 2026-08-11; production creates separate token managers in `_build_token_manager` and `_build_soak_adapter`; neither constructor provides a process-independent cache.
- timestamp: 2026-08-11; token expiry is represented only as a monotonic deadline, so safe cross-process reuse requires persisting a wall-clock deadline and reconstructing a local monotonic deadline.
- timestamp: 2026-08-11; `_fetch_query_page` already strips raw exception text to the exception class name and strips HTTP responses to a numeric status, so stable diagnostic categories can be propagated without retaining bodies, headers, credentials, or tokens.
- timestamp: 2026-08-11; the global shell has no `pytest` executable (`command not found`); testing must use the repository-managed environment.
- timestamp: 2026-08-11; repository baseline via `.venv/bin/pytest` is green: 30 focused auth/order tests passed.
- timestamp: 2026-08-11; new diagnostic regression is RED exactly at the catch boundary: timeout, transport, HTTP-auth, and HTTP failures all returned `QUERY_UNAVAILABLE`; provider and parse cases already returned their bounded categories.
- timestamp: 2026-08-11; new persistent-cache regression is RED at configuration construction (`KisAuthConfig` has no `cache_path`), independently confirming there is no cross-process reuse capability.
- timestamp: 2026-08-11; after the fix, all 11 exact new regressions pass: cross-manager zero-POST reuse, margin refresh, credential isolation, corrupt/unsafe cache refresh with 0600/0700 permissions, and six bounded GET diagnostic cases.
- timestamp: 2026-08-11; the first expanded-test command collected nothing because `tests/test_soak_compat.py` does not exist; this is a test-selection error, not a code failure.
- timestamp: 2026-08-11; corrected adjacent offline suite is green: 127 config, soak-config, auth, order, reconciliation, and CLI tests passed.
- timestamp: 2026-08-11; signed-cache tamper regression and all six query diagnostic cases pass (7 tests); a modified token with its old signature is rejected and refreshed.
- timestamp: 2026-08-11; whole-suite collection is independently blocked in `tests/test_soak_campaign.py` because concurrent `CandidateReportRow` now requires `reason_detail`; the failure does not import or exercise the changed KIS auth/query code.
- timestamp: 2026-08-11; all unaffected tests pass: 678 tests green with only `test_soak_campaign.py` ignored; `py_compile` and `git diff --check` pass, and offline tests created no repository token cache artifact.
- timestamp: 2026-08-11; downstream regression passes: a `QUERY_TIMEOUT` daily envelope remains `DAILY_QUERY_TIMEOUT|BALANCE_COMPLETE` in the reconciliation snapshot rather than collapsing to `QUERY_UNAVAILABLE`.
- timestamp: 2026-08-11; final adjacent verification is green: 129 tests passed; compilation and diff checks remain clean and no repository token-cache artifact was created.
- timestamp: 2026-08-11T02:25:02Z; operator-authorized first GET-only RESUME created `data/.kis-token-cache` as 0700 and token/lock files as 0600, completed the daily-order page, and preserved the bounded balance failure as `BALANCE_QUERY_TIMEOUT` rather than `QUERY_UNAVAILABLE`.
- timestamp: 2026-08-11T02:25:17Z; a second CLI process started seconds later reused the cached token, completed both daily-order and balance pages in about four seconds, and persisted a COMPLETE broker snapshot without `AUTH_UNAVAILABLE`.

## Eliminated

- hypothesis: "KIS mock daily-order inquiry is currently down."
  reason: "The authenticated endpoint returned `rt_cd=0` and one valid order row during the same investigation."

## Resolution

- root_cause: "`KisTokenManager` stores only a monotonic in-memory token, so every CLI process performs a new token POST and can hit KIS issuance throttling. Separately, `_query_pages` catches `_TransientOrderQueryError` but discards its normalized category, collapsing timeout, transport, and HTTP failures into `QUERY_UNAVAILABLE`."
- fix: "Added a signed credential-keyed process-independent token cache with persisted wall-clock expiry, Unix process locking, restrictive file/directory permissions, and safe stale/corrupt/unsafe fallback; configured both normal and soak CLI managers to share it. Added allowlisted timeout, transport, HTTP-auth, and HTTP reason codes to transient GET errors and preserved them in paged query envelopes."
- verification: "RED/GREEN confirmed on 12 cache/security and query-diagnostic cases plus downstream snapshot propagation; 129 adjacent tests passed, 678 unaffected tests passed with only the unrelated concurrently broken `test_soak_campaign.py` ignored; `py_compile` and `git diff --check` passed. Operator-authorized live GET-only verification confirmed restrictive cache permissions, bounded `QUERY_TIMEOUT` propagation, successful cross-process token reuse, and a subsequent COMPLETE snapshot without AUTH_UNAVAILABLE; no order, cancel, or modification POST was executed."
- files_changed: "trading_bot/kis_auth.py, trading_bot/config.py, trading_bot/soak_config.py, trading_bot/cli.py, trading_bot/kis_order.py, tests/test_kis_auth.py, tests/test_kis_order.py, tests/test_soak_reconcile.py"
