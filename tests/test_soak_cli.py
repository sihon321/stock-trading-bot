from pathlib import Path

from pydantic import SecretStr
from typer.testing import CliRunner

from trading_bot.config import KisCredentialGroup
from trading_bot.soak_config import SoakSettings
from trading_bot.soak_models import (
    BrokerPageEnvelope,
    CompatibilityState,
    PageCompleteness,
    SoakEvidenceClass,
)
from trading_bot.soak_compat import CompatibilityResult


def _settings(tmp_path: Path, *, domain: str = "https://openapivts.koreainvestment.com:29443") -> SoakSettings:
    return SoakSettings(
        kis_mock=KisCredentialGroup(
            domain=domain,
            app_key=SecretStr("app-key-secret"),
            app_secret=SecretStr("app-secret-secret"),
            tr_id_profile="official-example-v1",
            label="mock",
        ),
        kis_mock_account_cano=SecretStr("12345678"),
        primary_audit_db_path=tmp_path / "audit.db",
        soak_db_path=tmp_path / "soak.db",
        controller_db_path=tmp_path / "controller.db",
        accepted_profile_versions=("official-example-v1",),
    )


def _result() -> CompatibilityResult:
    envelope = BrokerPageEnvelope(
        rows=(), summary={}, page_count=1,
        completeness=PageCompleteness.COMPLETE, reason_code="COMPLETE",
    )
    return CompatibilityResult(
        CompatibilityState.ACCEPTED,
        SoakEvidenceClass.KIS_OBSERVED,
        "official-example-v1",
        envelope,
        envelope,
        {"daily_pages": 1},
    )


def test_cli_registers_one_soak_group_and_probe_is_post_free(tmp_path: Path, monkeypatch) -> None:
    import trading_bot.cli as cli

    calls = {"adapter": 0, "probe": 0}
    monkeypatch.setattr(cli, "_soak_settings_factory", lambda: _settings(tmp_path))
    monkeypatch.setattr(cli, "_build_soak_adapter", lambda settings: calls.__setitem__("adapter", calls["adapter"] + 1) or object())
    monkeypatch.setattr(cli, "_soak_probe", lambda *args, **kwargs: calls.__setitem__("probe", calls["probe"] + 1) or _result())
    monkeypatch.setattr(cli, "build_runtime", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("general runtime called")))

    result = CliRunner().invoke(cli.app, ["soak", "start", "--campaign-id", "campaign-1", "--probe-only"])

    assert result.exit_code == 0, result.output
    assert calls == {"adapter": 1, "probe": 1}
    assert "target=mock" in result.stdout
    assert "account_suffix=5678" in result.stdout
    assert "12345678" not in result.output
    assert sum(group.name == "soak" for group in cli.app.registered_groups) == 1


def test_invalid_identity_stops_before_any_runtime_or_mutation(tmp_path: Path, monkeypatch) -> None:
    import trading_bot.cli as cli

    calls: list[str] = []
    monkeypatch.setattr(cli, "_soak_settings_factory", lambda: _settings(tmp_path, domain="https://openapi.koreainvestment.com:9443"))
    monkeypatch.setattr(cli, "_build_soak_adapter", lambda settings: calls.append("adapter"))
    monkeypatch.setattr(cli, "_soak_probe", lambda *args, **kwargs: calls.append("probe"))
    monkeypatch.setattr(cli, "build_runtime", lambda *args, **kwargs: calls.append("runtime"))

    result = CliRunner().invoke(cli.app, ["soak", "start", "--campaign-id", "campaign-1", "--probe-only"])

    assert result.exit_code == 2
    assert "MOCK_ISOLATION_BLOCKED" in result.stderr
    assert calls == []
    assert "app-key-secret" not in result.output


def test_proof_order_is_explicit_and_fails_closed_until_prerequisites_exist(tmp_path: Path, monkeypatch) -> None:
    import trading_bot.cli as cli

    monkeypatch.setattr(cli, "_soak_settings_factory", lambda: _settings(tmp_path))
    monkeypatch.setattr(cli, "_build_soak_adapter", lambda settings: (_ for _ in ()).throw(AssertionError("adapter reached")))

    result = CliRunner().invoke(cli.app, ["soak", "start", "--campaign-id", "campaign-1", "--proof-order"])

    assert result.exit_code == 2
    assert "PROOF_ORDER_PREREQUISITES_MISSING" in result.stderr


def test_probe_fixture_export_is_conflict_safe(tmp_path: Path, monkeypatch) -> None:
    import trading_bot.cli as cli

    output = tmp_path / "compat.json"
    monkeypatch.setattr(cli, "_soak_settings_factory", lambda: _settings(tmp_path))
    monkeypatch.setattr(cli, "_build_soak_adapter", lambda settings: object())
    monkeypatch.setattr(cli, "_soak_probe", lambda *args, **kwargs: _result())
    args = ["soak", "start", "--campaign-id", "campaign-1", "--probe-only", "--fixture", str(output)]

    first = CliRunner().invoke(cli.app, args)
    second = CliRunner().invoke(cli.app, args)
    output.write_text("conflict", encoding="utf-8")
    conflict = CliRunner().invoke(cli.app, args)

    assert first.exit_code == second.exit_code == 0
    assert conflict.exit_code == 2
    assert "COMPATIBILITY_FIXTURE_CONFLICT" in conflict.stderr
    document = output.read_text(encoding="utf-8")
    assert "12345678" not in document
    assert "app-key-secret" not in document
