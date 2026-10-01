# Phase 12 Pattern Map

Inline mapping from inspected sources; no existing codebase map was available.

| New responsibility | Existing analog | Reuse boundary |
|---|---|---|
| Strict bundle, guarded dates | trading_bot/replay.py load_replay_bundle/guarded_historical_view | Separate schema; reject unknown fields and future decision access |
| Pure strategy decisions | execution.py, risk.py, screener.py, indicators.py | Narrow adapter to shipped pure functions, float bridge checked; no live coordinator |
| Decimal ledger, simulated broker | trading_bot/domain.py; replay.py MockBroker use | New simulator; production Money is float, MockBroker lacks settlement/costs |
| Canonical evidence | replay.py canonical_json_bytes/compute_result_id/write_replay_result | Reuse serialization/writer ideas; separate backtest validation and identity schema |
| Korean reports and safe output | trading_bot/report_cli.py write_report_text/_deliver | Reuse validated delivery; no settings mutation or runtime initialization |
| Offline registration | trading_bot/cli.py replay/report registration | Lightweight Typer subgroup, explicit capability tripwire tests |

No database schema migration or ORM is needed. Frozen file schemas are versioned explicitly. Read source signatures before implementing adapters. Existing replay/report schema and trading behavior must stay compatible.
