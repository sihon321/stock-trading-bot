import logging

import pytest
from pydantic import SecretStr, ValidationError

from conftest import make_settings

from trading_bot.config import (
    KisCredentialGroup,
    LLMProviderName,
    Settings,
    TradingMode,
    startup_banner,
)


SECRET_VALUES = (
    "mock-app-key-secret",
    "mock-app-secret-secret",
    "real-app-key-secret",
    "real-app-secret-secret",
    "anthropic-api-key-secret",
    "openai-api-key-secret",
)

ENV_KEYS = (
    "TRADING_MODE",
    "CONFIRM_REAL_TRADING",
    "LLM_PROVIDER",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_MODEL",
    "ANTHROPIC_TEMPERATURE",
    "OPENAI_MODEL",
    "OPENAI_TEMPERATURE",
    "LLM_MAX_RETRIES",
    "LLM_RETRY_BACKOFF_SECONDS",
    "KIS_MOCK__DOMAIN",
    "KIS_MOCK__APP_KEY",
    "KIS_MOCK__APP_SECRET",
    "KIS_MOCK__TR_ID_PROFILE",
    "KIS_MOCK__LABEL",
    "KIS_REAL__DOMAIN",
    "KIS_REAL__APP_KEY",
    "KIS_REAL__APP_SECRET",
    "KIS_REAL__TR_ID_PROFILE",
    "KIS_REAL__LABEL",
    "DRY_RUN",
    "BUY_CONFIDENCE_THRESHOLD",
    "SELL_CONFIDENCE_THRESHOLD",
    "BUY_CASH_FRACTION",
    "MAX_POSITION_VALUE",
    "STOP_LOSS_PCT",
    "TAKE_PROFIT_PCT",
    "DAILY_LOSS_THRESHOLD",
    # Phase 3 data-pipeline source-policy fields (DATA-01..05, D-02/08/09/11/12/14).
    "OHLCV_ADJUSTED",
    "SCREENER_MAX_CANDIDATES",
    "SCREENER_MARKETS",
    "SCREENER_MIN_TRADING_VALUE",
    "SCREENER_MIN_VOLUME_RATIO",
    "SCREENER_EXCLUDED_STATES",
    "KIS_TOKEN_REFRESH_MARGIN_SECONDS",
    "KIS_MIN_INTERVAL_SECONDS",
    "KIS_MAX_RETRIES",
    "KIS_RETRY_BACKOFF_SECONDS",
    "NAVER_NEWS_ENABLED",
    "NAVER_NEWS_MAX_ITEMS",
    "NAVER_NEWS_MAX_CHARS",
    "AUDIT_DB_PATH",
    "DISCORD_WEBHOOK_URL",
    "ORDER_TIMEOUT_SECONDS",
)


def set_base_env(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> None:
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

    values = {
        "TRADING_MODE": "mock",
        "CONFIRM_REAL_TRADING": "no",
        "LLM_PROVIDER": "claude",
        "ANTHROPIC_API_KEY": "anthropic-api-key-secret",
        "KIS_MOCK__DOMAIN": "https://mock.example.test",
        "KIS_MOCK__APP_KEY": "mock-app-key-secret",
        "KIS_MOCK__APP_SECRET": "mock-app-secret-secret",
        "KIS_MOCK__TR_ID_PROFILE": "mock",
        "KIS_MOCK__LABEL": "KIS mock account",
        "KIS_REAL__DOMAIN": "https://real.example.test",
        "KIS_REAL__APP_KEY": "real-app-key-secret",
        "KIS_REAL__APP_SECRET": "real-app-secret-secret",
        "KIS_REAL__TR_ID_PROFILE": "real",
        "KIS_REAL__LABEL": "KIS real account",
        "DRY_RUN": "true",
    }
    values.update(overrides)

    for key, value in values.items():
        monkeypatch.setenv(key, value)


def assert_no_secret_leaked(*texts: str) -> None:
    combined = "\n".join(texts)
    for secret in SECRET_VALUES:
        assert secret not in combined


def test_settings_load_secrets_without_repr_banner_or_log_leaks(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    set_base_env(monkeypatch)
    settings = Settings()

    with caplog.at_level(logging.INFO):
        logging.getLogger("trading_bot.config").info(startup_banner(settings))

    assert settings.trading_mode is TradingMode.MOCK
    assert settings.llm_provider is LLMProviderName.CLAUDE
    assert settings.active_kis.app_key.get_secret_value() == "mock-app-key-secret"
    assert settings.active_llm_api_key.get_secret_value() == "anthropic-api-key-secret"
    assert "REDACTED" in startup_banner(settings)
    assert_no_secret_leaked(repr(settings), startup_banner(settings), caplog.text)


def test_mock_mode_selects_complete_mock_kis_group(monkeypatch: pytest.MonkeyPatch) -> None:
    set_base_env(monkeypatch, TRADING_MODE="mock")

    settings = Settings()

    assert isinstance(settings.active_kis, KisCredentialGroup)
    assert settings.active_kis == settings.kis_mock
    assert settings.active_kis != settings.kis_real
    assert settings.active_kis.domain == "https://mock.example.test"
    assert settings.active_kis.tr_id_profile == "mock"
    assert settings.active_kis.label == "KIS mock account"


def test_real_mode_requires_confirmation_before_selecting_real_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_base_env(monkeypatch, TRADING_MODE="real", CONFIRM_REAL_TRADING="no")

    with pytest.raises(ValidationError) as exc_info:
        Settings()

    diagnostic = str(exc_info.value)
    assert "TRADING_MODE=real" in diagnostic
    assert "CONFIRM_REAL_TRADING=yes" in diagnostic
    assert "real trading" in diagnostic.lower()
    assert_no_secret_leaked(diagnostic)


def test_real_mode_with_confirmation_selects_complete_real_kis_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_base_env(monkeypatch, TRADING_MODE="real", CONFIRM_REAL_TRADING="yes")

    settings = Settings()

    assert settings.trading_mode is TradingMode.REAL
    assert settings.confirm_real_trading is True
    assert settings.active_kis == settings.kis_real
    assert settings.active_kis != settings.kis_mock
    assert settings.active_kis.domain == "https://real.example.test"
    assert settings.active_kis.tr_id_profile == "real"
    assert settings.active_kis.label == "KIS real account"


def test_claude_provider_requires_only_anthropic_key(monkeypatch: pytest.MonkeyPatch) -> None:
    set_base_env(monkeypatch, LLM_PROVIDER="claude")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    settings = Settings()

    assert settings.llm_provider is LLMProviderName.CLAUDE
    assert settings.active_llm_api_key.get_secret_value() == "anthropic-api-key-secret"


def test_openai_provider_requires_only_openai_key(monkeypatch: pytest.MonkeyPatch) -> None:
    set_base_env(monkeypatch, LLM_PROVIDER="openai", OPENAI_API_KEY="openai-api-key-secret")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    settings = Settings()

    assert settings.llm_provider is LLMProviderName.OPENAI
    assert settings.active_llm_api_key.get_secret_value() == "openai-api-key-secret"


def test_selected_llm_provider_missing_key_fails_without_inactive_secret_requirement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_base_env(monkeypatch, LLM_PROVIDER="openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ValidationError) as exc_info:
        Settings()

    diagnostic = str(exc_info.value)
    assert "OPENAI_API_KEY" in diagnostic
    assert "openai" in diagnostic
    assert "ANTHROPIC_API_KEY" not in diagnostic
    assert_no_secret_leaked(diagnostic)


def test_phase4_llm_defaults_are_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_base_env(monkeypatch)

    settings = Settings()

    assert settings.anthropic_model == "claude-opus-4-8"
    assert settings.anthropic_temperature == 0.0
    assert settings.openai_model == "gpt-4.1"
    assert settings.openai_temperature == 0.0
    assert settings.llm_max_retries == 3
    assert settings.llm_retry_backoff_seconds == 1.0


def test_phase4_llm_fields_accept_environment_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_base_env(
        monkeypatch,
        ANTHROPIC_MODEL="claude-sonnet-4-6",
        ANTHROPIC_TEMPERATURE="0.2",
        OPENAI_MODEL="gpt-4.1-mini",
        OPENAI_TEMPERATURE="0.1",
        LLM_MAX_RETRIES="5",
        LLM_RETRY_BACKOFF_SECONDS="2.5",
    )

    settings = Settings()

    assert settings.anthropic_model == "claude-sonnet-4-6"
    assert settings.anthropic_temperature == 0.2
    assert settings.openai_model == "gpt-4.1-mini"
    assert settings.openai_temperature == 0.1
    assert settings.llm_max_retries == 5
    assert settings.llm_retry_backoff_seconds == 2.5


@pytest.mark.parametrize(
    "override",
    [
        {"LLM_MAX_RETRIES": "0"},
        {"LLM_RETRY_BACKOFF_SECONDS": "0"},
    ],
)
def test_phase4_non_positive_llm_retry_values_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    override: dict[str, str],
) -> None:
    set_base_env(monkeypatch, **override)

    with pytest.raises(ValidationError) as exc_info:
        Settings()

    diagnostic = str(exc_info.value)
    assert next(iter(override)).lower() in diagnostic.lower()
    assert_no_secret_leaked(diagnostic)


def test_phase4_llm_temperature_zero_is_valid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_base_env(
        monkeypatch,
        ANTHROPIC_TEMPERATURE="0.0",
        OPENAI_TEMPERATURE="0.0",
    )

    settings = Settings()

    assert settings.anthropic_temperature == 0.0
    assert settings.openai_temperature == 0.0


def test_execution_and_risk_defaults_are_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_base_env(monkeypatch)

    settings = Settings()

    # D-05: separate BUY/SELL confidence thresholds, both default 0.8.
    assert settings.buy_confidence_threshold == 0.8
    assert settings.sell_confidence_threshold == 0.8
    # D-06: cash fraction and per-ticker max position cap.
    assert 0.0 < settings.buy_cash_fraction <= 1.0
    assert settings.max_position_value > 0
    # D-09: stop-loss / take-profit percentages against average price.
    assert settings.stop_loss_pct > 0
    assert settings.take_profit_pct > 0
    # D-08: daily-loss kill-switch threshold.
    assert settings.daily_loss_threshold > 0


def test_execution_and_risk_fields_accept_environment_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_base_env(
        monkeypatch,
        BUY_CONFIDENCE_THRESHOLD="0.9",
        SELL_CONFIDENCE_THRESHOLD="0.7",
        BUY_CASH_FRACTION="0.25",
        MAX_POSITION_VALUE="1500000",
        STOP_LOSS_PCT="0.05",
        TAKE_PROFIT_PCT="0.12",
        DAILY_LOSS_THRESHOLD="300000",
    )

    settings = Settings()

    assert settings.buy_confidence_threshold == 0.9
    assert settings.sell_confidence_threshold == 0.7
    assert settings.buy_cash_fraction == 0.25
    assert settings.max_position_value == 1500000.0
    assert settings.stop_loss_pct == 0.05
    assert settings.take_profit_pct == 0.12
    assert settings.daily_loss_threshold == 300000.0


def test_phase3_source_policy_defaults_are_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_base_env(monkeypatch)

    settings = Settings()

    # DATA-01/02/05: adjusted OHLCV (수정주가) per recorded manual decision.
    assert settings.ohlcv_adjusted is True
    # D-02/D-11: small operator-reviewable screener breadth over KOSPI+KOSDAQ.
    assert settings.screener_max_candidates == 20
    assert settings.screener_markets == ("KOSPI", "KOSDAQ")
    # D-11/D-12: positive liquidity floors.
    assert settings.screener_min_trading_value > 0
    assert settings.screener_min_volume_ratio > 0
    assert isinstance(settings.screener_excluded_states, tuple)
    assert settings.screener_excluded_states  # non-empty exclusion set
    # DATA-03: KIS token/rate controls, all positive.
    assert settings.kis_token_refresh_margin_seconds == 600
    assert settings.kis_min_interval_seconds == 0.5
    assert settings.kis_max_retries == 3
    assert settings.kis_retry_backoff_seconds == 1.0
    # DATA-04: Naver scraping disabled by default.
    assert settings.naver_news_enabled is False
    assert settings.naver_news_max_items > 0
    assert settings.naver_news_max_chars > 0


def test_phase3_source_policy_fields_accept_environment_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_base_env(
        monkeypatch,
        OHLCV_ADJUSTED="false",
        SCREENER_MAX_CANDIDATES="5",
        SCREENER_MARKETS='["KOSPI"]',
        SCREENER_MIN_TRADING_VALUE="2000000000",
        SCREENER_MIN_VOLUME_RATIO="1.5",
        SCREENER_EXCLUDED_STATES='["HALTED"]',
        KIS_TOKEN_REFRESH_MARGIN_SECONDS="300",
        KIS_MIN_INTERVAL_SECONDS="1.0",
        KIS_MAX_RETRIES="5",
        KIS_RETRY_BACKOFF_SECONDS="2.0",
        NAVER_NEWS_ENABLED="true",
        NAVER_NEWS_MAX_ITEMS="3",
        NAVER_NEWS_MAX_CHARS="500",
    )

    settings = Settings()

    assert settings.ohlcv_adjusted is False
    assert settings.screener_max_candidates == 5
    assert settings.screener_markets == ("KOSPI",)
    assert settings.screener_min_trading_value == 2_000_000_000.0
    assert settings.screener_min_volume_ratio == 1.5
    assert settings.screener_excluded_states == ("HALTED",)
    assert settings.kis_token_refresh_margin_seconds == 300
    assert settings.kis_min_interval_seconds == 1.0
    assert settings.kis_max_retries == 5
    assert settings.kis_retry_backoff_seconds == 2.0
    assert settings.naver_news_enabled is True
    assert settings.naver_news_max_items == 3
    assert settings.naver_news_max_chars == 500


@pytest.mark.parametrize(
    "override",
    [
        {"SCREENER_MAX_CANDIDATES": "0"},
        {"SCREENER_MIN_TRADING_VALUE": "0"},
        {"SCREENER_MIN_VOLUME_RATIO": "0"},
        {"KIS_TOKEN_REFRESH_MARGIN_SECONDS": "-1"},
        {"KIS_MIN_INTERVAL_SECONDS": "-0.5"},
        {"KIS_MAX_RETRIES": "-1"},
        {"KIS_RETRY_BACKOFF_SECONDS": "-1"},
        {"NAVER_NEWS_MAX_ITEMS": "0"},
        {"NAVER_NEWS_MAX_CHARS": "0"},
    ],
)
def test_phase3_non_positive_source_policy_values_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    override: dict[str, str],
) -> None:
    set_base_env(monkeypatch, **override)

    with pytest.raises(ValidationError) as exc_info:
        Settings()

    assert_no_secret_leaked(str(exc_info.value))


def test_phase3_source_policy_fields_do_not_leak_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_base_env(monkeypatch, NAVER_NEWS_ENABLED="true")

    settings = Settings()

    assert_no_secret_leaked(repr(settings), startup_banner(settings))


def test_phase5_audit_db_path_default_is_gitignored_location() -> None:
    assert make_settings().audit_db_path == "./data/audit.db"


def test_phase5_discord_webhook_is_secret_and_redacted_from_banner() -> None:
    webhook_url = "https://discord.test/webhook/SECRET"
    settings = make_settings(discord_webhook_url=SecretStr(webhook_url))

    assert settings.discord_webhook_url is not None
    assert settings.discord_webhook_url.get_secret_value() == webhook_url
    assert webhook_url not in startup_banner(settings)


def test_phase5_non_positive_order_timeout_fails_closed() -> None:
    with pytest.raises(ValidationError) as exc_info:
        make_settings(order_timeout_seconds=0)

    assert "order_timeout_seconds" in str(exc_info.value)


def test_config_import_has_no_execution_or_risk_module_side_effects() -> None:
    import importlib
    import sys

    before_import = set(sys.modules)
    importlib.import_module("trading_bot.config")

    loaded = set(sys.modules) - before_import
    for forbidden in (
        "anthropic",
        "openai",
        "pykrx",
        "requests",
        "httpx",
    ):
        assert forbidden not in loaded
    forbidden_local = [
        name
        for name in loaded
        if name.startswith("trading_bot.")
        and any(fragment in name for fragment in ("execution", "risk", "adapter", "kis", "broker"))
    ]
    assert forbidden_local == []


def test_startup_banner_reports_safety_facts_without_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_base_env(
        monkeypatch,
        TRADING_MODE="real",
        CONFIRM_REAL_TRADING="yes",
        LLM_PROVIDER="openai",
        OPENAI_API_KEY="openai-api-key-secret",
        DRY_RUN="false",
    )

    banner = startup_banner(Settings())

    assert "Trading mode: real" in banner
    assert "KIS environment: KIS real account" in banner
    assert "LLM provider: openai" in banner
    assert "Dry run: False" in banner
    assert "Real trading confirmed: True" in banner
    assert "Secrets: REDACTED" in banner
    assert_no_secret_leaked(banner)
