"""Strict, account-scoped KIS portfolio truth contracts.

Only snapshots proven complete by every required GET-only query are eligible to
authorize a later mutation.  This module deliberately retains normalized scalar
facts only; account identifiers and raw provider mappings never enter the model.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Any, Iterable, Mapping, Sequence

from trading_bot.kis_order import KisOrderAccount
from trading_bot.soak_models import MockTrProfile, PageCompleteness


class PortfolioCompleteness(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    UNKNOWN = "UNKNOWN"


class DivergenceSeverity(StrEnum):
    WARNING = "WARNING"
    BLOCKING = "BLOCKING"


class EvaluationProvenance(StrEnum):
    HELD = "HELD"
    SCREENED = "SCREENED"


@dataclass(frozen=True)
class EvaluationTarget:
    ticker: str
    provenance: tuple[EvaluationProvenance, ...]


@dataclass(frozen=True)
class EvaluationUniverse:
    """One attributable daily target per ticker plus account-wide authority."""

    targets: tuple[EvaluationTarget, ...]
    executable: bool
    reason_code: str


@dataclass(frozen=True)
class HeldPositionContext:
    """Trusted normalized position facts rendered separately from market text."""

    average_price: float
    total_quantity: int
    orderable_quantity: int
    current_price: float
    unrealized_return: float
    open_sell_quantity: int


@dataclass(frozen=True)
class TickerEvidenceVerdict:
    """Pure per-target evidence decision; it never removes a daily target."""

    status: str
    decision: str
    reason_code: str
    executable: bool


@dataclass(frozen=True)
class PortfolioHolding:
    ticker: str
    total_quantity: int
    orderable_quantity: int
    average_price: float


@dataclass(frozen=True)
class PortfolioOrder:
    order_id: str
    original_order_id: str | None
    ticker: str
    side: str
    ordered_quantity: int
    filled_quantity: int
    remaining_quantity: int
    cancelled_quantity: int
    rejected_quantity: int
    limit_price: float
    status: str
    order_date: str
    order_time: str

    @property
    def terminal(self) -> bool:
        return self.status in {"FILLED", "CANCELLED", "EXPIRED", "REJECTED"}


@dataclass(frozen=True)
class PortfolioFill:
    fill_id: str
    order_id: str
    ticker: str
    quantity: int
    price: float


@dataclass(frozen=True)
class PortfolioAccountSummary:
    available_cash: float
    total_evaluation: float


@dataclass(frozen=True)
class PortfolioDivergence:
    code: str
    severity: DivergenceSeverity
    ticker: str | None = None
    order_intent_id: str | None = None


@dataclass(frozen=True)
class PortfolioSnapshot:
    snapshot_id: str
    account_scope_hash: str
    trading_date: date
    previous_trading_date: date
    observed_at: datetime
    completeness: PortfolioCompleteness
    reason_code: str
    daily_page_count: int
    balance_page_count: int
    holdings: tuple[PortfolioHolding, ...]
    orders: tuple[PortfolioOrder, ...]
    fills: tuple[PortfolioFill, ...]
    account: PortfolioAccountSummary
    divergences: tuple[PortfolioDivergence, ...] = ()

    @property
    def mutation_capable(self) -> bool:
        return (
            self.completeness is PortfolioCompleteness.COMPLETE
            and not any(
                item.severity is DivergenceSeverity.BLOCKING
                for item in self.divergences
            )
        )


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


def _text(row: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _side(value: Any) -> str:
    normalized = str(value or "").strip().upper()
    return {"01": "SELL", "02": "BUY"}.get(normalized, normalized or "UNKNOWN")


def _status(
    row: Mapping[str, Any], ordered: int, filled: int, remaining: int,
    cancelled: int, rejected: int,
) -> str:
    explicit = _text(row, "status", "ord_stat", "ord_stat_name").upper()
    aliases = {
        "CANCELED": "CANCELLED", "취소": "CANCELLED", "취소완료": "CANCELLED",
        "체결": "FILLED", "완료": "FILLED", "거부": "REJECTED", "거절": "REJECTED",
        "접수": "OPEN", "미체결": "NO_FILL", "부분체결": "PARTIAL",
    }
    explicit = aliases.get(explicit, explicit)
    valid = {"OPEN", "PARTIAL", "FILLED", "NO_FILL", "CANCELLED", "EXPIRED", "REJECTED"}
    arithmetic_ok = ordered == filled + remaining + cancelled + rejected
    if not arithmetic_ok or filled > ordered or remaining > ordered:
        return "UNKNOWN"
    inferred = (
        "FILLED" if ordered > 0 and filled == ordered
        else "REJECTED" if rejected > 0 and remaining == 0 and filled == 0
        else "CANCELLED" if cancelled > 0 and remaining == 0
        else "PARTIAL" if filled > 0 and remaining > 0
        else "NO_FILL" if filled == 0 and remaining > 0
        else "UNKNOWN"
    )
    if explicit in valid:
        compatible = {
            ("OPEN", "NO_FILL"), ("NO_FILL", "NO_FILL"),
            ("PARTIAL", "PARTIAL"), ("FILLED", "FILLED"),
            ("CANCELLED", "CANCELLED"), ("EXPIRED", "CANCELLED"),
            ("REJECTED", "REJECTED"),
        }
        return explicit if (explicit, inferred) in compatible else "UNKNOWN"
    return inferred


def _normalize_order(row: Mapping[str, Any]) -> PortfolioOrder | None:
    order_id = _text(row, "odno")
    ticker = _text(row, "pdno")
    ordered = _integer(row.get("ord_qty"))
    filled = _integer(row.get("tot_ccld_qty"))
    remaining = _integer(row.get("rmn_qty"))
    cancelled = _integer(row.get("cncl_cfrm_qty") or row.get("cncl_qty") or 0)
    rejected = _integer(row.get("rjct_qty") or 0)
    price = _number(row.get("ord_unpr"))
    if (
        not order_id or len(ticker) != 6 or not ticker.isdigit()
        or None in (ordered, filled, remaining, cancelled, rejected, price)
    ):
        return None
    return PortfolioOrder(
        order_id=order_id,
        original_order_id=_text(row, "orgn_odno", "orig_odno") or None,
        ticker=ticker,
        side=_side(row.get("sll_buy_dvsn_cd")),
        ordered_quantity=ordered,
        filled_quantity=filled,
        remaining_quantity=remaining,
        cancelled_quantity=cancelled,
        rejected_quantity=rejected,
        limit_price=price,
        status=_status(row, ordered, filled, remaining, cancelled, rejected),
        order_date=_text(row, "ord_dt"),
        order_time=_text(row, "ord_tmd"),
    )


def held_first_targets(
    held_tickers: Iterable[str], screened_tickers: Iterable[str]
) -> tuple[EvaluationTarget, ...]:
    held = tuple(dict.fromkeys(str(item) for item in held_tickers))
    screened = tuple(dict.fromkeys(str(item) for item in screened_tickers))
    screened_set = set(screened)
    result = [
        EvaluationTarget(
            ticker,
            (EvaluationProvenance.HELD, EvaluationProvenance.SCREENED)
            if ticker in screened_set else (EvaluationProvenance.HELD,),
        )
        for ticker in held
    ]
    held_set = set(held)
    result.extend(
        EvaluationTarget(ticker, (EvaluationProvenance.SCREENED,))
        for ticker in screened if ticker not in held_set
    )
    return tuple(result)


def build_evaluation_universe(
    snapshot: PortfolioSnapshot,
    screened_candidates: Iterable[Any],
) -> EvaluationUniverse:
    """Build a deterministic held-first union from authoritative broker truth.

    Holdings sort by ticker so provider row ordering cannot change evaluation
    identity. Screened-only candidates retain screener rank order. A candidate
    may be a ticker string or an object exposing a normalized ``ticker`` field;
    raw provider mappings are intentionally not accepted here.
    """

    held_tickers = tuple(sorted({holding.ticker for holding in snapshot.holdings}))
    screened_tickers: list[str] = []
    for candidate in screened_candidates:
        ticker = candidate if isinstance(candidate, str) else getattr(candidate, "ticker", "")
        ticker = str(ticker)
        if ticker and ticker not in screened_tickers:
            screened_tickers.append(ticker)
    executable = snapshot.mutation_capable
    return EvaluationUniverse(
        targets=held_first_targets(held_tickers, screened_tickers),
        executable=executable,
        reason_code="READY" if executable else "ACCOUNT_DATA_INCOMPLETE",
    )


def build_held_position_context(
    snapshot: PortfolioSnapshot,
    ticker: str,
    *,
    current_price: float,
) -> HeldPositionContext | None:
    """Return trusted held-position facts without retaining provider mappings."""

    holding = next(
        (item for item in snapshot.holdings if item.ticker == ticker),
        None,
    )
    if holding is None:
        return None
    open_sell_quantity = sum(
        order.remaining_quantity
        for order in snapshot.orders
        if order.ticker == ticker
        and order.side == "SELL"
        and not order.terminal
        and order.status in {"OPEN", "PARTIAL", "NO_FILL"}
    )
    unrealized_return = (
        (float(current_price) - holding.average_price) / holding.average_price
        if holding.average_price > 0
        else 0.0
    )
    return HeldPositionContext(
        average_price=holding.average_price,
        total_quantity=holding.total_quantity,
        orderable_quantity=holding.orderable_quantity,
        current_price=float(current_price),
        unrealized_return=unrealized_return,
        open_sell_quantity=open_sell_quantity,
    )


def evaluate_ticker_evidence(
    universe: EvaluationUniverse,
    target: EvaluationTarget,
    *,
    market_evidence_available: bool,
) -> TickerEvidenceVerdict:
    """Keep ticker-local market gaps attributable while preserving global block."""

    if target not in universe.targets:
        raise ValueError("target must belong to the evaluation universe")
    if not universe.executable:
        return TickerEvidenceVerdict(
            "DATA_INCOMPLETE", "HOLD", "ACCOUNT_DATA_INCOMPLETE", False
        )
    if not market_evidence_available:
        return TickerEvidenceVerdict(
            "DATA_INCOMPLETE", "HOLD", "MARKET_DATA_INCOMPLETE", False
        )
    return TickerEvidenceVerdict("READY", "HOLD", "READY", True)


def _matches_unresolved(order: PortfolioOrder, unresolved: Mapping[str, Any]) -> bool:
    broker_id = str(unresolved.get("broker_order_id") or "")
    if broker_id:
        return order.order_id == broker_id or order.original_order_id == broker_id
    return (
        order.ticker == str(unresolved.get("ticker") or "")
        and order.side == str(unresolved.get("side") or "").upper()
        and order.ordered_quantity == _integer(unresolved.get("quantity"))
    )


def collect_portfolio_snapshot(
    *,
    adapter: Any,
    account: KisOrderAccount,
    profile: MockTrProfile,
    trading_date: date,
    previous_trading_date: date,
    account_scope_hash: str,
    local_unresolved: Sequence[Mapping[str, Any]] = (),
    observed_at: datetime | None = None,
) -> PortfolioSnapshot:
    """Collect fresh whole-account truth using GET-only paginated inquiries."""

    daily = adapter.query_daily_ccld_pages(
        account=account, profile=profile,
        start_date=previous_trading_date, end_date=trading_date,
    )
    balance = adapter.query_balance_pages(account=account, profile=profile)
    all_rows = list(daily.rows)
    origin_page_count = 0
    query_incomplete = daily.completeness is not PageCompleteness.COMPLETE
    reasons = [f"DAILY_{daily.reason_code}", f"BALANCE_{balance.reason_code}"]

    for unresolved in local_unresolved:
        if any(
            _matches_unresolved(order, unresolved)
            for row in all_rows if (order := _normalize_order(row)) is not None
        ):
            continue
        origin = unresolved.get("origin_date")
        if not isinstance(origin, date):
            query_incomplete = True
            continue
        older = adapter.query_daily_ccld_pages(
            account=account, profile=profile, start_date=origin, end_date=origin,
            ticker=str(unresolved.get("ticker") or ""),
        )
        origin_page_count += older.page_count
        all_rows.extend(older.rows)
        if older.completeness is not PageCompleteness.COMPLETE:
            query_incomplete = True
            reasons.append(f"ORIGIN_{older.reason_code}")

    orders: list[PortfolioOrder] = []
    normalization_error = False
    conflict = False
    for row in all_rows:
        order = _normalize_order(row)
        if order is None:
            normalization_error = True
            continue
        conflict = conflict or order.status == "UNKNOWN"
        orders.append(order)

    holdings: list[PortfolioHolding] = []
    for row in balance.rows:
        ticker = _text(row, "pdno")
        total = _integer(row.get("hldg_qty"))
        orderable = _integer(row.get("ord_psbl_qty"))
        average = _number(row.get("pchs_avg_pric"))
        if len(ticker) != 6 or not ticker.isdigit() or None in (total, orderable, average):
            normalization_error = True
            continue
        holdings.append(PortfolioHolding(ticker, total, orderable, average))

    cash = _number(balance.summary.get("dnca_tot_amt"))
    total_evaluation = _number(balance.summary.get("tot_evlu_amt"))
    if cash is None or total_evaluation is None:
        normalization_error = True

    divergences: list[PortfolioDivergence] = []
    for unresolved in local_unresolved:
        matches = [order for order in orders if _matches_unresolved(order, unresolved)]
        if len(matches) != 1:
            divergences.append(
                PortfolioDivergence(
                    "UNATTRIBUTED_UNRESOLVED_ORDER",
                    DivergenceSeverity.BLOCKING,
                    str(unresolved.get("ticker") or "") or None,
                    str(unresolved.get("order_intent_id") or "") or None,
                )
            )

    fills = tuple(
        PortfolioFill(
            _text(row, "ccld_no") or f"{order.order_id}:aggregate",
            order.order_id,
            order.ticker,
            order.filled_quantity,
            _number(row.get("avg_prvs")) or order.limit_price,
        )
        for row in all_rows
        if (order := _normalize_order(row)) is not None and order.filled_quantity > 0
    )
    pages_complete = (
        not query_incomplete
        and balance.completeness is PageCompleteness.COMPLETE
    )
    if conflict or divergences:
        completeness = PortfolioCompleteness.UNKNOWN
        reason = "ORDER_TRUTH_UNKNOWN"
    elif not pages_complete or normalization_error:
        completeness = PortfolioCompleteness.INCOMPLETE
        reason = "|".join(reasons + (["NORMALIZATION_ERROR"] if normalization_error else []))
    else:
        completeness = PortfolioCompleteness.COMPLETE
        reason = "COMPLETE"

    safe_cash = cash if cash is not None else 0.0
    safe_total = total_evaluation if total_evaluation is not None else 0.0
    stamp = observed_at or datetime.now(timezone.utc)
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware")
    return PortfolioSnapshot(
        snapshot_id=str(uuid.uuid4()),
        account_scope_hash=account_scope_hash,
        trading_date=trading_date,
        previous_trading_date=previous_trading_date,
        observed_at=stamp,
        completeness=completeness,
        reason_code=reason,
        daily_page_count=daily.page_count + origin_page_count,
        balance_page_count=balance.page_count,
        holdings=tuple(sorted(holdings, key=lambda item: item.ticker)),
        orders=tuple(orders),
        fills=fills,
        account=PortfolioAccountSummary(safe_cash, safe_total),
        divergences=tuple(divergences),
    )


def canonical_account_scope_hash(mode: str, account_suffix: str) -> str:
    """Return a non-reversible account scope suitable for durable linkage."""

    payload = json.dumps([str(mode), str(account_suffix)], separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
