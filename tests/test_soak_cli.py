from pathlib import Path
from datetime import date
from dataclasses import replace

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


def test_soak_adapter_keeps_query_timeout_separate_from_mutation_timeout(
    tmp_path: Path,
) -> None:
    import trading_bot.cli as cli

    adapter = cli._build_soak_adapter(_settings(tmp_path))

    assert adapter._timeout_seconds == 5.0
    assert adapter._query_timeout_seconds == 15.0
    adapter._client.close()


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

    def admit_designated_run(self, **kwargs):
        self.calls.append("campaign:admit")
        return type("Verdict", (), {"code": type("Code", (), {"value": "ADMITTED"})()})()

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


def test_start_resumes_only_exact_incomplete_startup_without_post(tmp_path: Path) -> None:
    import trading_bot.cli as cli
    from trading_bot.soak_campaign import SoakCampaignService
    from trading_bot.soak_store import (
        append_or_validate_identity_receipt,
        append_snapshot,
        connect_soak_store,
    )

    settings = _settings(tmp_path)
    soak = connect_soak_store(settings.soak_db_path)
    campaign = SoakCampaignService(
        market_policy=object(),
        store=soak,
        daily_report_builder=lambda _day: (_ for _ in ()).throw(
            AssertionError("daily report reached")
        ),
    )
    reconciliations = 0
    bootstraps = 0

    def reconcile(stage, run_id):
        nonlocal reconciliations
        reconciliations += 1
        complete = reconciliations == 2
        append_snapshot(
            soak,
            snapshot_id=f"startup-{reconciliations}",
            campaign_id="campaign-1",
            run_id=run_id,
            stage=stage,
            completeness=(
                PageCompleteness.COMPLETE if complete else PageCompleteness.INCOMPLETE
            ),
        )
        return type("Result", (), {"complete": complete})()

    def bootstrap() -> None:
        nonlocal bootstraps
        bootstraps += 1

    runtime = cli._SoakRuntime(
        campaign_id="campaign-1",
        settings=settings,
        receipt=object(),
        campaign=campaign,
        persist_receipt=lambda: append_or_validate_identity_receipt(
            soak,
            receipt_id="campaign-1:identity",
            campaign_id="campaign-1",
            target="mock",
            domain_class="mock.example.test",
            account_suffix="5678",
            profile_version="official-example-v1",
            policy_version="mock-isolation-v1",
            detail={"tr_profile": "official-example-v1"},
        ),
        reconcile=reconcile,
        bootstrap_controller=bootstrap,
        execute_designated=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("POST-capable path reached")
        ),
        rebuild_freezes=lambda: (_ for _ in ()).throw(
            AssertionError("freeze mutation reached")
        ),
        close=soak.close,
    )
    policy = {
        "accepted_profile_fingerprint": "sha256:test",
        "accepted_profile_version": "official-example-v1",
        "field_contract_version": "kis-mock-compat-v1",
        "ambiguity_policy_version": "ambiguity-v1",
        "ambiguity_window_seconds": 60,
        "ambiguity_poll_cadence_seconds": 5,
        "ambiguity_max_observations": 12,
    }

    with pytest.raises(RuntimeError, match="RECONCILIATION_INCOMPLETE:STARTUP"):
        cli._orchestrate_soak_start(runtime, campaign_policy=policy)
    with pytest.raises(ValueError, match="SOAK_START_RESUME_BLOCKED:POLICY_DRIFT"):
        cli._orchestrate_soak_start(
            runtime,
            campaign_policy={**policy, "target_eligible_days": 21},
        )
    identity_drift_runtime = replace(
        runtime,
        persist_receipt=lambda: append_or_validate_identity_receipt(
            soak,
            receipt_id="campaign-1:identity",
            campaign_id="campaign-1",
            target="mock",
            domain_class="mock.example.test",
            account_suffix="9999",
            profile_version="official-example-v1",
            policy_version="mock-isolation-v1",
            detail={"tr_profile": "official-example-v1"},
        ),
    )
    with pytest.raises(ValueError, match="SOAK_START_RESUME_BLOCKED:IDENTITY_DRIFT"):
        cli._orchestrate_soak_start(identity_drift_runtime, campaign_policy=policy)
    assert reconciliations == 1

    status = cli._orchestrate_soak_start(runtime, campaign_policy=policy)
    assert getattr(status["state"], "value", status["state"]) == "ACTIVE"
    assert reconciliations == 2
    assert bootstraps == 1
    assert soak.execute("SELECT COUNT(*) FROM soak_campaigns").fetchone()[0] == 1
    assert soak.execute("SELECT COUNT(*) FROM soak_identity_receipts").fetchone()[0] == 1
    assert soak.execute("SELECT COUNT(*) FROM soak_snapshots").fetchone()[0] == 2

    with pytest.raises(ValueError, match="SOAK_START_RESUME_BLOCKED"):
        cli._orchestrate_soak_start(runtime, campaign_policy=policy)
    assert reconciliations == 2


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
        "campaign:admit",
        "reconcile:PRE_RUN",
        "production:decision-risk-sizing",
        "production:post",
        "reconcile:POST_SUBMISSION",
        "reconcile:PRE_FINALIZE",
        "campaign:finalize",
    ]


def test_post_reconciliation_failure_is_raised_after_execution_returns() -> None:
    import trading_bot.cli as cli

    calls: list[str] = []
    runtime = _runtime(calls)

    def reconcile(stage, run_id):
        calls.append(f"reconcile:{stage.value}")
        return type("Result", (), {"complete": stage is not cli.ReconciliationStage.POST_SUBMISSION})()

    runtime = replace(runtime, reconcile=reconcile)

    with pytest.raises(RuntimeError, match="RECONCILIATION_INCOMPLETE:POST_SUBMISSION"):
        cli._orchestrate_soak_run(
            runtime, run_id="run-1", observed_at="2026-07-20T10:00:00+09:00"
        )

    assert calls == [
        "campaign:admit",
        "reconcile:PRE_RUN",
        "production:decision-risk-sizing",
        "production:post",
        "reconcile:POST_SUBMISSION",
    ]


def test_post_submission_tracker_waits_for_reconciled_accepted_order() -> None:
    import trading_bot.cli as cli
    from trading_bot.audit_models import OrderEvent, OrderEventType

    calls: list[str] = []
    tracker = cli._PostSubmissionTracker(lambda: calls.append("post"))

    accepted = OrderEvent(
        order_intent_id="intent-1",
        origin_run_id="run-1",
        observer_run_id="run-1",
        ticker="005930",
        event_type=OrderEventType.SUBMISSION_ACCEPTED,
    )
    reconciled = OrderEvent(
        order_intent_id="intent-1",
        origin_run_id="run-1",
        observer_run_id="run-1",
        ticker="005930",
        event_type=OrderEventType.RECONCILED,
    )

    tracker.observe(accepted)
    assert calls == []
    assert tracker.submission_count == 1

    tracker.observe(reconciled)
    assert calls == ["post"]
    assert tracker.post_count == 1

    tracker.flush_pending()
    assert calls == ["post"]


def test_post_submission_tracker_flushes_accepted_order_after_fill_readback_error() -> None:
    import trading_bot.cli as cli
    from trading_bot.audit_models import OrderEvent, OrderEventType

    calls: list[str] = []
    tracker = cli._PostSubmissionTracker(lambda: calls.append("post"))
    tracker.observe(
        OrderEvent(
            order_intent_id="intent-1",
            origin_run_id="run-1",
            observer_run_id="run-1",
            ticker="005930",
            event_type=OrderEventType.SUBMISSION_ACCEPTED,
        )
    )

    tracker.flush_pending()

    assert calls == ["post"]
    assert tracker.submission_count == tracker.post_count == 1


def test_post_submission_tracker_reconciles_ambiguous_submission_immediately() -> None:
    import trading_bot.cli as cli
    from trading_bot.audit_models import OrderEvent, OrderEventType

    calls: list[str] = []
    tracker = cli._PostSubmissionTracker(lambda: calls.append("post"))

    tracker.observe(
        OrderEvent(
            order_intent_id="intent-1",
            origin_run_id="run-1",
            observer_run_id="run-1",
            ticker="005930",
            event_type=OrderEventType.SUBMISSION_AMBIGUOUS,
        )
    )

    assert calls == ["post"]
    assert tracker.submission_count == tracker.post_count == 1


def test_post_submission_tracker_never_retries_failed_reconciliation_attempt() -> None:
    import trading_bot.cli as cli
    from trading_bot.audit_models import OrderEvent, OrderEventType

    attempts = 0

    def fail() -> None:
        nonlocal attempts
        attempts += 1
        raise OSError("query failed")

    tracker = cli._PostSubmissionTracker(fail)
    tracker.observe(
        OrderEvent(
            order_intent_id="intent-1",
            origin_run_id="run-1",
            observer_run_id="run-1",
            ticker="005930",
            event_type=OrderEventType.SUBMISSION_ACCEPTED,
        )
    )

    with pytest.raises(OSError, match="query failed"):
        tracker.flush_pending()
    tracker.flush_pending()

    assert attempts == 1
    assert tracker.submission_count == tracker.post_count == 1


def test_non_admitted_day_stops_before_reconciliation_or_production() -> None:
    import trading_bot.cli as cli

    calls: list[str] = []
    runtime = _runtime(calls)

    def block(**kwargs):
        calls.append("campaign:admit")
        return type("Verdict", (), {"code": type("Code", (), {"value": "UNKNOWN_DATE"})()})()

    runtime.campaign.admit_designated_run = block

    with pytest.raises(RuntimeError, match="SOAK_RUN_NOT_ADMITTED:UNKNOWN_DATE"):
        cli._orchestrate_soak_run(
            runtime, run_id="run-1", observed_at="2026-07-29T09:10:00+09:00"
        )

    assert calls == ["campaign:admit"]


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


@pytest.mark.parametrize(
    ("initial_stage", "initial_run_id"),
    (
        (ReconciliationStage.POST_SUBMISSION, "run-accepted"),
        (ReconciliationStage.RESUME, "resume"),
    ),
)
def test_accepted_unresolved_order_is_frozen_and_resume_terminally_releases(
    tmp_path: Path,
    monkeypatch,
    initial_stage: ReconciliationStage,
    initial_run_id: str,
) -> None:
    import trading_bot.cli as cli
    from trading_bot.audit_models import OrderEvent, OrderEventType
    from trading_bot.soak_models import BrokerPageEnvelope, PageCompleteness
    from trading_bot.sqlite_audit import append_order_event, connect, start_run
    from trading_bot.soak_store import (
        append_campaign_event,
        connect_soak_store,
        create_campaign,
    )

    settings = _settings(tmp_path)
    primary = connect(settings.primary_audit_db_path)
    start_run(
        primary,
        run_id="run-accepted",
        trading_mode="mock",
        dry_run=False,
        trading_date_kst=date.today().strftime("%Y%m%d"),
    )
    for event_type, broker_order_id, broker_status in (
        (OrderEventType.INTENT_CREATED, None, None),
        (OrderEventType.SUBMISSION_ATTEMPTED, None, None),
        (OrderEventType.SUBMISSION_ACCEPTED, "ORDER-1", "ACCEPTED"),
    ):
        append_order_event(
            primary,
            OrderEvent(
                order_intent_id="intent-accepted",
                origin_run_id="run-accepted",
                observer_run_id="run-accepted",
                ticker="005930",
                event_type=event_type,
                submission_id="submission-accepted",
                broker_order_id=broker_order_id,
                side="BUY",
                requested_qty=5,
                broker_status=broker_status,
            ),
        )
    primary.close()

    soak = connect_soak_store(settings.soak_db_path)
    create_campaign(
        soak,
        campaign_id="campaign-1",
        accepted_profile_fingerprint="sha256:approved-profile",
        accepted_profile_version="official-example-v1",
        field_contract_version="kis-mock-compat-v1",
        ambiguity_policy_version="ambiguity-v1",
        ambiguity_window_seconds=60,
        ambiguity_poll_cadence_seconds=5,
        ambiguity_max_observations=12,
    )
    append_campaign_event(
        soak,
        campaign_id="campaign-1",
        run_id="run-accepted",
        ticker="005930",
        order_intent_id="intent-accepted",
        event_code="ORDER_INTENT_ATTRIBUTED",
    )
    soak.close()

    class Adapter:
        _token_manager = object()
        _request_limiter = object()

        def __init__(self) -> None:
            self.complete = False
            self.get_calls = 0
            self.post_calls = 0

        def fetch_trading_day(self, _day):
            return True

        def query_daily_ccld_pages(self, **_kwargs):
            self.get_calls += 1
            if not self.complete:
                return BrokerPageEnvelope(
                    completeness=PageCompleteness.INCOMPLETE,
                    reason_code="QUERY_UNAVAILABLE",
                    page_count=0,
                )
            return BrokerPageEnvelope(
                rows=(
                    {
                        "odno": "ORDER-1",
                        "pdno": "005930",
                        "sll_buy_dvsn_cd": "02",
                        "ord_qty": "5",
                        "tot_ccld_qty": "5",
                        "rmn_qty": "0",
                        "avg_prvs": "70000",
                        "ord_stat_name": "FILLED",
                    },
                ),
                completeness=PageCompleteness.COMPLETE,
                reason_code="COMPLETE",
                page_count=1,
            )

        def query_balance_pages(self, **_kwargs):
            self.get_calls += 1
            return BrokerPageEnvelope(
                rows=(
                    {
                        "pdno": "005930",
                        "hldg_qty": "5",
                        "ord_psbl_qty": "5",
                        "pchs_avg_pric": "70000",
                    },
                ),
                summary={"dnca_tot_amt": "650000", "tot_evlu_amt": "1000000"},
                completeness=PageCompleteness.COMPLETE,
                reason_code="COMPLETE",
                page_count=1,
            )

        def place_order_cash(self, *_args, **_kwargs):
            self.post_calls += 1
            raise AssertionError("resume must never submit an order")

    adapter = Adapter()

    class Policy:
        def __init__(self, _calendar):
            pass

        def completed_bar_cutoff(self, _day):
            return type(
                "Cutoff", (), {"available": True, "cutoff_date": date(2026, 8, 8)}
            )()

    class Quote:
        def fetch_current_price(self, _ticker):
            raise AssertionError("resume must not read a quote")

    monkeypatch.setattr(
        cli, "_read_audit_health", lambda *_args: type("Health", (), {"healthy": True})()
    )
    monkeypatch.setattr(cli, "_build_soak_adapter", lambda _settings: adapter)
    monkeypatch.setattr(cli, "ObservedKRXCalendar", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(cli, "MarketCyclePolicy", Policy)
    monkeypatch.setattr(cli, "PykrxOhlcvAdapter", lambda **_kwargs: object())
    monkeypatch.setattr(cli, "KisQuoteAdapter", lambda **_kwargs: Quote())
    monkeypatch.setattr(cli, "build_data_source", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(cli, "build_llm_provider", lambda _settings: object())
    monkeypatch.setattr(cli, "KISBroker", lambda **_kwargs: object())

    runtime = cli._build_soak_runtime(settings, "campaign-1")
    try:
        first = runtime.reconcile(initial_stage, initial_run_id)
        assert first.complete is False
        frozen = runtime.campaign.load_status("campaign-1")["active_freezes"]
        assert [(row["ticker"], row["order_intent_id"], row["freeze_kind"]) for row in frozen] == [
            ("005930", "intent-accepted", "REMAINING_ORDER")
        ]

        adapter.complete = True
        second = runtime.reconcile(ReconciliationStage.RESUME, "resume")
        assert second.complete is True
        assert runtime.campaign.load_status("campaign-1")["active_freezes"] == []

        released = runtime.campaign.store.execute(
            """SELECT release_evidence_type,release_evidence_id
               FROM soak_ticker_freezes WHERE state='RELEASED'"""
        ).fetchone()
        assert released is not None
        assert released[0] == "COMPARISON"
        comparison = runtime.campaign.store.execute(
            """SELECT campaign_id,ticker,order_intent_id,verdict,remaining_order_terminal
               FROM soak_comparisons WHERE comparison_id=?""",
            (released[1],),
        ).fetchone()
        assert tuple(comparison) == (
            "campaign-1",
            "005930",
            "intent-accepted",
            "MATCHED",
            1,
        )

        adapter.complete = False
        runtime.reconcile(ReconciliationStage.RESUME, "resume")
        assert runtime.campaign.load_status("campaign-1")["active_freezes"] == []
        assert runtime.campaign.store.execute(
            "SELECT COUNT(*) FROM soak_comparisons WHERE order_intent_id='intent-accepted'"
        ).fetchone()[0] == 2
        assert adapter.post_calls == 0
    finally:
        runtime.close()


def test_resume_selects_only_attributed_campaign_intents_and_origin_date_window(
    tmp_path: Path, monkeypatch
) -> None:
    import trading_bot.cli as cli
    from trading_bot.audit_models import OrderEvent, OrderEventType
    from trading_bot.soak_models import BrokerPageEnvelope, PageCompleteness
    from trading_bot.sqlite_audit import append_order_event, connect, start_run
    from trading_bot.soak_store import (
        append_campaign_event,
        connect_soak_store,
        create_campaign,
    )

    settings = _settings(tmp_path)
    primary = connect(settings.primary_audit_db_path)
    for campaign_id, run_id, intent_id, ticker, trading_date in (
        ("campaign-a", "run-a", "intent-a", "017900", "20260808"),
        ("campaign-b", "run-b", "intent-b", "009830", "20260809"),
    ):
        start_run(
            primary,
            run_id=run_id,
            trading_mode="mock",
            dry_run=False,
            trading_date_kst=trading_date,
        )
        for event_type, broker_order_id, broker_status in (
            (OrderEventType.INTENT_CREATED, None, None),
            (OrderEventType.SUBMISSION_ATTEMPTED, None, None),
            (OrderEventType.SUBMISSION_ACCEPTED, f"ORDER-{run_id[-1].upper()}", "ACCEPTED"),
        ):
            append_order_event(
                primary,
                OrderEvent(
                    order_intent_id=intent_id,
                    origin_run_id=run_id,
                    observer_run_id=run_id,
                    ticker=ticker,
                    event_type=event_type,
                    submission_id=f"submission-{run_id}",
                    broker_order_id=broker_order_id,
                    side="BUY",
                    requested_qty=1,
                    broker_status=broker_status,
                ),
            )
    primary.close()

    soak = connect_soak_store(settings.soak_db_path)
    for campaign_id, run_id, intent_id, ticker in (
        ("campaign-a", "run-a", "intent-a", "017900"),
        ("campaign-b", "run-b", "intent-b", "009830"),
    ):
        create_campaign(
            soak,
            campaign_id=campaign_id,
            accepted_profile_fingerprint="sha256:approved-profile",
            accepted_profile_version="official-example-v1",
            field_contract_version="kis-mock-compat-v1",
            ambiguity_policy_version="ambiguity-v1",
            ambiguity_window_seconds=60,
            ambiguity_poll_cadence_seconds=5,
            ambiguity_max_observations=12,
        )
        append_campaign_event(
            soak,
            campaign_id=campaign_id,
            run_id=run_id,
            ticker=ticker,
            order_intent_id=intent_id,
            event_code="ORDER_INTENT_ATTRIBUTED",
        )
    soak.close()

    class Adapter:
        _token_manager = object()
        _request_limiter = object()

        def __init__(self) -> None:
            self.windows: list[tuple[date, date]] = []

        def fetch_trading_day(self, _day):
            return True

        def query_daily_ccld_pages(self, **kwargs):
            self.windows.append((kwargs["start_date"], kwargs["end_date"]))
            return BrokerPageEnvelope(
                rows=(
                    {
                        "odno": "ORDER-B",
                        "pdno": "009830",
                        "sll_buy_dvsn_cd": "02",
                        "ord_qty": "1",
                        "tot_ccld_qty": "1",
                        "rmn_qty": "0",
                        "avg_prvs": "70000",
                        "ord_stat_name": "FILLED",
                        "ord_dt": "20260809",
                    },
                ),
                completeness=PageCompleteness.COMPLETE,
                reason_code="COMPLETE",
                page_count=1,
            )

        def query_balance_pages(self, **_kwargs):
            return BrokerPageEnvelope(
                rows=(
                    {
                        "pdno": "009830",
                        "hldg_qty": "1",
                        "ord_psbl_qty": "1",
                        "pchs_avg_pric": "70000",
                    },
                ),
                summary={"dnca_tot_amt": "650000", "tot_evlu_amt": "1000000"},
                completeness=PageCompleteness.COMPLETE,
                reason_code="COMPLETE",
                page_count=1,
            )

    adapter = Adapter()

    class Policy:
        def __init__(self, _calendar):
            pass

        def completed_bar_cutoff(self, _day):
            return type(
                "Cutoff", (), {"available": True, "cutoff_date": date(2026, 8, 8)}
            )()

    class Quote:
        def fetch_current_price(self, _ticker):
            raise AssertionError("resume must not read a quote")

    monkeypatch.setattr(
        cli, "_read_audit_health", lambda *_args: type("Health", (), {"healthy": True})()
    )
    monkeypatch.setattr(cli, "_build_soak_adapter", lambda _settings: adapter)
    monkeypatch.setattr(cli, "ObservedKRXCalendar", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(cli, "MarketCyclePolicy", Policy)
    monkeypatch.setattr(cli, "PykrxOhlcvAdapter", lambda **_kwargs: object())
    monkeypatch.setattr(cli, "KisQuoteAdapter", lambda **_kwargs: Quote())
    monkeypatch.setattr(cli, "build_data_source", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(cli, "build_llm_provider", lambda _settings: object())
    monkeypatch.setattr(cli, "KISBroker", lambda **_kwargs: object())

    runtime = cli._build_soak_runtime(settings, "campaign-b")
    try:
        result = runtime.reconcile(ReconciliationStage.RESUME, "resume")
        assert result.complete is True
        assert adapter.windows == [(date(2026, 8, 9), date.today())]
        compared = runtime.campaign.store.execute(
            """SELECT campaign_id,order_intent_id,verdict
               FROM soak_comparisons WHERE campaign_id='campaign-b' ORDER BY id"""
        ).fetchall()
        assert [tuple(row) for row in compared] == [
            ("campaign-b", "intent-b", "MATCHED")
        ]
        assert runtime.campaign.load_status("campaign-b")["state"].value == "ACTIVE"

        def fake_cycle(**kwargs):
            kwargs["order_event_hook"](
                OrderEvent(
                    order_intent_id="intent-new",
                    origin_run_id="run-new",
                    observer_run_id="run-new",
                    ticker="005930",
                    event_type=OrderEventType.INTENT_CREATED,
                )
            )
            return {}

        monkeypatch.setattr(cli, "run_cycle", fake_cycle)
        assert runtime.execute_designated("run-new", lambda: None)["submissions"] == 0
        attribution = runtime.campaign.store.execute(
            """SELECT campaign_id,run_id,ticker,order_intent_id,event_code
               FROM soak_events WHERE order_intent_id='intent-new'"""
        ).fetchone()
        assert tuple(attribution) == (
            "campaign-b",
            "run-new",
            "005930",
            "intent-new",
            "ORDER_INTENT_ATTRIBUTED",
        )
    finally:
        runtime.close()


def test_resume_window_fails_closed_when_origin_trading_date_is_missing() -> None:
    import trading_bot.cli as cli
    from trading_bot.audit_models import OrderEvent, OrderEventType
    from trading_bot.sqlite_audit import append_order_event, connect, start_run

    primary = connect(":memory:")
    start_run(primary, run_id="run-undated", trading_mode="mock", dry_run=False)
    append_order_event(
        primary,
        OrderEvent(
            order_intent_id="intent-undated",
            origin_run_id="run-undated",
            observer_run_id="run-undated",
            ticker="005930",
            event_type=OrderEventType.INTENT_CREATED,
        ),
    )

    assert cli._resume_snapshot_window(
        primary,
        intent_ids=("intent-undated",),
        today=date(2026, 8, 11),
    ) is None


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


def test_no_order_pre_run_snapshot_uses_campaign_scoped_preflight_identity() -> None:
    import trading_bot.cli as cli

    assert cli._snapshot_run_id(
        cli.ReconciliationStage.PRE_RUN, "future-run", (), ()
    ) == "preflight"
    assert cli._snapshot_run_id(
        cli.ReconciliationStage.PRE_RUN, "future-run", ("intent-1",), ()
    ) == "future-run"
    assert cli._snapshot_run_id(
        cli.ReconciliationStage.PRE_FINALIZE, "future-run", (), ()
    ) == "future-run"


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


def test_soak_preflight_cli_uses_mock_specific_preflight_without_runtime(
    tmp_path: Path, monkeypatch
) -> None:
    import trading_bot.cli as cli
    from trading_bot.preflight import (
        PreflightCheck,
        PreflightCode,
        PreflightResult,
        PreflightState,
    )

    settings = _settings(tmp_path)
    result = PreflightResult(
        checks=(
            PreflightCheck(
                code=PreflightCode.KRX_SESSION_OPEN,
                state=PreflightState.PASS,
                explanation_ko="KRX 연속매매 시간이 확인되었습니다.",
                facts={"source": "kis_mock_calendar"},
                stops_run=False,
            ),
        ),
        global_executable=True,
        frozen_tickers={},
    )
    calls: list[object] = []

    monkeypatch.setattr(cli, "_soak_settings_factory", lambda: settings)
    monkeypatch.setattr(
        cli,
        "_soak_preflight_factory",
        lambda actual, campaign_id: calls.append((actual, campaign_id)) or result,
    )
    monkeypatch.setattr(
        cli,
        "_soak_runtime_factory",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("runtime called")),
    )

    invoked = CliRunner().invoke(
        cli.app, ["soak", "preflight", "--campaign-id", "campaign-1"]
    )

    assert invoked.exit_code == 0, invoked.output
    assert "KRX_SESSION_OPEN" in invoked.stdout
    assert "실행 가능: 예" in invoked.stdout
    assert calls == [(settings, "campaign-1")]


def test_soak_preflight_wires_selected_mock_calendar_witness(
    tmp_path: Path, monkeypatch
) -> None:
    import trading_bot.cli as cli
    from trading_bot.market_cycle import (
        CalendarState,
        MarketCycleEvidence,
        MarketSession,
    )
    from trading_bot.preflight import PreflightResult

    settings = _settings(tmp_path)
    settings.primary_audit_db_path.touch()
    captured: dict[str, object] = {}

    class Adapter:
        def fetch_trading_day(self, day):
            captured["witness_day"] = day
            return True

        def place_order_cash(self, *args, **kwargs):
            raise AssertionError("preflight must never submit an order")

    class Calendar:
        def __init__(self, _ohlcv, *, calendar_witness, **_kwargs):
            captured["calendar_witness"] = calendar_witness

    class Policy:
        def __init__(self, calendar):
            self.calendar = calendar

        def classify(self, observed_at):
            assert captured["calendar_witness"](observed_at.date()) is True
            return MarketCycleEvidence(
                observed_at,
                observed_at.date(),
                CalendarState.TRADING_DAY,
                MarketSession.CONTINUOUS,
                True,
                "continuous trading",
            )

    monkeypatch.setattr(cli, "_build_soak_adapter", lambda _settings: Adapter())
    monkeypatch.setattr(cli, "ObservedKRXCalendar", Calendar)
    monkeypatch.setattr(cli, "MarketCyclePolicy", Policy)
    monkeypatch.setattr(cli, "PykrxOhlcvAdapter", lambda **kwargs: object())
    monkeypatch.setattr(
        cli, "_read_audit_health", lambda path: type("Audit", (), {"healthy": True})()
    )
    monkeypatch.setattr(
        cli, "_read_unresolved_orders", lambda path: type("Scan", (), {"complete": True})()
    )

    def evaluate(mock_reader, audit_reader, market_reader, unresolved_reader):
        assert mock_reader().confirmed is True
        assert audit_reader().healthy is True
        assert market_reader().executable is True
        assert unresolved_reader().complete is True
        return PreflightResult((), True, {})

    monkeypatch.setattr(cli, "evaluate_preflight", evaluate)

    result = cli._build_soak_preflight_result(settings, "campaign-1")

    assert result.global_executable is True
    assert captured["witness_day"] == date.today()
