from pathlib import Path
from datetime import date

import pytest
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
from trading_bot.soak_models import ReconciliationStage


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


def test_soak_runtime_wires_only_its_selected_mock_adapter_as_calendar_witness(
    tmp_path: Path, monkeypatch
) -> None:
    import trading_bot.cli as cli

    settings = _settings(tmp_path)
    settings.primary_audit_db_path.touch()
    captured: dict[str, object] = {}
    calls: list[str] = []

    class Adapter:
        _token_manager = object()
        _request_limiter = object()

        def fetch_trading_day(self, day):
            calls.append(f"calendar:{day}")
            return True

        def place_order_cash(self, *args, **kwargs):
            raise AssertionError("calendar wiring must not submit an order")

    class Connection:
        def close(self):
            calls.append("primary:close")

    class Store(Connection):
        pass

    class Calendar:
        def __init__(self, _ohlcv, *, calendar_witness, **_kwargs):
            captured["calendar_witness"] = calendar_witness

    class Policy:
        def __init__(self, calendar):
            captured["calendar"] = calendar

        def completed_bar_cutoff(self, _day):
            return type("Cutoff", (), {"available": True, "cutoff_date": date(2026, 7, 25)})()

    class Quote:
        def fetch_current_price(self, _ticker):
            raise AssertionError("calendar wiring must not read a quote")

    monkeypatch.setattr(cli, "validate_store_topology", lambda *args: None)
    monkeypatch.setattr(cli, "_read_audit_health", lambda *_args: type("Health", (), {"healthy": True})())
    monkeypatch.setattr(cli, "build_soak_identity_receipt", lambda *_args: object())
    monkeypatch.setattr(cli, "_build_soak_adapter", lambda _settings: Adapter())
    monkeypatch.setattr(cli.sqlite_audit, "connect", lambda _path: Connection())
    monkeypatch.setattr(cli, "connect_soak_store", lambda _path: Store())
    monkeypatch.setattr(cli, "ObservedKRXCalendar", Calendar)
    monkeypatch.setattr(cli, "MarketCyclePolicy", Policy)
    monkeypatch.setattr(cli, "SoakCampaignService", lambda **_kwargs: object())
    monkeypatch.setattr(cli, "KisQuoteAdapter", lambda **_kwargs: Quote())
    monkeypatch.setattr(cli, "build_data_source", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(cli, "build_llm_provider", lambda _settings: object())
    monkeypatch.setattr(cli, "KISBroker", lambda **_kwargs: object())
    monkeypatch.setattr(
        cli, "build_runtime", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("general runtime called"))
    )

    runtime = cli._build_soak_runtime(settings, "campaign-1")

    witness = captured["calendar_witness"]
    assert callable(witness)
    assert witness(date(2026, 7, 28)) is True
    assert calls == ["calendar:2026-07-28"]
    runtime.close()


def test_proof_order_is_explicit_and_fails_closed_until_prerequisites_exist(tmp_path: Path, monkeypatch) -> None:
    import trading_bot.cli as cli

    monkeypatch.setattr(cli, "_soak_settings_factory", lambda: _settings(tmp_path))
    monkeypatch.setattr(cli, "_build_soak_adapter", lambda settings: (_ for _ in ()).throw(AssertionError("adapter reached")))

    result = CliRunner().invoke(cli.app, ["soak", "start", "--campaign-id", "campaign-1", "--proof-order"])

    assert result.exit_code == 2
    assert "PROOF_ORDER_PREREQUISITES_MISSING" in result.stderr


def test_proof_order_uses_dedicated_service_after_exact_confirmation(tmp_path: Path, monkeypatch) -> None:
    import json
    import trading_bot.cli as cli

    settings = _settings(tmp_path)
    settings.primary_audit_db_path.touch()
    settings.soak_db_path.touch()
    accepted = tmp_path / "accepted.json"
    accepted.write_text(json.dumps({
        "schema_version": "kis-mock-compat-v1", "state": "ACCEPTED",
        "evidence_class": "KIS_OBSERVED", "profile_version": "official-example-v1",
    }), encoding="utf-8")
    calls: list[object] = []

    class Service:
        def __init__(self, *, adapter):
            calls.append(adapter)

        def run(self, request):
            calls.append(request)
            return type("Result", (), {"cross_ids_validated": True})()

    monkeypatch.setattr(cli, "_soak_settings_factory", lambda: settings)
    monkeypatch.setattr(cli, "_build_soak_adapter", lambda value: "mock-adapter")
    monkeypatch.setattr(cli, "_proof_service_factory", Service)
    monkeypatch.setattr(cli, "build_runtime", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("general runtime called")))
    result = CliRunner().invoke(cli.app, [
        "soak", "start", "--campaign-id", "proof-1", "--proof-order",
        "--ticker", "005930", "--side", "BUY", "--quantity", "1", "--price", "70000",
        "--accepted-profile", str(accepted), "--confirm", "PROOF MOCK 5678 005930 1",
    ])
    assert result.exit_code == 0, result.output
    assert calls[0] == "mock-adapter"
    assert len(calls) == 2


def test_bad_proof_confirmation_has_zero_service_and_zero_campaign_mutation(tmp_path: Path, monkeypatch) -> None:
    import json
    import sqlite3
    import trading_bot.cli as cli

    settings = _settings(tmp_path)
    settings.primary_audit_db_path.touch()
    settings.soak_db_path.touch()
    accepted = tmp_path / "accepted.json"
    accepted.write_text(json.dumps({
        "schema_version": "kis-mock-compat-v1", "state": "ACCEPTED",
        "evidence_class": "KIS_OBSERVED", "profile_version": "official-example-v1",
    }), encoding="utf-8")
    calls: list[str] = []
    monkeypatch.setattr(cli, "_soak_settings_factory", lambda: settings)
    monkeypatch.setattr(cli, "_build_soak_adapter", lambda value: calls.append("adapter"))
    result = CliRunner().invoke(cli.app, [
        "soak", "start", "--campaign-id", "proof-1", "--proof-order",
        "--ticker", "005930", "--side", "BUY", "--quantity", "1", "--price", "70000",
        "--accepted-profile", str(accepted), "--confirm", "yes",
    ])
    assert result.exit_code == 2
    assert "PROOF_ORDER_CONFIRMATION_MISMATCH" in result.stderr
    assert calls == []
    assert sqlite3.connect(settings.soak_db_path).execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='soak_campaigns'"
    ).fetchone() is None


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


def test_soak_command_family_is_exact_and_ordinary_run_has_no_soak_switches() -> None:
    import re
    import trading_bot.cli as cli

    runner = CliRunner()
    nested = runner.invoke(cli.app, ["soak", "--help"])
    ordinary = runner.invoke(cli.app, ["run", "--help"])

    assert nested.exit_code == 0
    assert re.findall(r"│\s+(start|run|resume|status|drill)\s", nested.stdout) == [
        "start", "run", "resume", "status", "drill"
    ]
    assert ordinary.exit_code == 0
    assert "soak" not in ordinary.stdout.lower()
    assert "fault" not in ordinary.stdout.lower()


def test_drill_is_the_only_cli_route_with_fault_authority(tmp_path: Path, monkeypatch) -> None:
    import trading_bot.cli as cli

    calls: list[tuple[object, str]] = []

    class Service:
        def __init__(self, *, settings):
            assert settings == "drill-settings"

        def run(self, fault, campaign_id):
            calls.append((fault, campaign_id))
            return type(
                "Result",
                (),
                {
                    "drill_id": "generated-drill-id",
                    "verdict": type("Verdict", (), {"value": "PASSED"})(),
                },
            )()

    monkeypatch.setattr(cli, "_soak_settings_factory", lambda: "drill-settings")
    monkeypatch.setattr(cli, "_drill_service_factory", Service)
    result = CliRunner().invoke(
        cli.app,
        ["soak", "drill", "accepted-then-timeout", "--campaign-id", "campaign-1"],
    )

    assert result.exit_code == 0, result.output
    assert calls == [(cli.FaultName.ACCEPTED_THEN_TIMEOUT, "campaign-1")]
    assert "drill_id=generated-drill-id" in result.stdout
    assert "drill_verdict=PASSED" in result.stdout
    assert "fault" not in cli._SoakRuntime.__dataclass_fields__
    assert "fault" not in cli._build_soak_runtime.__code__.co_varnames


class _Campaign:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.status = {"state": "ACTIVE", "active_freezes": [{"ticker": "000660"}]}

    def start_campaign(self, **kwargs):
        self.calls.append("campaign:create")
        return self.status

    def finalize_designated_day(self, **kwargs):
        self.calls.append("campaign:finalize")
        return type("Verdict", (), {"code": type("Code", (), {"value": "CREDITED"})()})()

    def load_status(self, campaign_id):
        self.calls.append("campaign:status")
        return self.status


def _runtime(calls: list[str]):
    import trading_bot.cli as cli

    campaign = _Campaign(calls)

    def reconcile(stage, run_id):
        calls.append(f"reconcile:{stage.value}")
        return type("Result", (), {"complete": True})()

    def execute(run_id, post_submission):
        calls.append("production:decision-risk-sizing")
        calls.append("production:post")
        post_submission()
        return {"run_id": run_id, "submissions": 1}

    return cli._SoakRuntime(
        campaign_id="campaign",
        settings=_settings(Path("/tmp/soak-cli-test")),
        receipt=object(),
        campaign=campaign,
        persist_receipt=lambda: calls.append("receipt:persist"),
        reconcile=reconcile,
        bootstrap_controller=lambda: calls.append("controller:bootstrap"),
        execute_designated=execute,
        rebuild_freezes=lambda: calls.append("freeze:rebuild") or {"000660": object()},
        close=lambda: calls.append("runtime:close"),
    )


def test_start_persists_receipt_reconciles_and_bootstraps_before_activation() -> None:
    import trading_bot.cli as cli

    calls: list[str] = []
    cli._orchestrate_soak_start(_runtime(calls), campaign_policy={})
    assert calls[:5] == [
        "campaign:create",
        "receipt:persist",
        "reconcile:STARTUP",
        "controller:bootstrap",
        "campaign:status",
    ]


def test_start_bootstraps_empty_controller_for_read_only_predrill_status(
    tmp_path: Path, monkeypatch
) -> None:
    import sqlite3

    import trading_bot.cli as cli
    from trading_bot import sqlite_audit
    from trading_bot.soak_campaign import SoakCampaignService
    from trading_bot.soak_controller import (
        CONTROLLER_SCHEMA_VERSION,
        bootstrap_controller_journal,
    )
    from trading_bot.soak_store import connect_soak_store

    settings = _settings(tmp_path)
    sqlite_audit.connect(settings.primary_audit_db_path).close()
    soak = connect_soak_store(settings.soak_db_path)
    campaign = SoakCampaignService(
        market_policy=object(),
        store=soak,
        daily_report_builder=lambda day: (_ for _ in ()).throw(
            AssertionError("daily report reached")
        ),
    )
    runtime = cli._SoakRuntime(
        campaign_id="campaign-1",
        settings=settings,
        receipt=object(),
        campaign=campaign,
        persist_receipt=lambda: None,
        reconcile=lambda stage, run_id: type("Result", (), {"complete": True})(),
        bootstrap_controller=lambda: bootstrap_controller_journal(
            settings.controller_db_path,
            settings.primary_audit_db_path,
            settings.soak_db_path,
        ),
        execute_designated=lambda run_id, post_submission: (_ for _ in ()).throw(
            AssertionError("submission path reached")
        ),
        rebuild_freezes=lambda: (_ for _ in ()).throw(
            AssertionError("freeze mutation reached")
        ),
        close=soak.close,
    )

    assert not settings.controller_db_path.exists()
    status = cli._orchestrate_soak_start(
        runtime,
        campaign_policy={
            "accepted_profile_fingerprint": "sha256:test",
            "accepted_profile_version": "official-example-v1",
            "field_contract_version": "kis-mock-compat-v1",
            "ambiguity_policy_version": "ambiguity-v1",
            "ambiguity_window_seconds": 60,
            "ambiguity_poll_cadence_seconds": 5,
            "ambiguity_max_observations": 12,
        },
    )
    runtime.close()

    assert getattr(status["state"], "value", status["state"]) == "ACTIVE"
    controller = sqlite3.connect(settings.controller_db_path)
    try:
        assert controller.execute("PRAGMA user_version").fetchone()[0] == (
            CONTROLLER_SCHEMA_VERSION
        )
        assert controller.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        for table in (
            "drill_contracts",
            "drill_commits",
            "drill_observations",
            "drill_verdicts",
        ):
            assert controller.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    finally:
        controller.close()

    before = settings.controller_db_path.read_bytes()
    monkeypatch.setattr(cli, "_soak_settings_factory", lambda: settings)
    result = CliRunner().invoke(
        cli.app, ["soak", "status", "--campaign-id", "campaign-1"]
    )

    assert result.exit_code == 0, result.output
    assert "상태: ACTIVE" in result.stdout
    assert settings.controller_db_path.read_bytes() == before


def test_designated_run_has_all_reconciliation_boundaries_in_order() -> None:
    import trading_bot.cli as cli

    calls: list[str] = []
    result = cli._orchestrate_soak_run(
        _runtime(calls), run_id="run-1", observed_at="2026-07-20T10:00:00+09:00"
    )
    assert result["verdict"] == "CREDITED"
    assert calls == [
        "reconcile:PRE_RUN",
        "production:decision-risk-sizing",
        "production:post",
        "reconcile:POST_SUBMISSION",
        "reconcile:PRE_FINALIZE",
        "campaign:finalize",
    ]


def test_resume_reconciles_and_rebuilds_freezes_without_submission() -> None:
    import trading_bot.cli as cli

    calls: list[str] = []
    status = cli._orchestrate_soak_resume(_runtime(calls))
    assert status["active_freezes"] == [{"ticker": "000660"}]
    assert calls == [
        "reconcile:RESUME",
        "freeze:rebuild",
        "campaign:status",
    ]
    assert not any(item.startswith("production:") for item in calls)


def test_incomplete_reconciliation_blocks_each_forbidden_mutation() -> None:
    import trading_bot.cli as cli

    calls: list[str] = []
    runtime = _runtime(calls)
    runtime = cli._SoakRuntime(
        **{
            **runtime.__dict__,
            "reconcile": lambda stage, run_id: type("Result", (), {"complete": False})(),
        }
    )
    with pytest.raises(RuntimeError, match="RECONCILIATION_INCOMPLETE"):
        cli._orchestrate_soak_run(
            runtime, run_id="run-1", observed_at="2026-07-20T10:00:00+09:00"
        )
    assert not any(item.startswith("production:") for item in calls)


def test_status_is_read_only() -> None:
    import trading_bot.cli as cli

    calls: list[str] = []
    status = cli._orchestrate_soak_status(_runtime(calls))
    assert status["state"] == "ACTIVE"
    assert calls == ["campaign:status"]


def test_status_cli_uses_only_the_read_only_triple_store_report(
    tmp_path: Path, monkeypatch
) -> None:
    import trading_bot.cli as cli

    settings = _settings(tmp_path)
    calls: list[object] = []

    class Repository:
        def __init__(self, audit, soak, controller):
            calls.append((audit, soak, controller))

    monkeypatch.setattr(cli, "_soak_settings_factory", lambda: settings)
    monkeypatch.setattr(cli, "_soak_report_repository_factory", Repository)
    monkeypatch.setattr(
        cli,
        "_soak_report_builder",
        lambda repository, campaign_id: calls.append((repository, campaign_id)) or "report",
    )
    monkeypatch.setattr(cli, "_soak_report_renderer", lambda report: "truthful-report\n")
    monkeypatch.setattr(
        cli,
        "_soak_runtime_factory",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("live runtime called")),
    )
    monkeypatch.setattr(
        cli,
        "_build_soak_adapter",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("KIS called")),
    )

    result = CliRunner().invoke(
        cli.app, ["soak", "status", "--campaign-id", "campaign-1"]
    )

    assert result.exit_code == 0, result.output
    assert result.stdout == "truthful-report\n"
    assert calls[0] == (
        settings.primary_audit_db_path,
        settings.soak_db_path,
        settings.controller_db_path,
    )
    assert calls[1][1] == "campaign-1"
