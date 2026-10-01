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
