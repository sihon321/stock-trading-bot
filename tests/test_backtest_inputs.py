import copy
import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from trading_bot.backtest_models import BacktestBundle, content_hash

FIXTURE=Path(__file__).parent/'fixtures/backtest/chronological.json'

def raw_bundle():
    return json.loads(FIXTURE.read_text())


def test_strict_normalization_and_shuffled_records():
    raw=raw_bundle(); first=BacktestBundle.model_validate(raw)
    for key in ['calendar','bars','membership','signals','cost_rules']:
        raw[key].reverse()
    assert content_hash(first)==content_hash(BacktestBundle.model_validate(raw))

@pytest.mark.parametrize('mutation',[
    lambda b:b.update(secret='never-print'),
    lambda b:b['bars'][0].update(close='NaN'),
    lambda b:b['bars'][0].update(open='-1'),
    lambda b:b['bars'][0].update(volume=True),
    lambda b:b['bars'][0].update(high='1'),
    lambda b:b['bars'][0].update(known_at='2023-01-02T15:30:00'),
    lambda b:b['bars'].append(copy.deepcopy(b['bars'][0])),
    lambda b:b['tick_rules'][0]['bands'].append({'lower':'10','tick':'1'}),
])
def test_rejects_unsafe_contract(mutation):
    b=raw_bundle(); mutation(b)
    with pytest.raises(ValidationError): BacktestBundle.model_validate(b)

from datetime import date
from trading_bot.backtest_inputs import load_backtest_bundle, resolve_backtest_window, decision_view
from trading_bot.backtest_models import BacktestInputError, CoverageStatus


def test_default_three_years_is_not_silently_shortened():
    b=load_backtest_bundle(FIXTURE); w=resolve_backtest_window(b)
    assert w.requested_start==w.requested_end.replace(year=w.requested_end.year-3)
    assert w.coverage_status is CoverageStatus.INCOMPLETE
    assert 'REQUESTED_COVERAGE_MISSING' in w.reasons


def test_leap_day_default():
    raw=raw_bundle(); raw['calendar'].append({'session':'2024-02-29','close_at':'2024-02-29T15:30:00+09:00'})
    w=resolve_backtest_window(BacktestBundle.model_validate(raw))
    assert w.requested_start==date(2021,2,28)


def test_point_in_time_future_mutation_and_raw_adjustment_separation():
    raw=raw_bundle(); b=BacktestBundle.model_validate(raw); s=b.calendar[10].session
    before=decision_view(b,s)
    for bar in raw['bars']:
        if bar['session']>s.isoformat(): bar['volume']+=100
    raw['corporate_actions'][0]['ratio']='3'
    after=decision_view(BacktestBundle.model_validate(raw),s)
    assert before==after
    later=decision_view(b,b.calendar[23].session)
    assert later.history['005930'][0].close==b.bars[35].close/2
    assert later.prices['005930']==next(x.close for x in b.bars if x.ticker=='005930' and x.session==b.calendar[23].session)


def test_held_union_late_signal_and_unknown_price():
    raw=raw_bundle(); session=raw['calendar'][5]['session']
    raw['signals'][0]['known_at']='2024-01-01T00:00:00+00:00'
    raw['bars']=[x for x in raw['bars'] if not (x['ticker']=='005930' and x['session']==session)]
    b=BacktestBundle.model_validate(raw); view=decision_view(b,date.fromisoformat(session),('123456',))
    assert '123456' in view.universe
    assert '005930' not in view.signals
    assert 'PRICE_UNKNOWN:005930' in view.unknowns


def test_json_duplicate_keys_are_sanitized(tmp_path):
    f=tmp_path/'bad.json';f.write_text('{"secret":"sensitive","secret":2}')
    with pytest.raises(BacktestInputError,match='DUPLICATE_JSON_KEY') as exc: load_backtest_bundle(f)
    assert 'sensitive' not in str(exc.value)


def test_complete_short_window_needs_reviewed_rules_and_warmup():
    raw=raw_bundle()
    for r in raw['cost_rules']+raw['tick_rules']: r.update(synthetic=False,source='https://example.org/reviewed-test-rule')
    b=BacktestBundle.model_validate(raw)
    w=resolve_backtest_window(b,b.calendar[5].session,b.calendar[-1].session)
    assert w.coverage_status is CoverageStatus.COMPLETE
    assert resolve_backtest_window(b,b.calendar[0].session).coverage_status is CoverageStatus.INCOMPLETE
