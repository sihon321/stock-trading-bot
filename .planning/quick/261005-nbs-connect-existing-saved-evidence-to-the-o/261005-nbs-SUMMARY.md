---
quick_id: 261005-nbs
status: complete
---

# Existing saved evidence connected

The owner successfully logged in and reported that every dashboard item was UNKNOWN. Both protected web deployment configurations had empty registered_resources, so the app had no saved evidence authority.

Registered four fixed read-only resource owners: audit and portfolio in the existing data/audit.db, soak in data/soak.db, and controller in data/soak-controller.db. The empty data/controller.db is not registered. Source schema owners remain independent even when sharing a DB.

Positive attribution comes from one saved mock/KIS_MOCK_VTS identity and exact equality between the production legacy portfolio scope formula (mock, saved suffix plus product code 01) and the persisted portfolio snapshot hash. No raw account details, credentials or cookie secrets were copied into planning artifacts. The protected deployment config retains its exact HTTPS origin, login, signing key and trusted proxy.

Validated all four existing reader schemas, then restarted only the tracked web process. Actual TLS-verified authenticated HTTPS overview, account, holdings, runs, decisions, candidates, orders and workers pages return 200. A saved run ID and holding ticker appear in their rendered pages. Saved holdings count is 10; recent-30-day history has 14 runs, 120 decisions and 147 candidates. All source readers report OK without diagnostic errors. SHA-256 digests of the three source DB files are unchanged after registration and live page verification.

This is historical evidence: portfolio snapshot is 2026-09-08; latest audit observation is 2026-10-02. The default history filter is today, so the owner should select 30d to see existing history. Missing service/validation proof and current-day observations remain UNKNOWN. No trading worker, broker query, provider evaluation or evidence migration was executed. No application source changes or new tests were needed.
