from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone

import pytest

from conftest import make_data_context, make_settings
from trading_bot.domain import Decision, LLMSignal, Money, Position, Ticker
from trading_bot.portfolio import (
    PortfolioAccountSummary,
    PortfolioCompleteness,
    PortfolioHolding,
    PortfolioSnapshot,
)


class DataSource:
    def __init__(self, candidates=("005930", "035420")):
        self.candidates = candidates
        self.contexts: list[str] = []

    def screen_daily_candidates(self, trading_date):
        return type("Screen", (), {"selected": self.candidates})()

    def build_context(self, ticker):
        self.contexts.append(ticker.value)
        return make_data_context(ticker=ticker, current_price=Money(70_000.0, "KRW"))


class Provider:
    def __init__(self, calls, failures=0):
        self.calls = calls
        self.failures = failures

    def generate_signal(self, context):
        self.calls.append(context.ticker.value)
        if self.failures:
            self.failures -= 1
            raise RuntimeError("provider unavailable")
        return LLMSignal(Decision.HOLD, 0.9, "durable daily hold")


class Broker:
    def __init__(self):
        self.orders = []
        self.positions = {
            "005930": Position(Ticker("005930"), 2, Money(65_000.0, "KRW"))
        }

    def get_position(self, ticker):
        return self.positions.get(ticker.value)

    def place_order(self, order, **kwargs):
        self.orders.append(order)
        return "ORDER-1"


class Lease:
    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail

    def assert_active_owner(self):
        self.calls += 1
        if self.fail:
            raise RuntimeError("lease lost")


class Notifier:
    def send(self, summary):
        return True


def snapshot(*, cash=1_000_000.0, observed_second=0):
    return PortfolioSnapshot(
        snapshot_id=f"snapshot-{cash}-{observed_second}",
        account_scope_hash="a" * 64,
        trading_date=date(2026, 9, 4),
        previous_trading_date=date(2026, 9, 3),
        observed_at=datetime(2026, 9, 4, 1, 0, observed_second, tzinfo=timezone.utc),
        completeness=PortfolioCompleteness.COMPLETE,
        reason_code="COMPLETE",
        daily_page_count=1,
        balance_page_count=1,
        holdings=(PortfolioHolding("005930", 2, 2, 65_000.0),),
        orders=(),
        fills=(),
        account=PortfolioAccountSummary(cash, 2_000_000.0),
    )


def invoke(conn, *, run_id, trading_date="20260904", reader=None, factory=None,
           lease=None, cycle=None):
    from trading_bot.cli import run_cycle

    return run_cycle(
        settings=make_settings(llm_max_retries=2),
        data_source=DataSource(),
        llm_provider_factory=factory,
        broker=Broker(),
        audit_conn=conn,
        notifier=Notifier(),
        run_cycle=cycle,
        trading_date=trading_date,
        run_id=run_id,
        portfolio_snapshot_reader=reader or (lambda: snapshot()),
        mutation_lease=lease or Lease(),
    )


def test_same_day_overlap_reuses_one_final_signal_without_provider_construction():
    conn = sqlite3.connect(":memory:")
    calls: list[str] = []
    constructions = []

    def factory():
        constructions.append("built")
        return Provider(calls)

    first = invoke(conn, run_id="phase11-first", factory=factory)
    second = invoke(conn, run_id="phase11-second", factory=factory)

    assert [item["ticker"] for item in first["outcomes"]] == ["005930", "035420"]
    assert [item["ticker"] for item in second["outcomes"]] == ["005930", "035420"]
    assert calls == ["005930", "035420"]
    assert constructions == ["built"]
    assert conn.execute("SELECT COUNT(*) FROM daily_evaluations").fetchone() == (2,)
    provenance = conn.execute(
        "SELECT provenance_json FROM daily_evaluations WHERE ticker='005930'"
    ).fetchone()[0]
    assert provenance == '["HELD","SCREENED"]'


def test_started_crash_is_finalized_unavailable_and_never_calls_provider():
    from trading_bot.portfolio_store import migrate_portfolio, start_daily_evaluation

    conn = sqlite3.connect(":memory:")
    migrate_portfolio(conn)
    start_daily_evaluation(
        conn,
        trading_date_kst=date(2026, 9, 4),
        ticker="005930",
        provenance=("HELD", "SCREENED"),
        canonical_input=b"committed-before-crash",
        account_scope_hash="a" * 64,
    )
    calls = []

    result = invoke(conn, run_id="phase11-recovery", factory=lambda: Provider(calls))

    assert calls == []
    assert result["outcomes"][0]["final_action"] == "HOLD"
    assert conn.execute(
        "SELECT reason_code FROM daily_evaluation_events WHERE ticker IS NULL "
        if False else
        "SELECT reason_code FROM daily_evaluation_events WHERE event_type='LLM_UNAVAILABLE'"
    ).fetchone() == ("LLM_UNAVAILABLE",)


def test_date_rollover_allows_one_new_provider_boundary():
    conn = sqlite3.connect(":memory:")
    calls = []
    factory = lambda: Provider(calls)

    invoke(conn, run_id="phase11-day-one", trading_date="20260904", factory=factory)
    invoke(conn, run_id="phase11-day-two", trading_date="20260905", factory=factory)

    assert calls == ["005930", "035420", "005930", "035420"]
    assert conn.execute("SELECT COUNT(*) FROM daily_evaluations").fetchone() == (4,)


def test_reused_signal_rechecks_lease_before_execution_and_post_boundary():
    conn = sqlite3.connect(":memory:")
    calls = []
    invoke(conn, run_id="phase11-seed", factory=lambda: Provider(calls))
    lost = Lease(fail=True)

    result = invoke(
        conn, run_id="phase11-replay", factory=lambda: pytest.fail("must not construct"),
        lease=lost,
    )

    assert calls == ["005930", "035420"]
    assert lost.calls >= 1
    assert all(item["status"] == "error" for item in result["outcomes"])


def test_screened_only_sizing_uses_post_held_broker_cash_snapshot():
    conn = sqlite3.connect(":memory:")
    snapshots = iter((snapshot(cash=100.0), snapshot(cash=900.0, observed_second=1)))
    seen_cash = []

    def cycle(provider, context, **kwargs):
        seen_cash.append((context.ticker.value, kwargs["available_cash"]))
        from trading_bot.llm_provider import run_llm_cycle
        return run_llm_cycle(provider, context, **kwargs)

    invoke(
        conn,
        run_id="phase11-cash-refresh",
        reader=lambda: next(snapshots),
        factory=lambda: Provider([]),
        cycle=cycle,
    )

    assert seen_cash == [("005930", 100.0), ("035420", 900.0)]
