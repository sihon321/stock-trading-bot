# Phase 15: Unattended Scheduling & Service Resilience - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md; this log preserves the alternatives considered.

**Date:** 2026-10-04 (discussion began 2026-10-03 KST)
**Phase:** 15-unattended-scheduling-service-resilience
**Areas discussed:** 실행 시간과 감시 주기, 누락 실행과 재시작, 일시정지·재개·긴급 중단, 상시 운영과 건강 상태

## Initial area selection

Presented all four areas. **User's choice:** `1,2,3,4`.

## 실행 시간과 감시 주기

### 일일 평가 시간

| Option | Description | Selected |
|---|---|---|
| 1 | 09:10 유지 — 권장: 기존 운영 기록과 같은 시간 | ✓ |
| 2 | 다른 고정 시간: 운영자가 KST 시간 지정 |  |
| 3 | 설정으로 선택: 기본 09:10, 실행 전 변경 가능 |  |

**User's choice:** `1` — 1. KST 09:10 유지; 하루 1회 LLM 평가

### 장중 위험 감시 시작

| Option | Description | Selected |
|---|---|---|
| 1 | 09:00부터 — 권장: 기존 보유 종목 보호 | ✓ |
| 2 | 09:10 평가 완료 후 |  |
| 3 | 별도 KST 시간 지정 |  |

**User's choice:** `1` — 1. KST 09:00부터; LLM 호출 없는 보유 종목 위험 감시

### 보유 종목 위험 감시 주기

| Option | Description | Selected |
|---|---|---|
| 1 | 60초 — 권장: 기존 기본값 유지 | ✓ |
| 2 | 120초 |  |
| 3 | 설정으로 선택: 기본 60초, 60초 이상 지정 |  |

**User's choice:** `1` — 1. 60초

### 개장 전 자동 준비 점검

| Option | Description | Selected |
|---|---|---|
| 1 | 08:50 점검 추가 — 권장 | ✓ |
| 2 | 09:00 시작 시 점검 |  |
| 3 | 개장 전 KST 시간 지정 |  |

**User's choice:** `1` — 1. KST 08:50 점검 추가; 주문 직전에도 안전 조건 재확인

### 일정 추가 논의 또는 다음 영역

| Option | Description | Selected |
|---|---|---|
| 1 | 다음 영역으로: 누락 실행과 재시작 | ✓ |
| 2 | 실행 일정 더 논의하기 |  |

**User's choice:** `1` — 1. 다음 영역으로

## 누락 실행과 재시작

### PC가 늦게 켜져 미시작 일일 평가를 놓친 경우

| Option | Description | Selected |
|---|---|---|
| 1 | 10분 이내 보충 — 권장 | ✓ |
| 2 | 보충 없이 건너뛰기 |  |
| 3 | 허용 시간 지정 |  |

**User's choice:** `1` — 1. 10분 이내 보충: KST 09:20 전까지 안전 점검 통과 후 한 번 실행; 이후 누락 기록·알림

### 실행 중 서비스 중단 후 재시작 복구

| Option | Description | Selected |
|---|---|---|
| 1 | 안전 확인 후 자동 재개 — 권장 | ✓ |
| 2 | 항상 수동 재개 |  |
| 3 | 위험 감시만 자동 재개 |  |

**User's choice:** `1` — 1. 안전 확인 후 자동 재개; 불확실한 주문은 차단하고 동결 유지

### 일일 평가 일부 종목 처리 후 중단

| Option | Description | Selected |
|---|---|---|
| 1 | 09:20 전까지 남은 평가 재개 — 권장 | ✓ |
| 2 | 그날 평가는 종료 |  |
| 3 | 수동 재개 |  |

**User's choice:** `1` — 1. 09:20 전까지 저장 입력·진행 기록을 유지해 미시작 종목만 재개; 이후 미완료 기록. 완료된 평가 반복 또는 불확실한 LLM 호출 자동 재시도 금지

### 일일 평가 실패 또는 누락 시 위험 감시

| Option | Description | Selected |
|---|---|---|
| 1 | 안전 조건을 만족하면 계속 — 권장 | ✓ |
| 2 | 전체 일시정지 |  |
| 3 | 조회만 계속 |  |

**User's choice:** `1` — 1. 자체 안전 조건이 통과하면 계속; 공통 안전 문제는 주문 차단

### 복구 추가 논의 또는 다음 영역

| Option | Description | Selected |
|---|---|---|
| 1 | 다음 영역으로: 일시정지·재개·긴급 중단 | ✓ |
| 2 | 누락 실행과 복구 더 논의하기 |  |

**User's choice:** `1` — 1. 다음 영역으로

## 일시정지·재개·긴급 중단

### 일반 일시정지 범위

| Option | Description | Selected |
|---|---|---|
| 1 | 일일 평가 중단, 위험 감시 유지 — 권장 | ✓ |
| 2 | 모든 신규 주문 중단 |  |
| 3 | 두 방식 제공 |  |

**User's choice:** `1` — 1. 일일 평가·신규 매수 중단; 보유 손절·익절 및 제출 주문 확인 계속

### 긴급 중단(킬 스위치) 동작

| Option | Description | Selected |
|---|---|---|
| 1 | 모든 신규 주문 차단 — 권장 | ✓ |
| 2 | 신규 주문 차단 후 서비스 종료 |  |

**User's choice:** `1` — 1. 매수·위험 매도 모두 신규 주문 차단; 제출 주문 확인·알림 계속; 자동 취소하지 않음

### 일시정지·재개·긴급 중단 조작 위치

| Option | Description | Selected |
|---|---|---|
| 1 | CLI와 웹 모두 — 권장 | ✓ |
| 2 | CLI만 |  |
| 3 | 웹은 중단만 |  |

**User's choice:** `1` — 1. CLI와 로그인한 웹 모두; 웹은 제어 요청만 전달하고 실행 서비스가 안전 조건 검증

### 운영자가 설정한 일시정지·긴급 중단 해제

| Option | Description | Selected |
|---|---|---|
| 1 | 명시적으로 재개할 때까지 유지 — 권장 | ✓ |
| 2 | 일시정지는 다음 거래일에 해제 |  |
| 3 | 일시정지 만료 시각 지정 |  |

**User's choice:** `1` — 1. 명시적 재개까지 재시작·다음 거래일에도 유지; 재개 요청 후 안전 점검 통과 필요. 장애 후 자동 복구와 별개

### 운영 제어 추가 논의 또는 다음 영역

| Option | Description | Selected |
|---|---|---|
| 1 | 마지막 영역으로: 상시 운영과 건강 상태 | ✓ |
| 2 | 운영 제어 더 논의하기 |  |

**User's choice:** `1` — 1. 마지막 영역으로

## 상시 운영과 건강 상태

### 거래 서비스 실행 기기

| Option | Description | Selected |
|---|---|---|
| 1 | 현재 개발용 Mac — 권장 | ✓ |
| 2 | 별도 상시 가동 Mac |  |
| 3 | Linux 서버 |  |

**User's choice:** `1` — 1. 현재 개발용 Mac 한 대; 예약 시간에 켜져 있고 잠들지 않아야 함

### Mac 재시작 시 서비스 시작

| Option | Description | Selected |
|---|---|---|
| 1 | 로그인 후 자동 시작 — 권장 | ✓ |
| 2 | 수동 시작 |  |
| 3 | 부팅 직후 자동 시작 |  |

**User's choice:** `1` — 1. 소유자 로그인 후 자동 시작, 복구 점검; 저장된 일시정지·긴급 중단 유지

### 프로세스 예기치 않은 종료 후 자동 재시작

| Option | Description | Selected |
|---|---|---|
| 1 | 10분 내 최대 3회 — 권장 | ✓ |
| 2 | 자동 재시작 없이 알림 |  |
| 3 | 제한 직접 지정 |  |

**User's choice:** `1` — 1. 10분 내 최대 3회; 반복 실패 시 자동 재시작 중단 및 수동 확인 상태 기록·알림; 매 재시작 복구·안전 점검

### 서비스 건강 상태 알림

| Option | Description | Selected |
|---|---|---|
| 1 | 문제 발생·악화·복구만 알림 — 권장 | ✓ |
| 2 | 매일 08:50 준비 상태도 알림 |  |

**User's choice:** `1` — 1. Discord 문제 발생·악화·복구만 알림; 미확인 CRITICAL 30분 reminder; 웹 건강 상태 표시. 동일 Mac 모든 프로세스 정지 시 즉시 자체 알림 불가능 설명

### 상시 운영 추가 논의 또는 전체 검토

| Option | Description | Selected |
|---|---|---|
| 1 | 전체 결정 검토로 | ✓ |
| 2 | 상시 운영과 건강 상태 더 논의하기 |  |

**User's choice:** `1` — 1. 전체 결정 검토로

## Final context selection

1. 컨텍스트 작성 — write 15-CONTEXT.md and discussion log.
2. 추가 논의 — explore remaining gray areas.

**User's choice:** `1` (2026-10-04). No further gray areas requested.

## Carried-forward clarification

The existing 15:20 no-new-order and 15:30 watch termination boundaries were explained in the cadence discussion and repeated in the schedule summary; they were not separate new preference questions. Orders and uncertain LLM calls are never blindly retried. Phase 9 Plan 09-08 acceptance is required before unattended mutation. Total same-Mac power/sleep outage cannot immediately notify through its own stopped processes.

## Agent's Discretion

No preference question was delegated to the agent. Scheduler/service choice, schemas, module names, control transport, timeouts/backoff and health thresholds remain research/planning mechanics bounded by the captured decisions. CONTEXT.md distinguishes these from owner-selected preferences.

## Deferred Ideas

None introduced by the owner. Existing Phase 16 and future Tailscale deployment/device acceptance boundaries remain.
