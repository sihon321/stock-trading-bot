# Phase 1: Foundation - Pattern Map

**Mapped:** 2026-06-30
**Files analyzed:** 10
**Analogs found:** 0 / 10

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `pyproject.toml` | config | batch | none - first project config | no-analog |
| `.gitignore` | config | file-I/O | none - no existing ignore config | no-analog |
| `.env.example` | config | file-I/O | none - first env template | no-analog |
| `trading_bot/__init__.py` | config | request-response | none - first package marker | no-analog |
| `trading_bot/config.py` | config | request-response | none - first settings module | no-analog |
| `trading_bot/domain.py` | model | transform | none - first domain module | no-analog |
| `trading_bot/ports.py` | provider | request-response | none - first port module | no-analog |
| `tests/test_config.py` | test | request-response | none - first test module | no-analog |
| `tests/test_domain.py` | test | transform | none - first test module | no-analog |
| `tests/test_ports.py` | test | request-response | none - first test module | no-analog |

## Pattern Assignments

### `pyproject.toml` (config, batch)

**Analog:** No application source analog exists.

**Planning source:** `.planning/phases/01-foundation/01-RESEARCH.md` lines 75-89, 99-117, 148-160.

**Dependency and test config guidance** (lines 79-89):
```markdown
| `pydantic-settings` | 2.11.0 | `BaseSettings`, `.env`, environment parsing, nested settings |
| `pydantic` | 2.13.4 | `BaseModel`, validation errors, `SecretStr` |
| Python stdlib `dataclasses`, `enum`, `typing.Protocol` | Python 3.9.6 local | Domain models and semantic ports |
| `pytest` | 8.4.2 | Unit tests for settings, logs, imports, and ports |
```

**Package legitimacy checkpoint** (lines 113-117):
```markdown
| `pydantic-settings` | PyPI | latest published 2026-06-19 | unknown via gate | ... | SUS | Flagged -- planner must add `checkpoint:human-verify` before install. |
| `pydantic` | PyPI | latest published 2026-05-06 | unknown via gate | ... | SUS | Flagged -- planner must add `checkpoint:human-verify` before install. |
| `pytest` | PyPI | latest published 2026-06-19 | unknown via gate | ... | SUS | Flagged -- planner must add `checkpoint:human-verify` before install. |
```

Planner should create minimal package metadata, pytest configuration, and dependency declarations only after the human verification checkpoint for the flagged packages.

---

### `.gitignore` (config, file-I/O)

**Analog:** No application source analog exists.

**Planning source:** `.planning/ROADMAP.md` lines 32-40 and `.planning/phases/01-foundation/01-CONTEXT.md` lines 17-20.

**Secret file requirement** (ROADMAP lines 37-38):
```markdown
Operator can place all secrets (KIS appkey/secret, LLM API keys) in a gitignored `.env`, and they load through typed settings -- secrets never appear in logs
Selecting `mock` vs `real` in config binds KIS domain, appkey, appsecret, and TR_ID together atomically
```

Planner should ensure `.env` is ignored. Keep `.env.example` tracked with placeholder names only.

---

### `.env.example` (config, file-I/O)

**Analog:** No application source analog exists.

**Planning source:** `.planning/phases/01-foundation/01-CONTEXT.md` lines 17-20, 29-33 and `.planning/phases/01-foundation/01-RESEARCH.md` lines 126-145.

**Environment flow** (RESEARCH lines 126-145):
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
```

Use conventional placeholder variables for nested settings, for example `KIS_MOCK__APP_KEY`, `KIS_MOCK__APP_SECRET`, `KIS_REAL__APP_KEY`, `KIS_REAL__APP_SECRET`, `LLM_PROVIDER`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `TRADING_MODE`, and `CONFIRM_REAL_TRADING`.

---

### `trading_bot/__init__.py` (config, request-response)

**Analog:** No application source analog exists.

**Planning source:** `.planning/phases/01-foundation/01-RESEARCH.md` lines 148-160.

**Project skeleton** (lines 150-160):
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

Keep `__init__.py` side-effect free. Do not load settings or import external adapters at package import time.

---

### `trading_bot/config.py` (config, request-response)

**Analog:** No application source analog exists.

**Planning source:** `.planning/phases/01-foundation/01-RESEARCH.md` lines 169-207, 213-225, 324-346 and `.planning/phases/01-foundation/01-CONTEXT.md` lines 17-20, 29-33.

**Imports pattern from planning guidance** (RESEARCH lines 171-174):
```python
from enum import Enum
from pydantic import BaseModel, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
```

**Atomic KIS mode binding pattern** (RESEARCH lines 177-207):
```python
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

**Startup banner pattern** (RESEARCH lines 215-225):
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

**Active LLM provider pattern** (RESEARCH lines 329-345):
```python
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

**Error handling and validation constraints** (CONTEXT lines 18-20, 30-31):
```markdown
Required secrets for the selected active mode/provider must be validated at startup.
`trading_mode=real` without confirmation must fail startup.
Errors may name the missing or invalid environment variable and active mode/provider context, but must never print secret values.
```

---

### `trading_bot/domain.py` (model, transform)

**Analog:** No application source analog exists.

**Planning source:** `.planning/phases/01-foundation/01-CONTEXT.md` lines 22-27 and `.planning/phases/01-foundation/01-RESEARCH.md` lines 81-83, 95-97.

**Model boundary** (CONTEXT lines 23-27):
```markdown
Start with minimal core domain models: `Decision`, `Order`, `Position`, and small value objects such as `Ticker` or `Money` only if useful during planning.
Include a typed LLM signal model now for the strict JSON contract: `decision`, `confidence`, and `reason`.
Use Pydantic for settings/env validation and standard-library dataclasses/enums for domain objects unless later implementation pressure justifies Pydantic domain models.
```

**Implementation pattern:** use stdlib `Enum` and frozen `dataclass` for domain types. Keep this module free of Pydantic settings, KIS SDKs, LLM SDKs, pykrx, HTTP clients, and filesystem reads.

---

### `trading_bot/ports.py` (provider, request-response)

**Analog:** No application source analog exists.

**Planning source:** `.planning/phases/01-foundation/01-RESEARCH.md` lines 228-248 and `.planning/phases/01-foundation/01-CONTEXT.md` lines 25-26.

**Imports pattern** (RESEARCH lines 232-235):
```python
from typing import Optional, Protocol
```

**Semantic Protocol pattern** (RESEARCH lines 237-248):
```python
class Broker(Protocol):
    def get_position(self, ticker: Ticker) -> Optional[Position]: ...
    def place_order(self, order: Order) -> str: ...


class LLMProvider(Protocol):
    def generate_signal(self, context: "DataContext") -> LLMSignal: ...


class DataSource(Protocol):
    def build_context(self, ticker: Ticker) -> "DataContext": ...
```

**Boundary constraint** (CONTEXT lines 25-26):
```markdown
Define narrow semantic Protocols instead of adapter-shaped/vendor-shaped interfaces.
Keep port contracts synchronous first.
```

---

### `tests/test_config.py` (test, request-response)

**Analog:** No application test analog exists.

**Planning source:** `.planning/phases/01-foundation/01-RESEARCH.md` lines 297-320 and `.planning/phases/01-foundation/01-CONTEXT.md` lines 29-33.

**Test imports and fixtures pattern** (RESEARCH lines 301-304):
```python
import logging
import pytest
```

**Secret redaction test pattern** (RESEARCH lines 307-320):
```python
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

**Required coverage** (CONTEXT lines 30-33):
```markdown
Tests must cover settings loading, missing secrets failing closed, real mode requiring confirmation, secret redaction, domain model imports, and Protocol import/type shape.
```

Add tests for: mock default, real mode without `CONFIRM_REAL_TRADING=yes` raising, complete mock/real credential group selection, active LLM provider requiring only its selected secret, and no fake secret strings in `repr(settings)`, banner text, validation messages, or captured logs.

---

### `tests/test_domain.py` (test, transform)

**Analog:** No application test analog exists.

**Planning source:** `.planning/phases/01-foundation/01-CONTEXT.md` lines 22-27, 32-33 and `.planning/ROADMAP.md` lines 36-40.

**Domain success criteria** (ROADMAP lines 36-40):
```markdown
Domain models (Decision, Order, Position) and the three port Protocols (Broker, LLMProvider, DataSource) exist and import cleanly with no concrete adapters yet
```

Test basic construction/imports for `Decision`, `Order`, `Position`, and `LLMSignal`. Keep these tests pure: no env, no network, no provider SDKs.

---

### `tests/test_ports.py` (test, request-response)

**Analog:** No application test analog exists.

**Planning source:** `.planning/phases/01-foundation/01-RESEARCH.md` lines 228-248, 290-295 and `.planning/phases/01-foundation/01-CONTEXT.md` lines 25-26.

**Port shape pattern** (RESEARCH lines 237-248):
```python
class Broker(Protocol):
    def get_position(self, ticker: Ticker) -> Optional[Position]: ...
    def place_order(self, order: Order) -> str: ...


class LLMProvider(Protocol):
    def generate_signal(self, context: "DataContext") -> LLMSignal: ...


class DataSource(Protocol):
    def build_context(self, ticker: Ticker) -> "DataContext": ...
```

**Anti-pattern guard** (RESEARCH lines 290-295):
```markdown
Ports must not mirror vendor APIs.
Warning signs: `ports.py` imports HTTP clients, KIS constants, or provider SDK classes.
```

Test imports and structural typing with small fake classes. Avoid concrete KIS, Anthropic, OpenAI, pykrx, and scraping imports.

## Shared Patterns

### No Application Analogs
**Source:** `.planning/phases/01-foundation/01-CONTEXT.md` lines 55-65
**Apply to:** All Phase 1 source and test files
```markdown
No application source files exist yet. Phase 1 is expected to create the initial Python package skeleton.
No existing Python package or test pattern exists yet. The planner should establish a simple, testable project layout rather than conforming to prior code.
Future phases will attach concrete KIS, pykrx/Naver, broker, and LLM adapters behind the semantic ports created in this phase.
```

### Secret Safety
**Source:** `.planning/phases/01-foundation/01-CONTEXT.md` lines 17-20, 29-31 and `.planning/phases/01-foundation/01-RESEARCH.md` lines 269-274
**Apply to:** `trading_bot/config.py`, `.env.example`, `tests/test_config.py`
```markdown
Secret handling must fail closed.
Required secrets for the selected active mode/provider must be validated at startup.
Secret fields must use redacted/secret-safe representations where practical.
The startup banner must never print secrets.
Errors may name missing or invalid environment variables, but must never print secret values.
```

### Atomic Trading Mode
**Source:** `.planning/phases/01-foundation/01-RESEARCH.md` lines 163-207 and `.planning/phases/01-foundation/01-CONTEXT.md` lines 19-20
**Apply to:** `trading_bot/config.py`, `.env.example`, `tests/test_config.py`
```markdown
Store mock and real KIS settings as separate nested models and expose one derived `active_kis` property.
`trading_mode=real` requires `CONFIRM_REAL_TRADING=yes`.
Do not expose independent active KIS domain/key/secret/TR_ID fields.
```

### Semantic Synchronous Ports
**Source:** `.planning/phases/01-foundation/01-RESEARCH.md` lines 228-248, 290-295
**Apply to:** `trading_bot/ports.py`, `tests/test_ports.py`
```markdown
Define business-action Protocols with synchronous methods and domain types, not vendor payload shapes.
Do not import KIS, Anthropic, OpenAI, pykrx, or scraping libraries in Phase 1 ports.
```

### Test Style
**Source:** `.planning/phases/01-foundation/01-RESEARCH.md` lines 297-320
**Apply to:** All tests
```markdown
Use pytest `monkeypatch` for env setup and `caplog` for log redaction assertions.
Known fake secrets should be asserted absent from repr, banner, validation diagnostics, and logs.
```

## No Analog Found

Files with no close match in the codebase. Planner should use the planning-artifact guidance above instead of copying source patterns.

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `pyproject.toml` | config | batch | No Python package metadata exists yet. |
| `.gitignore` | config | file-I/O | No existing ignore config exists in repo root. |
| `.env.example` | config | file-I/O | No tracked env template exists yet. |
| `trading_bot/__init__.py` | config | request-response | No application package exists yet. |
| `trading_bot/config.py` | config | request-response | No settings module exists yet. |
| `trading_bot/domain.py` | model | transform | No domain module exists yet. |
| `trading_bot/ports.py` | provider | request-response | No port or adapter module exists yet. |
| `tests/test_config.py` | test | request-response | No tests exist yet. |
| `tests/test_domain.py` | test | transform | No tests exist yet. |
| `tests/test_ports.py` | test | request-response | No tests exist yet. |

## Metadata

**Analog search scope:** repo root via `rg --files` and `find`, including Python/config/test patterns and project skill indexes.
**Files scanned:** 0 application source files; planning artifacts and GSD workflow scaffolding only.
**Project instruction files:** No `AGENTS.md` found. Local `.codex/skills` and `.agents/skills` exist, but sampled indexes are GSD workflow routing/orchestration skills, not Python implementation conventions.
**Pattern extraction date:** 2026-06-30
