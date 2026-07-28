---
status: resolved
trigger: "SCREEN에서 pykrx AVAILABLE 후보 제외가 KIS_UNAVAILABLE로 잘못 보고됨"
created: 2026-07-27
updated: 2026-07-27
---

## Symptoms

- 기대: SCREEN에서 제외된 종목은 실제 제외 사유와 원본 소스 상태를 보고한다.
- 실제: pykrx `AVAILABLE` 종목 46개가 `KIS_UNAVAILABLE`로 보고됐다.
- 재현: `bot run` 뒤 `bot report daily` 실행.
- 증거: SCREEN 단계는 KIS를 호출하지 않으며, CLI가 stale/quote가 아닌 모든 SCREEN 사유를 `KIS_UNAVAILABLE`로 매핑한다.

## Current Focus

- hypothesis: SCREEN 감사 이벤트의 원인 문자열을 보존하지 않아 CLI가 잘못된 일반 사유 코드로 축소한다.
- next_action: resolved

## Evidence

- timestamp: 2026-07-27; 46개 감사 행이 8ms 이내에 기록됐고 detail의 source/status는 `pykrx`/`AVAILABLE`였다.

## Resolution

- root_cause: CLI가 stale/quote가 아닌 모든 SCREEN 제외 사유를 KIS_UNAVAILABLE로 지정했다.
- fix: SCREEN_REJECTED 코드와 bounded screen_reason 상세를 감사·보고서에 추가했다.
- verification: CLI/보고서 관련 pytest 54개 통과, compileall 및 git diff --check 통과.
- files_changed: trading_bot/audit_models.py, trading_bot/cli.py, trading_bot/reporting.py, tests/test_cli.py, tests/test_reporting.py
