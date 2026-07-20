"""Operator Typer CLI for manual trading-bot runs."""

from __future__ import annotations

import dotenv
dotenv.load_dotenv()

import os
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Callable, Optional, Sequence
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import typer

from trading_bot.config import LLMProviderName, Settings, TradingMode, startup_banner
from trading_bot.data_source import ObservedKRXCalendar, build_data_source
from trading_bot.domain import Money, Ticker
from trading_bot.execution import ExecutionConfig, ExecutionResult
from trading_bot.kis_auth import KisTokenManager, build_kis_auth_config
from trading_bot.kis_broker import AmbiguousSubmissionError, KISBroker, build_kis_broker
from trading_bot.kis_order import KisOrderAccount
from trading_bot.kis_order import KisOrderAdapter, MOCK_TR_PROFILE_CANDIDATES
from trading_bot.kis_auth import KisAuthConfig
from trading_bot.kis_quote import KisQuoteAdapter
from trading_bot.market_cycle import MarketCycleEvidence, MarketCyclePolicy
from trading_bot.pykrx_adapter import PykrxOhlcvAdapter
from trading_bot.llm_provider import build_llm_provider, run_llm_cycle as _run_llm_cycle
from trading_bot.mock_broker import MockBroker
from trading_bot.notifier import NoopNotifier, build_notifier, format_run_summary
from trading_bot.preflight import (
    AuditHealthEvidence,
    MockTargetEvidence,
    PreflightResult,
    UnresolvedOrderEvidence,
    UnresolvedOrderScan,
    evaluate_preflight,
    render_preflight,
)
from trading_bot.report_cli import report_app
from trading_bot.soak_compat import export_compatibility_fixture, probe_mock_profile
from trading_bot.soak_config import (
    SoakSettings,
    build_soak_identity_receipt,
    render_mock_identity_receipt,
    validate_store_topology,
)
from trading_bot.soak_proof import (
    ProofOrderRequest,
    ProofOrderService,
    build_proof_fixture,
    export_proof_fixture,
)
from trading_bot.soak_reconcile import (
    AmbiguityPolicy,
    SnapshotCampaign,
    SnapshotWindow,
    collect_broker_snapshot,
    compare_broker_truth,
    load_local_order_evidence,
    rebuild_ticker_freezes,
)
from trading_bot.soak_models import (
    FaultName,
    PageCompleteness,
    ReconciliationStage,
    ReconciliationVerdict,
)
from trading_bot.soak_store import (
    append_comparison,
    append_identity_receipt,
    append_snapshot,
    connect_soak_store,
    fingerprint_accepted_profile,
    load_campaign_state,
)
from trading_bot.soak_campaign import SoakCampaignService
from trading_bot.soak_drills import DrillService, parse_fault_name
from trading_bot.reporting import ReadOnlyAuditRepository, build_daily_report
from trading_bot.risk import DailyLossState, RiskConfig
from trading_bot import sqlite_audit
from trading_bot.audit_models import (
    FailedStage,
    NotificationAttempt,
    NotificationDeliveryStatus,
    NotificationKind,
    OrderEventType,
    ReasonCode,
    RunKind,
    RunStatus,
    TickerOutcome,
    TickerOutcomeCode,
    sanitize_detail,
)

app = typer.Typer(no_args_is_help=True, help="Manual stock-trading bot operator CLI.")
app.add_typer(report_app, name="report")
soak_app = typer.Typer(no_args_is_help=True, help="KIS mock-only soak compatibility workflow.")
app.add_typer(soak_app, name="soak")

_soak_settings_factory = SoakSettings
_soak_probe = probe_mock_profile
_proof_service_factory = ProofOrderService
_drill_service_factory = DrillService

RunCycleFn = Callable[..., ExecutionResult]


@dataclass(frozen=True)
class _Runtime:
    settings: Settings
    token_manager: Optional[KisTokenManager]
    data_source: Any
    llm_provider: Any
    broker: Any
    audit_conn: sqlite3.Connection
    notifier: Any
    cycle_evidence: Optional[MarketCycleEvidence] = None
    completed_bar_cutoff: Optional[str] = None


@dataclass(frozen=True)
class _SoakRuntime:
    """Narrow campaign composition root with no real-account capability."""

    campaign_id: str
    settings: SoakSettings
    receipt: Any
    campaign: Any
    persist_receipt: Callable[[], Any]
    reconcile: Callable[[ReconciliationStage, str], Any]
    execute_designated: Callable[[str, Callable[[], None]], dict[str, Any]]
    rebuild_freezes: Callable[[], Any]
    close: Callable[[], None]


def _reconciliation_complete(result: Any) -> bool:
    return bool(getattr(result, "complete", result is True))


def _require_soak_reconciliation(
    runtime: _SoakRuntime, stage: ReconciliationStage, run_id: str
) -> Any:
    result = runtime.reconcile(stage, run_id)
    if not _reconciliation_complete(result):
        raise RuntimeError(f"RECONCILIATION_INCOMPLETE:{stage.value}")
    return result


def _orchestrate_soak_start(
    runtime: _SoakRuntime, *, campaign_policy: dict[str, Any]
) -> dict[str, Any]:
    """Persist policy and identity before the mandatory STARTUP broker gate."""

    runtime.campaign.start_campaign(campaign_id=runtime.campaign_id, **campaign_policy)
    runtime.persist_receipt()
    _require_soak_reconciliation(runtime, ReconciliationStage.STARTUP, "startup")
    return runtime.campaign.load_status(runtime.campaign_id)


def _orchestrate_soak_run(
    runtime: _SoakRuntime, *, run_id: str, observed_at: str | datetime
) -> dict[str, Any]:
    """Surround the production decision path and every POST with broker truth."""

    observed = (
        datetime.fromisoformat(observed_at) if isinstance(observed_at, str) else observed_at
    )
    _require_soak_reconciliation(runtime, ReconciliationStage.PRE_RUN, run_id)
    post_count = 0

    def post_submission() -> None:
        nonlocal post_count
        _require_soak_reconciliation(
            runtime, ReconciliationStage.POST_SUBMISSION, run_id
        )
        post_count += 1

    result = runtime.execute_designated(run_id, post_submission)
    declared = int(result.get("submissions", post_count))
    if declared != post_count:
        raise RuntimeError("POST_SUBMISSION_RECONCILIATION_CARDINALITY_MISMATCH")
    _require_soak_reconciliation(runtime, ReconciliationStage.PRE_FINALIZE, run_id)
    verdict = runtime.campaign.finalize_designated_day(
        campaign_id=runtime.campaign_id,
        run_id=run_id,
        observed_at=observed,
        pre_finalize_complete=True,
    )
    return {**result, "verdict": verdict.code.value}


def _orchestrate_soak_resume(runtime: _SoakRuntime) -> dict[str, Any]:
    """Recover broker truth and freezes without exposing any submission callback."""

    _require_soak_reconciliation(runtime, ReconciliationStage.RESUME, "resume")
    runtime.rebuild_freezes()
    return runtime.campaign.load_status(runtime.campaign_id)


def _orchestrate_soak_status(runtime: _SoakRuntime) -> dict[str, Any]:
    """Read campaign state without reconciliation, adapter, or mutation calls."""

    return runtime.campaign.load_status(runtime.campaign_id)


class _MockOnlyExecutionSettings:
    """Production policy view that deliberately has no ``kis_real`` field."""

    trading_mode = TradingMode.MOCK
    confirm_real_trading = False
    dry_run = False
    buy_confidence_threshold = 0.8
    sell_confidence_threshold = 0.8
    buy_cash_fraction = 0.1
    max_position_value = 1_000_000.0
    stop_loss_pct = 0.05
    take_profit_pct = 0.10
    daily_loss_threshold = 500_000.0
    ohlcv_adjusted = True
    screener_max_candidates = 20
    screener_markets = ("KOSPI", "KOSDAQ")
    screener_min_trading_value = 1_000_000_000.0
    screener_min_volume_ratio = 1.0
    screener_excluded_states = ("HALTED", "DELISTING", "ADMIN")
    pykrx_request_timeout_seconds = 10.0
    naver_news_enabled = False
    naver_news_max_items = 5
    naver_news_max_chars = 2_000
    discord_webhook_url = None
    order_timeout_seconds = 5.0
    llm_provider = LLMProviderName.CODEX_CLI
    anthropic_api_key = None
    anthropic_auth_token = None
    openai_api_key = None
    anthropic_model = "claude-opus-4-8"
    anthropic_temperature = 0.0
    openai_model = "gpt-4.1"
    openai_temperature = 0.0
    codex_cli_binary = "codex"
    codex_cli_model = None
    codex_cli_temperature = 0.0
    codex_cli_timeout_seconds = 120.0
    codex_cli_extra_args: tuple[str, ...] = ()
    llm_max_retries = 3
    llm_retry_backoff_seconds = 1.0

    def __init__(self, settings: SoakSettings) -> None:
        self.kis_mock = settings.kis_mock
        self.audit_db_path = str(settings.primary_audit_db_path)
        self.kis_token_refresh_margin_seconds = settings.kis_token_refresh_margin_seconds
        self.kis_min_interval_seconds = settings.kis_min_interval_seconds
        self.kis_max_retries = settings.kis_max_retries
        self.kis_retry_backoff_seconds = settings.kis_retry_backoff_seconds
        self.order_timeout_seconds = settings.kis_timeout_seconds

    @property
    def active_kis(self) -> Any:
        return self.kis_mock


def _persist_snapshot_evidence(store: sqlite3.Connection, snapshot: Any) -> None:
    append_snapshot(
        store,
        snapshot_id=snapshot.snapshot_id,
        campaign_id=snapshot.campaign_id,
        run_id=snapshot.run_id,
        stage=snapshot.stage,
        completeness=snapshot.completeness,
        orders=tuple(
            {
                "observation_id": item.observation_id,
                "order_id": item.order_id,
                "status": item.status,
                "remaining_qty": item.remaining_qty,
                "ticker": item.ticker,
                "side": item.side,
                "ordered_qty": item.ordered_qty,
                "filled_qty": item.filled_qty,
                "snapped_price": item.snapped_price,
            }
            for item in snapshot.orders
        ),
        fills=tuple(
            {
                "observation_id": item.observation_id,
                "order_id": item.order_id,
                "fill_id": item.fill_id,
                "quantity": item.quantity,
                "price": item.price,
                "ticker": item.ticker,
            }
            for item in snapshot.fills
        ),
        holdings=tuple(
            {
                "observation_id": item.observation_id,
                "ticker": item.ticker,
                "quantity": item.quantity,
                "average_price": item.average_price,
                "available_quantity": item.available_quantity,
            }
            for item in snapshot.holdings
        ),
        accounts=(
            {
                "observation_id": snapshot.account.observation_id,
                "available_cash": snapshot.account.available_cash,
                "total_value": snapshot.account.total_value,
                "account_suffix": snapshot.account.account_suffix,
            },
        ),
        detail={
            "reason_code": snapshot.reason_code,
            "daily_page_count": snapshot.daily_page_count,
            "balance_page_count": snapshot.balance_page_count,
        },
        observed_at=snapshot.observed_at,
    )


def _build_soak_runtime(settings: SoakSettings, campaign_id: str) -> _SoakRuntime:
    """Build the genuine mock adapters and isolated primary/soak store owners."""

    validate_store_topology(
        settings.primary_audit_db_path,
        settings.soak_db_path,
        settings.controller_db_path,
    )
    if not settings.primary_audit_db_path.is_file():
        raise ValueError("AUDIT_HEALTH_UNKNOWN")
    audit_health = _read_audit_health(str(settings.primary_audit_db_path))
    if not audit_health.healthy:
        raise ValueError("AUDIT_HEALTH_UNKNOWN")
    selected = tuple(
        profile
        for profile in MOCK_TR_PROFILE_CANDIDATES
        if profile.version == settings.kis_mock.tr_id_profile
    )
    if len(selected) != 1:
        raise ValueError("MOCK_ISOLATION_BLOCKED: selected profile is not unique")
    profile = selected[0]
    receipt = build_soak_identity_receipt(settings, campaign_id, profile)
    adapter = _build_soak_adapter(settings)
    account = KisOrderAccount(
        cano=settings.kis_mock_account_cano.get_secret_value(),
        account_product_code=settings.kis_mock_account_product_code,
    )
    primary = sqlite_audit.connect(settings.primary_audit_db_path)
    soak = connect_soak_store(settings.soak_db_path)
    policy = MarketCyclePolicy(
        ObservedKRXCalendar(
            PykrxOhlcvAdapter(adjusted=True, request_timeout_seconds=10.0)
        )
    )
    campaign = SoakCampaignService(
        market_policy=policy,
        store=soak,
        daily_report_builder=lambda day: build_daily_report(
            ReadOnlyAuditRepository(settings.primary_audit_db_path), day
        ),
    )

    def persist_receipt() -> int:
        return append_identity_receipt(
            soak,
            receipt_id=f"{campaign_id}:identity",
            campaign_id=campaign_id,
            target=receipt.target,
            domain_class=receipt.domain_class,
            account_suffix=receipt.account_suffix,
            profile_version=receipt.profile_version,
            policy_version=receipt.policy_version,
            detail={"tr_profile": receipt.profile_version},
        )

    def reconcile(stage: ReconciliationStage, run_id: str) -> Any:
        today = datetime.now(ZoneInfo("Asia/Seoul")).date()
        rows = primary.execute(
            "SELECT DISTINCT order_intent_id,ticker FROM order_events WHERE origin_run_id=?",
            (run_id,),
        ).fetchall()
        intent_ids = tuple(str(row[0]) for row in rows if row[0])
        tickers = tuple(str(row[1]) for row in rows if row[1])
        snapshot = collect_broker_snapshot(
            adapter,
            SnapshotCampaign(campaign_id, run_id, account, receipt.account_suffix, profile),
            stage,
            SnapshotWindow(today, today),
            {"order_ids": (), "tickers": tickers},
        )
        _persist_snapshot_evidence(soak, snapshot)
        complete = snapshot.completeness is PageCompleteness.COMPLETE
        for intent_id in intent_ids:
            local = load_local_order_evidence(primary, order_intent_id=intent_id)
            comparison = compare_broker_truth(local, snapshot)
            append_comparison(
                soak,
                comparison_id=comparison.comparison_id,
                campaign_id=comparison.campaign_id,
                snapshot_id=comparison.snapshot_id,
                run_id=comparison.run_id,
                ticker=comparison.ticker,
                order_intent_id=comparison.order_intent_id,
                verdict=comparison.verdict,
                remaining_order_terminal=comparison.remaining_order_terminal,
                detail={
                    "dimension_codes": "|".join(item.code for item in comparison.dimensions)
                },
            )
            complete = complete and comparison.complete and (
                comparison.verdict is not ReconciliationVerdict.UNKNOWN
            )
            if comparison.verdict is ReconciliationVerdict.MISMATCHED:
                campaign.record_safety_breach(
                    campaign_id=campaign_id,
                    code="BROKER_TRUTH_DISAGREEMENT",
                    run_id=run_id,
                    ticker=comparison.ticker,
                    order_intent_id=comparison.order_intent_id,
                )
        return SimpleNamespace(complete=complete)

    mock_settings = _MockOnlyExecutionSettings(settings)
    quote = KisQuoteAdapter(
        token_manager=adapter._token_manager,
        domain=settings.kis_mock.domain,
        tr_id="FHKST01010100",
        min_interval_seconds=settings.kis_min_interval_seconds,
        max_retries=settings.kis_max_retries,
        retry_backoff_seconds=settings.kis_retry_backoff_seconds,
        timeout_seconds=settings.kis_timeout_seconds,
    )
    ohlcv = PykrxOhlcvAdapter(adjusted=True, request_timeout_seconds=10.0)
    cutoff = policy.completed_bar_cutoff(datetime.now(ZoneInfo("Asia/Seoul")).date())
    if not cutoff.available or cutoff.cutoff_date is None:
        primary.close()
        soak.close()
        raise ValueError("KRX_CALENDAR_UNKNOWN")
    cutoff_text = cutoff.cutoff_date.strftime("%Y%m%d")
    data_source = build_data_source(
        mock_settings,
        expected_date=cutoff_text,
        accepted_latest_date=cutoff_text,
        ohlcv_adapter=ohlcv,
        quote_adapter=quote,
    )
    llm = build_llm_provider(mock_settings)
    broker = KISBroker(
        order_adapter=adapter,
        account=account,
        pre_submit_quote_reader=quote.fetch_current_price,
    )

    def execute_designated(
        run_id: str, post_submission: Callable[[], None]
    ) -> dict[str, Any]:
        submission_count = 0

        def order_event_hook(event: Any) -> None:
            nonlocal submission_count
            if event.event_type in {
                OrderEventType.SUBMISSION_ACCEPTED,
                OrderEventType.SUBMISSION_AMBIGUOUS,
            }:
                submission_count += 1
                post_submission()

        frozen_rows = soak.execute(
            """SELECT f.ticker FROM soak_ticker_freezes f
               WHERE f.state='FROZEN' AND NOT EXISTS (
                 SELECT 1 FROM soak_ticker_freezes r
                 WHERE r.freeze_id=f.freeze_id AND r.state='RELEASED')"""
        ).fetchall()
        preflight = PreflightResult(
            (), True, {str(row[0]): ReasonCode.AMBIGUOUS_SUBMISSION for row in frozen_rows}
        )
        result = run_cycle(
            execute=True,
            settings=mock_settings,
            data_source=data_source,
            llm_provider=llm,
            broker=broker,
            audit_conn=primary,
            notifier=NoopNotifier(),
            run_cycle=_run_llm_cycle,
            trading_date=_today_kst(),
            run_id=run_id,
            preflight_result=preflight,
            order_event_hook=order_event_hook,
        )
        result["submissions"] = submission_count
        return result

    return _SoakRuntime(
        campaign_id=campaign_id,
        settings=settings,
        receipt=receipt,
        campaign=campaign,
        persist_receipt=persist_receipt,
        reconcile=reconcile,
        execute_designated=execute_designated,
        rebuild_freezes=lambda: rebuild_ticker_freezes(soak, campaign_id),
        close=lambda: (primary.close(), soak.close()),
    )


_soak_runtime_factory = _build_soak_runtime


def _today_kst() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d")


def _ensure_audit_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(sqlite_audit.SCHEMA)
    conn.commit()


def _candidate_tickers(result: Any) -> list[str]:
    if hasattr(result, "candidates"):
        return [candidate.ticker for candidate in result.candidates]
    if hasattr(result, "selected"):
        return [str(ticker) for ticker in result.selected]
    if isinstance(result, Sequence) and not isinstance(result, (str, bytes)):
        return [str(ticker) for ticker in result]
    raise TypeError("screener result did not expose candidates")


def _validate_ticker(ticker: str) -> str:
    if len(ticker) != 6 or not ticker.isdigit():
        raise typer.BadParameter("ticker must be a 6-digit KRX code")
    return ticker


def _screen_progress(message: str) -> None:
    typer.echo(f"[screen] {message}", err=True)


def _execution_config(settings: Settings) -> ExecutionConfig:
    return ExecutionConfig(
        buy_confidence_threshold=settings.buy_confidence_threshold,
        sell_confidence_threshold=settings.sell_confidence_threshold,
        buy_cash_fraction=settings.buy_cash_fraction,
        max_position_value=settings.max_position_value,
    )


def _risk_config(settings: Settings) -> RiskConfig:
    return RiskConfig(
        stop_loss_pct=settings.stop_loss_pct,
        take_profit_pct=settings.take_profit_pct,
    )


def _daily_loss_state(settings: Settings) -> DailyLossState:
    return DailyLossState(
        realized_loss=0.0,
        threshold=settings.daily_loss_threshold,
    )


def _available_cash(broker: Any, settings: Settings) -> float:
    cash = getattr(broker, "cash", None)
    if cash is not None:
        return float(cash.amount)
    return max(
        float(settings.max_position_value),
        float(settings.max_position_value) / max(float(settings.buy_cash_fraction), 0.01),
    )


def _build_token_manager(settings: Settings) -> KisTokenManager:
    return KisTokenManager(build_kis_auth_config(settings))


def _build_soak_adapter(settings: SoakSettings) -> KisOrderAdapter:
    """Build only the mock token/query capability from the narrow soak root."""

    credential = settings.kis_mock
    token_manager = KisTokenManager(
        KisAuthConfig(
            domain=credential.domain,
            app_key=credential.app_key.get_secret_value(),
            app_secret=credential.app_secret.get_secret_value(),
            refresh_margin_seconds=settings.kis_token_refresh_margin_seconds,
            min_interval_seconds=settings.kis_min_interval_seconds,
            max_retries=settings.kis_max_retries,
            retry_backoff_seconds=settings.kis_retry_backoff_seconds,
            timeout_seconds=settings.kis_timeout_seconds,
        )
    )
    return KisOrderAdapter(
        token_manager=token_manager,
        domain=credential.domain,
        tr_id_profile="mock",
        min_interval_seconds=settings.kis_min_interval_seconds,
        max_retries=settings.kis_max_retries,
        retry_backoff_seconds=settings.kis_retry_backoff_seconds,
        timeout_seconds=settings.kis_timeout_seconds,
    )


def _build_quote_adapter(settings: Settings, token_manager: KisTokenManager) -> KisQuoteAdapter:
    active = settings.active_kis
    return KisQuoteAdapter(
        token_manager=token_manager,
        domain=active.domain,
        tr_id="FHKST01010100",
        min_interval_seconds=settings.kis_min_interval_seconds,
        max_retries=settings.kis_max_retries,
        retry_backoff_seconds=settings.kis_retry_backoff_seconds,
        timeout_seconds=settings.order_timeout_seconds,
    )


def _account_from_env() -> Optional[KisOrderAccount]:
    cano = os.getenv("KIS_ACCOUNT_CANO")
    product_code = os.getenv("KIS_ACCOUNT_PRODUCT_CODE", "01")
    if not cano:
        return None
    return KisOrderAccount(cano=cano, account_product_code=product_code)


def _build_broker(
    settings: Settings,
    *,
    token_manager: Optional[KisTokenManager],
    account: Optional[KisOrderAccount] = None,
    quote_adapter: Any = None,
) -> Any:
    if settings.trading_mode is TradingMode.MOCK:
        return MockBroker(
            cash=Money(10_000_000.0, "KRW"),
            pre_submit_quote_reader=(
                quote_adapter.fetch_current_price if quote_adapter is not None else None
            ),
        )

    if token_manager is None:
        raise ValueError("real broker requires the shared KisTokenManager")
    real_account = account or _account_from_env()
    if real_account is None:
        raise ValueError(
            "real KIS broker requires KIS_ACCOUNT_CANO and optional "
            "KIS_ACCOUNT_PRODUCT_CODE in the environment"
        )
    kwargs: dict[str, Any] = {}
    if quote_adapter is not None:
        kwargs["pre_submit_quote_reader"] = quote_adapter.fetch_current_price
    return build_kis_broker(
        settings, token_manager=token_manager, account=real_account, **kwargs
    )


def build_runtime(
    *,
    settings: Optional[Settings] = None,
    trading_date: Optional[str] = None,
    kis_account: Optional[KisOrderAccount] = None,
) -> _Runtime:
    """Build default production collaborators for a CLI command."""

    resolved_settings = settings or Settings()
    token_manager = _build_token_manager(resolved_settings)
    quote_adapter = _build_quote_adapter(resolved_settings, token_manager)
    now_kst = datetime.now(ZoneInfo("Asia/Seoul"))
    resolved_trading_date = trading_date or now_kst.strftime("%Y%m%d")
    ohlcv_adapter = PykrxOhlcvAdapter(
        adjusted=resolved_settings.ohlcv_adjusted,
        request_timeout_seconds=resolved_settings.pykrx_request_timeout_seconds,
    )
    policy = MarketCyclePolicy(ObservedKRXCalendar(ohlcv_adapter))
    cycle_evidence = policy.classify(now_kst)
    cutoff = policy.completed_bar_cutoff(now_kst.date())
    if not cutoff.available or cutoff.cutoff_date is None:
        raise RuntimeError("KRX completed-bar cutoff is unknown; execution fails closed")
    cutoff_text = cutoff.cutoff_date.strftime("%Y%m%d")
    data_source = build_data_source(
        resolved_settings,
        expected_date=cutoff_text,
        accepted_latest_date=cutoff_text,
        ohlcv_adapter=ohlcv_adapter,
        quote_adapter=quote_adapter,
    )
    return _Runtime(
        settings=resolved_settings,
        token_manager=token_manager,
        data_source=data_source,
        llm_provider=build_llm_provider(resolved_settings),
        broker=_build_broker(
            resolved_settings,
            token_manager=token_manager,
            account=kis_account,
            quote_adapter=quote_adapter,
        ),
        audit_conn=sqlite_audit.connect(resolved_settings.audit_db_path),
        notifier=build_notifier(resolved_settings),
        cycle_evidence=cycle_evidence,
        completed_bar_cutoff=cutoff_text,
    )


def _notification_attempt(
    notifier: Any,
    summary: str,
) -> tuple[NotificationDeliveryStatus, str | None]:
    """Return a bounded delivery verdict without allowing transport failure to escape."""

    if isinstance(notifier, NoopNotifier):
        notifier.send(summary)
        return NotificationDeliveryStatus.DISABLED, None
    try:
        delivered = bool(notifier.send(summary))
    except Exception:  # noqa: BLE001 - transport failure is durable, not fatal.
        return NotificationDeliveryStatus.FAILED, "TRANSPORT_EXCEPTION"
    if delivered:
        return NotificationDeliveryStatus.DELIVERED, None
    return NotificationDeliveryStatus.FAILED, "TRANSPORT_FAILED"


def _send_and_record_notification(
    *,
    conn: sqlite3.Connection,
    notifier: Any,
    run_id: str,
    ticker: str | None,
    kind: NotificationKind,
    summary: str,
) -> None:
    """Persist exactly one row for one logical delivery attempt.

    Transport remains fail-soft. The append is deliberately outside that safety
    envelope so evidence-write failure stops the caller.
    """

    status, failure_category = _notification_attempt(notifier, summary)
    sqlite_audit.append_notification_attempt(
        conn,
        NotificationAttempt(
            run_id=run_id,
            ticker=ticker,
            kind=kind,
            status=status,
            failure_category=failure_category,
            detail={},
            observed_at=datetime.now(timezone.utc),
        ),
    )


def _audit_connection(path: str, *, read_only: bool) -> sqlite3.Connection:
    resolved = Path(path).resolve(strict=True)
    if not resolved.is_file():
        raise ValueError("audit database path must be a regular file")
    mode = "ro" if read_only else "rw"
    return sqlite3.connect(f"{resolved.as_uri()}?mode={mode}", uri=True)


def _read_audit_health(path: str) -> AuditHealthEvidence:
    """Probe supported schema, integrity, FK enforcement, and rollback-only write access."""

    conn = _audit_connection(path, read_only=False)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        schema_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        integrity_ok = conn.execute("PRAGMA quick_check").fetchone() == ("ok",)
        foreign_keys_on = conn.execute("PRAGMA foreign_keys").fetchone() == (1,)
        writable = False
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE runs SET status = status WHERE 0")
            conn.rollback()
            writable = True
        except Exception:
            conn.rollback()
        healthy = (
            schema_version == sqlite_audit.SCHEMA_VERSION
            and integrity_ok
            and foreign_keys_on
            and writable
        )
        return AuditHealthEvidence(healthy, schema_version, integrity_ok, writable)
    finally:
        conn.close()


def _read_unresolved_orders(path: str) -> UnresolvedOrderScan:
    """Reduce append-only local evidence without claiming authenticated broker truth."""

    conn = _audit_connection(path, read_only=True)
    try:
        rows = conn.execute(
            """SELECT order_intent_id, ticker, event_type, duplicate_of_intent_id
               FROM order_events ORDER BY id"""
        ).fetchall()
    finally:
        conn.close()
    unresolved: dict[str, UnresolvedOrderEvidence] = {}
    for intent_id, ticker, event_type, duplicate_of in rows:
        try:
            event = OrderEventType(str(event_type))
        except ValueError:
            return UnresolvedOrderScan(False, ())
        key = str(intent_id)
        if event is OrderEventType.RECONCILED:
            unresolved.pop(key, None)
        elif duplicate_of is not None:
            unresolved[key] = UnresolvedOrderEvidence(
                str(ticker) if ticker else None,
                ReasonCode.DUPLICATE_ORDER,
                key,
            )
        elif event is OrderEventType.SUBMISSION_AMBIGUOUS:
            unresolved[key] = UnresolvedOrderEvidence(
                str(ticker) if ticker else None,
                ReasonCode.AMBIGUOUS_SUBMISSION,
                key,
            )
    return UnresolvedOrderScan(True, tuple(unresolved.values()))


def build_preflight_result(settings: Settings | None = None) -> PreflightResult:
    """Build the production D-11 evidence result shared by status and run."""

    resolved = settings or Settings()

    def market_reader() -> MarketCycleEvidence:
        adapter = PykrxOhlcvAdapter(
            adjusted=resolved.ohlcv_adjusted,
            request_timeout_seconds=resolved.pykrx_request_timeout_seconds,
        )
        policy = MarketCyclePolicy(ObservedKRXCalendar(adapter))
        return policy.classify(datetime.now(ZoneInfo("Asia/Seoul")))

    return evaluate_preflight(
        lambda: MockTargetEvidence(
            resolved.trading_mode is TradingMode.MOCK
            and resolved.active_kis == resolved.kis_mock,
            resolved.trading_mode.value,
        ),
        lambda: _read_audit_health(resolved.audit_db_path),
        market_reader,
        lambda: _read_unresolved_orders(resolved.audit_db_path),
    )


def _outcome_from_result(
    *,
    result: ExecutionResult,
    ticker: str,
    current_price: float,
    correlation_id: str,
    status: str = "ok",
) -> dict[str, Any]:
    audit = result.audit
    return {
        "ticker": ticker,
        "status": status,
        "final_action": audit.final_action if audit else result.action.value,
        "parsed_decision": audit.parsed_decision if audit else None,
        "confidence": result.confidence,
        "broker_order_id": result.broker_order_id,
        "order_reason": audit.order_reason if audit else result.reason,
        "requested_qty": result.order.quantity if result.order is not None else None,
        "filled_qty": None,
        "current_price": current_price,
        "correlation_id": correlation_id,
    }


def _reason_for_exception(exc: BaseException) -> tuple[ReasonCode, FailedStage]:
    if isinstance(exc, AmbiguousSubmissionError):
        return ReasonCode.AMBIGUOUS_SUBMISSION, FailedStage.ORDER
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    if "timeout" in name or "timeout" in message:
        return ReasonCode.LLM_TIMEOUT, FailedStage.LLM
    if "parse" in name or "malformed" in message or "json" in message:
        return ReasonCode.MALFORMED_SIGNAL, FailedStage.PARSING
    if "stale" in message:
        return ReasonCode.STALE_OHLCV, FailedStage.DATA_COLLECTION
    if "kis" in message or "broker" in message:
        return ReasonCode.KIS_UNAVAILABLE, FailedStage.ORDER
    return ReasonCode.KIS_UNAVAILABLE, FailedStage.DATA_COLLECTION


def _terminal_outcome(result: ExecutionResult) -> tuple[TickerOutcomeCode, ReasonCode]:
    audit = result.audit
    reason = (audit.order_reason if audit else result.reason).lower()
    action = audit.final_action if audit else result.action.value
    if "ambiguous" in reason:
        return TickerOutcomeCode.EXECUTION_ERROR, ReasonCode.AMBIGUOUS_SUBMISSION
    if "duplicate" in reason:
        return TickerOutcomeCode.ORDER_SUPPRESSED, ReasonCode.DUPLICATE_ORDER
    if result.broker_order_id:
        return TickerOutcomeCode.ORDER_SUBMITTED, ReasonCode.COMPLETED
    if action == "HOLD":
        if "confidence" in reason:
            return TickerOutcomeCode.NO_TRADE, ReasonCode.LOW_CONFIDENCE
        return TickerOutcomeCode.NO_TRADE, ReasonCode.HOLD_SIGNAL
    if result.order is not None:
        return TickerOutcomeCode.ORDER_SUPPRESSED, ReasonCode.COMPLETED
    return TickerOutcomeCode.NO_TRADE, ReasonCode.COMPLETED


def _run_provenance(*, ticker: str | None, trading_date: str) -> dict[str, Any]:
    return {"ticker": ticker, "requested_trading_date": trading_date}


def run_cycle(
    *,
    ticker: Optional[str] = None,
    execute: bool = False,
    live_confirm: bool = False,
    settings: Optional[Settings] = None,
    data_source: Any = None,
    llm_provider: Any = None,
    broker: Any = None,
    audit_conn: Optional[sqlite3.Connection] = None,
    notifier: Any = None,
    run_cycle: Optional[RunCycleFn] = None,
    trading_date: Optional[str] = None,
    run_id: Optional[str] = None,
    parent_run_id: Optional[str] = None,
    kis_account: Optional[KisOrderAccount] = None,
    preflight_result: Optional[PreflightResult] = None,
    order_event_hook: Optional[Callable[[Any], None]] = None,
) -> dict[str, Any]:
    """Run the screened universe with injected or production collaborators."""

    resolved_settings = settings or Settings()
    print(startup_banner(resolved_settings))

    dry_run = not execute
    if (
        resolved_settings.trading_mode is TradingMode.REAL
        and execute
        and not live_confirm
    ):
        raise SystemExit("real execute requires --live-confirm")

    resolved_trading_date = trading_date or _today_kst()
    fully_injected = all(
        item is not None
        for item in (data_source, llm_provider, broker, audit_conn, notifier)
    )
    resolved_preflight = preflight_result
    if resolved_preflight is None:
        resolved_preflight = (
            PreflightResult((), True, {})
            if fully_injected
            else build_preflight_result(resolved_settings)
        )
    if not resolved_preflight.global_executable:
        blocking_codes = sorted({
            check.code.value
            for check in resolved_preflight.checks
            if check.stops_run and check.state.value != "PASS"
        })
        raise SystemExit("preflight blocked: " + ",".join(blocking_codes))

    runtime: Optional[_Runtime] = None
    if any(item is None for item in (data_source, llm_provider, broker, audit_conn, notifier)):
        runtime = build_runtime(
            settings=resolved_settings,
            trading_date=resolved_trading_date,
            kis_account=kis_account,
        )
    resolved_data_source = data_source if data_source is not None else runtime.data_source
    resolved_llm_provider = llm_provider if llm_provider is not None else runtime.llm_provider
    resolved_broker = broker if broker is not None else runtime.broker
    resolved_audit_conn = audit_conn if audit_conn is not None else runtime.audit_conn
    resolved_notifier = notifier if notifier is not None else runtime.notifier
    cycle_fn = run_cycle or _run_llm_cycle

    resolved_run_id = run_id or uuid.uuid4().hex
    _ensure_audit_schema(resolved_audit_conn)
    sqlite_audit.recover_abandoned_runs(resolved_audit_conn)
    sqlite_audit.start_run(
        resolved_audit_conn,
        run_id=resolved_run_id,
        trading_mode=resolved_settings.trading_mode.value,
        dry_run=dry_run,
        run_kind=RunKind.RUN,
        trading_date_kst=resolved_trading_date,
        target=resolved_settings.trading_mode.value,
        policy_snapshot={
            "version": "execution-v1",
            "buy_confidence_threshold": resolved_settings.buy_confidence_threshold,
            "sell_confidence_threshold": resolved_settings.sell_confidence_threshold,
            "timing_policy_version": (
                runtime.cycle_evidence.policy_version
                if runtime is not None and runtime.cycle_evidence is not None else None
            ),
        },
        provenance={
            **_run_provenance(ticker=ticker, trading_date=resolved_trading_date),
            "completed_bar_cutoff": runtime.completed_bar_cutoff if runtime else None,
            "market_session": (
                runtime.cycle_evidence.session.value
                if runtime is not None and runtime.cycle_evidence is not None else None
            ),
            "market_executable": (
                runtime.cycle_evidence.executable
                if runtime is not None and runtime.cycle_evidence is not None else None
            ),
            "market_reason": (
                runtime.cycle_evidence.reason
                if runtime is not None and runtime.cycle_evidence is not None else None
            ),
        },
        parent_run_id=parent_run_id,
    )
    if hasattr(resolved_broker, "set_evidence_sink"):
        def persist_order_event(event: Any) -> None:
            sqlite_audit.append_order_event(resolved_audit_conn, event)
            if order_event_hook is not None:
                order_event_hook(event)

        resolved_broker.set_evidence_sink(persist_order_event)

    outcomes: list[dict[str, Any]] = []
    try:
        if ticker is not None:
            tickers = [_validate_ticker(ticker)]
        else:
            tickers = _candidate_tickers(
                resolved_data_source.screen_daily_candidates(resolved_trading_date)
            )
        for symbol in tickers:
            correlation_id = f"{resolved_run_id}:{symbol}"
            frozen_reason = resolved_preflight.frozen_tickers.get(symbol)
            if frozen_reason is not None:
                explanation = (
                    "로컬 감사 증거의 미해결 주문으로 이 티커가 동결되었습니다. "
                    "KIS 원장 확인 및 조정 증거 전에는 재주문하지 않습니다."
                )
                outcomes.append({
                    "ticker": symbol,
                    "status": "frozen",
                    "final_action": "HOLD",
                    "parsed_decision": None,
                    "confidence": None,
                    "broker_order_id": None,
                    "order_reason": explanation,
                    "requested_qty": None,
                    "filled_qty": None,
                    "current_price": None,
                    "correlation_id": correlation_id,
                })
                sqlite_audit.write_ticker_outcome(
                    resolved_audit_conn,
                    TickerOutcome(
                        run_id=resolved_run_id,
                        ticker=symbol,
                        outcome_code=TickerOutcomeCode.NO_TRADE,
                        reason_code=frozen_reason,
                        detail={
                            "correlation_id": correlation_id,
                            "freeze_scope": "local_audit_only",
                        },
                        final_order_state="FROZEN",
                    ),
                )
                continue
            terminal: TickerOutcome | None = None
            try:
                context = resolved_data_source.build_context(Ticker(symbol))
                result = cycle_fn(
                    resolved_llm_provider,
                    context,
                    broker=resolved_broker,
                    available_cash=_available_cash(resolved_broker, resolved_settings),
                    execution_config=_execution_config(resolved_settings),
                    risk_config=_risk_config(resolved_settings),
                    daily_loss_state=_daily_loss_state(resolved_settings),
                    dry_run=dry_run,
                    origin_run_id=resolved_run_id,
                )
                if result.audit is None:
                    raise RuntimeError("cycle result missing audit event")
                reconciliation = getattr(resolved_broker, "last_reconciliation", None)
                requested_qty = result.order.quantity if result.order is not None else None
                filled_qty = getattr(reconciliation, "filled_qty", None)
                if reconciliation is not None:
                    requested_qty = getattr(reconciliation, "requested_qty", requested_qty)
                sqlite_audit.write_decision(
                    resolved_audit_conn,
                    resolved_run_id,
                    result.audit,
                    confidence=result.confidence,
                    current_price=context.current_price.amount,
                    requested_qty=requested_qty,
                    filled_qty=filled_qty,
                    correlation_id=correlation_id,
                )
                outcome = _outcome_from_result(
                    result=result,
                    ticker=symbol,
                    current_price=context.current_price.amount,
                    correlation_id=correlation_id,
                )
                outcome["requested_qty"] = requested_qty
                outcome["filled_qty"] = filled_qty
                outcomes.append(outcome)
                outcome_code, reason_code = _terminal_outcome(result)
                terminal = TickerOutcome(
                    run_id=resolved_run_id, ticker=symbol,
                    outcome_code=outcome_code, reason_code=reason_code,
                    detail={
                        "correlation_id": correlation_id,
                        **(
                            resolved_data_source.cycle_evidence_for(symbol)
                            if hasattr(resolved_data_source, "cycle_evidence_for") else {}
                        ),
                    },
                    final_order_state=outcome_code.value,
                )
            except Exception as exc:  # noqa: BLE001 - isolate one ticker's failure.
                reason_code, failed_stage = _reason_for_exception(exc)
                outcome = {
                    "ticker": symbol,
                    "status": "error",
                    "final_action": "ERROR",
                    "parsed_decision": None,
                    "confidence": None,
                    "broker_order_id": None,
                    "order_reason": str(exc),
                    "requested_qty": None,
                    "filled_qty": None,
                    "current_price": None,
                    "correlation_id": correlation_id,
                }
                outcomes.append(outcome)
                terminal = TickerOutcome(
                    run_id=resolved_run_id, ticker=symbol,
                    outcome_code=TickerOutcomeCode.EXECUTION_ERROR,
                    reason_code=reason_code, failed_stage=failed_stage,
                    detail={"error_type": type(exc).__name__},
                    order_intent_id=(
                        exc.order_intent_id
                        if isinstance(exc, AmbiguousSubmissionError) else None
                    ),
                    final_order_state=(
                        "AMBIGUOUS_SUBMISSION"
                        if isinstance(exc, AmbiguousSubmissionError) else None
                    ),
                )
                _send_and_record_notification(
                    conn=resolved_audit_conn,
                    notifier=resolved_notifier,
                    run_id=resolved_run_id,
                    ticker=symbol,
                    kind=NotificationKind.IMMEDIATE_ERROR,
                    summary=f"ERROR {symbol}: {type(exc).__name__}: {exc}",
                )
            finally:
                if terminal is not None:
                    sqlite_audit.write_ticker_outcome(resolved_audit_conn, terminal)

        error_count = sqlite_audit.count_failed_ticker_outcomes(
            resolved_audit_conn, run_id=resolved_run_id
        )
        sqlite_audit.finish_run(
            resolved_audit_conn, run_id=resolved_run_id,
            status=(RunStatus.COMPLETED_WITH_ERRORS if error_count else RunStatus.COMPLETED),
        )
    except KeyboardInterrupt:
        sqlite_audit.finish_run(
            resolved_audit_conn, run_id=resolved_run_id, status=RunStatus.INTERRUPTED
        )
        raise
    except BaseException:
        sqlite_audit.finish_run(
            resolved_audit_conn, run_id=resolved_run_id, status=RunStatus.FAILED
        )
        raise

    summary = format_run_summary(
        run_id=resolved_run_id,
        trading_mode=resolved_settings.trading_mode.value,
        dry_run=dry_run,
        outcomes=outcomes,
    )
    _send_and_record_notification(
        conn=resolved_audit_conn,
        notifier=resolved_notifier,
        run_id=resolved_run_id,
        ticker=None,
        kind=NotificationKind.FINAL_SUMMARY,
        summary=summary,
    )
    return {
        "run_id": resolved_run_id,
        "dry_run": dry_run,
        "refused": False,
        "outcomes": outcomes,
        "errors": error_count,
    }


@soak_app.command("start")
def soak_start_command(
    campaign_id: str = typer.Option(..., "--campaign-id", help="Stable soak campaign identifier."),
    probe_only: bool = typer.Option(False, "--probe-only", help="Run authenticated GET-only compatibility probing."),
    proof_order: bool = typer.Option(False, "--proof-order", help="Request the separately gated one-order proof workflow."),
    fixture: Optional[Path] = typer.Option(None, "--fixture", dir_okay=False, help="Exclusive-create sanitized compatibility fixture."),
    ticker: Optional[str] = typer.Option(None, "--ticker", help="Explicit six-digit proof-order ticker."),
    side: Optional[str] = typer.Option(None, "--side", help="Explicit BUY or SELL proof-order side."),
    quantity: Optional[int] = typer.Option(None, "--quantity", min=1, max=10, help="Explicit small proof-order quantity."),
    price: Optional[float] = typer.Option(None, "--price", min=1, max=100_000_000, help="Explicit proof-order limit price."),
    accepted_profile: Optional[Path] = typer.Option(None, "--accepted-profile", dir_okay=False, help="Approved authenticated compatibility fixture."),
    confirmation: Optional[str] = typer.Option(None, "--confirm", help="Exact mock proof confirmation; prompted when omitted."),
) -> None:
    """Validate mock identity, then run only the explicitly selected safe path."""

    if probe_only and proof_order:
        typer.echo("select at most one of --probe-only or --proof-order", err=True)
        raise typer.Exit(2)
    try:
        settings = _soak_settings_factory()
        selected = tuple(
            profile
            for profile in MOCK_TR_PROFILE_CANDIDATES
            if profile.version == settings.kis_mock.tr_id_profile
        )
        if len(selected) != 1:
            raise ValueError("MOCK_ISOLATION_BLOCKED: selected profile is not a unique candidate")
        receipt = build_soak_identity_receipt(settings, campaign_id, selected[0])
        typer.echo(render_mock_identity_receipt(receipt))
        if proof_order:
            if any(value is None for value in (ticker, side, quantity, price, accepted_profile)):
                raise ValueError("PROOF_ORDER_PREREQUISITES_MISSING")
            assert ticker is not None and side is not None and quantity is not None
            assert price is not None and accepted_profile is not None
            if not settings.primary_audit_db_path.is_file() or not settings.soak_db_path.is_file():
                raise ValueError("PROOF_ORDER_STORES_MUST_EXIST")
            validate_store_topology(
                settings.primary_audit_db_path,
                settings.soak_db_path,
                settings.controller_db_path,
            )
            try:
                profile_document = json.loads(accepted_profile.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                raise ValueError("PROOF_ORDER_ACCEPTED_PROFILE_INVALID") from None
            if not isinstance(profile_document, dict) or (
                profile_document.get("state") != "ACCEPTED"
                or profile_document.get("evidence_class") != "KIS_OBSERVED"
                or profile_document.get("profile_version") != receipt.profile_version
                or profile_document.get("schema_version") != "kis-mock-compat-v1"
            ):
                raise ValueError("PROOF_ORDER_ACCEPTED_PROFILE_INVALID")
            expected_confirmation = (
                f"PROOF MOCK {receipt.account_suffix} {ticker} {quantity}"
            )
            supplied_confirmation = confirmation
            if supplied_confirmation is None:
                supplied_confirmation = typer.prompt(
                    f"Type exactly '{expected_confirmation}' to authorize one mock POST"
                )
            if supplied_confirmation != expected_confirmation:
                raise ValueError("PROOF_ORDER_CONFIRMATION_MISMATCH")
            policy = AmbiguityPolicy(
                version="ambiguity-v1",
                duration_seconds=60,
                poll_seconds=5,
                max_observations=12,
                profile_version=receipt.profile_version,
                field_contract_version="kis-mock-compat-v1",
            )
            adapter = _build_soak_adapter(settings)
            service = _proof_service_factory(adapter=adapter)
            proof_result = service.run(ProofOrderRequest(
                campaign_id=campaign_id,
                ticker=ticker,
                side=side,
                quantity=quantity,
                price=price,
                account=KisOrderAccount(
                    cano=settings.kis_mock_account_cano.get_secret_value(),
                    account_product_code=settings.kis_mock_account_product_code,
                ),
                receipt=receipt,
                primary_audit_db_path=settings.primary_audit_db_path,
                soak_db_path=settings.soak_db_path,
                controller_db_path=settings.controller_db_path,
                accepted_profile_fingerprint=fingerprint_accepted_profile(profile_document),
                field_contract_version="kis-mock-compat-v1",
                ambiguity_policy=policy,
            ))
            if fixture is not None:
                typer.echo(
                    f"fixture={export_proof_fixture(fixture, build_proof_fixture(proof_result))}"
                )
            typer.echo("proof_order=COMPLETE")
            return
        if not probe_only:
            if accepted_profile is None:
                raise ValueError("ACCEPTED_PROFILE_REQUIRED")
            try:
                profile_document = json.loads(accepted_profile.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                raise ValueError("ACCEPTED_PROFILE_INVALID") from None
            if not isinstance(profile_document, dict) or (
                profile_document.get("state") != "ACCEPTED"
                or profile_document.get("evidence_class") != "KIS_OBSERVED"
                or profile_document.get("profile_version") != receipt.profile_version
                or profile_document.get("schema_version") != "kis-mock-compat-v1"
            ):
                raise ValueError("ACCEPTED_PROFILE_INVALID")
            runtime = _soak_runtime_factory(settings, campaign_id)
            try:
                status = _orchestrate_soak_start(
                    runtime,
                    campaign_policy={
                        "accepted_profile_fingerprint": fingerprint_accepted_profile(
                            profile_document
                        ),
                        "accepted_profile_version": receipt.profile_version,
                        "field_contract_version": "kis-mock-compat-v1",
                        "ambiguity_policy_version": "ambiguity-v1",
                        "ambiguity_window_seconds": 60,
                        "ambiguity_poll_cadence_seconds": 5,
                        "ambiguity_max_observations": 12,
                        "target_eligible_days": settings.target_eligible_days,
                        "availability_failure_budget": settings.availability_failure_budget,
                    },
                )
            finally:
                runtime.close()
            typer.echo(f"campaign_state={getattr(status['state'], 'value', status['state'])}")
            return
        adapter = _build_soak_adapter(settings)
        result = _soak_probe(
            adapter,
            KisOrderAccount(
                cano=settings.kis_mock_account_cano.get_secret_value(),
                account_product_code=settings.kis_mock_account_product_code,
            ),
            selected,
            (date.today(), date.today()),
        )
        typer.echo(f"compatibility_state={result.state.value}")
        typer.echo(f"evidence_class={result.evidence_class.value}")
        typer.echo(f"profile_version={result.profile_version or 'UNKNOWN'}")
        if fixture is not None:
            typer.echo(f"fixture={export_compatibility_fixture(result, fixture)}")
    except (ValueError, OSError) as exc:
        typer.echo(str(exc)[:200], err=True)
        raise typer.Exit(2) from None


@soak_app.command("run")
def soak_run_command(
    campaign_id: str = typer.Option(..., "--campaign-id"),
    run_id: Optional[str] = typer.Option(None, "--run-id"),
) -> None:
    """Run one explicitly designated, broker-reconciled KIS mock day."""

    runtime: _SoakRuntime | None = None
    try:
        settings = _soak_settings_factory()
        runtime = _soak_runtime_factory(settings, campaign_id)
        result = _orchestrate_soak_run(
            runtime,
            run_id=run_id or uuid.uuid4().hex,
            observed_at=datetime.now(ZoneInfo("Asia/Seoul")),
        )
        typer.echo(f"run_id={result['run_id']}")
        typer.echo(f"day_verdict={result['verdict']}")
    except (ValueError, RuntimeError, OSError) as exc:
        typer.echo(str(exc)[:200], err=True)
        raise typer.Exit(2) from None
    finally:
        if runtime is not None:
            runtime.close()


@soak_app.command("resume")
def soak_resume_command(
    campaign_id: str = typer.Option(..., "--campaign-id"),
) -> None:
    """Reconcile and rebuild durable freezes; never replay a prior POST."""

    runtime: _SoakRuntime | None = None
    try:
        settings = _soak_settings_factory()
        runtime = _soak_runtime_factory(settings, campaign_id)
        status = _orchestrate_soak_resume(runtime)
        typer.echo(f"campaign_state={getattr(status['state'], 'value', status['state'])}")
        typer.echo(f"active_freezes={len(status['active_freezes'])}")
    except (ValueError, RuntimeError, OSError) as exc:
        typer.echo(str(exc)[:200], err=True)
        raise typer.Exit(2) from None
    finally:
        if runtime is not None:
            runtime.close()


@soak_app.command("status")
def soak_status_command(
    campaign_id: str = typer.Option(..., "--campaign-id"),
) -> None:
    """Read persisted campaign status without opening broker or controller paths."""

    conn: sqlite3.Connection | None = None
    try:
        settings = _soak_settings_factory()
        paths = validate_store_topology(
            settings.primary_audit_db_path,
            settings.soak_db_path,
            settings.controller_db_path,
        )
        soak_path = paths["soak_db_path"]
        if not soak_path.is_file():
            raise ValueError("SOAK_STORE_NOT_FOUND")
        conn = sqlite3.connect(f"{soak_path.as_uri()}?mode=ro", uri=True)
        conn.execute("PRAGMA query_only=ON")
        status = load_campaign_state(conn, campaign_id=campaign_id)
        typer.echo(f"campaign_state={status['state'].value}")
        typer.echo(f"credited_days={status['credited_days']}")
        typer.echo(f"active_freezes={len(status['active_freezes'])}")
    except (KeyError, ValueError, RuntimeError, OSError, sqlite3.Error) as exc:
        typer.echo(str(exc)[:200], err=True)
        raise typer.Exit(2) from None
    finally:
        if conn is not None:
            conn.close()


@soak_app.command("drill")
def soak_drill_command(
    fault: str = typer.Argument(..., help="One explicit controlled fault name."),
    campaign_id: str = typer.Option(..., "--campaign-id"),
) -> None:
    """Run one controller-gated controlled fault against an active mock campaign."""

    try:
        selected = parse_fault_name(fault)
        settings = _soak_settings_factory()
        result = _drill_service_factory(settings=settings).run(selected, campaign_id)
        typer.echo(f"drill_id={result.drill_id}")
        typer.echo(f"drill_verdict={result.verdict.value}")
    except (KeyError, ValueError, RuntimeError, OSError, sqlite3.Error) as exc:
        typer.echo(str(exc)[:200], err=True)
        raise typer.Exit(2) from None


@app.command("run")
def run_command(
    ticker: Optional[str] = typer.Option(None, "--ticker", help="Run one 6-digit KRX ticker."),
    execute: bool = typer.Option(False, "--execute", help="Place orders; omitted means dry-run."),
    live_confirm: bool = typer.Option(
        False,
        "--live-confirm",
        help="Required in real mode when --execute is passed.",
    ),
    parent_run_id: Optional[str] = typer.Option(None, "--parent-run-id", help="UUID of an explicit retry parent."),
) -> None:
    """Run one manual evaluation cycle over the screened universe."""

    try:
        result = run_cycle(
            ticker=ticker,
            execute=execute,
            live_confirm=live_confirm,
            parent_run_id=parent_run_id,
        )
    except SystemExit as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from None

    typer.echo(f"Run {result['run_id']} complete: {len(result['outcomes'])} tickers")


@app.command("replay")
def replay_command(
    fixture: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    output: Path = typer.Option(..., "--output", file_okay=False),
) -> None:
    """Replay a frozen fixture bundle entirely offline and write normalized evidence."""
    from trading_bot.replay import (
        NON_PROFITABILITY_DISCLAIMER,
        ReplayResult,
        build_replay_funnel,
        build_replay_manifest,
        load_replay_bundle,
        run_replay_scenarios,
        verify_replay_expectations,
        write_replay_result,
    )

    try:
        raw = json.loads(fixture.read_text(encoding="utf-8"))
        scenarios = load_replay_bundle(fixture)
        outcomes = run_replay_scenarios(scenarios)
        funnel = build_replay_funnel(outcomes)
        verification = verify_replay_expectations(outcomes)
        manifest = build_replay_manifest(
            scenario_fixtures=raw["scenarios"],
            ohlcv_fixtures=[row for scenario in raw["scenarios"] for row in scenario["market_history"]],
            raw_signal_fixtures=[step["raw_signal"] for scenario in raw["scenarios"] for step in scenario["steps"]],
            policy={scenario["id"]: scenario["policy"] for scenario in raw["scenarios"]},
            initial_state={scenario["id"]: scenario["initial_state"] for scenario in raw["scenarios"]},
            evaluation_time="|".join(scenario["evaluation_time"] for scenario in raw["scenarios"]),
            trading_date="|".join(scenario["trading_date"] for scenario in raw["scenarios"]),
            fixture_schema_version=raw["schema_version"],
        )
        result = ReplayResult(manifest, outcomes, {}, funnel, verification)
        written = write_replay_result(result, output)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        typer.echo(f"Replay failed: {type(exc).__name__}: {str(exc)[:200]}", err=True)
        raise typer.Exit(2) from None

    typer.echo(f"Replay result: {result.result_id}")
    for scenario_id in sorted({item.scenario_id for item in outcomes}):
        selected = [item for item in outcomes if item.scenario_id == scenario_id]
        counts = {action: sum(item.action == action for item in selected) for action in ("BUY", "HOLD", "SELL")}
        blocked = sum(item.blocked_reason is not None for item in selected)
        typer.echo(
            f"{scenario_id}: BUY={counts['BUY']} HOLD={counts['HOLD']} "
            f"SELL={counts['SELL']} blocked={blocked}"
        )
    for name in ("evaluated", "selected", "buy_signaled", "confidence_qualified", "risk_qualified", "validly_sized", "order_eligible"):
        count = getattr(funnel, name)
        typer.echo(f"{name}: {count.numerator}/{count.denominator}")
    typer.echo(f"Verification: {'PASS' if verification.passed else 'FAIL'}")
    for check in verification.checks:
        if not check.passed:
            typer.echo(
                f"Mismatch {check.scenario_id}/{check.ticker}/{check.stage}: "
                f"expected={check.expected} actual={check.actual}"
            )
    typer.echo(f"Evidence: {written}")
    typer.echo(NON_PROFITABILITY_DISCLAIMER)
    if not verification.passed:
        raise typer.Exit(1)


@app.command("screen")
def screen_command(
    trading_date: Optional[str] = typer.Option(None, "--date", help="KRX trading date YYYYMMDD."),
    no_progress: bool = typer.Option(
        False,
        "--no-progress",
        help="Suppress screening progress messages on stderr.",
    ),
    parent_run_id: Optional[str] = typer.Option(None, "--parent-run-id", help="UUID of an explicit retry parent."),
) -> None:
    """Preview the screened candidate universe without placing orders."""

    resolved_trading_date = trading_date or _today_kst()
    runtime = build_runtime(trading_date=resolved_trading_date)
    _ensure_audit_schema(runtime.audit_conn)
    sqlite_audit.recover_abandoned_runs(runtime.audit_conn)
    run_id = uuid.uuid4().hex
    sqlite_audit.start_run(
        runtime.audit_conn, run_id=run_id,
        trading_mode=runtime.settings.trading_mode.value, dry_run=True,
        run_kind=RunKind.SCREEN, trading_date_kst=resolved_trading_date,
        target=runtime.settings.trading_mode.value,
        policy_snapshot={"version": "screen-v1"},
        provenance={"requested_trading_date": resolved_trading_date},
        parent_run_id=parent_run_id,
    )
    progress = None if no_progress else _screen_progress
    try:
        result = runtime.data_source.screen_daily_candidates(
            resolved_trading_date,
            progress=progress,
        )
        candidates = _candidate_tickers(result)
        outcomes: dict[str, TickerOutcome] = {}
        for event in getattr(result, "audit_events", ()):
            symbol = event.ticker
            is_error = str(event.action).upper() not in {"SKIP_CANDIDATE", "REJECTED"}
            reason_text = str(event.reason).lower()
            if "stale" in reason_text:
                reason_code = ReasonCode.STALE_OHLCV
            elif "quote" in reason_text:
                reason_code = ReasonCode.STALE_QUOTE
            else:
                reason_code = ReasonCode.KIS_UNAVAILABLE
            outcomes[symbol] = TickerOutcome(
                run_id=run_id,
                ticker=symbol,
                outcome_code=(
                    TickerOutcomeCode.SCREEN_ERROR if is_error else TickerOutcomeCode.REJECTED
                ),
                reason_code=reason_code,
                failed_stage=FailedStage.SCREENING if is_error else None,
                detail=sanitize_detail({
                    "source": event.source,
                    "status": event.status,
                    "action": event.action,
                    "observed_date": event.observed_date,
                    "expected_date": event.expected_date,
                }),
            )
        for symbol in candidates:
            outcomes[symbol] = TickerOutcome(
                run_id=run_id, ticker=symbol,
                outcome_code=TickerOutcomeCode.SELECTED,
                reason_code=ReasonCode.COMPLETED,
            )
        for outcome in outcomes.values():
            sqlite_audit.write_ticker_outcome(
                runtime.audit_conn, outcome,
            )
        sqlite_audit.finish_run(runtime.audit_conn, run_id=run_id, status=RunStatus.COMPLETED)
    except KeyboardInterrupt:
        sqlite_audit.finish_run(runtime.audit_conn, run_id=run_id, status=RunStatus.INTERRUPTED)
        raise
    except BaseException:
        sqlite_audit.finish_run(runtime.audit_conn, run_id=run_id, status=RunStatus.FAILED)
        raise
    if progress is not None:
        progress(f"selected {len(candidates)} candidates")
    for symbol in candidates:
        typer.echo(symbol)


@app.command("status")
def status_command() -> None:
    """Render the exact D-11 safety result enforced by mutable runs."""

    typer.echo(render_preflight(build_preflight_result()))
