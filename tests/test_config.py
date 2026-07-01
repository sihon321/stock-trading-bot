import logging

import pytest
from pydantic import ValidationError

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
