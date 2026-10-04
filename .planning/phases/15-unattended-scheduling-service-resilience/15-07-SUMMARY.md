---
phase: 15-unattended-scheduling-service-resilience
plan: "07"
subsystem: execution
tags: [provider, httpx, sqlite, flock, one-shot, offline-tests]
requires:
  - phase: 15-02
    provides: Installation-global pending and applied operational controls
  - phase: 15-03
    provides: Protected operational journal, immutable universe and consumed admission writer
  - phase: 15-04
    provides: Scoped ACTIVE-owner dispatch claim, immutable envelope and conservative recovery
  - phase: 15-05
    provides: Protected exact-date reviewed session evidence
provides:
  - Stored-envelope SDK calls with disabled SDK, HTTP and outer retries
  - One-use actual synchronous transport-entry acknowledgement under global admission lock
  - Protected manual daily topology, consumed dispatch orchestration and full saved-signal reuse
affects: [15-06, 15-08, 15-09, 15-14]
tech-stack:
  added: []
  patterns: [concrete synchronous transport entry, bounded entry guard, immutable consumed identity, fail-closed unsupported adapter]
key-files:
  created: [tests/test_daily_dispatch.py]
  modified: [trading_bot/llm_provider.py, trading_bot/cli.py, trading_bot/service_store.py, trading_bot/portfolio_store.py, tests/test_phase11_cli.py, tests/test_portfolio_store.py]
key-decisions:
  - "Daily recovery requires actual exclusive ACTIVE scoped account ownership; a saved finalized signal grants no current trading authority."
  - "Global admission flock orders accepted controls against actual concrete HTTP/Popen entry; response waits begin after acknowledgement releases the flock."
  - "CLI configuration flags are not positive retry capability proof: unverified actual Codex execution is suppressed without a subprocess."
requirements-completed: []
duration: 22min
completed: 2026-10-04
status: complete
---

# Phase 15 Plan 07: Frozen Single-Shot Daily Dispatch Summary

**첫 저장 envelope의 provider 호출을 한 번만 소비하고, 실제 전송 진입에서 현재 session·시간·accepted/applied controls를 검증하며 불확실한 결과를 영속 HOLD/UNKNOWN으로 보존한다.**

## Performance

- 약 22분: 컨텍스트 확인부터 최종 구현 커밋까지. 첫 RED 커밋은 05:12 UTC, 마지막 GREEN 커밋은 05:29 UTC이다.
- 작업 2/2, 변경 파일 7개. 패키지 설치·다운로드·네트워크·실제 provider/KIS/Discord·production DB 접근·launchctl 수행 없음.

## Accomplishments

- `ClaudeLLMProvider`, `OpenAILLMProvider`, `CodexCLIProvider`에 `generate_signal_from_envelope` 경계를 추가했다. envelope와 canonical prompt hash, frozen provider/schema identity를 검증하고 현재 context를 다시 render하지 않는다. SDK request는 저장된 prompt/system/model/temperature와 동일한 TradeSignal schema를 사용한다. generic `generate_signal`은 기존 계약을 유지한다.
- `build_single_shot_llm_provider`는 OpenAI/Anthropic 생성자에 `max_retries=0`, `timeout=90`과 검증된 synchronous HTTP transport를 전달한다. HTTP transport retries도 0이며 redirect follow와 daily outer retry loop는 없다. 임의 주입 SDK와 지원 여부가 확인되지 않은 transport는 fail closed이다. SDK timeout/reset/invalid response에서 fake 실제 HTTP attempt는 각각 한 번이다.
- `ProviderDispatchAdmission`은 consumed identity/scope/date/envelope, control/session readers, clock, 좁은 writer, global admission lock만 받는다. broker/계정 lease/거래 설정 loader/거래 journal writer를 받지 않는다. 하나의 `TransportEntryAck`는 같은 실행 thread에서만 한 번 사용되며 scope/date, 09:10 ≤ 현재시각 < 09:20, 긍정적 continuous session의 전체 fingerprint, applied 및 accepted pending PAUSE/KILL을 검증한다.
- SDK의 `_SingleShotTransport`는 admission flock을 보유한 채 concrete `_AcknowledgedHTTPTransport.handle_request`에 진입한다. 해당 실제 transport entry에서 ACK를 수행하고 바로 flock을 해제한 후 network/response를 기다린다. 검증·저장·entry synchronization은 최대 1초 budget이며 90초 응답 wait는 flock/SQLite transaction 밖이다. 이후 accepted KILL은 이미 진입한 호출을 회수하지 않고 후속 작업의 control truth가 된다.
- 좁은 `ProviderAdmissionWriter.read_prepared/enter_transport(check)`를 추가했다. 동일 PREPARED 행만 검사하며 guarded update 중 변경은 rollback한다. commit 이후 guard가 거부하면 입증된 무호출을 `SUPPRESSED_NO_CALL`과 NULL invocation timestamp로 기록한다. terminal row를 PREPARED로 되돌릴 수 없고 새로운 claim/control/job authority도 없다. 저장 실패는 호출을 허용하지 않으며 consumed portfolio claim은 parent recovery에서 UNKNOWN으로 남는다.
- Codex의 지원된 테스트 adapter는 Popen creation을 flock 안에서 단 한 번 수행한 뒤 ACK를 해제하고 `communicate(timeout=90)`를 밖에서 기다린다. 로컬 binary symlink는 `/opt/homebrew/Caskroom/codex/0.144.6/codex-aarch64-apple-darwin`이었다. 내부 request/stream retry=0 설정 적용을 긍정적으로 입증할 로컬 schema/source/docs 증거를 확보하지 못했으므로 **actual Codex 기본 adapter에는 durable daily 호출 권한이 없다**. config flag 문자열만으로 지원을 주장하지 않으며 명시적으로 검증된 injected adapter만 테스트했다. generic 기존 CLI 경로의 호환성은 유지한다.
- 수동 `bot run --service-config` 및 `BOT_SERVICE_CONFIG`를 보호된 등록 topology와 `DailyDispatchRuntime`에 연결했다. 기존 owner control setup이 있어야 하며 RUNNING을 합성하지 않는다. 등록된 mock scope의 첫 held-first universe를 service journal에 보존하고 같은 날짜의 saved universe를 재사용한다.
- pre-lease `recover_started_evaluations(conn)`를 제거했다. 실제 ACTIVE owner, scope/target/date/deadline를 갖춘 호출만 daily recovery를 수행한다. 첫 저장 envelope와 identity/canonical bytes를 다시 검증하며 legacy/target/scope/schema mismatch는 blocked HOLD로 처리한다. claim 이후 provider construction 및 transport entry에서 변경된 deadline/session/control은 재호출 없이 소비된 unavailable/unknown으로 finalization한다.
- finalized signal은 provider construction 없이 `_FinalSignalProvider`로 재사용한다. `decision/confidence/reason` 전체 동등성을 보존하도록 기존 event detail에 검증된 bounded reason을 저장한다. 누락된 saved reason은 HOLD이다. deterministic evaluation-derived intent ID를 저장하고 lease-guarded broker에 전달한다. 이미 진입한 호출은 09:20 이후에도 bounded response와 signal evidence를 finalize하지만 새 sibling provider 호출은 하지 않는다.

## Task Commits

| Task | Stage | Commit | Verification |
|---|---|---|---|
| 1 | RED | c5ba90b | 새 admission/builder API 부재로 13개 expected failures |
| 1 | GREEN | cb664fd | daily_dispatch + llm_provider + service_store, 71 passed |
| 2 | RED | e5232f1 | 새 DailyDispatchRuntime API 부재로 7개 expected failures |
| 2 | GREEN | c2035b2 | 지정 5개 test modules, 103 passed |

## Verification

실제 최종 명령:

`PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_daily_dispatch.py tests/test_phase11_cli.py tests/test_portfolio_store.py tests/test_llm_provider.py tests/test_service_store.py`

**103 passed in 4.95s.** `git diff --check`도 통과했다. 모든 stores는 temp/injected fixtures이며 `tests/service_fixtures.py`는 변경하지 않았다.

검증 범위: SDK 중첩 retry 설정/attempt cardinality, frozen bytes, refused/invalid response와 실패 안전성, current cutoff/date/session fingerprint/control 변화, 저장 transaction 및 commit gap, entry 안의 cutoff 변화, lock availability during slow response, accepted KILL after entry, Codex 한 번의 Popen 및 unverified capability refusal, 실제 ACTIVE lease recovery, 첫 입력 변경 후 재사용, 전체 signal 동등성, consumed crash UNKNOWN, construction 중 cutoff suppression, entered response의 deadline 이후 finalization과 새 ticker expiry.

실제 service crash supervision, production adapter paid call, Mac sleep/wake, 외부 기기 또는 macOS 설치를 검증했다고 주장하지 않는다. 부모 orchestrator가 phase-wide regression과 independent verification을 수행한다.

## Deviations from Plan

### Execution Order

15-07은 원래 wave 3이지만 선언된 02/03/04/05 dependencies 완료 뒤 15-06보다 먼저 실행했다. 15-04의 엄격한 recovery API가 기존 CLI의 pre-lease global recovery 호출을 거부하므로 부모가 dependency-ready 통합 수정을 지정했다. 임시 authority bypass 없이 07 전체 구현으로 해결했다. 06은 계속 미완료이며 GSD Current Plan은 시작 시 6이었다. 등록 handler의 순차 advance 효과를 부모에게 보고하고 부모가 earliest pending 06 위치를 복원한다.

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] Narrow writer의 저장/entry gap 검증**
- 작업 1에서 기존 writer가 bound PREPARED read-back과 post-persistence guard를 제공하지 않는 것을 확인했다.
- 부모가 `trading_bot/service_store.py`의 최소 확장을 승인했다. guarded transition과 true no-call suppression을 추가하고 temp-store gap tests로 검증했다.
- Commit: cb664fd.

**2. [Rule 1 - Bug] Finalized signal reason 유실**
- 작업 2에서 기존 scoped finalize API가 `detail_json='{}'`로 reason을 버려 saved-signal 동등성을 깨는 것을 확인했다.
- 부모가 `trading_bot/portfolio_store.py`, `tests/test_portfolio_store.py`의 최소 확장을 승인했다. strict parser로 검증한 bounded reason을 기존 event detail에 보존하고 전체 signal 동등성 및 빈 reason 거부를 검증했다. schema/authority 변경은 없다.
- Commit: c2035b2.

## Integration Boundaries and Gates

- provider wait와 반복 pass 사이의 **account lease 해제/재획득은 15-09 범위**이다. 이 계획의 수동 daily orchestration은 current account owner로 finalization을 검증하지만 아직 계정 lease를 provider response 동안 내려놓지 않는다. shared *admission* flock은 entry ACK 즉시 해제한다. 이 두 lock을 같은 것으로 주장하지 않는다.
- control BUY/KILL의 broker POST 경계, risk worker progress, scheduler supervision은 15-08/15-09 후속 통합과 전체 검증 대상이다. 이 계획의 slow-response 증거는 admission lock availability/accepted KILL이며 실제 risk POST progress를 주장하지 않는다.
- 09-08 task 1/task 2 approvals 부재, 000660 unresolved freeze, real-money refusal를 보존한다. 합성 fixtures는 unattended mutation/promotion 권한을 주지 않는다.
- `requirements-completed: []`; AUTO-01/FUT-04/AUTO-02는 phase-wide verification까지 pending이다. Auth gates 없음. goal를 막는 placeholder/stub 없음; unsupported actual Codex는 명시적 fail-closed capability 제한이다.

## Self-Check: PASSED

변경 파일 7개와 SUMMARY의 존재, RED/GREEN 커밋 4개의 실제 Git object를 확인했다. 원치 않는 tracked deletion이나 generated untracked file은 없다.
