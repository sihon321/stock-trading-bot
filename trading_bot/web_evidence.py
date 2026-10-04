"""Bounded saved evidence services. No source mutation or live capabilities."""
from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import sqlite3
import base64
import re
import unicodedata

from . import evidence_contracts as contracts
from .web_config import checked_path
from .web_models import (AccountDTO, EvidenceRecord, EvidenceSelection, OverviewDTO,
                         ResourceScope, SourceEnvelope, PeriodSelection, RecordPage,
                         WorkerDTO, AlertSourceBatch, ServiceHealthDTO, ControlStateDTO, KST)

# Fixed capabilities: table, primary key, durable time and public fields only.
_HISTORY = {
    ('audit', 'runs'): ('runs', 'run_id', 'started_at', ('run_id', 'run_kind', 'status', 'started_at', 'finished_at', 'trading_date_kst', 'target')),
    ('audit', 'candidates'): ('ticker_outcomes', 'id', 'created_at', ('run_id', 'ticker', 'outcome_code', 'reason_code', 'failed_stage', 'order_intent_id', 'final_order_state')),
    ('audit', 'decisions'): ('decisions', 'id', 'created_at', ('run_id', 'ticker', 'final_action', 'parsed_decision', 'confidence', 'order_reason', 'override_reason', 'broker_order_id', 'requested_qty', 'filled_qty', 'correlation_id')),
    ('audit', 'orders'): ('order_events', 'id', 'observed_at', ('order_intent_id', 'origin_run_id', 'observer_run_id', 'ticker', 'event_type', 'submission_id', 'broker_order_id', 'side', 'requested_qty', 'filled_qty', 'unfilled_qty', 'broker_status')),
    ('portfolio', 'evaluations'): ('daily_evaluations', 'evaluation_id', 'started_at', ('evaluation_id', 'ticker', 'account_scope_hash', 'status', 'started_at', 'finalized_at', 'canonical_input_hash')),
    ('portfolio', 'watch'): ('watch_iterations', 'iteration_id', 'started_at', ('iteration_id', 'snapshot_id', 'terminal_status')),
    ('portfolio', 'transitions'): ('transition_states', 'id', 'last_observed_at', ('state_identity', 'account_scope_hash', 'ticker', 'event_family', 'broker_subject_id', 'state_code', 'occurrence_count', 'duration_seconds', 'active', 'severity', 'last_notification_status')),
    ('portfolio', 'transition_observations'): ('transition_observations', 'id', 'observed_at', ('state_identity', 'state_code', 'severity')),
    ('portfolio', 'transition_notifications'): ('transition_notifications', 'id', 'observed_at', ('state_identity', 'event_code', 'severity', 'delivery_status', 'failure_category')),
    ('portfolio', 'divergences'): ('portfolio_divergences', 'id', 'observed_at', ('snapshot_id', 'code', 'severity', 'ticker', 'order_intent_id')),
    ('portfolio', 'evaluation_events'): ('daily_evaluation_events', 'id', 'observed_at', ('evaluation_id', 'event_type', 'action', 'confidence', 'reason_code')),
    ('portfolio', 'lease_events'): ('mutation_lease_events', 'id', 'observed_at', ('account_scope_hash', 'event_type', 'from_state', 'to_state', 'origin_cycle_id', 'observer_cycle_id')),
    ('soak', 'soak_events'): ('soak_events', 'id', 'observed_at', ('campaign_id', 'event_code', 'evidence_class', 'run_id', 'ticker', 'order_intent_id', 'observation_id')),
    ('audit', 'notifications'): ('notification_attempts', 'id', 'observed_at', ('run_id', 'ticker', 'kind', 'delivery_status', 'failure_category')),
    ('soak', 'freezes'): ('soak_ticker_freezes', 'id', 'observed_at', ('freeze_id', 'campaign_id', 'ticker', 'order_intent_id', 'freeze_kind', 'state', 'release_evidence_type', 'release_evidence_id')),
    ('soak', 'campaigns'): ('soak_campaigns', 'campaign_id', 'created_at', ('campaign_id', 'state', 'campaign_kind', 'safety_failure_code', 'availability_failure_code', 'target_eligible_days')),
    ('soak', 'comparisons'): ('soak_comparisons', 'id', 'observed_at', ('comparison_id', 'campaign_id', 'run_id', 'snapshot_id', 'ticker', 'order_intent_id', 'verdict', 'remaining_order_terminal')),
    ('controller', 'drills'): ('drill_observations', 'id', 'observed_at', ('drill_id', 'observation_type', 'evidence_class', 'primary_run_id', 'reconciliation_id', 'ticker', 'order_intent_id', 'freeze_id')),
}
_KINDS = {kind for _, kind in _HISTORY} | {'holdings', 'fills', 'broker_orders'}

_OPERATIONAL_HISTORY = {
    ('service', 'service_jobs'): ('service_jobs','job_id','due_at'),
    ('service', 'service_job_events'): ('service_job_events','event_id','observed_at'),
    ('service', 'service_expectations'): ('service_expectations','expectation_id','observed_at'),
    ('service', 'service_expectation_health'): ('service_expectation_health','event_id','observed_at'),
    ('service', 'service_heartbeats'): ('service_heartbeats','worker_id','observed_at'),
    ('service', 'service_restarts'): ('service_restart_attempts','attempt_id','admitted_at'),
    ('service', 'service_attention'): ('service_attention_events','event_id','observed_at'),
    ('service', 'service_provider_admissions'): ('service_provider_admissions','dispatch_id','observed_at'),
    ('control', 'control_requests'): ('control_requests','request_id','requested_at'),
    ('control', 'control_applications'): ('control_applications','application_id','applied_at'),
    ('control', 'control_admissions'): ('submission_admissions','admission_id','admitted_at'),
}
# JSON payloads, canonical inputs, PID and unreviewed actor text are never exported.
for (owner, kind), (table, key, stamp) in _OPERATIONAL_HISTORY.items():
    schema = contracts.SERVICE_REPORT_SCHEMA if owner == 'service' else contracts.CONTROL_REPORT_SCHEMA
    fields = tuple(sorted(schema[table] - {'evidence_json','universe_json','source_ids_json','safety_evidence_ids_json','actor','payload_hash'}))
    _HISTORY[(owner, kind)] = (table, key, stamp, fields)
    _KINDS.add(kind)


def _operational_stamp(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        try:
            return datetime.fromtimestamp(value, timezone.utc)
        except (ValueError, OverflowError, OSError):
            raise EvidenceUnavailable('INVALID_SOURCE_TIME') from None
    return _stamp(value)


def _clean(value):
    if not isinstance(value, str):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return value
    # Sanitize before truncation, so a secret spanning the boundary is still removed.
    value = re.sub(r'(?i)\b(?:sk-|ghp_|github_pat_)[a-z0-9_-]+', '[REDACTED]', value)
    value = re.sub(r'(?i)\bBearer\s+[^\s]+', 'Bearer [REDACTED]', value)
    value = re.sub(r'(?i)\b(?:cano|account(?:_number)?|api[_ -]?key|app[_ -]?key|app[_ -]?secret|secret|token|password|cookie|session)[\s:=]+[^\s,;]+', '[REDACTED]', value)
    value = re.sub(r'https?://[^\s]*/api/webhooks/[^\s]+', '[REDACTED]', value)
    value = re.sub(r'\beyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\b', '[REDACTED]', value)
    value = re.sub(r'\b\d{8,14}(?:-\d{2})?\b', '[REDACTED]', value)
    value = ''.join(c if unicodedata.category(c) not in {'Cc', 'Cf', 'Cs'} else ' ' for c in value)
    return value[:4096]


def _wire_record(resource, kind, row, key, stamp, fields, *, conn=None, snapshot_id=None, source_ids=(), completeness='COMPLETE'):
    rid = f'{kind}:{row[key]}'
    if len(rid) > 512 or _clean(rid) != rid or any(len(str(v)) > 128 or _clean(str(v)) != str(v) for v in source_ids):
        raise EvidenceUnavailable('INVALID_SOURCE_ID')
    projected = tuple((name, _clean(row[name])) for name in fields)
    if sum(len(str(v).encode()) + len(k) for k, v in projected) > 10000:
        projected = tuple((name, value[:512] if isinstance(value, str) else value) for name, value in projected)
    return EvidenceRecord(rid, kind, _envelope(resource, datetime.now(timezone.utc), conn=conn,
        source_observed_at=_stamp(stamp), completeness=completeness),
        _selection(resource, kind, (rid,), snapshot_id, source_ids), projected)


class EvidenceUnavailable(ValueError):
    """Stable non-sensitive diagnostic, never a raw source exception."""


def _stamp(value):
    try:
        result = datetime.fromisoformat(str(value))
        if result.tzinfo is None or result.utcoffset() is None:
            raise ValueError()
        return result.astimezone(timezone.utc)
    except (ValueError, TypeError):
        raise EvidenceUnavailable('INVALID_SOURCE_TIME') from None


def _json(value):
    if not isinstance(value, str) or len(value) > 65536:
        raise EvidenceUnavailable('INVALID_SOURCE_DATA')
    try:
        return json.loads(value)
    except ValueError:
        raise EvidenceUnavailable('INVALID_SOURCE_DATA') from None


def _identity(*parts):
    return hashlib.sha256(json.dumps(parts, separators=(',', ':'), default=str).encode()).hexdigest()


def _portfolio_read_version(conn):
    rows = conn.execute('SELECT owner,version FROM portfolio_schema_metadata').fetchall()
    if len(rows) != 1 or rows[0][0] != contracts.PORTFOLIO_SCHEMA_OWNER:
        raise EvidenceUnavailable('UNSUPPORTED_SCHEMA')
    version = rows[0][1]
    try:
        contracts.portfolio_read_schema(version)
    except ValueError:
        raise EvidenceUnavailable('UNSUPPORTED_SCHEMA') from None
    return version


def _envelope(resource, now, *, conn=None, **values):
    version = (_portfolio_read_version(conn) if conn is not None else None) if resource.owner == 'portfolio' else {
        'audit': contracts.PRIMARY_AUDIT_SCHEMA_VERSION,
        'soak': contracts.SOAK_SCHEMA_VERSION, 'controller': contracts.CONTROLLER_SCHEMA_VERSION,
    }.get(resource.owner)
    if resource.owner in {'service','control'}:
        version = 1
    return SourceEnvelope(resource.id, resource.owner,
        version,
        resource.account_hash, resource.target, now, **values)


@contextmanager
def _transaction(resource):
    conn = None
    try:
        path = checked_path(resource.path)
        if not path.is_file():
            raise EvidenceUnavailable('SOURCE_MISSING')
        if resource.owner in {'service','control'} and (path.stat().st_uid!=os.getuid()
                or path.stat().st_mode & 0o077 or path.parent.stat().st_mode & 0o077):
            raise EvidenceUnavailable('SOURCE_OWNER_UNSAFE')
        conn = sqlite3.connect(f'{path.as_uri()}?mode=ro', uri=True, isolation_level=None, timeout=1)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA query_only=ON')
        # Bound virtual-machine work even when registered data is malformed/huge.
        budget = [0]
        def progress():
            budget[0] += 1
            return budget[0] > 2000
        conn.set_progress_handler(progress, 1000)
        conn.execute('BEGIN')
        schemas = {'portfolio': contracts.PORTFOLIO_REPORT_SCHEMA,
                   'audit': contracts.PRIMARY_REPORT_SCHEMA,
                   'soak': contracts.SOAK_REPORT_SCHEMA,
                   'controller': contracts.CONTROLLER_REPORT_SCHEMA,
                   'service': contracts.SERVICE_REPORT_SCHEMA,
                   'control': contracts.CONTROL_REPORT_SCHEMA}
        schema = schemas.get(resource.owner)
        if schema is None:
            raise EvidenceUnavailable('UNSUPPORTED_SOURCE_OWNER')
        if resource.owner == 'portfolio':
            actual = _portfolio_read_version(conn)
            schema = contracts.portfolio_read_schema(actual)
        elif resource.owner in {'service','control'}:
            rows = conn.execute(f'SELECT owner,version FROM {resource.owner}_metadata').fetchall()
            expected_owner = {'service':contracts.SERVICE_SCHEMA_OWNER,'control':contracts.CONTROL_SCHEMA_OWNER}[resource.owner]
            if len(rows)!=1 or tuple(rows[0])!=(expected_owner,1):
                raise EvidenceUnavailable('UNSUPPORTED_SCHEMA')
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables!=set(schema):
                raise EvidenceUnavailable('UNSUPPORTED_SCHEMA')
            actual = 1
        else:
            actual = conn.execute('PRAGMA user_version').fetchone()[0]
        expected = {'audit': contracts.PRIMARY_AUDIT_SCHEMA_VERSION,
            'soak': contracts.SOAK_SCHEMA_VERSION, 'controller': contracts.CONTROLLER_SCHEMA_VERSION,
            'service':1,'control':1}.get(resource.owner)
        if resource.owner != 'portfolio' and actual != expected:
            raise EvidenceUnavailable('UNSUPPORTED_SCHEMA')
        for table, columns in schema.items():
            actual_cols = {r[1] for r in conn.execute(f'PRAGMA table_info({table})')}
            if actual_cols != set(columns):
                raise EvidenceUnavailable('UNSUPPORTED_SCHEMA')
        yield conn
    except EvidenceUnavailable:
        raise
    except (sqlite3.Error, OSError, ValueError):
        raise EvidenceUnavailable('SOURCE_QUERY_FAILED') from None
    finally:
        if conn is not None:
            if conn.in_transaction:
                conn.rollback()
            conn.close()


def _selection(resource, kind, record_ids=(), snapshot_id=None, source_ids=(), denominator=None):
    scope = ResourceScope(resource.account_hash, resource.target, resource.id)
    return EvidenceSelection(_identity(resource.id, kind, scope, snapshot_id, record_ids),
        resource.id, kind, scope, tuple(record_ids), snapshot_id, tuple(source_ids),
        len(record_ids), denominator if denominator is not None else len(record_ids))


def _check_run(conn, resource, run_id):
    # Registered scope is positive authority, but any available source contradiction wins.
    exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name='runs' AND type='table'").fetchone()
    if not exists:
        return
    run = conn.execute('SELECT target,provenance FROM runs WHERE run_id=?', (run_id,)).fetchone()
    if run is None:
        return
    provenance = _json(run['provenance'])
    if not isinstance(provenance, dict):
        raise EvidenceUnavailable('SCOPE_CONFLICT')
    account = provenance.get('account_scope_hash')
    if run['target'] != resource.target or (account is not None and account != resource.account_hash):
        raise EvidenceUnavailable('SCOPE_CONFLICT')


def _bounded_rows(conn, query, args=()):
    rows = conn.execute(query, args).fetchmany(10001)
    if len(rows) > 10000:
        raise EvidenceUnavailable('SOURCE_ROW_BOUND')
    return rows


def _table_source(table, *, portfolio_version=None):
    if table in contracts.SERVICE_REPORT_SCHEMA:
        numeric_times={'started_at','stopped_at','due_at','dispatch_deadline_at','observed_at','admitted_at',
            'expected_until','config_effective_at','login_effective_at','controls_observed_at','invocation_started_at'}
        columns=sorted(contracts.SERVICE_REPORT_SCHEMA[table])
        projection=','.join(f"strftime('%Y-%m-%dT%H:%M:%f+00:00',{c},'unixepoch') AS {c}" if c in numeric_times else c for c in columns)
        return f'(SELECT {projection} FROM {table})'
    if table == 'portfolio_divergences':
        return '(SELECT d.*,s.observed_at FROM portfolio_divergences d JOIN portfolio_snapshots s ON s.snapshot_id=d.snapshot_id)'
    if table == 'daily_evaluations':
        # Canonical prompts are deliberately absent even from the fetched SQL rows.
        if portfolio_version == 4:
            return '''(SELECT e.evaluation_id,e.trading_date_kst,e.ticker,e.canonical_input_hash,
                e.account_scope_hash,e.status,e.started_at,e.finalized_at,
                d.execution_target,d.dispatch_state,d.dispatch_id,d.envelope_hash,
                d.dispatched_at,d.finalized_at AS dispatch_finalized_at,d.execution_intent_id
                FROM daily_evaluations e LEFT JOIN daily_evaluation_dispatches d USING(evaluation_id))'''
        return '(SELECT evaluation_id,trading_date_kst,ticker,canonical_input_hash,account_scope_hash,status,started_at,finalized_at FROM daily_evaluations)'
    return table


class ReadOnlyPortfolioRepository:
    def __init__(self, resource, *, clock=lambda: datetime.now(timezone.utc)):
        if resource.owner != 'portfolio':
            raise ValueError('portfolio owner required')
        self.resource, self.clock = resource, clock

    def account(self, snapshot_id=None):
        r, now = self.resource, self.clock()
        with _transaction(r) as conn:
            snapshots = _bounded_rows(conn, 'SELECT * FROM portfolio_snapshots WHERE account_scope_hash=? ORDER BY julianday(observed_at) DESC,snapshot_id DESC LIMIT 10001', (r.account_hash,))
            for snapshot in snapshots:
                _stamp(snapshot['observed_at'])
                _check_run(conn, r, snapshot['cycle_id'])
            latest = snapshots[0] if snapshots else None
            complete = next((s for s in snapshots if s['completeness'] == 'COMPLETE'
                             and s['daily_page_count'] > 0 and s['balance_page_count'] > 0
                             and (snapshot_id is None or s['snapshot_id'] == snapshot_id)), None)
            if complete is None:
                return AccountDTO(_envelope(r, now, conn=conn, diagnostic_code='NO_COMPLETE_SNAPSHOT'),
                    _selection(r, 'account'), latest_attempt_id=latest['snapshot_id'] if latest else None,
                    latest_attempt_status=latest['completeness'] if latest else 'UNKNOWN')
            amounts = (complete['available_cash'], complete['total_evaluation'])
            if any(not isinstance(v, (float, int)) or not math.isfinite(v) or v < 0 for v in amounts):
                raise EvidenceUnavailable('INVALID_ACCOUNT_TOTAL')
            sid = complete['snapshot_id']
            env = _envelope(r, now, conn=conn, source_observed_at=_stamp(complete['observed_at']), completeness='COMPLETE', provenance='saved_broker')
            projected = []
            for kind, table, key in (('holdings', 'portfolio_holdings', 'ticker'),
                                     ('orders', 'portfolio_orders', 'order_id'),
                                     ('fills', 'portfolio_fills', 'fill_id')):
                rows = _bounded_rows(conn, f'SELECT * FROM {table} WHERE snapshot_id=? ORDER BY {key} LIMIT 10001', (sid,))
                records = []
                for row in rows:
                    rid = f'{kind}:{sid}:{row[key]}'
                    selection = _selection(r, kind, (rid,), sid, (complete['observation_id'], complete['cycle_id']))
                    records.append(EvidenceRecord(rid, kind, env, selection,
                        tuple((k, _clean(row[k])) for k in row.keys() if k != 'snapshot_id')))
                projected.append(tuple(records))
            order_ids = {record.data['order_id'] for record in projected[1]}
            if any(record.data['order_id'] not in order_ids for record in projected[2]):
                raise EvidenceUnavailable('BROKEN_SOURCE_LINK')
            ids = tuple(record.record_id for rows in projected for record in rows)
            return AccountDTO(env, _selection(r, 'account', ids, sid,
                (complete['observation_id'], complete['cycle_id'])), float(amounts[0]), float(amounts[1]),
                holdings=projected[0], orders=projected[1], fills=projected[2],
                latest_attempt_id=latest['snapshot_id'], latest_attempt_status=latest['completeness'])


class OperatorEvidenceService:
    def __init__(self, settings, *, clock=lambda: datetime.now(timezone.utc), shadow_proof_catalog=None):
        self.settings, self.clock = settings, clock
        self.shadow_proof_catalog = shadow_proof_catalog
        self._cache = OrderedDict()

    def _resources(self, scope=None, owner=None):
        return tuple(r for r in self.settings.registered_resources
            if (owner is None or r.owner == owner) and (scope is None or
                (scope.account_hash == r.account_hash and scope.target == r.target
                 and (scope.resource_id is None or scope.resource_id == r.id))))

    def _account(self, resource):
        key = (resource.id, resource.account_hash, resource.target, 'account')
        try:
            account = ReadOnlyPortfolioRepository(resource, clock=self.clock).account()
            if account.envelope.completeness == 'COMPLETE':
                self._cache[key] = account
                self._cache.move_to_end(key)
                while len(self._cache) > 128:
                    self._cache.popitem(last=False)
            elif key in self._cache:
                previous = self._cache[key]
                env = replace(previous.envelope, query_at=self.clock(), diagnostic_code='NO_CURRENT_COMPLETE_SNAPSHOT')
                account = replace(previous, envelope=env, latest_attempt_id=account.latest_attempt_id,
                                  latest_attempt_status=account.latest_attempt_status,
                                  holdings=tuple(replace(row, envelope=env) for row in previous.holdings),
                                  orders=tuple(replace(row, envelope=env) for row in previous.orders),
                                  fills=tuple(replace(row, envelope=env) for row in previous.fills))
            return account
        except EvidenceUnavailable as exc:
            if key in self._cache and str(exc) != 'SCOPE_CONFLICT':
                old = self._cache[key]
                env = replace(old.envelope, query_at=self.clock(), query_status='FAILED', diagnostic_code=str(exc))
                return replace(old, envelope=env,
                    holdings=tuple(replace(row, envelope=env) for row in old.holdings),
                    orders=tuple(replace(row, envelope=env) for row in old.orders),
                    fills=tuple(replace(row, envelope=env) for row in old.fills))
            return AccountDTO(_envelope(resource, self.clock(), query_status='FAILED', diagnostic_code=str(exc)),
                              _selection(resource, 'account'))

    def overview(self, scope):
        return OverviewDTO(self.clock(), accounts=tuple(self._account(r) for r in self._resources(scope, 'portfolio')),
                           unresolved=self._unresolved(scope), workers=self._workers(scope), sources=self.source_status(scope),
                           safety_blocks=self._safety_blocks(scope), service_health=self.service_health(scope),
                           controls=self.control_states(scope))

    def _safety_blocks(self, scope):
        """Positive persisted campaign latches, independent of observer/date filters.

        Campaign completion or missing rows never clears an irreversible latch.
        Creation time is not substituted for an absent latch observation event.
        """
        records = []
        for resource in self._resources(scope, 'soak'):
            cache_key = ('safety_blocks', resource.id)
            try:
                with _transaction(resource) as conn:
                    rows = _bounded_rows(conn, "SELECT * FROM soak_campaigns WHERE safety_failure_code IS NOT NULL OR availability_failure_code IS NOT NULL ORDER BY campaign_id LIMIT 10001")
                    projected = []
                    for row in rows:
                        record = self._project(conn, resource, 'campaigns', row)
                        code = 'SAFETY_FAILURE_LATCHED' if row['safety_failure_code'] else 'AVAILABILITY_BUDGET_EXCEEDED'
                        proof = conn.execute("SELECT * FROM soak_events WHERE campaign_id=? AND event_code=? ORDER BY id DESC LIMIT 1", (row['campaign_id'], code)).fetchone()
                        linked = proof is not None
                        if proof and proof['run_id']:
                            linked = False
                            for primary in self._resources(ResourceScope(resource.account_hash, resource.target), 'audit'):
                                try:
                                    with _transaction(primary) as audit:
                                        if audit.execute('SELECT 1 FROM runs WHERE run_id=?', (proof['run_id'],)).fetchone():
                                            _check_run(audit, primary, proof['run_id'])
                                            linked = True
                                except EvidenceUnavailable:
                                    continue
                        record = replace(record, envelope=replace(record.envelope,
                            source_observed_at=_stamp(proof['observed_at']) if proof else None,
                            completeness='COMPLETE' if linked else 'UNKNOWN',
                            diagnostic_code=None if linked else 'BROKEN_SOURCE_LINK'),
                            selection=replace(record.selection, source_ids=(f'soak_events:{proof["id"]}',) if proof else ()))
                        projected.append(record)
                    # Latches cannot disappear from a successful query either.
                    seen = {row.record_id for row in projected}
                    projected.extend(replace(row, envelope=replace(row.envelope, query_at=self.clock(),
                        completeness='UNKNOWN', diagnostic_code='LATCH_SOURCE_MISSING'))
                        for row in self._cache.get(cache_key, ()) if row.record_id not in seen)
                    self._cache[cache_key] = tuple(projected)
                    self._cache.move_to_end(cache_key)
                    while len(self._cache) > 128:
                        self._cache.popitem(last=False)
                    records.extend(projected)
            except EvidenceUnavailable as exc:
                records.extend(replace(row, envelope=replace(row.envelope, query_at=self.clock(),
                    query_status='FAILED', diagnostic_code=str(exc))) for row in self._cache.get(cache_key, ()))
        return tuple(records)

    def _project(self, conn, resource, kind, row):
        _, key, time_key, fields = _HISTORY[(resource.owner, kind)]
        source_ids = []
        sid = None
        if resource.owner in {'service','control'}:
            if resource.owner=='service' and 'scope_hash' in row.keys() and (row['scope_hash'],row['target'])!=(resource.account_hash,resource.target):
                raise EvidenceUnavailable('SCOPE_CONFLICT')
            if resource.owner=='service' and kind in {'service_job_events','service_heartbeats'}:
                parent=conn.execute('SELECT scope_hash,target FROM '+('service_jobs WHERE job_id=?' if kind=='service_job_events' else 'service_generations WHERE generation_id=?'),
                    (row['job_id'] if kind=='service_job_events' else row['generation_id'],)).fetchone()
                if parent is None or tuple(parent)!=(resource.account_hash,resource.target):
                    raise EvidenceUnavailable('BROKEN_SOURCE_LINK')
            record = _wire_record(resource,kind,row,key,_operational_stamp(row[time_key]).isoformat(),fields,conn=conn)
            return replace(record,envelope=replace(record.envelope,query_at=self.clock()))
        if resource.owner == 'audit':
            for run_key in ('run_id', 'origin_run_id', 'observer_run_id'):
                if run_key in row.keys():
                    run_id = row[run_key]
                    if conn.execute('SELECT 1 FROM runs WHERE run_id=?', (run_id,)).fetchone() is None:
                        raise EvidenceUnavailable('BROKEN_SOURCE_LINK')
                    _check_run(conn, resource, run_id)
                    source_ids.append(run_id)
        if resource.owner == 'portfolio':
            if 'account_scope_hash' in row.keys() and row['account_scope_hash'] != resource.account_hash:
                raise EvidenceUnavailable('SCOPE_CONFLICT')
            if kind == 'watch':
                snapshot = conn.execute('SELECT * FROM portfolio_snapshots WHERE snapshot_id=?', (row['snapshot_id'],)).fetchone()
                if snapshot is None or snapshot['account_scope_hash'] != resource.account_hash:
                    raise EvidenceUnavailable('BROKEN_SOURCE_LINK')
                _check_run(conn, resource, snapshot['cycle_id'])
                sid = snapshot['snapshot_id']
                source_ids.extend((snapshot['observation_id'], snapshot['cycle_id']))
            if kind.startswith('transition_'):
                state = conn.execute('SELECT account_scope_hash,ticker,event_family,broker_subject_id FROM transition_states WHERE state_identity=?', (row['state_identity'],)).fetchone()
                if state is None or state[0] != resource.account_hash:
                    raise EvidenceUnavailable('BROKEN_SOURCE_LINK')
                source_ids.append(row['state_identity'])
            if kind == 'evaluation_events':
                evaluation = conn.execute('SELECT account_scope_hash FROM daily_evaluations WHERE evaluation_id=?', (row['evaluation_id'],)).fetchone()
                if evaluation is None or evaluation[0] != resource.account_hash:
                    raise EvidenceUnavailable('BROKEN_SOURCE_LINK')
                source_ids.append(row['evaluation_id'])
                if _portfolio_read_version(conn) == 4:
                    dispatch = conn.execute('SELECT execution_target FROM daily_evaluation_dispatches WHERE evaluation_id=?', (row['evaluation_id'],)).fetchone()
                    if dispatch and dispatch[0] is not None and dispatch[0] != resource.target:
                        raise EvidenceUnavailable('SCOPE_CONFLICT')
            if kind == 'divergences':
                snapshot = conn.execute('SELECT account_scope_hash,cycle_id,observation_id FROM portfolio_snapshots WHERE snapshot_id=?', (row['snapshot_id'],)).fetchone()
                if snapshot is None or snapshot['account_scope_hash'] != resource.account_hash:
                    raise EvidenceUnavailable('BROKEN_SOURCE_LINK')
                _check_run(conn, resource, snapshot['cycle_id'])
                sid = row['snapshot_id']
                source_ids.extend((snapshot['cycle_id'], snapshot['observation_id']))
        record = _wire_record(resource, kind, row, key, row[time_key], fields, conn=conn,
                              snapshot_id=sid, source_ids=source_ids)
        extra = []
        if kind.startswith('transition_'):
            extra.extend((name, _clean(state[name])) for name in ('ticker', 'event_family', 'broker_subject_id'))
            if kind == 'transition_observations':
                # Terminal meaning comes from saved state code, not mutable active=0.
                recovered = row['state_code'] in {'FILLED', 'RESOLVED', 'RECOVERED', 'STOPPED'}
                prior = conn.execute('SELECT 1 FROM transition_observations WHERE state_identity<>? AND id<? AND state_identity IN (SELECT state_identity FROM transition_states WHERE account_scope_hash=? AND COALESCE(ticker,\'\')=COALESCE(?,\'\') AND event_family=? AND COALESCE(broker_subject_id,\'\')=COALESCE(?,\'\')) LIMIT 1',
                    (row['state_identity'], row['id'], resource.account_hash, state['ticker'], state['event_family'], state['broker_subject_id'])).fetchone()
                extra.append(('producer_event_code', 'STATE_RECOVERED' if recovered else 'STATE_CHANGED' if prior else 'STATE_BEGIN'))
        if kind in {'candidates', 'evaluation_events'}:
            detail = _json(row['detail_json'])
            allowed = ('rank', 'screen_reason') if kind == 'candidates' else ('reason', 'provider', 'model', 'attempt', 'attempts')
            if isinstance(detail, dict):
                extra.extend((name, _clean(detail[name])) for name in allowed
                             if name in detail and (detail[name] is None or type(detail[name]) in {str, int, float, bool}))
        if kind == 'evaluations':
            if 'dispatch_state' in row.keys():
                target = row['execution_target']
                if target is not None and target != resource.target:
                    raise EvidenceUnavailable('SCOPE_CONFLICT')
                extra.extend((name, _clean(row[name])) for name in
                    ('execution_target','dispatch_state','dispatch_id','envelope_hash',
                     'dispatched_at','dispatch_finalized_at','execution_intent_id'))
                if row['dispatch_id']:
                    source_ids = record.selection.source_ids + (row['dispatch_id'],)
                    record = replace(record, selection=replace(record.selection, source_ids=source_ids))
                record = replace(record, envelope=replace(record.envelope,
                    provenance='saved_daily_dispatch' if target else 'saved_daily_dispatch_unknown_target'))
            event = conn.execute('SELECT id,event_type,action,confidence,reason_code,detail_json,observed_at FROM daily_evaluation_events WHERE evaluation_id=? AND event_type IN (?,?) ORDER BY id DESC LIMIT 1',
                (row['evaluation_id'], 'SIGNAL_FINALIZED', 'LLM_UNAVAILABLE')).fetchone()
            if event:
                detail = _json(event['detail_json'])
                extra.extend((name, _clean(event[name])) for name in ('action', 'confidence', 'reason_code'))
                extra.append(('terminal_event_type', event['event_type']))
                extra.append(('reason', _clean(detail.get('reason')) if isinstance(detail, dict) else None))
                record = replace(record, envelope=replace(record.envelope, source_observed_at=_stamp(event['observed_at'])),
                    selection=replace(record.selection, source_ids=record.selection.source_ids + (f'evaluation_events:{event["id"]}',)))
        if kind == 'orders':
            provenance = 'saved_broker_progression' if row['event_type'] in {'BROKER_OBSERVED', 'RECONCILED'} else 'saved_local_intent'
            record = replace(record, envelope=replace(record.envelope, provenance=provenance))
        if extra:
            # Multiple reason fields remain bounded together, including fixed evidence metadata.
            values = record.fields + tuple(extra)
            if sum(len(str(value).encode()) for _, value in values) > 10000:
                values = tuple((key, value[:512] if isinstance(value, str) else value) for key, value in values)
            record = replace(record, fields=values)
        return replace(record, envelope=replace(record.envelope, query_at=self.clock()))

    def _workers(self, scope=None):
        workers = []
        for resource in self._resources(scope, 'portfolio'):
            try:
                with _transaction(resource) as conn:
                    lifecycle = conn.execute("SELECT * FROM transition_states WHERE account_scope_hash=? AND event_family='INTRADAY_LIFECYCLE' ORDER BY julianday(last_observed_at) DESC,id DESC LIMIT 1", (resource.account_hash,)).fetchone()
                    lease = conn.execute('SELECT state,heartbeat_at,cycle_id,command FROM mutation_leases WHERE account_scope_hash=?', (resource.account_hash,)).fetchone()
                    # Outer-cycle identity comes from the linked snapshot, never iteration.cycle_id.
                    observation = conn.execute('''SELECT w.iteration_id,w.terminal_status,s.snapshot_id,s.cycle_id,
                        s.observation_id,o.id,o.observed_at,o.detail_json
                        FROM watch_observations o JOIN watch_iterations w ON w.iteration_id=o.iteration_id
                        JOIN portfolio_snapshots s ON s.snapshot_id=w.snapshot_id
                        WHERE s.account_scope_hash=?
                        ORDER BY julianday(o.observed_at) DESC,o.id DESC LIMIT 1''', (resource.account_hash,)).fetchone()
                    ids, sid, observed, cadence = [], None, None, None
                    state, expected = 'UNKNOWN', None
                    if lifecycle:
                        state = lifecycle['state_code']
                        ids.append(lifecycle['state_identity'])
                        observed = _stamp(lifecycle['last_observed_at'])
                        if state in {'STARTED', 'RUNNING'}:
                            expected, state = True, 'RUNNING'
                        elif state in {'STOPPED', 'RELEASED'}:
                            expected, state = False, 'STOPPED'
                        elif state in {'FAILED', 'INTERRUPTED', 'LEASE_LOST'}:
                            expected, state = False, 'FAILED'
                    if observation:
                        _check_run(conn, resource, observation['cycle_id'])
                        sid = observation['snapshot_id']
                        ids.extend((observation['iteration_id'], observation['cycle_id'], observation['observation_id'], str(observation['id'])))
                        watched_at = _stamp(observation['observed_at'])
                        observed = max(observed, watched_at) if observed else watched_at
                        detail = _json(observation['detail_json'])
                        recorded = detail.get('cadence_seconds') if isinstance(detail, dict) else None
                        # A documented per-observation cadence is not trading configuration.
                        if type(recorded) in {int, float} and math.isfinite(recorded) and 0 < recorded <= 86400:
                            cadence = float(recorded)
                        if observation['terminal_status'] in {'FAILED', 'INTERRUPTED'}:
                            state, expected = 'FAILED', False
                    lease_time = _stamp(lease['heartbeat_at']) if lease else None
                    if lease and lease['state'] == 'RELEASED':
                        state, expected = 'STOPPED', False
                    elif lease and lease['state'] in {'LOST', 'RECOVERY_BLOCKED'}:
                        state, expected = 'FAILED', False
                    freshness = 'UNKNOWN'
                    if expected is False and state == 'STOPPED':
                        freshness = 'NOT_EXPECTED'
                    elif expected is True and cadence is not None and observed is not None:
                        age = (self.clock() - observed).total_seconds()
                        if age < 0:
                            raise EvidenceUnavailable('FUTURE_SOURCE_TIME')
                        freshness = 'FRESH' if age <= max(180, 3 * cadence) else 'STALE'
                    env = _envelope(resource, self.clock(), conn=conn, source_observed_at=observed,
                        freshness=freshness, completeness='COMPLETE' if observation else 'UNKNOWN')
                    workers.append(WorkerDTO(env, f'{resource.id}:intraday', state, expected,
                                             cadence, lease_time, tuple(ids), sid))
            except EvidenceUnavailable as exc:
                workers.append(WorkerDTO(_envelope(resource, self.clock(), query_status='FAILED', diagnostic_code=str(exc)), f'{resource.id}:intraday'))
        return tuple(workers)

    def control_states(self, scope=None):
        result=[]
        for resource in self._resources(scope,'control'):
            try:
                with _transaction(resource) as conn:
                    scopes=sorted({(r.account_hash,r.target) for r in self._resources() if r.owner in {'service','control'}})
                    fixed=getattr(self.settings,'control_resource',None)
                    if fixed is not None:
                        scopes=sorted(fixed.registered_scopes)
                    digest=hashlib.sha256(json.dumps({'registered_scopes':[
                        {'account_scope_hash':account,'execution_target':target} for account,target in scopes
                    ]},separators=(',',':')).encode()).hexdigest()
                    setup=conn.execute("SELECT scope_hash,target FROM control_request_audit WHERE event='OWNER_SETUP'").fetchall()
                    if len(setup)!=1 or tuple(setup[0])!=(digest,'mock'):
                        raise EvidenceUnavailable('CONTROL_SCOPE_CONFLICT')
                    applied=conn.execute("SELECT * FROM control_applications WHERE result='APPLIED' ORDER BY revision DESC LIMIT 1").fetchone()
                    if applied is None:
                        raise EvidenceUnavailable('CONTROL_STATE_UNKNOWN')
                    pending=conn.execute('SELECT * FROM control_requests WHERE acceptance_revision>? ORDER BY acceptance_revision DESC LIMIT 1',(applied['revision'],)).fetchone()
                    stamp=max(_stamp(applied['applied_at']), _stamp(pending['requested_at']) if pending else _stamp(applied['applied_at']))
                    ids=(f'control_applications:{applied["application_id"]}',)+( (f'control_requests:{pending["request_id"]}',) if pending else ())
                    result.append(ControlStateDTO(_envelope(resource,self.clock(),source_observed_at=stamp,completeness='COMPLETE'),
                        pending['acceptance_revision'] if pending else applied['revision'],applied['mode'],
                        pending['action'] if pending else None,pending['request_id'] if pending else applied['request_id'],ids))
            except EvidenceUnavailable as exc:
                result.append(ControlStateDTO(_envelope(resource,self.clock(),query_status='FAILED',diagnostic_code=str(exc))))
        return tuple(result)

    def service_health(self, scope=None):
        """Saved obligations and runtime observations remain distinct trust facts.

        A 30-second poll never refreshes original config/login/session/control dates.
        UNKNOWN current sources suppress inference; only independently saved prior
        obligations establish absence. Total sleep can only be seen after resumption.
        """
        result=[]; now=self.clock(); day=str(now.astimezone(KST).date())
        controls=self.control_states(scope)
        for resource in self._resources(scope,'service'):
            try:
                with _transaction(resource) as conn:
                    records=_bounded_rows(conn,"SELECT * FROM service_expectations WHERE scope_hash=? AND target=? AND trading_date_kst=? AND producer_kind='OBSERVER_DERIVED' ORDER BY observed_at,rowid LIMIT 10001",(resource.account_hash,resource.target,day))
                    jobs=_bounded_rows(conn,'SELECT * FROM service_jobs WHERE scope_hash=? AND target=? AND trading_date_kst=? LIMIT 10001',(resource.account_hash,resource.target,day))
                    heartbeat=conn.execute('SELECT * FROM service_heartbeats WHERE generation_id IN (SELECT generation_id FROM service_generations WHERE scope_hash=? AND target=?) ORDER BY observed_at DESC LIMIT 1',(resource.account_hash,resource.target)).fetchone()
                    attention=conn.execute('SELECT * FROM service_attention_events ORDER BY event_id DESC LIMIT 1').fetchone()
                    restarts=conn.execute('SELECT COUNT(*) FROM service_restart_attempts WHERE admitted_at>?',(now.timestamp()-600,)).fetchone()[0]
                    source_health=conn.execute('SELECT * FROM service_expectation_health WHERE scope_hash=? AND target=? AND trading_date_kst=? ORDER BY event_id DESC LIMIT 1',(resource.account_hash,resource.target,day)).fetchone()
                    control=next((c for c in controls if (c.envelope.account_hash,c.envelope.target)==(resource.account_hash,resource.target)),None)
                    for kind in ('PREP','DAILY','RISK'):
                        rows=[r for r in records if r['kind']==kind]
                        current=rows[-1] if rows else None
                        # Later observations cannot overwrite the proven due interval.
                        proven=[r for r in rows if r['expected_running']=='EXPECTED' and r['due_at'] is not None and r['observed_at']<=r['due_at']]
                        obligation=proven[-1] if proven else current
                        subject=f'{resource.id}:{day}:{kind}'
                        if obligation is None:
                            result.append(ServiceHealthDTO(_envelope(resource,now,diagnostic_code='EXPECTATION_UNKNOWN'),subject,kind,trading_date_kst=day))
                            continue
                        saved=_json(obligation['evidence_json'])
                        if (not isinstance(saved,dict) or saved.get('producer_kind')!='OBSERVER_DERIVED'
                                or saved.get('scope')!={'account_scope_hash':resource.account_hash,'execution_target':resource.target}
                                or saved.get('trading_date_kst')!=day or saved.get('kind')!=kind
                                or saved.get('state')!=obligation['expected_running']):
                            raise EvidenceUnavailable('EXPECTATION_PROVENANCE_CONFLICT')
                        for column in ('config_hash','login_source_id','session_source_id','session_source_hash','control_revision','producer_kind','reason_code'):
                            if saved.get(column)!=obligation[column]:
                                raise EvidenceUnavailable('EXPECTATION_PROVENANCE_CONFLICT')
                        for column in ('config_effective_at','login_effective_at','controls_observed_at','observed_at'):
                            if _stamp(saved.get(column))!=_operational_stamp(obligation[column]):
                                raise EvidenceUnavailable('EXPECTATION_PROVENANCE_CONFLICT')
                        due=_operational_stamp(obligation['due_at']) if obligation['due_at'] is not None else None
                        deadline=_operational_stamp(obligation['expected_until']) if obligation['expected_until'] is not None else None
                        stamp=_operational_stamp(obligation['observed_at'])
                        ids=[f'service_expectations:{obligation["expectation_id"]}']
                        job=next((j for j in jobs if j['kind']==kind),None)
                        event=conn.execute('SELECT * FROM service_job_events WHERE job_id=? ORDER BY sequence DESC LIMIT 1',(job['job_id'],)).fetchone() if job else None
                        successful=conn.execute("SELECT * FROM service_job_events WHERE job_id=? AND ((state='RUNNING' AND reason_code IN ('RISK_PROTECTED','RISK_RECONCILED','RECONCILIATION_ONLY')) OR (state='COMPLETED' AND reason_code IN ('PREP_READ_ONLY','DAILY_TERMINAL','RISK_SESSION_TERMINAL'))) ORDER BY sequence DESC LIMIT 1",(job['job_id'],)).fetchone() if job else None
                        progress=_operational_stamp(successful['observed_at']) if successful else None
                        if event: ids.append(f'service_job_events:{event["event_id"]}')
                        if successful and (not event or successful['event_id']!=event['event_id']): ids.append(f'service_job_events:{successful["event_id"]}')
                        if heartbeat: ids.append(f'service_heartbeats:{heartbeat["worker_id"]}')
                        manual=bool(attention and attention['state']=='MANUAL_ATTENTION')
                        if manual: ids.append(f'service_attention:{attention["event_id"]}')
                        expected={'EXPECTED':True,'NOT_EXPECTED':False,'UNKNOWN':None}.get(current['expected_running'])
                        # Only DUE_HISTORY_UNKNOWN may use prior proven history; an
                        # unavailable current input cannot establish current health.
                        if expected is None and current['reason_code']=='DUE_HISTORY_UNKNOWN' and proven:
                            expected=True
                        if control is None or control.envelope.query_status!='OK': expected=None
                        if source_health and source_health['state']!='AVAILABLE' and source_health['observed_at']>=current['observed_at']: expected=None
                        if stamp>now or (progress and progress>now): expected=None
                        if control and control.revision is not None and control.revision>obligation['control_revision']:
                            if kind=='DAILY' and (control.applied_mode in {'PAUSED','KILLED'} or control.pending_action in {'PAUSE','KILL'}): expected=False
                            else: expected=None
                        if kind=='RISK' and deadline is not None and now>=deadline: expected=False
                        state='EXPECTATION_UNKNOWN' if expected is None else 'NOT_EXPECTED' if expected is False else 'WAITING'
                        if expected:
                            if manual: state='SERVICE_MANUAL_ATTENTION'
                            elif kind!='RISK' and deadline and now>=deadline and (job is None or job['state'] in {'MISSED','CLAIMED','DEFERRED'}): state='MISSED_SCHEDULE'
                            elif kind=='RISK' and due and now>=due:
                                hb=_operational_stamp(heartbeat['observed_at']) if heartbeat else None
                                if event and event['state'] in {'BLOCKED','UNKNOWN','FAILED'}: state=event['state']
                                elif event and event['reason_code'] not in {'RISK_PROTECTED','RISK_RECONCILED','RECONCILIATION_ONLY','RISK_SESSION_TERMINAL'}: state='BLOCKED'
                                elif (hb is None and (now-due).total_seconds()>=120) or (hb and (now-hb).total_seconds()>120): state='WORKER_STALLED'
                                elif (progress and (now-progress).total_seconds()>105) or (progress is None and (now-due).total_seconds()>=120): state='WORKER_STALLED'
                                elif hb: state='RECOVERY_BLOCKED' if heartbeat['phase']=='RECOVERY_BLOCKED' else 'RUNNING'
                            elif job:
                                state=job['state']
                        observed=max(stamp,progress or stamp)
                        if event: observed=max(observed,_operational_stamp(event['observed_at']))
                        if manual: observed=max(observed,_operational_stamp(attention['observed_at']))
                        if state=='WORKER_STALLED' and heartbeat: observed=max(observed,_operational_stamp(heartbeat['observed_at']))
                        env=_envelope(resource,now,source_observed_at=observed,completeness='COMPLETE',
                            provenance='OBSERVER_DERIVED',diagnostic_code=state if state in {'EXPECTATION_UNKNOWN','MISSED_SCHEDULE','WORKER_STALLED','BLOCKED','UNKNOWN','FAILED'} else None)
                        result.append(ServiceHealthDTO(env,subject,kind,state,expected,due,deadline,progress,tuple(ids),
                            'OBSERVER_DERIVED',day,obligation['control_revision'],obligation['session_source_id'],obligation['login_source_id'],obligation['config_hash'],
                            restarts,manual,event['reason_code'] if event and state in {'BLOCKED','UNKNOWN','FAILED'} else current['reason_code'],False if state in {'RECOVERY_BLOCKED','SERVICE_MANUAL_ATTENTION','BLOCKED','UNKNOWN','FAILED'} else None))
            except EvidenceUnavailable as exc:
                result.append(ServiceHealthDTO(_envelope(resource,now,query_status='FAILED',diagnostic_code=str(exc)),
                    resource.id,'SOURCE','SERVICE_SOURCE_UNAVAILABLE'))
        return tuple(result)

    def source_status(self, scope=None):
        statuses = []
        for resource in self._resources(scope):
            try:
                if resource.owner == 'portfolio':
                    statuses.append(self._account(resource).envelope)
                    continue
                if resource.owner in {'audit', 'soak', 'controller', 'service', 'control'}:
                    with _transaction(resource) as conn:
                        stamps = []
                        for (owner, _), (table, _, time_key, _) in _HISTORY.items():
                            if owner == resource.owner:
                                order=time_key if resource.owner in {'service','control'} else f'julianday({time_key})'
                                stamp = conn.execute(f'SELECT {time_key} FROM {table} ORDER BY {order} DESC LIMIT 1').fetchone()
                                if stamp:
                                    stamps.append(_operational_stamp(stamp[0]) if resource.owner in {'service','control'} else _stamp(stamp[0]))
                        statuses.append(_envelope(resource, self.clock(), source_observed_at=max(stamps, default=None)))
                    continue
                path = checked_path(resource.path)
                if not path.is_file():
                    raise EvidenceUnavailable('SOURCE_MISSING')
                if path.stat().st_size > 10 * 1024 * 1024:
                    raise EvidenceUnavailable('SOURCE_BYTE_BOUND')
                # Pure saved verifiers; never prepare/run a replay, backtest or shadow.
                if resource.owner == 'replay':
                    from .reporting import load_replay_results
                    load_replay_results((path,))
                elif resource.owner == 'backtest':
                    from .backtest_reporting import load_backtest_result
                    load_backtest_result(path)
                elif resource.owner == 'shadow':
                    from .shadow_reporting import load_shadow_result
                    load_shadow_result(path, proof_catalog=self.shadow_proof_catalog)
                else:
                    raise EvidenceUnavailable('UNSUPPORTED_SOURCE_OWNER')
                # File mtime/browser query is never a producer observation time.
                statuses.append(replace(_envelope(resource, self.clock(), completeness='COMPLETE'), schema_version=1))
            except (EvidenceUnavailable, ValueError, OSError, TypeError, KeyError):
                statuses.append(_envelope(resource, self.clock(), query_status='FAILED', diagnostic_code='SOURCE_UNAVAILABLE'))
        return tuple(statuses)

    def observe_alert_sources(self, cursor=None):
        previous = {}
        if cursor:
            try:
                if len(cursor) > 65536:
                    raise ValueError()
                doc = json.loads(base64.urlsafe_b64decode(cursor.encode()))
                if doc['registry'] != _identity(tuple((r.id, r.account_hash, r.target) for r in self._resources())):
                    raise ValueError()
                previous = doc['streams']
                if not isinstance(previous, dict) or len(previous) > 1024:
                    raise ValueError()
                for key, value in previous.items():
                    if (not isinstance(key, str) or len(key) > 128 or not isinstance(value, list)
                            or len(value) != 2 or not isinstance(value[0], str) or len(value[0]) != 64
                            or type(value[1]) is not int or not 0 <= value[1] <= 10000):
                        raise ValueError()
            except (ValueError, TypeError, KeyError, UnicodeError):
                raise ValueError('invalid alert source cursor') from None
        facts = []
        source_failures={}
        kinds = {'transitions', 'transition_observations', 'transition_notifications', 'lease_events',
                 'notifications', 'soak_events', 'campaigns', 'comparisons', 'orders', 'runs', 'evaluations', 'evaluation_events', 'candidates'}
        kinds.update(kind for _,kind in _OPERATIONAL_HISTORY)
        for resource in self._resources():
            try:
                with _transaction(resource) as conn:
                    for (owner, kind), (table, key, _, _) in _HISTORY.items():
                        if owner == resource.owner and kind in kinds:
                            rows = _bounded_rows(conn, f'SELECT * FROM {table} ORDER BY {key} LIMIT 10001')
                            for row in rows:
                                facts.append(self._project(conn, resource, kind, row))
                    if resource.owner == 'portfolio':
                        rows = _bounded_rows(conn, '''SELECT d.*,s.observed_at FROM portfolio_divergences d
                            JOIN portfolio_snapshots s ON s.snapshot_id=d.snapshot_id
                            WHERE s.account_scope_hash=? ORDER BY d.id LIMIT 10001''', (resource.account_hash,))
                        for row in rows:
                            facts.append(self._project(conn, resource, 'divergences', row))
            except EvidenceUnavailable as exc:
                source_failures[resource.id]=str(exc)
                continue
        scopes = {(r.account_hash, r.target) for r in self._resources()}
        for account, target in sorted(scopes):
            facts.extend(self._unresolved(ResourceScope(account, target), include_released=True))
        # Producer timestamps may collide or be backdated. Stream content checkpoints
        # also detect in-place transition-state updates; absence is never recovery.
        groups = {}
        for row in facts:
            if row.envelope.source_observed_at is not None:
                groups.setdefault(f'{row.resource_id}:{row.kind}', {})[row.record_id] = row
        positions, selected = dict(previous), []
        for stream in sorted(groups):
            rows = sorted(groups[stream].values(), key=lambda row: (
                row.envelope.source_observed_at, row.record_id))
            digest = _identity(tuple((row.record_id, row.envelope.source_observed_at,
                                      row.fields, row.selection.source_ids) for row in rows))
            old = previous.get(stream)
            offset = old[1] if old and old[0] == digest else 0
            count = min(100 - len(selected), len(rows) - offset)
            if count > 0:
                selected.extend(rows[offset:offset + count])
                offset += count
            positions[stream] = [digest, offset]
            if len(selected) == 100:
                break
        next_cursor = base64.urlsafe_b64encode(json.dumps({'registry': _identity(tuple((r.id, r.account_hash, r.target) for r in self._resources())), 'streams': positions}, separators=(',', ':')).encode()).decode()
        if len(next_cursor) > 65536:
            raise EvidenceUnavailable('ALERT_CURSOR_BOUND')
        health=self.service_health()
        for item in health:
            if item.envelope.query_status!='OK':
                source_failures[item.envelope.resource_id]=item.envelope.diagnostic_code or 'SOURCE_UNAVAILABLE'
        sources=tuple(replace(s,query_status='FAILED',diagnostic_code=source_failures[s.resource_id])
            if s.resource_id in source_failures else s for s in self.source_status())
        return AlertSourceBatch(self.clock(), tuple(selected), self._workers(),
                                sources, next_cursor, health)

    def list_records(self, kind, scope, period=None, cursor=None, limit=50):
        if kind not in _KINDS or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('invalid bounded selector')
        period = period or PeriodSelection.for_days(self.clock())
        if not isinstance(period, PeriodSelection):
            raise ValueError('invalid period')
        snapshot_bindings = tuple((r.id, self._account(r).snapshot_id) for r in self._resources(scope, 'portfolio')) if kind in {'holdings', 'fills', 'broker_orders', 'orders'} else ()
        selection = _identity(kind, scope, period.start.isoformat(), period.end.isoformat(), snapshot_bindings)
        after = None
        if cursor:
            try:
                if len(cursor) > 2048:
                    raise ValueError()
                payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
                if payload['selection'] != selection or len(payload['last']) != 3:
                    raise ValueError()
                after = tuple(payload['last'])
                _stamp(after[0])
            except (ValueError, KeyError, TypeError, UnicodeError):
                raise ValueError('invalid scoped cursor') from None
        records, envelopes, total = [], [], 0
        for resource in self._resources(scope):
            spec = _HISTORY.get((resource.owner, kind))
            if spec is None:
                if resource.owner == 'portfolio' and kind in {'holdings', 'fills', 'broker_orders', 'orders'}:
                    account = self._account(resource)
                    rows = {'holdings': account.holdings, 'fills': account.fills,
                            'broker_orders': account.orders, 'orders': account.orders}[kind]
                    # Snapshot-backed account rows keep the same exact saved selection.
                    rows = tuple(row for row in rows if row.envelope.source_observed_at is not None
                                 and period.start <= row.envelope.source_observed_at < period.end)
                    records.extend(rows)
                    if total is not None:
                        total += len(rows)
                    envelopes.append(account.envelope)
                continue
            table, key, time_key, _ = spec
            try:
                with _transaction(resource) as conn:
                    query_source = _table_source(table, portfolio_version=
                        _portfolio_read_version(conn) if resource.owner == 'portfolio' else None)
                    where = f'julianday({time_key})>=julianday(?) AND julianday({time_key})<julianday(?)'
                    args = [period.start.isoformat(), period.end.isoformat()]
                    if resource.owner == 'portfolio' and 'account_scope_hash' in contracts.PORTFOLIO_REPORT_SCHEMA[table]:
                        where += ' AND account_scope_hash=?'
                        args.append(resource.account_hash)
                    if conn.execute(f'SELECT 1 FROM {query_source} WHERE julianday({time_key}) IS NULL LIMIT 1').fetchone():
                        raise EvidenceUnavailable('INVALID_SOURCE_TIME')
                    # Validate all selected attribution rather than silently count mixed rows.
                    selected = _bounded_rows(conn, f'SELECT * FROM {query_source} WHERE {where} ORDER BY julianday({time_key}),{key} LIMIT 10001', args)
                    projected = [self._project(conn, resource, kind, row) for row in selected]
                    if total is not None:
                        total += len(projected)
                    if after:
                        after_time, after_resource, after_id = after
                        tail_where, tail_args = where, list(args)
                        if resource.id < after_resource:
                            tail_where += f' AND julianday({time_key})>julianday(?)'
                            tail_args.append(after_time)
                        elif resource.id > after_resource:
                            tail_where += f' AND julianday({time_key})>=julianday(?)'
                            tail_args.append(after_time)
                        else:
                            tail_where += f" AND (julianday({time_key})>julianday(?) OR (julianday({time_key})=julianday(?) AND (? || CAST({key} AS TEXT))>?))"
                            tail_args.extend((after_time, after_time, kind + ':', after_id))
                        tail_args.append(limit + 1)
                        tail_rows = conn.execute(f'SELECT * FROM {query_source} WHERE {tail_where} ORDER BY julianday({time_key}),CAST({key} AS TEXT) LIMIT ?', tail_args).fetchall()
                        records.extend(self._project(conn, resource, kind, row) for row in tail_rows)
                    else:
                        records.extend(projected)
                    envelopes.append(_envelope(resource, self.clock(), conn=conn, completeness='COMPLETE',
                        source_observed_at=max((r.envelope.source_observed_at for r in projected), default=None)))
            except EvidenceUnavailable as exc:
                total = None
                envelopes.append(_envelope(resource, self.clock(), query_status='FAILED', diagnostic_code=str(exc)))
        def order(row):
            return (row.envelope.source_observed_at.isoformat(), row.resource_id, row.record_id)
        records.sort(key=order)
        if after:
            records = [row for row in records if order(row) > after]
        page_rows = tuple(records[:limit])
        next_cursor = None
        if len(records) > limit:
            next_cursor = base64.urlsafe_b64encode(json.dumps({'selection': selection, 'last': order(page_rows[-1])}).encode()).decode()
        return RecordPage(kind, selection, page_rows, total, next_cursor, tuple(envelopes),
            self._unresolved(scope) if kind == 'orders' else ())

    def get_record(self, resource_id, record_id):
        resource = self.settings.resource(resource_id)
        if not isinstance(record_id, str) or len(record_id) > 512 or ':' not in record_id:
            raise ValueError('invalid record selector')
        kind, key = record_id.split(':', 1)
        if kind in {'holdings', 'orders', 'fills'} and resource.owner == 'portfolio':
            if ':' not in key:
                raise ValueError('invalid snapshot selector')
            sid, _ = key.rsplit(':', 1)
            account = ReadOnlyPortfolioRepository(resource, clock=self.clock).account(sid)
            record = next((row for rows in (account.holdings, account.orders, account.fills)
                           for row in rows if row.record_id == record_id), None)
        else:
            spec = _HISTORY.get((resource.owner, kind))
            if spec is None:
                raise ValueError('invalid kind for owner')
            table, pk, _, _ = spec
            with _transaction(resource) as conn:
                query_source = _table_source(table, portfolio_version=
                    _portfolio_read_version(conn) if resource.owner == 'portfolio' else None)
                row = conn.execute(f'SELECT * FROM {query_source} WHERE {pk}=?', (key,)).fetchone()
                record = self._project(conn, resource, kind, row) if row else None
        if record is None:
            raise EvidenceUnavailable('RECORD_NOT_FOUND')
        return record

    def get_evidence(self, resource_id, record_id):
        # This is the same fixed authorized field map, never a raw payload/model dump.
        return self.get_record(resource_id, record_id)

    def _unresolved(self, scope, *, include_released=False):
        records = []
        for resource in self._resources(scope, 'portfolio'):
            account = self._account(resource)
            records.extend(row for row in account.orders
                           if row.data.get('remaining_quantity', 0) > 0 or row.data.get('status') == 'UNKNOWN')
        for resource in self._resources(scope, 'audit'):
            try:
                with _transaction(resource) as conn:
                    # Local intent and broker observation remain different records.
                    latest = _bounded_rows(conn, 'SELECT e.* FROM order_events e WHERE e.id=(SELECT MAX(last.id) FROM order_events last WHERE last.order_intent_id=e.order_intent_id) ORDER BY e.id LIMIT 10001')
                    local = tuple(self._project(conn, resource, 'orders', row) for row in latest
                        if not (row['event_type'] in {'BROKER_OBSERVED', 'RECONCILED'}
                                and row['broker_status'] in {'FILLED', 'CANCELLED', 'REJECTED'}
                                and row['unfilled_qty'] == 0 and row['broker_order_id']))
                    records.extend(local)
                    self._cache[('unresolved', resource.id)] = local
            except EvidenceUnavailable as exc:
                records.extend(replace(row, envelope=replace(row.envelope, query_at=self.clock(),
                    query_status='FAILED', diagnostic_code=str(exc)))
                    for row in self._cache.get(('unresolved', resource.id), ()))
        for resource in self._resources(scope, 'soak'):
            try:
                with _transaction(resource) as conn:
                    frozen = _bounded_rows(conn, "SELECT * FROM soak_ticker_freezes WHERE state='FROZEN' ORDER BY id LIMIT 10001")
                    for row in frozen:
                        released = conn.execute("SELECT * FROM soak_ticker_freezes WHERE freeze_id=? AND state='RELEASED' ORDER BY id DESC LIMIT 1", (row['freeze_id'],)).fetchone()
                        valid = False
                        if released is not None and released['prior_transition_id'] == row['id']:
                            spec = {'COMPARISON': ('soak_comparisons', 'comparison_id', {'MATCHED'}),
                                    'AMBIGUITY_OBSERVATION': ('soak_ambiguity_observations', 'observation_id', {'NO_MATCH_CONFIRMED', 'ONE_MATCH_DETERMINATE'})}.get(released['release_evidence_type'])
                            if spec:
                                table, pk, verdicts = spec
                                proof = conn.execute(f'SELECT * FROM {table} WHERE {pk}=?', (released['release_evidence_id'],)).fetchone()
                                valid = bool(proof and proof['verdict'] in verdicts and proof['remaining_order_terminal'] == 1
                                    and all(proof[k] == row[k] for k in ('campaign_id', 'ticker', 'order_intent_id')))
                        if not valid:
                            record = self._project(conn, resource, 'freezes', row)
                            # A missing primary link does not remove an active risk subject.
                            linked = False
                            for primary in self._resources(ResourceScope(resource.account_hash, resource.target), 'audit'):
                                try:
                                    with _transaction(primary) as audit:
                                        linked = audit.execute('SELECT 1 FROM order_events WHERE order_intent_id=? AND ticker=? LIMIT 1',
                                                               (row['order_intent_id'], row['ticker'])).fetchone() is not None
                                except EvidenceUnavailable:
                                    pass
                                if linked:
                                    break
                            if not linked:
                                record = replace(record, envelope=replace(record.envelope, completeness='UNKNOWN', diagnostic_code='BROKEN_SOURCE_LINK'))
                            records.append(record)
                        elif include_released:
                            record = self._project(conn, resource, 'freezes', released)
                            records.append(replace(record, fields=record.fields + (('release_validated', True),)))
            except EvidenceUnavailable as exc:
                # Query failure is never positive recovery; preserve the last risk facts.
                records.extend(replace(row, envelope=replace(row.envelope, query_at=self.clock(),
                    query_status='FAILED', diagnostic_code=str(exc)))
                    for row in self._cache.get(('unresolved', resource.id), ()))
                continue
            self._cache[('unresolved', resource.id)] = tuple(r for r in records if r.resource_id == resource.id)
            while len(self._cache) > 128:
                self._cache.popitem(last=False)
        return tuple(records)
