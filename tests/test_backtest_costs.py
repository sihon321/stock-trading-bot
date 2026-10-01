from datetime import date, datetime, timezone
from decimal import Decimal as D
import pytest
from trading_bot.backtest_costs import cost_profile, calculate_fill_costs, effective_rule, round_tick
from trading_bot.backtest_models import BacktestBundle, BacktestInputError, TickBand
from test_backtest_inputs import raw_bundle


def test_cost_components_and_assumptions():
    b=BacktestBundle.model_validate(raw_bundle()); r=b.cost_rules[0]; p=cost_profile('baseline')
    buy=calculate_fill_costs('BUY',100,D('100'),p,r)
    sell=calculate_fill_costs('SELL',100,D('100'),p,r)
    assert (buy.commission,buy.sell_tax,buy.surtax)==(D('2'),D('0'),D('0'))
    assert (sell.commission,sell.sell_tax,sell.surtax)==(D('2'),D('10'),D('5'))
    assert cost_profile('stress').participation==D('.005')
    assert 'not account-specific' in p.document()['assumption']


def test_effective_boundary_and_unknown_review():
    b=BacktestBundle.model_validate(raw_bundle());r=b.cost_rules[0]; dt=datetime(2023,1,1,tzinfo=timezone.utc)
    assert effective_rule(b.cost_rules,r.market,date(2023,1,1),dt)==r
    with pytest.raises(BacktestInputError): effective_rule(b.cost_rules,r.market,r.effective_end,dt)
    with pytest.raises(BacktestInputError): effective_rule((r.model_copy(update={'reviewed_at':datetime(2024,1,1,tzinfo=timezone.utc)}),),r.market,date(2023,1,1),dt)


def test_tick_cross_band_side_aware_rounding():
    r=BacktestBundle.model_validate(raw_bundle()).tick_rules[0].model_copy(update={'bands':(TickBand(lower=D('0'),upper=D('100'),tick=D('1')),TickBand(lower=D('100'),tick=D('5')))})
    assert round_tick(D('101'),r,'floor')==D('100')
    assert round_tick(D('101'),r,'ceil')==D('105')
    assert round_tick(D('99.5'),r,'ceil')==D('100')

@pytest.mark.parametrize('side,q,p',[('BAD',1,D('1')),('BUY',True,D('1')),('SELL',-1,D('1')),('BUY',1,D('NaN'))])
def test_invalid_cost_input(side,q,p):
    r=BacktestBundle.model_validate(raw_bundle()).cost_rules[0]
    with pytest.raises(BacktestInputError): calculate_fill_costs(side,q,p,cost_profile('baseline'),r)
