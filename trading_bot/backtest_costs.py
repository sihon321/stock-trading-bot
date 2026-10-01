"""Date-effective reviewed market rules and labeled synthetic fee assumptions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from typing import Literal

from .backtest_models import BacktestBundle, BacktestInputError, CostRule, TickRule

ZERO = Decimal('0')
BPS = Decimal('10000')


@dataclass(frozen=True)
class CostProfile:
    name: Literal['baseline', 'stress']
    commission_bps: Decimal
    slippage_bps: Decimal
    participation: Decimal
    version: str = 'cost-profile-v1'
    rounding: str = 'KRW-1-ceiling-costs-v1'

    def document(self):
        return {'name': self.name, 'version': self.version, 'commission_bps': str(self.commission_bps),
                'slippage_bps': str(self.slippage_bps), 'participation': str(self.participation),
                'rounding': self.rounding, 'assumption': 'synthetic; not account-specific tariff'}


def cost_profile(name: str) -> CostProfile:
    if name == 'baseline':
        return CostProfile('baseline', Decimal('1.5'), Decimal('10'), Decimal('.01'))
    if name == 'stress':
        return CostProfile('stress', Decimal('3'), Decimal('25'), Decimal('.005'))
    raise BacktestInputError('UNSUPPORTED_PROFILE')


def effective_rule(rules, market: str, session: date, cutoff: datetime):
    found = [r for r in rules if r.market == market and r.effective_start <= session < r.effective_end and r.known_at <= cutoff and r.reviewed_at <= cutoff]
    if len(found) != 1:
        raise BacktestInputError('MARKET_RULE_COVERAGE_MISSING')
    return found[0]


def ceil_krw(value: Decimal) -> Decimal:
    return value.quantize(Decimal('1'), rounding=ROUND_CEILING)


@dataclass(frozen=True)
class FillCosts:
    commission: Decimal
    sell_tax: Decimal
    surtax: Decimal

    @property
    def total(self):
        return self.commission + self.sell_tax + self.surtax


def calculate_fill_costs(side: str, quantity: int, price: Decimal, profile: CostProfile, rule: CostRule) -> FillCosts:
    if side not in ('BUY', 'SELL') or isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0 or not price.is_finite() or price < 0:
        raise BacktestInputError('INVALID_FILL_COST_INPUT')
    notional = price * quantity
    return FillCosts(ceil_krw(notional*profile.commission_bps/BPS),
                     ceil_krw(notional*rule.sell_tax) if side == 'SELL' else ZERO,
                     ceil_krw(notional*rule.surtax) if side == 'SELL' else ZERO)


def round_tick(price: Decimal, rule: TickRule, direction: str) -> Decimal:
    """Round across date-effective bands to a valid positive zero-anchored grid."""
    if direction not in ('floor', 'ceil') or not price.is_finite() or price <= 0:
        raise BacktestInputError('INVALID_TICK_PRICE')
    candidates = []
    for band in rule.bands:
        rounding = ROUND_FLOOR if direction == 'floor' else ROUND_CEILING
        candidate = (price/band.tick).to_integral_value(rounding=rounding)*band.tick
        if direction == 'floor' and band.upper is not None and candidate >= band.upper:
            candidate = ((band.upper/band.tick).to_integral_value(rounding=ROUND_CEILING)-1)*band.tick
        if direction == 'ceil' and candidate < band.lower:
            candidate = (band.lower/band.tick).to_integral_value(rounding=ROUND_CEILING)*band.tick
        if candidate > 0 and band.lower <= candidate and (band.upper is None or candidate < band.upper):
            if (direction == 'floor' and candidate <= price) or (direction == 'ceil' and candidate >= price):
                candidates.append(candidate)
    if not candidates:
        raise BacktestInputError('PRICE_BELOW_VALID_TICK')
    return max(candidates) if direction == 'floor' else min(candidates)
