"""Display-only balance retrieval, failure retention and saved web integration."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import re
import sqlite3

import httpx
import pytest

from test_web_routes import saved_web
from test_web_security import csrf, login, web
from trading_bot.account_refresh import (AccountRefreshSettings, BALANCE_PATH, MOCK_DOMAIN,
    MockBalanceTransport, load_settings, normalize_balance, record_refresh, refresh_once)
from trading_bot.kis_order import KisOrderAccount
from trading_bot.portfolio import canonical_account_scope_hash
from trading_bot.soak_models import BrokerPageEnvelope, PageCompleteness
from trading_bot.web_config import ResourceDescriptor
from trading_bot.web_evidence import EvidenceUnavailable, OperatorEvidenceService, ReadOnlyAccountViewRepository


def balance(**changes):
    values = dict(rows=({'pdno':'005930','hldg_qty':'10','ord_psbl_qty':'8',
        'pchs_avg_pric':'70000','prpr':'69000','evlu_amt':'690000',
        'evlu_pfls_amt':'-10000','evlu_pfls_rt':'-1.43'},),
        summary={'dnca_tot_amt':'100000','tot_evlu_amt':'790000','evlu_pfls_smtl_amt':'-10000'},
        page_count=1,completeness=PageCompleteness.COMPLETE,reason_code='COMPLETE')
    values.update(changes)
    return BrokerPageEnvelope(**values)


def settings(tmp_path):
    directory = tmp_path/'account-source'
    directory.mkdir(mode=0o700)
    return AccountRefreshSettings(db_path=directory/'balance.db', token_cache_path=directory/'tokens.json',
        app_key='synthetic-key', app_secret='synthetic-secret', account_cano='12345678',
        expected_account_hash=canonical_account_scope_hash('mock','5678:01'))


def test_signed_values_optional_missing_and_no_guessed_prices():
    data, reason = normalize_balance(balance())
    assert reason == 'COMPLETE'
    assert data['unrealized_value'] == -10000
    assert data['holdings'][0]['unrealized_return'] == -1.43
    row = dict(balance().rows[0])
    row.pop('prpr')
    row['evlu_pfls_amt'] = float('nan')
    data, reason = normalize_balance(balance(rows=(row,)))
    assert reason == 'VALUATION_MISSING'
    assert data['holdings'][0]['current_price'] is None
    assert data['holdings'][0]['unrealized_profit'] is None
    data, _ = normalize_balance(balance(rows=(), summary={'dnca_tot_amt':'0','tot_evlu_amt':'0','evlu_pfls_smtl_amt':'0'}))
    assert data['holdings'] == [] and data['unrealized_value'] == 0


@pytest.mark.parametrize('case', ['pages','duplicate','quantity','total','nonfinite','bool'])
def test_invalid_balance_cannot_be_promoted(case):
    current = balance()
    if case == 'pages':
        current = replace(current,completeness=PageCompleteness.INCOMPLETE)
    elif case == 'duplicate':
        current = replace(current,rows=current.rows*2)
    elif case == 'quantity':
        current = replace(current,rows=({**current.rows[0],'ord_psbl_qty':'11'},))
    else:
        invalid = {'total':None,'nonfinite':float('inf'),'bool':True}[case]
        current = replace(current,summary={**current.summary,'tot_evlu_amt':invalid})
    assert normalize_balance(current)[0] is None


def test_refresh_boundary_only_issues_mock_balance_get_and_oauth(tmp_path):
    config = settings(tmp_path)
    calls = []
    def handler(request):
        calls.append((request.method, request.url.path))
        if request.url.path == '/oauth2/tokenP':
            return httpx.Response(200,json={'access_token':'synthetic-access','expires_in':86400})
        assert request.headers['tr_id']=='VTTC8434R'
        assert request.url.params['CANO']=='12345678'
        return httpx.Response(200,json={'rt_cd':'0','output1':[dict(row) for row in balance().rows],
            'output2':[dict(balance().summary)]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert refresh_once(config,client=client)=='COMPLETE'
        boundary=MockBalanceTransport(client,KisOrderAccount('12345678','01'))
        for path in ('/uapi/hashkey','/uapi/domestic-stock/v1/trading/order-cash'):
            with pytest.raises(ValueError,match='ACCOUNT_POST_PROHIBITED'):
                boundary.post(MOCK_DOMAIN+path,json={})
        with pytest.raises(ValueError,match='ACCOUNT_QUERY_BOUNDARY'):
            boundary.get('https://openapi.koreainvestment.com:9443'+BALANCE_PATH)
        with pytest.raises(ValueError,match='ACCOUNT_QUERY_BOUNDARY'):
            boundary.get(MOCK_DOMAIN+BALANCE_PATH,headers={'tr_id':'VTTC8434R'},params={'CANO':'87654321','ACNT_PRDT_CD':'01'})
    assert calls==[('POST','/oauth2/tokenP'),('GET',BALANCE_PATH)]
    with sqlite3.connect(config.db_path) as conn:
        assert conn.execute('SELECT unrealized_profit FROM account_view_holdings').fetchone()[0]==-10000
        assert not conn.execute("SELECT name FROM sqlite_master WHERE name IN ('order_events','mutation_leases','daily_evaluations')").fetchall()
    assert config.db_path.stat().st_mode & 0o077 == 0
    assert 'synthetic-secret' not in repr(config) and '12345678' not in repr(config)


def test_settings_reject_cross_account_real_config_and_unprotected_file(tmp_path):
    config = settings(tmp_path)
    values = config.model_dump()
    with pytest.raises(ValueError):
        AccountRefreshSettings(**{**values,'expected_account_hash':'b'*64})
    with pytest.raises(ValueError):
        AccountRefreshSettings(**{**values,'trading_mode':'real'})
    path=tmp_path/'refresh.json'
    path.write_text('{}')
    path.chmod(0o644)
    with pytest.raises(ValueError,match='PROTECTED_ACCOUNT_CONFIG_REQUIRED'):
        load_settings(path)


@pytest.fixture
def account_web(saved_web,tmp_path):
    app,client,sources=saved_web
    config=settings(tmp_path)
    # Saved web fixture identity is independently synthetic; no live credentials used.
    record_config=SimpleNamespace(db_path=config.db_path,expected_account_hash=sources.account_hash)
    data,_=normalize_balance(balance())
    record_refresh(record_config,data,'COMPLETE',observed_at=sources.clock()-timedelta(days=3))
    resource=ResourceDescriptor(id='account-display',path=config.db_path,owner='account_view',account_hash=sources.account_hash,target='mock')
    original=app.extensions['web_store'].settings
    updated=original.model_copy(update={'registered_resources':original.registered_resources+(resource,)})
    from trading_bot.web_app import create_app
    reader=OperatorEvidenceService(updated,clock=sources.clock,shadow_proof_catalog=sources.shadow_proof_catalog)
    rebuilt=create_app(updated,evidence_service=reader,clock=sources.clock)
    current=rebuilt.test_client()
    assert login(current).status_code==303
    return rebuilt,current,sources,record_config,resource


def test_last_holdings_outside_today_drilldown_and_negative_returns(account_web):
    _,client,sources,_,resource=account_web
    page=client.get('/holdings')
    assert page.status_code==200
    for text in ('005930','69,000원','690,000원','-10,000원','-1.43%','오래된 관측','마지막 성공 관측'):
        assert text in page.text
    assert '700000' not in page.text  # no fabricated valuation from average cost
    account=client.get('/account')
    assert account.status_code==200 and '예수금' in account.text
    assert '100,000원' in account.text and '-10,000원' in account.text
    repo=ReadOnlyAccountViewRepository(resource,clock=sources.clock)
    saved=repo.account()
    row=saved.holdings[0]
    response=client.get(f'/records/{resource.id}/{row.record_id}')
    assert response.status_code==200 and 'unrealized_return' not in response.text and '평가수익률' in response.text
    evidence=client.get(f'/evidence/{resource.id}/{row.record_id}')
    assert evidence.status_code==200
    other=resource.model_copy(update={'account_hash':'f'*64})
    with pytest.raises(EvidenceUnavailable,match='SCOPE_CONFLICT'):
        ReadOnlyAccountViewRepository(other,clock=sources.clock).account()


def test_failed_refresh_survives_reader_restart_without_replacing_balance(account_web):
    app,client,sources,config,resource=account_web
    before=ReadOnlyAccountViewRepository(resource,clock=sources.clock).account()
    record_refresh(config,None,'QUERY_UNAVAILABLE',observed_at=sources.clock())
    after=ReadOnlyAccountViewRepository(resource,clock=sources.clock).account()
    assert before.snapshot_id==after.snapshot_id
    assert after.envelope.source_observed_at==before.envelope.source_observed_at
    assert after.latest_attempt_status=='FAILED' and after.envelope.diagnostic_code=='ACCOUNT_REFRESH_FAILED'
    assert '최근 KIS 계좌 갱신이 실패' in client.get('/account').text
    assert '-1.43%' in client.get('/holdings').text
    record_refresh(config,None,'INCOMPLETE_PAGES',observed_at=sources.clock()+timedelta(seconds=1))
    with pytest.raises(EvidenceUnavailable,match='FUTURE_SOURCE_TIME'):
        ReadOnlyAccountViewRepository(resource,clock=sources.clock).account()


def test_never_collected_and_failed_without_success_are_distinct(account_web):
    _,client,sources,config,resource=account_web
    with sqlite3.connect(config.db_path) as conn:
        conn.execute('DELETE FROM account_view_holdings')
        conn.execute('DELETE FROM account_view_snapshots')
        conn.execute('DELETE FROM account_view_attempts')
    # Use a new repository instance so no in-memory last-success cache is involved.
    never=ReadOnlyAccountViewRepository(resource,clock=sources.clock).account()
    assert never.snapshot_id is None and never.available_cash is None
    assert never.envelope.diagnostic_code=='ACCOUNT_NOT_COLLECTED'
    record_refresh(config,None,'AUTH_UNAVAILABLE',observed_at=sources.clock())
    failed=ReadOnlyAccountViewRepository(resource,clock=sources.clock).account()
    assert failed.snapshot_id is None and failed.total_evaluation is None
    assert failed.envelope.diagnostic_code=='ACCOUNT_REFRESH_FAILED'
    assert failed.latest_attempt_status=='FAILED'
