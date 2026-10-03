---
phase: 14-operator-dashboard-alerting
verified: 2026-10-02T10:08:10Z
status: passed
score: 36/36 must-haves verified
behavior_unverified: 0
overrides_applied: 0
verification_head: a1fc4836c55c3db6a2c82d574c014575b58d1882
human_acceptance_recorded: 2026-10-03
human_acceptance_source: 14-UAT.md
re_verification:
  previous_status: gaps_found
  previous_score: 34/36
  gaps_closed:
    - "G-1: 정확한 등록 범위 CRITICAL 합계와 동일 구성 행/상세 선택"
    - "G-2: saved refresh의 안전 헤더 합계·링크 갱신"
  gaps_remaining: []
  regressions: []
gaps: []
human_verification:
  - test: "한국어 운영 화면의 시각적 사용성 검토"
    result: passed
    expected: "안전 개요의 우선순위, 네 탐색 그룹, 모바일 상세, 밝음/어두움 테마에서 미해결 000660·UNKNOWN·INCOMPLETE·원천 관측 경과를 색에 의존하지 않고 이해할 수 있다."
    why_human: "Chromium의 계산된 대비·레이아웃·키보드·200% 확대 증거는 존재하지만 운영자가 한국어 문구와 현실적인 저장 증거의 읽기 편의성을 수용했는지는 자동화로 판정할 수 없다. 14-12에서 이 확인을 단계 말에 유보했다."
  - test: "조건부: 소유자가 사설 VPN/HTTPS를 명시적으로 구성한 경우 실제 휴대폰 모바일 데이터 접속 확인"
    applicability: not_configured_yet
    disposition: deferred_until_Tailscale_deployment
    expected: "사설 경로로만 접속하고 정상 HTTPS 인증서를 사용한다. 앱 로그인이 필수이고 Secure/HttpOnly/SameSite cookie 및 PC/휴대폰 독립 세션·로그아웃·절대 12시간 만료가 유지된다. 기본 PC loopback과 공개 미노출도 확인한다."
    why_human: "실제 VPN·인증서·방화벽·휴대폰은 합성 로컬 테스트 밖이다. 선택적 미구성 배포는 구현 gap이 아니며 휴대폰 도달성·실제 배포를 검증했다고 주장하지 않는다."
---

# Phase 14: 운영 웹 UI·대시보드·알림 검증 보고서

**Phase Goal:** Operators can use an authenticated responsive web application to inspect portfolio, decision, order, validation, report, and worker-health evidence and handle non-trading operational workflows without granting the web process trade authority.

**검증 시각:** 2026-10-02T10:08:10Z
**상태:** passed — 현재 적용 사용자 확인 완료, 선택적 Tailscale 배포 수용은 구성 후 확인
**재검증:** 예 — 최초 두 gap의 수정 후 좁은 독립 재검증
**기준:** HEAD `a1fc4836c55c3db6a2c82d574c014575b58d1882`

두 구현 결함이 해소되어 36/36 자동 검증 진실이 VERIFIED이다. 정확한 CRITICAL 합계와 동일 구성 행 선택, 성공한 새로고침의 헤더 갱신을 독립적으로 확인했다. 2026-10-03 사용자가 한국어 화면 사용성을 수용했고 향후 외부 접속 방식으로 Tailscale을 선택했다. 현재 미구성인 실제 접속 항목은 원래 조건에 따라 적용 범위 밖의 배포 후 수용 검사로 보존하여 전체 상태를 passed로 확정했다. 실제 Tailscale 접속을 통과했다고 주장하지 않는다.

## 검증 범위와 증거 출처

AGENTS.md, config, REQUIREMENTS, 전체 ROADMAP의 14/15/16 경계, 14개 PLAN과 SUMMARY, D-01–D-16 CONTEXT, 승인된 UI-SPEC, RESEARCH의 실제 위험, VALIDATION의 실행 관측 및 11/12/13 VERIFICATION을 대조했다. 프로젝트 skill 인덱스에는 이번 코드 검증에 추가 적용할 품질 rules가 없다. 현재 GSD 실행 단계의 검증 산출물만 작성했으며 코드·테스트·STATE·ROADMAP·REQUIREMENTS·VALIDATION은 변경하지 않았다.

최초 검증 당시 부모 실행 증거는 전체 명령 `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q`의 **1412 passed / 320.01s**이다. 이 최초 실행은 당시 최종 소스 변경 후 이루어졌으며 Chromium UI 16건·refresh 12건과 이전 검증에 참조된 현존 37개 테스트 파일을 포함한다. 전체 suite를 반복하지 않았다. 테스트 본문과 실제 호출 경로를 읽고, 본 검증 프로세스에서 별도 capability probe와 상태 불변식 spot-check를 실행했다. 전체 회귀 통과를 합계 정확성의 증거로 대체하지 않았다.

이번에는 기존 보고서(commit 4c7fa73), 14-12-SUMMARY/14-VALIDATION의 마지막 follow-up 및 RED 1af0c88/GREEN e457357의 실제 변경을 대조했다. 현재 마지막 소스/테스트 변경 후 부모 전체 실행은 **1418 passed / 336.19s**, 관련 route/security/UI/browser는 **153 passed / 50.23s**, 추가 경계는 **7 passed / 6.91s**이다. 검증자는 전체 suite를 반복하지 않고 아래 네 named tests(첫 항목 네 parameter cases)를 별도 실행하여 **7 passed / 7.12s**를 확인했다. 변경 없는 기존 34개 VERIFIED는 변경 영향만 검토했다.

실행 인터프리터는 Python 3.14.3이다. `requires-python >=3.10`만으로 StrEnum이 필요한 3.10 호환성을 주장하지 않는다. 운영자 원천 DB·.env·자격 증명·KIS·LLM·실제 Discord를 사용하지 않았고 서비스/배포/거래를 실행하지 않았다. 결함 재현은 TemporaryDirectory의 합성 원천과 운영 DB, Flask test client 및 모든 요청을 test-client 응답으로 fulfill하는 Chromium route를 사용했다. 재현용 서버는 시작하지 않았다.

## 목표 달성

### 관찰 가능한 진실

다섯 ROADMAP 계약을 먼저 유지하고 PLAN의 50개 진실 중 의미상 중복인 화면·인증·상세·테마·수출 주장을 합쳤다. 아래 36개 항목은 PLAN이 ROADMAP 범위를 줄이지 않도록 구성한 합집합이다. VERIFIED는 존재·실질 구현·호출 연결을 확인했고 상태 전환은 이름 있는 행동 테스트를 읽고 통과 증거를 확인했다. FAILED는 BLOCKER이다. 시각 사용성/실제 선택적 네트워크 확인은 별도 WARNING 사람 항목이며 자동화된 화면 존재나 반응형 동작과 혼동하지 않는다.

| # | 진실 | 판정 | 실제 증거 |
|---|---|---|---|
| 1 | SC-1: 한국어 PC/모바일에서 계좌·보유·후보·판단·주문·체결·실행·보고서·Replay·Soak·보정·준비도·작업 상태를 확인한다. | VERIFIED | `web_app.OPERATIONAL_VIEWS`, validation/report/alert routes, `base.html`의 17개 경로; `test_every_destination_detail_theme_contrast_and_mobile_targets`가 1280/390/320×두 테마에서 실제 이동·상세를 검사. 백테스트/Shadow도 포함. |
| 2 | SC-2: 표시 합계가 정확한 durable 구성 증거로 연결되고 UNKNOWN/INCOMPLETE를 유지한다. | VERIFIED | 새 incident_selection이 등록 resource/account/target·active·severity 조건을 COUNT/LIMIT 전에 적용한다. 정확한101건/혼합 범위/같은 구성 페이지와 상세/UNKNOWN 독립 행동 검사 통과. G-1 해소. |
| 3 | SC-3: 보고서 생성·수출·알림 읽음이 인증·권한·CSRF·감사 기록을 요구한다. | VERIFIED | 전역 `guard`, `generate_report`, `owned_artifact`, `acknowledge_alert`; route/method/expired/download 보안 matrix와 actor-owned artifacts·transactional action audit. |
| 4 | SC-4: 심각도 기반 중복 제거·증거 연결 알림이 실패/오래된 작업·미해결 주문·래치·브로커 차이를 포괄한다. | VERIFIED | `AlertDetector.detect/_record/_worker`, `AlertStore.observe`, saved stream/subject joins; detector family/strict stale boundary/positive recovery, episode/revision/producer receipt 테스트. 헤더 합계/갱신도 #2/#34에서 재검증 통과. |
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
| 20 | D-12: 기본 오늘은 KST이며 기간 필터가 all-date 000660·활성 위험을 숨기지 않는다. | VERIFIED | `PeriodSelection`, `_unresolved`, safety blocks 별도; today/custom native route/browser tests. 새 활성 합계/페이지도 all-date 조건을 유지한다. |
| 21 | 계좌·대상·원천 시간이 확실히 귀속되고 snapshot constituent/watch joins가 정확하다. | VERIFIED | same snapshot_id holdings/orders/fills, watch_iterations.snapshot_id join, `_check_run` scope conflict rejection; 본 검증 worker join/strict stale boundary 통과. |
| 22 | D-16: TXT/JSON/CSV가 IDs·scope·정밀도·분모·UNKNOWN·모의/advisory 의미와 안전한 spreadsheet profile을 보존한다. | VERIFIED | `serialize_report`, Decimal exact JSON, CSV NFKC/control/formula-prefix neutralization·identity-as-text; actual download parsing 및 byte/row/period caps. |
| 23 | 모든 validation metric은 excluded/unknown 포함 동일 선택의 constituent rows로 연결된다. | VERIFIED | `SavedReportProjection.metric_detail`, constituent ID subset checks, `_daily/_replay/_backtest/_shadow/_soak/_calibration/_readiness`; same selector/native metric links. 헤더 CRITICAL 선택도 #2에서 재검증 통과. |
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
| 34 | D-09: 30초/수동 saved refresh가 요약을 갱신하고 timeout/no overlap/source time 분리를 지킨다. | VERIFIED | replaceStatus가 same-origin /alerts 링크를 검증해 같은 헤더 노드의 text/href를 갱신한다. 실제 Chromium 수동 worsening·30초 recovery·scope 변경·dirty deferred 갱신 통과. 기존 timeout/no overlap/source time 증거 유지. G-2 해소. |
| 35 | D-10: dirty form·focus·selection·disclosure·scroll·last success 및 expiry/back hide/no POST replay를 보존한다. | VERIFIED | operator.js dirty/defer/apply·AbortController·restorePending·sessionEnded; 12개 real refresh tests가 실제 DOM·fake time·action failure를 검사. |
| 36 | 기존 평가 API는 실행 측에 남고 saved 소비자의 schema/identity/UNKNOWN 계약은 fail closed다. | VERIFIED | calibration.evaluate_variants의 original replay path, shadow preparation strict execution checks, legacy re-export, saved family owner-schema/forged-link tests; 이전11–13 regression은 현재 전체1418 실행에도 포함. |

**점수:** 36/36 진실 VERIFIED. 두 초기 FAILED는 해소되었다. PRESENT_BEHAVIOR_UNVERIFIED는 0이며 override는 없다. 현재 적용 사용자 확인이 수용되어 passed로 확정했고, 미구성인 선택적 실제 Tailscale 접속 검사는 배포 후 조건부 항목으로 보존했다.

### PLAN must-have 추적

각 배열의 번호는 PLAN frontmatter의 truths 순서다. 같은 ROADMAP 계약/구현 진실을 반복하는 항목은 위 번호로 중복 제거했다. 전 단계 E2E 주장은 실제 구성 진실/행동 증거로 판단하며 task-complete만으로 통과시키지 않는다.

| PLAN | truths → 위 항목 | 결과 |
|---|---|---|
| 14-01 | 1→6 | VERIFIED |
| 14-02 | 1→7; 2→8 | VERIFIED |
| 14-03 | 1→9; 2→10 | VERIFIED |
| 14-04 | 1→11; 2→12; 3→13/22 | VERIFIED |
| 14-05 | 1→14; 2→15; 3→16; 4→17; 5→18 | VERIFIED |
| 14-06 | 1→19; 2→2/21/23; 3→20; 4→21 | VERIFIED — G-1 해소 |
| 14-07 | 1→22; 2→9; 3→23 | VERIFIED |
| 14-08 | 1→24; 2→25; 3→26 | VERIFIED |
| 14-09 | 1→27; 2→28; 3→4; 4→29 | VERIFIED |
| 14-10 | 1→30; 2→31; 3→32; 4→33; 5→21/23; 6→3 | VERIFIED (운영 source totals와 안전 헤더 #2는 구분) |
| 14-11 | 1→34; 2→19/35; 3→27; 4→25/3; 5→22/3; 6→1/23/12 | VERIFIED — G-2 해소 |
| 14-12 | 1→1–36; 2→14/17; 3→31; 4→33; 5→5/18 | 구현 VERIFIED — G-1/G-2 해소; 시각/선택적 네트워크 human 항목 별도 |
| 14-13 | 1→9; 2→10/22; 3→18/36 | VERIFIED |
| 14-14 | 1→31/32; 2→33; 3→7/1 | VERIFIED |

### 필수 산출물 — 존재·실질 구현·연결

`verify.artifacts`를 14개 PLAN에 각각 실행했다. 선언된 87개 artifact 참조는 모두 존재하며 도구의 line/pattern 검사는 통과한다. 이것만으로 목표를 통과시키지 않았다. 아래 호출/데이터 흐름을 별도로 확인했고 web_app/JS의 초기 구현 결함과 현재 해소 근거를 명시했다. 테스트 파일은 해당 test/fixture의 실제 호출·assertion과 pytest 수집/최종 실행 연결을 확인했다.

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
| web_app.py; login/overview/list/detail/validation/reports/alerts templates; routes/security/alert-route tests | guarded SSR/API, native actions/source details; 등록 triple 조건의 exact COUNT/bounded page | VERIFIED — G-1 해소 |
| base.html/macros.html/operator.css; test_web_ui_contract | 17-route shell·escaped bounded facts·responsive system themes·44px native targets | VERIFIED; critical-count는 같은 범위·CRITICAL/active selector 보존 |
| operator.js; browser/test_operator_refresh | saved cadence/abort/cache/dirty/expiry DOM wiring; 같은 헤더 node 갱신 | VERIFIED — G-2 해소 |
| test_web_capabilities/test_web_security/test_operator_integration/browser/test_operator_ui | 실제 호출 before-import/negative source invariance/security/mobile/contrast assertions | VERIFIED; exact totals/헤더 refresh 회귀 assertion 추가 |
| docs/operator-runbook.md/test_web_packaging | exact local/private config·independent monitor lifecycle·offline installed wheel | VERIFIED; 실제 network/한국어 사용성은 human |

### 핵심 연결

PLAN의 key-links 46개는 대부분 `"portfolio snapshot totals"`, `"every screen/action"`처럼 설명형 from/to이며 실제 파일 경로가 아니다. 기계 `verify.key-links`는 0/46으로 보고한다. 이를 46개 제품 미연결로 오판하거나 통과 도구 결과로 대체하지 않고 실제 파일/호출/행동을 수동 추적했다.

| 연결 | 실제 호출 경로 | 판정 |
|---|---|---|
| approved package set→installed extras/browser | 14-01 gate→pyproject exact pins→test_operator_setup metadata/actual launch | WIRED |
| shared pure schema/DTO→saved consumers | reporting/backtest/shadow/calibration/soak imports→pure contracts/validators, compatibility re-exports | WIRED |
| snapshot totals→holdings/orders/fills | ReadOnlyPortfolioRepository.account(sid)→same snapshot_id→EvidenceSelection→native list/record/evidence | WIRED |
| watch iteration→portfolio snapshot/worker | watch_iterations.snapshot_id JOIN snapshots→source observation/cadence→WorkerDTO | WIRED |
| all-date unresolved/safety→overview/orders/alerts | _unresolved/_safety_blocks separate from period→overview/orders; detector streams→episodes | WIRED; 새 header exact selection도 확인 |
| registered report request→saved builders→exact metrics | fixed ReportRequest/catalog→project→family builder→metric_detail same ID selection | WIRED |
| actor-owned artifact→generated bytes/download | pinned dir_fd·opaque sealed ID→metadata+audit transaction→load_owned_artifact→guarded download | WIRED |
| durable observation→episode/revision/read | unique source key·subject→observe→expected_revision ack→actor/time/note, source unchanged | WIRED |
| producer event→delivery history | observation subject→receipt→unique producer link; missing delivery UNKNOWN | WIRED |
| outbox→bounded transport | committed claim→send→finalize; crash→UNKNOWN/no blind resend; CRITICAL due window | WIRED |
| explicit alerts CLI→foreground lifecycle | once/watch/status→independent monitor; request factory has no start invocation | WIRED |
| every page/action→auth/CSRF/audit | global before_request + method guards→saved routes/actions + store audit | WIRED |
| native shell→secure pages→Chromium/package | extends base/macros+packaged CSS/JS→17 routes→mobile/no-JS/installed-wheel probes | WIRED |
| saved refresh response→safety header | JSON/rendered_html→replaceStatus→same-node critical-count text/href; dirty defer에도 적용 | WIRED — G-2 해소 |

### 데이터 흐름 — Level 4

| 렌더 산출물 | 표시 데이터 | 원천/선택 | 판정 |
|---|---|---|---|
| overview/account/holdings | cash/total/holdings/orders/fills | registered readonly portfolio SQL→one complete snapshot→same snapshot rows; last complete time/cache failure label | FLOWING |
| candidates/decisions/orders/fills/runs/record/evidence | saved rows/reasons/order progression/IDs | fixed consumed SQL fields→positive resource scope→stable ID/selection→escaped bounded DTO | FLOWING |
| workers/source metadata | lifecycle/expectation/cadence/actual observation/lease age | saved transitions/watch/snapshot joins; lease 단독으로 건강을 증명하지 않음; no observation/cadence→UNKNOWN | FLOWING |
| validation/report metrics | result rows/denominators/exclusions/unknowns | validated saved files/readonly owners + registered proof facts→metric constituent selection | FLOWING; missing proof typed UNKNOWN |
| alerts/detail | subject/revision/count/duration/read/recovery/attempt history | operational episodes + append-only durable source sequence + source ID links | FLOWING |
| overview/header CRITICAL | active count/incident links | 등록 triple/active/severity→readonly exact COUNT→same-selector bounded page/detail | FLOWING — G-1 해소 |
| JS refreshed header CRITICAL | new saved count/link | API rendered HTML→replaceStatus→기존 header node 갱신 | FLOWING — G-2 해소 |

빈 Jinja extension block·initial nullable field·unknown model/rank/mark·없어진 source·미등록 saved proof는 stub으로 판정하지 않았다. 실제 reader가 가능한 데이터를 채우며 unavailable을 구체적으로 표시한다. 초기 합계 결함은 source selection/DOM wiring 오류였으며 이번에 수정·재검증했다. 원천들마다 독립 관측·트랜잭션이며 한 번의 cross-database atomic snapshot이라고 주장하지 않는다.

### 행동 spot-check 및 초기 실패 재현 이력

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
| 101 distinct active CRITICAL | TemporaryDirectory + registered portfolio subjects + AlertStore.observe + authenticated Flask GET / | SQL COUNT=101; HTTP200; HTML `미해결 CRITICAL · 100` | 초기 FAIL — G-1 (현재 해소) |
| newer unrelated scope100 + valid scoped1 | same fixture; scoped saved subject first, clock+1s then foreign/real100 | HTTP200; actual scoped1; HTML `미해결 CRITICAL · 0` | FAIL — G-1 |
| safety header consumes successful refresh | real Chromium, page.route fulfill of test-client responses (no server); initial0→save1→manual button→success status | header0 remains; same fresh GET HTML1 | 초기 FAIL — G-2 (현재 해소) |

실제 browser 28건의 기존 테스트 본문을 검토했다. cadence/timeout/hidden/no overlap/dirty/focus/disclosure/cache/expiry/no-POST-replay는 직접 상태를 assert한다. 최초 `test_visible_cadence_manual_and_source_time`만으로는 G-2를 반증할 수 없었다. 새 회귀 테스트가 실제 안전 헤더 전환을 직접 assert하며 이번 독립 실행에서 통과했다.


### 현재 독립 재검증 — G-1/G-2 해소

동일 `P` 명령에 아래 네 nodes와 `--browser chromium`을 지정했다. 결과 **7 passed / 7.12s**, exit0이다. 첫 실행의 잘못 추정한 browser node 이름은 collection exit4였고 올바른 node로 재실행했으며, 수집 오류는 행동 증거에 포함하지 않았다.

| Test node | 직접 확인한 동작 | 결과 |
|---|---|---|
| `tests/test_web_alert_routes.py::test_critical_total_exact_scoped_and_all_pages` | same 범위101; newer 다른 등록 원천/미등록/계좌·target 혼합 각 scoped1; COUNT 전에 등록 triple 필터; all-date CRITICAL active selector·bounded page·모든 unique 구성 detail·source bytes 불변 | 4 cases PASS |
| `tests/test_web_alert_routes.py::test_critical_storage_failure_is_unknown_and_filters_are_validated` | storage 실패 header UNKNOWN/ALERT_STORAGE_UNAVAILABLE, invalid severity/active400 | PASS |
| `tests/browser/test_operator_refresh.py::test_critical_header_tracks_saved_worsening_recovery_and_scope` | 실제 Chromium header1→manual worsening2→30초 recovery1→audit scope0; 같은 CRITICAL/resource 링크 | PASS |
| `tests/browser/test_operator_refresh.py::test_dirty_note_focus_disclosure_scroll_and_explicit_refresh` | dirty auto defer 중 header2; draft/focus/selection/disclosure/scroll/기존revision 보존; explicit refresh 후 새revision과draft 유지 | PASS |

`incident_selection`은 owner 검증 후 parameterized 등록 resource_id/account_hash/target와 active/severity를 SQL WHERE에 먼저 적용한다. COUNT/page IDs는 같은 readonly operational read transaction이며 active는 기간 제한을 적용하지 않는다. 저장소 오류는 UNKNOWN이다. cross-owner/source/detail 읽기 전체의 atomic snapshot을 주장하지 않는다. `replaceStatus`는 응답 href의 same-origin `/alerts`를 검증하고 같은 헤더 node의 text/href를 dirty defer 이전에도 갱신한다. 인증/CSRF·source readers·report serializers/artifact rollback·detector/observer/평가 API는 이 수정에서 변경되지 않았다.

### Probe 실행

`scripts/*/tests/probe-*.sh` 디렉터리/선언은 없다. 이 단계가 명시한 runnable probe는 `tests/capability_probe.py`이고 다른 dry-run으로 대체하지 않았다.

| Probe | 본 검증 실행 | 결과 | 판정 |
|---|---|---|---|
| fresh supported surface/source invariance | `P tests/test_web_capabilities.py::test_fresh_supported_surface_and_each_source_owner_invariant` | **1 passed / 19.04s**, child마다 before-import guard. factory/routes/all eight AVAILABLE families×TXT/JSON/CSV/ack/observer once+watch stop/status/CLI/malformed/missing source의 8 surface 실행 | PASS |
| existing per-family saved contracts | 최초1412 및 현재1418 실제 실행의 evidence/saved backtest/Shadow/calibration/soak named tests와 child code를 대조 | canonical identity·strict version/links·forgery·same-source inventories 검사 확인 | PASS — 부모 최종 실행 evidence, 본 검증 suite 반복 없음 |

### 요구사항 커버리지

PLAN 전체 frontmatter의 요구사항 합집합은 FUT-03/UI-01/UI-02/OPSV-01이며 REQUIREMENTS의 Phase14 매핑과 일치한다. orphaned requirement는 없다. REQUIREMENTS checkbox/상태는 본 검증이 수정하지 않았다.

| 요구사항 | 선언 PLAN | 구현 증거/의미 | 판정 |
|---|---|---|---|
| FUT-03 | 02/03/04/06/07/10/11/12/13/14 | authenticated Korean saved account/decision/order/report/health review가 구현됨. 안전 요약 exact count/refresh도 독립 재검증 통과 | SATISFIED — G-1/G-2 해소 |
| UI-01 | 02/04/06/07/10/11/12/14 | 17 destinations·source/detail·mobile/theme objective proof 존재. 정확한 표시 합계와 header refresh 회귀 검사 통과 | SATISFIED — 한국어 visual usability human pending |
| UI-02 | 01–14 | global authentication/authorization/CSRF/audit·read-only saved actions·authority absence·source-byte invariance·secure local/private config | SATISFIED (실제 optional private network 수용은 조건부 human) |
| OPSV-01 | 02/06/08/09/11/12 | durable severity/dedup/evidence-linked occurrence/worsening/recovery/critical reminders·producer ownership·explicit observer 구현 입증 | SATISFIED — detector/delivery 경로; 안전 헤더도 동일 범위 합계/refresh 확인 |

### 금지사항과 안전 회귀

12개 PLAN(02–13)의 같은 prohibition은 source mutation/migration 및 broker/live provider/trading Settings/policy/gate-waiver capability 취득 금지이다. 레거시 frontmatter가 string 항목이며 별도 verification tier 필드는 없지만 deterministic enforcement가 실제로 연결되어 있다: fresh process forbidden import/constructor/env/socket/source SQL/file trap, route capability matrix, per-action bytes/schema/logical row inventories. 이 부정 검증이 PASS하므로 silent judgment 통과나 enforcement 없는 test-tier green이 아니다. 선언된 judgment-tier prohibition/override는 없다.

Phase11의 snapshot/lease/notification evidence 안전 계약, Phase12 modeled accounting/ledger ID, Phase13 frozen shadow provenance 경계를 확인했다. 현재 웹은 lease를 읽기만 하며 갱신/복구/주문을 얻지 않는다. 읽음과 routine completion은 freeze/latch recovery 증명이 아니고 readiness는 수동승격 권한을 부여하지 않는다. 현존 과거37 test-file refs가 부모 최종 전체 회귀에 포함되어 이전 검증 문서의 PASS 주장만을 증거로 삼지 않았다.

### Anti-pattern / 반증 관측

PLAN artifact/key-file 집합(79개 경로)의 source/test 텍스트에서 unreferenced TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER marker는 발견하지 않았다. empty/default 상태는 실제 상위 writer/reader 사용을 추적했다. 신규 금지된 source write나 raw-secret surface는 발견하지 않았다.

| 파일/위치 | 패턴 | 심각도 | 영향 |
|---|---|---|---|
| web_app.py / operator.js | 최초 LIMIT/filter order와 header wiring 결함 | 해소된 이력 | 현재 exact selector/count 및 실제 header 전환 회귀 tests 통과 |
| pyproject.toml requires-python | metadata>=3.10 및 실제 StrEnum/runtime 간 범위 차이 | INFO | 실제 검증은3.14.3만; 지원하지 않은 interpreter 통과를 주장하지 않음 |

최초 반례는 보고서 commit4c7fa73와 RED1af0c88에 보존된다. GREENe457357의 실제 수정과 이번 독립 행동 실행이 두 반례를 해소했다. 이번 수정 diff에서 새 debt marker/stub/금지된 source write/raw secret를 발견하지 않았다. 기존 34개 VERIFIED의 변경 영향 검토와 부모 최종1418 회귀에서 새로운 회귀는 발견되지 않았다.

## 사람 확인 결과 — 2026-10-03

### 1. 한국어 운영 화면의 시각적 사용성

**결과:** PASS. 사용자는 검토 화면 제시 후 “좋아 완료 된거야?”라고 응답했고 14-UAT.md에 수용을 기록했다.

**검사:** 현실적인 저장 증거로 안전 개요·네 탐색 그룹·계좌/주문/검증 상세를 PC와 휴대폰에서 밝음/어두움 테마로 검토한다. 000660, UNKNOWN/INCOMPLETE, stale/failed와 원천 시각을 읽는다.
**기대:** 색 없이 위험과 증거 한계를 이해하며 상세·보고서·읽음 작업을 찾을 수 있다.
**사람이 필요한 이유:** computed contrast/44px/keyboard/zoom 통과는 실제 한국어 이해/사용성 수용을 대신하지 않는다. 14-12 PLAN과 VALIDATION이 끝 단계 사람 확인으로 명시했다.

### 2. 조건부 실제 사설 휴대폰 접속

**적용 여부:** 현재 미구성으로 비적용. 사용자는 “vpn은 아니고 tailscale 이용해서 밖에서도 폰이나 맥으로 접속하게 할려고 하거든”이라고 향후 접속 방식을 선택했다. 실제 Tailscale/HTTPS 구성과 휴대폰·맥 접속 검증은 배포 후 수행한다. 조건부 항목을 실제 접속 PASS로 기록하지 않았다.

**검사:** 소유자가 별도로 VPN/HTTPS/인증서/방화벽/host-origin-single proxy를 명시 구성한 경우에만 runbook의 실제 모바일 데이터→사설 VPN→HTTPS 체크를 수행한다. PC 세션을 유지한 채 휴대폰 로그인·독립 logout·12h 만료를 확인한다.
**기대:** 사설 경로+앱 인증이 모두 필요하고 인증서 오류를 우회하지 않으며 공개 접근은 생기지 않는다.
**사람이 필요한 이유:** 이 검증은 actual network topology/phone provisioning을 다루지 않는다. 선택적 배포가 없는 상태 자체는 구현 gap이 아니며 이 항목은 거래·LLM·Discord 발송 권한을 추가하지 않는다.

## 현재 결론과 후속 경계

G-1의 정확한 CRITICAL 범위 합계/구성 선택과 G-2의 성공한 refresh DOM 연결은 해소되었다. 현재 열린 구현 gap은 없으며 canonical `gaps: []`이다. 기존 report/export/ack/observer의 권한 부재와 원천 불변성 경계도 유지된다.

초기 결함은 Phase15/16로 유보하지 않고 이 단계 안에서 수정했다. 2026-10-03 현재 적용 한국어 사용성 UAT가 수용되어 passed로 확정했다. 미구성인 Tailscale 외부 접속의 실제 장치 수용 검사는 배포 후 항목으로 남는다. 독립 검증의 기존 실행 근거와 소스 기준 HEAD는 보존했으며, 부모가 사용자 수용 결과만 추가했다.

---

_검증자: gsd-verifier · 좁은 독립 재검증 · 2026-10-02T10:08:10Z_
