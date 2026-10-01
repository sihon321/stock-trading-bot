# Stock Trading Bot

한국 시장용 개인 자동매매 봇입니다. 모의투자 검증과 명시적 실행 게이트를 사용합니다.

과거 데이터의 LLM 결과 비교는 `bot shadow prepare/run/resume/retry`와
`bot report shadow`를 사용합니다. [Shadow 운영 절차](docs/shadow-evaluation-runbook.md)를
참고하세요. 준비·보고서는 오프라인이고, 호출에는 별도 LLM 자격증명과 검토된 요금표가 필요합니다.
비교 결과는 주문·정책 변경·실거래 승격 권한을 부여하지 않습니다.
