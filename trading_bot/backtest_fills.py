"""Conservative opening-only limit fills; daily range touches are not fills."""
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from .backtest_costs import BPS, calculate_fill_costs, cost_profile, effective_rule, round_tick
from .backtest_inputs import latest_record
from .backtest_models import BacktestBundle, BacktestInputError, FillEvidence, OpenIntent

FILL_VERSION = 'opening-only-shared-participation-v1'


def opening_cutoff(session: date) -> datetime:
    return datetime.combine(session, datetime.min.time().replace(hour=9), ZoneInfo('Asia/Seoul'))


def model_session_fills(bundle: BacktestBundle, session: date, intents: tuple[OpenIntent, ...], profile_name: str) -> tuple[FillEvidence, ...]:
    profile = cost_profile(profile_name)
    cutoff = opening_cutoff(session)
    capacity = {}; results = []
    for intent in sorted(intents, key=lambda x: (x.decision_session, x.intent_id)):
        member = latest_record(bundle.membership, intent.ticker, session, cutoff)
        if member is None:
            raise BacktestInputError('FILL_MARKET_UNKNOWN')
        tax = effective_rule(bundle.cost_rules, member.market, session, cutoff)
        tick = effective_rule(bundle.tick_rules, member.market, session, cutoff)
        bar = next((b for b in bundle.bars if b.ticker == intent.ticker and b.session == session), None)
        status = latest_record(bundle.trading_status, intent.ticker, session, cutoff)
        reason = ''; quantity = 0; price = Decimal('0'); reference = bar.open if bar else Decimal('0')
        if session <= intent.decision_session or session < intent.eligible_session:
            reason = 'NOT_YET_ELIGIBLE'
        elif bar is None:
            reason = 'EXECUTION_BAR_UNKNOWN'
        elif status is None:
            reason = 'TRADING_STATUS_UNKNOWN'
        elif status.state != 'NORMAL':
            reason = 'NOT_TRADABLE'
        elif bar.volume == 0:
            reason = 'ZERO_VOLUME'
        elif (status.limit_lock or bar.high == bar.low) and not status.tradability_proof:
            reason = 'LIMIT_LOCK_UNPROVEN'
        else:
            multiplier = Decimal('1') + profile.slippage_bps/BPS if intent.side == 'BUY' else Decimal('1') - profile.slippage_bps/BPS
            price = round_tick(bar.open*multiplier, tick, 'ceil' if intent.side == 'BUY' else 'floor')
            limit = round_tick(intent.limit_price, tick, 'floor' if intent.side == 'BUY' else 'ceil')
            if not bar.low <= price <= bar.high:
                reason = 'ADVERSE_PRICE_OUTSIDE_BAR'
            elif (intent.side == 'BUY' and price > limit) or (intent.side == 'SELL' and price < limit):
                reason = 'OPENING_LIMIT_NOT_MET'
            else:
                capacity.setdefault(intent.ticker, int(Decimal(bar.volume)*profile.participation))
                quantity = min(intent.remaining_quantity, capacity[intent.ticker])
                capacity[intent.ticker] -= quantity
                reason = 'FILLED' if quantity == intent.remaining_quantity else ('PARTIAL' if quantity else 'CAPACITY_EXHAUSTED')
        if not quantity:
            price = Decimal('0')
        costs = calculate_fill_costs(intent.side, quantity, price, profile, tax)
        results.append(FillEvidence(intent_id=intent.intent_id, ticker=intent.ticker, side=intent.side, session=session,
                      quantity=quantity, reference_price=reference, executed_price=price,
                      commission=costs.commission, sell_tax=costs.sell_tax, surtax=costs.surtax,
                      slippage_drag=abs(price-reference)*quantity if quantity else Decimal('0'), reason=reason,
                      rule_ids=(tax.rule_id,tick.rule_id)))
    return tuple(results)
