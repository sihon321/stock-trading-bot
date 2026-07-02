# Phase 5: Real-Money Readiness & Operations - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-02
**Phase:** 5-Real-Money Readiness & Operations
**Areas discussed:** CLI trigger & real gate, Real KIS order path, Audit store (SQLite), Notifications

---

## CLI Trigger & Real-Money Gate (OPS-01, CFG-04)

### CLI command surface
| Option | Description | Selected |
|--------|-------------|----------|
| run + screen + status | `bot run` / `--dry-run` / `bot screen` / `bot status` — richest surface | ✓ |
| run + --dry-run only | Single `bot run` with a flag; screening internal | |
| run + screen | `bot run` + standalone `bot screen`, no status | |

### Scope of one `bot run`
| Option | Description | Selected |
|--------|-------------|----------|
| Full screened universe | Loop over every candidate | |
| Single ticker via --ticker | One ticker per run | |
| Universe, --ticker optional override | Universe default, narrow with --ticker | ✓ |

### Real-money guard beyond config flag
| Option | Description | Selected |
|--------|-------------|----------|
| Config flag + runtime confirm | Interactive typed confirmation on real runs | |
| Config flag only | Existing gate sufficient | |
| Config flag + --i-understand flag | Per-invocation CLI confirm flag (non-interactive) | ✓ |

### Default behavior of bare `bot run`
| Option | Description | Selected |
|--------|-------------|----------|
| Place mock orders | Bare run places against MockBroker | |
| Dry-run by default | Bare run logs only; --execute to place | ✓ |

**Notes:** Safety-first — dry-run default in both modes; real execution requires config flag + per-invocation confirm + --execute (three independent acts).

---

## Real KIS Order Path (EXEC-04)

### python-kis vs extend direct-REST
| Option | Description | Selected |
|--------|-------------|----------|
| Extend direct-REST layer | Reuse Phase 3 kis_auth + add order endpoints | |
| Introduce python-kis | Add the library for orders | |
| You decide (research first) | Planner compares against live KIS docs + code | ✓ |

### Idempotency mechanism
| Option | Description | Selected |
|--------|-------------|----------|
| Query-before-submit reconcile | Reconcile against broker truth before POST | |
| Client order ID dedup | Deterministic client order ID | |
| Both: client ID + reconcile | Defense in depth | ✓ |

### Partial fill handling
| Option | Description | Selected |
|--------|-------------|----------|
| Record, no auto-chase | Record filled vs requested, no follow-up | |
| Record + reconcile position | Also update tracked position to actual fill | ✓ |
| You decide | Planner decides on KIS semantics | |

### Order pricing/timing
| Option | Description | Selected |
|--------|-------------|----------|
| Limit at current price | Limit using real-time price | |
| Market orders | Immediate fill, less control | |
| Limit + market-hours pre-check | Limit + fail-safe if closed/stale | ✓ |

**Notes:** Order POST treated as the most dangerous op — defense-in-depth idempotency required; no auto-chase; no market orders.

---

## Persistent Audit Store (OPS-02)

### SQLite schema
| Option | Description | Selected |
|--------|-------------|----------|
| One row per ticker-decision | Flat decision rows | |
| One row per cycle (run) | Per-run row with JSON blobs | |
| Two tables: runs + decisions | Normalized, most queryable | ✓ |

### Persist depth
| Option | Description | Selected |
|--------|-------------|----------|
| Full incl. raw prompt/response | DB is system of record incl. raw | |
| Structured fields, no raw prompt | Raw stays in structlog only | |
| Full, raw as reference to log | Structured in DB + correlation ID to structlog raw | ✓ |

### Wiring & DB location
| Option | Description | Selected |
|--------|-------------|----------|
| Writer consumes CycleAuditEvent | New sink module, no domain change | ✓ |
| Extend CycleAuditEvent + writer | Add fields to domain type | |
| You decide | Planner chooses boundary | |

**Notes:** Lean DB, full traceability via correlation ID; no Phase 2 domain-type change; DB at configurable gitignored path (default ~ ./data/audit.db).

---

## Notifications (OPS-03)

### Channel structure
| Option | Description | Selected |
|--------|-------------|----------|
| Telegram behind a Notifier port | Port + Telegram adapter | |
| Telegram directly | No port abstraction | |
| **Discord behind a Notifier port** (user free-text) | Notifier port + Discord webhook adapter; config holds webhook URL; channel-agnostic cycle code | ✓ |

### Triggers
| Option | Description | Selected |
|--------|-------------|----------|
| Per-run summary + errors | One digest per run + immediate error push | ✓ |
| Only trades + errors | Silent on HOLD-only runs | |
| Every ticker decision | One message per ticker incl. HOLDs | |

### Fail-soft handling
| Option | Description | Selected |
|--------|-------------|----------|
| Fail-soft, never block | Log and continue on failure | |
| Fail-soft + retry | Bounded retry then log; never blocks | ✓ |

**Notes:** User chose **Discord** (webhook) over the requirement's Telegram example — deliberate, within OPS-03 scope (channel is illustrative). Notifier port keeps the choice reversible. Per-run digest implies per-ticker error isolation in the run loop.

---

## Claude's Discretion

- KIS order library choice itself (python-kis vs extend direct-REST) — deferred to research (D-05).
- Exact module/symbol names, typer flag naming, SQLite column set/indexes within the two-table shape, correlation-ID scheme, default DB path, Discord message/embed format, and tenacity retry counts/backoff (align with existing KIS defaults).

## Deferred Ideas

- Scheduler / always-on loop (out of scope for v1).
- Ensemble/consensus across LLM providers (ENSEMBLE-01).
- Auto-chasing partial fills.
- Additional notification channels (Telegram/Slack/email) via the Notifier port.
- Interactive typed runtime confirmation (set aside in favor of the non-interactive flag).
