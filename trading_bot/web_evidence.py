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

from . import evidence_contracts as contracts
from .web_config import checked_path
from .web_models import (AccountDTO, EvidenceRecord, EvidenceSelection, OverviewDTO,
                         ResourceScope, SourceEnvelope)


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

    def account(self):
        r, now = self.resource, self.clock()
        with _transaction(r) as conn:
            snapshots = _bounded_rows(conn, 'SELECT * FROM portfolio_snapshots WHERE account_scope_hash=? ORDER BY observed_at DESC,snapshot_id DESC LIMIT 10001', (r.account_hash,))
            for snapshot in snapshots:
                _stamp(snapshot['observed_at'])
                _check_run(conn, r, snapshot['cycle_id'])
            latest = snapshots[0] if snapshots else None
            complete = next((s for s in snapshots if s['completeness'] == 'COMPLETE'
                             and s['daily_page_count'] > 0 and s['balance_page_count'] > 0), None)
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
                        tuple((k, row[k]) for k in row.keys() if k != 'snapshot_id')))
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
        return OverviewDTO(self.clock(), accounts=tuple(self._account(r) for r in self._resources(scope, 'portfolio')))
