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
from datetime import date, datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

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
    connect_soak_store,
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


@dataclass(frozen=True)
class AmbiguityPolicy:
    version: str
    duration_seconds: int
    poll_seconds: int
    max_observations: int
    profile_version: str
    field_contract_version: str

    def __post_init__(self) -> None:
        if not self.version or not self.profile_version or not self.field_contract_version:
            raise ValueError("ambiguity policy versions are required")
        if self.duration_seconds <= 0 or self.poll_seconds <= 0 or self.max_observations <= 0:
            raise ValueError("ambiguity policy bounds must be positive")
        if self.poll_seconds > self.duration_seconds:
            raise ValueError("ambiguity poll cadence exceeds duration")


@dataclass(frozen=True)
class AmbiguousIntent:
    campaign_id: str
    run_id: str
    order_intent_id: str
    submission_id: str
    account_suffix: str
    ticker: str
    side: str
    quantity: int
    snapped_price: float
    submitted_at: datetime
    broker_order_id: str | None = None

    def __post_init__(self) -> None:
        if self.submitted_at.tzinfo is None or self.submitted_at.utcoffset() is None:
            raise ValueError("submitted_at must be timezone-aware")
        if self.quantity <= 0 or self.snapped_price <= 0:
            raise ValueError("ambiguous intent quantity and price must be positive")
        if len(self.account_suffix) != 4 or not self.account_suffix.isdigit():
            raise ValueError("account_suffix must contain exactly four digits")


@dataclass(frozen=True)
class ObservationWindow:
    started_at: datetime
    ended_at: datetime
    complete: bool

    def __post_init__(self) -> None:
        for value in (self.started_at, self.ended_at):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("observation window timestamps must be timezone-aware")
        if self.ended_at < self.started_at:
            raise ValueError("observation window end precedes start")


@dataclass(frozen=True)
class AmbiguityMatch:
    verdict: AmbiguityVerdict
    matched_order_ids: tuple[str, ...]
    remaining_order_terminal: bool
    reason_code: str


@dataclass(frozen=True)
class AmbiguityReconciliation:
    verdict: AmbiguityVerdict
    matched_order_id: str | None
    observation_ids: tuple[str, ...]
    reconciliation_complete: bool
    freeze_released: bool


@dataclass(frozen=True)
class RebuiltFreeze:
    freeze_id: str
    ticker: str
    order_intent_id: str | None
    freeze_kind: str
    reconciliation_complete: bool


@dataclass
class ReconciliationStores:
    """Owner-specific handles; the controller path is validated but never opened."""

    primary: sqlite3.Connection
    soak: sqlite3.Connection
    controller_db_path: Path

    def close(self) -> None:
        self.primary.close()
        self.soak.close()


def open_reconciliation_stores(
    primary_audit_db_path: str | Path,
    soak_db_path: str | Path,
    controller_db_path: str | Path,
) -> ReconciliationStores:
    """Open primary audit read-only and soak writable, leaving controller unopened."""

    from trading_bot.soak_config import validate_store_topology

    paths = validate_store_topology(
        Path(primary_audit_db_path), Path(soak_db_path), Path(controller_db_path)
    )
    primary_path = paths["primary_audit_db_path"]
    if not primary_path.is_file():
        raise FileNotFoundError(primary_path)
    primary = sqlite3.connect(f"file:{primary_path}?mode=ro", uri=True)
    try:
        primary.execute("PRAGMA query_only=ON")
        soak = connect_soak_store(paths["soak_db_path"])
    except Exception:
        primary.close()
        raise
    return ReconciliationStores(primary, soak, paths["controller_db_path"])


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
        and _number(balance.summary.get("dnca_tot_amt")) is not None
        and _number(balance.summary.get("tot_evlu_amt")) is not None
    )
    if complete:
        reason = "COMPLETE"
    elif (
        balance.completeness is PageCompleteness.COMPLETE
        and (
            _number(balance.summary.get("dnca_tot_amt")) is None
            or _number(balance.summary.get("tot_evlu_amt")) is None
        )
    ):
        reason = f"DAILY_{daily.reason_code}|BALANCE_SUMMARY_INCOMPLETE"
    else:
        reason = f"DAILY_{daily.reason_code}|BALANCE_{balance.reason_code}"
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
        order_missing = selected is None and order_id is not None

        def order_dimension(
            name: str, local_name: str, broker_value: Any, code: str
        ) -> ComparisonDimension:
            local_value = _value(local_evidence, local_name)
            if name == "order_state" and local_value is not None:
                local_value = str(local_value).upper()
            if order_missing and local_value is not None:
                return ComparisonDimension(
                    name, ComparisonState.MISMATCHED, local_value, None, "ORDER_NOT_FOUND"
                )
            return _dimension(
                name,
                local_value,
                broker_value,
                code,
                missing_code="ORDER_STATE_UNKNOWN" if name == "order_state" else "ORDER_NOT_FOUND",
            )

        dimensions = (
            order_dimension("requested_qty", "requested_qty", selected.ordered_qty if selected else None, "REQUESTED_QTY_CONTRADICTION"),
            order_dimension("filled_qty", "filled_qty", selected.filled_qty if selected else None, "FILLED_QTY_CONTRADICTION"),
            order_dimension("remaining_qty", "remaining_qty", selected.remaining_qty if selected else None, "REMAINING_QTY_CONTRADICTION"),
            order_dimension("order_state", "order_state", selected.status if selected else None, "ORDER_STATE_CONTRADICTION"),
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


def _order_observed_at(order: BrokerOrder) -> datetime | None:
    if len(order.order_date) != 8 or len(order.order_time) != 6:
        return None
    try:
        observed = datetime.strptime(
            order.order_date + order.order_time, "%Y%m%d%H%M%S"
        ).replace(tzinfo=ZoneInfo("Asia/Seoul"))
    except ValueError:
        return None
    return observed


def match_ambiguous_intent(
    intent: AmbiguousIntent,
    snapshot: BrokerSnapshot,
    window: ObservationWindow,
) -> AmbiguityMatch:
    """Return exact no/one/multiple cardinality without a first-match shortcut."""

    if snapshot.completeness is not PageCompleteness.COMPLETE or not window.complete:
        return AmbiguityMatch(
            AmbiguityVerdict.MULTIPLE_OR_INCONCLUSIVE,
            (),
            False,
            "INCOMPLETE_OBSERVATION_WINDOW",
        )
    if snapshot.account.account_suffix != intent.account_suffix:
        return AmbiguityMatch(
            AmbiguityVerdict.MULTIPLE_OR_INCONCLUSIVE,
            (),
            False,
            "ACCOUNT_SUFFIX_MISMATCH",
        )
    if intent.broker_order_id:
        matches = tuple(
            order for order in snapshot.orders if order.order_id == intent.broker_order_id
        )
        field_inconclusive = False
    else:
        matches_list: list[BrokerOrder] = []
        field_inconclusive = False
        for order in snapshot.orders:
            if (
                order.ticker != intent.ticker
                or order.side != intent.side.upper()
                or order.ordered_qty != intent.quantity
                or order.snapped_price != float(intent.snapped_price)
            ):
                continue
            observed_at = _order_observed_at(order)
            if observed_at is None:
                field_inconclusive = True
                continue
            if window.started_at <= observed_at <= window.ended_at:
                matches_list.append(order)
        matches = tuple(matches_list)
    ids = tuple(sorted(order.order_id for order in matches))
    if len(matches) == 1:
        return AmbiguityMatch(
            AmbiguityVerdict.ONE_MATCH_DETERMINATE,
            ids,
            matches[0].terminal,
            "ONE_STABLE_MATCH",
        )
    if len(matches) == 0 and not field_inconclusive:
        return AmbiguityMatch(
            AmbiguityVerdict.NO_MATCH_CONFIRMED,
            (),
            True,
            "COMPLETE_WINDOW_ZERO_MATCHES",
        )
    return AmbiguityMatch(
        AmbiguityVerdict.MULTIPLE_OR_INCONCLUSIVE,
        ids,
        False,
        "MULTIPLE_OR_MISSING_MATCH_FIELDS",
    )


def load_ambiguity_policy(
    conn: sqlite3.Connection,
    *,
    campaign_id: str,
    profile_version: str,
) -> AmbiguityPolicy:
    """Load the immutable campaign policy; runtime cadence overrides do not exist."""

    row = conn.execute(
        """SELECT ambiguity_policy_version,ambiguity_window_seconds,
                  ambiguity_poll_cadence_seconds,ambiguity_max_observations,
                  accepted_profile_version,field_contract_version
           FROM soak_campaigns WHERE campaign_id=?""",
        (campaign_id,),
    ).fetchone()
    if row is None:
        raise KeyError(campaign_id)
    policy = AmbiguityPolicy(
        version=str(row[0]),
        duration_seconds=int(row[1]),
        poll_seconds=int(row[2]),
        max_observations=int(row[3]),
        profile_version=str(row[4]),
        field_contract_version=str(row[5]),
    )
    if policy.profile_version != profile_version:
        raise ValueError("runtime profile differs from immutable campaign policy")
    return policy


def _persist_snapshot_only(conn: sqlite3.Connection, snapshot: BrokerSnapshot) -> None:
    append_snapshot(
        conn,
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
            "window_start": snapshot.window.start_date.isoformat(),
            "window_end": snapshot.window.end_date.isoformat(),
        },
        observed_at=snapshot.observed_at,
    )


def _active_freeze(
    conn: sqlite3.Connection, *, campaign_id: str, ticker: str, order_intent_id: str
) -> tuple[str, str] | None:
    row = conn.execute(
        """SELECT f.freeze_id,f.freeze_kind FROM soak_ticker_freezes f
           WHERE f.campaign_id=? AND f.ticker=? AND f.order_intent_id=?
             AND f.state='FROZEN' AND NOT EXISTS (
               SELECT 1 FROM soak_ticker_freezes r
               WHERE r.freeze_id=f.freeze_id AND r.state='RELEASED')
           ORDER BY f.id DESC LIMIT 1""",
        (campaign_id, ticker, order_intent_id),
    ).fetchone()
    return (str(row[0]), str(row[1])) if row is not None else None


def reconcile_ambiguous_submission(
    *,
    conn: sqlite3.Connection,
    adapter: Any,
    campaign: SnapshotCampaign,
    intent: AmbiguousIntent,
    query_window: SnapshotWindow,
    sleeper: Callable[[float], None] = time.sleep,
) -> AmbiguityReconciliation:
    """Run the campaign-frozen query cadence and append every GET observation."""

    if intent.campaign_id != campaign.campaign_id or intent.run_id != campaign.run_id:
        raise ValueError("ambiguity intent cross-IDs do not match campaign context")
    policy = load_ambiguity_policy(
        conn,
        campaign_id=campaign.campaign_id,
        profile_version=campaign.profile.version,
    )
    started_at = intent.submitted_at
    ended_at = started_at + timedelta(seconds=policy.duration_seconds)
    observation_window = ObservationWindow(started_at, ended_at, True)
    observations: list[tuple[str, AmbiguityMatch]] = []
    for index in range(policy.max_observations):
        snapshot = collect_broker_snapshot(
            adapter,
            campaign,
            ReconciliationStage.POST_SUBMISSION,
            query_window,
            {"order_ids": ((intent.broker_order_id,) if intent.broker_order_id else ()), "tickers": (intent.ticker,)},
        )
        _persist_snapshot_only(conn, snapshot)
        matched = match_ambiguous_intent(intent, snapshot, observation_window)
        observation_id = str(uuid.uuid4())
        append_ambiguity_observation(
            conn,
            observation_id=observation_id,
            campaign_id=campaign.campaign_id,
            run_id=campaign.run_id,
            ticker=intent.ticker,
            order_intent_id=intent.order_intent_id,
            verdict=matched.verdict,
            remaining_order_terminal=matched.remaining_order_terminal,
            detail={
                "snapshot_id": snapshot.snapshot_id,
                "observation_index": index + 1,
                "match_count": len(matched.matched_order_ids),
                "reason_code": matched.reason_code,
                "submission_id": intent.submission_id,
            },
        )
        observations.append((observation_id, matched))
        if index + 1 < policy.max_observations:
            sleeper(policy.poll_seconds)

    verdicts = {item.verdict for _, item in observations}
    one_ids = {
        item.matched_order_ids[0]
        for _, item in observations
        if item.verdict is AmbiguityVerdict.ONE_MATCH_DETERMINATE
        and len(item.matched_order_ids) == 1
    }
    if verdicts == {AmbiguityVerdict.NO_MATCH_CONFIRMED}:
        final_verdict = AmbiguityVerdict.NO_MATCH_CONFIRMED
        matched_order_id = None
        final_terminal = True
    elif verdicts == {AmbiguityVerdict.ONE_MATCH_DETERMINATE} and len(one_ids) == 1:
        final_verdict = AmbiguityVerdict.ONE_MATCH_DETERMINATE
        matched_order_id = next(iter(one_ids))
        final_terminal = all(item.remaining_order_terminal for _, item in observations)
    else:
        final_verdict = AmbiguityVerdict.MULTIPLE_OR_INCONCLUSIVE
        matched_order_id = None
        final_terminal = False
    freeze_released = False
    active = _active_freeze(
        conn,
        campaign_id=campaign.campaign_id,
        ticker=intent.ticker,
        order_intent_id=intent.order_intent_id,
    )
    if (
        active is not None
        and final_verdict is not AmbiguityVerdict.MULTIPLE_OR_INCONCLUSIVE
        and final_terminal
    ):
        transition_freeze(
            conn,
            freeze_id=active[0],
            release_evidence_type="AMBIGUITY_OBSERVATION",
            release_evidence_id=observations[-1][0],
            detail={"reason_code": "DETERMINATE_TERMINAL_BROKER_TRUTH"},
        )
        freeze_released = True
    return AmbiguityReconciliation(
        verdict=final_verdict,
        matched_order_id=matched_order_id,
        observation_ids=tuple(item[0] for item in observations),
        reconciliation_complete=(
            final_verdict is not AmbiguityVerdict.MULTIPLE_OR_INCONCLUSIVE
        ),
        freeze_released=freeze_released,
    )


def rebuild_ticker_freezes(
    store: sqlite3.Connection | object, campaign_id: str
) -> dict[str, RebuiltFreeze]:
    """Reconstruct active freezes from append-only transitions after restart."""

    conn = store if isinstance(store, sqlite3.Connection) else getattr(store, "conn")
    state = load_campaign_state(conn, campaign_id=campaign_id)
    rebuilt: dict[str, RebuiltFreeze] = {}
    for row in state["active_freezes"]:
        ticker = str(row["ticker"])
        complete = conn.execute(
            """SELECT 1 FROM soak_comparisons
               WHERE campaign_id=? AND ticker=? AND order_intent_id=?
                 AND verdict='MATCHED' AND remaining_order_terminal=1
               ORDER BY id DESC LIMIT 1""",
            (campaign_id, ticker, row["order_intent_id"]),
        ).fetchone() is not None
        rebuilt[ticker] = RebuiltFreeze(
            freeze_id=str(row["freeze_id"]),
            ticker=ticker,
            order_intent_id=row["order_intent_id"],
            freeze_kind=str(row["freeze_kind"]),
            reconciliation_complete=complete,
        )
    return rebuilt


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
