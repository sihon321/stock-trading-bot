---
phase: 15-unattended-scheduling-service-resilience
plan: "01"
subsystem: infra
tags: [service, pydantic, safety, immutable-evidence, offline, multiprocessing]
requires:
  - phase: 11
    provides: Durable daily identity and account mutation exclusion contracts
  - phase: 14
    provides: Protected settings/path roles and owned alert contracts/store
provides:
  - Immutable scope, logical job, control, dispatch, approval, session and expectation models
  - Disabled-by-default mock-only protected service registration with fixed timing contracts
  - Shared offline clocks, temporary topology, synthetic approval/source/alert fixtures and spawn crash barriers
affects: [15-02, 15-03, 15-04, 15-05, 15-06, 15-07, 15-10, 15-11, 15-13, 15-14]
tech-stack:
  added: []
  patterns: [Frozen extra-forbid nested tuples, Explicit protected JSON registration, Durable actual-entry counters, Spawn-safe crash barriers]
key-files:
  created: [trading_bot/service_models.py, trading_bot/service_config.py, tests/service_fixtures.py, tests/test_service_contracts.py]
  modified: []
key-decisions:
  - "ControlRequest scope is an InstallationScope containing every registered mock account; it has no trading date or process identity."
  - "Nested approval/source evidence uses immutable typed tuples; missing checkpoints remain representable but cannot establish acceptance."
  - "Protected service writable roots remain outside existing data journal roots and are distinct from control/lock roots."
  - "Requirement completion remains pending: this plan proves foundational contracts, not the entire Phase 15 behavior."
patterns-established:
  - "ServiceContract and ServiceSettings copies validate updates instead of inheriting unchecked Pydantic model_copy behavior."
  - "ProviderCallAdmission always restores_dispatch_authority=False, including SUPPRESSED_NO_CALL."
  - "All new service fixture consumers import tests/service_fixtures.py; global conftest is unchanged."
requirements-completed: []
coverage:
  - id: D1
    description: Strict immutable logical identities, operational controls, provenance and consumed dispatch semantics
    requirement: AUTO-01
    verification:
      - kind: unit
        ref: tests/test_service_contracts.py
        status: pass
    human_judgment: false
  - id: D2
    description: Disabled mock-only settings and protected path/timeout registration contracts
    requirement: FUT-04
    verification:
      - kind: unit
        ref: tests/test_service_contracts.py#test_defaults_and_every_fixed_timeout
        status: pass
    human_judgment: false
  - id: D3
    description: Offline independent clocks, source/login/alert fixtures and deterministic crash barriers
    requirement: AUTO-02
    verification:
      - kind: integration
        ref: tests/test_service_contracts.py#test_fixture_child_crash_barriers_leave_durable_facts_and_no_process
        status: pass
      - kind: integration
        ref: tests/test_service_contracts.py#test_fixture_alert_owner_uses_only_temporary_store
        status: pass
    human_judgment: false
duration: 15min
completed: 2026-10-04
status: complete
---

# Phase 15 Plan 01: Shared Service Contracts and Offline Fixtures Summary

**엄격한 불변 서비스 증거, DISABLED/mock 전용 보호 설정, 전송 진입 기록과 12개 spawn 중단 장벽을 제공했습니다.**

## Performance

- Started: 2026-10-04T03:05:00Z
- Completed: 2026-10-04T03:20:00Z
- Duration: approximately 15 minutes
- Tasks: 2/2
- Implementation/test files: 4

## Accomplishments

- `ServiceScope`, `LogicalJobKey`, `ServiceAttempt`, `ServiceJobState`, `ControlAction`, `ControlMode`, `ControlRequest`, `AppliedControl`, `DailyDispatchEnvelope`, `AcceptanceReceipt`, `SessionEvidence`, `OwnerLoginEvidence`, `ExpectationInputs`, `ServiceExpectation`, `ProviderCallAdmission`을 추가했습니다. 논리 작업 ID는 scope/date/kind에서만 유도하며 generation/attempt는 별도 모델입니다.
- 모든 증거 모델은 frozen/extra-forbid/hide-input-in-errors이며 aware timestamp를 요구합니다. 등록 scope와 제어의 installation scope 불일치, 잘못된 세션 날짜·경계, 출처 누락, 미래 유효시각, 임의 요청 필드를 거부합니다. OBSERVER_DERIVED와 RUNTIME_OBSERVED는 명시적 producer_kind로 구분합니다.
- exact prompt bytes/digest와 system/schema/provider/model/temperature/version을 고정합니다. source/checkpoint 증거는 불변 중첩 모델+tuple이고, 승인 checkpoint 이름은 정확히 `09-08 task 1` / `09-08 task 2`입니다. receipt shape와 실제 현재 승인 권한은 별개입니다.
- `ServiceSettings`는 BOT_SERVICE_ prefix, init/env-only, env_file=None, DISABLED/service_enabled=false 기본값과 mock 고정 target을 사용합니다. 실행 설정·브로커·LLM 구성은 import/생성하지 않습니다. 명시적 `load_service_settings`는 bounded owner-protected JSON만 읽습니다. 설정은 secrets 대신 고정 paths/scopes만 포함합니다.
- 고정값 전체를 검증합니다: risk 60s, provider 90s, account work 45s, POST 10s, control lock 1s, provider admission 1s, restart window 600s, restart 최대 3회, shutdown 30s, worker stale 120s. no-link/hardlink checks와 root overlap 거부를 적용했습니다.
- `FakeServiceClock`는 aware UTC/KST wall과 독립 monotonic을 제공합니다. holiday/UNKNOWN/10:00 delayed session, confirmed/absent/UNKNOWN GUI login, observer-only midnight progression, 실패하는 source reader, SYNTHETIC ApprovalBundle, single-shot provider/broker/notification counters를 제공합니다.
- `SpawnedCrashBarrier`는 INPUT_COMMITTED, DISPATCHED, ACCOUNT_RECONCILED, ACCOUNT_RELEASED, CHILD_STARTED, PROVIDER_ADMISSION_PREPARED, BEFORE_TRANSPORT_ENTRY, TRANSPORT_ENTERED, RESPONSE_RECEIVED, SIGNAL_FINALIZED, SUBMISSION_ATTEMPTED, POST_RETURNED를 검사합니다. actual transport entry에서만 counter를 fsync하고 admission lock 아래 진입을 acknowledge합니다. 응답 대기는 잠금 해제 후 진행합니다.
- pending-CRITICAL/outbox/reminder fixture는 실제 Phase 14 owner 모델을 사용합니다. `temporary_pending_critical_store`는 기존 `AlertStore.initialize/observe`를 임시 경로에서만 호출합니다. 아직 존재하지 않는 service/control schema APIs는 만들거나 호출하지 않습니다.

## Task Commits

| Task | Stage | Commit | Outcome |
|---|---|---|---|
| 1 | RED | 0a6c537 | 11 expected failures: new contract modules absent |
| 1 | GREEN | 42f2660 | 15 contract/settings tests passed |
| 2 | RED | 7d73f3a | 18 expected fixture failures; existing 15 passed |
| 2 | GREEN | 79bf10f | 34 tests passed, including 12 spawn barriers and real temporary alert-owner fixtures |
| 1 follow-up | Safety fix | ce9caa0 | Unchecked settings-copy updates rejected; final 34 passed |

## Verification

- Required command: `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_service_contracts.py` → **34 passed in 2.87s**, no warnings.
- `git diff --check` passed. No unexpected tracked deletions or generated untracked artifacts.
- SDK/HTTP/socket/process tripwires were exercised with no real external calls. Temporary alert migration uses only the existing owner migrator on tmp_path. No production SQLite opens/migrations, installs/downloads, service installation, launchctl execution, KIS/Discord/paid-provider calls occurred.
- Tests show exact-date rollover, independently reversed wall/advancing monotonic clocks, durable crash facts, child termination cleanup, zero call counters before entry, response isolation from admission locks, suppressed admission retaining consumed authority, hidden validation inputs, protected paths and fixed defaults.
- No full Phase 15 runtime, macOS login/wake, real device, authenticated KIS, elapsed-day or production activation acceptance is claimed.

## Files Created/Modified

- `trading_bot/service_models.py`: shared contracts and allowlisted states, immutable nested evidence and identities.
- `trading_bot/service_config.py`: protected credential-free registration, explicit load, topology and fixed bounds.
- `tests/service_fixtures.py`: sole Phase 15 shared fixture owner; clocks, synthetic evidence, no-external tripwires, real temporary alert owner and spawn barriers.
- `tests/test_service_contracts.py`: contract/settings/fixture behavioral proofs.

## Decisions Made

- The installation-global control domain explicitly contains all registered scopes, without day/generation fields. Subsequent control writers/readers must use this domain.
- SessionEligibility is ELIGIBLE/HOLIDAY/UNKNOWN. Session bounds are aware datetimes on the exact KST date; unconfirmed sessions carry no trading bounds. Expectation states are EXPECTED/NOT_EXPECTED/UNKNOWN.
- Approval/source structures are `CheckpointApproval` / `SourceHash` tuples rather than mutable mappings. Incomplete receipts can be saved; completeness alone never proves authenticity.
- Initial AppliedControl revision 0 has request_id=None; later revisions require a request identity. Invocation-start evidence is mandatory for IN_FLIGHT/FINISHED and forbidden for PREPARED/SUPPRESSED_NO_CALL.
- Fixed writable defaults are `service-data/journal`, `service-data/control`, `service-data/locks`, separate from existing `data` evidence roots. Disabled missing source paths remain reserved; enabled registrations require protected source files.
- Installed Pydantic behavior was checked against its [official model documentation](https://docs.pydantic.dev/latest/concepts/models/) and [settings documentation](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) after Context7 MCP/CLI proved unavailable. No dependency changes were made.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Validate copied settings updates**
- Found during final Task 1 safety review.
- Pydantic's unchecked model_copy update could bypass mock-only target and fixed timeout validation on copied settings.
- Override model_copy with full constructor validation and test invalid target/cadence copy updates.
- Files: service_config.py, test_service_contracts.py.
- Commit: ce9caa0. Final focused verification: 34 passed.

### Execution tracking adjustment

- Per orchestrator instruction, FUT-04/AUTO-01/AUTO-02 completion is deferred to later implementation and final phase verification. `requirements-completed` remains empty; coverage records only this plan's verified foundation contribution. REQUIREMENTS.md is not marked complete from contract-only proofs.
- RED test failures arose from intentionally absent new modules before implementation; no collection/syntax failures. The behavioral rejection cases were then exercised in GREEN. Both tasks retain separate RED/GREEN commits.
- [Rule 3 - Blocking] Installed GSD state handlers require named flags instead of the supplied positional examples. After inspecting registered CLI handlers, metrics/decisions/session were successfully recorded with --phase/--plan/--duration, --summary and --stopped-at/--resume-file. No raw state overwrite was used. SDK aggregate progress retains a legacy 31-plan denominator (97%); actual Phase 15 ROADMAP progress is 1/14 In Progress.

## Known Stubs

None preventing this plan's goal. Initial empty registered scopes/evidence IDs and nullable absent/UNKNOWN bounds are deliberate fail-closed contracts, not fabricated authority. Fixture content is intentionally SYNTHETIC and does not substitute for production configuration or approval.

## External Activation Blockers

- Both Phase 09-08 task 1 and task 2 human approvals remain absent. No unattended trading activation is granted.
- Ticker 000660 retains its unresolved freeze pending same-subject determinate terminal broker evidence.
- Real-money promotion remains Phase 16's separate deliberate gated step.
- Actual protected installation, owner-GUI/login/wake supervision, reviewed exact-date exchange sessions, private phone access and authenticated acceptance remain future external work.

## Next Plan Readiness

15-02 can implement exact-date protected session loading against these contracts. Subsequent plans can consume ServiceSettings and shared fixtures without adding credentials to observer/web paths or inferring approvals. Pure fixture schemas do not confer production authority.

## Self-Check: PASSED

- Four implementation/test files and SUMMARY.md exist.
- All five recorded task/fix commits resolve to actual Git commits.
- Required focused suite passed; no external activation or requirement completion is inferred.
