---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Mock Soak & Replay Validation
current_phase: 09
current_phase_name: kis-mock-soak-fault-drills
status: executing
stopped_at: Completed 10-03-PLAN.md; Phase 9 gate remains incomplete
last_updated: "2026-08-10T05:14:58.161Z"
last_activity: 2026-07-28
last_activity_desc: "Completed quick task 260728-e0i: Make KIS mock soak market-date preflight resilient to every current-day pykrx uncertainty while retaining explicit evidence and fail-closed safety"
progress:
  total_phases: 5
  completed_phases: 3
  total_plans: 31
  completed_plans: 29
  percent: 60
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-11)

**Core value:** Given fresh market data, the bot produces a trustworthy, machine-checkable trading signal and acts on it through KIS — without placing an order the rules don't justify.
**Current focus:** Phase 09 — kis-mock-soak-fault-drills

## Current Position

Phase: 09 (kis-mock-soak-fault-drills) — EXECUTING
Plan: 8 of 10
Status: Ready to execute
Last activity: 2026-07-28 - Completed quick task 260728-e0i: Make KIS mock soak market-date preflight resilient to every current-day pykrx uncertainty while retaining explicit evidence and fail-closed safety

Progress: [██████████] 96%

## Performance Metrics

**Velocity:**

- Total plans completed: 26
- Average duration: 3 min
- Total execution time: 0.15 hours

**Shipped milestone:** v1.0 — 5 phases, 21 roadmap plans, completed 2026-07-03

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table. Current milestone constraints:

- Evidence completeness and explicit cycle boundaries precede replay, reports, and soak collection.
- Replay reuses production decision/risk gates with frozen fixtures and no live providers.
- Only the explicit KIS mock path counts as soak evidence; local simulation does not.
- Calibration is advisory only and cannot mutate settings or enable real-money trading.
- Real-money promotion remains an evidence-linked checklist with separate explicit manual approval.
- [Phase 06]: Run finalization is a guarded RUNNING-to-terminal transition; abandoned work is recovered before mutable invocations. — Preserves immutable lifecycle evidence after crashes.
- [Phase 06]: Ticker completeness is derived from durable ticker_outcomes and persisted detail excludes raw exception text. — Makes partial completion queryable without leaking provider data.
- [Phase 06]: KIS POST acknowledgement uncertainty terminalizes as ambiguous and is never blindly retried.
- [Phase 06]: Order reconciliation retains origin_run_id and records the later observer_run_id.
- [Phase 06]: KRX execution requires positively observed trading-day data and the half-open [09:00, 15:20) KST continuous session. — Fail closed outside confirmed continuous trading.
- [Phase 06]: Daily context uses the immediately preceding confirmed KRX trading day, with unknown provider state failing closed. — Exclude incomplete bars and weekday assumptions.
- [Phase 06]: KIS orders re-fetch an aware timestamped quote immediately before POST and accept an inclusive maximum age of 10 seconds. — Enforce freshness at the money-moving boundary.
- [Phase 6]: Selected screen candidates override duplicate rejection evidence for the same ticker.
- [Phase 6]: Real and mock mutation boundaries share an inclusive 10-second freshness verdict and normalized evidence shape.
- [Phase 07]: Hash Git HEAD and normalized replay-relevant tracked diff separately so dirty executions remain attributable.
- [Phase 07]: Compute replay result identity from canonical deterministic evidence only; persist invocation metadata outside identity.
- [Phase 07]: Canonical replay technicals come only from cutoff-safe raw OHLCV passed through the shipped calculate_technicals function.
- [Phase 07]: Explicit non-AVAILABLE fixture health overrides indicator health; otherwise the actual IndicatorResult health controls screening.
- [Phase 08]: Notification failure categories use bounded uppercase stable codes — Raw exception text never crosses the durable evidence boundary
- [Phase 08]: Notification attempt ordering uses integer insertion identity — Timezone-aware timestamps remain observational and may collide
- [Phase 08]: 보고서는 실행 수명주기, 티커 완전성, 대상, reconciliation, 알림 전달을 서로 다른 증거 차원으로 유지한다.
- [Phase 08]: Replay는 stable ID와 cardinality를 검증한 뒤 fixture schema, policy, scenario basis가 같은 결과만 집계한다.
- [Phase 08]: 보고 CLI는 자격 증명 Settings와 분리된 audit_db_path 전용 ReportSettings만 사용한다. — 읽기 전용 보고가 KIS와 LLM 환경 변수 없이도 동작하게 한다.
- [Phase 08]: 터미널과 파일은 하나의 LF 정규화 UTF-8 payload를 공유하고 기존 충돌 바이트를 덮어쓰지 않는다. — D-04의 동일 문서 계약과 감사 증거 보존을 보장한다.
- [Phase 08]: 전역 실행 가능 여부는 stops_run이 설정된 전역 점검만 결정하며 확정된 미해결 주문은 해당 티커만 동결한다. — D-11 전역 안전 증명과 D-16 티커 귀속을 분리한다.
- [Phase 08]: 알림 transport 실패는 거래 결과를 바꾸지 않지만 알림 증거 저장 실패는 호출자에게 전파한다. — D-17의 fail-soft transport와 fail-closed evidence 경계를 보존한다.
- [Phase 08]: Phase 8 unresolved-order 점검은 로컬 append-only 증거만 축약한다. — Phase 9 이전에 인증된 KIS broker truth를 주장하지 않는다.
- [Phase 08]: 08:50 bot status는 비실행 PRE_OPEN 준비 관찰이며, 실행 권한은 post-open CONTINUOUS 전역 PASS 점검에서만 부여한다. — 런북과 반개구간 시장 정책의 의미를 일치시키고 pre-open 거래 허가를 방지한다.
- [Phase 09]: SoakSettings is independent of Settings, keeping real credentials and target selection structurally absent. — Capability restriction is stronger than a runtime mode check.
- [Phase 09]: KIS mock TR IDs remain explicit versioned candidates until authenticated KIS-observed evidence accepts one. — Repository legacy and official examples currently differ.
- [Phase 09]: The proof-order path remains closed until durable profile, store, reconciliation, and exact operator-confirmation prerequisites exist. — Prevents compatibility probing from acquiring mutation authority.
- [Phase 09]: Accept official-example-v1 as the authenticated KIS mock profile after complete read-only pagination and explicit operator approval. — The observed account had empty order and holding rows, so retained evidence stays truthful while deterministic tests cover non-empty normalization semantics.
- [Phase 09]: Keep soak storage independently versioned and linked to primary audit/controller evidence only by stable IDs. — Prevents schema ownership drift and cross-database transaction coupling.
- [Phase 09]: Keep availability exhaustion separate from the irreversible D-09 safety latch. — Preserves independent campaign accounting dimensions.
- [Phase 09]: Release ticker freezes only by appending same-subject determinate terminal broker evidence. — Prevents local state or day credit from clearing unresolved broker risk.
- [Phase 09]: Broker truth is complete only after all order/fill and balance pages plus required cash fields normalize successfully.
- [Phase 09]: Ambiguity becomes determinate only when the entire bounded observation sequence agrees on zero matches or one stable broker order.
- [Phase 09]: Reconciliation reads primary audit in query-only mode, writes only the soak store, and leaves the controller DB unopened.
- [Phase 09]: Treat the authenticated proof acknowledgement as ambiguous and retain the 000660 freeze. — No broker order ID was returned and the complete post-submission comparison remains UNKNOWN.
- [Phase 09]: Proof-order ambiguity remains non-credit and cannot authorize resubmission. — Cross-linked durable evidence and a restart-persistent freeze preserve safety without overstating broker truth.
- [Phase 09]: Non-credit soak verdicts persist as events without consuming a designated-day attempt. — Prevents closed, unknown, preview, dry-run, drill, rerun, or incomplete evidence from consuming credit opportunities.
- [Phase 09]: All active soak freezes are projected into designated-run preflight across campaign boundaries. — Preserves the authenticated 000660 ambiguity freeze at the money-moving boundary.
- [Phase 09]: Each accepted or ambiguous submission requires one POST_SUBMISSION reconciliation before finalization. — Makes reconciliation cardinality explicit and prevents blind retry or unsupported credit.
- [Phase 09]: Fault construction requires a committed controller contract and independent read-back token. — Prevents any injection from starting on evidence that exists only in memory or an uncommitted transaction.
- [Phase 09]: Controlled faults use one immutable registry and single-use port; only accepted-then-timeout crosses one POST boundary. — Makes hidden or multiple activation structurally unavailable and preserves the no-blind-retry contract.
- [Phase 09]: Controlled drill evidence remains accounting-neutral and provenance-separated. — Keeps eligible-day credit, availability budget, and KIS-observed evidence truthful.
- [Phase 09]: Read each evidence owner in its own stable mode=ro/query_only transaction and never claim a cross-database atomic snapshot. — Preserves truthful ownership boundaries while supporting one report.
- [Phase 09]: Downgrade missing or contradictory primary/controller links to UNKNOWN instead of omitting them or preserving a persisted PASS. — Missing provenance cannot support a successful operator claim.
- [Phase 09]: Keep CONTROLLED_INJECTION, KIS_OBSERVED, and SYNTHETIC drill denominators separate from eligible-day and availability accounting. — Prevents synthetic drills from overstating authenticated clean operation.
- [Phase 09]: Make soak status require the canonical existing triple and construct no KIS, LLM, data, or order collaborator. — Read-only inspection must not acquire live or mutating authority.

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 9 planning must confirm authenticated KIS mock restrictions, inquiry behavior, and fault semantics.
- Phase 10 planning must define sample sufficiency, uncertainty, and promotion thresholds before calibration claims.
- Ticker 000660 remains frozen after the authenticated proof because the KIS acknowledgement was ambiguous and no determinate broker order was observed; do not resubmit or release without same-subject terminal broker evidence.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260720-elk | Commit the existing weekend and holiday OHLCV trading-day evidence fix | 2026-07-20 | 628f5e6 | [260720-elk-commit-the-existing-weekend-and-holiday-](./quick/260720-elk-commit-the-existing-weekend-and-holiday-/) |
| 260727-d5y | Treat campaign-scoped RESUME comparisons as valid without weakening 000660 ambiguity freeze or order safety | 2026-07-27 | 5105ee8 | [260727-d5y-treat-campaign-scoped-resume-comparisons](./quick/260727-d5y-treat-campaign-scoped-resume-comparisons/) |
| 260728-d3r | Fix KRX market-session preflight UNKNOWN during KIS mock soak without weakening fail-closed safety | 2026-07-28 | 1ad1ec9 | [260728-d3r-fix-krx-market-session-preflight-unknown](./quick/260728-d3r-fix-krx-market-session-preflight-unknown/) |
| 260728-e0i | Make KIS mock soak market-date preflight resilient to every current-day pykrx uncertainty while retaining explicit evidence and fail-closed safety | 2026-07-28 | 270b114 | [260728-e0i-make-kis-mock-soak-market-date-preflight](./quick/260728-e0i-make-kis-mock-soak-market-date-preflight/) |
| Phase 10 P01 | 7 min | 2 tasks | 4 files |
| Phase 10 P02 | 6 min | 2 tasks | 4 files |
| Phase 10 P03 | 4 min | 2 tasks | 3 files |

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Validation | Full portfolio backtest, live-LLM historical replay, web dashboard, unattended scheduling | Future | v1.1 scoping |
| Automation | Automatic policy writes or real-money promotion | Prohibited | v1.1 scoping |
| Phase 06 P01 | 8min | 3 tasks | 6 files |
| Phase 06 P02 | 12min | 2 tasks | 4 files |
| Phase 06 P03 | 12min | 2 tasks | 7 files |
| Phase 06 P04 | 12m | 3 tasks | 8 files |
| Phase 06 P05 | 10min | 3 tasks | 7 files |
| Phase 07 P02 | 10min | 2 tasks | 2 files |
| Phase 07 P06 | 7min | 2 tasks | 5 files |
| Phase 08 P01 | 4 min | 2 tasks | 3 files |
| Phase 08 P02 | 10min | 2 tasks | 2 files |
| Phase 08 P03 | 6min | 2 tasks | 5 files |
| Phase 08 P04 | 8min | 2 tasks | 6 files |
| Phase 08 P05 | 4min | 2 tasks | 3 files |
| Phase 08 P06 | 4 min | 2 tasks | 3 files |
| Phase 09 P01 | 12 min | 3 tasks | 8 files |
| Phase 09 P02 | 62 min | 1 tasks | 1 files |
| Phase 09 P03 | 10 min | 2 tasks | 2 files |
| Phase 09 P04 | 11 min | 2 tasks | 5 files |
| Phase 09 P09 | 12 min | 2 tasks | 8 files |
| Phase 09 P10 | 8 min | 1 tasks | 1 files |
| Phase 09 P05 | 12 min | 2 tasks | 4 files |
| Phase 09 P06 | 11 min | 2 tasks | 5 files |
| Phase 09 P07 | 10 min | 2 tasks | 6 files |

## Session Continuity

Last session: 2026-08-10T05:14:58.155Z
Stopped at: Completed 10-03-PLAN.md; Phase 9 gate remains incomplete
Resume file: .planning/phases/10-advisory-risk-calibration-promotion-readiness/10-04-PLAN.md

## Operator Next Steps

- Run `$gsd-verify-work 7` to independently re-verify the completed replay phase.
- Then run `$gsd-discuss-phase 8` to define decision reports and the operator runbook.
