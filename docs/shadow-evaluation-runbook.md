# 과거 LLM Shadow 운영

준비와 보고서는 오프라인입니다. run/resume/retry만 유료 호출을 수행합니다.
기본 한도는 표본 100, 시도 100, 토큰 200000, USD 5, 동시 호출 1입니다.
입력과 요금표를 동결하고 실제 호출 전에 검토합니다. UNKNOWN은 자동 재호출하지 않습니다.
Codex CLI는 UNSUPPORTED_SHADOW_CAPABILITY로 차단됩니다.
모델·프롬프트·정책 채택과 실거래 승격은 별도 수동 결정입니다.

```sh
bot shadow prepare frozen-bundle.json --variants reviewed-variants.json --pricing reviewed-pricing.json --output data/shadow/spec.json
bot shadow run data/shadow/spec.json --journal data/shadow/run.sqlite --output data/shadow/first.json
bot shadow resume data/shadow/spec.json --journal data/shadow/run.sqlite --output data/shadow/resumed.json
bot shadow retry data/shadow/spec.json --journal data/shadow/run.sqlite --attempt PRIOR_ATTEMPT_ID --output data/shadow/retried.json
bot report shadow data/shadow/resumed.json --output data/shadow/report.md
```
