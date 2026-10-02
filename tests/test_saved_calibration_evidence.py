"""Saved advisory reductions must not acquire execution or writer capabilities."""

import hashlib
import json
import subprocess
import sys

import pytest


# Runs before any trading_bot import in a clean interpreter, independent of conftest.
PROBE = r'''
import builtins, importlib.abc, json, os, socket, sqlite3, sys
from pathlib import Path
forbidden = (
    'trading_bot.calibration', 'trading_bot.replay', 'trading_bot.execution',
    'trading_bot.config', 'trading_bot.soak_config', 'trading_bot.mock_broker',
    'trading_bot.brokers', 'trading_bot.providers', 'trading_bot.soak_store',
    'trading_bot.sqlite_audit', 'trading_bot.portfolio_store',
    'trading_bot.soak_controller', 'trading_bot.mutation_lease',
)
class Reject(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == name or fullname.startswith(name + '.') for name in forbidden):
            raise AssertionError('forbidden capability: ' + fullname)
sys.meta_path.insert(0, Reject())
def deny(*args, **kwargs):
    raise AssertionError('saved reader acquired socket/write capability')
socket.socket = socket.create_connection = deny
def audit(event, args):
    if event == 'open':
        mode, flags = args[1:3]
        if (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
            isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)
        ):
            deny()
    if event in ('os.remove', 'os.rename', 'os.mkdir', 'os.rmdir', 'os.link', 'os.symlink'):
        deny()
sys.addaudithook(audit)
real_connect = sqlite3.connect
def read_connection(database, *args, **kwargs):
    assert str(database).endswith('?mode=ro') and kwargs.get('uri') is True
    conn = real_connect(database, *args, **kwargs)
    def authorize(action, first, second, db, trigger):
        allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION,
                   sqlite3.SQLITE_TRANSACTION}
        if action == sqlite3.SQLITE_PRAGMA:
            return sqlite3.SQLITE_OK if first.lower() in ('query_only', 'user_version', 'table_info') and (second is None or first.lower() in ('query_only', 'table_info')) else sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY
    conn.set_authorizer(authorize)
    return conn
sqlite3.connect = read_connection
payload = json.loads(sys.argv[1])
'''


SAVED_ROWS = [
    dict(variant_id=variant_id, metrics=dict(
        evaluated=3, denominator=3, buy_actions=1, hold_actions=1, sell_actions=1,
        order_eligible=opportunity, low_confidence=0, risk_blocks=risk,
        stop_loss_triggers=0, take_profit_triggers=0, exposure_total=exposure,
        expectation_deltas=0,
    ))
    for variant_id, risk, exposure, opportunity in (
        ("BASELINE", 1, 500_000.0, 2),
        ("BUY_CONFIDENCE_085", 0, 400_000.0, 1),
        ("MAX_POSITION_500000", 1, 300_000.0, 1),
    )
]

LOAD_ROWS = '''
from trading_bot.calibration_evidence import (
    VariantEvaluation, VariantMetrics, build_variant_catalog, judge_variants,
)
catalog = {v.variant_id: v for v in build_variant_catalog()}
rows = tuple(VariantEvaluation(catalog[r['variant_id']], VariantMetrics(**r['metrics']), ())
             for r in payload['rows'])
'''


def _child(script, payload):
    child = subprocess.run(
        [sys.executable, "-B", "-c", PROBE + script, json.dumps(payload)],
        capture_output=True, text=True, timeout=20,
    )
    assert child.returncode == 0, child.stderr
    return json.loads(child.stdout)


def test_pure_judgment_in_fresh_child_from_saved_rows():
    result = _child(LOAD_ROWS + '''
from dataclasses import asdict, replace
judgment = judge_variants(rows)
try:
    judge_variants((rows[0], replace(rows[1], metrics=replace(rows[1].metrics,
                    evaluated=4, denominator=4))))
except ValueError as exc:
    assert 'one denominator' in str(exc)
else:
    raise AssertionError('malformed saved denominator accepted')
print(json.dumps(asdict(judgment)))
''', {"rows": SAVED_ROWS})
    assert result == dict(
        status="PROVISIONAL_CANDIDATE", selected_variant_id="BUY_CONFIDENCE_085",
        ranked_variant_ids=["BUY_CONFIDENCE_085", "MAX_POSITION_500000", "BASELINE"],
        risk_event_delta=-1, exposure_delta=-100_000.0, order_eligible_delta=-1,
    )


def test_legacy_calibration_exports_are_identical_and_catalog_is_frozen():
    from trading_bot import calibration as legacy, calibration_evidence as pure
    from trading_bot.replay_evidence import canonical_json_bytes
    for name in (*pure.__all__, "_CANDIDATES", "_risk_events"):
        assert getattr(legacy, name) is getattr(pure, name)
    assert "evaluate_variants" not in pure.__dict__
    assert hashlib.sha256(canonical_json_bytes(pure.build_variant_catalog())).hexdigest() == (
        "69c54b1500d054cce561f6d45bf41179a8f6083eb9e6d535f81ab7bf789c6262"
    )


@pytest.mark.parametrize("module", ["trading_bot.replay", "trading_bot.soak_store"])
def test_probe_rejects_forbidden_imports(module):
    result = _child('''
try:
    __import__(payload['module'])
except AssertionError:
    print('true')
else:
    raise AssertionError('probe did not reject capability')
''', {"module": module})
    assert result is True
