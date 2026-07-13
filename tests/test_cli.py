"""Offline tests for the Typer CLI composition root."""

from __future__ import annotations

import sqlite3
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from conftest import make_data_context, make_settings
from trading_bot.config import TradingMode
from trading_bot.domain import Decision, LLMSignal, Money, Ticker
from trading_bot.execution import (
    CycleAuditEvent,
    ExecutionAction,
    ExecutionResult,
)

REPLAY_FIXTURES = Path(__file__).parent / "fixtures" / "replay"


@dataclass
class _ScreenerResult:
    selected: tuple[str, ...]


class _DataSource:
    def __init__(self, tickers: tuple[str, ...] = ("005930",), fail_on: str | None = None):
        self.tickers = tickers
        self.fail_on = fail_on
        self.contexts: list[str] = []

    def screen_daily_candidates(self, trading_date: str) -> _ScreenerResult:
        assert trading_date
        return _ScreenerResult(self.tickers)

    def build_context(self, ticker: Ticker):
        self.contexts.append(ticker.value)
        if ticker.value == self.fail_on:
            raise RuntimeError(f"context failed for {ticker.value}")
        return make_data_context(
            ticker=ticker,
            current_price=Money(70_000.0, "KRW"),
        )


class _ProgressDataSource:
    def __init__(self) -> None:
        self.progress_messages: list[str] = []
        self.trading_date: str | None = None

    def screen_daily_candidates(
        self,
        trading_date: str,
        *,
        progress=None,
    ) -> _ScreenerResult:
        self.trading_date = trading_date
        if progress is not None:
            progress("fetching test market")
            progress("built 2 screenable rows")
        return _ScreenerResult(("005930", "000660"))


class _Provider:
    def generate_signal(self, context):
        return LLMSignal(
            decision=Decision.BUY,
            confidence=0.95,
            reason=f"qualified {context.ticker.value}",
        )


class _Broker:
    def __init__(self) -> None:
        self.orders = []

    def get_position(self, ticker: Ticker):
        return None

    def place_order(self, order):
        self.orders.append(order)
        return f"ORDER-{len(self.orders)}"


class _Notifier:
    def __init__(self, *, fail_on_error: bool = False) -> None:
        self.messages: list[str] = []
        self.fail_on_error = fail_on_error

    def send(self, summary: str) -> bool:
        self.messages.append(summary)
        if self.fail_on_error and "ERROR" in summary:
            raise RuntimeError("transport down")
        return True


def test_ambiguous_submission_becomes_terminal_ticker_outcome() -> None:
    from trading_bot.cli import run_cycle as cli_run_cycle
    from trading_bot.kis_broker import AmbiguousSubmissionError

    conn = sqlite3.connect(":memory:")

    def ambiguous_cycle(*args, **kwargs):
        raise AmbiguousSubmissionError(
            order_intent_id="intent-ambiguous", submission_id="submission-once"
        )

    result = cli_run_cycle(
        ticker="005930", execute=True, settings=make_settings(),
        data_source=_DataSource(), llm_provider=_Provider(), broker=_Broker(),
        audit_conn=conn, notifier=_Notifier(), run_cycle=ambiguous_cycle,
        trading_date="20260702", run_id="ambiguous-run",
    )
    row = conn.execute(
        "SELECT reason_code, order_intent_id, final_order_state FROM ticker_outcomes"
    ).fetchone()
    assert result["errors"] == 1
    assert row == (
        "AMBIGUOUS_SUBMISSION", "intent-ambiguous", "AMBIGUOUS_SUBMISSION"
    )


def _run_with(
    *,
    settings=None,
    data_source=None,
    broker=None,
    notifier=None,
    ticker: str | None = None,
    execute: bool = False,
    live_confirm: bool = False,
    run_cycle=None,
) -> dict[str, Any]:
    from trading_bot.cli import run_cycle as cli_run_cycle

    return cli_run_cycle(
        ticker=ticker,
        execute=execute,
        live_confirm=live_confirm,
        settings=settings or make_settings(),
        data_source=data_source or _DataSource(),
        llm_provider=_Provider(),
        broker=broker or _Broker(),
        audit_conn=sqlite3.connect(":memory:"),
        notifier=notifier or _Notifier(),
        run_cycle=run_cycle,
        trading_date="20260702",
        run_id="test-run",
    )


def test_real_execute_requires_live_confirm() -> None:
    from trading_bot.cli import app

    real_settings = make_settings(
        trading_mode=TradingMode.REAL,
        confirm_real_trading=True,
    )
    broker = _Broker()

    with pytest.raises(SystemExit):
        _run_with(settings=real_settings, broker=broker, execute=True)
    assert broker.orders == []

    accepted = _run_with(
        settings=real_settings,
        broker=broker,
        execute=True,
        live_confirm=True,
        run_cycle=lambda **kwargs: ExecutionResult(
            action=ExecutionAction.HOLD,
            order=None,
            reason="safe hold",
            audit=CycleAuditEvent(
                ticker=kwargs["context"].ticker.value,
                parsed_decision="HOLD",
                parse_error=None,
                risk_override=False,
                override_reason="",
                final_action="HOLD",
                order_reason="safe hold",
                dry_run=kwargs["dry_run"],
            ),
        ),
    )
    assert accepted["refused"] is False

    runner = CliRunner()
    assert "run" in runner.invoke(app, ["--help"]).stdout
    assert "screen" in runner.invoke(app, ["--help"]).stdout
    assert "status" in runner.invoke(app, ["--help"]).stdout


def test_report_group_is_discoverable_once_with_exact_nested_commands() -> None:
    from trading_bot.cli import app

    runner = CliRunner()
    top_level = runner.invoke(app, ["--help"])
    nested = runner.invoke(app, ["report", "--help"])

    assert top_level.exit_code == 0
    assert top_level.stdout.count("report") == 1
    assert nested.exit_code == 0
    command_lines = re.findall(r"│\s+(daily|period|replay)\s", nested.stdout)
    assert command_lines == ["daily", "period", "replay"]


def test_screen_command_reports_progress_on_stderr(monkeypatch: pytest.MonkeyPatch) -> None:
    import trading_bot.cli as cli

    data_source = _ProgressDataSource()

    monkeypatch.setattr(
        cli,
        "build_runtime",
        lambda *, trading_date: cli._Runtime(
            settings=make_settings(),
            token_manager=None,
            data_source=data_source,
            llm_provider=_Provider(),
            broker=_Broker(),
            audit_conn=sqlite3.connect(":memory:"),
            notifier=_Notifier(),
        ),
    )

    result = CliRunner().invoke(cli.app, ["screen", "--date", "20260709"])

    assert result.exit_code == 0
    assert result.stdout.splitlines() == ["005930", "000660"]
    assert "[screen] fetching test market" in result.stderr
    assert "[screen] selected 2 candidates" in result.stderr
    assert data_source.trading_date == "20260709"


def test_screen_command_can_suppress_progress(monkeypatch: pytest.MonkeyPatch) -> None:
    import trading_bot.cli as cli

    monkeypatch.setattr(
        cli,
        "build_runtime",
        lambda *, trading_date: cli._Runtime(
            settings=make_settings(),
            token_manager=None,
            data_source=_ProgressDataSource(),
            llm_provider=_Provider(),
            broker=_Broker(),
            audit_conn=sqlite3.connect(":memory:"),
            notifier=_Notifier(),
        ),
    )

    result = CliRunner().invoke(
        cli.app,
        ["screen", "--date", "20260709", "--no-progress"],
    )

    assert result.exit_code == 0
    assert result.stdout.splitlines() == ["005930", "000660"]
    assert result.stderr == ""


def test_screen_persists_each_selected_rejected_and_error_ticker_once(monkeypatch) -> None:
    import trading_bot.cli as cli
    from trading_bot.data_models import DataSourceAuditEvent

    conn = sqlite3.connect(":memory:")
    result_value = _ScreenerResult(("005930",))
    result_value.audit_events = (
        DataSourceAuditEvent("005930", "pykrx", "stale", "stale", "SKIP_CANDIDATE"),
        DataSourceAuditEvent("000660", "pykrx", "stale", "stale", "SKIP_CANDIDATE"),
        DataSourceAuditEvent("035420", "pykrx", "error", "failed", "ERROR"),
    )

    class _ScreenSource:
        def screen_daily_candidates(self, trading_date, *, progress=None):
            return result_value

    monkeypatch.setattr(cli, "build_runtime", lambda *, trading_date: cli._Runtime(
        settings=make_settings(), token_manager=None, data_source=_ScreenSource(),
        llm_provider=_Provider(), broker=_Broker(), audit_conn=conn, notifier=_Notifier(),
    ))
    invoked = CliRunner().invoke(cli.app, ["screen", "--date", "20260709", "--no-progress"])

    assert invoked.exit_code == 0
    rows = conn.execute(
        "SELECT ticker, outcome_code, failed_stage FROM ticker_outcomes ORDER BY ticker"
    ).fetchall()
    assert rows == [
        ("000660", "REJECTED", None),
        ("005930", "SELECTED", None),
        ("035420", "SCREEN_ERROR", "SCREENING"),
    ]


def test_dry_run_default_no_orders(capsys) -> None:
    broker = _Broker()

    result = _run_with(broker=broker)

    assert broker.orders == []
    assert result["dry_run"] is True
    captured = capsys.readouterr()
    assert "Trading bot startup safety" in captured.out
    assert "Trading mode: mock" in captured.out


def test_ticker_error_isolation() -> None:
    data_source = _DataSource(("005930", "000660", "035420"), fail_on="000660")
    notifier = _Notifier()
    conn = sqlite3.connect(":memory:")

    from trading_bot.cli import run_cycle as cli_run_cycle

    result = cli_run_cycle(
        ticker=None,
        execute=False,
        live_confirm=False,
        settings=make_settings(),
        data_source=data_source,
        llm_provider=_Provider(),
        broker=_Broker(),
        audit_conn=conn,
        notifier=notifier,
        trading_date="20260702",
        run_id="test-run",
    )

    assert [outcome["ticker"] for outcome in result["outcomes"]] == [
        "005930",
        "000660",
        "035420",
    ]
    assert result["outcomes"][1]["status"] == "error"
    assert "000660" in notifier.messages[-1]
    assert "context failed" in notifier.messages[-1]
    rows = conn.execute(
        "SELECT ticker FROM decisions ORDER BY id"
    ).fetchall()
    assert rows == [("005930",), ("035420",)]
    audit_rows = conn.execute(
        "SELECT ticker, outcome_code, failed_stage FROM ticker_outcomes ORDER BY id"
    ).fetchall()
    assert audit_rows == [
        ("005930", "ORDER_SUPPRESSED", None),
        ("000660", "EXECUTION_ERROR", "DATA_COLLECTION"),
        ("035420", "ORDER_SUPPRESSED", None),
    ]
    assert conn.execute(
        "SELECT status FROM runs WHERE run_id='test-run'"
    ).fetchone() == ("COMPLETED_WITH_ERRORS",)
    assert data_source.contexts == ["005930", "000660", "035420"]


def test_run_records_provenance_and_clean_terminal_state() -> None:
    conn = sqlite3.connect(":memory:")
    from trading_bot.cli import run_cycle as cli_run_cycle

    result = cli_run_cycle(
        settings=make_settings(), data_source=_DataSource(("005930",)),
        llm_provider=_Provider(), broker=_Broker(), audit_conn=conn,
        notifier=_Notifier(), trading_date="20260702",
    )

    assert len(result["run_id"]) == 32
    row = conn.execute(
        "SELECT run_kind, status, trading_date_kst, target, policy_snapshot, provenance FROM runs"
    ).fetchone()
    assert row[:4] == ("RUN", "COMPLETED", "20260702", "mock")
    assert "execution-v1" in row[4]
    assert "requested_trading_date" in row[5]
    assert conn.execute("SELECT COUNT(*) FROM ticker_outcomes").fetchone() == (1,)


def test_confidence_persisted_end_to_end() -> None:
    """OPS-02/D-10: the parsed signal confidence round-trips into SQLite.

    Runs the real cycle path (run_cycle defaulted to None so _run_llm_cycle ->
    execute_signal_cycle runs the genuine _Provider signal) through the real
    write_decision sink, then reads the stored decisions.confidence back. This
    inverts the verifier's failing probe (VERIFICATION.md line 94, which saw NULL)
    and pins the fail-safe: a failing ticker records no decisions row, so its
    confidence is never a spurious non-null.
    """

    data_source = _DataSource(("005930", "000660"), fail_on="000660")
    conn = sqlite3.connect(":memory:")

    from trading_bot.cli import run_cycle as cli_run_cycle

    result = cli_run_cycle(
        ticker=None,
        execute=False,
        live_confirm=False,
        settings=make_settings(),
        data_source=data_source,
        llm_provider=_Provider(),
        broker=_Broker(),
        audit_conn=conn,
        notifier=_Notifier(),
        run_cycle=None,  # real _run_llm_cycle -> execute_signal_cycle path
        trading_date="20260702",
        run_id="test-run",
    )

    # The parsed ticker persists a NON-NULL confidence equal to the provider's 0.95.
    row = conn.execute(
        "SELECT confidence FROM decisions WHERE ticker = ?", ("005930",)
    ).fetchone()
    assert row is not None
    assert row[0] is not None
    assert row[0] == pytest.approx(0.95)

    # Fail-safe: the failing ticker records NO decisions row (so no spurious
    # non-null confidence); confidence is non-null ONLY for the parsed ticker.
    failed_rows = conn.execute(
        "SELECT confidence FROM decisions WHERE ticker = ?", ("000660",)
    ).fetchall()
    assert failed_rows == []
    assert result["errors"] == 1

    all_conf = conn.execute("SELECT confidence FROM decisions").fetchall()
    assert all_conf == [(pytest.approx(0.95),)]


def test_ticker_option_narrows_universe() -> None:
    data_source = _DataSource(("005930", "000660", "035420"))

    result = _run_with(data_source=data_source, ticker="000660")

    assert [outcome["ticker"] for outcome in result["outcomes"]] == ["000660"]
    assert data_source.contexts == ["000660"]


def test_real_broker_uses_shared_token_manager(monkeypatch) -> None:
    import trading_bot.cli as cli
    from trading_bot.kis_order import KisOrderAccount

    real_settings = make_settings(
        trading_mode=TradingMode.REAL,
        confirm_real_trading=True,
    )
    token_manager = object()
    account = KisOrderAccount(cano="12345678", account_product_code="01")
    calls = []

    def fake_build_kis_broker(settings, *, token_manager, account, client=None):
        calls.append(
            {
                "settings": settings,
                "token_manager": token_manager,
                "account": account,
                "client": client,
            }
        )
        return _Broker()

    monkeypatch.setattr(cli, "build_kis_broker", fake_build_kis_broker)

    broker = cli._build_broker(
        real_settings,
        token_manager=token_manager,
        account=account,
    )

    assert isinstance(broker, _Broker)
    assert calls == [
        {
            "settings": real_settings,
            "token_manager": token_manager,
            "account": account,
            "client": None,
        }
    ]


def test_immediate_error_push() -> None:
    error_notifier = _Notifier(fail_on_error=True)
    error_result = _run_with(
        data_source=_DataSource(("005930", "000660"), fail_on="000660"),
        notifier=error_notifier,
    )
    assert error_result["errors"] == 1
    assert len(error_notifier.messages) == 2
    assert "ERROR" in error_notifier.messages[0]
    assert "000660" in error_notifier.messages[0]
    assert "Trading run test-run" in error_notifier.messages[1]

    clean_notifier = _Notifier()
    clean_result = _run_with(
        data_source=_DataSource(("005930", "035420")),
        notifier=clean_notifier,
    )
    assert clean_result["errors"] == 0
    assert len(clean_notifier.messages) == 1
    assert "Trading run test-run" in clean_notifier.messages[0]


def test_replay_command_is_offline_concise_and_writes_complete_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import trading_bot.cli as cli

    monkeypatch.setattr(
        cli, "build_runtime",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("live builder called")),
    )
    result = CliRunner().invoke(
        cli.app,
        ["replay", str(REPLAY_FIXTURES / "focused.json"), "--output", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    assert "Replay result:" in result.stdout
    assert "Verification: PASS" in result.stdout
    assert "evaluated:" in result.stdout and "/" in result.stdout
    assert "decision-policy paths only" in result.stdout
    assert "Mismatch " not in result.stdout
    output_files = list(tmp_path.glob("*.json"))
    assert len(output_files) == 1
    document = json.loads(output_files[0].read_text())
    assert document["result_id"] in result.stdout
    assert document["evidence"]["verification"]["passed"] is True
    assert document["evidence"]["funnel"]["evaluated"]["denominator"] > 0
    assert "decision-policy paths only" in document["evidence"]["disclaimer"]

    repeated = CliRunner().invoke(
        cli.app,
        ["replay", str(REPLAY_FIXTURES / "focused.json"), "--output", str(tmp_path)],
    )
    assert repeated.exit_code == 0, repeated.output
    assert len(list(tmp_path.glob("*.json"))) == 1
    assert document["result_id"] in repeated.stdout


def test_replay_command_shows_only_mismatch_detail_and_exits_nonzero(tmp_path: Path) -> None:
    import trading_bot.cli as cli

    raw = json.loads((REPLAY_FIXTURES / "focused.json").read_text())
    raw["scenarios"][0]["steps"][0]["expected_action"] = "HOLD"
    fixture = tmp_path / "mismatch.json"
    fixture.write_text(json.dumps(raw), encoding="utf-8")
    result = CliRunner().invoke(
        cli.app, ["replay", str(fixture), "--output", str(tmp_path / "out")]
    )
    assert result.exit_code == 1
    assert "Verification: FAIL" in result.stdout
    assert "Mismatch buy-at-threshold/005930/action" in result.stdout
    assert "malformed-signal/000002/action" not in result.stdout


def test_replay_command_rejects_invalid_fixture_with_bounded_diagnostic(tmp_path: Path) -> None:
    from trading_bot.cli import app

    fixture = tmp_path / "invalid.json"
    fixture.write_text('{"secret":"do-not-echo"}', encoding="utf-8")
    result = CliRunner().invoke(
        app, ["replay", str(fixture), "--output", str(tmp_path / "out")]
    )
    assert result.exit_code == 2
    assert "Replay failed:" in result.stderr
    assert len(result.stderr) < 300
