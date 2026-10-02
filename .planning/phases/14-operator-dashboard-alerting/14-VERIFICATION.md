---
phase: 14-operator-dashboard-alerting
verified: 2026-10-02T09:45:35Z
status: gaps_found
score: 34/36 must-haves verified
behavior_unverified: 0
overrides_applied: 0
verification_head: 9ac4f28477ec256e47d7b99e0188e2a0ff171590
gaps:
  - truth: "Every displayed total drills down to durable source details and preserves UNKNOWN/INCOMPLETE states rather than smoothing them away."
    status: failed
    reason: "활성 알림을 전역 LIMIT 100으로 먼저 자른 뒤 등록 원천/계좌/대상과 CRITICAL을 필터링한다. 합성 101건은 100으로 표시되고, 더 최근의 다른 범위 100건은 해당 범위의 실제 CRITICAL 1건을 0으로 숨긴다. 헤더 링크도 정확한 CRITICAL/범위 선택을 보존하지 않는다."
    artifacts:
      - path: trading_bot/web_app.py
        issue: "operational_view의 active_incidents/critical_count 계산에서 범위·심각도 필터보다 LIMIT이 먼저 적용됨."
      - path: trading_bot/templates/operator/base.html
        issue: "critical-count가 범위·심각도 선택 없이 /alerts로 이동함."
    missing:
      - "등록된 원천·계좌·대상·활성·심각도 조건을 먼저 적용한 정확한 합계 또는 확인 불가 시 UNKNOWN."
      - "합계와 동일 선택을 유지하는 제한된 구성 행 페이지·상세 링크."
      - "101건 이상 및 다른 등록/미등록 계좌·대상이 앞선 경우의 합계/페이지 회귀 테스트."
  - truth: "D-09: Visible tabs read saved evidence every 30 seconds with manual refresh, no overlap and 10-second timeout; browser query time never overwrites source observation time."
    status: failed
    reason: "저장 증거 새로고침 성공 시 source-status와 operator-evidence만 교체한다. 실제 Chromium에서 CRITICAL 0건 화면을 연 뒤 1건을 저장하고 수동 새로고침해도 헤더는 0건이다. 같은 시점의 새 GET HTML은 1건이다."
    artifacts:
      - path: trading_bot/static/operator.js
        issue: "refresh/apply/replaceStatus가 헤더 critical-count를 갱신하지 않음."
      - path: tests/browser/test_operator_refresh.py
        issue: "조회 횟수/시간/본문/초안은 검증하지만 새 CRITICAL 합계의 헤더 갱신은 검증하지 않음."
    missing:
      - "성공한 동일 원천 선택의 응답으로 헤더 안전 요약도 갱신하는 연결."
      - "새 알림·복구·범위 변경 후 자동/수동 새로고침의 헤더 수와 구성 행 일치 테스트."
human_verification:
  - test: "한국어 운영 화면의 시각적 사용성 검토"
    expected: "안전 개요의 우선순위, 네 탐색 그룹, 모바일 상세, 밝음/어두움 테마에서 미해결 000660·UNKNOWN·INCOMPLETE·원천 관측 경과를 색에 의존하지 않고 이해할 수 있다."
    why_human: "Chromium의 계산된 대비·레이아웃·키보드·200% 확대 증거는 존재하지만 운영자가 한국어 문구와 현실적인 저장 증거의 읽기 편의성을 수용했는지는 자동화로 판정할 수 없다. 14-12에서 이 확인을 단계 말에 유보했다."
  - test: "조건부: 소유자가 사설 VPN/HTTPS를 명시적으로 구성한 경우 실제 휴대폰 모바일 데이터 접속 확인"
    expected: "사설 경로로만 접속하고 정상 HTTPS 인증서를 사용한다. 앱 로그인이 필수이고 Secure/HttpOnly/SameSite cookie 및 PC/휴대폰 독립 세션·로그아웃·절대 12시간 만료가 유지된다. 기본 PC loopback과 공개 미노출도 확인한다."
    why_human: "실제 VPN·인증서·방화벽·휴대폰은 합성 로컬 테스트 밖이다. 선택적 미구성 배포는 구현 gap이 아니며 휴대폰 도달성·실제 배포를 검증했다고 주장하지 않는다."
---

# Phase 14: 운영 웹 UI·대시보드·알림 검증 보고서

**Phase Goal:** Operators can use an authenticated responsive web application to inspect portfolio, decision, order, validation, report, and worker-health evidence and handle non-trading operational workflows without granting the web process trade authority.

**검증 시각:** 2026-10-02T09:45:35Z  
**상태:** gaps_found  
**재검증:** 아니오 — 기존 14-VERIFICATION.md가 없는 최초 검증  
**기준:** HEAD `9ac4f28477ec256e47d7b99e0188e2a0ff171590`

목표 달성은 아직 입증되지 않았다. 화면·저장 보고서·인증·비거래 권한 경계는 실질적으로 구현되었지만, 안전 헤더가 잘못된 CRITICAL 합계를 표시하며 성공한 새로고침에도 이전 합계를 유지한다. 두 결함을 수정하고 재검증하기 전에는 다음 단계로 진행하지 않는다. SUMMARY의 완료 문구를 증거로 사용하지 않았다.

## 검증 범위와 증거 출처

AGENTS.md, config, REQUIREMENTS, 전체 ROADMAP의 14/15/16 경계, 14개 PLAN과 SUMMARY, D-01–D-16 CONTEXT, 승인된 UI-SPEC, RESEARCH의 실제 위험, VALIDATION의 실행 관측 및 11/12/13 VERIFICATION을 대조했다. 프로젝트 skill 인덱스에는 이번 코드 검증에 추가 적용할 품질 rules가 없다. 현재 GSD 실행 단계의 검증 산출물만 작성했으며 코드·테스트·STATE·ROADMAP·REQUIREMENTS·VALIDATION은 변경하지 않았다.

실제 부모 실행 증거는 최종 전체 명령 `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q`의 **1412 passed / 320.01s**이다. 이 실행은 최종 소스 변경 후 이루어졌으며 Chromium UI 16건·refresh 12건과 이전 검증에 참조된 현존 37개 테스트 파일을 포함한다. 전체 suite를 반복하지 않았다. 테스트 본문과 실제 호출 경로를 읽고, 본 검증 프로세스에서 별도 capability probe와 상태 불변식 spot-check를 실행했다. 전체 회귀 통과를 합계 정확성의 증거로 대체하지 않았다.

실행 인터프리터는 Python 3.14.3이다. `requires-python >=3.10`만으로 StrEnum이 필요한 3.10 호환성을 주장하지 않는다. 운영자 원천 DB·.env·자격 증명·KIS·LLM·실제 Discord를 사용하지 않았고 서비스/배포/거래를 실행하지 않았다. 결함 재현은 TemporaryDirectory의 합성 원천과 운영 DB, Flask test client 및 모든 요청을 test-client 응답으로 fulfill하는 Chromium route를 사용했다. 재현용 서버는 시작하지 않았다.

## 목표 달성

### 관찰 가능한 진실

다섯 ROADMAP 계약을 먼저 유지하고 PLAN의 50개 진실 중 의미상 중복인 화면·인증·상세·테마·수출 주장을 합쳤다. 아래 36개 항목은 PLAN이 ROADMAP 범위를 줄이지 않도록 구성한 합집합이다. VERIFIED는 존재·실질 구현·호출 연결을 확인했고 상태 전환은 이름 있는 행동 테스트를 읽고 통과 증거를 확인했다. FAILED는 BLOCKER이다. 시각 사용성/실제 선택적 네트워크 확인은 별도 WARNING 사람 항목이며 자동화된 화면 존재나 반응형 동작과 혼동하지 않는다.

| # | 진실 | 판정 | 실제 증거 |
|---|---|---|---|
| 1 | SC-1: 한국어 PC/모바일에서 계좌·보유·후보·판단·주문·체결·실행·보고서·Replay·Soak·보정·준비도·작업 상태를 확인한다. | VERIFIED | `web_app.OPERATIONAL_VIEWS`, validation/report/alert routes, `base.html`의 17개 경로; `test_every_destination_detail_theme_contrast_and_mobile_targets`가 1280/390/320×두 테마에서 실제 이동·상세를 검사. 백테스트/Shadow도 포함. |
| 2 | SC-2: 표시 합계가 정확한 durable 구성 증거로 연결되고 UNKNOWN/INCOMPLETE를 유지한다. | FAILED — BLOCKER | 계좌/보고서 구성 선택은 연결되지만 `web_app.py`의 CRITICAL 합계는 전역 첫 100건에 제한된다. 실제 101→100, 다른 범위 100건+해당 범위 1건→0 재현. G-1. |
| 3 | SC-3: 보고서 생성·수출·알림 읽음이 인증·권한·CSRF·감사 기록을 요구한다. | VERIFIED | 전역 `guard`, `generate_report`, `owned_artifact`, `acknowledge_alert`; route/method/expired/download 보안 matrix와 actor-owned artifacts·transactional action audit. |
| 4 | SC-4: 심각도 기반 중복 제거·증거 연결 알림이 실패/오래된 작업·미해결 주문·래치·브로커 차이를 포괄한다. | VERIFIED | `AlertDetector.detect/_record/_worker`, `AlertStore.observe`, saved stream/subject joins; detector family/strict stale boundary/positive recovery, episode/revision/producer receipt 테스트. 헤더 표시 결함은 #2/#34에 별도 실패. |
| 5 | SC-5: 웹은 주문·live LLM·정책 쓰기·비밀 표시·실거래 활성화·안전 면제 권한이 없고 local/private가 기본이다. | VERIFIED | 독립 `WebSettings`, pure saved import graph, registered resource/path topology, global route capability matrix; 본 검증의 fresh child 8 surface·전 원천 불변성 probe 통과. |
| 6 | 새 패키지는 명시적인 소유자 검증 후 승인된 일곱 pin으로만 설치된다. | VERIFIED | 부모가 제공한 직접 사용자 승인 provenance, 14-01의 차단 checkpoint, pyproject의 exact pins 및 `test_operator_setup` 설치 metadata. SUMMARY 자체만으로 런타임 정확성을 판정하지 않음. |
| 7 | 독립 합성 fixture/browser harness가 broker/LLM/Discord 없이 귀속된 증거를 검증한다. | VERIFIED | `operator_fixtures`, `capability_probe`, browser conftest; test-owned writer는 child 밖, child는 shared conftest 없이 guard를 먼저 설치. |
| 8 | 설치된 wheel에 독립 bot-web/bot-alerts와 모든 native 자원이 있다. | VERIFIED | pyproject scripts/package-data; `test_offline_installed_wheel_has_native_resources_independent_entrypoints_and_render`가 offline wheel/isolated target·checkout 없는 child에서 help/factory/template/assets를 검사. |
| 9 | Replay/backtest/Shadow/Soak/calibration/readiness의 saved 소비자는 평가·live 수집 없이 import/build/render한다. | VERIFIED | `evidence_contracts`, `replay_evidence`, `backtest_evidence`, `shadow_evidence`, `calibration_evidence`; `web_reports`는 fixed family dispatch; fresh per-family 및 전 surface before-import tripwire. backtest legacy writer는 웹에서 사용하지 않음. |
| 10 | 과거 canonical ID/bytes는 보존되고 변경된 source code identity는 새로 귀속된다. | VERIFIED | frozen UTF-8 replay ID, historical backtest ID, `test_future_code_identity_covers_moved_evidence`, calibration/readiness/soak frozen vectors; legacy class/helper 동일 객체 re-export. |
| 11 | saved Shadow가 trusted proof·provenance·journal cardinality·derived metrics를 재검증한다. | VERIFIED | `validate_saved_shadow_result`, registered catalog resolve/expected_hash, inventory/comparisons checks; `test_registered_proof_passes_without_any_evaluator`. |
| 12 | 누락된 Shadow proof·재hash 위조는 성공 판정이 아닌 named UNKNOWN/unavailable이다. | VERIFIED | `SavedShadowUnavailable`, `SAVED_SHADOW_PROVENANCE_UNAVAILABLE`; absent proof·rehashed forgery·self-register proof negative tests. |
| 13 | Shadow의 coverage/usage/cost 분모와 ESTIMATED·advisory 한계를 유지한다. | VERIFIED | `web_reports._shadow`, report metrics/excluded/unknown rows, saved reporting exact denominator tests; 동의율을 정확도·수익성·승격으로 표현하지 않음. |
| 14 | D-05: loopback 기본이며 명시 private HTTPS의 host/origin/single proxy·앱 인증을 요구한다. | VERIFIED | `WebSettings.validate_contract`, `FixedProxyBoundary`, Waitress serve options; private peer/proto/chain/spoof tests 및 구체적인 선택적 runbook. 실제 휴대폰 도달성은 조건부 사람 확인. |
| 15 | D-06: 전용 계정은 로컬 setup/reset에서 별도 scrypt hash로 관리한다. | VERIFIED | `WebAuth.hash_password` scrypt:131072:8:1·random salt; CLI hidden prompt·protected config·reset revoke, 실제 scrypt test. |
| 16 | D-07: 서버의 발급+12시간 절대 만료가 polling으로 연장되지 않는다. | VERIFIED | `WebStore` session row와 `issued_at <= now < expires_at`; 본 검증 `test_exact_expiry_and_polling_never_slide` 통과. |
| 17 | D-08: PC/휴대폰 세션·logout은 독립이고 password reset은 모두 폐기한다. | VERIFIED | 별도 opaque reference rows, reset transaction; auth tests와 real Chromium independent-context boundary tests. |
| 18 | operational schema만 쓰고 source owner/version/schema/data/bytes를 변경하지 않는다. | VERIFIED | mode=ro/query_only·owner version·fixed schema·독립 transactions; WebStore/AlertStore의 별도 metadata; 본 검증 전 surface source inventory/bytes 동일. |
| 19 | D-10: 실패/불완전 읽기는 과거 완전 관측·원천 시간/age를 유지하고 unknown 금액은 0이 아니다. | VERIFIED | `ReadOnlyPortfolioRepository.account`, `_account` cache와 immutable envelope replace; 본 검증 cache-time 테스트 및 incomplete_zero_cash/failed-source browser 테스트. |
| 20 | D-12: 기본 오늘은 KST이며 기간 필터가 all-date 000660·활성 위험을 숨기지 않는다. | VERIFIED | `PeriodSelection`, `_unresolved`, safety blocks 별도; today/custom native route/browser tests. G-1은 알림 개수 한도에서 별도로 위험을 숨기는 결함. |
| 21 | 계좌·대상·원천 시간이 확실히 귀속되고 snapshot constituent/watch joins가 정확하다. | VERIFIED | same snapshot_id holdings/orders/fills, watch_iterations.snapshot_id join, `_check_run` scope conflict rejection; 본 검증 worker join/strict stale boundary 통과. |
| 22 | D-16: TXT/JSON/CSV가 IDs·scope·정밀도·분모·UNKNOWN·모의/advisory 의미와 안전한 spreadsheet profile을 보존한다. | VERIFIED | `serialize_report`, Decimal exact JSON, CSV NFKC/control/formula-prefix neutralization·identity-as-text; actual download parsing 및 byte/row/period caps. |
| 23 | 모든 validation metric은 excluded/unknown 포함 동일 선택의 constituent rows로 연결된다. | VERIFIED | `SavedReportProjection.metric_detail`, constituent ID subset checks, `_daily/_replay/_backtest/_shadow/_soak/_calibration/_readiness`; same selector/native metric links. 헤더 CRITICAL은 이 서비스 밖이며 #2 실패. |
| 24 | D-14: durable source occurrence만 count하고 worsening/recurrence는 새 unread revision/episode다. | VERIFIED | unique observation key·active subject index·ordered reduction; episode historical/backdated/revision tests 및 본 검증 end-to-end recurrence 통과. |
| 25 | D-15: 읽음은 actor/server time/optional note를 저장하고 reminder만 중지하며 복구/동결을 해제하지 않는다. | VERIFIED | expected_revision CAS·append-only ack·next_reminder NULL; conflict note retention/positive recovery/recurrent unread 테스트 및 본 검증 통과. |
| 26 | D-13: Phase11 소유 delivery는 link하고 재전송하지 않으며 missing receipt는 UNKNOWN이다. | VERIFIED | producer event/attempt unique keys, `_receipts`, link_producer_delivery; late receipt/recurrence/producer ownership 테스트. |
| 27 | INFO/WARNING/CRITICAL와 active/history/attempts를 웹에 유지하며 채널 delivery는 소유권에 따른다. | VERIFIED | alerts template/list/detail/history, INFO web-only, WARNING/CRITICAL observer events+recovery; observer fake transport tests, 실제 Discord 전달은 수행하지 않음. |
| 28 | D-14: 명시 monitor는 30초 scan, unread CRITICAL만 30분 reminder, WARNING/no catchup이다. | VERIFIED | watch wait(30), due_reminders exact boundary·ack suppression; 본 검증 `test_reminder_critical_only_exact_boundary_ack_suppression_no_catchup` 통과. |
| 29 | observer start/heartbeat/stop/claim/crash는 durable이며 browser나 거래 리스에 종속되지 않는다. | VERIFIED | 독립 observer ownership, committed claim before send, failed/UNKNOWN terminalization; 본 검증 crash-after-send no-duplicate, fresh watch-stop/status probe 통과. |
| 30 | D-01: 안전 위험·health·원천 시각이 계좌/최근 활동보다 먼저 보인다. | VERIFIED | overview #safety→#health→#source-times→#accounts→#activity; positive saved latch는 NOT_STARTED observer에서도 표시. route 순서 및 브라우저 저장 위험 tests. |
| 31 | D-02: 모바일·no-JS에서도 모든 화면/상세/수출/읽음 기능을 사용할 수 있다. | VERIFIED | 같은 SSR native routes/forms, table/card facts; real Chromium 390/320·no-JS navigation·downloads/ack tests. 사람의 한국어 가독성 수용은 별도. |
| 32 | D-03: 네 그룹의 17개 목적지를 PC/모바일 메뉴에서 찾을 수 있다. | VERIFIED | base fixed paths와 guarded route registry; actual navigation matrix·native summary Space/Enter·JS aria toggle tests. |
| 33 | D-04: system light/dark·text/icon·대비·44px·keyboard·200% 확대가 작동한다. | VERIFIED | approved CSS tokens/media/focus/reduced motion; 실제 computed 4.5:1 text/3:1 controls·targets·local scroll·zoom 검증. 정적 token 존재만으로 통과시키지 않음. |
| 34 | D-09: 30초/수동 saved refresh가 요약을 갱신하고 timeout/no overlap/source time 분리를 지킨다. | FAILED — BLOCKER | 타이머/timeout/source-time 동작은 기존 테스트로 입증되었으나 actual Chromium 수동 성공 후 헤더 0→0, 동일 GET 새 HTML 1 재현. G-2. |
| 35 | D-10: dirty form·focus·selection·disclosure·scroll·last success 및 expiry/back hide/no POST replay를 보존한다. | VERIFIED | operator.js dirty/defer/apply·AbortController·restorePending·sessionEnded; 12개 real refresh tests가 실제 DOM·fake time·action failure를 검사. |
| 36 | 기존 평가 API는 실행 측에 남고 saved 소비자의 schema/identity/UNKNOWN 계약은 fail closed다. | VERIFIED | calibration.evaluate_variants의 original replay path, shadow preparation strict execution checks, legacy re-export, saved family owner-schema/forged-link tests; 이전11–13 regression은 전체1412 실행에 포함. |

**점수:** 34/36 진실 VERIFIED. 두 FAILED는 동작이 없는 불확실성이 아니라 실제 잘못된 결과이다. PRESENT_BEHAVIOR_UNVERIFIED는 0이며 override는 없다. `passed`로 판정하지 않는다.

### PLAN must-have 추적

각 배열의 번호는 PLAN frontmatter의 truths 순서다. 같은 ROADMAP 계약/구현 진실을 반복하는 항목은 위 번호로 중복 제거했다. 전 단계 E2E 주장은 해당 구성 진실의 실패를 상속하므로 task-complete로 통과시키지 않는다.

| PLAN | truths → 위 항목 | 결과 |
|---|---|---|
| 14-01 | 1→6 | VERIFIED |
| 14-02 | 1→7; 2→8 | VERIFIED |
| 14-03 | 1→9; 2→10 | VERIFIED |
| 14-04 | 1→11; 2→12; 3→13/22 | VERIFIED |
| 14-05 | 1→14; 2→15; 3→16; 4→17; 5→18 | VERIFIED |
| 14-06 | 1→19; 2→2/21/23; 3→20; 4→21 | 2 FAILED(G-1), 나머지 VERIFIED |
| 14-07 | 1→22; 2→9; 3→23 | VERIFIED |
| 14-08 | 1→24; 2→25; 3→26 | VERIFIED |
| 14-09 | 1→27; 2→28; 3→4; 4→29 | VERIFIED |
| 14-10 | 1→30; 2→31; 3→32; 4→33; 5→21/23; 6→3 | VERIFIED (운영 source totals와 안전 헤더 #2는 구분) |
| 14-11 | 1→34; 2→19/35; 3→27; 4→25/3; 5→22/3; 6→1/23/12 | 1 FAILED(G-2), 나머지 VERIFIED |
| 14-12 | 1→1–36; 2→14/17; 3→31; 4→33; 5→5/18 | 1 FAILED(G-1/G-2), 나머지 구현 VERIFIED; 시각/선택적 네트워크 human 항목 별도 |
| 14-13 | 1→9; 2→10/22; 3→18/36 | VERIFIED |
| 14-14 | 1→31/32; 2→33; 3→7/1 | VERIFIED |

### 필수 산출물 — 존재·실질 구현·연결

`verify.artifacts`를 14개 PLAN에 각각 실행했다. 선언된 87개 artifact 참조는 모두 존재하며 도구의 line/pattern 검사는 통과한다. 이것만으로 목표를 통과시키지 않았다. 아래 호출/데이터 흐름을 별도로 확인했고 web_app/JS의 구현 결함을 명시했다. 테스트 파일은 해당 test/fixture의 실제 호출·assertion과 pytest 수집/최종 실행 연결을 확인했다.

| 산출물 | 실질 구현/사용 연결 | 판정 |
|---|---|---|
| 14-01-SUMMARY; pyproject.toml; test_operator_setup/operator_fixtures/capability_probe/test_operator_fixtures/browser conftest | 승인 pin/entry points/resources, temporary source+clock, before-import guard, 실제 Chromium harness | VERIFIED |
| evidence_contracts.py/replay_evidence.py/replay.py/reporting.py; test_evidence_contracts | pure owner schemas/DTO/hash; legacy evaluator re-export·readonly report imports | VERIFIED |
| backtest_evidence.py/backtest_engine.py/backtest_reporting.py; test_saved_backtest_evidence | ledger/accounting saved validation·engine compatibility·historical identity | VERIFIED |
| shadow_evidence.py/shadow_runner.py/shadow_reporting.py/shadow_inputs.py; saved Shadow/reporting/capability tests | trusted proof→saved validator; preparation/run 경로는 엄격한 별도 execution path | VERIFIED |
| calibration_evidence.py/calibration.py/calibration_reporting.py/promotion_readiness.py/soak_reporting.py; saved calibration/soak tests | pure saved reduction·read schema·nine checks; original evaluate API retained | VERIFIED |
| web_config.py/web_store.py/web_auth.py/web_cli.py; config/store/auth/CLI tests | immutable registration/topology, operational ownership, dedicated password/session, setup/reset/Waitress | VERIFIED |
| web_models.py/web_evidence.py; test_web_evidence | typed selections/envelopes·bounded readonly source readers·snapshot/history/cache/health | VERIFIED |
| web_reports.py; test_web_reports/test_web_report_routes | eight fixed saved families·same selection·three serializers·owned atomic artifacts·rollback | VERIFIED |
| alert_models.py/alert_store.py/notification_transport.py/notifier.py; store/transport tests | stable episode/revision/ack/outbox/compatibility notifier·sanitized bounded transport | VERIFIED |
| alert_detector.py/alert_config.py/alert_observer.py/alert_cli.py; detector/observer/CLI tests | durable fact detection·foreground ownership/claims/stop·credential-free status | VERIFIED |
| web_app.py; login/overview/list/detail/validation/reports/alerts templates; routes/security/alert-route tests | guarded SSR/API, authenticated native actions and source details; CRITICAL summary LIMIT/filter order defect | 구현 존재·연결됨, G-1 BLOCKER |
| base.html/macros.html/operator.css; test_web_ui_contract | 17-route shell·escaped bounded facts·responsive system themes·44px native targets | VERIFIED; critical-count selector link는 G-1 |
| operator.js; browser/test_operator_refresh | saved fetch cadence/abort/cache/dirty/expiry DOM wiring; header summary update 없음 | 구현 존재·연결됨, G-2 BLOCKER |
| test_web_capabilities/test_web_security/test_operator_integration/browser/test_operator_ui | 실제 호출 before-import/negative source invariance/security/mobile/contrast assertions | VERIFIED; CRITICAL 합계/헤더 refresh missing assertion은 G-1/G-2 |
| docs/operator-runbook.md/test_web_packaging | exact local/private config·independent monitor lifecycle·offline installed wheel | VERIFIED; 실제 network/한국어 사용성은 human |

### 핵심 연결

PLAN의 key-links 46개는 대부분 `"portfolio snapshot totals"`, `"every screen/action"`처럼 설명형 from/to이며 실제 파일 경로가 아니다. 기계 `verify.key-links`는 0/46으로 보고한다. 이를 46개 제품 미연결로 오판하거나 통과 도구 결과로 대체하지 않고 실제 파일/호출/행동을 수동 추적했다.

| 연결 | 실제 호출 경로 | 판정 |
|---|---|---|
| approved package set→installed extras/browser | 14-01 gate→pyproject exact pins→test_operator_setup metadata/actual launch | WIRED |
| shared pure schema/DTO→saved consumers | reporting/backtest/shadow/calibration/soak imports→pure contracts/validators, compatibility re-exports | WIRED |
| snapshot totals→holdings/orders/fills | ReadOnlyPortfolioRepository.account(sid)→same snapshot_id→EvidenceSelection→native list/record/evidence | WIRED |
| watch iteration→portfolio snapshot/worker | watch_iterations.snapshot_id JOIN snapshots→source observation/cadence→WorkerDTO | WIRED |
| all-date unresolved/safety→overview/orders/alerts | _unresolved/_safety_blocks separate from period→overview/orders; detector streams→episodes | WIRED; header subset selection는 G-1 |
| registered report request→saved builders→exact metrics | fixed ReportRequest/catalog→project→family builder→metric_detail same ID selection | WIRED |
| actor-owned artifact→generated bytes/download | pinned dir_fd·opaque sealed ID→metadata+audit transaction→load_owned_artifact→guarded download | WIRED |
| durable observation→episode/revision/read | unique source key·subject→observe→expected_revision ack→actor/time/note, source unchanged | WIRED |
| producer event→delivery history | observation subject→receipt→unique producer link; missing delivery UNKNOWN | WIRED |
| outbox→bounded transport | committed claim→send→finalize; crash→UNKNOWN/no blind resend; CRITICAL due window | WIRED |
| explicit alerts CLI→foreground lifecycle | once/watch/status→independent monitor; request factory has no start invocation | WIRED |
| every page/action→auth/CSRF/audit | global before_request + method guards→saved routes/actions + store audit | WIRED |
| native shell→secure pages→Chromium/package | extends base/macros+packaged CSS/JS→17 routes→mobile/no-JS/installed-wheel probes | WIRED |
| saved refresh response→safety header | JSON/rendered_html→replaceStatus/apply; .critical-count는 교체 대상 밖 | NOT_WIRED — G-2 |

### 데이터 흐름 — Level 4

| 렌더 산출물 | 표시 데이터 | 원천/선택 | 판정 |
|---|---|---|---|
| overview/account/holdings | cash/total/holdings/orders/fills | registered readonly portfolio SQL→one complete snapshot→same snapshot rows; last complete time/cache failure label | FLOWING |
| candidates/decisions/orders/fills/runs/record/evidence | saved rows/reasons/order progression/IDs | fixed consumed SQL fields→positive resource scope→stable ID/selection→escaped bounded DTO | FLOWING |
| workers/source metadata | lifecycle/expectation/cadence/actual observation/lease age | saved transitions/watch/snapshot joins; lease 단독으로 건강을 증명하지 않음; no observation/cadence→UNKNOWN | FLOWING |
| validation/report metrics | result rows/denominators/exclusions/unknowns | validated saved files/readonly owners + registered proof facts→metric constituent selection | FLOWING; missing proof typed UNKNOWN |
| alerts/detail | subject/revision/count/duration/read/recovery/attempt history | operational episodes + append-only durable source sequence + source ID links | FLOWING |
| overview/header CRITICAL | active count/incident links | operational query result limited100→scope filtering→count | FLOWING, 합계 오류 — G-1 |
| JS refreshed header CRITICAL | stale initial count | API produces new HTML; header count DOM not consumed | DISCONNECTED — G-2 |

빈 Jinja extension block·initial nullable field·unknown model/rank/mark·없어진 source·미등록 saved proof는 stub으로 판정하지 않았다. 실제 reader가 가능한 데이터를 채우며 unavailable을 구체적으로 표시한다. 합계 결함은 데이터가 없는 stub이 아니라 실제 source selection/DOM wiring 오류이다. 원천들마다 독립 관측·트랜잭션이며 한 번의 cross-database atomic snapshot이라고 주장하지 않는다.

### 행동 spot-check와 실제 실패 재현

접두어 `P = PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q`.

| 행동 | 본 검증 명령/방법 | 결과 | 판정 |
|---|---|---|---|
| 12h boundary/polling no slide | `P tests/test_web_auth.py::test_exact_expiry_and_polling_never_slide` | 아래 일곱 named cases 통합 7 passed/2.50s | PASS |
| last complete/source time/cache | `P tests/test_web_evidence.py::test_snapshot_last_complete_and_cache_time_not_query_time` | 같은 실행 | PASS |
| actual watch join/stale equality | `P tests/test_web_evidence.py::test_worker_watch_snapshot_join_and_freshness_strict_boundary` | 같은 실행 | PASS |
| exact CRITICAL reminder/ack/no catchup | `P tests/test_alert_store.py::test_reminder_critical_only_exact_boundary_ack_suppression_no_catchup` | 같은 실행 | PASS |
| crash uncertainty/no duplicate | `P tests/test_alert_observer.py::test_crash_after_send_stays_unknown_no_duplicate` | 같은 실행 | PASS |
| read→worsen→positive recovery→recurrence/producer ownership | `P tests/test_operator_integration.py::test_web_read_worsening_positive_recovery_recurrence_and_producer_ownership` | 같은 실행 | PASS |
| artifact partial publish rollback | `P tests/test_web_reports.py::test_artifact_partial_publish_failure_rolls_back_metadata_safely` | 같은 실행 | PASS |
| 101 distinct active CRITICAL | TemporaryDirectory + registered portfolio subjects + AlertStore.observe + authenticated Flask GET / | SQL COUNT=101; HTTP200; HTML `미해결 CRITICAL · 100` | FAIL — G-1 |
| newer unrelated scope100 + valid scoped1 | same fixture; scoped saved subject first, clock+1s then foreign/real100 | HTTP200; actual scoped1; HTML `미해결 CRITICAL · 0` | FAIL — G-1 |
| safety header consumes successful refresh | real Chromium, page.route fulfill of test-client responses (no server); initial0→save1→manual button→success status | header0 remains; same fresh GET HTML1 | FAIL — G-2 |

실제 browser 28건의 기존 테스트 본문을 검토했다. cadence/timeout/hidden/no overlap/dirty/focus/disclosure/cache/expiry/no-POST-replay는 직접 상태를 assert한다. 하지만 `test_visible_cadence_manual_and_source_time`는 account 화면의 request 수/시간/본문을 검사하며 CRITICAL 헤더 변화는 검사하지 않는다. 따라서 그 테스트의 PASS는 G-2를 반증하지 못한다.

### Probe 실행

`scripts/*/tests/probe-*.sh` 디렉터리/선언은 없다. 이 단계가 명시한 runnable probe는 `tests/capability_probe.py`이고 다른 dry-run으로 대체하지 않았다.

| Probe | 본 검증 실행 | 결과 | 판정 |
|---|---|---|---|
| fresh supported surface/source invariance | `P tests/test_web_capabilities.py::test_fresh_supported_surface_and_each_source_owner_invariant` | **1 passed / 19.04s**, child마다 before-import guard. factory/routes/all eight AVAILABLE families×TXT/JSON/CSV/ack/observer once+watch stop/status/CLI/malformed/missing source의 8 surface 실행 | PASS |
| existing per-family saved contracts | 최종1412 실제 실행의 evidence/saved backtest/Shadow/calibration/soak named tests와 child code를 대조 | canonical identity·strict version/links·forgery·same-source inventories 검사 확인 | PASS — 부모 최종 실행 evidence, 본 검증 suite 반복 없음 |

### 요구사항 커버리지

PLAN 전체 frontmatter의 요구사항 합집합은 FUT-03/UI-01/UI-02/OPSV-01이며 REQUIREMENTS의 Phase14 매핑과 일치한다. orphaned requirement는 없다. REQUIREMENTS checkbox/상태는 본 검증이 수정하지 않았다.

| 요구사항 | 선언 PLAN | 구현 증거/의미 | 판정 |
|---|---|---|---|
| FUT-03 | 02/03/04/06/07/10/11/12/13/14 | authenticated Korean saved account/decision/order/report/health review가 구현됨. 안전 요약 count 및 refresh가 사실과 불일치 | BLOCKED — G-1/G-2 |
| UI-01 | 02/04/06/07/10/11/12/14 | 17 destinations·source/detail·mobile/theme objective proof 존재. 정확한 표시 합계 contract와 header refresh가 실패 | BLOCKED — G-1/G-2; 한국어 visual usability human |
| UI-02 | 01–14 | global authentication/authorization/CSRF/audit·read-only saved actions·authority absence·source-byte invariance·secure local/private config | SATISFIED (실제 optional private network 수용은 조건부 human) |
| OPSV-01 | 02/06/08/09/11/12 | durable severity/dedup/evidence-linked occurrence/worsening/recovery/critical reminders·producer ownership·explicit observer 구현 입증 | SATISFIED — detector/delivery 경로; 안전 헤더 표시 결함은 FUT-03/UI-01에 명시 |

### 금지사항과 안전 회귀

12개 PLAN(02–13)의 같은 prohibition은 source mutation/migration 및 broker/live provider/trading Settings/policy/gate-waiver capability 취득 금지이다. 레거시 frontmatter가 string 항목이며 별도 verification tier 필드는 없지만 deterministic enforcement가 실제로 연결되어 있다: fresh process forbidden import/constructor/env/socket/source SQL/file trap, route capability matrix, per-action bytes/schema/logical row inventories. 이 부정 검증이 PASS하므로 silent judgment 통과나 enforcement 없는 test-tier green이 아니다. 선언된 judgment-tier prohibition/override는 없다.

Phase11의 snapshot/lease/notification evidence 안전 계약, Phase12 modeled accounting/ledger ID, Phase13 frozen shadow provenance 경계를 확인했다. 현재 웹은 lease를 읽기만 하며 갱신/복구/주문을 얻지 않는다. 읽음과 routine completion은 freeze/latch recovery 증명이 아니고 readiness는 수동승격 권한을 부여하지 않는다. 현존 과거37 test-file refs가 부모 최종 전체 회귀에 포함되어 이전 검증 문서의 PASS 주장만을 증거로 삼지 않았다.

### Anti-pattern / 반증 관측

PLAN artifact/key-file 집합(79개 경로)의 source/test 텍스트에서 unreferenced TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER marker는 발견하지 않았다. empty/default 상태는 실제 상위 writer/reader 사용을 추적했다. 신규 금지된 source write나 raw-secret surface는 발견하지 않았다.

| 파일/위치 | 패턴 | 심각도 | 영향 |
|---|---|---|---|
| web_app.py operational_view active_incidents/critical_count | 전역 LIMIT 후 권한/범위/심각도 필터 | BLOCKER | 많은 다른 범위 사건이 해당 범위 위험을0으로 숨김; 실제101건을100으로 단정 |
| operator.js replaceStatus/apply/refresh | 본문은 refresh되지만 헤더 안전 합계는 initial SSR DOM에 남음 | BLOCKER | 성공한 읽음 뒤에도 새 위험/복구 합계가 오래된 값으로 보임 |
| browser/test_operator_refresh.py visible cadence case | request/source time/body PASS가 header summary 전환을 검사하지 않음 | WARNING | 전체1412 green이 실제 header refresh 동작을 보증하지 않음 |
| pyproject.toml requires-python | metadata>=3.10 및 실제 StrEnum/runtime 간 범위 차이 | INFO | 실제 검증은3.14.3만; 지원하지 않은 interpreter 동작을 주장하지 않음 |

Inversion/Confirmation Bias Counter를 적용해 (1) 합계가 제한/범위에서 실패할 가능성, (2) 새로고침의 본문 테스트가 헤더를 놓칠 가능성, (3) 실패/uncertain dispatch가 자동 복구/재전송될 가능성을 대조했다. 앞의 두 건은 실제 실패로 입증했고 세 번째는 crash UNKNOWN·no replay·positive source recovery 행동 테스트로 반증했다. 단순히 테스트 총수에 기대어 PASS하지 않았다.

## 사람 확인 필요 — WARNING

### 1. 한국어 운영 화면의 시각적 사용성

**검사:** 결함 수정 후 현실적인 저장 증거로 안전 개요·네 탐색 그룹·계좌/주문/검증 상세를 PC와 휴대폰에서 밝음/어두움 테마로 검토한다. 000660, UNKNOWN/INCOMPLETE, stale/failed와 원천 시각을 읽는다.  
**기대:** 색 없이 위험과 증거 한계를 이해하며 상세·보고서·읽음 작업을 찾을 수 있다.  
**사람이 필요한 이유:** computed contrast/44px/keyboard/zoom 통과는 실제 한국어 이해/사용성 수용을 대신하지 않는다. 14-12 PLAN과 VALIDATION이 끝 단계 사람 확인으로 명시했다.

### 2. 조건부 실제 사설 휴대폰 접속

**검사:** 소유자가 별도로 VPN/HTTPS/인증서/방화벽/host-origin-single proxy를 명시 구성한 경우에만 runbook의 실제 모바일 데이터→사설 VPN→HTTPS 체크를 수행한다. PC 세션을 유지한 채 휴대폰 로그인·독립 logout·12h 만료를 확인한다.  
**기대:** 사설 경로+앱 인증이 모두 필요하고 인증서 오류를 우회하지 않으며 공개 접근은 생기지 않는다.  
**사람이 필요한 이유:** 이 검증은 actual network topology/phone provisioning을 다루지 않는다. 선택적 배포가 없는 상태 자체는 구현 gap이 아니며 이 항목은 거래·LLM·Discord 발송 권한을 추가하지 않는다.

## Gap 요약과 후속 경계

G-1은 정확한 CRITICAL 범위 합계/constituent 선택, G-2는 그 합계의 성공한 refresh DOM 소비 연결이다. 두 건은 동일 안전 요약에서 드러나지만 서버 선택과 클라이언트 갱신이라는 별도 원인이므로 각각 고쳐야 한다. report/export/ack/observer의 금지 권한 경계와 소스 불변성 검증은 유지해야 한다.

후속 ROADMAP Phase15의 unattended scheduling/leader locking/worker recovery/pause·kill과 Phase16의 manual real-money pilot는 이 합계·DOM 오류를 구현한다고 구체적으로 약속하지 않는다. G-1/G-2는 뒤 단계로 유보하지 않았다. `roadmap.analyze`는 활성 v1.1 구간만 반환해14 이후를 생략하므로 전체 ROADMAP 원문15/16 성공 기준도 직접 확인했다. 현재 Phase14를 complete로 표시하거나 문서를 commit하지 않았다. 구조화한 gaps는 `$gsd-plan-phase --gaps` 또는 승인된 좁은 수정 뒤 재검증의 입력이다.

---

_검증자: gsd-verifier · 독립 goal-backward 검증 · 2026-10-02T09:45:35Z_
