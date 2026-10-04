---
phase: 15-unattended-scheduling-service-resilience
plan: "04"
subsystem: database
tags: [sqlite, dispatch, immutable-input, saved-evidence, read-only, offline-tests]
requires:
  - phase: 15-01
    provides: Immutable DailyDispatchEnvelope and explicit mock ServiceScope
  - phase: 15-03
    provides: Consumed DISPATCHED operational handoff contract
provides:
  - Owned phase11 portfolio v4 migration preserving primary audit version and historical facts
  - Immutable envelope and scoped one-shot daily dispatch with ACTIVE account authority
  - Conservative uncertain/expired/legacy recovery and terminal HOLD evidence
  - Pure exact v3/v4 capabilities and private-prompt-free saved reader projections
affects: [15-07, 15-08, 15-09, 15-10, 15-11, 15-13, 15-14]
tech-stack:
  added: []
  patterns: [rollbackable owned migration, immutable canonical envelope, immediate one-shot consumption, version-sensitive query-only capabilities]
key-files:
  created: []
  modified: [trading_bot/audit_models.py, trading_bot/portfolio_store.py, trading_bot/evidence_contracts.py, trading_bot/web_evidence.py, tests/test_portfolio_store.py, tests/test_evidence_contracts.py]
key-decisions:
  - "First committed canonical bytes and envelope win; the legacy date/ticker uniqueness remains a fail-closed collision across account scopes or unknown targets."
  - "Claim commits DISPATCHED and dispatched_at before transport; uncertain recovery cannot reset consumed dispatch authority."
  - "Every dispatch mutation and scoped recovery requires the actual ACTIVE MutationLease and current owner token in the same trading store."
  - "Saved readers choose exact pure v3/v4 contracts without migration or trading-owner imports; unknown target remains explicit saved uncertainty."
requirements-completed: []
coverage:
  - id: D1
    description: Immutable scoped one-shot dispatch and conservative owned migration/recovery
    requirement: AUTO-01
    verification:
      - kind: integration
        ref: tests/test_portfolio_store.py#test_scoped_concurrent_claim_has_one_winner_and_terminal_cannot_reset
        status: pass
      - kind: unit
        ref: tests/test_portfolio_store.py#test_legacy_attempts_never_replay_and_migration_preserves_old_facts
        status: pass
      - kind: unit
        ref: tests/test_portfolio_store.py#test_recovery_retains_never_dispatched_then_expires_and_unknown_never_replays
        status: pass
    human_judgment: false
  - id: D2
    description: Pure exact saved v3/v4 reader capabilities preserving source time, identity and confidentiality
    verification:
      - kind: integration
        ref: tests/test_evidence_contracts.py#test_saved_portfolio_reader_version_timestamp_and_private_envelope
        status: pass
      - kind: unit
        ref: tests/test_evidence_contracts.py#test_portfolio_supported_versions_have_exact_pure_contracts
        status: pass
      - kind: integration
        ref: tests/test_web_capabilities.py#test_fresh_supported_surface_and_each_source_owner_invariant
        status: pass
    human_judgment: false
duration: 12min
completed: 2026-10-04
status: complete
---

# Phase 15 Plan 04: Immutable Daily Dispatch and Saved Readers Summary

**phase11 v4의 최초 입력·envelope를 불변으로 저장하고 ACTIVE 계좌 소유자만 한 번 디스패치하도록 제한하며, v3/v4 저장 증거를 쓰기나 원본 프롬프트 노출 없이 읽는다.**

## Performance

- Recorded task interval: 2026-10-04T04:36:59Z–2026-10-04T04:49:03Z, approximately 12min. Initial context discovery preceded this interval.
- Tasks: 2/2. Implementation/test files: 6.

## Accomplishments

- `DailyEvaluationStatus` STARTED/FINALIZED와 기존 이벤트를 보존하고 `DailyDispatchState` 및 typed dispatch 이벤트를 추가했다. v1/v2/v3→v4와 새 DB는 phase11 metadata만 소유한다. `PRAGMA user_version`은 변경하지 않는다. 외부 owner/미지원 버전을 거부하며, 주입된 dispatch migration 실패는 DDL과 metadata를 함께 rollback한다. 기존 canonical bytes/hash/ID/event 순서와 snapshot/lease/transition 사실은 그대로 남는다.
- `daily_evaluation_dispatches`는 계획의 9개 컬럼을, `daily_dispatch_identities`는 evaluation/scope/target/date/ticker 유일성을 갖는다. 기존 date/ticker 유일성도 유지해 계좌·target 충돌이 기존 신호 재사용으로 이어지지 않는다. 과거 FINALIZED는 FINALIZED, 미완료 PROVIDER_ATTEMPT는 DISPATCHED_UNKNOWN, target/envelope 권한이 없는 미완료 평가는 BLOCKED_LEGACY이다. 현재 프롬프트를 재구성하지 않는다.
- 신규 `start_daily_evaluation(..., execution_target='mock', envelope=..., lease=...)`는 canonical bytes와 frozen envelope가 일치해야 하고 실제 ACTIVE 계좌 lease를 요구한다. 동일 identity 재호출은 첫 저장 input/envelope/provenance를 반환한다. 기존 인자 호출은 BLOCKED_LEGACY 증거만 남긴다. immutable triggers는 canonical input/envelope/identity 변경 및 소비된 dispatch reset/delete를 거부한다.
- `claim_daily_dispatch(conn, evaluation_id, lease, now, deadline)`는 동일 trading store의 실제 MutationLease·scope·현재 ACTIVE token을 검증하고 BEGIN IMMEDIATE 내부에서 재검증한다. 같은 KST 날짜, 저장 input 이후이며 deadline 전인 경우만 허용하며 deadline은 09:20을 넘지 못한다. UUID dispatch_id, DISPATCHED, aware ISO `dispatched_at`을 외부 작업 전 commit한다. 독립 reader에서 소비를 즉시 확인할 수 있다.
- `load_daily_dispatch`는 15-03 handoff가 요구한 dict 키를 제공한다. `finalize_daily_dispatch(..., lease, now, action, confidence, reason_code, unknown, execution_intent_id)`는 소비된 평가만 종료한다. `unknown=True`는 HOLD/0/LLM_UNAVAILABLE 및 DISPATCHED_UNKNOWN이다. `recover_daily_dispatches(..., lease, account_scope_hash, execution_target, trading_date_kst, now, deadline)`는 해당 scope/date만 처리한다. intact NEVER_DISPATCHED만 창 내 재개 가능하며, 만료된 입력은 EXPIRED_NEVER_DISPATCHED, 소비·legacy 불확실성은 terminal HOLD로 남아 재호출되지 않는다. compatibility `recover_started_evaluations`는 무권한 전역 변이를 거부한다.
- `evidence_contracts`는 PORTFOLIO_SCHEMA_VERSION=4, 지원 읽기 버전 {3,4}, 정확한 개별 maps와 기존 public alias를 제공한다. web reader는 실제 metadata에 따라 순수 capability를 선택한다. mode=ro/query_only, bounded row/identity, scope 검증과 기존 원본 시각을 유지한다. v4에서는 저장된 state/ID/envelope hash/target/timestamps만 공개한다. canonical bytes/envelope JSON/system prompt는 조회 SQL에서도 제외한다. target 부재는 명시적 unknown-target provenance이며 상충한 positive target은 SCOPE_CONFLICT이다.

## Task Commits

| Task | Stage | Commit | Verification |
|---|---|---|---|
| 1 | RED | 1cb5b08 | 13 expected failures / 4 existing passes |
| 1 | GREEN | ab0b945 | 19 portfolio tests passed |
| 2 | RED | a09db68 | v4 capability/version/reader failures established |
| 2 | GREEN | 12dcfa8 | 53 combined designated tests passed |

## Verification

- Task 1: `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_portfolio_store.py` → **19 passed in 0.17s**.
- Final designated command: `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_portfolio_store.py tests/test_evidence_contracts.py tests/test_web_evidence.py tests/test_web_capabilities.py` → **53 passed in 28.14s**.
- Covers exact 09:19:59/09:20, same-date refusal, first envelope/canonical bytes, same-store current authority, cross-scope/real-target refusal, one concurrent winner, commit-before-transport read-back, terminal no-reset, conservative legacy attempts, v1/v2/v3 migration/idempotence/rollback, exact retained v3 and migration-created v4 capabilities, target contradiction, immutable reader bytes, saved timestamps and private envelope exclusion. Existing designated fresh-interpreter checks cover saved report families/web/observer without writer/network/trading imports.
- `git diff --check` passed; normal Git hooks ran. No tracked deletion, generated untracked artifact or shared fixture edit was introduced.
- All journals and inputs were temporary synthetic offline fixtures. No package install/download, external calls, production DB access/migration, KIS/paid LLM/Discord, bootstrap/install/launchctl occurred. Full wave regression remains the parent executor's responsibility.

## Deviations from Plan

None in implementation scope. The planned fail-closed recovery change exposes the pre-existing integration seam below; its owner is 15-07. Legacy date/ticker uniqueness remains intentionally stricter than scoped uniqueness, as required by the plan, pending positive provenance for any safe future rebuild.

## Deferred Integration Issue

- Parent-requested focused reproduction: `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_phase11_cli.py::test_started_crash_is_finalized_unavailable_and_never_calls_provider` → **1 failed in 0.50s**. `cli.py:1660` calls `recover_started_evaluations(conn)` before acquiring account authority. The new required contract raises `RuntimeError: scoped active owner required for evaluation recovery`. No provider call occurs. 15-07 must move/wire scoped recovery after account authority and frozen one-shot dispatch, updating the existing CLI recovery expectation. This file is outside 15-04 ownership and was left unchanged; the issue was reported to the parent before completion. It does not imply full Phase 15 integration passes.

## Known Stubs

None preventing this plan's owned dispatch/reader goal. Null legacy target/envelope/dispatch ID represents missing historical authority and cannot authorize replay. Null new unconsumed dispatch ID/time is an explicit NEVER_DISPATCHED fact. CLI one-shot integration is the subsequent 15-07 deliverable, tracked above.

## External Activation Blockers

- Both Phase 09-08 task 1/task 2 approvals remain absent; unattended mutation is closed.
- 000660 remains frozen until same-subject determinate terminal broker evidence. No freeze facts were changed.
- Real-money dispatch/service remains refused; Phase 16 promotion is a separate deliberate gate.
- Actual installation/login/wake/private-device and authenticated elapsed-day acceptance remain unperformed. Fixtures do not grant production approval.
- AUTO-01/AUTO-02/FUT-04 remain pending for subsequent plans and complete phase verification; requirements-completed is empty.

## Next Plan Readiness

15-07 can consume `load_daily_dispatch`/`claim_daily_dispatch` dictionaries directly, hand the committed DISPATCHED facts to `ServiceJournal.prepare_provider_admission`, and load the frozen envelope through the trading owner. It must bind manual CLI recovery to current scoped authority and never convert UNKNOWN/suppressed/expired/legacy states back to NEVER_DISPATCHED.

## Self-Check: PASSED

- All six declared implementation/test files and this canonical SUMMARY exist.
- 1cb5b08, ab0b945, a09db68 and 12dcfa8 were verified as actual Git commit objects.
- Final designated suite passed. Stub/threat/deletion checks found no unimplemented owned goal, new unmodeled endpoint or unexpected deletion.
- External acceptance and the reported CLI integration test remain explicitly separate from the completed owned checks.
