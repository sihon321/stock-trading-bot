---
status: testing
phase: 05-real-money-readiness-operations
source: [05-VERIFICATION.md]
started: 2026-07-03T01:10:56Z
updated: 2026-07-03T01:10:56Z
---

## Current Test

number: 1
name: Live KIS mock order path — idempotent, reconciled real-money execution
expected: |
  With live KIS mock credentials and an open market session, running
  `bot run --ticker <code> --execute --live-confirm` under `TRADING_MODE=real`
  and `CONFIRM_REAL_TRADING=yes` places the order so it appears in KIS broker
  truth; re-running after a transport uncertainty reconciles against broker
  truth and skips the duplicate POST (idempotent, query-before-POST).
awaiting: user response

## Tests

### 1. Live KIS mock order path — idempotent, reconciled real-money execution
expected: With live KIS mock credentials and an open market session, run `bot run --ticker <code> --execute --live-confirm` under `TRADING_MODE=real` and `CONFIRM_REAL_TRADING=yes`. The order appears in KIS broker truth; re-running after a transport uncertainty reconciles and skips the duplicate POST (idempotent, query-before-POST).
result: [pending]

### 2. Discord notification delivery
expected: Set `DISCORD_WEBHOOK_URL`, run a dry-run cycle, and inspect the Discord channel. One consolidated per-run summary arrives; on a forced per-ticker error, an immediate error message also arrives.
result: [pending]

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps
