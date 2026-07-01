---
status: complete
phase: 02-mock-execution-core
source: [02-01-SUMMARY.md, 02-02-SUMMARY.md, 02-03-SUMMARY.md]
started: 2026-07-01T00:45:13Z
updated: 2026-07-01T00:47:00Z
---

## Current Test

[testing complete]

## Tests

<!-- All entries deterministically covered by passing tests + phase VERIFICATION.md (status: passed). source: automated → not presented as manual checkpoints. -->

### 1. Parser: valid payload → ParsedSignal wrapping canonical LLMSignal; extra fields ignored (EXEC-01)
expected: Valid JSON returns ParsedSignal; unknown fields ignored, canonical signal unchanged
result: pass
source: automated
coverage_id: 02-01-D1

### 2. Parser: malformed/invalid input raises SignalParseError, never a tradeable signal (EXEC-01)
expected: Malformed JSON, missing fields, unknown decision, out-of-range/non-numeric confidence, blank reason all raise SignalParseError
result: pass
source: automated
coverage_id: 02-01-D2

### 3. Parser: confidence range only; in-range BUY/SELL below execution thresholds accepted (EXEC-01)
expected: Parser validates 0.0..1.0 range without applying BUY/SELL thresholds
result: pass
source: automated
coverage_id: 02-01-D3

### 4. Parser: ParsedSignal preserves raw input + ignored-field diagnostics; import boundary clean (EXEC-01)
expected: Diagnostics expose ignored field names only; parser imports no forbidden external/adapter/config modules
result: pass
source: automated
coverage_id: 02-01-D4

### 5. Config: independent BUY/SELL thresholds (default 0.8) + risk params, env-overridable (EXEC-01)
expected: Settings exposes thresholds, cash fraction, max position value, stop/take pct, daily-loss threshold with env overrides
result: pass
source: automated
coverage_id: 02-02-D1

### 6. Risk: pure stop-loss/take-profit emits SELL vs average price without any LLMSignal (RISK-01)
expected: Stop-loss/take-profit breach → SELL; no position/zero qty/non-positive prices → safe HOLD
result: pass
source: automated
coverage_id: 02-02-D2

### 7. Risk: daily-loss kill switch blocks new BUYs but allows SELL/risk exits (RISK-03)
expected: After daily-loss breach, BUYs blocked; SELLs and risk exits still allowed
result: pass
source: automated
coverage_id: 02-02-D3

### 8. Execution: BUY requires Decision.BUY and confidence >= BUY threshold (EXEC-01)
expected: Below-threshold or non-BUY decision does not produce a BUY order
result: pass
source: automated
coverage_id: 02-02-D4

### 9. Execution: BUY sizing uses cash fraction capped by max position value and price (EXEC-02)
expected: Order quantity = capped cash fraction / price; zero/negative price → no order
result: pass
source: automated
coverage_id: 02-02-D5

### 10. Execution: SELL requires Decision.SELL, threshold, and a held position (EXEC-03)
expected: SELL only for held positions at/above SELL threshold; uses full held quantity
result: pass
source: automated
coverage_id: 02-02-D6

### 11. Execution: parser failure caught at boundary → HOLD/no-order, no broker mutation (EXEC-01)
expected: SignalParseError at the execution boundary maps to HOLD with no order
result: pass
source: automated
coverage_id: 02-02-D7

### 12. Execution: risk SELL overrides conflicting same-ticker LLM BUY with logged evidence (RISK-02)
expected: Risk exit suppresses same-ticker LLM BUY; override reason recorded in ExecutionResult + CycleAuditEvent
result: pass
source: automated
coverage_id: 02-02-D8

### 13. Import boundary: core modules load no KIS/LLM/pykrx/HTTP/adapter code; risk.py stays pure (RISK-01)
expected: risk/execution/config import no forbidden or cross-layer modules
result: pass
source: automated
coverage_id: 02-02-D9

### 14. MockBroker satisfies the synchronous Broker Protocol; seeded positions, no external calls
expected: isinstance(MockBroker, Broker); non-coroutine methods; get_position returns seeded state
result: pass
source: automated
coverage_id: 02-03-D1

### 15. MockBroker place_order: deterministic IDs; BUY debits/averages, SELL credits/trims (in-memory only)
expected: Deterministic MOCK-N IDs; BUY debits cash + volume-weights entry; SELL credits cash + trims/removes
result: pass
source: automated
coverage_id: 02-03-D2

### 16. MockBroker fails closed: invalid qty/oversell raise ValueError with zero mutation; import clean
expected: Invalid quantity and oversell raise ValueError leaving state unchanged; no forbidden imports
result: pass
source: automated
coverage_id: 02-03-D3

### 17. EXEC-05 dry-run: computes/logs would-be order but zero place_order calls and zero mutation (EXEC-05)
expected: Dry-run BUY/SELL/risk-exit → 0 place_order calls, broker cash/positions/history unchanged before/after
result: pass
source: automated
coverage_id: 02-03-D4

### 18. Live run: exactly one place_order, records broker_order_id, mutates only via place_order (EXEC-05)
expected: Non-dry-run places 1 order + records ID; HOLD places nothing
result: pass
source: automated
coverage_id: 02-03-D5

### 19. Integration EXEC-01/02/03: end-to-end BUY/SELL/hold/malformed against hand-written signals (EXEC-01)
expected: At-threshold BUY → mock BUY sized by cap; below-threshold → hold; held SELL → full sell; malformed → HOLD
result: pass
source: automated
coverage_id: 02-03-D6

### 20. Integration RISK-01/02/03: stop-loss sell, take-profit override, daily-loss BUY block (RISK-01)
expected: Stop-loss sells without LLM SELL; take-profit suppresses same-ticker LLM BUY with logged reason; daily-loss blocks BUY, allows exits
result: pass
source: automated
coverage_id: 02-03-D7

### 21. Import boundary (combined): parser/risk/execution/mock_broker import no forbidden/adapter modules
expected: Fresh-process import of all four core modules leaks no KIS/LLM/pykrx/requests/httpx/adapter modules
result: pass
source: automated
coverage_id: 02-03-D8

## Summary

total: 21
passed: 21
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none yet]
