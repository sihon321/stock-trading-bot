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

## 처음 준비할 파일

Phase 12의 동결된 `BacktestBundle`을 사용합니다. 이미 저장한 기준 결과가 있으면
`prepare --baseline baseline.json`으로 연결하세요. 입력 해시와 현금·보유·체결·행동 경로가
일치해야 하며 원본 기준 결과를 덮어쓰지 않습니다. 코드 식별자만 달라진 경우는 원래
식별자를 유지하면서 새 수집 코드의 식별자도 명세에 기록합니다. 요청한 시작·종료일이
기준 결과와 다르면 거부합니다.

`--variants`는 변형 배열입니다. 기본 한 개의 명시적 모델과 기존 프롬프트를 권장합니다.
각 항목에 `provider`(openai 또는 claude), 실제 검토한 `model`, `system_prompt`,
`prompt_version`, `signal_schema_json`, `settings_json`(`"{}"` 권장),
`max_output_tokens`(기본 1024)을 넣습니다. `variant_id`는 생략해 자동 해시를 사용하세요.
기존 계약은 Python에서 다음과 같이 얻을 수 있습니다. 이 코드는 네트워크를 호출하지 않습니다.

```python
from trading_bot.prompts import SYSTEM_PROMPT, PROMPT_VERSION
from trading_bot.trade_signal import TradeSignal
from trading_bot.shadow_models import canonical_json

# 위 값과 명시적으로 선택한 provider/model을 변형 파일에 저장한다.
schema = canonical_json(TradeSignal.model_json_schema())
```

실제 모델 ID·가격을 예시로 지어내지 않습니다. 공급자 공식 문서에서 **선택한 정확한
모델/엔드포인트**의 JSON schema/강제 tool 계약, 최대 허용 입력 문맥, 출력 한도와
요금표를 검토하고 같은 순서의 `--pricing` 배열을 준비하세요. OpenAI endpoint는
`chat.completions`, Claude는 `messages`입니다. 제공자는 지정된 HTTPS 공식 호스트만 사용합니다.
반환 모델 식별자가 요청 모델과 다르면 `ACCOUNTING_BREACH`로 중단하므로 명시적 모델 버전을
검토하세요. 반환 식별자가 없으면 UNKNOWN이며 예약을 유지합니다.

각 요금표 항목에는 `provider`, `model`, `endpoint`, `currency`, `tier`(`standard`),
`source`(검토한 HTTPS 주소), `reviewed_at`(시간대 있는 시각), `synthetic: false`,
`context_upper_bound`(문서에 근거한 최대 허용 입력 토큰), `max_output_tokens`,
`input_per_million`, `output_per_million`을 넣습니다. 숫자 금액은 Decimal 문자열로
작성합니다. 캐시 읽기/쓰기 요금이 적용되면 `cache_read_per_million`과
`cache_write_per_million`을 포함하세요. 높은 쓰기 요금도 사전 예약에 들어갑니다.
캐시 사용량이 있으나 요금이 빠지면 추정 총액은 UNKNOWN이며 예약을 유지합니다.
입력 추정 토큰 수를 문서상 상한 대신 사용하지 않습니다. 출력/추론은 출력 한도에 포함됩니다.
`settings_supported_json`은 허용한 요청 설정의 정확한 키/값 JSON 문자열입니다.
설정이 없다면 `"{}"`를 사용합니다. tools/서버 도구/thinking/임의 엔드포인트/서비스 등급은
지원하지 않습니다. Claude의 emit_signal은 반환 데이터 계약이며 실행되는 도구가 아닙니다.

USD 이외 통화는 `usd_per_native`, `fx_source`, `fx_reviewed_at`을 함께 동결해야 합니다.
보고서는 원통화 추정과 환율을 기록합니다. 실제 사용량, 요금표 기반 ESTIMATED 금액,
근거 있는 청구서 금액을 구분합니다. USD 5는 계획용 모델링 한도이며 실제 청구서 상한을
보장하지 않습니다. 실제 사용량이나 청구 근거가 예약을 초과하면 값을 자르지 않고 기록한
뒤 추가 호출을 막습니다.

선택적으로 `--news`에 배열 JSON을 제공할 수 있습니다. 각 항목은
`ticker`, `known_at`, `source_hash`(SHA-256), `text`입니다. 1 MiB까지 읽고 결정 시각 뒤의
뉴스는 입력에서 제외합니다. 뉴스 텍스트는 비신뢰 구역의 구분자를 탈출할 수 없도록
이스케이프합니다. 뉴스가 없으면 보고서에 부재로 남기며 현재 뉴스나 가격을 수집하지 않습니다.

## 호출과 중단

기본값: 표본 최대 **100**, 변형 최대 **2**, 반복 **1**, 시도 **100**, 총 토큰 **200000**,
모델링 금액 **USD 5**, 동시 호출 **1**. 명시적 옵션은 prepare에서만 변경하고 동결합니다.
`--concurrency`는 1–4, `--repetitions`는 1–100입니다. 두 변형과 모든 반복·명시적 재시도가
같은 예산을 나눕니다. 단위의 비교 그룹이 모두 예약될 수 없으면 해당 그룹을 호출하지 않습니다.

`SHADOW_OPENAI_API_KEY` 또는 `SHADOW_ANTHROPIC_API_KEY`만 선택한 제공자가 필요할 때
읽습니다. 일반 OPENAI/ANTHROPIC/KIS 키를 대체로 사용하거나 `.env`를 자동 로드하지 않습니다.
prepare/report에는 키가 필요 없습니다. 키를 명세·명령 인자·보고서에 넣지 마세요.

SDK 재시도는 **0회**, HTTP 제한은 **60초**입니다. HTTP 본문은 최대 1 MiB이고 압축 응답,
리다이렉트와 환경 프록시는 허용하지 않습니다. 프롬프트와 보존 응답은 각각 UTF-8 64 KiB,
명세/결과 JSON은 16 MiB입니다. 저장할 수 없는 응답의 공간을 호출 전에 보수적으로 확보합니다.
`EVIDENCE_SIZE_LIMIT`이면 호출을 더 하지 않고 PARTIAL 결과를 저장합니다.
큰 반복 그룹이나 큰 기준 묶음은 예산 또는 저장 한도 때문에 일찍 멈출 수 있습니다.

호출 의도를 SQLite에 먼저 기록합니다. 이 기록은 네트워크 호출 완료 증명이 아닙니다.
Ctrl-C는 새 작업을 멈추고 진행 작업을 최대 60초 동안 정리합니다. 의도만 남았거나 완료를
알 수 없으면 TIMEOUT_UNKNOWN과 상한 예약을 유지합니다. 타임아웃 후에도 제공자 쪽 작업과
청구가 완료됐는지는 추측하지 않습니다. 보수적인 상한 예약 때문에 실제 사용량보다 훨씬
빠르게 한도에 도달할 수 있습니다.

## 재개와 별도 재시도

resume는 원래 manifest와 journal을 그대로 사용합니다. 새 소유자가 OS 파일 잠금을 얻어
이전 소유권이 끝났음을 확인해야 하며, 오래된 heartbeat만으로 잠금을 빼앗지 않습니다.
활성 소유자가 있으면 거부합니다. 이미 완료한 응답을 재사용하고 의도만 남은 항목을
UNKNOWN으로 복구합니다. 실패·거절·잘못된 응답·UNKNOWN 항목을 자동으로 다시 호출하지 않습니다.

정말 다시 호출하려면 저장 결과의 해당 `attempt_id`를 `retry --attempt`에 명시합니다.
새 attempt ID가 원래 attempt를 가리키고 원래 응답/예약은 그대로 남습니다. 성공한 응답의
불필요한 재시도는 거부합니다. 남은 원래 한도가 없으면 호출하지 않고 한도 소진 결과를 냅니다.

모델·프롬프트·표본·가격·상한·코드가 바뀌면 resume할 수 없습니다. 변경된 조건은
`prepare --parent-result old-result.json`으로 연결한 **새 명세와 새 journal**로 실행합니다.
표본은 기간, 원시 결정, 보유/선별, 위험, 종목별로 순환 배분하며 seed와 ID를 동결합니다.
없는 결정·보유·위험·기간 층과 뉴스·워밍업·자료 한계가 보고서에 나옵니다.

## 저장과 해석

전용 기본 경로는 `data/shadow/`입니다. 실제 감사/soak DB를 journal로 지정하면 스키마를
이관하거나 수정하지 않고 거부합니다. symlink와 충돌하는 출력도 거부합니다.
명시적 run/resume/retry `--output`은 매번 새 파일을 사용하세요. prepare/report의 동일한
바이트 출력은 재사용할 수 있지만 다른 내용으로 덮어쓸 수 없습니다.

종료 코드 0은 모든 선택 작업의 판별 가능한 결과가 있는 정상 저장,
1은 PARTIAL/BUDGET_EXHAUSTED/INTERRUPTED/ACCOUNTING_BREACH 결과 저장,
2는 잘못된 입력·지원하지 않는 기능·경로/명세 충돌입니다. 코드 2나 저장 실패에도 journal은
보존합니다. 불확실한 항목을 확인 없이 다시 호출하지 말고 원래 코드/입력에서 재개하세요.

일치율은 유효한 기준/LLM 신호 쌍을 분모로, 실패율은 호출 의도를 분모로 사용합니다.
잘못된 기준 신호는 유효 쌍에 포함하지 않습니다. MALFORMED/REFUSAL/PROVIDER_ERROR/
TIMEOUT_UNKNOWN은 성공한 HOLD가 아니며 실패한 응답은 위험 매도보다 앞서 no-action으로 처리합니다.
유효한 HOLD/BUY의 모의 위험 매도, 낮은 BUY 신뢰도, 현금/예약/자료/다음 세션 차단은
기존 공통 정책을 통해 비교합니다. 서로 다른 결과를 후속 기준 포트폴리오에 넣지 않습니다.

기본 판정은 INSUFFICIENT_EVIDENCE입니다. 모든 적격 쌍의 신호(이유·신뢰도 포함)와 가상
행동·수량·위험 결과가 정확히 같을 때만 NO_MEANINGFUL_DIFFERENCE입니다. 일치율은 정확도,
통계적 우월성, 수익성, 신뢰도 보정이나 실거래 준비의 증거가 아닙니다. 현재 모델이 과거 이후
사건을 학습했을 수 있으므로 CURRENT_MODEL_HINDSIGHT_CONTAMINATION을 유지합니다.

정책 채택은 별도 수동 결정이며 자동 승자 선정·배포·주문·설정 변경을 하지 않습니다.
Phase 9 elapsed-day 모의투자 증거와 Phase 10/11 승격·운영 게이트는 별도로 충족해야 합니다.
이번 구현 검증은 가짜 SDK/HTTP 응답과 설치된 CLI의 오프라인 prepare/report로 수행합니다.
유료 제공자 호출이나 KIS 실호출을 검증 완료로 주장하지 않습니다.

## 제공자 계약 검토 근거

유료 요금표에는 `strict_schema_supported`, `output_ceiling_supported`,
`usage_envelope_supported`를 검토 후 `true`로 기록해야 합니다. Claude는 추가로
`forced_tool_supported: true`가 필요합니다. 기본값은 모두 false이며 미검토 계약은
자격증명을 읽기 전에 거부합니다. 합성 프로필은 가짜 테스트 주입에서만 허용합니다.

Claude 어댑터는 강제 emit_signal만 지원합니다. 현재 공식 문서에서 강제 tool 선택을
지원하지 않는다고 명시한 모델 계열은 사전에 UNSUPPORTED_SHADOW_CAPABILITY로 차단합니다.
자동으로 다른 모델이나 auto 선택 방식으로 바꾸지 않습니다.
[Claude 강제 tool 선택의 모델별 제한](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools#forcing-tool-use)을
선택한 모델에 맞춰 확인하세요 (2026-10-01 확인).

OpenAI의 출력 계약은 [Chat Completions 생성 API](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)의
strict json_schema와 max_completion_tokens입니다. 설치된 openai 2.44.0 / anthropic 0.115.1
SDK의 실제 생성 인자와 가짜 HTTP 요청도 구현 테스트에서 확인했습니다. 특정 모델의 실제
지원 여부·문맥 한도·가격 검토 및 유료 실호출은 이 테스트를 대신하지 않습니다.
