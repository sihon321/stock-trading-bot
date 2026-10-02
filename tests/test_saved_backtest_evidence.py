"""Saved accounting validates without acquiring an evaluation capability."""

import json
import subprocess
import sys
from decimal import Decimal

import pytest

from test_backtest_engine import run
from trading_bot.backtest_models import BacktestInputError, content_hash
from trading_bot.backtest_reporting import build_backtest_result, load_backtest_result, write_backtest_result


def _historical_result():
    recorded = run()
    manifest = dict(recorded.manifest)
    manifest['code_identity'] = 'f' * 64
    manifest['scenario_group'] = content_hash({'input': manifest['input_hash'],
                                             'window': manifest['window'],
                                             'code': manifest['code_identity']})
    return build_backtest_result(recorded.model_copy(update={'manifest': manifest}))


def test_saved_loader_and_renderer_have_no_evaluation_capability(tmp_path):
    result = _historical_result()
    assert result.result_id == '6cb3f5a5d90fe30f8483f9d5cdfc74671739afa18d615621de17e91198db80fb'
    path = tmp_path / 'saved.json'
    write_backtest_result(result, path)
    before = path.read_bytes()
    script = '''
import importlib.abc, sys
forbidden = ('trading_bot.backtest_engine', 'trading_bot.replay',
             'trading_bot.execution', 'trading_bot.mock_broker',
             'trading_bot.brokers', 'trading_bot.providers',
             'trading_bot.config', 'trading_bot.mutation_lease')
class Reject(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == name or fullname.startswith(name + '.') for name in forbidden):
            raise AssertionError('forbidden capability: ' + fullname)
sys.meta_path.insert(0, Reject())
from trading_bot import backtest_fills, backtest_inputs
def forbidden_evaluation(*args, **kwargs):
    raise AssertionError('saved evidence reevaluated')
backtest_fills.model_session_fills = forbidden_evaluation
backtest_inputs.decision_view = forbidden_evaluation
backtest_inputs.resolve_backtest_window = forbidden_evaluation
from trading_bot.backtest_reporting import load_backtest_result, render_backtest_report
result = load_backtest_result(sys.argv[1])
assert result.run.manifest['code_identity'] == 'f' * 64
assert '모의 계산' in render_backtest_report(result)
assert not any(name in sys.modules for name in forbidden)
print(result.result_id)
'''
    child = subprocess.run([sys.executable, '-c', script, str(path)], capture_output=True, text=True)
    assert child.returncode == 0, child.stderr
    assert child.stdout.strip() == result.result_id
    assert path.read_bytes() == before


def test_legacy_engine_reexports_identical_contracts():
    from trading_bot import backtest_engine as engine, backtest_evidence as pure
    for name in ('DecisionEvidence', 'BacktestRun', 'checked_float'):
        assert getattr(engine, name) is getattr(pure, name)
    assert pure.checked_float(Decimal('0.8')) == 0.8
    with pytest.raises(BacktestInputError):
        pure.checked_float(Decimal('1e500'))


def test_future_code_identity_covers_moved_evidence(monkeypatch):
    from pathlib import Path
    from trading_bot.backtest_engine import code_identity
    before = code_identity()
    original = Path.read_bytes
    def changed(path):
        value = original(path)
        return value + b'\n# changed evidence contract\n' if path.name == 'backtest_evidence.py' else value
    monkeypatch.setattr(Path, 'read_bytes', changed)
    assert code_identity() != before


@pytest.mark.parametrize('forgery', ['fill', 'ledger', 'coverage'])
def test_rehashed_self_consistent_forgery_is_rejected(forgery, tmp_path):
    raw = _historical_result().model_dump(mode='json')
    if forgery == 'fill':
        raw['run']['fills'][0]['commission'] = '999'
        raw['metrics']['commission'] = '999'
    elif forgery == 'ledger':
        raw['run']['sessions'][0]['settled_cash'] = '999'
    else:
        raw['run']['final_coverage'] = 'COMPLETE'
        raw['run']['sessions'][0]['coverage_status'] = 'COMPLETE'
        raw['run']['sessions'][0]['unknowns'] = ['MISSING_SOURCE']
    raw['result_id'] = content_hash({k: v for k, v in raw.items() if k != 'result_id'})
    path = tmp_path / 'forged.json'
    path.write_text(json.dumps(raw))
    with pytest.raises(BacktestInputError):
        load_backtest_result(path)
