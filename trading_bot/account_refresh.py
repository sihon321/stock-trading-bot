"""Independent mock balance reader. No execution/LLM/service composition."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import math
import os
from pathlib import Path
import signal
import sqlite3
import threading
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
import typer

from .account_view_contracts import ACCOUNT_VIEW_OWNER, ACCOUNT_VIEW_VERSION, REFRESH_REASONS
from .kis_auth import KisAuthConfig, KisTokenManager
from .kis_order import KisOrderAccount, KisOrderAdapter, MOCK_TR_PROFILE_CANDIDATES
from .portfolio import canonical_account_scope_hash
from .soak_models import PageCompleteness
from .web_config import checked_path, overlaps

MOCK_DOMAIN = 'https://openapivts.koreainvestment.com:29443'
BALANCE_PATH = '/uapi/domestic-stock/v1/trading/inquire-balance'
app = typer.Typer(no_args_is_help=True, help='모의계좌 조회 전용 갱신 · 주문/LLM 실행 없음')


class AccountRefreshSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid', hide_input_in_errors=True)
    db_path: Path
    token_cache_path: Path
    app_key: SecretStr = Field(repr=False)
    app_secret: SecretStr = Field(repr=False)
    account_cano: SecretStr = Field(repr=False)
    account_product_code: str = Field(default='01', pattern=r'^\d{2}$')
    expected_account_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    interval_seconds: int = Field(default=60, ge=60, le=3600)
    page_cap: int = Field(default=10, ge=1, le=10)

    @model_validator(mode='after')
    def validate_scope(self):
        cano = self.account_cano.get_secret_value()
        if not self.app_key.get_secret_value().strip() or not self.app_secret.get_secret_value().strip():
            raise ValueError('MOCK_CREDENTIALS_REQUIRED')
        if len(cano) != 8 or not cano.isdigit():
            raise ValueError('INVALID_MOCK_ACCOUNT')
        if canonical_account_scope_hash('mock', f'{cano[-4:]}:{self.account_product_code}') != self.expected_account_hash:
            raise ValueError('ACCOUNT_SCOPE_CONFLICT')
        for path in (self.db_path, self.token_cache_path):
            checked_path(path)
        if overlaps(self.db_path, self.token_cache_path):
            raise ValueError('ACCOUNT_STORAGE_OVERLAP')
        return self


def load_settings(config: Path):
    path = checked_path(config)
    if (not path.is_file() or path.stat().st_uid != os.getuid()
            or path.stat().st_mode & 0o077 or path.stat().st_size > 65536):
        raise ValueError('PROTECTED_ACCOUNT_CONFIG_REQUIRED')
    settings = AccountRefreshSettings(**json.loads(path.read_text()))
    if overlaps(path, settings.db_path) or overlaps(path, settings.token_cache_path):
        raise ValueError('ACCOUNT_CONFIG_OVERLAP')
    return settings


class MockBalanceTransport:
    """Network boundary allows one mock GET endpoint and OAuth token issuance."""
    def __init__(self, client, account):
        self._client, self._account = client, account

    def get(self, url, **kwargs):
        params, headers = kwargs.get('params', {}), kwargs.get('headers', {})
        if (url != MOCK_DOMAIN + BALANCE_PATH or headers.get('tr_id') != 'VTTC8434R'
                or params.get('CANO') != self._account.cano
                or params.get('ACNT_PRDT_CD') != self._account.account_product_code):
            raise ValueError('ACCOUNT_QUERY_BOUNDARY')
        return self._client.get(url, **kwargs)

    def post(self, url, **kwargs):
        if url != MOCK_DOMAIN + '/oauth2/tokenP':
            raise ValueError('ACCOUNT_POST_PROHIBITED')
        return self._client.post(url, **kwargs)


def number(value, *, signed=False):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) and (signed or result >= 0) else None
    except (TypeError, ValueError, OverflowError):
        return None


def normalize_balance(balance):
    if balance.completeness is not PageCompleteness.COMPLETE or balance.page_count <= 0:
        return None, 'INCOMPLETE_PAGES'
    cash = number(balance.summary.get('dnca_tot_amt'))
    total = number(balance.summary.get('tot_evlu_amt'))
    profit = number(balance.summary.get('evlu_pfls_smtl_amt'), signed=True)
    if cash is None or total is None:
        return None, 'INVALID_BALANCE'
    holdings, seen = [], set()
    if len(balance.rows) > 10000:
        return None, 'INVALID_BALANCE'
    for row in balance.rows:
        ticker = str(row.get('pdno', ''))
        quantity, orderable = number(row.get('hldg_qty')), number(row.get('ord_psbl_qty'))
        average = number(row.get('pchs_avg_pric'))
        if (len(ticker) != 6 or not ticker.isdigit() or ticker in seen
                or quantity is None or orderable is None or average is None
                or not quantity.is_integer() or not orderable.is_integer() or orderable > quantity):
            return None, 'INVALID_BALANCE'
        seen.add(ticker)
        if quantity == 0:
            continue
        holdings.append(dict(ticker=ticker, quantity=int(quantity), orderable_quantity=int(orderable),
            average_price=average, current_price=number(row.get('prpr')),
            evaluation_amount=number(row.get('evlu_amt')),
            unrealized_profit=number(row.get('evlu_pfls_amt'), signed=True),
            unrealized_return=number(row.get('evlu_pfls_rt'), signed=True)))
    complete = profit is not None and all(all(h[k] is not None for k in
        ('current_price', 'evaluation_amount', 'unrealized_profit', 'unrealized_return')) for h in holdings)
    return dict(available_cash=cash, total_evaluation=total, unrealized_value=profit,
        valuation_complete=int(complete), page_count=balance.page_count, holdings=holdings), (
        'COMPLETE' if complete else 'VALUATION_MISSING')


@contextmanager
def store_connection(path):
    path = checked_path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.parent.stat().st_uid != os.getuid() or path.parent.stat().st_mode & 0o077:
        raise ValueError('PROTECTED_ACCOUNT_STORAGE_REQUIRED')
    if path.exists() and (path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077):
        raise ValueError('PROTECTED_ACCOUNT_STORAGE_REQUIRED')
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    os.close(fd)
    with sqlite3.connect(path, timeout=5) as conn:
        conn.execute('PRAGMA foreign_keys=ON')
        yield conn


def initialize_store(conn, account_hash):
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if tables:
        row = conn.execute('SELECT owner,version,account_hash,target FROM account_view_metadata').fetchall()
        if row != [(ACCOUNT_VIEW_OWNER, ACCOUNT_VIEW_VERSION, account_hash, 'mock')]:
            raise ValueError('ACCOUNT_STORAGE_SCOPE_CONFLICT')
        return
    conn.execute('CREATE TABLE account_view_metadata(owner TEXT PRIMARY KEY, version INTEGER NOT NULL, account_hash TEXT NOT NULL, target TEXT NOT NULL)')
    conn.execute('CREATE TABLE account_view_attempts(attempt_id TEXT PRIMARY KEY, observed_at TEXT NOT NULL, status TEXT NOT NULL, reason_code TEXT NOT NULL, snapshot_id TEXT)')
    conn.execute('CREATE TABLE account_view_snapshots(snapshot_id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL UNIQUE REFERENCES account_view_attempts(attempt_id), observed_at TEXT NOT NULL, available_cash REAL NOT NULL, total_evaluation REAL NOT NULL, unrealized_value REAL, valuation_complete INTEGER NOT NULL, page_count INTEGER NOT NULL)')
    conn.execute('CREATE TABLE account_view_holdings(snapshot_id TEXT NOT NULL REFERENCES account_view_snapshots(snapshot_id), ticker TEXT NOT NULL, quantity INTEGER NOT NULL, orderable_quantity INTEGER NOT NULL, average_price REAL NOT NULL, current_price REAL, evaluation_amount REAL, unrealized_profit REAL, unrealized_return REAL, PRIMARY KEY(snapshot_id,ticker))')
    conn.execute('INSERT INTO account_view_metadata VALUES (?,?,?,?)', (ACCOUNT_VIEW_OWNER, ACCOUNT_VIEW_VERSION, account_hash, 'mock'))
    conn.execute('PRAGMA user_version=1')


def record_refresh(settings, data, reason, *, observed_at=None):
    stamp = observed_at or datetime.now(timezone.utc)
    if stamp.tzinfo is None or reason not in REFRESH_REASONS:
        raise ValueError('INVALID_REFRESH_RECORD')
    attempt, snapshot = str(uuid4()), str(uuid4()) if data is not None else None
    with store_connection(settings.db_path) as conn:
        conn.execute('BEGIN IMMEDIATE')
        initialize_store(conn, settings.expected_account_hash)
        conn.execute('INSERT INTO account_view_attempts VALUES (?,?,?,?,?)',
            (attempt, stamp.isoformat(), 'COMPLETE' if data is not None else 'FAILED', reason, snapshot))
        if data is not None:
            conn.execute('INSERT INTO account_view_snapshots VALUES (?,?,?,?,?,?,?,?)',
                (snapshot, attempt, stamp.isoformat(), data['available_cash'], data['total_evaluation'],
                 data['unrealized_value'], data['valuation_complete'], data['page_count']))
            conn.executemany('INSERT INTO account_view_holdings VALUES (?,?,?,?,?,?,?,?,?)',
                [(snapshot, *(h[k] for k in ('ticker', 'quantity', 'orderable_quantity', 'average_price',
                    'current_price', 'evaluation_amount', 'unrealized_profit', 'unrealized_return'))) for h in data['holdings']])
    return reason


def refresh_once(settings, *, client=None):
    own_client = client is None
    client = client or httpx.Client(follow_redirects=False, trust_env=False)
    try:
        account = KisOrderAccount(settings.account_cano.get_secret_value(), settings.account_product_code)
        transport = MockBalanceTransport(client, account)
        tokens = KisTokenManager(KisAuthConfig(MOCK_DOMAIN, settings.app_key.get_secret_value(),
            settings.app_secret.get_secret_value(), 600, 0.5, 1, 1.0, 5.0, settings.token_cache_path), client=transport)
        adapter = KisOrderAdapter(token_manager=tokens, domain=MOCK_DOMAIN, tr_id_profile='mock',
            client=transport, max_retries=1, timeout_seconds=5.0)
        profile = next(p for p in MOCK_TR_PROFILE_CANDIDATES if p.version == 'official-example-v1')
        balance = adapter.query_balance_pages(account=account, profile=profile, page_cap=settings.page_cap)
        data, reason = normalize_balance(balance)
        if data is None and balance.reason_code != 'COMPLETE':
            reason = 'AUTH_UNAVAILABLE' if 'AUTH' in balance.reason_code or 'TOKEN' in balance.reason_code else 'QUERY_UNAVAILABLE'
    except Exception:
        data, reason = None, 'REFRESH_FAILED'
    finally:
        if own_client:
            client.close()
    return record_refresh(settings, data, reason)


@app.command('once')
def once(config: Path = typer.Option(..., '--config')):
    try:
        reason = refresh_once(load_settings(config))
    except Exception:
        typer.echo('계좌 조회 설정 또는 저장소를 확인하세요. ACCOUNT_REFRESH_UNAVAILABLE', err=True)
        raise typer.Exit(1) from None
    typer.echo('계좌 조회 결과: ' + reason)
    if reason not in {'COMPLETE', 'VALUATION_MISSING'}:
        raise typer.Exit(1)


@app.command('watch')
def watch(config: Path = typer.Option(..., '--config')):
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    try:
        settings = load_settings(config)
        with store_connection(settings.db_path) as conn:
            conn.execute('BEGIN IMMEDIATE')
            initialize_store(conn, settings.expected_account_hash)
        lock_path = checked_path(settings.db_path.with_suffix('.lock'))
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            while not stop.is_set():
                typer.echo('계좌 조회 결과: ' + refresh_once(settings))
                stop.wait(settings.interval_seconds)
    except Exception:
        typer.echo('계좌 조회 작업을 시작하거나 유지할 수 없습니다. ACCOUNT_REFRESH_UNAVAILABLE', err=True)
        raise typer.Exit(1) from None


if __name__ == '__main__':
    app()
