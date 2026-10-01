# Phase 14: Operator Web UI, Dashboard & Alerting - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md; this log preserves the alternatives considered.

**Date:** 2026-10-01
**Phase:** 14-operator-dashboard-alerting
**Areas discussed:** 첫 화면과 탐색, 접속과 로그인, 갱신과 증거 조회, 알림과 보고서 작업

## Discussion setup

The user selected all four areas with `1,2,3,4`. Interactive text questions were answered individually; no defaults were silently selected.

## 첫 화면과 탐색

### 1. 로그인 직후 어떤 화면을 보여줄까요?

| Option | Description | Selected |
|--------|-------------|----------|
| 1. 운영 안전 요약 (권장) | Offered preference; selected behavior detailed below. | ✓ |
| 2. 계좌·보유 중심 | Offered preference; selected behavior detailed below. |  |
| 3. 최근 실행 중심 | Offered preference; selected behavior detailed below. |  |

**User's choice:** 1 — 운영 안전 요약. 미해결 주문, 안전 차단, 워커 상태, 데이터 갱신 시각을 먼저 표시하고 계좌·보유 요약을 이어서 표시한다.

### 2. 모바일에서는 어떻게 구성할까요?

| Option | Description | Selected |
|--------|-------------|----------|
| 1. 안전 요약 우선, 상세는 별도 화면 (권장) | Offered preference; selected behavior detailed below. | ✓ |
| 2. PC와 같은 내용을 세로 배치 | Offered preference; selected behavior detailed below. |  |
| 3. 계좌·보유 우선 | Offered preference; selected behavior detailed below. |  |

**User's choice:** 1 — 안전 요약 우선, 상세는 별도 화면. 경고와 핵심 상태를 먼저 확인하고 보유·주문·실행 기록은 눌러서 조회한다.

### 3. PC에서 상세 화면을 오가는 메뉴는 어떻게 배치할까요?

| Option | Description | Selected |
|--------|-------------|----------|
| 1. 왼쪽 메뉴를 업무별로 묶기 (권장) | Offered preference; selected behavior detailed below. | ✓ |
| 2. 상단 탭 | Offered preference; selected behavior detailed below. |  |
| 3. 요약 화면에서 바로 이동 | Offered preference; selected behavior detailed below. |  |

**User's choice:** 1 — 왼쪽 메뉴를 운영 요약 / 계좌·보유 / 판단·주문 / 검증·보고서로 묶고 모바일은 접이식 메뉴를 제공한다.

### 4. 화면의 시각적 스타일은 어떤 방향이 좋을까요?

| Option | Description | Selected |
|--------|-------------|----------|
| 1. 밝고 간결한 운영 화면 (권장) | Offered preference; selected behavior detailed below. |  |
| 2. 어두운 운영 화면 | Offered preference; selected behavior detailed below. |  |
| 3. 시스템 설정에 맞춤 | Offered preference; selected behavior detailed below. | ✓ |

**User's choice:** 3 — 시스템 설정에 맞춤. 기기의 밝은·어두운 모드에 따라 자동 전환한다.

### 5. 화면 구성을 더 논의할까요, 다음 영역으로 이동할까요?

| Option | Description | Selected |
|--------|-------------|----------|
| 1. 다음 영역으로 이동 (권장) | Offered preference; selected behavior detailed below. | ✓ |
| 2. 화면 구성을 더 논의 | Offered preference; selected behavior detailed below. |  |

**User's choice:** 1 — 다음 영역으로 이동.

---

## 접속과 로그인

### 1. 대시보드를 어디에서 사용할까요?

| Option | Description | Selected |
|--------|-------------|----------|
| 1. 집 밖에서도 휴대폰으로 접속 — PC 로컬 기본 + 개인 VPN | Offered preference; selected behavior detailed below. | ✓ |
| 2. 실행 PC에서만 접속 | Offered preference; selected behavior detailed below. |  |
| 3. 같은 집 Wi-Fi에서만 PC·휴대폰으로 접속 | Offered preference; selected behavior detailed below. |  |

**User's choice:** 1 — PC 로컬 기본 + 개인 VPN을 통해 집 밖에서도 휴대폰 접속. 사설망 의미를 설명한 후 사용자가 외부 휴대폰 접속을 선택했다. 양쪽 모두 대시보드 로그인이 필요하다.

**Clarification:** The user asked “사설망이 어떤걸 얘기하는거야”. The agent explained same-home Wi-Fi versus a personal VPN allowing outside-home mobile-data access, and retained application login. The user selected outside-home VPN access. No vendor was chosen.

### 2. 대시보드 로그인은 어떤 방식이 좋을까요?

| Option | Description | Selected |
|--------|-------------|----------|
| 1. 운영자 계정 하나 + 비밀번호 (권장) | Offered preference; selected behavior detailed below. | ✓ |
| 2. 외부 계정으로 로그인 | Offered preference; selected behavior detailed below. |  |
| 3. 구현 단계에서 선택 | Offered preference; selected behavior detailed below. |  |

**User's choice:** 1 — 운영자 계정 하나 + 전용 비밀번호. KIS·LLM 키와 별개이며 최초 설정 때 구성한다.

### 3. 로그인 상태는 얼마나 유지할까요?

| Option | Description | Selected |
|--------|-------------|----------|
| 1. 최대 12시간 (권장) | Offered preference; selected behavior detailed below. | ✓ |
| 2. 30분 미사용 시 로그아웃 | Offered preference; selected behavior detailed below. |  |
| 3. 최대 7일 | Offered preference; selected behavior detailed below. |  |

**User's choice:** 1 — 최대 12시간 유지, 만료 후 다시 로그인.

### 4. PC와 휴대폰에서 동시에 로그인할 수 있게 할까요?

| Option | Description | Selected |
|--------|-------------|----------|
| 1. 동시 로그인 허용 (권장) | Offered preference; selected behavior detailed below. | ✓ |
| 2. 한 기기만 허용 | Offered preference; selected behavior detailed below. |  |

**User's choice:** 1 — 동시 로그인 허용. 각 기기의 로그인은 별도로 만료된다.

### 5. 접속·로그인을 더 논의할까요, 다음 영역으로 이동할까요?

| Option | Description | Selected |
|--------|-------------|----------|
| 1. 다음 영역으로 이동 (권장) | Offered preference; selected behavior detailed below. | ✓ |
| 2. 접속·로그인을 더 논의 | Offered preference; selected behavior detailed below. |  |

**User's choice:** 1 — 다음 영역으로 이동.

---

## 갱신과 증거 조회

### 1. 화면이 저장된 최신 기록을 얼마나 자주 확인할까요?

| Option | Description | Selected |
|--------|-------------|----------|
| 1. 30초마다 자동 갱신 + 수동 갱신 (권장) | Offered preference; selected behavior detailed below. | ✓ |
| 2. 60초마다 자동 갱신 + 수동 갱신 | Offered preference; selected behavior detailed below. |  |
| 3. 수동 갱신만 | Offered preference; selected behavior detailed below. |  |

**User's choice:** 1 — 30초마다 자동 갱신 + 수동 갱신. 원본 관측 시각은 별도 표시하며 화면 갱신은 KIS 조회나 LLM 실행을 시작하지 않는다.

### 2. 오래됐거나 조회에 실패한 데이터는 어떻게 보여줄까요?

| Option | Description | Selected |
|--------|-------------|----------|
| 1. 마지막 값 유지 + 상태·시각 표시 (권장) | Offered preference; selected behavior detailed below. | ✓ |
| 2. 오래된 값 숨김 | Offered preference; selected behavior detailed below. |  |
| 3. 마지막 값과 최신 상태를 분리 | Offered preference; selected behavior detailed below. |  |

**User's choice:** 1 — 마지막 값 유지 + 상태·시각 표시. 오래됨·조회 실패를 명시하고 확인 불가능한 합계는 UNKNOWN으로 표시한다.

### 3. 합계나 상태를 눌렀을 때 상세 기록은 어떻게 보여줄까요?

| Option | Description | Selected |
|--------|-------------|----------|
| 1. 목록 → 개별 기록 → 원본 증거 (권장) | Offered preference; selected behavior detailed below. | ✓ |
| 2. 시간순 경과 중심 | Offered preference; selected behavior detailed below. |  |
| 3. 원본 증거 중심 | Offered preference; selected behavior detailed below. |  |

**User's choice:** 1 — 목록 → 개별 기록 → 원본 증거. 구성 항목, 판단 이유, 주문 경과, 출처 ID를 단계적으로 확인하고 원본 증거는 펼쳐 본다.

### 4. 실행·판단·주문 기록의 기본 조회 기간은 어떻게 할까요?

| Option | Description | Selected |
|--------|-------------|----------|
| 1. 오늘, 한국 시간 기준 (권장) | Offered preference; selected behavior detailed below. | ✓ |
| 2. 최근 7일 | Offered preference; selected behavior detailed below. |  |
| 3. 마지막에 선택한 기간 유지 | Offered preference; selected behavior detailed below. |  |

**User's choice:** 1 — 오늘, 한국 시간 기준. 기간 변경 가능. 미해결 주문·활성 경고는 발생 날짜와 관계없이 계속 표시한다.

### 5. 갱신·증거 조회를 더 논의할까요, 다음 영역으로 이동할까요?

| Option | Description | Selected |
|--------|-------------|----------|
| 1. 다음 영역으로 이동 (권장) | Offered preference; selected behavior detailed below. | ✓ |
| 2. 갱신·증거 조회를 더 논의 | Offered preference; selected behavior detailed below. |  |

**User's choice:** 1 — 다음 영역으로 이동.

---

## 알림과 보고서 작업

### 1. 운영 경고를 어디에서 받을까요?

| Option | Description | Selected |
|--------|-------------|----------|
| 1. 웹에 모두 표시 + Discord로 주요 경고 전송 (권장) | Offered preference; selected behavior detailed below. | ✓ |
| 2. 웹에서만 확인 | Offered preference; selected behavior detailed below. |  |
| 3. 웹에 모두 표시 + Discord는 심각 경고만 | Offered preference; selected behavior detailed below. |  |

**User's choice:** 1 — 웹에 모든 알림을 표시하고 기존 Discord 채널로 주의·심각 경고 및 복구 알림을 전송한다.

### 2. 같은 문제가 계속될 때 반복 알림은 어떻게 할까요?

| Option | Description | Selected |
|--------|-------------|----------|
| 1. 상태 변화 시 알림 + 미확인 심각 경고는 30분마다 재알림 (권장) | Offered preference; selected behavior detailed below. | ✓ |
| 2. 상태가 바뀔 때만 알림 | Offered preference; selected behavior detailed below. |  |
| 3. 미확인 경고를 모두 30분마다 재알림 | Offered preference; selected behavior detailed below. |  |

**User's choice:** 1 — 같은 문제는 하나로 묶고 발생·악화·복구 시 알림. 미확인 심각 경고는 30분마다 재알림. 주의 경고는 반복 전송하지 않는다.

### 3. 알림 확인 때 메모를 남기게 할까요?

| Option | Description | Selected |
|--------|-------------|----------|
| 1. 메모는 선택 사항 (권장) | Offered preference; selected behavior detailed below. | ✓ |
| 2. 심각 경고는 메모 필수 | Offered preference; selected behavior detailed below. |  |
| 3. 모든 경고에 메모 필수 | Offered preference; selected behavior detailed below. |  |

**User's choice:** 1 — 메모 선택 사항. 확인 시각과 계정 자동 기록. 확인은 읽었다는 표시이며 재알림만 멈춘다. 원본 증거가 해결을 입증할 때까지 활성 경고와 안전 차단 유지.

### 4. 보고서는 어떤 형식으로 다운로드할까요?

| Option | Description | Selected |
|--------|-------------|----------|
| 1. TXT + JSON + CSV (권장) | Offered preference; selected behavior detailed below. | ✓ |
| 2. TXT + JSON | Offered preference; selected behavior detailed below. |  |
| 3. TXT + JSON + PDF | Offered preference; selected behavior detailed below. |  |

**User's choice:** 1 — TXT + JSON + CSV. 한국어 읽기용 보고서, 구조화된 결과, 엑셀용 표를 제공하며 출처 ID와 UNKNOWN 상태를 보존한다.

### 5. 알림·보고서 작업을 더 논의할까요, 이 영역을 마무리할까요?

| Option | Description | Selected |
|--------|-------------|----------|
| 1. 이 영역 마무리 (권장) | Offered preference; selected behavior detailed below. | ✓ |
| 2. 알림·보고서 작업을 더 논의 | Offered preference; selected behavior detailed below. |  |

**User's choice:** 1 — 이 영역 마무리.

---

## Completion

After all four areas, the agent summarized the decisions and offered (1) create context or (2) discuss more. The user selected `1`, authorizing the context document.

## Agent Discretion

No preference questions were delegated. Technical mechanics remain for research/planning within the roadmap and existing safety contracts. CONTEXT.md separates the sixteen answered preferences from required implementation boundaries.

## Deferred Ideas

None introduced by the user. Scheduling and trading controls remain Phase 15; real-money pilot approval remains Phase 16.
