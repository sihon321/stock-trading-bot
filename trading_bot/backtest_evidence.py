"""Pure saved backtest DTOs and checked numeric bridge, without evaluation."""
from __future__ import annotations

import math
from datetime import date
from decimal import Decimal

from .backtest_models import (
    Amount, Bar, BenchmarkPoint, CorporateAction, CostRule, TickRule, Session,
    BacktestInputError, CoverageStatus, FillEvidence, Frozen, OpenIntent,
    SessionEvidence,
)

class DecisionEvidence(Frozen):
    session: date
    ticker: str
    action: str
    reason: str
    selected: bool
    risk_override: bool
    intent_id: str | None = None
    quantity: int = 0


class BacktestRun(Frozen):
    manifest: dict
    calendar: tuple[Session, ...]
    corporate_actions: tuple[CorporateAction, ...]
    cost_rules: tuple[CostRule, ...]
    tick_rules: tuple[TickRule, ...]
    benchmark: tuple[BenchmarkPoint, ...]
    intents: tuple[OpenIntent, ...]
    sessions: tuple[SessionEvidence, ...]
    fills: tuple[FillEvidence, ...]
    decisions: tuple[DecisionEvidence, ...]
    expiries: tuple[dict, ...]
    cash_events: tuple[dict, ...]
    open_intents: tuple[OpenIntent, ...]
    initial_marks: tuple[Bar, ...]
    initial_equity: Amount | None
    final_coverage: CoverageStatus
    limitations: tuple[str, ...]


def checked_float(value: Decimal) -> float:
    number = float(value)
    if not math.isfinite(number) or abs(Decimal(str(number))-value) > max(Decimal('.00000001'),abs(value)*Decimal('1e-15')):
        raise BacktestInputError('UNSAFE_POLICY_FLOAT_BRIDGE')
    return number
