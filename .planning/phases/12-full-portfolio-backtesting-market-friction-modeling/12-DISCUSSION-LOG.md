# Phase 12 Discussion Log

**Date:** 2026-10-01
**Areas:** Historical data/universe; execution; costs; reports.
**Audit trail only:** Downstream planning consumes `12-CONTEXT.md`.

## User answers

1. User requested `$gsd-discuss-phase 12` followed by `$gsd-plan-phase 12`.
2. Presented four areas; user selected `1,2,3,4`.
3. Presented recent three years (recommended), recent one year, or custom dates as the initial period question.
4. User instructed `다 권장으로 셋팅해줘`, explicitly delegating remaining choices to recommended defaults.

## Recommended defaults selected under delegation

| Area | Selected | Alternatives considered |
| --- | --- | --- |
| History | Three-year request, frozen point-in-time ordinary-share universe and explicit coverage limits | One year/custom dates; present-day fixed universe (only explicit limited mode) |
| Execution | Daily close decision, next-session conservative limit fills, deterministic shared ledger and T+2 availability | Same-bar fills or inferred intrabar paths (rejected as unsupported) |
| Costs | Versioned date-effective taxes/ticks, labeled baseline and stress commission/slippage assumptions | Constant current tax over all history or assumed actual brokerage tariff (rejected) |
| Reports | JSON evidence plus Korean text, identical gross/net path attribution, optional frozen benchmark | Dashboard and historical LLM calls (later phases) |

These were agent recommendations accepted by blanket delegation, not separately presented multiple-choice answers. Exact defaults and safety limitations are in D-01–D-16. No additional user ideas were deferred.
