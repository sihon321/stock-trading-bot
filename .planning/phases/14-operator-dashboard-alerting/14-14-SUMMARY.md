---
phase: 14-operator-dashboard-alerting
plan: "14"
subsystem: ui
tags: [jinja, korean, native-css, accessibility, saved-evidence, tdd]
requires:
  - phase: 14-02
    provides: Installed operator UI dependencies and isolated synthetic fixture boundaries
provides:
  - Korean semantic shell with 17 fixed destinations in four approved groups
  - Escaped source/status/filter/pagination/table-card/evidence macros
  - Exact approved native light/dark, responsive, focus and reduced-motion tokens
affects: [14-10, 14-11, 14-12]
tech-stack:
  added: []
  patterns: [Independent autoescaped Jinja rendering, native CSS system themes, presentation-only DTOs]
key-files:
  created:
    - trading_bot/templates/operator/base.html
    - trading_bot/templates/operator/macros.html
    - trading_bot/static/operator.css
    - tests/test_web_ui_contract.py
  modified: []
key-decisions:
  - Preserve all approved navigation labels and six /validation/* paths on desktop and mobile.
  - Render bounded plain-text facts with forceescape and route-owned app-relative URLs only.
  - Keep product browser proof assigned to 14-12 after 14-10/11 page wiring.
requirements-completed: [FUT-03, UI-01, UI-02]
coverage:
  - id: shared-shell
    description: Independent Korean semantic navigation and safe saved-DTO rendering
    requirement: UI-01
    verification:
      - kind: unit
        ref: tests/test_web_ui_contract.py -k 'shell or navigation or macro or escape'
        status: pass
    human_judgment: false
  - id: native-contract
    description: Approved numeric spacing, typography, system theme and responsive CSS contracts
    requirement: UI-02
    verification:
      - kind: unit
        ref: tests/test_web_ui_contract.py -k 'theme or responsive or tokens'
        status: pass
    human_judgment: false
duration: 8min
completed: 2026-10-02
status: complete
---

# Phase 14 Plan 14: Shared Korean Operator UI Summary

**17개 고정 탐색 경로, 이스케이프된 저장 증거 매크로와 승인된 시스템 테마 CSS를 독립 Jinja 계약 테스트로 구현했습니다.**

## Performance

- Started: 2026-10-02T01:50:05Z
- Implementation completed: 2026-10-02T01:58:05Z
- Tasks: 2/2
- Files: 4 implementation/test files

## Accomplishments

- 네 승인 그룹의 한글 이름과 17개 경로를 유지했습니다. 검증 경로는 `/validation/replay`, `/validation/backtest`, `/validation/shadow`, `/validation/soak`, `/validation/calibration`, `/validation/readiness`입니다.
- `lang=ko`, skip link, header/nav/main, 단일 h1, 현재 경로, 네이티브 메뉴 disclosure, 조회 GET, 독립 status/alert 영역과 운영자 표시를 제공합니다. 메뉴는 header 안에서 문서 흐름을 유지합니다. no-JS 초기 상태는 펼침이며 JS 구현은 disclosure 상태와 aria-expanded를 동기화해야 합니다.
- 원천 관측/경과/화면 조회와 freshness/completeness/query status를 분리합니다. UNKNOWN은 금액 0으로 대체하지 않습니다. 표와 모바일 카드가 같은 행 사실과 상세 링크를 렌더링합니다.
- 모든 승인 색상 쌍, 간격, 글꼴 크기/두께, 치수, tabular 숫자, focus, 로컬 표 스크롤과 reduced-motion 규칙을 구현했습니다. 외부 글꼴/아이콘/CDN/테마 선택기를 추가하지 않았습니다.

## Task Commits and TDD Gates

1. T1 RED — `c0a7a50`: test(14-14): specify Korean shared shell and escaped evidence contracts
2. T1 GREEN — `4ec15fd`: feat(14-14): implement semantic Korean operator shell and evidence macros
3. T2 RED — `d425f21`: test(14-14): specify approved system-theme and responsive CSS tokens
4. T2 GREEN — `843e939`: feat(14-14): apply approved native theme and responsive evidence styling

RED는 템플릿/CSS 산출물이 존재하지 않아 각각 37개/3개 계약이 실패했습니다. 기존 웹 앱 import나 실행기에 의존한 실패가 아닙니다. 각 RED 다음에 GREEN 커밋이 존재합니다. 별도 refactor 커밋은 필요하지 않았습니다.

## Verification

실행 접두어는 모두 `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q`입니다.

- T1 `tests/test_web_ui_contract.py -k 'shell or navigation or macro or escape'`: 37 passed in 1.47s.
- T2 `tests/test_web_ui_contract.py -k 'theme or responsive or tokens' --tb=short`: 3 passed, 37 deselected in 0.08s.
- 최종 `tests/test_web_ui_contract.py --tb=short`: 40 passed in 1.41s.
- `git diff --check`: passed. 구현 커밋에 파일 삭제가 없습니다.
- 앱 factory/서버/운영 DB/실제 KIS·LLM·Discord/운영자 비밀번호 설정과 패키지 설치 없이 검증했습니다.

## Produced Artifacts and Consumer Interfaces

`base.html` 입력: `title`, `current_path`(17개 탐색 GET 경로), attributable `target`, `critical_count`, `source`, `scope`, `operator_name`, 선택적 `csrf_token`. 모르는 대상은 UNKNOWN이며 계좌 hash로 대상/모드를 유추하지 않습니다. 상세 화면은 `current_path`에 상위 목록의 고정 탐색 경로를 전달합니다. 로그인/secure page wiring은 14-10 소유입니다.

공유 blocks: `head`, `refresh_fields`, `operator_menu`, `breadcrumb`, `source_status`, `refresh_status`, `errors`, `critical_announcement`, `actions`, `content`, `filters`, `summary`, `rows`, `pagination`, `evidence`, `scripts`. `content`를 override하면 내부의 다섯 세부 blocks가 기본적으로 렌더링되지 않으므로 페이지에서 순서를 유지합니다. 비어 있는 blocks는 후속 페이지용 확장점입니다.

매크로는 `operator/macros.html`을 `ui`로 import합니다.

| Macro | Signature / input contract |
|---|---|
| icon | `icon(kind='info')`: local SVG info/warning/critical/check/clock/chevron/menu; aria-hidden |
| badge | `badge(state='UNKNOWN', label=none)`: enumerated semantic style with escaped visible text; severity and evidence status remain separate calls |
| target_badge | `target_badge(target='UNKNOWN')`: attributable target labels only |
| link | `link(url, label='상세 보기')`: route-owned authorized app-relative GET URL; rejects unsafe schemes, protocol-relative paths, backslash, traversal, controls and encoded path tricks |
| amount | `amount(value=none, unit='')`: preformatted saved numeric text; missing value renders exact UNKNOWN copy; caller preserves source precision |
| message | `message(kind)`: approved empty/missing/failed/no_success/stale/incomplete/ambiguity/advisory/modeled/shadow/export/acknowledge copy |
| source_metadata | `source_metadata(source)`: mapping of resource_id, record_id, observed_at, age, queried_at, freshness, completeness, query_status; optional last_success_id/latest_attempt_id/diagnostic_code |
| period_filter | `period_filter(action, period='today', target='UNKNOWN', start='', end='')`: fixed allowlisted GET list path and validated period/scope; server validates actual scope/date |
| pagination | `pagination(page, total=none, previous_url=none, next_url=none)`: route-owned links retain validated filters; unknown total labeled explicitly |
| records_table | `records_table(caption, columns, rows, table_id='records', pairwise=false)`: columns key/label/numeric, rows ID/facts/route-owned detail_url; <=100 rows; unique page-owned table_id; pairwise keeps local scroll on mobile |
| evidence_details | `evidence_details(fields, truncated=false)`: allowlisted sanitized plain-text mapping; 4096 chars per value, 16KiB total presented field names/values; explicit truncation copy |

Routes must enable HTML autoescape, provide bounded sanitized presentation facts, authorize every resource link and validate all scope/URL parameters. Templates do not perform reads, freshness calculation, authentication or execution. Forceescape also prevents Markup-typed DTO facts becoming raw HTML. The link prefix defense does not replace route authorization.

CSS classes: `.summary-grid`, `.safety-grid`, `.account-grid`, `.card`, `.risk-panel`, `.record-card`, `.numeric`, `.table-scroll`, `.routine-table`, `.record-cards`, `.badge-*`, `.helper`, `.primary`. IDs available to progressive JS: `operator-navigation`, `main-content`, `source-status`, `refresh-status`, `error-summary`, `critical-announcement`; refresh control carries `data-refresh`.

## Decisions Made

승인된 D-02/D-03/D-04 계약을 그대로 적용했습니다. 독립 Jinja Environment와 autoescape 구성은 공식 [Jinja API](https://jinja.palletsprojects.com/en/stable/api/) 및 [template documentation](https://jinja.palletsprojects.com/en/stable/templates/)를 확인했습니다. Context7 MCP와 ctx7 CLI가 없어 공식 문서를 사용했으며 설치하지 않았습니다.

## Deviations from Plan

범위/디자인 변경은 없습니다. T2 통합 검증 중 모바일 메뉴를 header 내부로 정렬하고 증거 전체 한도에 필드 이름을 포함했습니다. 둘 다 기존 승인 계약 충족을 위한 구현 정정이며 T2 GREEN `843e939`에 포함됩니다.

## Known Stubs

목표를 막는 stub은 없습니다. 페이지별 빈 Jinja blocks와 초기 UNKNOWN 기본값은 14-10/11이 저장 DTO를 연결하는 명시된 인터페이스입니다. 로그인, 보고서/읽음 forms, 다운로드 URLs와 refresh JS를 이 계획에서 대체 구현하지 않았습니다.

## Next Phase Readiness and Remaining Verification

- 14-10/11: secure routes, 페이지 DTO/source selection, auth/CSRF, 보고서·읽음/다운로드 forms, 상세/증거 페이지, no-store와 progressive JS를 연결해야 합니다. 보고서와 읽음 controls는 공통 actions block에 배치하여 모바일에서 보존합니다.
- 14-12: 실제 라우트의 1280/390/320px computed layout/contrast, 모든 테마, 키보드, 200% zoom, 메뉴 aria 동기화, no-JS, 폼/다운로드/30초 refresh, 세션 expiry 검증이 필수입니다. 이번 정적 테스트를 실제 제품 브라우저 검증으로 주장하지 않습니다.
- 전체 회귀와 STATE/ROADMAP/REQUIREMENTS/VALIDATION 갱신은 parent orchestrator가 수행합니다. 기존 dirty STATE는 보존했습니다.

## Self-Check: PASSED

네 구현/테스트 산출물과 이 SUMMARY가 존재하며 TDD 네 커밋을 HEAD 이력에서 확인했습니다. 최종 독립 계약 테스트 40개가 통과했습니다.
