---
phase: 14
slug: operator-dashboard-alerting
status: approved
reviewed_at: "2026-10-01T14:32:07Z"
shadcn_initialized: false
preset: none
created: 2026-10-01
---

# Phase 14 — UI Design Contract

> Korean operator interface for saved, attributable evidence and authenticated non-trading actions.
> Canonical contract for planning, execution and UI verification; independently approved across all six design dimensions.

## Decision Sources and Authority

- `14-CONTEXT.md` D-01–D-16 supplies all 16 locked user preferences. No preference is reopened here.
- `14-RESEARCH.md` Summary, Standard Stack, freshness/session/incident sections and file map supply implementation boundaries.
- `ROADMAP.md` Phase 14 and `REQUIREMENTS.md` FUT-03/UI-01/UI-02/OPSV-01 require the full screen coverage below.
- `STATE.md` supplies the existing unresolved 000660 subject and continuing independent soak acceptance requirement.
- Layout dimensions, tokens, presentation limits and interaction details below are safe technical defaults within delegated mechanics.
- UI writes are restricted to sessions, action audit, report artifacts and incident acknowledgement in operational storage.
- No order/cancel, live LLM, policy change, real-mode activation, safety-clear, pause/resume/kill or promotion controls.
- Report generation consumes saved evidence only; exports never start replay, backtest, shadow or collection.

## Design System

| Property | Value |
|----------|-------|
| Tool | none; manual native CSS contract |
| Preset | not applicable |
| Component library | none; Flask/Jinja semantic HTML with progressive native JavaScript |
| Icon library | none; local inline SVG: info circle, warning triangle, critical octagon, check, clock, chevron, menu |
| Font | system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif |

No components.json, reusable frontend, CSS tokens or React/Next/Vite stack was detected; shadcn gate is not applicable.
Follow the researched `templates/operator/*`, `static/operator.css` and `static/operator.js` ownership map.
Do not add a Node/build runtime, external fonts, icon CDN or third-party registry block.
Use CSS custom properties for the tokens below; share shell, badges, evidence metadata, forms and pagination across screens.

## Spacing Scale

| Token | Value | Usage |
|-------|-------|-------|
| xs | 4px | Icon/text gap and label-to-helper spacing |
| sm | 8px | Badge padding, metadata and compact row gaps |
| md | 16px | Mobile page/card padding and form/control spacing |
| lg | 24px | Desktop card padding and grid gaps |
| xl | 32px | Desktop page padding and section separation |
| 2xl | 48px | Login/form section separation |
| 3xl | 64px | Header minimum height and large page separation |

Exceptions: 16px control horizontal padding, 44px minimum interactive target, 56px table row minimum, 240px sidebar,
320px minimum viewport, 1440px content maximum; all are multiples of 4. Borders are 1px; focus outlines are 2px with 4px offset.
Card radius is 8px; controls/badges use 4px. Use borders and spacing; no decorative gradients or card shadows.

## Typography

| Role | Size | Weight | Line Height |
|------|------|--------|-------------|
| Body | 16px | 400 | 1.5 |
| Label | 14px | 600 | 1.5 |
| Heading | 20px | 600 | 1.2 |
| Display | 28px | 600 | 1.2 |

Exactly four sizes and two weights (400/600). Secondary metadata/table cells use 14px/400 at 1.5; buttons use 16px/600.
One 28px page h1; section h2 uses 20px. Small card headings use 16px/600; no oversized numeric hero display.
Numbers use tabular-nums; monetary/quantity columns align right. Korean prose wraps naturally; IDs use overflow-wrap:anywhere.
Evidence code uses the local monospace fallback at 14px/400 and 1.5 without introducing another size or weight.

## Color

| Role | Light value | Dark value | Usage |
|------|-------------|------------|-------|
| Dominant (60%) | #F8FAFC | #0B1220 | Page background and spacious neutral areas |
| Secondary (30%) | #FFFFFF | #172033 | Cards, sidebar, header, tables and forms |
| Accent (10% maximum) | #1D4ED8 | #93C5FD | Primary CTA, selected nav marker, attributable links, focus ring |
| Destructive | #B91C1C | #FCA5A5 | Reserved for destructive actions; none exist in Phase 14 |
| Text | #0F172A | #F1F5F9 | Body, headings and numbers |
| Muted text | #475569 | #CBD5E1 | Source dates, helper text and metadata |
| Divider | #CBD5E1 | #334155 | Decorative dividers and card outlines |
| Control border | #64748B | #94A3B8 | Inputs, secondary buttons and outlined state markers |
| Accent foreground | #FFFFFF | #0B1220 | Filled primary button text |

Accent reserved for: `저장 증거 새로고침`, page-local primary submit, current-navigation 4px marker,
underlined evidence/detail links and keyboard focus. Other buttons remain neutral; do not color every interactive element.
System preference selects the theme through prefers-color-scheme and color-scheme; no theme picker or stored override.
The 60/30/10 hierarchy is a visual budget, not a quota that requires large accent panels.

| Semantic state | Light text / background | Dark text / background | Required marker |
|----------------|-------------------------|------------------------|-----------------|
| INFO / unknown | #1D4ED8 / #EFF6FF | #93C5FD / #172554 | Info circle + distinct text label |
| WARNING / stale / incomplete | #92400E / #FFFBEB | #FDE68A / #332B12 | Triangle + distinct text label |
| CRITICAL / failure / blocked | #B91C1C / #FEF2F2 | #FCA5A5 / #3F151C | Octagon + distinct text label |
| Recovery / confirmed pass | #166534 / #F0FDF4 | #86EFAC / #122C1C | Check + distinct text label |

Semantic CRITICAL color communicates observed risk and is separate from the unused destructive-action token.
Unknown must say UNKNOWN rather than imply INFO is a healthy verdict; severity and evidence status are separate badges.
All listed text pairs must meet contrast >=4.5:1; accent/control borders/focus on adjacent surfaces >=3:1.
Divider tokens are decorative only. Do not use opacity to dim essential text, unknown values or acknowledged active incidents.
Critical accents occupy a badge, icon and 4px row edge. Use one bounded overview risk panel; avoid full red page backgrounds,
flashing alerts, persistent full-page warnings and repeated banners. Every page retains a compact unresolved-critical count link.

## Responsive Layout

- At >=1024px use a 240px fixed left sidebar, 64px header and centered main area capped at 1440px with 32px padding.
- At 768–1023px collapse navigation; main padding is 24px and summary cards use two columns when they fit.
- At 320–767px use a 64px header, 16px main padding and a single-column safety-first summary; detailed views are separate pages.
- Header contains menu when collapsed, current page, target badge, compact critical count, refresh and operator menu.
- Mobile menu is a disclosure panel in document flow, not an overlay; expanded items retain 44px targets and group headings.
- Overview order: unresolved orders/safety blocks, worker and observer health, source times, account/holdings, latest activity.
- Desktop safety section uses two columns; account summary uses up to three equal cards; no fixed-height clipping.
- Main page order: breadcrumb, h1/scope, observation metadata, primary action, filters, summary, rows, pagination.
- Mobile routine tables become labeled record cards with the same facts/actions; pairwise validation tables retain local horizontal scroll.
- Wide table scrolling is limited to a named keyboard-focusable container; the whole page must not scroll sideways at 320px.
- Keep long reasons/evidence beneath the summary; use separate record routes and native details disclosure rather than nested drawers.
- No sticky footer. Header/sidebar must not hide focused content; use scroll-padding/scroll-margin for focus and anchor targets.

## Navigation and Screen Coverage

| Group | Korean navigation | Screen contract and minimum attributable facts |
|-------|-------------------|-----------------------------------------------|
| 운영 개요 | 안전 개요 | Active all-date episodes, unresolved orders/freezes, blocks, health, source statuses, account/holding summaries |
| 운영 개요 | 알림 | All severities; active all-date list first, selectable history, read status, occurrences, duration and delivery attempts |
| 운영 개요 | 작업 상태 | Watch/cycle/observer expectation, lifecycle, latest iteration, heartbeat/lease facts, age and failure reason code |
| 계좌·보유 | 계좌 요약 | Saved complete account scope, cash/total/valuation, completeness, snapshot ID, source observation and failed attempt |
| 계좌·보유 | 보유 종목 | Same-snapshot ticker, quantity, cost, available mark/valuation and unrealized result; missing marks remain UNKNOWN |
| 판단·주문 | 선별 후보 | Screening rank, ticker, selected/rejected reason, coverage, run/source IDs and evaluation date |
| 판단·주문 | LLM 판단 | Decision, confidence, bounded sanitized reason, validation/risk verdict, daily evaluation and provider/model if recorded |
| 판단·주문 | 주문 | Local intent vs broker observation, known broker ID, origin/observer run IDs, progression, unresolved all-date subjects |
| 판단·주문 | 체결 | Recorded fills, price/quantity/time, order/snapshot links and reconciliation status; never infer fill from submission |
| 판단·주문 | 실행 이력 | KST date, run lifecycle, target/mode, ticker completeness numerator/denominator, source links and failure category |
| 검증·보고 | 보고서 | Registered report types/scope, periods, denominators, generated TXT/JSON/CSV and exact source selection |
| 검증·보고 | Replay | Saved validated fixture/policy/scenario/code identities, result state, comparison rows and simulated denominators |
| 검증·보고 | 백테스트 | Saved modeled equity/drawdown/cost/turnover/fill metrics, frozen inputs, baseline comparison and friction assumptions |
| 검증·보고 | LLM Shadow | Saved baseline/variant/model/prompt identity hashes, coverage, valid pairs, unknown usage, ESTIMATED costs and limits |
| 검증·보고 | 모의투자 Soak | Campaign/day credit, budget, reconciliation/freeze/drill facts, cross-store UNKNOWN and provenance-separated counts |
| 검증·보고 | 위험 보정 | Saved advisory samples, exclusions, uncertainty, policy comparisons and exact denominators; no policy submit controls |
| 검증·보고 | 준비도 | Saved READY/BLOCKED/UNKNOWN and checklist evidence links; manual approvals shown as evidence facts only |

All rows have desktop/mobile routes and discoverable navigation; mobile keeps report generation, every export and acknowledgement.
Each screen has list -> record -> sanitized evidence; metrics link to the exact constituent selection, including excluded/unknown rows.
Report families appear only through registered saved resources supported by the shipped readers; an unavailable family has a named empty state.
Baseline/prompt identity means safe IDs/hashes, never prompt bytes, embedded input documents or raw provider outputs.
Readiness always displays `참고용 평가 · 실거래 승격 권한 없음`; simulated and shadow views retain their distinct badges.
Global/section scope labels use `모의투자`, `실거래 기록`, `드라이런`, `시뮬레이션`, `Shadow`, or `UNKNOWN` from attributable facts.
Do not derive target from an account hash. Never merge different targets/provenances into an unlabeled balance or success rate.

## Evidence, Freshness and History Contracts

- Every projection binds a registered resource, source schema and record/snapshot ID; aggregates and rows use that same selection.
- Show `원천 관측: YYYY-MM-DD HH:mm:ss KST`, `관측 경과: {duration}` and `화면 조회: YYYY-MM-DD HH:mm:ss KST` separately.
- Display known cash as `1,234,567원`, quantities as `123주`, confidence as `0.82`, rates with numerator/denominator next to the percentage.
- Preserve source precision in detail/exports. Unknown amounts use `UNKNOWN · 확인되지 않음`, never 0, dash-only or NaN.
- Freshness, completeness and query result remain separate: `저장 관측`, `오래된 관측`, `COMPLETE`, `INCOMPLETE`, `UNKNOWN`, `조회 실패`.
- Preserve the last valid complete snapshot when the latest attempt is incomplete/failed; identify both attempts and never mix their totals/rows.
- A complete saved account snapshot is historical observation, not proof of current broker truth; always expose age even after a successful poll.
- For an established expected running worker/source, stale threshold is max(180s, 3 x its documented cadence), matching research.
- Where expectation/cadence cannot be established, freshness verdict stays UNKNOWN. Stopped/not-expected differs from stale or failed.
- Show latest watch iteration and lease age separately; a lease timestamp alone cannot certify liveness or grant recovery authority.
- At threshold equality retain the within-threshold state; beyond threshold show stale. Missing timestamps cannot produce a recent badge.
- Immutable replay/backtest/shadow reports show generated/source dates and historical scope; never pretend they have live freshness.
- Default routine run/decision/order/fill history is today in Asia/Seoul; offer `오늘`, `최근 7일`, `최근 30일`, `기간 지정`.
- Period filters apply to routine history only. Active incidents and unresolved orders remain in a separate all-date section.
- Existing 000660 ambiguity remains visible with its source links until positive same-subject terminal evidence establishes recovery.
- Missing sources, incomplete pagination or invalid cross-store links retain UNKNOWN/INCOMPLETE and a safe diagnostic code.
- Multiple stores have their own observation IDs/times; never label the page an atomic cross-database snapshot.
- Lists default to 50 records/page; cap at 100. Page links expose known total or `총건수 UNKNOWN`; filtered counts disclose their scope.
- Evidence disclosure renders allowlisted plain text; bound fields to 4096 characters and each evidence page to 16KiB with explicit truncation.
- Expand/copy/download only registered sanitized evidence. No arbitrary paths, secret fields, session/token material or raw exception text.

## Interaction and Browser Contracts

- Server-rendered routes, navigation, filters, report forms and acknowledgement work without JavaScript; automatic refresh is progressive enhancement.
- Poll saved evidence once per 30 seconds in a visible tab, never overlap requests; timeout after 10 seconds and retain last success on failure.
- Manual `저장 증거 새로고침` invokes the same reader; disable only that button during its in-flight request and announce completion/failure.
- Pause polling in a hidden tab; one read on return then resume cadence. A refresh updates browser query time, never source observation time.
- Do not reorder rows under keyboard focus or erase selection, disclosures, scroll position or typed acknowledgement notes.
- While a form is dirty, update the compact source-status region and show `새 증거가 있습니다`; apply row changes after the operator refreshes.
- Filter GETs and pagination keep validated scope/period in URL; detail links preserve list return context and browser Back behavior.
- Use explicit `상세 보기`/source-ID links, not clickable whole rows. No hover-only explanations or auto-opening evidence.
- Credential, evidence and report responses use no-store. Back/restore/session expiry must validate authentication before showing cached content.
- At 12-hour absolute expiry stop polling, hide sensitive contents and show login; a new PC/phone login does not revoke the other session.
- Login return target is an allowlisted same-origin route. Do not replay a prior report/acknowledgement POST after reauthentication.
- Logout affects the current session; password reset revokes all sessions through the local setup workflow, outside the web UI.
- Generation requires registered report type, source scope, period and format; show the selection before `보고서 생성`.
- On success show source IDs, generation time and `TXT 내려받기`, `JSON 내려받기`, `CSV 내려받기`; no raw path input or overwrite UI.
- Downloads and generation are authenticated; mutation forms use CSRF. Show safe errors without stack traces or provider response bodies.
- Native form validation names the field and reason; server errors use an error summary with focus and field associations.
- Acknowledge through an incident-detail inline form: optional note (500 characters), consequence text and `읽음으로 기록`.
- Persist identity/time/note only after successful response; disable repeat submit in flight. No optimistic read/recovered badge.
- A failed/stale acknowledgement request leaves the incident unread and retains its note; a severity revision requires fresh review.

## Incident and Notification Contract

- Active incidents are one row per stable subject/episode/severity revision, not one row per refresh; show first/last observed and source occurrence count.
- Incident detail shows subject/target/ticker, severity, duration, linked source sequence, read status and separate recovery status.
- `읽음` stops that revision's periodic reminders but never resolves the incident, clears a latch/freeze or changes broker facts.
- Newly worsened or recurring incidents display `미확인` with a new revision/episode; previous acknowledgement stays in history.
- Web includes INFO/WARNING/CRITICAL and all histories. Discord occurrence/worsening/recovery respects existing delivery ownership.
- Only unacknowledged CRITICAL repeats every 30 minutes; WARNING has no reminders. Show last attempt and next due time if known.
- Show delivered/failed/UNKNOWN attempts separately from incident severity; unknown delivery must not claim successful delivery.
- Recovery requires positive same-subject durable source facts; disappearing rows, healthy polls or acknowledgement cannot create recovery.
- Observer running/stopped/stale/UNKNOWN is visible independently of the browser; explain that alerts run only while explicitly started monitoring runs.
- No web start/stop observer control; link to the sanitized operator runbook. No browser uptime indicator may imply unattended trading.

## Copywriting Contract

| Element | Exact Korean copy |
|---------|-------------------|
| Primary CTA | 저장 증거 새로고침 |
| Refresh helper | 저장된 증거만 조회합니다. 새 시세 수집이나 거래 실행을 시작하지 않습니다. |
| Initial loading | 저장된 증거를 불러오는 중입니다. |
| Refresh in flight / success | 저장 증거 조회 중… / 저장 증거를 다시 조회했습니다. |
| General empty heading | 표시할 저장 증거가 없습니다 |
| General empty body | 선택한 범위에 저장된 증거가 없습니다. 기간과 대상 범위를 확인하세요. |
| No configured source | 연결된 증거 원천이 없습니다. 로컬 설정과 등록된 원천을 확인하세요. |
| Query error | 저장 증거를 조회하지 못했습니다. 마지막 성공 관측을 유지합니다. 원천 상태를 확인한 뒤 다시 조회하세요. |
| No last success | 성공한 저장 관측이 없습니다. 값은 UNKNOWN입니다. 원천 상태를 확인하세요. |
| Stale value | 오래된 관측입니다. 현재 계좌 상태를 보장하지 않습니다. 원천 관측 시각을 확인하세요. |
| Incomplete value | 증거가 불완전합니다. 합계는 UNKNOWN입니다. 연결된 원천 상세를 확인하세요. |
| Source/link failure | 원천 연결을 확인할 수 없습니다. 상태는 UNKNOWN입니다. 등록된 원천과 연결된 ID를 확인하세요. |
| Login labels / CTA | 운영자 계정 / 비밀번호 / 로그인 |
| Login scope helper | 전용 운영자 계정으로 로그인하세요. KIS·LLM 자격 증명은 입력하지 마세요. |
| Login failure | 로그인할 수 없습니다. 계정과 비밀번호를 확인하세요. |
| Login throttled | 잠시 후 다시 로그인하세요. |
| Session information | 로그인은 최대 12시간 유지됩니다. PC와 휴대폰 세션은 각각 만료됩니다. |
| Session expired | 로그인 시간이 만료되었습니다. 계속하려면 다시 로그인하세요. |
| Logout | 로그아웃 |
| Password recovery | 비밀번호 재설정은 실행 PC의 로컬 설정 명령에서 진행하세요. |
| Form/token error | 요청을 확인할 수 없습니다. 화면을 다시 연 뒤 입력 내용을 확인하고 다시 시도하세요. |
| Missing/unauthorized record | 요청한 증거를 열 수 없습니다. 목록으로 돌아가 등록된 증거를 선택하세요. |
| Evidence disclosure | 정제된 원천 증거 펼치기 / 정제된 원천 증거 접기 |
| Evidence truncation | 표시 한도에 도달했습니다. 등록된 정제 보고서에서 범위를 나누어 확인하세요. |
| Empty active list | 조회한 저장 증거에서 활성 알림이 없습니다. 원천 상태와 관측 시각을 함께 확인하세요. |
| All-date section | 모든 날짜의 미해결 주문·활성 알림 |
| 000660 ambiguity | 000660 주문 결과 미확정 · 종목 동결 유지 |
| Acknowledgement note label | 대응 메모 (선택) |
| Acknowledgement CTA | 읽음으로 기록 |
| Acknowledgement consequence | 읽음 기록은 반복 알림만 중지합니다. 문제 해결이나 안전 차단 해제를 뜻하지 않습니다. |
| Acknowledgement success | 읽음으로 기록했습니다. 원천 증거의 복구 확인 전까지 활성 알림을 유지합니다. |
| Acknowledgement failure | 읽음 기록을 저장하지 못했습니다. 알림은 미확인 상태입니다. 메모를 확인하고 다시 시도하세요. |
| Revision conflict | 알림 상태가 변경되었습니다. 최신 증거를 확인한 뒤 읽음으로 기록하세요. |
| Read identity/time | 읽음 · {operator} · {time} KST |
| Recovery | 복구 확인 · 같은 대상의 원천 증거에서 복구가 확인되었습니다. |
| Delivery failure / unknown | Discord 전달 실패 · 전달 시도 상세를 확인하세요. / Discord 전달 결과 UNKNOWN |
| Monitoring stopped | 알림 관찰이 중지되어 있습니다. 로컬 실행 상태를 확인하세요. |
| Worker not expected / unknown | 실행 예정 없음 / 작업 실행 여부 UNKNOWN |
| Report CTA / loading | 보고서 생성 / 저장 증거로 보고서 생성 중… |
| Export CTA | TXT 내려받기 / JSON 내려받기 / CSV 내려받기 |
| Report failure | 보고서를 생성하지 못했습니다. 원천 상태와 선택 범위를 확인한 뒤 다시 시도하세요. |
| Export caveat | 원천 ID·범위·분모와 UNKNOWN/INCOMPLETE를 포함합니다. 모의·추정·참고용 결과를 구분하세요. |
| Advisory / modeled label | 참고용 평가 · 실거래 승격 권한 없음 / 시뮬레이션 · 실제 체결 아님 |
| Shadow limitation | Shadow 일치율은 정확도·수익성·운영 준비 상태를 증명하지 않습니다. |
| Destructive confirmation | 해당 없음. Phase 14에는 삭제·거래·안전 해제 동작이 없습니다. |

## Accessibility and Motion

- Set html lang=ko; use header/nav/main landmarks, skip link `본문으로 이동`, one h1 and logical heading order.
- All interactions support Tab/Shift+Tab/Enter/Space with visible focus; menu uses aria-expanded/aria-controls and current route uses aria-current.
- Use semantic buttons/links, input labels, helper/error associations, table captions and scoped column headers; record cards use labeled definition lists.
- Announce refresh/result changes through a small polite status region; errors use an alert region once per new failure, not every polling tick.
- New/worsened CRITICAL gets one concise alert announcement; recurring unchanged incidents do not interrupt screen readers every 30 seconds.
- Never move focus on automatic refresh. On route/form error focus h1/error summary; on success keep control focus and announce the result.
- Status icon is aria-hidden beside visible text; every severity, scope, UNKNOWN and read/recovery state is spelled out.
- Minimum touch target 44px, no gesture-only actions, no title-only tooltips; preserve content at 200% text zoom and 320px viewport.
- No essential motion, sound, flashing or skeleton shimmer. Optional disclosure transitions <=120ms; reduced-motion disables all transitions.
- Charts are optional only where saved report data supports them; supply the same numeric table, source IDs and exact denominators.

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| none | none | N/A — native HTML/CSS; no shadcn or third-party registry declared; codebase scout 2026-10-01 |

Library package checks remain the research/planning responsibility; this contract does not approve installs or registry execution.

## Verification Coverage

- Validate desktop 1280px and mobile 390px/320px, both system themes, keyboard use, zoom, contrast and every navigation route.
- Exercise 30s/manual reads with slow/failing sources, last-success fallback, complete-but-old snapshots, UNKNOWN totals and source-link failure.
- Verify aggregate->rows->record->sanitized evidence uses stable IDs, scope/denominators and all-date unresolved 000660 across date filters.
- Verify concurrent sessions and exactly-12h expiry, no POST replay, note preservation, revision conflicts and absence of sensitive cached views.
- Verify occurrence/worsening/recurrence/read/recovery remain distinct, reminders stop only as specified and source risk persists after reading.
- Verify TXT/JSON/CSV identify source/scope/provenance/unknowns; spreadsheet-safe output and capability tests block live execution and source writes.

## Checker Sign-Off

- [x] Dimension 1 Copywriting: PASS
- [x] Dimension 2 Visuals: PASS
- [x] Dimension 3 Color: PASS
- [x] Dimension 4 Typography: PASS
- [x] Dimension 5 Spacing: PASS
- [x] Dimension 6 Registry Safety: PASS

**Approval:** approved 2026-10-01 — independent UI checker, 6/6 PASS, no remaining BLOCKs or FLAGs. One revision aligned control horizontal padding to the 16px spacing token. Approval covers the design contract; application/browser verification remains required during phase execution.
