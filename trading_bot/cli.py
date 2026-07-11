"""Operator Typer CLI for manual trading-bot runs."""

from __future__ import annotations

import dotenv
dotenv.load_dotenv()

import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional, Sequence
from zoneinfo import ZoneInfo

import typer

from trading_bot.config import Settings, TradingMode, startup_banner
from trading_bot.data_source import ObservedKRXCalendar, build_data_source
from trading_bot.domain import Money, Ticker
from trading_bot.execution import ExecutionConfig, ExecutionResult
from trading_bot.kis_auth import KisTokenManager, build_kis_auth_config
from trading_bot.kis_broker import AmbiguousSubmissionError, build_kis_broker
from trading_bot.kis_order import KisOrderAccount
from trading_bot.kis_quote import KisQuoteAdapter
from trading_bot.market_cycle import MarketCycleEvidence, MarketCyclePolicy
from trading_bot.pykrx_adapter import PykrxOhlcvAdapter
from trading_bot.llm_provider import build_llm_provider, run_llm_cycle as _run_llm_cycle
from trading_bot.mock_broker import MockBroker
from trading_bot.notifier import build_notifier, format_run_summary
from trading_bot.risk import DailyLossState, RiskConfig
from trading_bot import sqlite_audit
from trading_bot.audit_models import (
    FailedStage,
    ReasonCode,
    RunKind,
    RunStatus,
    TickerOutcome,
    TickerOutcomeCode,
)

app = typer.Typer(no_args_is_help=True, help="Manual stock-trading bot operator CLI.")

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
        return MockBroker(cash=Money(10_000_000.0, "KRW"))

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


def _safe_send(notifier: Any, summary: str) -> bool:
    try:
        return bool(notifier.send(summary))
    except Exception:  # noqa: BLE001 - notification is deliberately fail-soft.
        return False


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
        resolved_broker.set_evidence_sink(
            lambda event: sqlite_audit.append_order_event(resolved_audit_conn, event)
        )

    outcomes: list[dict[str, Any]] = []
    try:
        if execute and runtime is not None and (
            runtime.cycle_evidence is None or not runtime.cycle_evidence.executable
        ):
            raise RuntimeError("KRX session is not authoritatively executable")
        if ticker is not None:
            tickers = [_validate_ticker(ticker)]
        else:
            tickers = _candidate_tickers(
                resolved_data_source.screen_daily_candidates(resolved_trading_date)
            )
        for symbol in tickers:
            correlation_id = f"{resolved_run_id}:{symbol}"
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
                _safe_send(resolved_notifier, f"ERROR {symbol}: {type(exc).__name__}: {exc}")
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
    _safe_send(resolved_notifier, summary)
    return {
        "run_id": resolved_run_id,
        "dry_run": dry_run,
        "refused": False,
        "outcomes": outcomes,
        "errors": error_count,
    }


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
        for symbol in candidates:
            sqlite_audit.write_ticker_outcome(
                runtime.audit_conn,
                TickerOutcome(
                    run_id=run_id, ticker=symbol,
                    outcome_code=TickerOutcomeCode.SELECTED,
                    reason_code=ReasonCode.COMPLETED,
                ),
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
    """Print a minimal local broker status snapshot."""

    runtime = build_runtime(trading_date=_today_kst())
    cash = getattr(runtime.broker, "cash", None)
    if cash is not None:
        typer.echo(f"Cash: {cash.amount:.0f} {cash.currency}")
    else:
        typer.echo(f"Trading mode: {runtime.settings.trading_mode.value}")
        typer.echo("Broker status: KIS account reconciliation is available during order runs")
