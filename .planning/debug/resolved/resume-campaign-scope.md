---
status: resolved
trigger: "Fix soak resume importing unresolved orders from prior campaigns and querying them with an incorrect current-day-only window, which irreversibly failed a new campaign."
created: 2026-08-11
updated: 2026-08-11T11:37:00+09:00
---

## Symptoms

- Expected: `soak resume --campaign-id X` reconciles only intents durably attributed to campaign X, uses a broker query window containing each origin trading date, and never latches X because an unrelated prior campaign order is absent from a current-day snapshot.
- Actual: GET-only RESUME for `soak-20260811-20d-v3` selected prior campaign `v1` accepted intent `1d93eac8-e736-4160-806b-71eb3ef12f25` for ticker `017900`, queried only 2026-08-11, classified the absent 2026-08-10 order as MISMATCHED, and irreversibly latched v3 with `D09_BROKER_TRUTH_DISAGREEMENT`.
- Error: comparison codes `ORDER_NOT_FOUND|ORDER_NOT_FOUND|ORDER_NOT_FOUND|ORDER_NOT_FOUND|HOLDING_UNKNOWN|AVAILABLE_CASH_UNKNOWN` followed by `SAFETY_FAILURE_LATCHED` for `017900`.
- Timeline: Reproduced on 2026-08-11 during human verification of the process-independent token cache.
- Reproduction: Keep an accepted-unresolved intent from campaign A whose origin run date precedes today, start campaign B, then run B's RESUME with a complete current-day-only daily-order snapshot.

## Current Focus

hypothesis: "Confirmed and fixed: RESUME must select only append-only campaign-attributed intents and query a window containing every selected origin trading date."
test: "Await operator/orchestrator confirmation after offline focused and broad regression verification."
expecting: "A real resume for a fresh campaign does not import prior-campaign intents and does not latch from an older same-campaign order omitted by a current-day-only query."
next_action: "resolved"

## Evidence

- timestamp: 2026-08-11T02:25:17Z; v3 RESUME persisted COMPLETE daily/balance broker snapshot after successful cross-process token reuse.
- timestamp: 2026-08-11T02:25:17Z; current-campaign intent `009830` became terminal MATCHED and its REMAINING_ORDER freeze was safely released.
- timestamp: 2026-08-11T02:25:17Z; the same RESUME compared prior v1 intent `017900` under v3, returned MISMATCHED/ORDER_NOT_FOUND, and latched v3 as FAILED.
- timestamp: 2026-08-11; `_build_soak_runtime.reconcile` RESUME selection reads unresolved histories from all primary `order_events`; `collect_broker_snapshot` receives `SnapshotWindow(today, today)`.
- timestamp: 2026-08-11; knowledge-base scan found no entry with two-keyword overlap for the cross-campaign/current-day-window symptom, so no known-pattern shortcut applies.
- timestamp: 2026-08-11T11:32:43+09:00; `reconcile(RESUME)` groups every unresolved primary `order_events` intent and supplies no campaign predicate, directly confirming the cross-campaign selection mechanism.
- timestamp: 2026-08-11T11:32:43+09:00; ordinary KIS order events do not carry campaign ID, while append-only `soak_events` already supports the full `(campaign_id, run_id, ticker, order_intent_id)` attribution tuple.
- timestamp: 2026-08-11T11:32:43+09:00; primary `runs.trading_date_kst` durably records the origin trading date, but RESUME constructs `SnapshotWindow(today, today)` regardless of selected origins.
- timestamp: 2026-08-11T11:32:43+09:00; global preflight protection is independent: unresolved-order scanning uses the primary audit globally and execution reads all active freezes without a campaign predicate, so narrowing RESUME attribution need not weaken the global block.
- timestamp: 2026-08-11T11:37:00+09:00; `uv` is not installed in this workspace shell, so the first focused-test invocation did not execute any test or mutate application state.
- timestamp: 2026-08-11T11:37:00+09:00; the focused offline regression fails red on `result.complete is True`: campaign B imported campaign A's unresolved intent and treated its broker absence as non-complete/mismatched before the expected campaign-scoped result.
- timestamp: 2026-08-11T11:37:00+09:00; after the fix, the focused two-campaign regression and both accepted-unresolved resume variants pass (3 tests): only campaign B is compared, its window begins at 2026-08-09, attribution is append-only, and no POST path is invoked.
- timestamp: 2026-08-11T11:37:00+09:00; the repository virtualenv does not contain Ruff, so lint verification must use available syntax/tests plus manual formatting inspection.
- timestamp: 2026-08-11T11:37:00+09:00; 61 focused offline tests pass across soak CLI, global preflight, and reconciliation, including accepted-unresolved UNKNOWN freeze retention and terminal same-subject release.
- timestamp: 2026-08-11T11:37:00+09:00; 681 offline tests pass when excluding `tests/test_soak_campaign.py`; the full suite is independently blocked during collection by an existing concurrent reporting change (`CandidateReportRow.reason_detail` missing in that test factory), outside this defect's files.
- timestamp: 2026-08-11T11:37:00+09:00; changed Python files compile successfully and `git diff --check` reports no whitespace errors.
- timestamp: 2026-08-11T02:43:19Z; operator-authorized GET-only RESUME on failed v3 selected no unattributed historic intent, created no new comparison or D09 event for prior v1 order `017900`, and preserved the independent bounded failure as `DAILY_QUERY_TIMEOUT|BALANCE_COMPLETE`.

## Eliminated

- hypothesis: "The new v3 order caused the safety latch."
  reason: "The v3 order `009830` was MATCHED terminal and released; the latch event explicitly references prior v1 ticker `017900` and its intent ID."

## Resolution

- root_cause: "`reconcile(RESUME)` selected unresolved primary order histories globally, with no durable campaign ownership predicate, then queried every selected order using `SnapshotWindow(today,today)` instead of the origin runs' `trading_date_kst`; an unrelated older intent was consequently compared as absent under the new campaign and triggered its irreversible safety latch."
- fix: "Persist `ORDER_INTENT_ATTRIBUTED` in append-only `soak_events` when an `INTENT_CREATED` event is emitted, restrict RESUME candidates to the requested campaign's attributed intent IDs, and derive the GET-only daily-order window from each selected intent's primary `runs.trading_date_kst`; missing/contradictory dates now fail closed before comparison."
- verification: "Focused red-to-green regression proves campaign B compares only its own intent, queries 2026-08-09 through the current date, remains ACTIVE, records intent attribution, and never invokes POST. Missing origin dates fail closed. 61 focused tests and 681 broader offline tests pass; full-suite collection has one unrelated concurrent reporting-fixture error. Live GET-only verification on v3 created no comparison or latch for the prior v1 order, confirming campaign scoping without any order mutation."
- files_changed: ["trading_bot/cli.py", "tests/test_soak_cli.py", ".planning/debug/resume-campaign-scope.md"]
