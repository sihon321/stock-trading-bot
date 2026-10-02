# 모의투자 일일 운영 런북

이 문서는 KRX 모의투자 운영자가 저장된 감사 증거를 기준으로 하루의 수동 실행을 시작하고 끝내는 절차다. 모든 시각은 KST(Asia/Seoul) 기준이다. 명령은 프로젝트의 활성 가상환경에서 `bot` 진입점을 사용할 수 있게 한 뒤 실행한다.

## 일일 수동 운영 절차

아래 순서는 운영자가 직접 실행하는 수동 절차이며 예약 실행이나 스케줄링이 아니다. 09:05 화면은 미리보기이고, 09:10 실행은 후보를 새로 선별하므로 두 후보 목록의 차이도 정상적인 감사 대상이다.

| KST | 수동 명령 | 목적 | 완료 조건 |
|---|---|---|---|
| 08:50 | `bot status` | 실행 허가가 아닌 개장 전 준비 상태를 관찰한다. | 정상 거래일이면 `PRE_OPEN`, `KRX_SESSION_BLOCKED`/`BLOCK`, `실행 가능: 아니오`를 확인하고, 모의투자 대상·감사 건강성·미해결 주문 스캔은 각각 `PASS`인지 확인한다. |
| 09:05 | `bot screen` | 당일 후보를 미리 본다. 주문은 제출하지 않는다. | SCREEN 실행과 각 후보 결과가 감사 DB에 terminal 증거로 남는다. |
| 09:10 직전 | `bot status` | 09:00 이후 실제 실행 가능 상태를 새로 확인한다. | `CONTINUOUS`, `KRX_SESSION_OPEN`/`PASS`, 모든 전역 중단 점검 `PASS`, `실행 가능: 예`를 확인한다. |
| 09:10 | `bot run` | 실행 시점의 새로운 screen 결과로 평가 주기를 시작한다. 기본은 dry-run이며 주문이 필요한 모의투자 실행만 명시적으로 `--execute`를 쓴다. | 출력된 `run_id`를 기록하고 실행이 terminal 상태가 될 때까지 확인한다. |
| 즉시 | `bot report daily` | 현재 KST 거래일의 실행·티커·주문·알림 증거를 직접 검토한다. | 아래 완료 판정의 모든 항목을 충족한다. |

날짜를 다시 확인할 때는 `bot report daily --date YYYY-MM-DD`를 사용한다. 파일 보관이 필요하면 `--output 경로`를 붙인다. 터미널과 파일은 동일한 UTF-8 문서이며, 기존 파일의 내용이 다르면 덮어쓰지 않고 실패한다.

### 08:50 사전 점검 판정

`bot status`는 모의투자 대상, 감사 저장소 건강성, KRX 거래일·연속매매 세션, 로컬 미해결 주문 스캔을 `PASS`, `BLOCK`, `UNKNOWN`으로 표시한다. `UNKNOWN`은 성공으로 추정하지 않는다. 08:50 점검은 실행 허가가 아니라 개장 전 준비 상태 관찰이다.

- 정상 거래일 08:50에는 `PRE_OPEN`, `KRX_SESSION_BLOCKED`/`BLOCK`, `실행 가능: 아니오`가 예상된다. 이때도 `MOCK_TARGET_CONFIRMED`, `AUDIT_HEALTHY`, `UNRESOLVED_SCAN_CLEAR`는 각각 `PASS`여야 하며, 이 준비 상태만으로 `bot run`을 허가하지 않는다.
- 09:00 이후 09:10 실행 직전에 `bot status`를 다시 실행한다. `CONTINUOUS`, `KRX_SESSION_OPEN`/`PASS`, 모든 전역 중단 점검 `PASS`, `실행 가능: 예`가 모두 확인될 때만 `bot run`으로 진행한다.
- `MOCK_TARGET_BLOCKED`, `AUDIT_UNHEALTHY`, `KRX_SESSION_BLOCKED`, `UNRESOLVED_SCAN_UNKNOWN` 중 하나라도 전역 `BLOCK` 또는 `UNKNOWN`이면 `bot run`을 중단한다. `bot status`와 과거 `bot report ...` 읽기는 계속할 수 있다.
- `TICKER_FROZEN_UNRESOLVED_ORDER`는 전역 실행 중단이 아니라 표시된 티커만 동결한다. 로컬 증거만 확인한 상태이므로 KIS 원장이 확정됐다고 해석하지 않는다.

## 보고서 판독

`bot report daily`는 요약을 먼저 보여 주고 SCREEN/RUN별 모든 후보 상세를 실제 처리 순서로 보여 준다. 09:05 preview와 09:10 fresh run의 후보 차이는 숨기지 않고 비교한다. stable reason code와 한국어 설명을 함께 읽으며 `HOLD_SIGNAL`, `LOW_CONFIDENCE`, `STALE_OHLCV`, `STALE_QUOTE`, `MALFORMED_SIGNAL`, `LLM_TIMEOUT`, `KIS_UNAVAILABLE`, `DUPLICATE_ORDER`, `AMBIGUOUS_SUBMISSION`을 임의 문장으로 치환하지 않는다.

기간 확인은 `bot report period --from YYYY-MM-DD --to YYYY-MM-DD`를 사용하며 양 끝 KST 거래일을 모두 포함한다. 전체 분모와 determinate 분모, complete·incomplete·unknown을 서로 합치거나 누락하지 않는다. 실행 수명주기, 티커 완전성, 대상(mock/real), reconciliation, 알림 전달 상태는 별도 증거 차원으로 읽는다.

replay 확인은 `bot report replay 결과.json [추가-결과.json ...]`을 사용한다. 각 stable result ID와 검증 결과를 먼저 확인하고 fixture schema, policy, scenario/input basis가 같은 결과만 집계한다. 호환되지 않는 결과는 분리된 이유를 읽는다. replay는 의사결정 정책 경로를 검증할 뿐 수익성이나 투자 성과를 추정하지 않는다.

## 완료 판정

아래 다섯 조건을 모두 만족하기 전에는 그날의 운영이 끝난 것이 아니다.

- [ ] 실행 상태가 `COMPLETED` 또는 `COMPLETED_WITH_ERRORS`인 terminal 실행
- [ ] 시도한 각 티커에 정확히 하나의 terminal outcome
- [ ] 모든 주문 또는 no-trade 증거와 stable reason code 검토
- [ ] `AMBIGUOUS_SUBMISSION`이 없거나 장애 대응 절차로 공식 이관
- [ ] 알림 실패 시 `bot report daily` 직접 검토

`FAILED`, `INTERRUPTED`, `RUNNING`, 알 수 없는 수명주기나 누락된 티커 결과는 완료가 아니다. `ORDER_SUBMITTED`, `ORDER_SUPPRESSED`, `ORDER_RECONCILED`, `NO_TRADE`, `EXECUTION_ERROR`를 실행별로 확인하고 주문 의도와 broker/reconciliation 증거가 서로 귀속되는지 검토한다.

## 장애 대응표

표의 중단 범위와 해결 기준을 임의로 완화하지 않는다. 원시 provider 응답 대신 stable code와 정규화된 감사 증거를 사용한다.

| 장애 유형 | 증상/코드 | 중단 범위 | 확인 증거/명령 | 금지 행동 | 안전한 다음 조치 | 해결 기준 |
|---|---|---|---|---|---|---|
| STALE_DATA | `STALE_OHLCV, STALE_QUOTE` | 해당 실행의 자동 재시도를 금지하고 영향 티커 평가를 중단한다. | `bot report daily`에서 trading date, completed-bar cutoff, quote freshness, failed stage를 확인한다. | 오래된 값을 정상으로 간주하거나 자동 재실행하지 않는다. | 데이터 시각을 바로잡고 감사 건강성과 주문 미제출을 확인한 뒤 parent-linked 수동 실행을 검토한다. | 최신성 증거가 정책을 통과하고 이전 실행에서 주문 제출 가능성이 없음이 입증된다. |
| API_FAILURE | `KIS_UNAVAILABLE` | 현재 실패 티커를 중단하며 전역 preflight가 불확실하면 신규 거래 전체를 중단한다. | `bot status`와 `bot report daily`에서 preflight, failed stage, terminal outcome, order event를 확인한다. | POST 응답이 불명확한 상태에서 재호출하거나 자동 재실행하지 않는다. | 제출 전 실패가 확정된 경우에만 서비스 정상화 후 parent-linked 수동 실행을 검토한다. | 감사 증거가 정상이고 주문 미제출이 확인되며 preflight가 `PASS`다. |
| LLM_TIMEOUT | `LLM_TIMEOUT` | 실패 티커 평가를 중단하고 이미 처리된 형제 티커 증거는 보존한다. | `bot report daily`에서 `LLM` failed stage, terminal outcome, 주문 이벤트 부재를 확인한다. | timeout을 BUY/SELL로 추정하거나 자동 재실행하지 않는다. | 주문 미제출과 감사 건강성을 확인한 후 필요할 때만 parent-linked 새 run을 수동 시작한다. | 이전 run과 새 run의 연결이 남고 이전 run에 주문 제출 가능성이 없다. |
| AMBIGUOUS_SUBMISSION | `AMBIGUOUS_SUBMISSION, SUBMISSION_AMBIGUOUS` | 영향받은 티커만 즉시 동결하고 상태가 불명확하면 재개하지 않는다. | 로컬 order event와 KIS 주문·미체결·체결 증거를 `order_intent_id`로 대조한다. | blind resubmission과 같은 intent의 재사용을 금지한다. | broker truth를 확정하고 append-only reconciliation 증거를 기록한다. | `RECONCILED` 증거로 주문 상태가 determinate이며 동결 해제가 명시된다. |
| DUPLICATE_ORDER | `DUPLICATE_ORDER, DUPLICATE_CHECKED` | 중복 intent가 귀속된 티커만 동결한다. | 기존 intent, `duplicate_of_intent_id`, broker order/open/fill, reconciliation을 확인한다. | 중복 요청을 새 주문으로 재제출하지 않는다. | 중복을 기존 주문 의도에 연결하고 broker truth를 반영한다. | 기존 주문과 중복 관계 및 최종 상태가 append-only 증거로 확정된다. |
| NOTIFICATION_FAILURE | `TRANSPORT_EXCEPTION, TRANSPORT_FAILED` | 거래 결과는 바꾸지 않는 fail-soft지만 일일 완료 판정은 보류한다. | `bot report daily`에서 `FINAL_SUMMARY` 또는 ticker-scoped `IMMEDIATE_ERROR`의 `FAILED`를 직접 확인한다. | 알림 실패를 거래 실패나 성공으로 바꾸거나 보고서 검토를 생략하지 않는다. | terminal·ticker·주문 증거를 보고서에서 직접 검토한다. | 직접 검토가 끝나고 실패 알림 시도가 run/ticker에 정확히 귀속된다. |
| AUDIT_FAILURE | `AUDIT_UNHEALTHY, UNKNOWN, BLOCK` | 감사 불확실성이 해소될 때까지 신규 거래 전체를 중단한다. | `bot status`에서 schema, integrity, writability와 stable preflight code를 확인하고 과거 보고서만 읽는다. | 감사 누락 상태로 거래하거나 원시 DB를 임의 수정하지 않는다. | 백업·파일 권한·스키마 무결성을 조사하고 안전한 복구 절차로 증거 건강성을 회복한다. | `AUDIT_HEALTHY`와 `PASS`가 확인되고 증거 누락 가능성이 해소된다. |

## 단계별 복구 체크리스트

공통 규칙은 자동 재실행 금지와 blind resubmission 금지다. 새 실행은 감사 증거가 정상이고 주문 제출 가능성이 없음이 확인된 경우에만 운영자가 `bot run --parent-run-id <이전-run_id>`로 시작한다. 새 run은 새 `run_id`를 가지며 이전 증거를 덮어쓰지 않는다. 자격 증명, webhook, 원시 payload, 전체 예외 본문을 복사하지 않는다.

### STALE_DATA

1. 보고서의 `STALE_OHLCV` 또는 `STALE_QUOTE`, 관측 시각, cutoff, failed stage를 확인한다.
2. 이전 run의 terminal outcome과 order event에서 주문 제출 가능성이 없음을 확인한다.
3. 데이터 원천이 현재 정책 시각을 만족하고 `bot status`가 안전할 때만 parent-linked 수동 run을 검토한다.

### API_FAILURE

1. `KIS_UNAVAILABLE`의 failed stage가 데이터 조회인지 주문 경계인지 분리한다.
2. 주문 경계라면 미제출로 추정하지 말고 `AMBIGUOUS_SUBMISSION` 절차로 이관한다.
3. 제출 전 실패와 감사 건강성이 확정된 경우에만 parent-linked 수동 run을 검토한다.

### LLM_TIMEOUT

1. 해당 티커가 `LLM_TIMEOUT`, `EXECUTION_ERROR`이고 주문 이벤트가 없는지 확인한다.
2. timeout을 신호로 해석하지 않고 기존 terminal 증거를 보존한다.
3. 주문 미제출·감사 건강성 확인 후에만 parent-linked 수동 run을 검토한다.

### AMBIGUOUS_SUBMISSION

1. 영향받은 티커만 동결하고 형제 티커와 전역 상태를 구분한다.
2. `order_intent_id`를 기준으로 KIS 주문·미체결·체결 증거에서 broker truth를 확인한다.
3. `RECONCILED` reconciliation 증거를 append-only로 추가하고 상태가 determinate일 때만 동결을 해제한다.

### DUPLICATE_ORDER

1. 영향받은 티커만 동결하고 duplicate evidence의 `duplicate_of_intent_id`를 확인한다.
2. 중복을 기존 `order_intent_id`에 연결하고 재제출하지 않는다.
3. KIS 주문·미체결·체결 증거와 reconciliation이 최종 상태를 확정한 뒤에만 동결을 해제한다.

### NOTIFICATION_FAILURE

1. 알림 전송 실패는 거래 결과를 바꾸지 않는 fail-soft로 유지한다.
2. `bot report daily`에서 run-scoped `FINAL_SUMMARY`와 ticker-scoped `IMMEDIATE_ERROR`를 직접 검토한다.
3. terminal run, 티커 완전성, 주문/no-trade 증거 검토를 끝낸 뒤에만 일일 완료를 표시한다.

### AUDIT_FAILURE

1. 감사 불확실성은 신규 거래 전체 중단으로 처리하고 `bot run`을 실행하지 않는다.
2. `bot status`의 `AUDIT_UNHEALTHY`, `UNKNOWN`, `BLOCK`, schema/integrity/writability 사실을 확인한다.
3. 감사 저장소를 임의로 고치거나 누락 증거를 추정하지 않는다. `AUDIT_HEALTHY`와 `PASS`가 복원된 뒤 별도 안전 절차로 재개한다.

## 운영 범위와 금지선

다음 항목은 이 런북이 실행하거나 허가하는 범위가 아니다.

- 예약 실행·스케줄러·무인 자동 재실행
- 자동 주문 재제출과 blind resubmission
- 정책·설정 자동 변경
- 수익성·투자성과 주장
- 실계좌 전환 또는 자동 승격
- Phase 9 KIS 모의계좌 soak·장애 주입 실행

## Phase 9 인증 운영 순서

이 절차는 Phase 9 전용 수동 절차다. Plan 02의 인증된 GET-only compatibility probe를 먼저 실행하고, Plan 09에서 구현된 durable proof 경로는 Plan 10의 별도 외부 승인으로 이미 한 번만 실행되었다. 그 결과 `000660` acknowledgement는 성공으로 승격되지 않았으며 현재 `FROZEN`/non-credit이다. 아래 명령의 오류는 모두 exit code `2`로 fail closed한다.

| 순서 | 명령 | gate | 실패 exit |
|---|---|---|---|
| 1 | `bot soak start --campaign-id <campaign_id> --probe-only --fixture <compat.json>` | 인증된 mock GET 페이지가 모두 COMPLETE이고 fixture가 KIS_OBSERVED인지 확인한다. | `2` |
| 2 | `bot soak start --campaign-id <campaign_id> --accepted-profile <compat.json>` | 승인 profile, 독립 저장소, STARTUP reconciliation이 모두 통과해야 campaign이 ACTIVE다. | `2` |
| 3 | `bot status` | 09:00 이후 CONTINUOUS, mock target, audit health, 전역 PASS를 확인한다. | `2` |
| 4 | `bot soak status --campaign-id <campaign_id>` | credited/target, 가용성 budget, 영구 안전 래치, reconciliation, 동결, provenance별 drill 분모를 기록한다. | `2` |
| 5 | `bot soak run --campaign-id <campaign_id> --run-id <run_id>` | PRE_RUN 뒤에만 실행하며 각 accepted/ambiguous submission마다 POST_SUBMISSION을 정확히 한 번 수행하고 PRE_FINALIZE를 통과한다. | `2` |
| 6 | `bot soak status --campaign-id <campaign_id>` | 실행 직후 지정/비인정, reconciliation UNKNOWN, 활성 동결을 확인한다. | `2` |
| 7 | `bot soak resume --campaign-id <campaign_id>` | RESUME query-only reconciliation과 freeze 재구성만 수행하며 과거 POST를 재생하지 않는다. | `2` |
| 8 | `bot soak status --campaign-id <campaign_id>` | 복구 후에도 모든 독립 분모가 reconcile되는지 최종 확인한다. | `2` |

`bot soak status`는 KIS, LLM, pykrx, 주문 adapter를 만들지 않는다. primary audit, soak, controller의 서로 다른 파일을 각각 `mode=ro`, `query_only`, stable read transaction으로 읽으며 cross-database atomic snapshot을 주장하지 않는다.

## Phase 9 ambiguity와 동결

인증 proof의 `000660` BUY 1주는 broker order ID가 없고 최종 비교가 `UNKNOWN`이므로 `FROZEN`/non-credit이다. D-13에 따라 같은 intent를 재제출하지 않는다. 새로운 KIS 조회에서 same-subject determinate terminal broker evidence가 완전하게 저장된 경우에만 append-only release transition을 검토한다.

일반 soak에서 acknowledgement ambiguity가 생기면 영향 ticker만 동결하고 즉시 `bot soak status`로 UNKNOWN과 comparison을 기록한다. partial/no-fill은 remaining order가 terminal이 될 때까지 해당 ticker를 동결한다. 어느 경우에도 로컬 행의 부재를 broker 미접수로 해석하거나 자동 취소·재주문하지 않는다.

## Phase 9 fault drill 명령

각 명령은 controller contract의 durable commit과 독립 read-back 뒤 단 한 번만 fault를 활성화한다. D-20에 따라 CONTROLLED_INJECTION은 적격일, 가용성 budget, KIS_OBSERVED 성과에 산입하지 않는다.

| fault | 명령 |
|---|---|
| STALE_DATA | `bot soak drill stale-data --campaign-id <campaign_id>` |
| MALFORMED_LLM | `bot soak drill malformed-llm --campaign-id <campaign_id>` |
| LLM_TIMEOUT | `bot soak drill timed-out-llm --campaign-id <campaign_id>` |
| KIS_API_FAILURE | `bot soak drill kis-api-failure --campaign-id <campaign_id>` |
| ACCEPTED_THEN_TIMEOUT | `bot soak drill accepted-then-timeout --campaign-id <campaign_id>` |
| THROTTLING | `bot soak drill throttling --campaign-id <campaign_id>` |
| PARTIAL_OR_NO_FILL | `bot soak drill partial-or-no-fill --campaign-id <campaign_id>` |
| INTERRUPTION | `bot soak drill interruption --campaign-id <campaign_id>` |
| NOTIFICATION_FAILURE | `bot soak drill notification-failure --campaign-id <campaign_id>` |
| AUDIT_FAILURE | `bot soak drill audit-failure --campaign-id <campaign_id>` |

각 실행 뒤 `bot soak status --campaign-id <campaign_id>`에서 D-22의 containment, primary-audit link, 필요한 reconciliation/restart, prohibited-action 관찰이 모두 PASS인지 확인한다. `CONTROLLED_INJECTION`과 `KIS_OBSERVED`의 required/passed/failed/unknown은 별도 표로 읽고 합산하지 않는다.

## Phase 9 저장소 백업과 복구 순서

모든 mutable 명령을 먼저 중단한다. 세 저장소는 독립 owner이므로 하나의 복사본이나 cross-database transaction으로 취급하지 않는다. 정상 파일의 안전한 SQLite backup은 각각 `sqlite3 data/audit.db '.backup data/audit.backup.db'`, `sqlite3 data/soak.db '.backup data/soak.backup.db'`, `sqlite3 data/soak-controller.db '.backup data/soak-controller.backup.db'`로 만든다. WAL 파일만 복사하지 않는다.

복구 판정 순서는 다음과 같다.

1. controller: `data/soak-controller.db`를 query-only로 열어 integrity, committed contract, D-22 observation, terminal verdict 또는 pending restart token을 확인한다. controller 증거가 없으면 fault 성공을 주장하지 않는다.
2. primary audit: `data/audit.db`를 query-only로 열어 run, ticker outcome, order intent/event의 terminal 귀속을 확인한다. 누락 가능성이 있으면 신규 거래 전체를 중단한다.
3. soak: `data/soak.db`를 query-only로 열어 campaign, reconciliation, comparison, freeze, drill link를 확인한다. controller와 primary audit의 stable ID가 일치하지 않으면 UNKNOWN/FAIL로 유지한다.
4. 세 owner가 각각 정상인 뒤 `bot soak resume --campaign-id <campaign_id>`를 한 번 실행한다. 이것은 broker 조회와 freeze 재구성만 하며 order POST를 재생하지 않는다.
5. 마지막으로 `bot soak status --campaign-id <campaign_id>`를 실행해 controller → primary audit → soak 복구 결과와 D-22 분모를 다시 확인한다.

audit failure나 interruption 뒤에는 미완료 controller contract를 새 contract로 덮어쓰지 않는다. ambiguity/accepted-then-timeout이면 query-only broker truth가 determinate해질 때까지 D-13의 no resubmission을 유지한다.

## Phase 9 외부 완료 gate

첫 1일 gate는 실제 지정 거래일의 terminal mock RUN, 완전한 필수 reconciliation, 명시적 non-credit/credit 판정, 활성 동결 검토를 요구한다. 20 eligible days gate는 서로 다른 확인된 KRX 거래일 20개가 모두 credited이고 credited/target이 `20/20`이며 가용성 budget과 영구 안전 래치가 별도 상태로 남아 있어야 한다.

이 두 gate와 한 번의 proof order는 실제 외부 KIS 모의계좌 확인이다. unit test, fixture, replay, synthetic evidence는 대체할 수 없다. D-17에 따라 KIS_OBSERVED, CONTROLLED_INJECTION, SYNTHETIC provenance를 분리하고 CONTROLLED_INJECTION 성공 수를 clean-operation이나 KIS 관측 수에 더하지 않는다.

## Phase 9 범위 금지선

- 스케줄링
- 실계좌 promotion
- 정책 자동 변경
- 자동 재제출
- 수익성 주장
- 새 전략

## Phase 10 실거래 승격 준비도

순서는 증거 수집 → `bot report readiness` 실행 → `BLOCKED`/`READY` 검토 → 정책 snapshot 동결 확인 → rollback/kill 절차 확인 → 명시적 수동 승인 기록이다. 그 뒤의 `TRADING_MODE=real` 변경은 이 명령과 분리된 미래의 수동 재확인 절차이며, 현재 Phase 9 미완료·안전 실패는 waiver할 수 없으므로 `BLOCKED`다.

명령은 `bot report readiness --replay-result <result.json> --calibration-fixture <fixture.json> --audit-db <audit.db> --soak-db <soak.db> --controller-db <controller.db> --campaign-id <id> --policy-snapshot <policy.json> --rollback-ack --kill-ack --manual-approval`이다. 결과의 `assessment_id`와 `calibration_id`는 증거·정책·승인이 바뀌면 무효화되어 다시 계산해야 한다.

검토 코드는 `REPLAY_VERIFIED`, `SOAK_ACCEPTED`, `REPORTS_COMPLETE`, `ORDERS_RESOLVED`, `CALIBRATION_VALID`, `POLICY_FROZEN`, `ROLLBACK_ACK`, `KILL_ACK`, `MANUAL_APPROVAL`이다. 하나라도 `BLOCK`/`UNKNOWN`이면 최종 결과는 `BLOCKED`다. 활성 ambiguity/freeze는 차단하지만 determinate하게 해결된 과거 ambiguity는 warning으로 남긴다.

이 보고 명령은 설정을 쓰거나 `TRADING_MODE=real`을 활성화하지 않고, 주문 제출·재제출·예약 실행·Phase 9 waiver·정책 자동 변경·수익성 주장을 하지 않는다. `READY`도 권한 토큰이 아니며 실제 전환은 별도 수동 절차다.

## Phase 11 인트라데이 운영

Phase 11도 운영자가 터미널에서 직접 시작하고 지켜보는 전경(foreground) 절차다. 일일 평가와 신호 생성은 `bot run`이 담당한다. 보유 종목의 순수 stop-loss/take-profit 재평가는 `bot intraday check` 한 번 또는 `bot intraday watch --interval-seconds 60`으로 수행하며 LLM을 만들거나 호출하지 않는다. 계정과 세션 상태의 읽기 전용 확인은 `bot status`를 사용한다.

watch cadence는 60초 기본값이자 최솟값이다. 더 짧은 값은 KIS 런타임을 만들기 전에 exit code 2로 거부한다. 각 iteration은 새 ID와 새 KIS portfolio snapshot을 가지며 이전 snapshot의 주문 권한을 이어받지 않는다.

| KST | lifecycle | 허용 동작 |
|---|---|---|
| 09:00 전 | `PREFLIGHT_READ_ONLY` | 계정·세션 상태만 읽고 신규 주문 POST는 하지 않는다. |
| 09:00 이상 15:20 미만 | `ACTIVE` | COMPLETE인 현재 KIS 원장, 최신 quote, active lease가 모두 확인된 iteration만 limit SELL을 검토한다. |
| 15:20 이상 15:30 미만 | `RECONCILE_ONLY` | 신규 POST 권한은 끝난다. 이미 제출된 intent의 주문·미체결·체결 상태만 조회하고 증거를 추가한다. |
| 15:30 이상 | `TERMINAL` | reconciliation 후 watch를 종료하며 주문을 자동 취소하지 않는다. |

`Ctrl-C`의 signal handler는 stop flag만 설정한다. 다음 안전 checkpoint에서 `STOPPING`으로 전이하며 순서는 **신규 POST 중단 → 제출 intent reconciliation → terminal 증거 저장 → lease 해제**다. signal handler는 원래 값으로 복원한다. 이미 보낸 주문을 취소하거나 같은 intent를 다시 보내지 않는다. restart 시 이전 mutable 상태가 있으면 `RECOVERY_ONLY`에서 시작하며 미해결 주문이 determinate해지기 전에는 `ACTIVE`로 가지 않는다.

## Phase 11 안전 경계와 복구

모든 알림은 bounded Korean text와 stable code만 포함한다. `INFO`는 시작·정상 종료·확정 체결, `WARNING`은 지속 장애 또는 `LONG_OPEN_ORDER`, `CRITICAL`은 `ORDER_AMBIGUOUS`, `LEASE_LOST`, broker truth 실패, `AUDIT_EVIDENCE_FAILED`에 사용한다. 같은 canonical state의 반복 관측은 매번 occurrence와 duration 증거를 추가하지만 begin 알림은 한 번만 보낸다. 상태 변경과 recovery 때만 새 알림을 보낸다.

- `ACCOUNT_DATA_INCOMPLETE`: pagination 또는 필수 계정 필드가 불완전하다. 그 iteration은 BLOCKED이며 다음 iteration에서 현재 KIS 원장을 새로 조회한다.
- `LEASE_BUSY`: 다른 mutable 명령의 pid, command, 시작 시각, 상태를 bounded metadata로 확인한다. observer fallback 없이 `bot status`만 읽는다.
- `LEASE_LOST`: 신규 POST를 즉시 막고 제출 intent를 reconcile한 뒤 terminalize·release한다.
- `ORDER_AMBIGUOUS`: 영향 티커를 동결하고 KIS 주문·미체결·체결을 같은 broker subject로 대조한다. 미접수로 추정하지 않는다.
- `LONG_OPEN_ORDER`: 기본 900초가 지난 OPEN/PARTIAL 주문을 WARNING으로 표시한다. 상태가 바뀔 때까지 반복 알림은 보내지 않는다.
- `TRANSPORT_FAILED`: 알림 전송 실패는 거래 결과를 바꾸지 않는 fail-soft다. 실패 attempt 증거를 확인하고 보고서를 직접 검토한다.
- `AUDIT_EVIDENCE_FAILED`: notification-attempt 또는 필수 transition 증거 저장이 실패했다. 이후 신규 주문 권한을 제거하고 감사 저장소가 복구될 때까지 읽기만 한다.

`OPEN/PARTIAL SELL은 reconciliation-only`이며 다른 SELL과 BUY를 모두 차단한다. quantity와 remaining state는 현재 KIS 원장만 권위가 있고 로컬 계산값은 권위가 아니다. 다음 금지선은 장애 중에도 완화하지 않는다.

- 백그라운드 scheduler/service 금지
- 자동 취소 금지
- 시장가 주문 금지
- 공격적 price chasing 금지
- blind retry/resubmission 금지
- 로컬 잔여수량 계산 금지
- 실계좌 자동 승격 금지

## Phase 11 인증 모의계좌 UAT

이 체크리스트는 KIS 모의투자 자격 증명이 있는 운영자가 수동으로 수행하며 자동화 테스트를 대체하지 않는다. 계좌 번호, token, 원시 응답, 자격 증명은 보관하지 않고 stable ID·count·status만 포함한 sanitized evidence를 남긴다.

- [ ] GET-only 계좌 조회에서 모든 pagination 페이지가 COMPLETE인지 확인한다.
- [ ] snapshot에 보유수량, 주문가능수량, 평균단가, 주문, 체결, 예수금이 누락 없이 mapping되는지 확인한다.
- [ ] 모의계좌의 bounded 1주 limit 주문으로 partial-fill 또는 no-fill을 관찰하고 동일 broker subject의 remaining 상태를 확인한다.
- [ ] cancel은 운영자가 KIS 화면에서 수행한 외부 관측으로만 확인한다. bot의 자동 cancel 기능을 만들거나 호출하지 않는다.
- [ ] 다음 조회에서 partial-fill/cancel 결과가 append-only reconciliation로 남고 로컬 잔여수량 계산이나 재제출이 없음을 확인한다.
- [ ] artifact 공유 전 account 값, credential, raw payload, exception 본문이 없는 sanitized evidence인지 다시 검사한다.

## Phase 12 오프라인 포트폴리오 백테스트

`bot backtest run BUNDLE`은 동결된 JSON만 읽으며 KIS·LLM·pykrx·네이버 연결, live 감사/soak DB 변경, 주문 전송, 설정 변경을 하지 않는다. 세션 간 하나의 원장을 유지하며, 종가 신호는 다음 거래일의 시가 체결 기회부터 평가한다. 장중 리스크 워커의 재현이나 실거래 승인이 아니다.

```bash
bot backtest run ./historical-bundle.json --start 2023-01-02 --end 2025-12-30 --profile baseline --output ./results/baseline.json
bot backtest run ./historical-bundle.json --start 2023-01-02 --end 2025-12-30 --profile stress --output ./results/stress.json
bot report backtest ./results/baseline.json --output ./results/baseline.txt
```

날짜를 생략하면 묶음의 마지막 완료 KRX 세션을 끝으로 최근 3개 달력년을 요청한다. 윤년 날짜는 2월 28일로 보정한다. 실제 자료 기간·워밍업·요청 기간을 별도로 표시하며 부족한 기간을 조용히 줄여 완전한 결과라고 표시하지 않는다. 기본 시작 현금은 **모델 가정 10,000,000 KRW**, 초기 보유는 없음이며 묶음 policy로 지정한다. 출력 기본값은 `data/backtests/<result_id>.json`. 동일 바이트의 재출력은 성공하고 충돌·심볼릭 링크는 거부한다. 성공한 모델 계산은 불완전 자료라도 종료 코드 0, 잘못된 입력·지원하지 않는 프로필/날짜·출력 충돌은 2다. 자동 운영 판단은 종료 코드 대신 `run.final_coverage`와 `run.limitations`를 확인한다.

묶음 schema_version은 1이며 정확한 계약은 `trading_bot/backtest_models.py`다. 필수 필드는 `calendar`, `bars`, `membership`, `trading_status`, `corporate_actions`, `signals`, `policy`, `cost_rules`, `tick_rules`, `sources`; `benchmark`는 선택이다. 각 일봉은 ticker/session/known_at 및 조정되지 않은 open/high/low/close/volume이다. 날짜는 YYYY-MM-DD, 시각은 시간대가 있는 ISO 8601, 금액·비율은 유한한 Decimal 문자열, 수량은 정수다. 달력 close_at은 그 세션의 한국 날짜와 일치해야 한다. sources는 요청 구간의 달력·종목 구성·기업행사 완전성 선언과 source_hashes를 기록한다. 이 선언은 데이터 수집자가 검토하며 수집·검토를 이 명령이 대신 수행하지 않는다.

과거 KOSPI/KOSDAQ 보통주 구성·거래 상태·기업행사는 effective와 known_at을 함께 기록한다. 신호는 당시 알려진 strict JSON 문자열이어야 한다. 누락·파싱 실패는 HOLD, 유효한 신호는 기존 confidence·사이징·리스크 규칙을 통과해야 한다. 조정 주가는 지표 입력에만 당시 알려진 분할 정보를 적용하며 실제 체결 가격은 raw 일봉을 사용한다. 배당은 입력된 순액과 지급 세션이 있어야 지급하며, 상장폐지는 처분 가격·지급 세션을 확인할 수 없으면 보유량을 유지하고 평가 미확정을 표시한다. 고정 allowlist는 생존 편향 경고와 불완전 판정을 포함한다.

수수료·슬리피지·유동성 가정:

| 프로필 | 매수·매도 수수료 | 불리한 시가 슬리피지 | 종목별 당일 합산 거래량 참여 |
|---|---|---|---|
| baseline | 각 1.5 bps | 10 bps | 1% |
| stress | 각 3 bps | 25 bps | 0.5% |

위 값은 실제 계좌 요금이 아닌 모델 가정이다. 거래세·추가 세목·호가 단위는 시장별 날짜 유효 구간 `[effective_start, effective_end)`과 known_at/source/reviewed_at/rule_id를 가진 검토 입력을 사용한다. 합성 규칙은 `synthetic: true`로 표시하며 완전한 실제 시장 증거로 취급하지 않는다. 현재 세율을 과거 전체에 대입하지 않으며 규칙 누락·중첩·지원하지 않는 시장/거래일은 실패한다. 거래세·추가 세목은 매도에만 적용한다. 비용은 Decimal로 계산한 뒤 KRW 1 단위 올림하는 **명시적인 보수적 모델 반올림**이다. 실제 증권사 정산 반올림을 보장하지 않는다. 틱은 가격 구간별 규칙을 사용하며 매수 한도는 내림, 매도 한도는 올림한다. 슬리피지 시가는 반대 방향으로 불리하게 틱 정렬하고 한도·일봉 범위를 다시 검증한다.

시가에서 한도를 만족하지 않으면 일봉 고저가가 한도를 건드려도 체결을 만들지 않는다. 거래량 0·거래 정지·단일가 잠김은 명시적인 거래 가능 증거 없이 체결하지 않는다. 거래량 한도는 주문마다 중복 부여하지 않고 종목·세션 전체가 공유한다. 부분 체결 뒤 잔량은 그 세션 끝에 만료하며 다음 주문은 새 신호를 요구한다. BUY 현금과 SELL 보유수량을 예약한다. 매도 순대금은 동결된 KRX 달력의 T+2 거래일에 현금으로 전환하며 당일 BUY 자금으로 재사용하지 않는다. 실제 증권사 buying power와 다를 수 있다. 거래량은 그 날 전체의 **사후 체결 근사 자료**이며 이전 날의 신호 판단에는 들어가지 않는다.

순자산은 정산 현금(예약분 포함) + 결제 대기금 + 보유 평가액이다. 노출은 보유 평가액/순자산, 회전율은 총 체결 금액/일별 순자산 평균, 최대 낙폭은 초기 순자산을 포함한 누적 최고점 대비 최대 하락 비율이다. 수익률은 종료 순자산/초기 순자산−1이다. gross는 **같은 net 체결 수량·시점**에 수수료·거래세·추가 세목·가격 슬리피지 귀속을 더한 값이며 비용 없는 별도 전략 결과가 아니다. 매입 비용은 원가에 포함하고 실현 손익과 미실현 손익을 분리한다. 배당·분할 현금은 거래 비용과 구분한다. 평가액 누락은 null이며 기간 수익률·낙폭·회전율을 산출하지 않는다. benchmark는 같은 계산 세션의 동결 지수 종가가 모두 있을 때만 매수 후 보유 수익률을 표시한다.

저장 증거에는 원래 입력/소스 해시, 정책/체결/비용/결제 버전, 관련 코드 내용 식별자, 의사결정·주문·체결·기업행사·일별 원장이 들어간다. 보고 명령은 해시와 비용·현금·수량·gross/net 계산을 재검증하며 원장 전이를 다시 계산한다. 식별자에 현재 시각·출력 위치·절대 로컬 경로는 들어가지 않는다. baseline/stress는 독립 실행하되 같은 입력·기간·코드의 scenario_group으로 연결된다. 테스트 fixture는 재현성·안전 계약을 확인할 뿐 3년 실측 수익률이나 수익 보장을 증명하지 않는다.

## Phase 14 운영자 웹과 독립 알림 관찰

웹은 **저장 증거 조회, 저장 보고서 생성·내려받기, 알림 읽음 기록**을 제공한다. KIS 조회나 LLM 평가, 주문·취소, 거래 정책 수정, 동결/래치 해제, 실계좌 승격, 거래 워커 시작·중지 권한은 없다. 기존 인증 모의계좌 수동 절차와 000660 동결은 그대로 적용된다. 아래는 소유자가 필요할 때 수행하는 로컬 설정 절차이며 이 구현 검증에서 소유자 서버·암호·원천 DB·Discord를 설정하거나 호출하지 않았다.

### 검증된 실행 환경과 설치

이번 검증의 실제 인터프리터는 **Python 3.14.3**이다. 저장 증거 모듈은 `enum.StrEnum`을 사용한다. 패키지 메타데이터의 `>=3.10`만으로 Python 3.10을 지원한다고 해석하지 않는다. 다른 Python 버전은 해당 버전에서 의존성·설치·회귀 검증을 별도로 수행한다. 웹 검증은 KIS 라이브러리의 해당 인터프리터 호환성을 증명하지 않는다.

Phase 14의 소유자 확인을 마친 정확한 추가 의존성은 Flask 3.1.3, Flask-WTF 1.3.0, waitress 3.0.2, Werkzeug 3.1.9, Jinja2 3.1.6, playwright 1.63.0, pytest-playwright 0.9.0이다. 새로운 환경에서 이름·버전·공식 배포 출처를 확인한 뒤 프로젝트 가상환경에 설치한다. 기존 확인된 환경에서는 다시 설치할 필요가 없다. 로컬 개발 환경 예시는 다음과 같다.

```bash
PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pip install --user -e '.[web,browser]'
PYTHONUSERBASE="$PWD/.python-userbase" python3 -m playwright install chromium
PYTHONUSERBASE="$PWD/.python-userbase" python3 -m trading_bot.web_cli --help
PYTHONUSERBASE="$PWD/.python-userbase" python3 -m trading_bot.alert_cli --help
```

브라우저 실행은 실제 Chromium이 필요하다. 브라우저가 없거나 테스트가 skip이면 모바일/테마 검증 성공으로 기록하지 않는다. 배포용 wheel은 `python3 -m pip wheel --no-index --no-deps --no-build-isolation . --wheel-dir <임시출력>`으로 로컬 빌드하고, 검토된 의존성이 이미 있는 환경에 로컬 wheel을 `python3 -m pip install --no-index --no-deps <wheel>`로 설치할 수 있다. wheel에는 `templates/operator/*.html`, `static/operator.css`, `static/operator.js`와 `bot-web`, `bot-alerts` 독립 진입점이 포함되어야 한다.

### 원천 등록·설정·암호의 소유권

소유자만 쓰는 서로 분리된 디렉터리를 사용한다. 다음 절대 경로들은 설명용 예시이며 실제 소유자 경로로 검토해 바꾼다.

| 위치 | 내용과 권한 |
|---|---|
| `/srv/operator/config/web.json` | 웹 전용 JSON, 파일 0600·소유자 소유, 디렉터리 0700. 운영자 cookie signing secret을 포함하며 KIS/LLM/webhook을 넣지 않는다. |
| `/srv/operator/config/alerts.json` | 관찰자 전용 JSON, 동일한 소유자 보호. Discord를 사용하는 경우 webhook은 이 파일에만 보관한다. 화면·로그·공유 자료에 출력하지 않는다. |
| `/srv/operator/operations/operator.db` | 세션·로그인 제한·웹 작업 audit·읽음·incident·outbox·전달·observer 건강성. 새 DB는 0600, 디렉터리 0700. |
| `/srv/operator/artifacts` | 등록된 ID의 TXT/JSON/CSV 출력, 디렉터리 0700. 원천 경로와 분리한다. |
| `/srv/trading-evidence` | 소유자가 이미 보유한 감사·portfolio·soak·controller·저장 JSON 증거. 웹/관찰자는 읽기 전용이며 생성·migration·수정하지 않는다. |

원천의 파일뿐 아니라 **그 파일의 부모 디렉터리**도 읽기 권한 영역이다. 운영 DB 부모·artifact·config 부모는 원천과 동일하거나 상하위일 수 없다. symlink/hardlink 또는 쓰기 영역 안의 원천 별칭을 등록하지 않는다. 감사와 portfolio가 같은 SQLite 파일을 공유하더라도 각 owner의 스키마 검증·읽기 트랜잭션은 구분된다. 여러 DB의 동시 원자적 스냅샷을 주장하지 않는다.

처음 빈 화면을 확인할 수 있는 최소 웹 JSON:

```json
{
  "operational_db_path": "/srv/operator/operations/operator.db",
  "artifact_root": "/srv/operator/artifacts",
  "registered_resources": [],
  "bind_host": "127.0.0.1",
  "port": 8765
}
```

`registered_resources`의 항목은 예를 들어 `{"id":"audit","path":"/srv/trading-evidence/audit.db","owner":"audit","account_hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","target":"mock"}`다. 이 hash는 합성 예시이며 실제 saved account scope hash로 대체한다. `id`는 고정 등록 식별자이고 브라우저에서 임의 파일 경로를 선택하지 않는다. owner는 audit/portfolio/soak/controller/replay/backtest/shadow/calibration 중 실제 스키마를 선택한다. target은 mock/real/dry_run/simulated/shadow 중 저장 증거의 실제 귀속을 선택하며 hash로 추측하지 않는다. 누락 파일·지원하지 않는 스키마·깨진 연결은 UNKNOWN으로 남는다. 거래자의 `.env`나 거래 `Settings`를 웹 설정으로 복사하지 않는다.

Shadow는 저장 결과에 대한 신뢰된 등록 proof가 있어야 검증된다. calibration은 저장 outcome·가격·원천 연결 proof, readiness는 등록된 saved facts가 있어야 AVAILABLE이다. proof가 등록되지 않은 family는 이름이 있는 unavailable/UNKNOWN 상태이며 CLI 설정이나 업로드한 자기 주장으로 성공 처리하지 않는다. 제공된 CLI factory에 그런 proof 등록이 없으면 해당 화면은 UNKNOWN으로 남는다.

```bash
bot-web setup --config /srv/operator/config/web.json --username operator
bot-web serve --config /srv/operator/config/web.json
bot-web reset-password --config /srv/operator/config/web.json
```

setup은 숨겨진 입력으로 12자 이상의 전용 운영자 암호를 두 번 받고 scrypt hash만 저장하며, 필요한 signing secret을 보호된 web.json에 생성한다. 기존 계정을 덮어쓰지 않는다. 암호를 명령행 인자나 KIS/LLM 계정으로 입력하지 않는다. reset-password는 실행 PC의 로컬 명령이며 모든 PC·휴대폰 세션을 폐기한다. 웹은 공개 회원가입이나 웹 암호 복구를 제공하지 않는다.

기본 주소는 `http://127.0.0.1:8765`이며 실행 PC에서만 사용한다. 로그인의 절대 유효 시간은 발급 후 **12시간**이다. 30초 조회가 expiry를 연장하지 않는다. PC·휴대폰 세션은 독립적이며 하나의 로그아웃이 다른 세션을 종료하지 않는다. cookie는 HttpOnly/SameSite=Lax이며 사설 HTTPS 모드에서는 Secure도 요구한다.

웹 schema owner는 `phase14_web_metadata`, 알림은 `phase14_alert_metadata`, 관찰자는 `phase14_alert_observer_metadata`다. 이들은 운영 DB만 관리하며 원천의 user_version이나 portfolio/soak/controller metadata를 변경하지 않는다. 백업은 웹·관찰자 쓰기를 멈춘 뒤 SQLite의 일관된 backup API와 보호된 config/artifact를 함께 보관한다. 실행 중 주 DB 파일 하나만 복사해 WAL 내용을 잃지 않는다. 백업에는 운영자 hash·session references·signing secret·webhook이 있을 수 있으므로 접근 권한을 유지한다. 복원 후 local reset-password로 세션을 폐기하고 각 schema owner 버전을 확인한다. 원천 evidence 백업·복구는 각 원천 소유자의 기존 절차를 따른다.

### 선택적 사설 VPN/HTTPS 접속

외부 휴대폰 접속은 소유자가 선택·설정한 **사설 VPN 경로와 HTTPS 종료점**에서만 사용한다. VPN 접속도 애플리케이션 로그인을 대체하지 않는다. 이 문서는 VPN 사업자를 선택하거나 배포하지 않으며 실제 휴대폰 도달성을 확인했다고 주장하지 않는다. 공개 DNS/port forwarding/public listener를 설정하지 않는다.

VPN 인터페이스가 실제로 `10.42.0.2`이고 HTTPS proxy가 같은 PC의 `127.0.0.1`에서 upstream에 접속한다고 소유자가 확인한 경우, web.json에 다음 명시적 값들을 더한다. 주소는 설명용이므로 실제 사설 주소·인증서 이름과 일치시킨다.

```json
{
  "private_mode": true,
  "bind_host": "127.0.0.1",
  "port": 8765,
  "tls_termination": true,
  "trusted_proxies": ["127.0.0.1"],
  "allowed_hosts": ["10.42.0.2"],
  "allowed_origin": "https://10.42.0.2"
}
```

위 JSON은 기존 보호된 설정에 병합하는 접속 필드다. Waitress는 고정 proxy peer 한 개와 한 hop만 신뢰한다. origin의 scheme·host·port는 브라우저가 사용하는 주소와 정확히 일치해야 한다. 임의 Forwarded/X-Forwarded-* 값, 다른 Host/Origin, proxy chain은 통과 조건이 아니다. HTTPS upstream 전달 방식과 peer 고정은 [Waitress 공식 proxy 문서](https://docs.pylonsproject.org/projects/waitress/en/stable/reverse-proxy.html)를 확인한다.

**분명히 선택적인 예시:** 소유자가 별도로 Caddy를 선택·검토한 경우의 사설 HTTPS 설정 모양이다. 설치·실행 명령이나 기본 선택이 아니다. 사설 주소에만 바인딩하고 자동 HTTP redirect listener를 끈다.

```caddyfile
{
    auto_https disable_redirects
}
https://10.42.0.2 {
    bind 10.42.0.2
    tls internal
    reverse_proxy 127.0.0.1:8765
}
```

주소 고정은 [Caddy bind 문서](https://caddyserver.com/docs/caddyfile/directives/bind), local CA는 [Caddy tls 문서](https://caddyserver.com/docs/caddyfile/directives/tls), redirect 비활성화는 [global options 문서](https://caddyserver.com/docs/caddyfile/options)를 따른 예시다. 휴대폰과 PC에서 선택한 인증서 CA를 명시적으로 신뢰해야 하며 인증서 경고를 우회해 로그인하지 않는다. 실제 VPN 인터페이스·인증서·방화벽·다른 listener 검토는 소유자 설정 단계에서 확인한다.

### 독립 전경 알림 관찰 시작·중지

alerts.json에는 `operational_db_path`와 웹과 같은 고정 `registered_resources`를 사용하고 webhook이 필요한 경우 observer 전용 `webhook_url`을 보호해 넣는다. 기본 `scan_interval_seconds`는 정확히 30초다. 웹 프로세스는 webhook을 읽거나 observer를 시작하지 않는다.

```bash
bot-alerts --config /srv/operator/config/alerts.json status
bot-alerts --config /srv/operator/config/alerts.json once
bot-alerts --config /srv/operator/config/alerts.json watch
```

status는 읽기 전용이고 DB를 초기화하거나 ownership을 얻지 않는다. once는 한 번 관찰·전달 기록 후 STOPPED가 된다. watch는 **전경의 비거래 알림 관찰**이며, SIGINT(Ctrl+C) 또는 SIGTERM으로 멈추면 STOPPED와 ownership 해제를 저장한다. 강제 종료 뒤에는 최근 heartbeat로 동시 소유자를 차단하며 기본 300초를 넘은 이전 ownership은 takeover 때 실패 이력과 미확정 전송으로 기록한다. 원천/필수 운영 증거 저장 실패는 FAILED가 되고 이후 전송을 막는다.

브라우저가 닫혀 있어도 **관찰자가 실행 중일 때만** 새 관찰과 반복 알림이 이루어진다. 웹 서버만 켜져 있다고 Discord 전달을 기대하지 않는다. status에서 NOT_STARTED/STOPPED/RUNNING/STALE/FAILED와 heartbeat·전달 집계를 각각 읽는다. 웹의 관찰자 stale 표시 기준은 180초이고 takeover 기준과 다르다. 다른 거래 워커의 기대 실행/cadence가 저장되어 있지 않으면 작업 상태는 UNKNOWN이지 정상 또는 장애 확정이 아니다.

INFO는 웹 이력에만 남고 WARNING/CRITICAL 발생·악화·복구는 해당 소유자의 전달 증거를 남긴다. 기존 Phase 11 producer가 소유한 전송은 연결된 attempt로 보여 주며 observer가 같은 occurrence를 중복 전송하지 않는다. WARNING은 정기 반복이 없고 미확인 CRITICAL만 **30분** 간격으로 reminder를 만든다. 읽음은 자동 기록한 운영자·시각과 선택 메모를 보관하며 현재 revision의 반복 알림만 중지한다. 읽음으로는 문제 해결·원천 동결·안전 래치를 바꾸지 않는다. 악화는 새 unread revision, 복구 뒤 재발은 새 unread episode가 된다. 같은 대상의 양의 원천 증거가 있어야 복구를 표시한다.

전송 전에 claim을 저장하며 네트워크 실패·중단/충돌·전송 후 crash의 불확실한 attempt는 **UNKNOWN**이다. 전송하지 않았다고 추측해 재발송하지 않는다. 정확히 한 번 전달을 보장하지 않는다. 운영자는 웹의 source/occurrence/revision/delivery history와 채널의 해당 메시지를 수동 대조하며 UNKNOWN이나 FAILED를 거래 성공/실패로 바꾸지 않는다. 저장된 secret-bearing 예외 본문 대신 bounded failure code를 확인한다. 이 관찰 명령은 Phase 15 무인 거래 scheduler와 Phase 16 실계좌 승인 기능이 아니다.

### 화면·보고서 판독과 수동 확인

`source_observed_at`의 **원천 관측** 시각과 `query_at`의 **화면 조회** 시각(KST)을 구분한다. 30초 자동 조회/수동 새로고침은 저장 증거만 읽는다. 마지막 성공 관측은 역사적 값일 수 있고 조회 실패/오래됨을 함께 표시한다. INCOMPLETE의 0 placeholder는 UNKNOWN으로 표시하며 누락 원천·깨진 연결·모르는 분모를 0이나 PASS로 바꾸지 않는다. 각 source owner의 관측을 동시에 생성한 계좌 사실로 합치지 않는다.

일상 실행·판단·주문 이력은 오늘 Asia/Seoul부터 보여 주며 7일/30일/기간 지정으로 바꿀 수 있다. 모든 날짜의 미해결 주문·활성 알림은 별도 유지되므로 과거 000660이 오늘의 routine 이력에 없다고 해결됐다고 해석하지 않는다. 합계→정확한 구성 행→개별 기록→정제된 원천 증거에서 ID·대상·scope·분모·excluded/UNKNOWN을 확인한다. 백테스트/replay는 모델링/시뮬레이션, Shadow는 비교 증거, calibration/readiness는 참고용이며 실거래 승격 권한이 없다.

TXT는 한국어 보고서, JSON은 구조화 결과, CSV는 표 검토용이다. 모든 형식에서 같은 source/selection IDs·대상·기간·분모·UNKNOWN/INCOMPLETE를 보존한다. CSV 텍스트의 수식 시작 문자는 작은따옴표로 중화하고 제어문자를 치환한다. **UTF-8, 쉼표 구분, 따옴표 인용, identity 열은 Text, 수식 평가 비활성화**로 Excel/LibreOffice에 가져온다. 숫자는 숫자로 유지한다. 임의 재저장·재가져오기·문자열 변환에서 작은따옴표가 제거되면 수식 보호가 보존되지 않을 수 있다. 다른 변환/가져오기 설정까지 안전을 보장하지 않는다.

자동 Chromium 검사와 별도로 다음 두 항목은 소유자 판단이 남아 있다.

- 선택적 실제 phone **mobile data** + 사설 VPN에서 HTTPS 주소의 인증서가 신뢰되는지, VPN 밖에서 도달하지 않는지, 로그인이 필수인지 확인한다. PC·휴대폰 동시 로그인, 한쪽 로그아웃, 12시간 절대 만료와 암호 재설정 후 전체 세션 폐기를 실제 구성에서 확인한다.
- PC/390px/320px와 시스템 light/dark에서 안전 개요→원천→상세→다운로드/읽음을 읽어 본다. UNKNOWN·원천 나이·000660 동결·읽음과 복구의 차이가 한국어로 명확한지 확인한다. 두 확인은 주문·알림 전송·정책 변경·실계좌 승격의 허가를 부여하지 않는다.
