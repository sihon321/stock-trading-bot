"""Typed runtime configuration and non-secret startup reporting."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TradingMode(str, Enum):
    """Supported trading environments."""

    MOCK = "mock"
    REAL = "real"


class LLMProviderName(str, Enum):
    """Supported LLM providers."""

    CLAUDE = "claude"
    OPENAI = "openai"


class KisCredentialGroup(BaseModel):
    """One atomic KIS environment credential group."""

    domain: str
    app_key: SecretStr
    app_secret: SecretStr
    tr_id_profile: str
    label: str


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
    )

    trading_mode: TradingMode = TradingMode.MOCK
    confirm_real_trading: bool = False
    llm_provider: LLMProviderName = LLMProviderName.CLAUDE
    anthropic_api_key: Optional[SecretStr] = None
    openai_api_key: Optional[SecretStr] = None
    kis_mock: KisCredentialGroup
    kis_real: KisCredentialGroup
    dry_run: bool = True

    # Execution rule defaults (D-05, D-06). A BUY/SELL only executes when the
    # parsed signal's confidence meets its side's threshold; both default 0.8.
    buy_confidence_threshold: float = 0.8
    sell_confidence_threshold: float = 0.8
    # BUY sizing spends this fraction of available cash, capped by the per-ticker
    # maximum position value (D-06).
    buy_cash_fraction: float = 0.1
    max_position_value: float = 1_000_000.0

    # Risk-net defaults (D-08, D-09). Stop-loss / take-profit are evaluated as
    # percentage moves against the held position's average price; the daily-loss
    # threshold arms the kill switch that blocks new BUYs for the rest of the day.
    stop_loss_pct: float = 0.05
    take_profit_pct: float = 0.10
    daily_loss_threshold: float = 500_000.0

    @model_validator(mode="after")
    def validate_safety_gates(self) -> "Settings":
        if self.trading_mode is TradingMode.REAL and not self.confirm_real_trading:
            raise ValueError(
                "TRADING_MODE=real requires CONFIRM_REAL_TRADING=yes before "
                "real trading configuration can start"
            )
        self._require_selected_llm_key()
        return self

    @property
    def active_kis(self) -> KisCredentialGroup:
        """Return the whole selected KIS credential group."""

        if self.trading_mode is TradingMode.REAL:
            return self.kis_real
        return self.kis_mock

    @property
    def active_llm_api_key(self) -> SecretStr:
        """Return the API key for the selected LLM provider."""

        return self._require_selected_llm_key()

    def _require_selected_llm_key(self) -> SecretStr:
        if self.llm_provider is LLMProviderName.CLAUDE:
            if self.anthropic_api_key is not None:
                return self.anthropic_api_key
            raise ValueError(
                "LLM_PROVIDER=claude requires ANTHROPIC_API_KEY for the active provider"
            )

        if self.openai_api_key is not None:
            return self.openai_api_key
        raise ValueError(
            "LLM_PROVIDER=openai requires OPENAI_API_KEY for the active provider"
        )


def startup_banner(settings: Settings) -> str:
    """Build an allowlisted startup safety banner without secret values."""

    active_kis = settings.active_kis
    return "\n".join(
        (
            "Trading bot startup safety",
            f"Trading mode: {settings.trading_mode.value}",
            f"KIS environment: {active_kis.label}",
            f"LLM provider: {settings.llm_provider.value}",
            f"Dry run: {settings.dry_run}",
            f"Real trading confirmed: {settings.confirm_real_trading}",
            "Secrets: REDACTED",
        )
    )
