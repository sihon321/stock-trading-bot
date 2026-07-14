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
