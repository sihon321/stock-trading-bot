"""Bounded saved evidence services. No source mutation or live capabilities."""
from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import math
import sqlite3
import base64
import re

from . import evidence_contracts as contracts
from .web_config import checked_path
from .web_models import (AccountDTO, EvidenceRecord, EvidenceSelection, OverviewDTO,
                         ResourceScope, SourceEnvelope, PeriodSelection, RecordPage)

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
    ('audit', 'notifications'): ('notification_attempts', 'id', 'observed_at', ('run_id', 'ticker', 'kind', 'delivery_status', 'failure_category')),
    ('soak', 'freezes'): ('soak_ticker_freezes', 'id', 'observed_at', ('freeze_id', 'campaign_id', 'ticker', 'order_intent_id', 'freeze_kind', 'state', 'release_evidence_type', 'release_evidence_id')),
    ('soak', 'campaigns'): ('soak_campaigns', 'campaign_id', 'created_at', ('campaign_id', 'state', 'campaign_kind', 'safety_failure_code', 'availability_failure_code', 'target_eligible_days')),
    ('soak', 'comparisons'): ('soak_comparisons', 'id', 'observed_at', ('comparison_id', 'campaign_id', 'run_id', 'snapshot_id', 'ticker', 'order_intent_id', 'verdict', 'remaining_order_terminal')),
}
_KINDS = {kind for _, kind in _HISTORY} | {'holdings', 'fills', 'broker_orders'}


def _clean(value):
    if not isinstance(value, str):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return value
    # Sanitize before truncation, so a secret spanning the boundary is still removed.
    value = re.sub(r'(?i)\b(?:sk-|ghp_|github_pat_)[a-z0-9_-]+', '[REDACTED]', value)
    value = re.sub(r'(?i)\bBearer\s+[^\s]+', 'Bearer [REDACTED]', value)
    value = re.sub(r'(?i)\b(?:cano|account(?:_number)?|api[_ -]?key|app[_ -]?key|secret|token|password|cookie|session)[\s:=]+[^\s,;]+', '[REDACTED]', value)
    value = re.sub(r'\b\d{8,14}(?:-\d{2})?\b', '[REDACTED]', value)
    value = ''.join(c if ord(c) >= 32 and not (127 <= ord(c) <= 159) else ' ' for c in value)
    return value[:4096]


def _wire_record(resource, kind, row, key, stamp, fields, *, snapshot_id=None, source_ids=(), completeness='COMPLETE'):
    rid = f'{kind}:{row[key]}'
    if len(rid) > 512 or _clean(rid) != rid or any(_clean(str(v)) != str(v) for v in source_ids):
        raise EvidenceUnavailable('INVALID_SOURCE_ID')
    projected = tuple((name, _clean(row[name])) for name in fields)
    if sum(len(str(v).encode()) + len(k) for k, v in projected) > 10000:
        projected = tuple((name, value[:512] if isinstance(value, str) else value) for name, value in projected)
    return EvidenceRecord(rid, kind, _envelope(resource, datetime.now(timezone.utc),
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


def _envelope(resource, now, **values):
    return SourceEnvelope(resource.id, resource.owner,
        {'portfolio': 3, 'audit': 3, 'soak': 2, 'controller': 1}.get(resource.owner),
        resource.account_hash, resource.target, now, **values)


@contextmanager
def _transaction(resource):
    conn = None
    try:
        path = checked_path(resource.path)
        if not path.is_file():
            raise EvidenceUnavailable('SOURCE_MISSING')
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
                   'controller': contracts.CONTROLLER_REPORT_SCHEMA}
        schema = schemas.get(resource.owner)
        if schema is None:
            raise EvidenceUnavailable('UNSUPPORTED_SOURCE_OWNER')
        if resource.owner == 'portfolio':
            version = conn.execute('SELECT version FROM portfolio_schema_metadata WHERE owner=?',
                                   (contracts.PORTFOLIO_SCHEMA_OWNER,)).fetchone()
            actual = version[0] if version else None
        else:
            actual = conn.execute('PRAGMA user_version').fetchone()[0]
        expected = {'portfolio': 3, 'audit': 3, 'soak': 2, 'controller': 1}[resource.owner]
        if actual != expected:
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
                return AccountDTO(_envelope(r, now, diagnostic_code='NO_COMPLETE_SNAPSHOT'),
                    _selection(r, 'account'), latest_attempt_id=latest['snapshot_id'] if latest else None,
                    latest_attempt_status=latest['completeness'] if latest else 'UNKNOWN')
            amounts = (complete['available_cash'], complete['total_evaluation'])
            if any(not isinstance(v, (float, int)) or not math.isfinite(v) or v < 0 for v in amounts):
                raise EvidenceUnavailable('INVALID_ACCOUNT_TOTAL')
            sid = complete['snapshot_id']
            env = _envelope(r, now, source_observed_at=_stamp(complete['observed_at']), completeness='COMPLETE')
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
    def __init__(self, settings, *, clock=lambda: datetime.now(timezone.utc)):
        self.settings, self.clock = settings, clock
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
                           unresolved=self._unresolved(scope))

    def _project(self, conn, resource, kind, row):
        _, key, time_key, fields = _HISTORY[(resource.owner, kind)]
        source_ids = []
        sid = None
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
                state = conn.execute('SELECT account_scope_hash FROM transition_states WHERE state_identity=?', (row['state_identity'],)).fetchone()
                if state is None or state[0] != resource.account_hash:
                    raise EvidenceUnavailable('BROKEN_SOURCE_LINK')
                source_ids.append(row['state_identity'])
        record = _wire_record(resource, kind, row, key, row[time_key], fields,
                              snapshot_id=sid, source_ids=source_ids)
        return replace(record, envelope=replace(record.envelope, query_at=self.clock()))

    def list_records(self, kind, scope, period=None, cursor=None, limit=50):
        if kind not in _KINDS or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('invalid bounded selector')
        period = period or PeriodSelection.for_days(self.clock())
        if not isinstance(period, PeriodSelection):
            raise ValueError('invalid period')
        selection = _identity(kind, scope, period.start.isoformat(), period.end.isoformat())
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
                    where = f'julianday({time_key})>=julianday(?) AND julianday({time_key})<julianday(?)'
                    args = [period.start.isoformat(), period.end.isoformat()]
                    if resource.owner == 'portfolio' and 'account_scope_hash' in contracts.PORTFOLIO_REPORT_SCHEMA[table]:
                        where += ' AND account_scope_hash=?'
                        args.append(resource.account_hash)
                    if conn.execute(f'SELECT 1 FROM {table} WHERE julianday({time_key}) IS NULL LIMIT 1').fetchone():
                        raise EvidenceUnavailable('INVALID_SOURCE_TIME')
                    # Validate all selected attribution rather than silently count mixed rows.
                    selected = _bounded_rows(conn, f'SELECT * FROM {table} WHERE {where} ORDER BY julianday({time_key}),{key} LIMIT 10001', args)
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
                        tail_rows = conn.execute(f'SELECT * FROM {table} WHERE {tail_where} ORDER BY julianday({time_key}),CAST({key} AS TEXT) LIMIT ?', tail_args).fetchall()
                        records.extend(self._project(conn, resource, kind, row) for row in tail_rows)
                    else:
                        records.extend(projected)
                    envelopes.append(_envelope(resource, self.clock(), completeness='COMPLETE',
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
                row = conn.execute(f'SELECT * FROM {table} WHERE {pk}=?', (key,)).fetchone()
                record = self._project(conn, resource, kind, row) if row else None
        if record is None:
            raise EvidenceUnavailable('RECORD_NOT_FOUND')
        return record

    def get_evidence(self, resource_id, record_id):
        # This is the same fixed authorized field map, never a raw payload/model dump.
        return self.get_record(resource_id, record_id)

    def _unresolved(self, scope):
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
