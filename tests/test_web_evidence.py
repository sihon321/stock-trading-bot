"""Synthetic source contracts; no owner runtime evidence is accessed."""
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
import sqlite3

import pytest

from operator_fixtures import make_operator_sources, capture_sources, NOW, ACCOUNT_HASH
from trading_bot.web_config import WebSettings, ResourceDescriptor
from trading_bot.web_models import ResourceScope
from trading_bot.web_evidence import OperatorEvidenceService


def service(sources):
    settings = WebSettings(operational_db_path=sources.operational_db,
        artifact_root=sources.artifact_root,
        registered_resources=tuple(ResourceDescriptor(id=r.id, path=r.path, owner=r.owner,
            account_hash=r.account_hash, target=r.target) for r in sources.resources))
    return OperatorEvidenceService(settings, clock=sources.clock)


def scope():
    return ResourceScope(ACCOUNT_HASH, 'mock')


def test_account_snapshot_exact_and_immutable(tmp_path):
    sources = make_operator_sources(tmp_path)
    before = capture_sources(sources)
    account = service(sources).overview(scope()).accounts[0]
    assert account.available_cash == 1000000
    assert account.total_evaluation == 1210000
    assert account.snapshot_id == 'operator-snapshot'
    assert account.unrealized_value is None
    assert len(account.holdings) == len(account.orders) == len(account.fills) == 1
    assert all(r.snapshot_id == account.snapshot_id for r in (*account.holdings, *account.orders, *account.fills))
    assert account.envelope.source_observed_at == NOW
    with pytest.raises(FrozenInstanceError):
        account.available_cash = 0
    assert capture_sources(sources) == before


@pytest.mark.parametrize('scenario', ['incomplete_zero_cash', 'scope_conflict'])
def test_account_incomplete_zero_and_scope_conflict_unknown(tmp_path, scenario):
    sources = make_operator_sources(tmp_path, scenario)
    account = service(sources).overview(scope()).accounts[0]
    assert account.available_cash is account.total_evaluation is None
    assert account.envelope.completeness == 'UNKNOWN'


def test_snapshot_last_complete_and_cache_time_not_query_time(tmp_path):
    sources = make_operator_sources(tmp_path)
    svc = service(sources)
    original = svc.overview(scope()).accounts[0]
    sources.clock.advance(minutes=10)
    with sqlite3.connect(sources.paths['audit']) as conn:
        conn.execute("INSERT INTO portfolio_snapshots SELECT 'incomplete',cycle_id,'new-observation',account_scope_hash,trading_date_kst,previous_trading_date_kst,?, 'INCOMPLETE',reason_code,1,0,0,0 FROM portfolio_snapshots", (sources.clock().isoformat(),))
    fallback = svc.overview(scope()).accounts[0]
    assert fallback.available_cash == original.available_cash
    assert fallback.latest_attempt_id == 'incomplete'
    assert fallback.latest_attempt_status == 'INCOMPLETE'
    assert fallback.historical
    sources.paths['audit'].rename(sources.paths['audit'].with_suffix('.removed'))
    cached = svc.overview(scope()).accounts[0]
    assert cached.available_cash == original.available_cash
    assert cached.envelope.query_status == 'FAILED'
    assert cached.envelope.source_observed_at == NOW
    assert cached.envelope.query_at == sources.clock()


def test_missing_schema_source_never_created_and_cache_scope_bound(tmp_path):
    sources = make_operator_sources(tmp_path)
    svc = service(sources)
    svc.overview(scope())
    sources.paths['audit'].unlink()
    assert svc.overview(ResourceScope('f' * 64, 'mock')).accounts == ()
    assert svc.overview(scope()).accounts[0].envelope.query_status == 'FAILED'
    assert not sources.paths['audit'].exists()
