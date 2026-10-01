"""Credential-free Typer controllers for deterministic evidence reports."""

from __future__ import annotations

import os
import hashlib
import json
import re
import tempfile
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import typer

from .config import ReportSettings
from .calibration import baseline_policy, build_variant_catalog, evaluate_variants
from .calibration_reporting import (
    ReadOnlyCalibrationEvidenceRepository,
    build_calibration_report,
    render_calibration_report,
)
from .replay import load_replay_bundle
from .promotion_readiness import (
    ReadinessEvidence,
    build_readiness_assessment,
    render_readiness_assessment,
)
from .soak_reporting import ReadOnlySoakRepository, build_soak_report
from .reporting import (
    ReadOnlyAuditRepository,
    build_daily_report,
    build_period_report,
    build_replay_report,
    load_replay_results,
    render_daily_report,
    render_period_report,
    render_replay_report,
)

report_app = typer.Typer(no_args_is_help=True, help="저장된 감사·replay 증거 보고서")


def _today_kst() -> date:
    return datetime.now(ZoneInfo("Asia/Seoul")).date()


def parse_kst_date(value: str) -> date:
    """Parse only the exact operator-facing YYYY-MM-DD grammar."""

    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("date must use valid YYYY-MM-DD format") from exc
    if parsed.isoformat() != value:
        raise ValueError("date must use valid YYYY-MM-DD format")
    return parsed


def resolve_report_audit_db_path(
    explicit: Path | None,
    settings_factory: Callable[[], ReportSettings] = ReportSettings,
) -> Path:
    """Resolve report storage without constructing credential-bearing Settings."""

    return Path(explicit) if explicit is not None else settings_factory().audit_db_path


def _normalized_text_bytes(rendered: str) -> bytes:
    normalized = rendered.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.rstrip("\n") + "\n"
    return normalized.encode("utf-8")


def _validated_output_parent(output: Path) -> tuple[Path, Path]:
    raw = Path(output)
    if raw.name in {"", ".", ".."} or ".." in raw.parts:
        raise ValueError("report output path is ambiguous")
    if raw.is_symlink():
        raise ValueError("report output may not be a symbolic link")

    current = Path(raw.anchor) if raw.is_absolute() else Path()
    for part in raw.parts[1:] if raw.is_absolute() else raw.parts:
        current /= part
        if current.is_symlink():
            raise ValueError("report output path may not contain symbolic links")

    parent = raw.parent
    cursor = parent
    missing: list[Path] = []
    while not cursor.exists():
        if cursor.is_symlink():
            raise ValueError("report output parent may not be a symbolic link")
        missing.append(cursor)
        next_cursor = cursor.parent
        if next_cursor == cursor:
            raise ValueError("report output parent is unavailable")
        cursor = next_cursor
    if cursor.is_symlink() or not cursor.is_dir():
        raise ValueError("report output parent must be a regular directory")

    for directory in reversed(missing):
        directory.mkdir()
    resolved_parent = parent.resolve(strict=True)
    if resolved_parent.is_symlink() or not resolved_parent.is_dir():
        raise ValueError("report output parent must be a regular directory")
    target = resolved_parent / raw.name
    return resolved_parent, target


def write_report_text(output: Path, rendered: str) -> None:
    """Atomically persist the same normalized UTF-8 report shown in the terminal."""

    root, target = _validated_output_parent(Path(output))
    if target.is_symlink():
        raise ValueError("report output may not be a symbolic link")
    payload = _normalized_text_bytes(rendered)
    if target.exists():
        if not target.is_file():
            raise ValueError("report output must be a regular file")
        if target.read_bytes() != payload:
            raise ValueError("report output conflict: existing content differs")
        return

    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=root, prefix=".report-", suffix=".tmp", delete=False
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, target)
        temporary_name = None
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def _diagnostic(exc: Exception) -> str:
    message = str(exc).replace("\r", " ").replace("\n", " ")[:200]
    return f"Report failed: {type(exc).__name__}: {message or 'invalid input'}"


def _deliver(rendered: str, output: Path | None) -> None:
    normalized = _normalized_text_bytes(rendered).decode("utf-8")
    if output is not None:
        write_report_text(output, normalized)
    typer.echo(normalized, nl=False)


def _existing_regular_input(value: Path) -> Path:
    raw = Path(value)
    if raw.is_symlink():
        raise ValueError("calibration input may not be a symbolic link")
    try:
        resolved = raw.resolve(strict=True)
    except FileNotFoundError:
        raise FileNotFoundError(f"calibration input does not exist: {raw}") from None
    if not resolved.is_file():
        raise ValueError("calibration input must be a regular file")
    cursor = raw.absolute()
    while cursor != cursor.parent:
        if cursor.is_symlink():
            raise ValueError("calibration input path may not contain symbolic links")
        cursor = cursor.parent
    return resolved


@report_app.command("daily")
def daily_command(
    date_text: str | None = typer.Option(None, "--date"),
    audit_db: Path | None = typer.Option(None, "--audit-db"),
    output: Path | None = typer.Option(None, "--output"),
) -> None:
    """KST 거래일 하루의 실행·티커 증거를 보고합니다."""

    try:
        selected = _today_kst() if date_text is None else parse_kst_date(date_text)
        repository = ReadOnlyAuditRepository(resolve_report_audit_db_path(audit_db))
        rendered = render_daily_report(build_daily_report(repository, selected))
        _deliver(rendered, output)
    except (OSError, ValueError, RuntimeError) as exc:
        typer.echo(_diagnostic(exc), err=True)
        raise typer.Exit(2) from None


@report_app.command("period")
def period_command(
    from_text: str = typer.Option(..., "--from"),
    to_text: str = typer.Option(..., "--to"),
    audit_db: Path | None = typer.Option(None, "--audit-db"),
    output: Path | None = typer.Option(None, "--output"),
) -> None:
    """포함 범위의 KST 거래일 증거를 보고합니다."""

    try:
        start = parse_kst_date(from_text)
        end = parse_kst_date(to_text)
        if start > end:
            raise ValueError("period start must not be after end")
        repository = ReadOnlyAuditRepository(resolve_report_audit_db_path(audit_db))
        rendered = render_period_report(build_period_report(repository, start, end))
        _deliver(rendered, output)
    except (OSError, ValueError, RuntimeError) as exc:
        typer.echo(_diagnostic(exc), err=True)
        raise typer.Exit(2) from None


@report_app.command("replay")
def replay_report_command(
    inputs: list[Path] = typer.Argument(...),
    output: Path | None = typer.Option(None, "--output"),
) -> None:
    """하나 이상의 정규화 replay 결과를 검증·집계합니다."""

    try:
        if not inputs:
            raise ValueError("at least one replay result is required")
        loaded = load_replay_results(inputs)
        rendered = render_replay_report(build_replay_report(loaded))
        _deliver(rendered, output)
    except (OSError, ValueError, RuntimeError) as exc:
        typer.echo(_diagnostic(exc), err=True)
        raise typer.Exit(2) from None


@report_app.command("calibration")
def calibration_command(
    fixtures: list[Path] = typer.Argument(...),
    audit_db: Path = typer.Option(..., "--audit-db"),
    soak_db: Path = typer.Option(..., "--soak-db"),
    campaign_id: str = typer.Option(..., "--campaign-id"),
    output: Path | None = typer.Option(None, "--output"),
) -> None:
    """Replay·mock 증거로 읽기 전용 정책 보정 자문을 생성합니다."""

    try:
        if not fixtures:
            raise ValueError("at least one replay fixture is required")
        if re.fullmatch(r"[^\x00-\x1f]{1,128}", campaign_id) is None:
            raise ValueError("campaign_id must be non-empty and bounded")
        paths = tuple(_existing_regular_input(path) for path in fixtures)
        inodes = {(path.stat().st_dev, path.stat().st_ino) for path in paths}
        if len(inodes) != len(paths):
            raise ValueError("duplicate replay fixture")

        scenarios = tuple(
            scenario
            for path in paths
            for scenario in load_replay_bundle(path)
        )
        if not scenarios:
            raise ValueError("replay fixture bundle is empty")
        scenario_ids = [scenario.scenario_id for scenario in scenarios]
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("duplicate replay scenario identity")
        expected_baseline = baseline_policy().as_mapping()
        if any(
            any(scenario.policy.get(key) != value for key, value in expected_baseline.items())
            for scenario in scenarios
        ):
            raise ValueError("incompatible replay calibration baseline")
        source_identities = tuple(
            f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}" for path in paths
        )
        if len(set(source_identities)) != len(source_identities):
            raise ValueError("duplicate replay fixture content")

        evidence = ReadOnlyCalibrationEvidenceRepository(audit_db, soak_db).load(
            campaign_id
        )
        evaluations = evaluate_variants(scenarios, build_variant_catalog())
        report = build_calibration_report(
            evidence,
            evaluations,
            source_identities=source_identities,
        )
        _deliver(render_calibration_report(report), output)
    except (OSError, KeyError, ValueError, RuntimeError) as exc:
        typer.echo(_diagnostic(exc), err=True)
        raise typer.Exit(2) from None


@report_app.command("readiness")
def readiness_command(
    replay_results: list[Path] = typer.Option(..., "--replay-result"),
    calibration_fixtures: list[Path] = typer.Option(..., "--calibration-fixture"),
    audit_db: Path = typer.Option(..., "--audit-db"),
    soak_db: Path = typer.Option(..., "--soak-db"),
    controller_db: Path = typer.Option(..., "--controller-db"),
    campaign_id: str = typer.Option(..., "--campaign-id"),
    policy_snapshot: Path = typer.Option(..., "--policy-snapshot"),
    rollback_ack: bool = typer.Option(False, "--rollback-ack"),
    kill_ack: bool = typer.Option(False, "--kill-ack"),
    manual_approval: bool = typer.Option(False, "--manual-approval"),
    output: Path | None = typer.Option(None, "--output"),
) -> None:
    """검증 증거에 묶인 읽기 전용 실거래 준비도를 평가합니다."""

    try:
        if not replay_results or not calibration_fixtures:
            raise ValueError("replay and calibration inputs are required")
        normalized_results = load_replay_results(
            [_existing_regular_input(path) for path in replay_results]
        )
        replay_verified = all(
            result.verification_status == "PASSED"
            for result in normalized_results
        )
        fixture_paths = tuple(_existing_regular_input(path) for path in calibration_fixtures)
        scenarios = tuple(
            scenario for path in fixture_paths for scenario in load_replay_bundle(path)
        )
        calibration_evidence = ReadOnlyCalibrationEvidenceRepository(
            audit_db, soak_db
        ).load(campaign_id)
        calibration_report = build_calibration_report(
            calibration_evidence,
            evaluate_variants(scenarios, build_variant_catalog()),
            source_identities=tuple(
                f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
                for path in fixture_paths
            ),
        )
        soak_report = build_soak_report(
            ReadOnlySoakRepository(audit_db, soak_db, controller_db), campaign_id
        )
        policy_path = _existing_regular_input(policy_snapshot)
        raw_policy = json.loads(policy_path.read_text(encoding="utf-8"))
        expected_policy = baseline_policy().as_mapping()
        if not isinstance(raw_policy, dict) or set(raw_policy) != set(expected_policy):
            raise ValueError("policy snapshot fields mismatch")
        policy_items = tuple(sorted((key, float(value)) for key, value in raw_policy.items()))
        policy_frozen = dict(policy_items) == expected_policy
        campaign = soak_report.campaign
        evidence = ReadinessEvidence(
            replay_verified=replay_verified,
            credited_days=campaign.credited_days,
            target_days=campaign.target_days,
            safety_failure_code=campaign.safety_failure_code,
            reconciliation_incomplete=soak_report.reconciliation.incomplete,
            reconciliation_unknown=soak_report.reconciliation.unknown,
            active_freezes=soak_report.freezes.active_count,
            cross_store_unknown=soak_report.cross_store_unknown,
            reports_complete=(
                not calibration_evidence.excluded_cycle_ids
                and not calibration_evidence.unknown_cycle_ids
            ),
            unresolved_orders=soak_report.freezes.active_count,
            calibration_valid=True,
            calibration_id=calibration_report.calibration_id,
            policy_frozen=policy_frozen,
            resolved_historical_ambiguity=soak_report.resolved_historical_ambiguity,
            source_identities=tuple(
                sorted(
                    [result.stable_result_id for result in normalized_results]
                    + [calibration_report.calibration_id, campaign_id]
                )
            ),
        )
        assessment = build_readiness_assessment(
            evidence,
            policy_snapshot=policy_items,
            rollback_ack=rollback_ack,
            kill_ack=kill_ack,
            manual_approval=manual_approval,
        )
        _deliver(render_readiness_assessment(assessment), output)
    except (OSError, KeyError, ValueError, RuntimeError) as exc:
        typer.echo(_diagnostic(exc), err=True)
        raise typer.Exit(2) from None


@report_app.command("backtest")
def backtest_report_command(
    result: Path = typer.Argument(..., help="검증할 저장 백테스트 JSON"),
    output: Path | None = typer.Option(None, "--output", help="한국어 보고서 파일"),
) -> None:
    from .backtest_models import BacktestInputError
    from .backtest_reporting import load_backtest_result, render_backtest_report
    try:
        _deliver(render_backtest_report(load_backtest_result(result)), output)
    except (BacktestInputError, ValueError, OSError) as exc:
        code = str(exc) if isinstance(exc, BacktestInputError) else "INVALID_REPORT_INPUT"
        typer.echo(f"백테스트 보고 실패: {code[:100]}", err=True)
        raise typer.Exit(2) from None
