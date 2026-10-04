---
phase: 15-unattended-scheduling-service-resilience
plan: "06"
subsystem: execution
tags: [kis-mock, acceptance, provenance, read-only, capability, offline-tests]
requires:
  - phase: 15-01
    provides: Strict immutable receipt/scope/source contracts and temporary offline fixtures
  - phase: 15-02
    provides: Reviewed session policy and independent current session authority
  - phase: 15-07
    provides: Shipped single-shot provider builder with disabled retries and unverified Codex denial
provides:
  - Both named Phase 09-08 checkpoint approvals validated against exact owned campaign/profile/evidence
  - Read-only versioned owner digests, detail-level day/drill checks and cross-campaign freeze projection
  - Disabled/offline/authentic mock capability branches with explicit protected init-only credentials
  - Typed final POST guard, audit, session, quote and whole-account inquiry seams
affects: [15-08, 15-09, 15-10, 15-13, 15-14]
tech-stack:
  added: []
  patterns: [independent owner read transactions, canonical row digests, explicit offline authority, lazy mock composition]
key-files:
  created: [trading_bot/service_activation.py, trading_bot/service_composition.py, tests/test_service_activation.py, tests/test_service_composition.py]
  modified: []
key-decisions:
  - "Both 09-08 approvals bind one immutable campaign and profile; synthetic or arbitrary injected evidence cannot authorize production construction."
  - "Source hashes bind owner/version/location and canonical selected rows including WAL truth; nested evidence IDs remain covered without exceeding bounded receipt root IDs."
  - "Initial activation conservatively rejects applicable unresolved ticker freezes, preserving their ticker identities separately from global UNKNOWN/latch facts; subsequent final guard/account pass behavior belongs to 15-08/09."
  - "Authenticated accepted V-prefixed TR IDs override the shipped legacy mode-derived adapter family explicitly; no in-memory MockBroker represents KIS mock acceptance."
requirements-completed: []
coverage:
  - id: D1
    description: Exact approval identity/count/safety gates with read-only owned evidence
    verification:
      - kind: unit
        ref: tests/test_service_activation.py
        status: pass
    human_judgment: false
  - id: D2
    description: Lazy mock-only capability construction and mandatory future final guard seam
    verification:
      - kind: unit
        ref: tests/test_service_composition.py
        status: pass
    human_judgment: false
duration: 25min
completed: 2026-10-04
status: complete
---

# Phase 15 Plan 06: Evidence-Gated Mock Composition Summary

**두 09-08 checkpoint 승인을 동일 campaign·profile·세 evidence owner의 저장 사실에 묶고, 현재 안전 증거가 검증된 후에만 실제 KIS mock adapter와 제한된 provider 조합을 구성한다.**

## Performance

- 약 25분, 2026-10-04 05:33–05:58 UTC.
- 작업 2/2, source/test 파일 4개 생성. 공유 tests/service_fixtures.py는 변경하지 않았다.
- 외부 broker/provider/Discord, production DB 접근·migration, 패키지 설치·다운로드, launchctl·설치·proof POST를 수행하지 않았다.

## Accomplishments

- `ActivationVerdict`, immutable `SavedAcceptanceEvidence`, day/drill details, `CurrentActivationSafety`, `OfflineActivationAuthority`와 `validate_unattended_activation`을 추가했다. 두 checkpoint의 별도 actor/time/evidence 링크, 동일 scope/campaign/profile, 정확한 source hash와 root IDs를 검증한다. 명시적인 offline authority 결과는 `OFFLINE_ONLY`; production은 정확한 owned reader·protected receipt read-back·KIS_OBSERVED provenance가 필요하다.
- target 20/budget 2, 완료된 하나의 SOAK campaign, 20개 고유 날짜/run, terminal mock day, authentic profile, 완전한 reconciliation/cross-links, zero breach와 permanent latch 부재를 요구한다. 다른 campaign 날짜 합산, PLAN 존재, readiness PASS 또는 receipt Boolean은 허가 근거가 아니다. Task1 approval은 designated day와 모든 exact controlled drill을, Task2 approval은 전체 root evidence를 포함해야 한다.
- `ReadOnlyAcceptanceEvidenceReader`는 shipped `ReadOnlySoakRepository`의 strict schema와 각 owner별 mode=ro/query_only transaction을 사용한다. 같은 저장 transaction으로 shipped soak report와 primary run completeness를 검증한다. 계좌 suffix의 canonical hash, accepted profile fingerprint/provenance, PRE_RUN/PRE_FINALIZE 및 accepted/ambiguous submission마다 POST_SUBMISSION cardinality, exact FaultName registry/required observations/containment/boundary/policy/terminal controller verdict와 primary/reconciliation/freeze links를 확인한다. migration·approval capture·freeze clear API가 없다.
- owner/version/location에 묶인 canonical selected row digest는 WAL 상태와 모든 nested snapshot/comparison/observation ID를 포함한다. Receipt의 최대 128 root IDs 안에서는 campaign/identity/designated primary run/controller drill roots를 나열하고 nested IDs는 불변 source hash로 함께 바인딩한다. DB file byte hash를 immutable journal 증거로 오인하지 않는다.
- current safety는 scope, 최대 10초 validity, 세 owner source identity, healthy/global latch 사실을 다시 확인한다. 모든 campaign의 freeze는 shipped terminal-release 검증을 통해 원래 ticker tuple로 투영된다. 같은 subject의 determinate terminal owner evidence만 release로 인정되며 local receipt, readiness, 날짜 변화는 해제 권한이 없다.
- `build_service_composition`은 DISABLED metadata만 반환하고 DRY_RUN은 별도의 owned temporary topology와 명시적인 frozen/injected callbacks만 받는다. 두 경로는 trading credential 설정·KIS client·broker·provider를 구성하지 않는다. KIS_MOCK은 receipt 검증 전 secret path를 읽지 않는다. 설정은 protected explicit JSON과 init-only sources를 사용하여 env/.env, real credentials, trading_mode/confirm_real flags가 들어올 수 없다.
- 실제 KIS 경로는 shipped `KisTokenManager`, `KisOrderAdapter`, `KisQuoteAdapter`, `collect_portfolio_snapshot`, `KISBroker`를 재사용한다. domain은 정확한 mock HTTPS host/port, account scope 및 triple path가 일치해야 한다. accepted official profile의 VTTC0012U/VTTC0011U/VTTC0081R/VTTC8434R를 실제 adapter에 바인딩하고 legacy mode-derived POST IDs를 암묵적으로 사용하지 않는다. 일반 `_build_broker`의 in-memory MockBroker나 soak campaign runner를 호출하지 않는다.
- order POST timeout은 10초, query timeout은 최대 15초/최대 3회 bounded GET, provider는 shipped 15-07 single-shot builder의 90초/zero SDK·HTTP retry 계약을 사용한다. actual Codex의 검증되지 않은 retry capability는 `PROVIDER_SINGLE_SHOT_UNVERIFIED`로 provider 실행 전에 차단한다. 모든 lazy callback/builder는 현재 activation을 다시 검증한다.
- `BrokerGuardContext`는 scope/current activation/all-campaign freezes/session policy/clock/10초 POST bound를 제공한다. `guarded_broker_builder`는 별도 actual adapter guard와 callable transition audit sink를 필수로 받으며 raw adapter 그대로 반환하는 guard를 거부한다. Legacy unguarded KIS test constructor는 사용하지 않는다. 실제 POST linearization/control/account authority는 다음 계획의 구현 책임이다.

## Task Commits

| Task | Stage | Commit | Verification |
|---|---|---|---|
| 1 | RED | 993b17e | 미구현 activation module에서 36개 expected failures |
| 1 | GREEN | c907196 | 39개 receipt/detail/owned-reader tests 통과 |
| 2 | RED | c7a4b31 | 미구현 composition module에서 15개 expected failures |
| 2 | GREEN | aa902fc | 지정 두 module 총 59개 tests 통과 |

## Verification

`PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_service_composition.py tests/test_service_activation.py --tb=short`

**59 passed in 1.21s** (activation 39, composition 20). Source `compileall` 및 `git diff --check` 통과. 모든 journals는 temp fixture owner API로만 생성했다. Owned reader의 byte-level before/after 검증, schema mismatch, source 변화, 다른 campaign 000660 freeze, 누락·외국 actor·두 approval·중복 날짜·synthetic day·부족/중복 drill·target/budget/breach/current expiry denials, 설정/secret/client/provider/broker zero-construction tripwires를 포함한다.

Composition 테스트는 fake client만으로 authentic shipped adapter identity/arguments와 whole-account normalization을 확인했다. real endpoint, 경로 변조·userinfo·query domain, foreign account/profile, real flags 및 secret env override는 client 생성 전에 거부된다. Fake transport/임시 KIS_OBSERVED 모양의 fixture도 `OFFLINE_FIXTURE` 또는 `OFFLINE_ONLY`로 표시되며 실제 승인이 아니다. 부모가 후속 wave/phase regression을 담당한다.

## Deviations from Plan

**1. [Rule 2 - Missing critical identity binding] Accepted mock profile의 실제 POST TR IDs를 명시적으로 바인딩했다.**
- Task2에서 shipped KisOrderAdapter의 mock mode 기본 BUY/SELL은 legacy VTTC0802U/VTTC0801U이고 authenticated official-example-v1은 VTTC0012U/VTTC0011U인 것을 확인했다.
- 신규 dependency나 기존 owner file 수정 없이 composition 내부에서 validated profile의 immutable KisOrderTrIds를 shipped adapter에 바인딩했다. exact family/domain/account denial tests로 검증했다. Commit aa902fc.

**2. [Rule 2 - Missing critical provenance] Shipped aggregate report에 root-level proof가 부족한 부분을 strict immutable read-only projection으로 보완했다.**
- Task1에서 aggregate drill count만으로 exact FaultName completeness를 증명할 수 없고 보고서만으로 accepted profile/owner digest 및 credited-date 상세가 충분하지 않았다.
- 동일 owned read transactions에서 원본 detail과 registry를 검증하고 canonical source digests를 생성한다. 기존 schema/report owner를 변경하지 않았다. Commit c907196.

## Integration Boundaries

- PLAN Task1의 `unresolved freeze blocks activation` behavior에 따라 **초기 활성화는 known scoped freeze에서도 보수적으로 거부된다**. Known frozen ticker identities와 글로벌 UNKNOWN/safety latch는 서로 다른 이유와 사실로 유지한다. 이 검증기는 ticker freeze를 global safety latch로 저장하거나 해제하지 않는다.
- `read_freezes`와 final-guard context는 원래 ticker tuple을 제공한다. D-08의 otherwise-safe held risk 보호, per-ticker final admission, provider wait 전후 bounded account lease release/reacquisition은 15-08/09 통합과 전체 증명 책임이다. 이 계획에서 global controls/account exclusion/final POST guard를 구현했다고 주장하지 않는다.
- `runtime_wired=False`는 명시적인 후속 계획 경계다. 실제 service entrypoint/web/observer/control CLI에는 import·wiring을 추가하지 않았다. `reconcile_orders`는 fresh whole-account normalized truth를 읽는 seam이며 owner authority 아래 비교 저장 및 terminal release는 이후 통합한다.
- actual production composition은 raw adapter/client/account를 공개하지 않는다. 임시 offline harness에서만 `_test_order_adapter` inspection을 제공한다. Binder의 duck-typed 함수 자체는 실제 15-08 guard의 안전 증명이 아니며 실제 wiring 전 전체 guard tests가 필요하다.

## Known Stubs

목표를 막는 placeholder 없음. `None` callbacks는 DISABLED/거부된 capability이며 `runtime_wired=False`와 final-guard bindings는 PLAN에 명시된 15-08/09 integration 경계이다. Unsupported actual Codex는 명시적인 fail-closed 제한이다. Test의 빈 counter와 fixture rows는 offline 증거이고 실제 broker truth나 승인으로 사용되지 않는다.

## External Activation Blockers

- 실제 Phase 09-08 Task1/Task2 explicit approvals, target20 eligible elapsed broker-facing evidence 및 source-linked receipt가 여전히 필요하다. 이번 테스트는 그 증거를 만들지 않았다.
- actual 000660 freeze는 same-subject determinate terminal broker evidence 전까지 유지된다. production store를 열거나 freeze를 변경하지 않았다.
- Reviewed current-date session evidence, 실제 owner login/wake/install/private device acceptance는 미수행이다. Unverified actual Codex single-shot capability는 차단된다.
- Phase16 real-money authority는 거부한다. FUT-04/AUTO-01/AUTO-02는 전체 phase proof 전까지 미완료이며 `requirements-completed: []`를 유지한다.
- Auth gate는 발생하지 않았다. 실행 과정에서 계정·provider·서비스 접근을 시도하지 않았다.

## Self-Check: PASSED

Source/test 네 파일과 canonical SUMMARY 경로의 존재를 확인했다. 993b17e/c907196/c7a4b31/aa902fc는 실제 Git commit objects이며 각 task RED→GREEN 순서가 존재한다. 지정 tests/compile/diff 검사 통과, 원치 않는 tracked deletion 또는 generated untracked file 없음. 새 network endpoint, schema/migration owner, approval transport 또는 real promotion surface를 도입하지 않았다.
