from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from trading_bot.exit_manager import (
    ExitDisposition,
    ExitTriggerKind,
    blocks_new_buy_for_ticker,
    evaluate_daily_exit_trigger,
    evaluate_exit_candidate,
    evaluate_risk_exit_trigger,
    submit_exit,
)
from trading_bot.portfolio import (
    PortfolioAccountSummary,
    PortfolioCompleteness,
    PortfolioHolding,
    PortfolioOrder,
    PortfolioSnapshot,
)
from trading_bot.domain import Money, Order, OrderSide, Ticker
from trading_bot.kis_broker import KISBroker, MarketClosedError
from trading_bot.kis_order import FillStatus, KisOrderAccount, KisOrderQueryResult
from trading_bot.data_models import SourceHealth, SourceStatus
from trading_bot.kis_quote import KisQuoteResult
from trading_bot.risk import RiskAction, RiskDecision


def _snapshot(*, orderable: int = 7, order_status: str | None = None) -> PortfolioSnapshot:
    orders = ()
    if order_status is not None:
        orders = (
            PortfolioOrder(
                order_id="KIS-SELL-1",
                original_order_id=None,
                ticker="005930",
                side="SELL",
                ordered_quantity=7,
                filled_quantity=2 if order_status == "PARTIAL" else 0,
                remaining_quantity=5 if order_status == "PARTIAL" else 7,
                cancelled_quantity=0,
                rejected_quantity=0,
                limit_price=70_000.0,
                status=order_status,
                order_date="20260904",
                order_time="100000",
            ),
        )
    return PortfolioSnapshot(
        snapshot_id="snapshot-current",
        account_scope_hash="a" * 64,
        trading_date=date(2026, 9, 4),
        previous_trading_date=date(2026, 9, 3),
        observed_at=datetime(2026, 9, 4, 1, tzinfo=timezone.utc),
        completeness=PortfolioCompleteness.COMPLETE,
        reason_code="COMPLETE",
        daily_page_count=1,
        balance_page_count=1,
        holdings=(PortfolioHolding("005930", 9, orderable, 65_000.0),),
        orders=orders,
        fills=(),
        account=PortfolioAccountSummary(1_000_000.0, 2_000_000.0),
    )


@pytest.mark.parametrize(
    ("kind", "trigger"),
    [
        (
            ExitTriggerKind.DAILY_LLM_SELL,
            lambda: evaluate_daily_exit_trigger(
                ticker="005930", cycle_id="cycle-1", decision="SELL", confidence=0.9,
                threshold=0.8,
            ),
        ),
        (
            ExitTriggerKind.INTRADAY_STOP_LOSS,
            lambda: evaluate_risk_exit_trigger(
                ticker="005930", cycle_id="cycle-1",
                decision=RiskDecision(RiskAction.SELL, "stop_loss"),
            ),
        ),
        (
            ExitTriggerKind.INTRADAY_TAKE_PROFIT,
            lambda: evaluate_risk_exit_trigger(
                ticker="005930", cycle_id="cycle-1",
                decision=RiskDecision(RiskAction.SELL, "take_profit"),
            ),
        ),
    ],
)
def test_all_exit_sources_reduce_to_one_full_orderable_submission(kind, trigger) -> None:
    result = evaluate_exit_candidate(trigger(), _snapshot(orderable=7))

    assert result.trigger is not None
    assert result.trigger.kind is kind
    assert result.disposition is ExitDisposition.SUBMIT
    assert result.quantity == 7


@pytest.mark.parametrize("status", ["OPEN", "PARTIAL"])
def test_open_or_partial_sell_is_reconcile_only_and_blocks_buy(status: str) -> None:
    trigger = evaluate_daily_exit_trigger(
        ticker="005930", cycle_id="cycle-2", decision="SELL", confidence=1.0,
        threshold=0.8,
    )

    result = evaluate_exit_candidate(trigger, _snapshot(order_status=status))

    assert result.disposition is ExitDisposition.RECONCILE_ONLY
    assert result.quantity == 0
    assert result.broker_subject_id == "KIS-SELL-1"
    assert blocks_new_buy_for_ticker(_snapshot(order_status=status), "005930") is True


def test_partial_fill_never_computes_a_local_authoritative_remainder() -> None:
    result = evaluate_exit_candidate(
        evaluate_risk_exit_trigger(
            ticker="005930", cycle_id="cycle-3",
            decision=RiskDecision(RiskAction.SELL, "stop_loss"),
        ),
        _snapshot(order_status="PARTIAL"),
    )

    assert result.disposition is ExitDisposition.RECONCILE_ONLY
    assert result.quantity == 0


def test_terminal_no_fill_requires_a_new_cycle_before_another_intent() -> None:
    trigger = evaluate_daily_exit_trigger(
        ticker="005930", cycle_id="cycle-same", decision="SELL", confidence=0.9,
        threshold=0.8,
    )

    same_cycle = evaluate_exit_candidate(
        trigger, _snapshot(order_status="NO_FILL"),
        latest_terminal_cycle_id="cycle-same",
    )
    next_cycle = evaluate_exit_candidate(
        evaluate_daily_exit_trigger(
            ticker="005930", cycle_id="cycle-next", decision="SELL", confidence=0.9,
            threshold=0.8,
        ),
        _snapshot(order_status="NO_FILL"),
        latest_terminal_cycle_id="cycle-same",
    )

    assert same_cycle.disposition is ExitDisposition.BLOCKED
    assert next_cycle.disposition is ExitDisposition.SUBMIT
    assert next_cycle.quantity == 7


def test_missing_or_non_orderable_holding_is_hold() -> None:
    trigger = evaluate_daily_exit_trigger(
        ticker="005930", cycle_id="cycle-4", decision="SELL", confidence=0.9,
        threshold=0.8,
    )
    assert evaluate_exit_candidate(trigger, _snapshot(orderable=0)).disposition is ExitDisposition.HOLD


def test_daily_loss_is_not_an_exit_input_or_liquidation_trigger() -> None:
    assert evaluate_daily_exit_trigger(
        ticker="005930", cycle_id="cycle-5", decision="BUY", confidence=1.0,
        threshold=0.8,
    ) is None
    risk_trigger = evaluate_risk_exit_trigger(
        ticker="005930", cycle_id="cycle-5",
        decision=RiskDecision(RiskAction.SELL, "take_profit"),
    )
    assert evaluate_exit_candidate(risk_trigger, _snapshot()).disposition is ExitDisposition.SUBMIT


class _BoundaryAdapter:
    def __init__(self, sequence: list[str], *, fail_post: bool = False) -> None:
        self.sequence = sequence
        self.fail_post = fail_post
        self.post_attempts = 0
        self.orders: list[Order] = []

    def inquire_daily_ccld(self, **kwargs):
        return KisOrderQueryResult(
            [], SourceHealth("kis_order", SourceStatus.AVAILABLE, "ok")
        )

    def inquire_balance(self, **kwargs):
        return KisOrderQueryResult(
            {}, SourceHealth("kis_order", SourceStatus.AVAILABLE, "ok")
        )

    def place_order_cash(self, *, order, **kwargs):
        self.sequence.append("post")
        self.post_attempts += 1
        self.orders.append(order)
        if self.fail_post:
            raise TimeoutError("provider prose must not persist")
        return type("PostResult", (), {"order_id": "KIS-1"})()

    def parse_fill_status(self, output, *, order_id, ticker):
        quantity = self.orders[-1].quantity
        return FillStatus(order_id, ticker, quantity, 0, quantity)


class _Lease:
    account_scope_hash = "a" * 64
    owner_token = "owner-secret-token"

    def __init__(self, sequence: list[str], *, fail: bool = False) -> None:
        self.sequence = sequence
        self.fail = fail

    def assert_active_owner(self) -> None:
        self.sequence.append("lease")
        if self.fail:
            raise RuntimeError("ownership lost")


def _live_order(side: OrderSide, quantity: int = 7) -> Order:
    return Order(Ticker("005930"), side, quantity, Money(70_123.0, "KRW"))


def _quote(now: datetime) -> KisQuoteResult:
    return KisQuoteResult(
        Money(70_111.0, "KRW"),
        SourceHealth("kis_quote", SourceStatus.AVAILABLE, "ok"),
        now,
    )


@pytest.mark.parametrize("side", [OrderSide.BUY, OrderSide.SELL])
def test_money_boundary_refreshes_regates_asserts_and_posts_once(side: OrderSide) -> None:
    sequence: list[str] = []
    now = datetime(2026, 9, 4, 1, tzinfo=timezone.utc)
    adapter = _BoundaryAdapter(sequence)
    events = []
    broker = KISBroker(
        order_adapter=adapter,
        account=KisOrderAccount("12345678", "01"),
        market_clock=lambda: True,
        evidence_sink=lambda event: (events.append(event), sequence.append(event.event_type.value)),
        pre_submit_quote_reader=lambda ticker: _quote(now),
        clock=lambda: now,
    )

    result = broker.place_order(
        _live_order(side),
        portfolio_refresh=lambda ticker: (sequence.append("refresh"), _snapshot(orderable=3))[1],
        lease_guard=_Lease(sequence),
        cycle_snapshot_id="snapshot-current",
    )

    assert result == "KIS-1"
    assert adapter.post_attempts == 1
    assert adapter.orders[0].quantity == (3 if side is OrderSide.SELL else 7)
    assert adapter.orders[0].limit_price.amount == 70_111.0
    assert sequence.index("INTENT_CREATED") < sequence.index("refresh")
    assert sequence.index("refresh") < sequence.index("lease")
    assert sequence.index("lease") < sequence.index("SUBMISSION_ATTEMPTED")
    assert sequence.index("SUBMISSION_ATTEMPTED") < sequence.index("post")


@pytest.mark.parametrize("side", [OrderSide.BUY, OrderSide.SELL])
def test_money_boundary_blocks_changed_truth_or_lease_loss_with_zero_post(side: OrderSide) -> None:
    for snapshot, lease in (
        (_snapshot(order_status="OPEN"), _Lease([])),
        (_snapshot(orderable=3), _Lease([], fail=True)),
    ):
        adapter = _BoundaryAdapter([])
        now = datetime(2026, 9, 4, 1, tzinfo=timezone.utc)
        broker = KISBroker(
            order_adapter=adapter,
            account=KisOrderAccount("12345678", "01"),
            market_clock=lambda: True,
            pre_submit_quote_reader=lambda ticker: _quote(now),
            clock=lambda: now,
        )
        with pytest.raises(MarketClosedError):
            broker.place_order(
                _live_order(side),
                portfolio_refresh=lambda ticker, value=snapshot: value,
                lease_guard=lease,
                cycle_snapshot_id="snapshot-current",
            )
        assert adapter.post_attempts == 0


def test_money_boundary_evidence_failure_prevents_post_and_token_is_not_persisted() -> None:
    adapter = _BoundaryAdapter([])
    now = datetime(2026, 9, 4, 1, tzinfo=timezone.utc)
    captured = []

    def sink(event):
        captured.append(event)
        if event.event_type.value == "SUBMISSION_ATTEMPTED":
            raise OSError("audit unavailable")

    broker = KISBroker(
        order_adapter=adapter,
        account=KisOrderAccount("12345678", "01"),
        market_clock=lambda: True,
        evidence_sink=sink,
        pre_submit_quote_reader=lambda ticker: _quote(now),
        clock=lambda: now,
    )
    with pytest.raises(OSError, match="audit unavailable"):
        broker.place_order(
            _live_order(OrderSide.SELL),
            portfolio_refresh=lambda ticker: _snapshot(orderable=3),
            lease_guard=_Lease([]),
            cycle_snapshot_id="snapshot-current",
        )
    assert adapter.post_attempts == 0
    assert "owner-secret-token" not in repr(captured)


@pytest.mark.parametrize("kind", ["stop_loss", "take_profit"])
def test_refreshed_risk_exit_that_clears_never_reaches_kis_post(kind: str) -> None:
    """The original risk decision must be re-proven using fresh broker truth."""

    sequence: list[str] = []
    adapter = _BoundaryAdapter(sequence)
    now = datetime(2026, 9, 4, 1, tzinfo=timezone.utc)
    events = []
    broker = KISBroker(
        order_adapter=adapter,
        account=KisOrderAccount("12345678", "01"),
        market_clock=lambda: True,
        evidence_sink=events.append,
        pre_submit_quote_reader=lambda ticker: _quote(now),
        clock=lambda: now,
    )
    trigger = evaluate_risk_exit_trigger(
        ticker="005930", cycle_id="cycle-cleared",
        decision=RiskDecision(RiskAction.SELL, kind),
    )
    candidate = evaluate_exit_candidate(trigger, _snapshot(orderable=3))

    with pytest.raises(MarketClosedError, match="EXIT_NO_LONGER_ACTIONABLE"):
        submit_exit(
            candidate,
            broker=broker,
            limit_price=Money(70_000.0, "KRW"),
            portfolio_refresh=lambda ticker: _snapshot(orderable=3),
            lease_guard=_Lease(sequence),
            cycle_snapshot_id="snapshot-current",
            origin_run_id="cycle-cleared",
            trigger_revalidator=lambda snapshot, quote: False,
        )

    assert adapter.post_attempts == 0
    assert "SUBMISSION_ATTEMPTED" not in [event.event_type.value for event in events]


def test_refreshed_risk_exit_posts_once_only_after_revalidation() -> None:
    sequence: list[str] = []
    adapter = _BoundaryAdapter(sequence)
    now = datetime(2026, 9, 4, 1, tzinfo=timezone.utc)
    broker = KISBroker(
        order_adapter=adapter,
        account=KisOrderAccount("12345678", "01"),
        market_clock=lambda: True,
        pre_submit_quote_reader=lambda ticker: _quote(now),
        clock=lambda: now,
    )
    trigger = evaluate_risk_exit_trigger(
        ticker="005930", cycle_id="cycle-live",
        decision=RiskDecision(RiskAction.SELL, "stop_loss"),
    )
    candidate = evaluate_exit_candidate(trigger, _snapshot(orderable=3))
    calls: list[str] = []

    order_id = submit_exit(
        candidate,
        broker=broker,
        limit_price=Money(70_000.0, "KRW"),
        portfolio_refresh=lambda ticker: _snapshot(orderable=3),
        lease_guard=_Lease(sequence),
        cycle_snapshot_id="snapshot-current",
        origin_run_id="cycle-live",
        trigger_revalidator=lambda snapshot, quote: calls.append("revalidated") or True,
    )

    assert order_id == "KIS-1"
    assert calls == ["revalidated"]
    assert adapter.post_attempts == 1
