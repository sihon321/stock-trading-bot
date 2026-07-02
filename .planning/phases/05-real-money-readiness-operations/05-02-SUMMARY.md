---
phase: 05-real-money-readiness-operations
plan: 02
subsystem: execution
tags: [kis, broker, order-cash, reconciliation, real-money]
requires:
  - phase: 05-real-money-readiness-operations
    provides: operations settings and direct-REST dependency posture from 05-01
provides:
  - Single-shot KIS order-cash adapter with hashkey and mode-derived TR_IDs
  - KISBroker structural Broker implementation with query-before-POST reconciliation
  - Fill readback parser using operator-confirmed TTTC8001R fields
affects: [execution, cli, audit, real-money-orders]
tech-stack:
  added: []
  patterns:
    - Direct REST adapter reusing shared KisTokenManager
    - Broker-truth reconciliation before any non-idempotent POST
    - Single-shot order POST excluded from tenacity retry
key-files:
  created: [trading_bot/kis_broker.py]
  modified: [trading_bot/kis_order.py, tests/test_kis_order.py, tests/test_kis_broker.py]
key-decisions:
  - "KIS order-cash POST remains physically outside tenacity retry; retry is limited to query legs."
  - "Client order reference is local audit metadata only; broker truth query is the duplicate gate."
  - "Fill readback uses operator-confirmed TTTC8001R fields: tot_ccld_qty, rmn_qty, ord_qty, odno."
patterns-established:
  - "KISBroker is a plain structural Broker like MockBroker; execution._finalize_cycle remains unchanged."
  - "Real order factories must consume a caller-owned shared KisTokenManager and a caller-provided account descriptor."
requirements-completed: [EXEC-04]
coverage:
  - id: D1
    description: "KIS order-cash adapter posts limit-only bodies with mode-derived TR_IDs, KIS hashkey, and no retry on order POST."
    requirement: EXEC-04
    verification:
      - kind: unit
        ref: "tests/test_kis_order.py#test_order_cash_body_headers_and_mode_tr_id"
        status: pass
      - kind: unit
        ref: "tests/test_kis_order.py#test_order_cash_post_not_retried"
        status: pass
    human_judgment: false
  - id: D2
    description: "Fill parser reads requested-vs-filled quantities from confirmed TTTC8001R fields."
    requirement: EXEC-04
    verification:
      - kind: unit
        ref: "tests/test_kis_order.py#test_fill_parser_uses_confirmed_daily_ccld_fields"
        status: pass
    human_judgment: false
  - id: D3
    description: "KISBroker satisfies Broker structurally and reconciles duplicate and partial-fill broker truth without modifying execution.py."
    requirement: EXEC-04
    verification:
      - kind: unit
        ref: "tests/test_kis_broker.py#test_kis_broker_is_broker"
        status: pass
      - kind: unit
        ref: "tests/test_kis_broker.py#test_reconcile_skips_duplicate"
        status: pass
      - kind: unit
        ref: "tests/test_kis_broker.py#test_partial_fill_reconciled"
        status: pass
      - kind: unit
        ref: "git diff -- trading_bot/execution.py"
        status: pass
    human_judgment: false
  - id: D4
    description: "KISBroker snaps off-tick limit prices and fails safe before POST when the market/staleness guard rejects placement."
    requirement: EXEC-04
    verification:
      - kind: unit
        ref: "tests/test_kis_broker.py#test_tick_snap_and_market_guard"
        status: pass
    human_judgment: false
duration: 5min
completed: 2026-07-02
status: complete
---

# Phase 05 Plan 02: KIS Order Broker Reconciliation Summary

**Single-shot KIS order-cash placement with broker-truth reconciliation and confirmed fill readback**

## Performance

- **Duration:** 5 min
- **Started:** 2026-07-02T13:49:56Z
- **Completed:** 2026-07-02T13:55:21Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments

- Extended `trading_bot/kis_order.py` with a limit-only order-cash POST body, KIS `/uapi/hashkey` use, mode-derived buy/sell TR_IDs, and no tenacity retry on the order POST path.
- Added confirmed fill-readback parsing for `tot_ccld_qty`, `rmn_qty`, `ord_qty`, and `odno`.
- Added `trading_bot/kis_broker.py`, a plain structural `Broker` implementation with market/stale pre-flight, tick snapping, query-before-POST duplicate reconciliation, and partial-fill position reconciliation.

## Task Commits

1. **Task 1 RED: kis_order.py query/validation foundation tests** - `8aaf71b`
2. **Task 1 GREEN: kis_order.py query/validation foundation** - `30819d3`
3. **Task 3 RED: order/broker reconciliation tests** - `65f9682`
4. **Task 3 GREEN: order-cash POST and KISBroker reconciliation** - `84cc58e`

## Files Created/Modified

- `trading_bot/kis_broker.py` - Structural `Broker` implementation wrapping KIS order/query adapter behavior.
- `trading_bot/kis_order.py` - Direct-REST order/query adapter with retryable query legs, single-shot order-cash POST, hashkey request, tick snap, and fill parser.
- `tests/test_kis_order.py` - Offline tests for TR_IDs, query validation, order body/header shape, no-retry POST, and fill fields.
- `tests/test_kis_broker.py` - Offline tests for Broker conformance, duplicate reconciliation, partial fills, tick snapping, and market guard.

## Decisions Made

- Order-cash POST remains outside retry by construction; only query legs use bounded tenacity retry.
- The local client reference is explicitly audit-only because KIS does not honor a client idempotency key.
- `build_kis_broker` requires the caller to provide the shared `KisTokenManager` and a KIS account descriptor; it does not open a second token flow or invent account values.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Factory account descriptor enforcement**
- **Found during:** Task 3
- **Issue:** `Settings` currently contains active KIS credential groups but no CANO/product-code account fields, so constructing an empty account descriptor in the factory would be unsafe for live wiring.
- **Fix:** `build_kis_broker` now requires a caller-provided `KisOrderAccount` and raises if it is missing.
- **Files modified:** `trading_bot/kis_broker.py`, `tests/test_kis_broker.py`
- **Verification:** `PYTHONUSERBASE="$PWD/.python-userbase" /opt/homebrew/bin/python3.14 -m pytest -q tests/test_kis_order.py tests/test_kis_broker.py -x`
- **Committed in:** `84cc58e`

**2. [Rule 1 - Bug] Duplicate reconciliation side matching made explicit**
- **Found during:** Task 3
- **Issue:** A broad side-code check could have treated either buy/sell broker code as a match if a future KIS row included side fields.
- **Fix:** Added explicit normalization for `BUY`/`SELL` and KIS-style `02`/`01`, and only treats absent side as side-agnostic.
- **Files modified:** `trading_bot/kis_broker.py`
- **Verification:** Full suite passed.
- **Committed in:** `84cc58e`

**Total deviations:** 2 auto-fixed (Rule 1: 1, Rule 2: 1)
**Impact on plan:** Both changes tightened correctness and live-order safety without changing the requested architecture.

## Issues Encountered

- The default `python3` on this machine is Apple Python 3.9 and cannot load the installed pytest stack. Verification used the repo-documented Homebrew Python path: `PYTHONUSERBASE="$PWD/.python-userbase" /opt/homebrew/bin/python3.14 -m pytest -q`.

## User Setup Required

None for this plan. Live wiring still needs a caller-provided `KisOrderAccount` when `build_kis_broker` is used.

## Known Stubs

None.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: real-money-order-post | `trading_bot/kis_order.py` | Adds the non-idempotent KIS order-cash POST boundary; mitigated by single-shot POST and query-before-POST reconciliation. |

## Verification

- `PYTHONUSERBASE="$PWD/.python-userbase" /opt/homebrew/bin/python3.14 -m pytest -q tests/test_kis_order.py tests/test_kis_broker.py -x` - 13 passed.
- `PYTHONUSERBASE="$PWD/.python-userbase" /opt/homebrew/bin/python3.14 -m pytest -q` - 293 passed, 8 skipped.
- `git diff -- trading_bot/execution.py` - no output; `execution.py` unchanged.

## Self-Check: PASSED

- Found `trading_bot/kis_order.py`
- Found `trading_bot/kis_broker.py`
- Found `tests/test_kis_order.py`
- Found `tests/test_kis_broker.py`
- Found commits `8aaf71b`, `30819d3`, `65f9682`, and `84cc58e`

## Next Phase Readiness

The real-order broker path is ready for the later CLI/audit wiring plans. Those plans must pass a real `KisOrderAccount` from operator configuration rather than relying on defaults.

---
*Phase: 05-real-money-readiness-operations*
*Completed: 2026-07-02*
