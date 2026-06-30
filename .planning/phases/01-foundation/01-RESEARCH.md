# Phase 1: Foundation - Research

**Researched:** 2026-06-30
**Domain:** Python typed configuration, secret-safe settings, domain models, and port Protocols
**Confidence:** MEDIUM

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
## Implementation Decisions

### Config and Mode Safety
- **D-01:** Use one typed `Settings` object for runtime configuration. It should load app mode, KIS credentials, active LLM provider, risk defaults where needed, and logging/safety flags from environment.
- **D-02:** Secret handling must fail closed. Required secrets for the selected active mode/provider must be validated at startup, secret fields must use redacted/secret-safe representations where practical, and tests must assert secrets do not leak through repr or logs.
- **D-03:** Represent KIS mock and real configuration as separate credential groups. Selecting `trading_mode` chooses one whole group, including domain and TR_ID policy, so endpoint, app key, app secret, and TR_ID cannot be mixed independently.
- **D-04:** Real trading mode requires a second explicit confirmation environment flag such as `CONFIRM_REAL_TRADING=yes`. `trading_mode=real` without that confirmation must fail startup.

### Domain Model and Port Boundaries
- **D-05:** Start with minimal core domain models: `Decision`, `Order`, `Position`, and small value objects such as `Ticker` or `Money` only if useful during planning.
- **D-06:** Include a typed LLM signal model now for the strict JSON contract: `decision`, `confidence`, and `reason`. Phase 1 defines the shared type; fail-safe parsing and enforcement happen in later phases.
- **D-07:** Define narrow semantic Protocols instead of adapter-shaped/vendor-shaped interfaces. Initial ports should represent business actions such as broker position lookup/order placement, LLM signal generation, and data context retrieval.
- **D-08:** Keep port contracts synchronous first. The v1 bot is manually triggered, and async should be introduced later only if concrete adapters need it.
- **D-09:** Use Pydantic for settings/env validation and standard-library dataclasses/enums for domain objects unless later implementation pressure justifies Pydantic domain models.

### Startup Behavior and Operator Feedback
- **D-10:** Print a safety summary startup banner containing active trading mode, KIS environment label, active LLM provider, dry-run setting if present, and whether real-trading confirmation is active. Secrets must always be redacted.
- **D-11:** Configuration failures should be actionable but non-secret. Errors may name the missing or invalid environment variable and active mode/provider context, but must never print secret values.
- **D-12:** Create a clear package skeleton for the foundation, such as `trading_bot/config.py`, `trading_bot/domain.py`, `trading_bot/ports.py`, plus tests.
- **D-13:** Phase 1 tests must be safety-focused unit tests covering settings loading, missing secrets failing closed, real mode requiring confirmation, secret redaction, domain model imports, and Protocol import/type shape.

### the agent's Discretion
No decisions were delegated wholesale to the agent. The planner may choose exact class, enum, and environment variable names consistent with the decisions above.

### Deferred Ideas (OUT OF SCOPE)
## Deferred Ideas

None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CFG-01 | Operator can configure all secrets via gitignored `.env`, loaded through typed settings; secrets never appear in logs | Use `pydantic-settings` `BaseSettings` with `.env` support, `SecretStr`, fail-closed validation, and pytest `caplog` assertions. [CITED: https://docs.pydantic.dev/latest/concepts/pydantic_settings/] [CITED: https://docs.pydantic.dev/latest/api/types/#pydantic.types.SecretStr] [CITED: https://docs.pytest.org/en/stable/how-to/logging.html] |
| CFG-02 | Operator selects `mock` / `real`; mode binds KIS domain, appkey, appsecret, and TR_ID atomically | Model mock and real as separate credential groups and expose only an `active_kis` derived property selected by `TradingMode`; do not expose independent active domain/key/TR_ID env vars. [VERIFIED: .planning/phases/01-foundation/01-CONTEXT.md] |
| CFG-03 | Operator selects active LLM provider (`claude` / `openai`); exactly one is active per run | Use a typed `LLMProviderName` enum/Literal and an `active_llm_secret` resolver that validates only the selected provider's required secret. [VERIFIED: .planning/REQUIREMENTS.md] |
</phase_requirements>

## Summary

Phase 1 should establish a small Python package with four stable surfaces: typed settings, domain models, semantic ports, and safety-focused tests. `pydantic-settings` is the standard fit for typed environment and `.env` loading, while Pydantic secret types provide redacted display by default; the planner should still add explicit tests that no startup banner, config repr, or validation error prints secret values. [CITED: https://docs.pydantic.dev/latest/concepts/pydantic_settings/] [CITED: https://docs.pydantic.dev/latest/api/types/#pydantic.types.SecretStr]

The most important design choice is to make trading mode a selector over whole credential groups, not a set of independent active fields. That means `Settings.trading_mode` returns one `KisCredentials` object containing domain, app key, app secret, and TR_ID policy; real mode additionally requires `CONFIRM_REAL_TRADING=yes`. [VERIFIED: .planning/phases/01-foundation/01-CONTEXT.md]

**Primary recommendation:** Use `pydantic-settings` for `Settings`, stdlib `Enum`/frozen `dataclass` for domain models, `typing.Protocol` for synchronous semantic ports, and pytest `monkeypatch`/`caplog` tests as the first implementation wave. [CITED: https://docs.python.org/3/library/typing.html] [CITED: https://docs.pytest.org/en/stable/how-to/monkeypatch.html]

## Project Constraints (from AGENTS.md)

No `AGENTS.md`, `CLAUDE.md`, or `.claude/CLAUDE.md` was found by `find . -maxdepth 3 \( -name AGENTS.md -o -name CLAUDE.md \) -print`; therefore there are no additional project instruction directives beyond `.planning/*` for this phase. [VERIFIED: codebase grep]

Local project skills under `.agents/skills/` are migrated GSD source-command routers, not implementation conventions for this Python package. [VERIFIED: codebase grep]

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|--------------|----------------|-----------|
| Typed runtime settings | CLI / Application bootstrap | Filesystem `.env` | Settings are loaded before adapters run and should fail startup before any trading path is reachable. [VERIFIED: .planning/phases/01-foundation/01-CONTEXT.md] |
| Secret loading/redaction | CLI / Application bootstrap | Test suite | Secrets enter through env/.env and must be validated/redacted before logging or errors. [VERIFIED: .planning/REQUIREMENTS.md] |
| Atomic mock/real KIS binding | Domain configuration layer | Future broker adapter | The selected mode owns the complete KIS credential group so future adapters receive one coherent config object. [VERIFIED: .planning/phases/01-foundation/01-CONTEXT.md] |
| LLM provider selection | Domain configuration layer | Future LLM adapter | Exactly one provider is selected at settings resolution time; provider implementations are later phases. [VERIFIED: .planning/REQUIREMENTS.md] |
| Domain models and ports | Core package | Future adapters | Models and Protocols define stable contracts with no concrete external calls in this phase. [VERIFIED: .planning/ROADMAP.md] |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pydantic-settings` [WARNING: flagged as suspicious by package gate due recent latest release/unknown downloads; verify before installing.] | 2.11.0 | `BaseSettings`, `.env`, environment parsing, nested settings | Official Pydantic settings package for settings/config classes from environment variables and secret files. [CITED: https://docs.pydantic.dev/latest/concepts/pydantic_settings/] [VERIFIED: PyPI `pip3 index versions`] |
| `pydantic` [WARNING: flagged as suspicious by package gate due unknown downloads; verify before installing.] | 2.13.4 | `BaseModel`, validation errors, `SecretStr` | Pydantic types include secret wrappers whose display is redacted; `pydantic-settings` builds on Pydantic. [CITED: https://docs.pydantic.dev/latest/api/types/#pydantic.types.SecretStr] [VERIFIED: PyPI `pip3 index versions`] |
| Python stdlib `dataclasses`, `enum`, `typing.Protocol` | Python 3.9.6 local | Domain models and semantic ports | Protocol supports structural subtyping/static duck typing; dataclasses/enums keep the domain dependency-light. [CITED: https://docs.python.org/3/library/typing.html] [VERIFIED: `python3 --version`] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` [WARNING: flagged as suspicious by package gate due recent latest release/unknown downloads; verify before installing.] | 8.4.2 | Unit tests for settings, logs, imports, and ports | Use immediately in Wave 0 because no test infrastructure exists. [CITED: https://docs.pytest.org/en/stable/] [VERIFIED: PyPI `pip3 index versions`] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `pydantic-settings` | `python-dotenv` plus custom dataclasses | Reject for this phase because custom validation/redaction/error shaping increases safety risk. [ASSUMED] |
| stdlib `Protocol` | Abstract base classes | Protocol is better for narrow semantic ports because adapters can satisfy contracts structurally without inheritance. [CITED: https://docs.python.org/3/library/typing.html] |
| dataclass domain objects | Pydantic domain models | Dataclasses match the locked decision to keep domain objects lightweight unless later pressure justifies validation-heavy models. [VERIFIED: .planning/phases/01-foundation/01-CONTEXT.md] |

**Installation:**
```bash
pip install "pydantic-settings==2.11.0" "pydantic==2.13.4" "pytest==8.4.2"
```

**Version verification performed:**
```bash
pip3 index versions pydantic-settings  # latest 2.11.0
pip3 index versions pydantic           # latest 2.13.4
pip3 index versions pytest             # latest 8.4.2
```

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `pydantic-settings` | PyPI | latest published 2026-06-19 | unknown via gate | https://github.com/pydantic/pydantic-settings | SUS | Flagged -- planner must add `checkpoint:human-verify` before install. [VERIFIED: package-legitimacy] |
| `pydantic` | PyPI | latest published 2026-05-06 | unknown via gate | https://github.com/pydantic/pydantic | SUS | Flagged -- planner must add `checkpoint:human-verify` before install. [VERIFIED: package-legitimacy] |
| `pytest` | PyPI | latest published 2026-06-19 | unknown via gate | https://github.com/pytest-dev/pytest | SUS | Flagged -- planner must add `checkpoint:human-verify` before install. [VERIFIED: package-legitimacy] |

**Packages removed due to [SLOP] verdict:** none. [VERIFIED: package-legitimacy]
**Packages flagged as suspicious [SUS]:** `pydantic-settings`, `pydantic`, `pytest`. [VERIFIED: package-legitimacy]

## Architecture Patterns

### System Architecture Diagram

```text
.env / environment
        |
        v
Settings(BaseSettings)
        |
        +--> validate selected LLM provider -> active_llm_secret
        |
        +--> trading_mode decision
                 |
                 +--> mock -> complete KisCredentialGroup(mock domain, key, secret, TR_ID profile)
                 |
                 +--> real -> require CONFIRM_REAL_TRADING=yes
                              -> complete KisCredentialGroup(real domain, key, secret, TR_ID profile)
        |
        v
startup_safety_banner(settings) -> prints mode/provider/dry-run/confirmation only
        |
        v
domain.py + ports.py import cleanly for later phases
```

### Recommended Project Structure

```text
pyproject.toml
trading_bot/
├── __init__.py
├── config.py        # Settings, enums, credential groups, startup banner text
├── domain.py        # Decision, Order, Position, LLMSignal, optional value objects
└── ports.py         # Broker, LLMProvider, DataSource Protocols
tests/
├── test_config.py
├── test_domain.py
└── test_ports.py
```

### Pattern 1: Atomic Mode Binding

**What:** Store mock and real KIS settings as separate nested models and expose one derived `active_kis` property. [VERIFIED: .planning/phases/01-foundation/01-CONTEXT.md]

**When to use:** Every time future code needs KIS domain, app key, app secret, or TR_ID policy. [VERIFIED: .planning/ROADMAP.md]

**Example:**
```python
# Source: Pydantic Settings docs + Phase 1 CONTEXT decisions
from enum import Enum
from pydantic import BaseModel, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TradingMode(str, Enum):
    MOCK = "mock"
    REAL = "real"


class KisCredentialGroup(BaseModel):
    domain: str
    app_key: SecretStr
    app_secret: SecretStr
    tr_id_profile: str
    label: str


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_nested_delimiter="__")

    trading_mode: TradingMode = TradingMode.MOCK
    confirm_real_trading: bool = False
    kis_mock: KisCredentialGroup
    kis_real: KisCredentialGroup

    @model_validator(mode="after")
    def reject_unconfirmed_real_mode(self) -> "Settings":
        if self.trading_mode is TradingMode.REAL and not self.confirm_real_trading:
            raise ValueError("TRADING_MODE=real requires CONFIRM_REAL_TRADING=yes")
        return self

    @property
    def active_kis(self) -> KisCredentialGroup:
        return self.kis_real if self.trading_mode is TradingMode.REAL else self.kis_mock
```

### Pattern 2: Secret-Safe Banner

**What:** Build banner text from non-secret fields only; never interpolate `SecretStr.get_secret_value()`. [CITED: https://docs.pydantic.dev/latest/api/types/#pydantic.types.SecretStr]

**Example:**
```python
def startup_banner(settings: Settings) -> str:
    active = settings.active_kis
    return (
        "=== TRADING BOT STARTUP SAFETY ===\n"
        f"Trading mode: {settings.trading_mode.value.upper()}\n"
        f"KIS environment: {active.label}\n"
        f"LLM provider: {settings.llm_provider.value}\n"
        f"Real trading confirmed: {settings.confirm_real_trading}\n"
        "Secrets: REDACTED\n"
        "=================================="
    )
```

### Pattern 3: Semantic Protocol Ports

**What:** Define business-action Protocols with synchronous methods and domain types, not vendor payload shapes. [CITED: https://docs.python.org/3/library/typing.html] [VERIFIED: .planning/phases/01-foundation/01-CONTEXT.md]

**Example:**
```python
from typing import Optional, Protocol


class Broker(Protocol):
    def get_position(self, ticker: Ticker) -> Optional[Position]: ...
    def place_order(self, order: Order) -> str: ...


class LLMProvider(Protocol):
    def generate_signal(self, context: "DataContext") -> LLMSignal: ...


class DataSource(Protocol):
    def build_context(self, ticker: Ticker) -> "DataContext": ...
```

### Anti-Patterns to Avoid

- **Independent active KIS env vars:** Do not define `KIS_DOMAIN`, `KIS_APPKEY`, `KIS_APPSECRET`, and `KIS_TR_ID` as separately selectable active values; that permits partial mock/real mixing. [VERIFIED: .planning/phases/01-foundation/01-CONTEXT.md]
- **Logging full settings objects:** Do not log `Settings.model_dump()` or validation payloads containing secrets; banner should be hand-built from allowlisted non-secret fields. [CITED: https://docs.pydantic.dev/latest/api/types/#pydantic.types.SecretStr] [ASSUMED]
- **Runtime adapter imports in ports:** Do not import KIS, Anthropic, OpenAI, pykrx, or scraping libraries in Phase 1 ports; adapters are later phases. [VERIFIED: .planning/ROADMAP.md]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Env and `.env` loading | Custom parser | `pydantic-settings` | Handles typed settings, dotenv, env priority, nested env delimiters. [CITED: https://docs.pydantic.dev/latest/concepts/pydantic_settings/] |
| Secret display redaction | Custom `__repr__` masking for every field | Pydantic `SecretStr` plus allowlisted banner | Secret types redact display; tests still verify no leaks. [CITED: https://docs.pydantic.dev/latest/api/types/#pydantic.types.SecretStr] |
| Port polymorphism | Base classes with inheritance requirements | `typing.Protocol` | Protocol supports structural subtyping/static duck typing. [CITED: https://docs.python.org/3/library/typing.html] |
| Log capture tests | Manual logger handlers | pytest `caplog` | pytest provides log capture fixtures and record/text inspection. [CITED: https://docs.pytest.org/en/stable/how-to/logging.html] |

**Key insight:** Phase 1 is a safety foundation, not an adapter phase; use standard config/test primitives and keep all external trading/LLM implementations out. [VERIFIED: .planning/ROADMAP.md]

## Common Pitfalls

### Pitfall 1: Secret Values Leak Through Diagnostics

**What goes wrong:** A failed settings load, startup banner, or debug log includes app keys or LLM API keys. [VERIFIED: .planning/REQUIREMENTS.md]
**Why it happens:** Code logs raw settings dumps or interpolates secret values for convenience. [ASSUMED]
**How to avoid:** Use `SecretStr`, hand-build the banner from allowlisted fields, and assert known fake secrets are absent from `repr(settings)`, `startup_banner(settings)`, and `caplog.text`. [CITED: https://docs.pydantic.dev/latest/api/types/#pydantic.types.SecretStr] [CITED: https://docs.pytest.org/en/stable/how-to/logging.html]
**Warning signs:** Tests search for `"mock-secret"` or `"real-secret"` in logs and fail. [ASSUMED]

### Pitfall 2: Partial Mock/Real Swaps

**What goes wrong:** Real domain is paired with mock TR_ID or mock key, or the inverse. [VERIFIED: .planning/phases/01-foundation/01-CONTEXT.md]
**Why it happens:** Active KIS fields are configured independently. [VERIFIED: .planning/phases/01-foundation/01-CONTEXT.md]
**How to avoid:** Only expose grouped mock/real config and an `active_kis` property. [VERIFIED: .planning/phases/01-foundation/01-CONTEXT.md]
**Warning signs:** Tests can instantiate settings with mixed active components. [ASSUMED]

### Pitfall 3: Validating Both LLM Providers as Required

**What goes wrong:** `LLM_PROVIDER=claude` fails because OpenAI key is absent, or vice versa. [VERIFIED: .planning/REQUIREMENTS.md]
**Why it happens:** All possible provider secrets are modeled as globally required. [ASSUMED]
**How to avoid:** Provider secret fields may be optional at raw settings level, then a validator requires only the active provider's secret. [ASSUMED]
**Warning signs:** Tests for one-provider config cannot pass without setting both keys. [ASSUMED]

### Pitfall 4: Ports Mirror Vendor APIs

**What goes wrong:** `Broker` methods expose KIS request bodies or TR_ID details before adapters exist. [VERIFIED: .planning/phases/01-foundation/01-CONTEXT.md]
**Why it happens:** Interface design starts from planned vendor calls instead of domain actions. [ASSUMED]
**How to avoid:** Methods should express `get_position`, `place_order`, `generate_signal`, and `build_context` over domain types. [VERIFIED: .planning/phases/01-foundation/01-CONTEXT.md]
**Warning signs:** `ports.py` imports HTTP clients, KIS constants, or provider SDK classes. [ASSUMED]

## Code Examples

### Pytest Secret and Env Tests

```python
# Source: pytest caplog and monkeypatch official docs
import logging
import pytest


def test_startup_banner_redacts_secrets(monkeypatch, caplog):
    monkeypatch.setenv("TRADING_MODE", "mock")
    monkeypatch.setenv("KIS_MOCK__APP_KEY", "mock-key")
    monkeypatch.setenv("KIS_MOCK__APP_SECRET", "mock-secret")
    # set remaining required env vars...

    settings = Settings()
    with caplog.at_level(logging.INFO):
        logging.getLogger("trading_bot").info(startup_banner(settings))

    assert "mock-secret" not in caplog.text
    assert "mock-key" not in caplog.text
    assert "Secrets: REDACTED" in caplog.text
```

### One Active LLM Provider

```python
from enum import Enum
from typing import Optional


class LLMProviderName(str, Enum):
    CLAUDE = "claude"
    OPENAI = "openai"


class Settings(BaseSettings):
    llm_provider: LLMProviderName
    anthropic_api_key: Optional[SecretStr] = None
    openai_api_key: Optional[SecretStr] = None

    @property
    def active_llm_api_key(self) -> SecretStr:
        if self.llm_provider is LLMProviderName.CLAUDE and self.anthropic_api_key:
            return self.anthropic_api_key
        if self.llm_provider is LLMProviderName.OPENAI and self.openai_api_key:
            return self.openai_api_key
        raise ValueError(f"Missing API key for active LLM provider: {self.llm_provider.value}")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Pydantic v1 `BaseSettings` inside `pydantic` | `pydantic-settings` package for v2 settings | Pydantic v2 era [ASSUMED] | Planner should add `pydantic-settings`, not rely on `pydantic.BaseSettings`. [CITED: https://docs.pydantic.dev/latest/concepts/pydantic_settings/] |
| Nominal-only adapter inheritance | Structural `Protocol` ports | Python typing Protocol support is in stdlib for local Python 3.9.6. [VERIFIED: `python3 --version`] | Future adapters can satisfy ports without inheriting project base classes. [CITED: https://docs.python.org/3/library/typing.html] |

**Deprecated/outdated:**
- `from pydantic import BaseSettings` for Pydantic v2 settings should not be used; use `from pydantic_settings import BaseSettings`. [CITED: https://docs.pydantic.dev/latest/concepts/pydantic_settings/]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `python-dotenv` plus custom dataclasses is less appropriate than `pydantic-settings` for this safety-focused config layer. | Standard Stack | Planner might overfit to Pydantic when a smaller dependency set is desired. |
| A2 | Logging full settings dumps can leak secrets despite secret field redaction in some serialization/error paths. | Architecture Patterns | Planner should still write explicit leak tests; if wrong, tests are harmless. |
| A3 | Provider-specific secret fields should be optional at raw settings level and required only for the active provider. | Common Pitfalls | Exact Pydantic validator design may differ, but behavior requirement stands. |
| A4 | Port warning signs such as vendor imports indicate over-coupling. | Common Pitfalls | Planner may allow constants if later phases demand them; Phase 1 should not. |

## Open Questions

1. **Exact environment variable names**
   - What we know: Decisions allow planner discretion on names. [VERIFIED: .planning/phases/01-foundation/01-CONTEXT.md]
   - What's unclear: Whether the operator prefers `ANTHROPIC_API_KEY` or `CLAUDE_API_KEY`, and exact KIS naming. [ASSUMED]
   - Recommendation: Use conventional names in `.env.example` and keep aliases only if needed. [ASSUMED]

2. **Exact KIS domain/TR_ID values**
   - What we know: Phase 1 must bind domain and TR_ID policy atomically. [VERIFIED: .planning/REQUIREMENTS.md]
   - What's unclear: The exact production/mock KIS domains and TR_IDs are Phase 5 API-specific details. [VERIFIED: .planning/ROADMAP.md]
   - Recommendation: Store configured values as opaque strings/profile names in Phase 1 and verify actual KIS values in the real broker phase. [ASSUMED]

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Python | Package and tests | yes | 3.9.6 | None needed. [VERIFIED: `python3 --version`] |
| pip | Dependency install | yes | 21.2.4 | Use virtualenv/venv with upgraded pip if planner adds install tasks. [VERIFIED: `pip3 --version`] |
| pytest | Test execution | no | not installed | Add Wave 0 dependency install. [VERIFIED: `python3 -m pytest --version`] |
| pydantic | Settings implementation | no | not installed | Add Wave 0 dependency install. [VERIFIED: local import check] |
| pydantic-settings | Settings implementation | no | not installed | Add Wave 0 dependency install. [VERIFIED: local import check] |

**Missing dependencies with no fallback:**
- `pydantic-settings`, `pydantic`, and `pytest` are not installed locally; implementation requires dependency setup first. [VERIFIED: local import/test checks]

**Missing dependencies with fallback:**
- None for this phase. [VERIFIED: local environment audit]

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.4.2 recommended; not installed locally. [VERIFIED: PyPI `pip3 index versions`] [VERIFIED: local pytest check] |
| Config file | none -- create `pyproject.toml` in Wave 0. [VERIFIED: codebase grep] |
| Quick run command | `python3 -m pytest tests/test_config.py tests/test_domain.py tests/test_ports.py -q` |
| Full suite command | `python3 -m pytest -q` |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| CFG-01 | `.env`/env secrets load through typed settings and never appear in logs/repr/banner | unit | `python3 -m pytest tests/test_config.py -q` | no -- Wave 0 |
| CFG-02 | `trading_mode` selects one complete KIS group; real mode requires confirmation | unit | `python3 -m pytest tests/test_config.py -q` | no -- Wave 0 |
| CFG-03 | exactly one active LLM provider resolves per run | unit | `python3 -m pytest tests/test_config.py -q` | no -- Wave 0 |
| CFG-01/02/03 | domain models and Protocols import cleanly without concrete adapters | import/unit | `python3 -m pytest tests/test_domain.py tests/test_ports.py -q` | no -- Wave 0 |

### Sampling Rate

- **Per task commit:** `python3 -m pytest tests/test_config.py tests/test_domain.py tests/test_ports.py -q`
- **Per wave merge:** `python3 -m pytest -q`
- **Phase gate:** Full suite green before `$gsd-verify-work`

### Wave 0 Gaps

- [ ] `pyproject.toml` -- package metadata and pytest config. [VERIFIED: codebase grep]
- [ ] `tests/test_config.py` -- covers CFG-01, CFG-02, CFG-03. [VERIFIED: codebase grep]
- [ ] `tests/test_domain.py` -- covers model imports/basic construction. [VERIFIED: codebase grep]
- [ ] `tests/test_ports.py` -- covers Protocol imports/type shape. [VERIFIED: codebase grep]
- [ ] Framework install: `pip install "pydantic-settings==2.11.0" "pydantic==2.13.4" "pytest==8.4.2"` after human verification checkpoint. [VERIFIED: package-legitimacy]

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V2 Authentication | no | No user authentication in Phase 1. [VERIFIED: .planning/ROADMAP.md] |
| V3 Session Management | no | No web/session surface in Phase 1. [VERIFIED: .planning/ROADMAP.md] |
| V4 Access Control | yes | Real trading requires separate explicit confirmation flag. [VERIFIED: .planning/phases/01-foundation/01-CONTEXT.md] |
| V5 Input Validation | yes | Pydantic settings validators and enums/Literals for mode/provider. [CITED: https://docs.pydantic.dev/latest/concepts/pydantic_settings/] |
| V6 Cryptography | yes | Do not implement crypto; use secret redaction and avoid custom secret storage in this phase. [CITED: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html] |
| V7 Error Handling and Logging | yes | Actionable non-secret config errors and caplog tests for non-disclosure. [VERIFIED: .planning/phases/01-foundation/01-CONTEXT.md] [CITED: https://docs.pytest.org/en/stable/how-to/logging.html] |

### Known Threat Patterns for Python Config Foundation

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Secret disclosure in logs/errors | Information Disclosure | `SecretStr`, hand-built banner, and `caplog` regression tests. [CITED: https://docs.pydantic.dev/latest/api/types/#pydantic.types.SecretStr] |
| Accidental real-money mode | Elevation of Privilege / Tampering | Default mock mode plus `CONFIRM_REAL_TRADING=yes` required for real mode. [VERIFIED: .planning/phases/01-foundation/01-CONTEXT.md] |
| Mixed mock/real credentials | Tampering | Atomic credential group selected by `TradingMode`. [VERIFIED: .planning/phases/01-foundation/01-CONTEXT.md] |
| Untrusted env values | Tampering | Enum/Literal validation and fail-closed startup errors. [CITED: https://docs.pydantic.dev/latest/concepts/pydantic_settings/] |

## Sources

### Primary (HIGH confidence)

- `.planning/phases/01-foundation/01-CONTEXT.md` -- locked Phase 1 implementation decisions. [VERIFIED: codebase grep]
- `.planning/REQUIREMENTS.md` -- CFG-01, CFG-02, CFG-03 requirement text. [VERIFIED: codebase grep]
- `.planning/ROADMAP.md` -- phase boundary and downstream adapter timing. [VERIFIED: codebase grep]

### Secondary (MEDIUM confidence)

- https://docs.pydantic.dev/latest/concepts/pydantic_settings/ -- Pydantic Settings install, env, dotenv, nested env, and settings source behavior. [CITED]
- https://docs.pydantic.dev/latest/api/types/#pydantic.types.SecretStr -- Pydantic secret type redaction behavior. [CITED]
- https://docs.python.org/3/library/typing.html -- Protocol and structural subtyping behavior. [CITED]
- https://docs.pytest.org/en/stable/how-to/logging.html -- `caplog` assertions. [CITED]
- https://docs.pytest.org/en/stable/how-to/monkeypatch.html -- `monkeypatch.setenv`/`delenv`. [CITED]
- https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html -- secrets management security reference. [CITED]

### Tertiary (LOW confidence)

- Assumptions in the Assumptions Log where exact implementation choices remain planner discretion. [ASSUMED]

## Metadata

**Confidence breakdown:**
- Standard stack: MEDIUM -- official docs and PyPI versions were checked, but package gate flagged all external packages as SUS due recent latest release or unknown download metadata. [VERIFIED: package-legitimacy]
- Architecture: HIGH -- driven primarily by locked Phase 1 decisions and roadmap boundaries. [VERIFIED: .planning/phases/01-foundation/01-CONTEXT.md]
- Pitfalls: MEDIUM -- key pitfalls come from locked safety requirements; some warning signs are inferred. [VERIFIED: .planning/REQUIREMENTS.md] [ASSUMED]

**Research date:** 2026-06-30
**Valid until:** 2026-07-07 for package versions; architecture guidance remains valid until Phase 1 decisions change. [ASSUMED]
