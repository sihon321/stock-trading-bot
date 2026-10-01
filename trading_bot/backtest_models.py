"""Strict, offline portfolio simulation contracts (no account capabilities)."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StrictInt, field_validator, model_validator


class BacktestInputError(ValueError):
    """Bounded public input error; never embeds source payloads."""


def decimal_value(value: object) -> Decimal:
    if not isinstance(value, (str, Decimal)):
        raise ValueError("decimal string required")
    try:
        number = Decimal(value)
    except Exception as exc:
        raise ValueError("invalid decimal") from exc
    if not number.is_finite() or abs(number) > Decimal('1e20') or number.as_tuple().exponent < -12:
        raise ValueError("decimal outside bounds")
    return number


Amount = Annotated[Decimal, BeforeValidator(decimal_value)]
Positive = Annotated[Amount, Field(gt=0)]
Nonnegative = Annotated[Amount, Field(ge=0)]
Symbol = Annotated[str, Field(pattern=r'^\d{6}$')]


class Frozen(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)

    @field_validator('*')
    @classmethod
    def aware_dates(cls, value):
        if isinstance(value, datetime):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError('aware timestamp required')
            return value.astimezone(timezone.utc)
        return value


class CoverageStatus(str, Enum):
    COMPLETE = 'COMPLETE'
    INCOMPLETE = 'INCOMPLETE'


class Session(Frozen):
    session: date
    close_at: datetime
    completed: bool = True

    @model_validator(mode='after')
    def matching_date(self):
        from zoneinfo import ZoneInfo
        if self.close_at.astimezone(ZoneInfo('Asia/Seoul')).date() != self.session:
            raise ValueError('session close mismatch')
        return self


class Bar(Frozen):
    ticker: Symbol
    session: date
    known_at: datetime
    open: Positive
    high: Positive
    low: Positive
    close: Positive
    volume: Annotated[StrictInt, Field(ge=0)]

    @model_validator(mode='after')
    def ohlc(self):
        if not self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high:
            raise ValueError('invalid OHLC range')
        return self


class Membership(Frozen):
    ticker: Symbol
    market: Literal['KOSPI', 'KOSDAQ']
    effective: date
    known_at: datetime
    ordinary: bool = True
    member: bool = True


class TradingStatus(Frozen):
    ticker: Symbol
    effective: date
    known_at: datetime
    state: Literal['NORMAL', 'SUSPENDED', 'HALTED', 'DELISTING', 'ADMIN_ISSUE'] = 'NORMAL'
    limit_lock: bool = False
    tradability_proof: bool = False


class CorporateAction(Frozen):
    action_id: Annotated[str, Field(min_length=1, max_length=100)]
    ticker: Symbol
    kind: Literal['SPLIT', 'DIVIDEND', 'DELIST']
    effective: date
    known_at: datetime
    ratio: Positive = Decimal('1')
    cash_per_share: Nonnegative | None = None
    payable_session: date | None = None
    disposition_price: Nonnegative | None = None
    fractional_cash_price: Nonnegative | None = None

    @model_validator(mode='after')
    def terms(self):
        if self.kind == 'DIVIDEND' and (self.cash_per_share is None or self.payable_session is None or self.payable_session < self.effective):
            raise ValueError('dividend net cash/payable terms required')
        return self


class FrozenSignal(Frozen):
    ticker: Symbol
    session: date
    known_at: datetime
    raw: Annotated[str, Field(max_length=8000)]


class Rule(Frozen):
    rule_id: Annotated[str, Field(min_length=1, max_length=100)]
    market: Literal['KOSPI', 'KOSDAQ']
    effective_start: date
    effective_end: date
    known_at: datetime
    source: Annotated[str, Field(min_length=1, max_length=500)]
    reviewed_at: datetime
    synthetic: bool = False

    @model_validator(mode='after')
    def interval(self):
        if self.effective_end <= self.effective_start:
            raise ValueError('empty rule interval')
        if not self.synthetic and not self.source.startswith('https://'):
            raise ValueError('reviewed source URL required')
        return self


class CostRule(Rule):
    sell_tax: Annotated[Nonnegative, Field(le=1)]
    surtax: Annotated[Nonnegative, Field(le=1)]


class TickBand(Frozen):
    lower: Nonnegative
    upper: Positive | None = None
    tick: Positive


class TickRule(Rule):
    bands: tuple[TickBand, ...]

    @model_validator(mode='after')
    def grid(self):
        if not self.bands or self.bands[0].lower != 0 or self.bands[-1].upper is not None:
            raise ValueError('tick bands must cover positive prices')
        for i, band in enumerate(self.bands):
            if band.upper is not None and band.upper <= band.lower:
                raise ValueError('invalid tick band')
            if i and self.bands[i-1].upper != band.lower:
                raise ValueError('tick gap/overlap')
        return self


class InitialPosition(Frozen):
    ticker: Symbol
    quantity: Annotated[StrictInt, Field(gt=0)]
    average_price: Positive
    known_at: datetime


class IndicatorPolicy(Frozen):
    sma_short_window: Annotated[StrictInt, Field(ge=2, le=500)] = 5
    sma_long_window: Annotated[StrictInt, Field(ge=2, le=500)] = 20
    rsi_window: Annotated[StrictInt, Field(ge=2, le=500)] = 14
    atr_window: Annotated[StrictInt, Field(ge=2, le=500)] = 14
    historical_volatility_window: Annotated[StrictInt, Field(ge=2, le=500)] = 20
    volume_ratio_window: Annotated[StrictInt, Field(ge=2, le=500)] = 20


class BacktestPolicy(Frozen):
    version: Literal['portfolio-policy-v1'] = 'portfolio-policy-v1'
    initial_cash: Nonnegative = Decimal('10000000')
    initial_positions: tuple[InitialPosition, ...] = ()
    universe_mode: Literal['POINT_IN_TIME', 'ALLOWLIST'] = 'POINT_IN_TIME'
    allowlist: tuple[Symbol, ...] = ()
    indicators: IndicatorPolicy = IndicatorPolicy()
    buy_confidence_threshold: Annotated[Nonnegative, Field(ge=Decimal('.8'), le=1)] = Decimal('.8')
    sell_confidence_threshold: Annotated[Nonnegative, Field(le=1)] = Decimal('.8')
    buy_cash_fraction: Annotated[Positive, Field(le=1)] = Decimal('.1')
    max_position_value: Positive = Decimal('1000000')
    stop_loss_pct: Annotated[Positive, Field(le=1)] = Decimal('.05')
    take_profit_pct: Annotated[Positive, Field(le=1)] = Decimal('.1')
    daily_loss_threshold: Nonnegative = Decimal('100000')
    max_candidates: Annotated[StrictInt, Field(ge=1, le=1000)] = 10
    min_trading_value: Nonnegative = Decimal('100000000')
    min_volume_ratio: Positive = Decimal('1.5')

    @model_validator(mode='after')
    def unique(self):
        if len({x.ticker for x in self.initial_positions}) != len(self.initial_positions):
            raise ValueError('duplicate initial position')
        if len(set(self.allowlist)) != len(self.allowlist) or (self.universe_mode == 'ALLOWLIST' and not self.allowlist):
            raise ValueError('invalid allowlist')
        return self


class Sources(Frozen):
    coverage_start: date
    coverage_end: date
    calendar_complete: bool
    membership_complete: bool
    corporate_actions_complete: bool
    source_hashes: tuple[Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')], ...]

    @model_validator(mode='after')
    def interval(self):
        if self.coverage_end < self.coverage_start or not self.source_hashes:
            raise ValueError('source coverage required')
        return self


class BenchmarkPoint(Frozen):
    session: date
    known_at: datetime
    close: Positive


class BacktestBundle(Frozen):
    schema_version: Literal[1]
    calendar: tuple[Session, ...]
    bars: tuple[Bar, ...]
    membership: tuple[Membership, ...]
    trading_status: tuple[TradingStatus, ...]
    corporate_actions: tuple[CorporateAction, ...]
    signals: tuple[FrozenSignal, ...]
    policy: BacktestPolicy
    cost_rules: tuple[CostRule, ...]
    tick_rules: tuple[TickRule, ...]
    benchmark: tuple[BenchmarkPoint, ...] = ()
    sources: Sources

    @model_validator(mode='after')
    def records(self):
        keys = {'calendar': lambda x: x.session, 'bars': lambda x: (x.ticker, x.session),
                'membership': lambda x: (x.ticker, x.effective, x.known_at),
                'trading_status': lambda x: (x.ticker, x.effective, x.known_at),
                'corporate_actions': lambda x: x.action_id, 'signals': lambda x: (x.ticker, x.session),
                'cost_rules': lambda x: x.rule_id, 'tick_rules': lambda x: x.rule_id,
                'benchmark': lambda x: x.session}
        for name, key in keys.items():
            records = getattr(self, name)
            if len(records) > 250000 or len({key(x) for x in records}) != len(records):
                raise ValueError('duplicate/excess records')
            object.__setattr__(self, name, tuple(sorted(records, key=key)))
        if not self.calendar or len(self.calendar) > 20000:
            raise ValueError('calendar required/bounded')
        sessions = {s.session: s for s in self.calendar}
        if any(x.session not in sessions for x in (*self.bars, *self.signals, *self.benchmark)):
            raise ValueError('observation outside calendar')
        if any(b.known_at < sessions[b.session].close_at for b in self.bars):
            raise ValueError('completed daily bar cannot be known before close')
        for name in ('cost_rules', 'tick_rules'):
            rules = getattr(self, name)
            for market in ('KOSPI', 'KOSDAQ'):
                ordered = sorted((r for r in rules if r.market == market), key=lambda r: r.effective_start)
                if any(a.effective_end > b.effective_start for a, b in zip(ordered, ordered[1:])):
                    raise ValueError('overlapping effective rules')
        return self


class OpenIntent(Frozen):
    intent_id: str
    ticker: Symbol
    side: Literal['BUY', 'SELL']
    quantity: Annotated[StrictInt, Field(gt=0)]
    remaining_quantity: Annotated[StrictInt, Field(ge=0)]
    limit_price: Positive
    decision_session: date
    eligible_session: date
    reserved_cash: Nonnegative = Decimal('0')
    reserved_quantity: Annotated[StrictInt, Field(ge=0)] = 0


class FillEvidence(Frozen):
    intent_id: str
    ticker: Symbol
    side: Literal['BUY', 'SELL']
    session: date
    quantity: Annotated[StrictInt, Field(ge=0)]
    reference_price: Nonnegative
    executed_price: Nonnegative
    commission: Nonnegative
    sell_tax: Nonnegative
    surtax: Nonnegative
    slippage_drag: Nonnegative
    reason: str
    rule_ids: tuple[str, ...] = ()


class HoldingEvidence(Frozen):
    ticker: Symbol
    quantity: Annotated[StrictInt, Field(gt=0)]
    average_price: Positive
    mark_price: Positive | None


class SessionEvidence(Frozen):
    session: date
    settled_cash: Nonnegative
    reserved_cash: Nonnegative
    pending_cash: Nonnegative
    holdings: tuple[HoldingEvidence, ...]
    net_equity: Amount | None
    gross_equity: Amount | None
    coverage_status: CoverageStatus
    unknowns: tuple[str, ...]
    realized_pnl: Amount
    unrealized_pnl: Amount | None
    action_cash: Amount


def canonical_bytes(value: BaseModel | dict) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode='json')
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')


def content_hash(value: BaseModel | dict) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()
