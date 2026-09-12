---
status: resolved
trigger: "09:10 KIS mock soak 자동 실행이 당일 pykrx 불확실성 때문에 매번 KRX_SESSION_BLOCKED UNKNOWN으로 중단된다."
created: 2026-07-29
updated: 2026-07-29
---

## Symptoms

- 기대: 09:10 KST의 적격 KRX 거래일이면 KIS MOCK 증거로 거래일과 연속매매 세션을 확정하고 soak 실행을 허가한다.
- 실제: 자동화의 전역 preflight가 `KRX_SESSION_BLOCKED` / `UNKNOWN`을 반환하여 매일 fail-closed 중단된다.
- 오류: `available=False source=krx_session`; 직접 진단은 `PYKRX_CURRENT_UNCERTAIN_NO_WITNESS`.
- 시작: 2026-07-28의 당일 pykrx 불확실성 보완 이후에도 2026-07-29 09:10 자동 실행에서 재현됐다.
- 재현: 장중 09:10 KST에 `.venv/bin/bot status`를 실행한 뒤 soak 캠페인 루틴을 진행한다.

## Current Focus

- hypothesis: soak runtime에는 KIS mock calendar witness가 연결됐지만 전역 `bot status` preflight에는 연결되지 않아 자동화 진입점이 항상 당일 pykrx 단독 판정으로 남아 있다.
- test: mock 전용 preflight가 실제 KIS calendar witness로 2026-07-29 장중을 판정하고 실행 전 admission이 UNKNOWN을 production 이전에 차단하는지 검증한다.
- expecting: `KRX_SESSION_OPEN` PASS와 production 이전 `SOAK_RUN_NOT_ADMITTED` 차단이 모두 성립한다.
- next_action: resolved

## Evidence

- timestamp: 2026-07-29; `.venv/bin/bot status`가 mock/audit/unresolved 검사는 PASS했지만 KRX session만 UNKNOWN으로 반환했다.
- timestamp: 2026-07-29; 직접 market-cycle 진단이 `PYKRX_CURRENT_UNCERTAIN_NO_WITNESS`를 반환했다.
- timestamp: 2026-07-29; commit `1ad1ec9`는 `_build_soak_runtime`에만 `calendar_witness=adapter.fetch_trading_day`를 연결했다.
- timestamp: 2026-07-29; mock 전용 `.venv/bin/bot soak preflight --campaign-id soak-20260720-20d-v1`가 실제 09:37 KST에 `KRX_SESSION_OPEN`, `session=CONTINUOUS`, `trading_date=2026-07-29` PASS를 반환했다.
- timestamp: 2026-07-29; KIS/calendar/preflight/CLI/soak focused regression 114개가 통과했다.

## Eliminated

- hypothesis: 000660 ambiguity freeze가 전역 UNKNOWN을 만든다.
  reason: 해당 freeze는 ticker-scoped non-global BLOCK이며 KRX session UNKNOWN과 별도다.

## Resolution

- root_cause: 어제 추가한 KIS mock witness는 soak runtime에만 연결됐지만 09:10 자동화는 witness 없는 일반 `bot status`를 별도 전역 gate로 요구했다. 또한 `soak run`의 캠페인 admission은 production 실행 뒤 finalization에서만 평가됐다.
- fix: mock 전용 `bot soak preflight` 명령을 추가해 authenticated KIS MOCK calendar witness로 D-11을 판정하고, `soak run`이 reconciliation·production 전에 `admit_designated_run`을 반드시 통과하도록 했다. 자동화도 일반 status 대신 새 mock 전용 preflight를 정확히 한 번 사용하도록 갱신했다.
- verification: focused pytest 114 passed; compileall 및 git diff --check 통과; 실제 mock-only preflight가 KRX_SESSION_OPEN PASS를 반환했다. 전체 suite는 기존 `CandidateReportRow.reason_detail` 누락으로 collection 단계에서 중단됐다.
- files_changed: trading_bot/cli.py, tests/test_soak_cli.py, .planning/debug/resolved/soak-preflight-witness-gap.md
