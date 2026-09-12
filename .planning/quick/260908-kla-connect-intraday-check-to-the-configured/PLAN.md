---
status: in-progress
---

# Connect intraday check to the configured mock account

Update the CLI account resolver so mock-mode runtime commands use the existing
SOAK mock account when the general KIS account variables are absent. Preserve
the requirement that real mode only uses the explicitly configured real-account
variables, and add regression coverage for both modes.

Verification: focused intraday/CLI tests and the full offline test suite.
