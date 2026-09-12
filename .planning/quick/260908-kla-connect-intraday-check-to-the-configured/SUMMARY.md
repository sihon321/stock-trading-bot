---
status: complete
---

# Summary

Connected mock-mode intraday runtime account resolution to the existing
`SOAK_KIS_MOCK_ACCOUNT_CANO` and product-code settings while keeping real mode
isolated to `KIS_ACCOUNT_*`. Added regression coverage for both modes.

Verification:

- Focused intraday tests: 3 passed.
- Full offline suite: 815 passed.
- Live `bot intraday check` reached the mock portfolio iteration; the prior
  missing `KIS_ACCOUNT_*` configuration error no longer occurs. The live check
  ended at `ITERATION_FAILED`, which is a downstream KIS portfolio-query result.
