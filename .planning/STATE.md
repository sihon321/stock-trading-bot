---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Mock Soak & Replay Validation
current_phase: 15
current_phase_name: Unattended Scheduling & Service Resilience
current_plan: 6
status: executing
stopped_at: Phase 15 plans 01-05 and 07 completed; wave 2 integration corrected; next 15-06
last_updated: "2026-10-04T05:32:16.359Z"
last_activity: 2026-10-04
last_activity_desc: Phase 15 execution started
progress:
  total_phases: 5
  completed_phases: 4
  total_plans: 31
  completed_plans: 30
  percent: 80
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-10-03)

**Core value:** Given fresh market data, the bot produces a trustworthy, machine-checkable trading signal and acts on it through KIS — without placing an order the rules don't justify.
**Current focus:** Phase 15 — Unattended Scheduling & Service Resilience

## Current Position

Current Phase: 15
Current Phase Name: Unattended Scheduling & Service Resilience
Current Plan: 6
Total Plans in Phase: 14
Phase: 15 (Unattended Scheduling & Service Resilience) — EXECUTING
Plan: 6 (15-06-PLAN.md; 15-07 integration completed early)
Status: Ready to execute
Last activity: 2026-10-04 — Phase 15 execution started

## Performance Metrics

**Phase 13:** 7 plans / 14 tasks completed; 80 new shadow tests and one added observer regression; final full suite 986 passed in 36.22s.

**Velocity:**

- Total plans completed: 26
- Average duration: 3 min
- Total execution time: 0.15 hours

**Shipped milestone:** v1.0 — 5 phases, 21 roadmap plans, completed 2026-07-03

## Accumulated Context

### Roadmap Evolution

- Phase 11 added: KIS Portfolio Synchronization & Intraday Exit Management
- Phase 12 added: Full Portfolio Backtesting & Market Friction Modeling
- Phase 13 added: Historical LLM Shadow Evaluation & Model Governance
- Phase 14 added: Operator Dashboard & Alerting
- Phase 15 added: Unattended Scheduling & Service Resilience
- Phase 16 added: Controlled Real-Money Pilot & Scale Gates
- Phase 14 edited: edited fields: title, goal, requirements, success_criteria; expanded to authenticated responsive web UI with non-trading operational actions

### Decisions

Phase 14 completion decisions:

- The web consumes saved evidence and exposes report/export/acknowledgement without trading authority.
- Registered resource/account/target and severity selection precedes exact CRITICAL counts and bounded constituent pages; saved refresh updates the header.
- Owner accepted Korean visual usability on 2026-10-03 and selected Tailscale for future external phone/Mac access. Actual configured private access requires later device acceptance.

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
- [Phase 11]: Keep Phase 11 whole-account projection separate from the existing Phase 9 touched projection. — Preserves shipped campaign-scoped reconciliation while making account truth complete.
- [Phase 11]: Version Phase 11 tables through a dedicated metadata owner. — Allows portfolio tables and the primary audit schema to evolve independently in one database.
- [Phase 11]: The first committed canonical input wins for a KRX date and ticker. — Daily uniqueness and crash recovery prevent repeat provider calls or input replacement.
- [Phase 11]: Preserve canonical account hashes and hash raw account scopes before lock or durable storage — Prevents raw CANO disclosure while keeping portfolio snapshot scope identity stable
- [Phase 11]: Treat every non-RELEASED predecessor lease as recovery-only — Heartbeat age never grants mutation authority after a crash
- [Phase 11]: Persist a new complete post-acquisition portfolio snapshot before reconciliation and activation — Restart authority cannot derive from stale process state
- [Phase 11]: Sort broker holdings by ticker, then retain screener rank for screened-only targets; overlap has one identity with HELD then SCREENED provenance. — Keeps daily identity deterministic and attributable.
- [Phase 11]: Persist exact rendered prompt bytes before provider construction or attempts. — Crash recovery and same-day reuse cannot replace the first committed input.
- [Phase 11]: Replay finalized signals through a capability-free adapter and a lease-guarded broker. — Historical decisions never become current execution authority.
- [Phase 11]: Use a post-held complete KIS snapshot for screened-only cash sizing. — Locally projected SELL proceeds never inflate BUY capacity.
- [Phase 11]: State-bearing lease loss requires a real terminalizer; recurring risk and broker-truth alerts use durable fact subjects instead of iteration UUIDs. — Preserves ordered shutdown evidence and restart-safe transition deduplication.

- [Phase 13]: Validate snapshots by replaying embedded frozen sources and retain original baseline/code facts; all variants share canonical pre-decision state.
- [Phase 13]: Single-shot dedicated API calls reserve full documented bounds; uncertain attempts retain reservations and require explicit linked retry.
- [Phase 13]: Reports remain advisory, with exact denominators and UNKNOWN/ESTIMATED facts; shadow has no trade/configuration/promotion authority.
- [Phase 15]: Controls use one installation-global registered scope domain, without trading-date or process-generation reset.
- [Phase 15]: Approval/source evidence uses immutable typed tuples; synthetic shape completeness is never activation authority.
- [Phase 15]: Protected service journal, control and lock roots are separate from existing trading journals and artifacts.
- [Phase 15]: FUT-04/AUTO-01/AUTO-02 remain pending until subsequent behavior and final phase verification prove them.
- [Phase 15]: Service policies re-read protected exact-date session authority and refresh current calendar observations; UNKNOWN cannot become execution authority without new positive evidence.
- [Phase 15]: Intraday shares MarketCyclePolicy with absolute 15:20 submission and 15:30 termination limits; delayed opening and overnight wake cannot extend or revive work.
- [Phase 15]: Service leadership holds a fixed installation flock separate from account POST, control and freeze authority.
- [Phase 15]: Consumed provider handoffs require committed daily universe and exact DISPATCHED dispatched_at read-back; suppressed and unknown calls never replay.
- [Phase 15]: Three automatic restarts per 600 seconds are durably reserved; attention persists until explicit validated reset and clock reversal remains denial.
- [Phase 15]: First canonical bytes and frozen envelope are immutable; scoped one-shot dispatch commits DISPATCHED before transport and uncertain recovery never resets consumption.
- [Phase 15]: Daily recovery requires actual same-store ACTIVE account authority; pure exact v3/v4 saved reader capabilities retain explicit unknown historical target.
- [Phase 15]: Installation-global control requests and final admission share a protected flock; accepted restrictions are immediately effective and survive restart/date changes.
- [Phase 15]: Actual live ServiceLeader ownership alone mints control application capability; fresh all-account owner resume and current source/revision checks cannot grant independent trading activation.
- [Phase 15]: Daily dispatch uses immutable consumed envelopes, actual transport-entry acknowledgement and no SDK, HTTP or outer retries.
- [Phase 15]: Unverified actual Codex retry capabilities fail closed; account-lease release around daily provider waits remains 15-09 integration.

### Pending Todos

None yet.

### Blockers/Concerns

- 2026-10-01 Phase 10 re-verification passed (24/24) after shared audit schema and historical ambiguity warning fixes. Focused suite: 116 passed; full suite: 828 passed. Phase 9 external acceptance remains required; current Phase 11 position is retained.

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
| Phase 10 P04 | 6 min | 2 tasks | 6 files |
| Phase 11 P01 | 8 min | 2 tasks | 6 files |
| Phase 11 P02 | 7 min | 2 tasks | 5 files |
| Phase 11 P03 | 14 min | 2 tasks | 6 files |
| Phase 11 P04 | 12 min | 2 tasks | 4 files |
| Phase 11 P09 | 12 min | 2 tasks | 5 files |
| Phase 15 P01 | 15min | 2 tasks | 4 files |
| Phase 15 P02 | 4min | 2 tasks | 5 files |
| Phase 15 P03 | 45min | 2 tasks | 4 files |
| Phase 15 P04 | 12min | 2 tasks | 6 files |
| Phase 15 P05 | 13min | 2 tasks | 3 files |
| Phase 15 P07 | 22min | 2 tasks | 7 files |

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Roadmap | Full portfolio backtest, LLM shadow evaluation, dashboard, and unattended scheduling | Phases 12–14 verified; Phase 15 not planned | 2026-08-25 roadmap expansion |
| Deployment | External phone/Mac access using Tailscale and HTTPS | Owner selected; configure and perform actual device acceptance before use | 2026-10-03 |
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

Last session: 2026-10-04T05:32:16.352Z
Stopped at: Phase 15 plans 01-05 and 07 completed; wave 2 integration corrected; next 15-06
Resume file: .planning/phases/15-unattended-scheduling-service-resilience/15-06-PLAN.md

## Operator Next Steps

- Continue Phase 9 Plan 09-08 elapsed-day KIS mock evidence collection without weakening its acceptance gate.
- Phase 14 is verified complete (14/14 plans; 1418 automated tests; independent 36/36; accepted Korean UI). Run `$gsd-discuss-phase 15` for Unattended Scheduling & Service Resilience.
- Use Tailscale for future external phone/Mac web access; verify actual private HTTPS/login/session behavior when deployment is configured.
- Optional paid shadow runs require reviewed model/capability/context/pricing records and dedicated LLM credentials. Codex CLI remains unsupported; no paid acceptance was performed here.
- Preserve Phase 11 authenticated UAT recorded pass (2026-09-07); Phase 9 elapsed-day acceptance remains independently required.
