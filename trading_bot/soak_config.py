"""Structurally mock-only configuration and identity gate for soak workflows."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from trading_bot.config import KisCredentialGroup
from trading_bot.soak_models import MockIdentityReceipt, MockTrProfile


MOCK_ISOLATION_BLOCKED = "MOCK_ISOLATION_BLOCKED"
MOCK_DOMAIN = "openapivts.koreainvestment.com"
MOCK_PORT = 29443
MOCK_DOMAIN_CLASS = "KIS_MOCK_VTS"
MOCK_ISOLATION_POLICY_VERSION = "mock-isolation-v1"


def validate_store_topology(
    primary_audit_db_path: Path,
    soak_db_path: Path,
    controller_db_path: Path,
) -> dict[str, Path]:
    """Validate the canonical three-store topology before any owner opens a DB."""

    paths = {
        "primary_audit_db_path": Path(primary_audit_db_path),
        "soak_db_path": Path(soak_db_path),
        "controller_db_path": Path(controller_db_path),
    }
    resolved = {
        name: path.expanduser().resolve(strict=False) for name, path in paths.items()
    }
    if len(set(resolved.values())) != len(resolved):
        raise ValueError("database paths must be pairwise distinct")
    items = tuple(paths.items())
    for index, (_, left) in enumerate(items):
        for _, right in items[index + 1 :]:
            if left.exists() and right.exists() and os.path.samefile(left, right):
                raise ValueError("database paths resolve to the same inode")
    return resolved


class SoakSettings(BaseSettings):
    """Credential root whose field graph has no real-target capability."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="SOAK_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    kis_mock: KisCredentialGroup
    kis_mock_account_cano: SecretStr
    kis_mock_account_product_code: str = "01"
    primary_audit_db_path: Path = Path("./data/audit.db")
    soak_db_path: Path = Path("./data/soak.db")
    controller_db_path: Path = Path("./data/soak-controller.db")
    target_eligible_days: int = 20
    availability_failure_budget: int = 2
    accepted_profile_versions: tuple[str, ...]
    mock_isolation_policy_version: str = MOCK_ISOLATION_POLICY_VERSION
    kis_min_interval_seconds: float = 1.0
    kis_max_retries: int = 3
    kis_retry_backoff_seconds: float = 1.0
    kis_timeout_seconds: float = 5.0
    kis_query_timeout_seconds: float = 15.0
    kis_token_refresh_margin_seconds: int = 600
    kis_token_cache_path: Path = Path("./data/.kis-token-cache/tokens.json")

    @model_validator(mode="after")
    def validate_mock_topology(self) -> "SoakSettings":
        if self.target_eligible_days <= 0 or self.availability_failure_budget < 0:
            raise ValueError("soak policy counts must be non-negative and target positive")
        if not self.accepted_profile_versions:
            raise ValueError("at least one accepted mock profile version is required")
        if any(
            value <= 0
            for value in (
                self.kis_min_interval_seconds,
                self.kis_max_retries,
                self.kis_timeout_seconds,
                self.kis_query_timeout_seconds,
                self.kis_token_refresh_margin_seconds,
            )
        ) or self.kis_retry_backoff_seconds < 0:
            raise ValueError("mock KIS query controls must be positive")
        validate_store_topology(
            self.primary_audit_db_path,
            self.soak_db_path,
            self.controller_db_path,
        )
        return self


def _blocked(reason: str) -> ValueError:
    return ValueError(f"{MOCK_ISOLATION_BLOCKED}: {reason}")


def build_soak_identity_receipt(
    settings: SoakSettings,
    campaign_id: str,
    profile: MockTrProfile,
) -> MockIdentityReceipt:
    """Validate every D-03 identity fact before returning immutable evidence."""

    parsed = urlsplit(settings.kis_mock.domain)
    if parsed.scheme != "https" or parsed.hostname != MOCK_DOMAIN or parsed.port != MOCK_PORT:
        raise _blocked("mock domain class mismatch")
    if not campaign_id or len(campaign_id) > 128:
        raise _blocked("campaign id is invalid")
    if profile.version not in settings.accepted_profile_versions:
        raise _blocked("TR profile version is not allowlisted")
    if settings.kis_mock.tr_id_profile != profile.version:
        raise _blocked("configured TR profile does not match selected profile")
    if any(not tr_id.startswith("V") for tr_id in profile.tr_ids):
        raise _blocked("mock TR IDs must be V-prefixed")
    if any(not tr_id or len(tr_id) > 16 for tr_id in profile.tr_ids):
        raise _blocked("mock TR IDs are invalid")
    account = settings.kis_mock_account_cano.get_secret_value()
    if len(account) < 4 or not account.isdigit():
        raise _blocked("mock account format is invalid")
    if settings.mock_isolation_policy_version != MOCK_ISOLATION_POLICY_VERSION:
        raise _blocked("isolation policy version mismatch")
    return MockIdentityReceipt(
        target="mock",
        domain_class=MOCK_DOMAIN_CLASS,
        account_suffix=account[-4:],
        profile_version=profile.version,
        buy_tr_id=profile.buy_tr_id,
        sell_tr_id=profile.sell_tr_id,
        daily_ccld_tr_id=profile.daily_ccld_tr_id,
        balance_tr_id=profile.balance_tr_id,
        campaign_id=campaign_id,
        policy_version=settings.mock_isolation_policy_version,
    )


def render_mock_identity_receipt(receipt: MockIdentityReceipt) -> str:
    """Render only the fixed, non-secret identity allowlist."""

    return "\n".join(
        (
            "KIS mock soak identity receipt",
            f"target={receipt.target}",
            f"domain_class={receipt.domain_class}",
            f"account_suffix={receipt.account_suffix}",
            f"profile_version={receipt.profile_version}",
            f"buy_tr_id={receipt.buy_tr_id}",
            f"sell_tr_id={receipt.sell_tr_id}",
            f"daily_ccld_tr_id={receipt.daily_ccld_tr_id}",
            f"balance_tr_id={receipt.balance_tr_id}",
            f"campaign_id={receipt.campaign_id}",
            f"policy_version={receipt.policy_version}",
            "secrets=REDACTED",
        )
    )
