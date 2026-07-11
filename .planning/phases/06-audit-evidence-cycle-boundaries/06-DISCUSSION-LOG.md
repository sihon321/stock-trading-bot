# Phase 6: Audit Evidence & Cycle Boundaries - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-11
**Phase:** 6-Audit Evidence & Cycle Boundaries
**Areas discussed:** 실행 생명주기와 식별자, 종목별 최종 결과 분류, 주문 증거 연결 구조, 시장 시간과 데이터 신선도

---

## 실행 생명주기와 식별자

- 기록 명령: `bot screen`과 `bot run`만 기록하기로 선택. 모든 CLI 기록 또는 `bot run`만 기록하는 방안은 선택하지 않음.
- 최종 상태: `COMPLETED`, `COMPLETED_WITH_ERRORS`, `FAILED`, `INTERRUPTED`를 선택. 단순 성공/실패 또는 완료/미완료 체계는 선택하지 않음.
- 비정상 종료: 다음 실행 시작 시 남은 `RUNNING`을 `INTERRUPTED`로 자동 복구하도록 선택. 수동 복구 또는 영구 `RUNNING` 유지는 선택하지 않음.
- 식별: 호출마다 UUID를 발급하고 재시도는 선택적 `parent_run_id`로 연결하도록 선택. 날짜 기반 덮어쓰기 또는 관계 없는 UUID만 사용하는 방안은 선택하지 않음.

## 종목별 최종 결과 분류

- 결과 구조: 제한된 `outcome_code`와 세부 `reason_code`·설명을 분리하도록 선택.
- 실행별 의미: `screen`과 `run`에 각각 의미가 분명한 결과 코드 집합을 사용하도록 선택.
- 완전성: 처리 단계와 관계없이 모든 시도에 정확히 하나의 최종 결과를 저장하도록 선택.
- 진단 정보: 표준 원인 코드와 민감정보를 제거한 상세 메시지를 함께 보존하도록 선택. 원본 예외/API 응답 저장은 선택하지 않음.

## 주문 증거 연결 구조

- 저장 형태: 변경 불가능한 시간순 이벤트와 종목별 최종 요약을 함께 사용하도록 선택.
- 식별: `order_intent_id`와 제출별 `submission_id`를 분리하도록 선택.
- 모호한 제출: `AMBIGUOUS_SUBMISSION`으로 종료하고 즉시 재주문하지 않으며, 후속 조회를 원래 주문과 양쪽 실행에 연결하도록 선택.
- 조정 증거: 조회 시각, 주문번호, 방향, 주문·체결·미체결 수량, 조회 상태를 정형화해 저장하고 원본 KIS 응답은 제외하도록 선택.

## 시장 시간과 데이터 신선도

- 주문 시간: 보수적인 KRX 정규장 연속매매 구간만 허용하도록 선택.
- 완료 일봉: 장중에는 직전 완료 거래일까지만 사용하도록 선택.
- 시세 신선도: 주문 직전 재조회하고 10초 이내 시세만 허용하도록 선택.
- 판정 실패: KRX 거래일 또는 세션을 확정할 수 없으면 거래를 차단하도록 선택.

## Agent Discretion

- 스키마와 내부 구성, 전체 코드 목록, 정확한 KRX 연속매매 시간 및 신뢰할 수 있는 캘린더 소스는 위 결정을 보존하는 범위에서 연구·계획 단계가 정한다.

## Deferred Ideas

- 없음. 논의는 Phase 6 범위 안에 머물렀다.
