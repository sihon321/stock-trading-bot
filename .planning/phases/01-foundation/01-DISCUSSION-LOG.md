# Phase 1: Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-30
**Phase:** 1-Foundation
**Areas discussed:** Config and mode safety, Domain model and port boundaries, Startup behavior and operator feedback

---

## Config and Mode Safety

| Option | Description | Selected |
|--------|-------------|----------|
| Single typed settings object | One `Settings` object loads app mode, KIS credentials, LLM provider, risk defaults, and logging flags from env. | yes |
| Nested typed settings objects | Separate `AppSettings`, `KisSettings`, `LlmSettings`, and `RiskSettings`. | |
| Minimal env helper first | Thin env parsing now, richer typed settings later. | |

**User's choice:** Single typed settings object.
**Notes:** The user selected the recommended safety-oriented foundation path.

| Option | Description | Selected |
|--------|-------------|----------|
| Fail closed on unsafe values | Validate required secrets, use redacted secret types where practical, block startup on missing active values, and test secret redaction. | yes |
| Redact in logs only | Allow settings to load normally, but redact known secret fields in output. | |
| Development lenient, production strict | Allow placeholders in dev, require real values under production/real mode. | |

**User's choice:** Fail closed on unsafe values.
**Notes:** This is a hard safety decision for Phase 1.

| Option | Description | Selected |
|--------|-------------|----------|
| Mode-specific credential groups | Separate mock and real KIS credential groups; selecting mode chooses one whole group. | yes |
| Single credential group plus mode switch | One credential set, with mode changing domain/TR_ID behavior. | |
| Provider object selected by mode | Build a `KisModeConfig` object per mode and expose the selected object. | |

**User's choice:** Mode-specific credential groups.
**Notes:** This prevents partial mock/real swaps.

| Option | Description | Selected |
|--------|-------------|----------|
| Require an explicit confirmation env flag | Real mode starts only if both `trading_mode=real` and confirmation are set. | yes |
| Allow real mode but print a loud banner | Startup makes real mode obvious but does not require second confirmation. | |
| Disallow real mode in v1 foundation | Model real mode config, but block real startup until Phase 5. | |

**User's choice:** Require an explicit confirmation env flag.
**Notes:** The confirmation flag is in addition to `trading_mode=real`.

---

## Domain Model and Port Boundaries

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal core models | Define essential shared objects such as `Decision`, `Order`, `Position`, and small value objects only if useful. | yes |
| Full v1 model skeleton | Add data context, news, indicators, broker responses, audit records, and LLM signals now. | |
| Ports first, models as loose dicts | Define Protocols now and postpone richer models. | |

**User's choice:** Minimal core models.
**Notes:** Avoid over-modeling before implementation pressure exists.

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, include typed signal model now | Add typed `decision`, `confidence`, and `reason` model for the strict JSON contract. | yes |
| No, wait until execution core | Add signal parsing/model in Phase 2. | |
| No, wait until LLM phase | Treat signal as provider-specific until Phase 4. | |

**User's choice:** Yes, include it now.
**Notes:** Phase 1 defines the shared type, not parser enforcement.

| Option | Description | Selected |
|--------|-------------|----------|
| Narrow semantic ports | Define Protocols around business actions such as broker order placement, LLM signal generation, and data context retrieval. | yes |
| Adapter-shaped ports | Mirror KIS/provider/pykrx APIs more closely. | |
| Marker Protocols only | Create empty or near-empty Protocol placeholders. | |

**User's choice:** Narrow semantic ports.
**Notes:** Avoid leaking vendor shapes into the core boundary.

| Option | Description | Selected |
|--------|-------------|----------|
| Synchronous first | Protocol methods are plain sync functions. | yes |
| Async from the start | Protocol methods are `async def`. | |
| Mixed by port | Broker/data sync, LLM async. | |

**User's choice:** Synchronous first.
**Notes:** Matches manual-trigger v1 and keeps orchestration simple.

| Option | Description | Selected |
|--------|-------------|----------|
| Pydantic for settings, dataclasses/enums for domain | Use Pydantic settings validation; keep domain plain. | yes |
| Pydantic everywhere | Settings and domain models are all Pydantic models. | |
| Standard library only | Use dataclasses, Enum, and manual env parsing. | |

**User's choice:** Pydantic for settings, dataclasses/enums for domain.
**Notes:** Balance validation strength with lightweight domain objects.

---

## Startup Behavior and Operator Feedback

| Option | Description | Selected |
|--------|-------------|----------|
| Safety summary banner | Print active mode, KIS environment label, active LLM provider, dry-run setting if present, and real-confirmation state. | yes |
| Mode only | Print just mock vs real. | |
| Full non-secret config summary | Print every non-secret setting. | |

**User's choice:** Safety summary banner.
**Notes:** Banner should support operator sanity checks without becoming noisy.

| Option | Description | Selected |
|--------|-------------|----------|
| Actionable but non-secret errors | Name missing/invalid variables and active mode/provider context, but never print secret values. | yes |
| Generic safe errors | Say config is invalid without naming exact variables. | |
| Verbose debug option | Default safe errors, with a debug flag for more detail. | |

**User's choice:** Actionable but non-secret errors.
**Notes:** Keep failures fixable without leaking values.

| Option | Description | Selected |
|--------|-------------|----------|
| Clear package skeleton | Create `trading_bot/config.py`, `trading_bot/domain.py`, `trading_bot/ports.py`, plus tests. | yes |
| Layered folders now | Start with folders like `config/`, `domain/`, `ports/`, `adapters/`, `services/`. | |
| Let planner decide layout | Capture decisions only; leave module shape to planning. | |

**User's choice:** Clear package skeleton.
**Notes:** Establish an explicit but small Python package structure.

| Option | Description | Selected |
|--------|-------------|----------|
| Safety-focused unit tests | Cover settings loading, missing secrets fail closed, real confirmation, secret redaction, imports, and Protocol shape. | yes |
| Smoke tests only | Confirm imports and one happy-path settings load. | |
| Broad test matrix | Exhaustive config combinations. | |

**User's choice:** Safety-focused unit tests.
**Notes:** Tests should directly defend the foundation's safety guarantees.

---

## the agent's Discretion

The user did not choose any "you decide" options. Exact names and module details remain planner discretion within the locked decisions.

## Deferred Ideas

None.
