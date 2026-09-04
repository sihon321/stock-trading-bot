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
)
from trading_bot.portfolio import (
    PortfolioAccountSummary,
    PortfolioCompleteness,
    PortfolioHolding,
    PortfolioOrder,
    PortfolioSnapshot,
)
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
