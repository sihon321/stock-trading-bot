"""Synthetic source contracts; no owner runtime evidence is accessed."""
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
import sqlite3

import pytest

from operator_fixtures import make_operator_sources, capture_sources, NOW, ACCOUNT_HASH
from trading_bot.web_config import WebSettings, ResourceDescriptor
from trading_bot.web_models import ResourceScope
from trading_bot.web_models import PeriodSelection
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


def test_history_kst_pagination_and_detail_selection(tmp_path):
    sources = make_operator_sources(tmp_path)
    svc = service(sources)
    period = PeriodSelection.for_days(NOW)
    assert period.start.hour == 0
    assert period.start.astimezone(NOW.tzinfo).hour == 15
    # UTC previous day 15:00 is KST midnight and included; upper bound is excluded.
    with sqlite3.connect(sources.paths['audit']) as conn:
        conn.execute("INSERT INTO decisions(run_id,ticker,final_action,risk_override,correlation_id,created_at) VALUES ('operator-run','000001','HOLD',0,'midnight',?)", (period.start.isoformat(),))
        conn.execute("INSERT INTO decisions(run_id,ticker,final_action,risk_override,correlation_id,created_at) VALUES ('operator-run','000002','HOLD',0,'upper',?)", (period.end.isoformat(),))
    first = svc.list_records('decisions', scope(), period, limit=1)
    assert first.total == 2 and len(first.rows) == 1 and first.cursor
    second = svc.list_records('decisions', scope(), period, first.cursor, 1)
    assert len(second.rows) == 1 and second.cursor is None
    assert second.selection_id == first.selection_id
    assert second.rows[0].record_id != first.rows[0].record_id
    row = first.rows[0]
    detail = svc.get_record(row.resource_id, row.record_id)
    assert detail.record_id == row.record_id
    assert detail.selection.source_ids == row.selection.source_ids
    with pytest.raises(ValueError):
        svc.list_records('runs', scope(), period, first.cursor)
    with pytest.raises(ValueError):
        svc.list_records('decisions', scope(), period, limit=101)


def test_unresolved_historic_freeze_survives_today_and_unproven_release(tmp_path):
    sources = make_operator_sources(tmp_path)
    svc = service(sources)
    page = svc.list_records('orders', scope())
    assert any(row.data['ticker'] == '000660' for row in page.active_unresolved)
    with sqlite3.connect(sources.paths['soak']) as conn:
        conn.execute("INSERT INTO soak_ticker_freezes(campaign_id,freeze_id,ticker,order_intent_id,freeze_kind,state,prior_transition_id,release_evidence_type,release_evidence_id,detail_json,observed_at) VALUES ('operator-campaign','historic-freeze','000660','historic-intent','AMBIGUITY','RELEASED',1,'comparison','missing','{}',?)", (NOW.isoformat(),))
    overview = svc.overview(scope())
    assert any(row.data['ticker'] == '000660' for row in overview.unresolved)


def test_detail_disclosure_allowlist_and_secret_sentinels(tmp_path):
    sources = make_operator_sources(tmp_path)
    svc = service(sources)
    sentinel = 'sk-test-operator-secret-sentinel'
    with sqlite3.connect(sources.paths['audit']) as conn:
        conn.execute("UPDATE decisions SET order_reason=?,parse_error=?,override_reason=?",
            ('reason '+sentinel+' Bearer hidden-token CANO=12345678\x00'+ 'x'*20000,
             'raw-exception-'+sentinel, 'api_key='+sentinel))
    page = svc.list_records('decisions', scope())
    row = svc.get_evidence('audit', page.rows[0].record_id)
    rendered = repr(row)
    assert sentinel not in rendered and '12345678' not in rendered
    assert 'hidden-token' not in rendered and 'raw-exception' not in rendered and '\x00' not in rendered
    assert len(str(row.data['order_reason'])) <= 4096
    assert len(rendered.encode()) <= 16384
    assert 'parse_error' not in row.data and 'canonical_input' not in row.data
    with pytest.raises(ValueError):
        svc.get_evidence('audit', 'sqlite_master:1')
    with pytest.raises(ValueError):
        svc.get_record('../../outside', 'runs:operator-run')


def test_history_missing_schema_bad_time_and_broken_links_safe(tmp_path):
    sources = make_operator_sources(tmp_path, 'broken_links')
    svc = service(sources)
    before = capture_sources(sources)
    risks = svc.overview(scope()).unresolved
    assert any(r.data.get('freeze_id') == 'historic-freeze' and
               r.envelope.completeness == 'UNKNOWN' for r in risks)
    assert capture_sources(sources) == before
    with sqlite3.connect(sources.paths['audit']) as conn:
        conn.execute("UPDATE decisions SET created_at='not-a-time'")
    result = svc.list_records('decisions', scope())
    assert result.total is None and result.rows == ()
    assert result.sources[0].diagnostic_code == 'INVALID_SOURCE_TIME'
    with sqlite3.connect(sources.paths['audit']) as conn:
        conn.execute("UPDATE portfolio_schema_metadata SET version=999")
    account = svc.overview(scope()).accounts[0]
    assert account.envelope.query_status == 'FAILED'
    assert account.envelope.diagnostic_code == 'UNSUPPORTED_SCHEMA'


def test_unresolved_positive_same_subject_terminal_release(tmp_path):
    sources = make_operator_sources(tmp_path)
    svc = service(sources)
    with sqlite3.connect(sources.paths['soak']) as conn:
        conn.execute("INSERT INTO soak_comparisons(comparison_id,campaign_id,run_id,snapshot_id,ticker,order_intent_id,verdict,remaining_order_terminal,detail_json,observed_at) VALUES ('terminal','operator-campaign','historic-run','proof','000660','historic-intent','MATCHED',1,'{}',?)", (NOW.isoformat(),))
        conn.execute("INSERT INTO soak_ticker_freezes(campaign_id,freeze_id,ticker,order_intent_id,freeze_kind,state,prior_transition_id,release_evidence_type,release_evidence_id,detail_json,observed_at) VALUES ('operator-campaign','historic-freeze','000660','historic-intent','AMBIGUITY','RELEASED',1,'COMPARISON','terminal','{}',?)", (NOW.isoformat(),))
    assert not any(r.data.get('freeze_id') == 'historic-freeze' for r in svc.overview(scope()).unresolved)
