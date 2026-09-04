"""Typed runtime configuration and non-secret startup reporting."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional, Tuple

from pydantic import BaseModel, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ReportSettings(BaseSettings):
    """Credential-free settings used only by read-only report commands."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
    )

    audit_db_path: Path = Path("./data/audit.db")


class TradingMode(str, Enum):
    """Supported trading environments."""

    MOCK = "mock"
    REAL = "real"


class LLMProviderName(str, Enum):
    """Supported LLM providers."""

    CLAUDE = "claude"
    OPENAI = "openai"
    # Codex CLI provider: instead of an HTTP API call, the bot shells out to the
    # locally installed ``codex`` CLI (``codex exec "<prompt>"``). The CLI holds
    # its own login/credentials, so no API key is required in this project.
    CODEX_CLI = "codex_cli"


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
    anthropic_auth_token: Optional[SecretStr] = None
    openai_api_key: Optional[SecretStr] = None
    # Phase 4 LLM provider pins (D-07/D-09). Anthropic temperature is
    # advisory/log-only because Claude 4.6+ rejects sampling parameters; the
    # OpenAI adapter is the only adapter that transmits its temperature.
    anthropic_model: str = "claude-opus-4-8"
    anthropic_temperature: float = 0.0
    openai_model: str = "gpt-4.1"
    openai_temperature: float = 0.0
    # Codex CLI provider knobs. The bot invokes ``codex_cli_binary exec [args]
    # <prompt>`` and parses a strict JSON signal from stdout. ``codex_cli_model``
    # is passed as ``--model`` only when set; temperature is advisory/log-only
    # because the CLI does not accept a sampling parameter on the command line.
    codex_cli_binary: str = "codex"
    codex_cli_model: Optional[str] = None
    codex_cli_temperature: float = 0.0
    codex_cli_timeout_seconds: float = 120.0
    codex_cli_extra_args: Tuple[str, ...] = ()
    llm_max_retries: int = 3
    llm_retry_backoff_seconds: float = 1.0
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

    # Phase 3 data-source policy (DATA-01..05, D-02/D-08/D-09/D-11/D-12/D-14).
    # Defaults are safe and operator-reviewable; recorded in 03-MANUAL-DECISIONS.md.
    #
    # pykrx price policy (DATA-01/02/05): adjusted prices (수정주가) by default so
    # indicators and screening use a consistent split/dividend-adjusted series.
    ohlcv_adjusted: bool = True
    # Screener breadth/markets/liquidity (D-11/D-12): small candidate set over
    # KOSPI+KOSDAQ, with positive liquidity floors and hard exclusion states.
    screener_max_candidates: int = 20
    screener_markets: Tuple[str, ...] = ("KOSPI", "KOSDAQ")
    screener_min_trading_value: float = 1_000_000_000.0
    screener_min_volume_ratio: float = 1.0
    screener_excluded_states: Tuple[str, ...] = ("HALTED", "DELISTING", "ADMIN")
    # pykrx has no reliable per-call timeout knob, so the adapter wraps vendor
    # calls and skips one stuck ticker instead of freezing the whole screen.
    pykrx_request_timeout_seconds: float = 10.0
    # KIS token/rate controls (DATA-03): refresh margin ahead of the runtime-
    # discovered token expiry, a min inter-request interval, and bounded retries.
    kis_token_refresh_margin_seconds: int = 600
    kis_min_interval_seconds: float = 0.5
    kis_max_retries: int = 3
    kis_retry_backoff_seconds: float = 1.0
    # Naver Finance news (DATA-04): disabled by default (robots.txt disallows
    # general crawlers); adapter fails soft to empty sanitized news when off.
    naver_news_enabled: bool = False
    naver_news_max_items: int = 5
    naver_news_max_chars: int = 2_000
    # Phase 5 operations settings (OPS-02/03, EXEC-04): local audit persistence,
    # fail-soft Discord notifications, and bounded real-order request timeout.
    audit_db_path: str = "./data/audit.db"
    discord_webhook_url: Optional[SecretStr] = None
    order_timeout_seconds: float = 5.0
    intraday_watch_interval_seconds: float = 60.0
    intraday_min_interval_seconds: float = 60.0
    intraday_reconciliation_timeout_seconds: float = 60.0
    intraday_reconciliation_poll_seconds: float = 5.0
    mutation_lease_heartbeat_seconds: float = 30.0
    intraday_long_open_warning_seconds: float = 900.0

    @model_validator(mode="after")
    def validate_safety_gates(self) -> "Settings":
        if self.trading_mode is TradingMode.REAL and not self.confirm_real_trading:
            raise ValueError(
                "TRADING_MODE=real requires CONFIRM_REAL_TRADING=yes before "
                "real trading configuration can start"
            )
        self._require_selected_llm_credentials()
        self._require_positive_source_policy()
        return self

    def _require_positive_source_policy(self) -> None:
        """Fail closed when Phase 3 source-policy controls are non-positive."""

        positive_fields = {
            "screener_max_candidates": self.screener_max_candidates,
            "screener_min_trading_value": self.screener_min_trading_value,
            "screener_min_volume_ratio": self.screener_min_volume_ratio,
            "pykrx_request_timeout_seconds": self.pykrx_request_timeout_seconds,
            "kis_token_refresh_margin_seconds": self.kis_token_refresh_margin_seconds,
            "kis_min_interval_seconds": self.kis_min_interval_seconds,
            "kis_max_retries": self.kis_max_retries,
            "kis_retry_backoff_seconds": self.kis_retry_backoff_seconds,
            "llm_max_retries": self.llm_max_retries,
            "llm_retry_backoff_seconds": self.llm_retry_backoff_seconds,
            "codex_cli_timeout_seconds": self.codex_cli_timeout_seconds,
            "naver_news_max_items": self.naver_news_max_items,
            "naver_news_max_chars": self.naver_news_max_chars,
            "order_timeout_seconds": self.order_timeout_seconds,
            "intraday_min_interval_seconds": self.intraday_min_interval_seconds,
            "intraday_reconciliation_timeout_seconds": self.intraday_reconciliation_timeout_seconds,
            "intraday_reconciliation_poll_seconds": self.intraday_reconciliation_poll_seconds,
            "mutation_lease_heartbeat_seconds": self.mutation_lease_heartbeat_seconds,
            "intraday_long_open_warning_seconds": self.intraday_long_open_warning_seconds,
        }
        for name, value in positive_fields.items():
            if value <= 0:
                raise ValueError(
                    f"{name} must be positive, got {value}"
                )
        if self.intraday_watch_interval_seconds < self.intraday_min_interval_seconds:
            raise ValueError(
                "intraday_watch_interval_seconds must be at least "
                "intraday_min_interval_seconds"
            )

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

    def _require_selected_llm_credentials(self) -> None:
        """Fail closed when the active provider has no usable credential.

        For CLAUDE, either an API key or an OAuth auth token satisfies the
        requirement (auth token takes precedence at client construction). For
        OPENAI, only the API key is accepted. This is the validator hook and
        must not read ``active_llm_api_key`` on the auth-token-only path.
        """

        if self.llm_provider is LLMProviderName.CLAUDE:
            if self.anthropic_api_key is None and self.anthropic_auth_token is None:
                raise ValueError(
                    "LLM_PROVIDER=claude requires ANTHROPIC_API_KEY or "
                    "ANTHROPIC_AUTH_TOKEN for the active provider"
                )
            return

        if self.llm_provider is LLMProviderName.CODEX_CLI:
            # The Codex CLI authenticates itself (its own login/token store); the
            # bot never handles a Codex API key, so there is no credential to
            # require here.
            return

        if self.openai_api_key is None:
            raise ValueError(
                "LLM_PROVIDER=openai requires OPENAI_API_KEY for the active provider"
            )

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
