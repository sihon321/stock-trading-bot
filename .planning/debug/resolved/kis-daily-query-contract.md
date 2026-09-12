---
status: resolved
trigger: "Align KIS same-day mock order inquiry with the official request contract and tolerate documented response latency"
created: 2026-08-11
updated: 2026-08-11
---

## Symptoms

- Expected: same-day mock order/fill inquiry uses the current official KIS request contract and obtains a bounded response without weakening order-POST safety.
- Actual: v4 RESUME repeatedly recorded `DAILY_QUERY_TIMEOUT|BALANCE_COMPLETE` after three five-second daily-query attempts.
- Error: `QUERY_TIMEOUT` from `/uapi/domestic-stock/v1/trading/inquire-daily-ccld`; balance succeeded in the same reconciliation.
- Timeline: observed during 2026-08-11 KIS mock soak reconciliation.
- Reproduction: run GET-only `bot soak resume --campaign-id soak-20260811-20d-v4`.

## Current Focus

- hypothesis: confirmed; official exchange routing was absent and the shared five-second limit was insufficient for the mock daily-query response. Query timeout needed separation from the mutation timeout.
- test: both daily-query paths send `EXCG_ID_DVSN_CD=KRX`; GET query timeout is configurable independently from order/hashkey timeout.
- expecting: complete.
- next_action: none; broker truth is now complete and v4 correctly failed closed on a separate reconciliation mismatch.

## Evidence

- timestamp: 2026-08-11; official KIS `inquire_daily_ccld.py` supports same-date start/end, uses `VTTC0081R` for mock within three months, and defaults `EXCG_ID_DVSN_CD` to `KRX`.
- timestamp: 2026-08-11; v4 identity is `official-example-v1`, so RESUME already used `VTTC0081R`; the missing exchange parameter and bounded timeout were the relevant local differences.
- timestamp: 2026-08-11T14:11:10+09:00; GET-only RESUME completed both daily and balance pages under the new 15-second query timeout and persisted snapshot `cdec71c9-d96c-450b-9191-300d3cfc8822` as COMPLETE.
- timestamp: 2026-08-11T14:11:10+09:00; complete KIS truth showed order `0000015678`, BUY 27 of 009830, FILLED, broker order price 36150 and fill price 36135, plus holding quantity 27. The local intent recorded snapped price 36200, so comparison 54 was MISMATCHED and the campaign correctly latched D09.

## Resolution

- root_cause: "The same-day API is supported, but local requests omitted the official KRX exchange discriminator and used one five-second timeout for both GET inquiry and mutation calls. The mock daily endpoint required longer than five seconds during the observed session."
- fix: "Use official within-three-month daily TR IDs VTTC0081R/TTTC0081R, add EXCG_ID_DVSN_CD=KRX to ordinary and paged daily requests, introduce a dedicated 15-second soak query timeout, and retain the existing five-second hashkey/order POST timeout and no-retry boundary."
- verification: "114 focused KIS/soak tests and 697 broad tests excluding the unrelated collection-broken test_soak_campaign.py passed; compileall and git diff --check passed. One live GET-only RESUME returned COMPLETE broker truth without any order POST or retry."
- files_changed: "trading_bot/kis_order.py, trading_bot/soak_config.py, trading_bot/cli.py, tests/test_kis_order.py, tests/test_soak_config.py, tests/test_soak_cli.py"
