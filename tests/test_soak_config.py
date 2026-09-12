from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from trading_bot.config import KisCredentialGroup
from trading_bot.soak_config import (
    MOCK_ISOLATION_BLOCKED,
    SoakSettings,
    build_soak_identity_receipt,
    render_mock_identity_receipt,
)
from trading_bot.soak_models import MockTrProfile


SECRETS = ("app-key-value", "app-secret-value", "12345678")


def _profile() -> MockTrProfile:
    return MockTrProfile(
        version="official-example-v1",
        buy_tr_id="VTTC0012U",
        sell_tr_id="VTTC0011U",
        daily_ccld_tr_id="VTTC0081R",
        balance_tr_id="VTTC8434R",
    )


def _settings(tmp_path: Path, **overrides: object) -> SoakSettings:
    values: dict[str, object] = {
        "kis_mock": KisCredentialGroup(
            domain="https://openapivts.koreainvestment.com:29443",
            app_key=SecretStr(SECRETS[0]),
            app_secret=SecretStr(SECRETS[1]),
            tr_id_profile="official-example-v1",
            label="KIS mock account",
        ),
        "kis_mock_account_cano": SecretStr(SECRETS[2]),
        "primary_audit_db_path": tmp_path / "audit.db",
        "soak_db_path": tmp_path / "soak.db",
        "controller_db_path": tmp_path / "controller.db",
        "accepted_profile_versions": ("official-example-v1",),
    }
    values.update(overrides)
    return SoakSettings(**values)


def test_soak_settings_schema_is_structurally_mock_only(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    fields = set(SoakSettings.model_fields)

    assert {"kis_mock", "kis_mock_account_cano", "primary_audit_db_path", "soak_db_path", "controller_db_path"} <= fields
    assert fields.isdisjoint({"kis_real", "trading_mode", "confirm_real_trading", "real_account"})
    assert settings.target_eligible_days == 20
    assert settings.availability_failure_budget == 2
    assert settings.kis_timeout_seconds == 5.0
    assert settings.kis_query_timeout_seconds == 15.0


def test_query_timeout_must_be_positive(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="mock KIS query controls must be positive"):
        _settings(tmp_path, kis_query_timeout_seconds=0)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("primary_audit_db_path", "soak_db_path"),
        ("primary_audit_db_path", "controller_db_path"),
        ("soak_db_path", "controller_db_path"),
    ],
)
def test_all_path_alias_pairs_fail_before_open(tmp_path: Path, left: str, right: str) -> None:
    shared = tmp_path / "shared.db"
    overrides = {left: shared, right: shared}
    with pytest.raises(ValidationError, match="database paths must be pairwise distinct"):
        _settings(tmp_path, **overrides)


def test_existing_same_inode_alias_fails(tmp_path: Path) -> None:
    original = tmp_path / "audit.db"
    alias = tmp_path / "audit-link.db"
    original.touch()
    alias.hardlink_to(original)

    with pytest.raises(ValidationError, match="same inode"):
        _settings(tmp_path, primary_audit_db_path=original, soak_db_path=alias)


def test_identity_receipt_contains_only_required_sanitized_facts(tmp_path: Path) -> None:
    receipt = build_soak_identity_receipt(_settings(tmp_path), "campaign-01", _profile())
    rendered = render_mock_identity_receipt(receipt)

    assert receipt.target == "mock"
    assert receipt.domain_class == "KIS_MOCK_VTS"
    assert receipt.account_suffix == "5678"
    assert receipt.profile_version == "official-example-v1"
    assert receipt.campaign_id == "campaign-01"
    assert receipt.policy_version == "mock-isolation-v1"
    assert all(value in rendered for value in ("target=mock", "account_suffix=5678", "campaign_id=campaign-01"))
    combined = repr(_settings(tmp_path)) + repr(receipt) + rendered
    for secret in SECRETS:
        assert secret not in combined


@pytest.mark.parametrize(
    "settings_override,profile_override",
    [
        ({"kis_mock": KisCredentialGroup(domain="https://openapi.koreainvestment.com:9443", app_key=SecretStr(SECRETS[0]), app_secret=SecretStr(SECRETS[1]), tr_id_profile="official-example-v1", label="mock")}, {}),
        ({"accepted_profile_versions": ("other",)}, {}),
        ({}, {"buy_tr_id": "TTTC0012U"}),
        ({}, {"balance_tr_id": ""}),
    ],
)
def test_identity_mismatch_fails_closed_without_secret_diagnostics(
    tmp_path: Path,
    settings_override: dict[str, object],
    profile_override: dict[str, str],
) -> None:
    profile_values = _profile().__dict__ | profile_override
    with pytest.raises(ValueError) as exc_info:
        build_soak_identity_receipt(
            _settings(tmp_path, **settings_override),
            "campaign-01",
            MockTrProfile(**profile_values),
        )
    message = str(exc_info.value)
    assert MOCK_ISOLATION_BLOCKED in message
    for secret in SECRETS:
        assert secret not in message
