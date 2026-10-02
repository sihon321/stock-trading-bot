---
phase: 14-operator-dashboard-alerting
plan: "06"
subsystem: evidence
tags: [readonly, portfolio, attribution, history, worker-health, sanitization, tdd]
requires:
  - phase: 14-03
    provides: Pure saved replay/backtest contracts
  - phase: 14-04
    provides: Registered Shadow proof verification and typed unavailable results
  - phase: 14-05
    provides: Credential-free immutable registered resource settings
  - phase: 14-13
    provides: Pure independent owner schema declarations
provides:
  - Immutable scoped account/detail/history/worker/alert-source DTOs
  - Bounded read-only portfolio snapshots with historical last-success retention
  - KST half-open histories and sanitized fixed-field drilldowns
  - All-date broker/local unresolved subjects and positively proven freeze releases
  - Observed worker lifecycle/cadence reduction and bounded alert checkpoints
affects: [14-07, 14-09, 14-10, 14-11, 14-12]
tech-stack:
  added: []
  patterns: [owner-specific readonly transactions, exact snapshot selectors, immutable tuples, stream checkpoints]
key-files:
  created: [trading_bot/web_models.py, trading_bot/web_evidence.py, tests/test_web_evidence.py]
  modified: []
key-decisions:
  - "Registered scope supplies positive account/target authority; contradictory saved run attribution overrides it and yields UNKNOWN."
  - "Missing saved marks, worker expectation or recorded cadence remain UNKNOWN; querying never renews source observation time."
  - "Alert checkpoints track bounded stream content and continuation offsets; changed streams may repeat durable IDs, requiring consumer deduplication."
requirements-completed: [FUT-03, UI-01, UI-02, OPSV-01]
coverage:
  - id: D1
    description: Exact complete snapshot totals, nullable incomplete zeros, scope rejection and historical cache
    requirement: UI-01
    verification: [{kind: integration, ref: tests/test_web_evidence.py#account-snapshot-scope-cache, status: pass}]
    human_judgment: false
  - id: D2
    description: KST history pagination, sanitized durable drilldown and all-date 000660 risk
    requirement: UI-02
    verification: [{kind: integration, ref: tests/test_web_evidence.py#history-detail-unresolved-disclosure, status: pass}]
    human_judgment: false
  - id: D3
    description: Actual worker observations, strict stale boundary and readonly ordered alert facts
    requirement: OPSV-01
    verification: [{kind: integration, ref: tests/test_web_evidence.py#worker-freshness-watch-transition, status: pass}]
    human_judgment: false
duration: 36min
completed: 2026-10-02
status: complete
---

# Phase 14 Plan 06: Saved Operator Evidence Summary

**완전한 단일 계좌 스냅샷, KST 이력과 비밀값을 제거한 증거 상세, 날짜에 무관한 미해결 주문, 실제 수명주기로 판단하는 작업자 상태를 읽기 전용 불변 DTO로 제공합니다.**

## Accomplishments

- `ReadOnlyPortfolioRepository` validates phase11 owner metadata and exact required columns, opens `mode=ro`, enables `query_only`, and closes each independent bounded read transaction. It imports no mutable portfolio connector, trading Settings, lease manager, broker or live provider.
- Whole-account cash/total/holdings/orders/fills bind one complete snapshot and original observation/cycle IDs. Stored incomplete zero placeholders are nullable UNKNOWN. Missing mark evidence leaves unrealized valuation UNKNOWN. New incomplete attempts stay separately identified; complete historical observations and bounded cached last-success values keep their original time after failure.
- `OperatorEvidenceService` exposes registered resource status, overview, KST today/7/30/custom half-open histories, scope/period/snapshot-bound keyset cursors, record and evidence lookups. Histories default to 50 rows and cap at 100; each source scan caps at 10,000 rows and SQL work is bounded. Aggregate counts become UNKNOWN when attribution/query validation fails.
- Local intent, broker progression and saved broker snapshots retain distinct provenance. Run/observer/origin IDs and snapshot links remain available. Daily evaluation terminal action/confidence/reason and candidate rank/rejection are exposed only where recorded. Raw canonical prompt bytes are excluded from fetched evaluation SQL rows.
- All-date local/broker unresolved subjects and soak freezes survive routine date filters. Broken primary freeze links remain visible with UNKNOWN attribution; a release requires a matching saved determinate terminal comparison or ambiguity observation for the same campaign/ticker/intent. Source failure retains cached unresolved facts without claiming recovery.
- Evidence uses fixed field maps, bounded scalar text, 4,096 characters per text and a conservative total projection budget below 16KiB. API keys, bearer values, account numbers, webhook tokens, JWTs and control/bidi text are sanitized; prompt, exception, configuration, lease owner token and raw payload fields are absent.
- Workers join watch facts through `snapshot_id`, preserving outer cycle IDs separately from iteration cycles. Positive durable lifecycle establishes expectation; only recorded observation cadence can establish freshness. Equality at `max(180s, 3×cadence)` is FRESH, strictly later is STALE. STOPPED/NOT_EXPECTED and FAILED remain separate; lease age never renews actual observation age.

## Task Commits and Verification

1. **T1 source/account contracts:** RED `ed96241`; GREEN `d846284`. Initial RED: 5 expected failures. Focused account/snapshot/scope/missing/cache: **5 passed in 3.05s**.
2. **T2 histories/detail:** RED `70cd806`; synthetic NOT NULL fixture correction RED `2f7f268`; GREEN `d994056`. Corrected history RED failed on the absent history method. Focused history/detail/unresolved/disclosure/pagination: **5 passed in 2.51s**.
3. **T3 observed worker/alerts:** RED `07b30e5`; GREEN `a09ada5`. Initial RED: 6 expected failures. Focused worker/freshness/watch/transition: **6 passed in 2.96s**.

Final command:

`PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_web_evidence.py`

**16 passed in 7.19s.** `git diff --check` passed. Source bytes/schema/data comparisons cover successful account reads and alert observations; missing, unsupported-schema, bad-time, conflicting-target, broken-link and adversarial-secret paths are exercised. No tracked deletions or generated untracked files remain. Full regression is reserved for the parent wave boundary.

## Consumer Interfaces

```python
from trading_bot.web_evidence import OperatorEvidenceService, ReadOnlyPortfolioRepository
from trading_bot.web_models import ResourceScope, PeriodSelection

service = OperatorEvidenceService(web_settings, clock=aware_clock,
                                 shadow_proof_catalog=registered_shadow_proofs)
scope = ResourceScope(account_hash, "mock")  # optional resource_id narrows one registration
overview = service.overview(scope)
statuses = service.source_status()
period = PeriodSelection.for_days(aware_clock(), 7)
page = service.list_records("decisions", scope, period=period, limit=50)
next_page = service.list_records("decisions", scope, period, page.cursor, 50)
record = service.get_record(page.rows[0].resource_id, page.rows[0].record_id)
evidence = service.get_evidence(record.resource_id, record.record_id)
batch = service.observe_alert_sources(previous_cursor)
```

- `SourceEnvelope`: registered resource/schema owner/version, account/target/provenance, durable `source_observed_at`, independent `query_at`, completeness/query/freshness, age and safe diagnostic code. Saved JSON files with no durable observation timestamp keep that time UNKNOWN; file mtime is not substituted. Shadow without the separate registered proof catalog is unavailable.
- `EvidenceSelection`: stable `selection_id`, exact resource/kind/scope, `record_ids`, `snapshot_id`, `source_ids`, numerator/denominator. Account detail selection is shared by its exact constituents. Snapshot-backed history cursors reject a changed snapshot selection.
- `AccountDTO`: nullable cash/total/unrealized values, immutable holdings/orders/fills, snapshot ID, separate latest attempt ID/status and historical label.
- `EvidenceRecord`: `record_id`, kind, envelope, selection and immutable scalar `fields`; `.data` returns a read-only mapping. Kind aliases `HoldingDTO`, `RunDTO`, `DecisionDTO`, `OrderDTO`, `FillDTO` share this contract. Unsupported/invalid resource/kind/cursor selectors raise bounded `ValueError`; unavailable record reads raise `EvidenceUnavailable` with a stable code.
- `RecordPage`: `rows`, known `total` or null, selection ID, next cursor, source envelopes and independent `active_unresolved` order subjects. Kinds: runs, candidates, decisions, orders, holdings, broker_orders, fills, evaluations, evaluation_events, watch, transitions, transition_observations, transition_notifications, divergences, lease_events, notifications, freezes, campaigns, comparisons, soak_events and drills. No table/path parameter is accepted.
- `WorkerDTO`: stable resource worker ID, state/expectation/cadence, observation envelope, distinct lease timestamp, source IDs and snapshot ID. Production records currently omit durable cadence/start expectation in some manual paths, so those cases intentionally remain UNKNOWN.
- `AlertSourceBatch`: immutable ordered facts, workers, source statuses, query time and opaque registry-bound cursor. Batches cap at 100 facts; cursors cap at 64KiB. A stream content change restarts that stream's bounded continuation and can reemit existing durable IDs: **14-09 must deduplicate by original source/resource/record identity**. This handles timestamp collisions, backdated insertion and updated transition-state rows without treating missing records as recovery. No notification is sent by this service.
- `OverviewDTO.atomic_cross_store` is always false. Distinct owners remain independently observed transactions; web/observer services acquire no write capability over them.

## Deviations from Plan

**[Rule 1 - Bug] Replaced timestamp-only alert continuation with bounded stream checkpoints.** A later durable notification inserted with an older source timestamp could otherwise be skipped permanently. Stream content identities and continuation offsets now detect it; the synthetic late historical INSERT regression passes. Included in T3 GREEN `a09ada5`.

The first history fixture omitted required SQLite decision columns. The fixture was corrected and RED re-run before implementation; no production schema changed.

Planning state/roadmap/requirements updates and the full wave regression remain exclusively parent-owned, as instructed. This summary's requirement metadata records plan scope, not completion of all Phase 14 deliverables.

## Issues Encountered

Optional `python3 -m ruff check` could not run because ruff is not installed. No dependency installation was attempted. Syntax/import execution and whitespace checks passed through the focused suite and `git diff --check`.

## Known Stubs

None blocking this plan. Nullable marks, missing producer/model metadata, absent cadence/expectation, missing durable saved-file timestamps and unregistered Shadow proof are explicit unavailable/UNKNOWN evidence states, not synthesized values.

## User Setup Required

None. No owner database, actual password, KIS/LLM/Discord call, persistent server, order, freeze mutation or trading setting was accessed or changed.

## Self-Check: PASSED

The three created implementation/test files and this SUMMARY exist. Git confirms `ed96241`, `d846284`, `70cd806`, `2f7f268`, `d994056`, `07b30e5` and `a09ada5`. All owned focused tests passed; no tracked files were deleted.
