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


def test_alert_stream_enriches_phase11_subject_and_daily_evaluation(tmp_path):
    sources = make_operator_sources(tmp_path)
    with sqlite3.connect(sources.paths['audit']) as conn:
        conn.execute("INSERT INTO transition_states(state_identity,account_scope_hash,ticker,event_family,broker_subject_id,state_code,occurrence_count,first_observed_at,last_observed_at,duration_seconds,active,severity,last_notification_status) VALUES('transition-subject',?,?,?,?,?,?,?,?,?,?,?,?)",
            (ACCOUNT_HASH, '005930', 'BROKER_ORDER', 'broker-1', 'FILLED', 1,
             NOW.isoformat(), NOW.isoformat(), 0, 0, 'INFO', None))
        conn.execute("INSERT INTO transition_observations(state_identity,state_code,severity,detail_json,observed_at) VALUES(?,?,?,?,?)",
            ('transition-subject', 'FILLED', 'INFO', '{}', NOW.isoformat()))
        conn.execute("INSERT INTO daily_evaluations(evaluation_id,trading_date_kst,ticker,provenance_json,canonical_input,canonical_input_hash,account_scope_hash,status,started_at) VALUES(?,?,?,?,?,?,?,?,?)",
            ('evaluation-1', '2026-10-02', '005930', '[]', b'input', 'b'*64, ACCOUNT_HASH, 'STARTED', NOW.isoformat()))
    svc = service(sources)
    batch = svc.observe_alert_sources()
    row = next(r for r in batch.facts if r.kind == 'transition_observations')
    assert row.data['ticker'] == '005930'
    assert row.data['event_family'] == 'BROKER_ORDER'
    assert row.data['broker_subject_id'] == 'broker-1'
    assert row.data['producer_event_code'] == 'STATE_RECOVERED'
    assert any(r.kind == 'evaluations' for r in batch.facts)


@pytest.mark.parametrize('proof_ticker,valid', [('000660', True), ('005930', False)])
def test_alert_stream_emits_only_same_subject_terminal_freeze_release(tmp_path, proof_ticker, valid):
    sources = make_operator_sources(tmp_path)
    with sqlite3.connect(sources.paths['soak']) as conn:
        conn.execute("INSERT INTO soak_comparisons(comparison_id,campaign_id,run_id,ticker,order_intent_id,verdict,remaining_order_terminal,detail_json,observed_at) VALUES(?,?,?,?,?,?,?,?,?)",
            ('release-proof', 'operator-campaign', 'run-1', proof_ticker, 'historic-intent', 'MATCHED', 1, '{}', NOW.isoformat()))
        conn.execute("INSERT INTO soak_ticker_freezes(freeze_id,campaign_id,ticker,order_intent_id,freeze_kind,state,prior_transition_id,release_evidence_type,release_evidence_id,detail_json,observed_at) SELECT freeze_id,campaign_id,ticker,order_intent_id,freeze_kind,'RELEASED',id,'COMPARISON','release-proof','{}',? FROM soak_ticker_freezes WHERE state='FROZEN'", (NOW.isoformat(),))
    before = capture_sources(sources)
    batch = service(sources).observe_alert_sources()
    rows = [r for r in batch.facts if r.kind == 'freezes']
    assert rows[0].data['state'] == ('RELEASED' if valid else 'FROZEN')
    assert rows[0].data.get('release_validated') is (True if valid else None)
    assert capture_sources(sources) == before


def service(sources):
    settings = WebSettings(operational_db_path=sources.operational_db,
        artifact_root=sources.artifact_root,
        registered_resources=tuple(ResourceDescriptor(id=r.id, path=r.path, owner=r.owner,
            account_hash=r.account_hash, target=r.target) for r in sources.resources))
    return OperatorEvidenceService(settings, clock=sources.clock)


def scope():
    return ResourceScope(ACCOUNT_HASH, 'mock')


def test_overview_all_date_safety_latch_without_observer_and_failed_cache(tmp_path):
    sources = make_operator_sources(tmp_path)
    old = (NOW - timedelta(days=400)).isoformat()
    with sqlite3.connect(sources.paths['soak']) as conn:
        conn.execute("UPDATE soak_campaigns SET created_at=?, safety_failure_code='BROKER_DIVERGENCE',state='FAILED' WHERE campaign_id='operator-campaign'", (old,))
    before = capture_sources(sources)
    reader = service(sources)
    overview = reader.overview(scope())
    assert overview.safety_blocks[0].data['safety_failure_code'] == 'BROKER_DIVERGENCE'
    assert overview.safety_blocks[0].record_id == 'campaigns:operator-campaign'
    assert overview.safety_blocks[0].envelope.source_observed_at is None  # creation != latch time
    assert capture_sources(sources) == before
    sources.paths['soak'].rename(sources.paths['soak'].with_suffix('.missing'))
    cached = reader.overview(scope()).safety_blocks[0]
    assert cached.envelope.query_status == 'FAILED'
    assert cached.data['safety_failure_code'] == 'BROKER_DIVERGENCE'


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


def running_worker(sources, *, cadence=60, lifecycle='RUNNING'):
    with sqlite3.connect(sources.paths['audit']) as conn:
        # Production iterations use their own cycle ID, not the outer snapshot cycle.
        conn.execute("UPDATE watch_iterations SET cycle_id='iteration-only'")
        conn.execute("UPDATE watch_observations SET detail_json=?", ('{"cadence_seconds":'+str(cadence)+'}' if cadence else '{}',))
        conn.execute("INSERT INTO transition_states(state_identity,account_scope_hash,ticker,event_family,broker_subject_id,state_code,occurrence_count,first_observed_at,last_observed_at,duration_seconds,active,severity) VALUES ('worker-lifecycle',?,NULL,'INTRADAY_LIFECYCLE','operator-run',?,1,?,?,0,1,'INFO')", (ACCOUNT_HASH, lifecycle, NOW.isoformat(), NOW.isoformat()))
        conn.execute("INSERT INTO mutation_leases(account_scope_hash,owner_token,state,pid,command,started_at,heartbeat_at,cycle_id) VALUES (?,'never-export-owner-secret','ACTIVE',1,'intraday-watch',?,?,'operator-run')", (ACCOUNT_HASH, (NOW-timedelta(hours=2)).isoformat(), (NOW-timedelta(hours=1)).isoformat()))


def test_worker_watch_snapshot_join_and_freshness_strict_boundary(tmp_path):
    sources = make_operator_sources(tmp_path)
    running_worker(sources)
    svc = service(sources)
    sources.clock.advance(seconds=180)
    worker = svc.overview(scope()).workers[0]
    assert worker.snapshot_id == 'operator-snapshot'
    assert worker.expected_running is True and worker.state == 'RUNNING'
    assert worker.envelope.freshness == 'FRESH'
    assert worker.envelope.age_seconds == 180
    assert worker.lease_observed_at == NOW - timedelta(hours=1)
    assert 'operator-run' in worker.source_ids and 'operator-watch' in worker.source_ids
    sources.clock.advance(microseconds=1)
    assert svc.overview(scope()).workers[0].envelope.freshness == 'STALE'


@pytest.mark.parametrize('lifecycle,cadence,expected,state', [
    ('RUNNING', None, True, 'RUNNING'), ('STOPPED', 60, False, 'STOPPED'),
    ('FAILED', 60, False, 'FAILED')])
def test_worker_freshness_no_cadence_stopped_failed(tmp_path, lifecycle, cadence, expected, state):
    sources = make_operator_sources(tmp_path)
    running_worker(sources, cadence=cadence, lifecycle=lifecycle)
    sources.clock.advance(days=2)
    worker = service(sources).overview(scope()).workers[0]
    assert worker.state == state and worker.expected_running is expected
    assert worker.envelope.freshness == ('NOT_EXPECTED' if state == 'STOPPED' else 'UNKNOWN')
    assert worker.envelope.source_observed_at == NOW


def test_worker_no_lifecycle_record_is_unknown(tmp_path):
    sources = make_operator_sources(tmp_path)
    svc = service(sources)
    worker = svc.overview(scope()).workers[0]
    assert worker.expected_running is None
    assert worker.envelope.freshness == 'UNKNOWN'
    assert worker.envelope.age_seconds == 0


def test_transition_alert_sources_order_cursor_and_no_source_writes(tmp_path):
    sources = make_operator_sources(tmp_path)
    running_worker(sources)
    before = capture_sources(sources)
    svc = service(sources)
    batch = svc.observe_alert_sources()
    assert batch.cursor and batch.facts and batch.workers
    assert any(row.kind == 'freezes' and row.data['ticker'] == '000660' for row in batch.facts)
    assert any(row.kind == 'transitions' for row in batch.facts)
    assert 'never-export-owner-secret' not in repr(batch)
    next_batch = svc.observe_alert_sources(batch.cursor)
    assert next_batch.facts == ()
    assert capture_sources(sources) == before
    # A later INSERT with a historical/colliding source time must still be observed.
    with sqlite3.connect(sources.paths['audit']) as conn:
        conn.execute("INSERT INTO notification_attempts(run_id,kind,delivery_status,detail_json,observed_at) VALUES ('historic-run','RUN_SUMMARY','DELIVERED','{}',?)", ((NOW-timedelta(days=40)).isoformat(),))
    late = svc.observe_alert_sources(batch.cursor)
    assert any(row.kind == 'notifications' for row in late.facts)
    statuses = svc.source_status()
    assert len(statuses) == len(sources.resources)
    portfolio = next(s for s in statuses if s.resource_id == 'portfolio')
    assert portfolio.query_status == 'OK'
    assert portfolio.source_observed_at == NOW
    sources.clock.advance(hours=1)
    assert next(s for s in svc.source_status() if s.resource_id == 'portfolio').source_observed_at == NOW
