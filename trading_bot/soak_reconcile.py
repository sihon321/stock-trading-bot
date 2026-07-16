"""Query-only KIS mock broker-truth reconciliation.

The service in this module intentionally has no order-submission capability.
KIS account inquiries may use the adapter's bounded retry policy, while every
reconciliation path remains GET-only and persists normalized campaign-scoped
facts before changing a durable ticker freeze.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from trading_bot.kis_order import KisOrderAccount
from trading_bot.soak_models import (
    AmbiguityVerdict,
    MockTrProfile,
    PageCompleteness,
    ReconciliationStage,
    ReconciliationVerdict,
)
from trading_bot.soak_store import (
    append_ambiguity_observation,
    append_comparison,
    append_snapshot,
    freeze_ticker,
    latch_safety_failure,
    load_campaign_state,
    transition_freeze,
)


_TERMINAL_STATES = {"FILLED", "CANCELLED", "REJECTED", "EXPIRED"}


def _value(source: Mapping[str, Any] | object, name: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def _integer(value: Any) -> int | None:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _number(value: Any) -> float | None:
    try:
        parsed = float(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _stage(value: ReconciliationStage | str) -> ReconciliationStage:
    normalized = str(value).upper()
    if normalized == "PRE_FINALIZATION":
        normalized = "PRE_FINALIZE"
    return ReconciliationStage(normalized)


@dataclass(frozen=True)
class SnapshotWindow:
    start_date: date
    end_date: date

    def __post_init__(self) -> None:
        if self.end_date < self.start_date:
            raise ValueError("snapshot window end must not precede start")


@dataclass(frozen=True)
class SnapshotCampaign:
    campaign_id: str
    run_id: str
    account: KisOrderAccount
    account_suffix: str
    profile: MockTrProfile

    def __post_init__(self) -> None:
        if not self.campaign_id or not self.run_id:
            raise ValueError("campaign_id and run_id are required")
        if len(self.account_suffix) != 4 or not self.account_suffix.isdigit():
            raise ValueError("account_suffix must contain exactly four digits")


@dataclass(frozen=True)
class BrokerOrder:
    observation_id: str
    order_id: str
    ticker: str
    side: str
    ordered_qty: int
    filled_qty: int
    remaining_qty: int
    snapped_price: float
    status: str
    order_date: str = ""
    order_time: str = ""
    broker_orgno: str = ""

    @property
    def terminal(self) -> bool:
        return self.status in _TERMINAL_STATES


@dataclass(frozen=True)
class BrokerFill:
    observation_id: str
    order_id: str
    fill_id: str
    ticker: str
    quantity: int
    price: float


@dataclass(frozen=True)
class BrokerHolding:
    observation_id: str
    ticker: str
    quantity: int
    available_quantity: int
    average_price: float


@dataclass(frozen=True)
class BrokerAccountSummary:
    observation_id: str
    account_suffix: str
    available_cash: float | None
    total_value: float | None


@dataclass(frozen=True)
class BrokerSnapshot:
    snapshot_id: str
    campaign_id: str
    run_id: str
    stage: ReconciliationStage
    window: SnapshotWindow
    completeness: PageCompleteness
    reason_code: str
    daily_page_count: int
    balance_page_count: int
    orders: tuple[BrokerOrder, ...]
    fills: tuple[BrokerFill, ...]
    holdings: tuple[BrokerHolding, ...]
    account: BrokerAccountSummary
    observed_at: str

    @classmethod
    def from_normalized(
        cls,
        *,
        snapshot_id: str,
        campaign: SnapshotCampaign,
        stage: ReconciliationStage | str,
        window: SnapshotWindow,
        orders: Sequence[Mapping[str, Any]] = (),
        fills: Sequence[Mapping[str, Any]] = (),
        holdings: Sequence[Mapping[str, Any]] = (),
        account: Mapping[str, Any] | None = None,
        completeness: PageCompleteness = PageCompleteness.COMPLETE,
        reason_code: str = "COMPLETE",
        daily_page_count: int = 1,
        balance_page_count: int = 1,
        observed_at: str | None = None,
    ) -> "BrokerSnapshot":
        normalized_orders = tuple(
            BrokerOrder(
                observation_id=str(row.get("observation_id") or f"{snapshot_id}:order:{index}"),
                order_id=str(row.get("order_id") or ""),
                ticker=str(row.get("ticker") or ""),
                side=str(row.get("side") or "UNKNOWN"),
                ordered_qty=int(row.get("ordered_qty") or 0),
                filled_qty=int(row.get("filled_qty") or 0),
                remaining_qty=int(row.get("remaining_qty") or 0),
                snapped_price=float(row.get("snapped_price") or 0),
                status=str(row.get("status") or "UNKNOWN").upper(),
                order_date=str(row.get("order_date") or ""),
                order_time=str(row.get("order_time") or ""),
                broker_orgno=str(row.get("broker_orgno") or ""),
            )
            for index, row in enumerate(orders)
        )
        normalized_fills = tuple(
            BrokerFill(
                observation_id=str(row.get("observation_id") or f"{snapshot_id}:fill:{index}"),
                order_id=str(row.get("order_id") or ""),
                fill_id=str(row.get("fill_id") or f"{row.get('order_id', '')}:{index}"),
                ticker=str(row.get("ticker") or ""),
                quantity=int(row.get("quantity") or 0),
                price=float(row.get("price") or 0),
            )
            for index, row in enumerate(fills)
        )
        normalized_holdings = tuple(
            BrokerHolding(
                observation_id=str(row.get("observation_id") or f"{snapshot_id}:holding:{index}"),
                ticker=str(row.get("ticker") or ""),
                quantity=int(row.get("quantity") or 0),
                available_quantity=int(row.get("available_quantity") or 0),
                average_price=float(row.get("average_price") or 0),
            )
            for index, row in enumerate(holdings)
        )
        account_values = dict(account or {})
        normalized_account = BrokerAccountSummary(
            observation_id=str(account_values.get("observation_id") or f"{snapshot_id}:account:0"),
            account_suffix=str(account_values.get("account_suffix") or campaign.account_suffix),
            available_cash=_number(account_values.get("available_cash")),
            total_value=_number(account_values.get("total_value")),
        )
        return cls(
            snapshot_id=snapshot_id,
            campaign_id=campaign.campaign_id,
            run_id=campaign.run_id,
            stage=_stage(stage),
            window=window,
            completeness=PageCompleteness(completeness),
            reason_code=reason_code,
            daily_page_count=daily_page_count,
            balance_page_count=balance_page_count,
            orders=normalized_orders,
            fills=normalized_fills,
            holdings=normalized_holdings,
            account=normalized_account,
            observed_at=observed_at or datetime.now(timezone.utc).isoformat(),
        )


class ComparisonState(StrEnum):
    MATCHED = "MATCHED"
    MISMATCHED = "MISMATCHED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ComparisonDimension:
    name: str
    state: ComparisonState
    local_value: str | int | float | None
    broker_value: str | int | float | None
    code: str


@dataclass(frozen=True)
class BrokerComparison:
    comparison_id: str
    campaign_id: str
    run_id: str
    snapshot_id: str
    ticker: str | None
    order_intent_id: str | None
    verdict: ReconciliationVerdict
    dimensions: tuple[ComparisonDimension, ...]
    remaining_order_terminal: bool

    @property
    def complete(self) -> bool:
        return all(item.state is not ComparisonState.UNKNOWN for item in self.dimensions)


def _side(value: Any) -> str:
    normalized = str(value or "").strip().upper()
    return {"01": "SELL", "02": "BUY"}.get(normalized, normalized or "UNKNOWN")


def _order_status(row: Mapping[str, Any], ordered: int, filled: int, remaining: int) -> str:
    explicit = str(
        row.get("status") or row.get("ord_stat") or row.get("ord_stat_name") or ""
    ).strip().upper()
    if explicit in _TERMINAL_STATES | {"PARTIAL", "NO_FILL", "OPEN"}:
        return explicit
    if remaining == 0 and filled >= ordered and ordered > 0:
        return "FILLED"
    if filled > 0 and remaining > 0:
        return "PARTIAL"
    if filled == 0 and remaining > 0:
        return "NO_FILL"
    return "UNKNOWN"


def _touched(touched_refs: Mapping[str, Iterable[str]] | object) -> tuple[set[str], set[str]]:
    ids = _value(touched_refs, "order_ids", ())
    tickers = _value(touched_refs, "tickers", ())
    return {str(value) for value in ids}, {str(value) for value in tickers}


def collect_broker_snapshot(
    adapter: Any,
    campaign: SnapshotCampaign,
    stage: ReconciliationStage | str,
    window: SnapshotWindow,
    touched_refs: Mapping[str, Iterable[str]] | object,
) -> BrokerSnapshot:
    """Collect complete paginated GET-only truth and discard unrelated rows."""

    daily = adapter.query_daily_ccld_pages(
        account=campaign.account,
        profile=campaign.profile,
        start_date=window.start_date,
        end_date=window.end_date,
    )
    balance = adapter.query_balance_pages(account=campaign.account, profile=campaign.profile)
    snapshot_id = str(uuid.uuid4())
    order_ids, tickers = _touched(touched_refs)
    orders: list[dict[str, Any]] = []
    fills: list[dict[str, Any]] = []
    for row in daily.rows:
        order_id = str(row.get("odno") or "").strip()
        ticker = str(row.get("pdno") or "").strip()
        if order_id not in order_ids and ticker not in tickers:
            continue
        ordered = _integer(row.get("ord_qty"))
        filled = _integer(row.get("tot_ccld_qty"))
        remaining = _integer(row.get("rmn_qty"))
        if ordered is None or filled is None or remaining is None:
            daily = type(daily)(
                rows=daily.rows,
                summary=daily.summary,
                page_count=daily.page_count,
                completeness=PageCompleteness.INCOMPLETE,
                reason_code="NORMALIZATION_ERROR",
            )
            continue
        status = _order_status(row, ordered, filled, remaining)
        orders.append(
            {
                "order_id": order_id,
                "ticker": ticker,
                "side": _side(row.get("sll_buy_dvsn_cd")),
                "ordered_qty": ordered,
                "filled_qty": filled,
                "remaining_qty": remaining,
                "snapped_price": _number(row.get("ord_unpr")) or 0,
                "status": status,
                "order_date": str(row.get("ord_dt") or ""),
                "order_time": str(row.get("ord_tmd") or ""),
                "broker_orgno": str(row.get("ord_gno_brno") or ""),
            }
        )
        if filled > 0:
            fills.append(
                {
                    "order_id": order_id,
                    "fill_id": str(row.get("ccld_no") or f"{order_id}:aggregate"),
                    "ticker": ticker,
                    "quantity": filled,
                    "price": _number(row.get("avg_prvs")) or _number(row.get("ord_unpr")) or 0,
                }
            )
    holdings: list[dict[str, Any]] = []
    for row in balance.rows:
        ticker = str(row.get("pdno") or "").strip()
        if ticker not in tickers:
            continue
        quantity = _integer(row.get("hldg_qty"))
        available = _integer(row.get("ord_psbl_qty"))
        average = _number(row.get("pchs_avg_pric"))
        if quantity is None or available is None or average is None:
            balance = type(balance)(
                rows=balance.rows,
                summary=balance.summary,
                page_count=balance.page_count,
                completeness=PageCompleteness.INCOMPLETE,
                reason_code="NORMALIZATION_ERROR",
            )
            continue
        holdings.append(
            {
                "ticker": ticker,
                "quantity": quantity,
                "available_quantity": available,
                "average_price": average,
            }
        )
    complete = (
        daily.completeness is PageCompleteness.COMPLETE
        and balance.completeness is PageCompleteness.COMPLETE
    )
    reason = "COMPLETE" if complete else f"DAILY_{daily.reason_code}|BALANCE_{balance.reason_code}"
    return BrokerSnapshot.from_normalized(
        snapshot_id=snapshot_id,
        campaign=campaign,
        stage=stage,
        window=window,
        orders=orders,
        fills=fills,
        holdings=holdings,
        account={
            "account_suffix": campaign.account_suffix,
            "available_cash": balance.summary.get("dnca_tot_amt"),
            "total_value": balance.summary.get("tot_evlu_amt"),
        },
        completeness=PageCompleteness.COMPLETE if complete else PageCompleteness.INCOMPLETE,
        reason_code=reason,
        daily_page_count=daily.page_count,
        balance_page_count=balance.page_count,
    )


def _dimension(
    name: str,
    local_value: Any,
    broker_value: Any,
    contradiction_code: str,
    *,
    missing_code: str,
) -> ComparisonDimension:
    if local_value is None or broker_value is None:
        return ComparisonDimension(name, ComparisonState.UNKNOWN, local_value, broker_value, missing_code)
    if local_value == broker_value:
        return ComparisonDimension(name, ComparisonState.MATCHED, local_value, broker_value, "MATCHED")
    return ComparisonDimension(
        name, ComparisonState.MISMATCHED, local_value, broker_value, contradiction_code
    )


def compare_broker_truth(
    local_evidence: Mapping[str, Any] | object, snapshot: BrokerSnapshot
) -> BrokerComparison:
    """Compare independent dimensions without turning unavailable truth into mismatch."""

    ticker = _value(local_evidence, "ticker")
    order_id = _value(local_evidence, "order_id") or _value(local_evidence, "broker_order_id")
    selected = next((item for item in snapshot.orders if item.order_id == order_id), None)
    if selected is None and ticker is not None:
        candidates = tuple(item for item in snapshot.orders if item.ticker == ticker)
        if len(candidates) == 1:
            selected = candidates[0]
    if snapshot.completeness is not PageCompleteness.COMPLETE:
        dimensions = tuple(
            ComparisonDimension(name, ComparisonState.UNKNOWN, _value(local_evidence, local), None, "BROKER_SNAPSHOT_INCOMPLETE")
            for name, local in (
                ("requested_qty", "requested_qty"), ("filled_qty", "filled_qty"),
                ("remaining_qty", "remaining_qty"), ("order_state", "order_state"),
                ("holding_quantity", "holding_quantity"), ("available_cash", "available_cash"),
            )
        )
        verdict = ReconciliationVerdict.UNKNOWN
        terminal = False
    else:
        holding = next((item for item in snapshot.holdings if item.ticker == ticker), None)
        dimensions = (
            _dimension("requested_qty", _value(local_evidence, "requested_qty"), selected.ordered_qty if selected else None, "REQUESTED_QTY_CONTRADICTION", missing_code="ORDER_NOT_FOUND"),
            _dimension("filled_qty", _value(local_evidence, "filled_qty"), selected.filled_qty if selected else None, "FILLED_QTY_CONTRADICTION", missing_code="ORDER_NOT_FOUND"),
            _dimension("remaining_qty", _value(local_evidence, "remaining_qty"), selected.remaining_qty if selected else None, "REMAINING_QTY_CONTRADICTION", missing_code="ORDER_NOT_FOUND"),
            _dimension("order_state", str(_value(local_evidence, "order_state") or "").upper() or None, selected.status if selected else None, "ORDER_STATE_CONTRADICTION", missing_code="ORDER_STATE_UNKNOWN"),
            _dimension("holding_quantity", _value(local_evidence, "holding_quantity"), holding.quantity if holding else 0 if ticker else None, "HOLDING_QTY_CONTRADICTION", missing_code="HOLDING_UNKNOWN"),
            _dimension("available_cash", _number(_value(local_evidence, "available_cash")), snapshot.account.available_cash, "AVAILABLE_CASH_CONTRADICTION", missing_code="AVAILABLE_CASH_UNKNOWN"),
        )
        if any(item.state is ComparisonState.MISMATCHED for item in dimensions):
            verdict = ReconciliationVerdict.MISMATCHED
        elif any(item.state is ComparisonState.UNKNOWN for item in dimensions):
            verdict = ReconciliationVerdict.UNKNOWN
        else:
            verdict = ReconciliationVerdict.MATCHED
        terminal = bool(selected and selected.terminal)
    return BrokerComparison(
        comparison_id=str(uuid.uuid4()),
        campaign_id=snapshot.campaign_id,
        run_id=snapshot.run_id,
        snapshot_id=snapshot.snapshot_id,
        ticker=str(ticker) if ticker is not None else None,
        order_intent_id=_value(local_evidence, "order_intent_id"),
        verdict=verdict,
        dimensions=dimensions,
        remaining_order_terminal=terminal,
    )


def _comparison_detail(comparison: BrokerComparison) -> dict[str, Any]:
    detail: dict[str, Any] = {"dimension_count": len(comparison.dimensions)}
    for item in comparison.dimensions:
        prefix = item.name.lower()
        detail[f"{prefix}_state"] = item.state.value
        detail[f"{prefix}_code"] = item.code
        detail[f"{prefix}_local"] = item.local_value
        detail[f"{prefix}_broker"] = item.broker_value
    return detail


def persist_reconciliation(
    conn: sqlite3.Connection, snapshot: BrokerSnapshot, comparison: BrokerComparison
) -> tuple[str, str]:
    """Append snapshot and comparison before applying the irreversible D-09 latch."""

    append_snapshot(
        conn,
        snapshot_id=snapshot.snapshot_id,
        campaign_id=snapshot.campaign_id,
        run_id=snapshot.run_id,
        stage=snapshot.stage,
        ticker=comparison.ticker,
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
            "window_start": snapshot.window.start_date.isoformat(),
            "window_end": snapshot.window.end_date.isoformat(),
        },
        observed_at=snapshot.observed_at,
    )
    append_comparison(
        conn,
        comparison_id=comparison.comparison_id,
        campaign_id=comparison.campaign_id,
        snapshot_id=comparison.snapshot_id,
        run_id=comparison.run_id,
        ticker=comparison.ticker,
        order_intent_id=comparison.order_intent_id,
        verdict=comparison.verdict,
        remaining_order_terminal=comparison.remaining_order_terminal,
        detail=_comparison_detail(comparison),
    )
    if comparison.verdict is ReconciliationVerdict.MISMATCHED:
        latch_safety_failure(
            conn,
            campaign_id=comparison.campaign_id,
            reason_code="D09_BROKER_TRUTH_CONTRADICTION",
            run_id=comparison.run_id,
            ticker=comparison.ticker,
            order_intent_id=comparison.order_intent_id,
        )
    return snapshot.snapshot_id, comparison.comparison_id


def load_local_order_evidence(
    primary_conn: sqlite3.Connection, *, order_intent_id: str
) -> dict[str, Any]:
    """Read one immutable order origin from the primary audit owner."""

    primary_conn.row_factory = sqlite3.Row
    rows = list(
        primary_conn.execute(
            "SELECT * FROM order_events WHERE order_intent_id=? ORDER BY id",
            (order_intent_id,),
        )
    )
    if not rows:
        raise KeyError(order_intent_id)
    origins = {str(row["origin_run_id"]) for row in rows}
    tickers = {str(row["ticker"]) for row in rows}
    if len(origins) != 1 or len(tickers) != 1:
        raise ValueError("primary order origin is contradictory")
    latest = rows[-1]
    detail: dict[str, Any] = {}
    for row in rows:
        try:
            detail.update(json.loads(row["detail_json"] or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            raise ValueError("primary order detail is malformed") from None
    return {
        "campaign_id": detail.get("campaign_id"),
        "run_id": next(iter(origins)),
        "ticker": next(iter(tickers)),
        "order_intent_id": order_intent_id,
        "order_id": latest["broker_order_id"],
        "requested_qty": latest["requested_qty"],
        "filled_qty": latest["filled_qty"],
        "remaining_qty": latest["unfilled_qty"],
        "order_state": latest["broker_status"],
        "submission_id": latest["submission_id"],
    }

