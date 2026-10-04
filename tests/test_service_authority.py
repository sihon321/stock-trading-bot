import importlib
import multiprocessing
import os
import sqlite3
from datetime import timedelta

import pytest

from tests.service_fixtures import FakeServiceClock, NOW, SCOPE, TempServiceTopology


def _hold(settings, ready, release):
    from trading_bot.service_leader import ServiceLeader
    from trading_bot.service_store import ServiceJournal
    journal = ServiceJournal(settings, clock=FakeServiceClock())
    with ServiceLeader(settings, journal=journal) as leader:
        journal.heartbeat('worker', leader.generation_id, phase='ACTIVE', observed_at=NOW-timedelta(seconds=1000))
        ready.put((leader.generation_id, leader.state))
        release.wait(30)


def setup(tmp_path):
    from trading_bot.service_store import ServiceJournal
    module = importlib.import_module('trading_bot.service_leader')
    settings = TempServiceTopology(tmp_path).registration()
    clock = FakeServiceClock()
    journal = ServiceJournal(settings, clock=clock)
    journal.initialize()
    return module, settings, journal, clock


def test_trading_control_reference_is_explicit_credential_free():
    from trading_bot.config import Settings
    field=Settings.model_fields['service_control_config_path']
    assert str(field.default).endswith('stock-trading-bot/service.json')


@pytest.mark.parametrize('root', ['manual_mock','direct_kis','proof','soak','intraday','saved_buy'])
def test_money_roots_missing_controls_cannot_submit(tmp_path,root):
    from tests.test_service_controls import submission_fixture
    from trading_bot.domain import Order, OrderSide, Money, Ticker
    from trading_bot.kis_broker import KISBroker
    from trading_bot.kis_order import KisOrderAccount
    from trading_bot import cli
    j,primary,lease,guard,broker,adapter,args=submission_fixture(tmp_path)
    try:
        if root=='manual_mock':
            from conftest import make_settings
            settings=make_settings(service_control_config_path=tmp_path/'missing.json')
            broker=cli._build_broker(settings,token_manager=None,account=KisOrderAccount('12345678','01'))
        elif root in ('direct_kis','saved_buy'):
            broker=KISBroker(order_adapter=adapter,account=KisOrderAccount('12345678','01'),market_clock=lambda:True)
        elif root=='proof':
            with pytest.raises(Exception): cli._proof_submission_context(tmp_path/'missing.json', adapter)
            return
        elif root=='soak':
            with pytest.raises(Exception): cli._build_submission_authority(tmp_path/'missing.json')
            return
        else:
            from tests.test_exit_manager import _snapshot
            from trading_bot.exit_manager import submit_exit, evaluate_exit_candidate, ExitTrigger, ExitTriggerKind
            broker=KISBroker(order_adapter=adapter,account=KisOrderAccount('12345678','01'),market_clock=lambda:True)
            candidate=evaluate_exit_candidate(ExitTrigger(ExitTriggerKind.DAILY_LLM_SELL,'005930','submission-run','LLM'),_snapshot())
            with pytest.raises(Exception): submit_exit(candidate,broker=broker,limit_price=Money(70000),
                portfolio_refresh=args['portfolio_refresh'],lease_guard=lease,cycle_snapshot_id='current',origin_run_id='submission-run')
            return
        with pytest.raises(Exception): broker.place_order(Order(Ticker('005930'),OrderSide.BUY,1,Money(70000)),**args)
        assert adapter.post_attempts==0
    finally: lease.release();primary.close()


def test_composition_binding_requires_concrete_final_authority():
    from trading_bot.service_composition import BrokerGuardBindings
    assert 'submission_authority' in BrokerGuardBindings.__dataclass_fields__


@pytest.mark.parametrize('path', ['manual_daily','saved_daily','intraday','direct_kis','designated_mock'])
@pytest.mark.parametrize('action,side,allowed', [('PAUSE','BUY',False),('PAUSE','SELL',True),('KILL','BUY',False),('KILL','SELL',False)])
def test_all_final_money_paths_share_effective_restrictions(tmp_path,path,action,side,allowed):
    from tests.test_service_controls import submission_fixture,request
    from trading_bot.domain import Order,OrderSide,Money,Ticker,Position
    from trading_bot import cli,sqlite_audit
    j,primary,lease,guard,broker,adapter,args=submission_fixture(tmp_path)
    order=Order(Ticker('005930'),OrderSide(side),1,Money(70000))
    try:
        j.request_writer(actor='owner').append_request(request(j,action))
        if path=='designated_mock':
            from trading_bot.mock_broker import MockBroker
            quote=broker._pre_submit_quote_reader
            broker=MockBroker(Money(1000000),positions=(Position(Ticker('005930'),1,Money(70000)),),
                pre_submit_quote_reader=quote,clock=j.clock,submission_authority=guard,
                submission_scope=j.settings.registered_scopes[0],require_submission_authority=True,
                evidence_sink=lambda event:sqlite_audit.append_order_event(primary,event))
        if path in ('manual_daily','saved_daily'):
            refresh=args['portfolio_refresh']
            broker=cli._LeaseGuardedBroker(broker,lease,portfolio_refresh=lambda:refresh('005930'),
                execution_intent_id=args['order_intent_id'])
        if path=='intraday' and side=='SELL':
            from trading_bot.exit_manager import submit_exit,evaluate_exit_candidate,ExitTrigger,ExitTriggerKind
            candidate=evaluate_exit_candidate(ExitTrigger(ExitTriggerKind.DAILY_LLM_SELL,'005930','submission-run','LLM'),args['portfolio_refresh']('005930'))
            invoke=lambda:submit_exit(candidate,broker=broker,limit_price=Money(70000),
                portfolio_refresh=args['portfolio_refresh'],lease_guard=lease,cycle_snapshot_id='current',origin_run_id='submission-run',
                submission_authority=guard)
        else: invoke=lambda:broker.place_order(order,**args)
        if allowed: invoke()
        else:
            with pytest.raises(Exception): invoke()
        calls=len(broker.order_history) if path=='designated_mock' else adapter.post_attempts
        assert calls==int(allowed)
        assert len(j.reader().list_admissions())==int(allowed)
    finally:lease.release();primary.close()


@pytest.mark.parametrize('action,side,allowed', [('PAUSE','BUY',False),('PAUSE','SELL',True),('KILL','BUY',False),('KILL','SELL',False)])
def test_actual_proof_context_preserves_ids_and_requires_no_service_receipt(tmp_path,action,side,allowed):
    from tests.test_service_controls import submission_fixture,request
    from tests.test_soak_proof import _request,_reconcile
    from dataclasses import replace
    from trading_bot.soak_models import BrokerPageEnvelope,PageCompleteness
    from trading_bot.submission_authority import ProofSubmissionContext
    from trading_bot.soak_proof import ProofOrderService
    j,primary,lease,guard,broker,adapter,args=submission_fixture(tmp_path,suffix_scope=True)
    lease.release()
    adapter.query_daily_ccld_pages=lambda **kw:BrokerPageEnvelope(page_count=1,completeness=PageCompleteness.COMPLETE,reason_code='COMPLETE')
    adapter.query_balance_pages=lambda **kw:BrokerPageEnvelope(rows=({'pdno':'005930','hldg_qty':'1','ord_psbl_qty':'1','pchs_avg_pric':'70000'},),
        summary={'dnca_tot_amt':'1000000','tot_evlu_amt':'1000000'},page_count=1,completeness=PageCompleteness.COMPLETE,reason_code='COMPLETE')
    proof=replace(_request(tmp_path),side=side,primary_audit_db_path=j.settings.trading_journal_paths[0],
        soak_db_path=j.settings.trading_journal_paths[1],controller_db_path=j.settings.trading_journal_paths[2])
    context=ProofSubmissionContext(guard,adapter=adapter,quote_reader=broker._pre_submit_quote_reader)
    service=ProofOrderService(adapter=adapter,submission_context=context,reconciliation_runner=_reconcile)
    try:
        j.request_writer(actor='owner').append_request(request(j,action))
        if allowed:
            result=service.run(proof)
            assert result.cross_ids_validated and result.order_intent_id==service._ids(proof)[2]
        else:
            with pytest.raises(Exception):service.run(proof)
        assert adapter.post_attempts==int(allowed)
    finally:primary.close()


@pytest.mark.parametrize('late', [False,True])
def test_actual_http_entry_after_preparation_is_guarded(tmp_path,late):
    from tests.test_service_controls import submission_fixture,request
    from tests.test_kis_order import _adapter,_post_response,HASHKEY_PATH,ORDER_CASH_PATH
    from tests.test_kis_broker import _query_result
    from trading_bot.kis_order import FillStatus
    from trading_bot.domain import Order,OrderSide,Money,Ticker
    j,primary,lease,guard,broker,fake,args=submission_fixture(tmp_path)
    adapter=_adapter([_post_response(HASHKEY_PATH,payload={'HASH':'fixture-hash'}),_post_response(ORDER_CASH_PATH)])
    adapter._domain='https://openapivts.koreainvestment.com:29443'
    adapter.inquire_daily_ccld=lambda **kw:_query_result([])
    adapter.inquire_balance=lambda **kw:_query_result({})
    adapter.read_fill_status=lambda **kw:FillStatus('KIS-1','005930',1,1,0)
    broker._order_adapter=adapter
    original=adapter.place_order_cash
    def call(**kw):
        if late:j.clock.advance(11)
        return original(**kw)
    adapter.place_order_cash=call
    post=adapter._client.post
    def transport(url,**kw):
        if url.endswith(HASHKEY_PATH):
            assert j.request_writer(actor='owner').append_request(request(j,'PAUSE')).status=='REQUESTED'
        else:
            assert not primary.in_transaction
            assert j.request_writer(actor='owner').append_request(request(j,'KILL',1,'kill')).status=='UNAVAILABLE'
        return post(url,**kw)
    adapter._client.post=transport
    try:
        order=Order(Ticker('005930'),OrderSide.SELL,1,Money(70000))
        if late:
            with pytest.raises(Exception):broker.place_order(order,**args)
        else:broker.place_order(order,**args)
        actual=[c for c in adapter._client.calls if c['url'].endswith(ORDER_CASH_PATH)]
        assert len(actual)==int(not late)
    finally:lease.release();primary.close()


def test_historical_proof_freeze_without_identity_is_scoped_and_retained(tmp_path):
    from tests.test_service_controls import submission_fixture
    from trading_bot import soak_store
    from trading_bot.soak_models import CampaignKind
    from trading_bot.submission_authority import SubmissionDenied
    from trading_bot.domain import Order,OrderSide,Money,Ticker
    j,primary,lease,guard,broker,adapter,args=submission_fixture(tmp_path)
    try:
        with sqlite3.connect(j.settings.trading_journal_paths[1]) as soak:
            soak_store.create_campaign(soak,campaign_id='historical-proof',
                accepted_profile_fingerprint='fixture-profile',accepted_profile_version='TEST',
                field_contract_version='TEST',ambiguity_policy_version='TEST',
                ambiguity_window_seconds=30,ambiguity_poll_cadence_seconds=5,ambiguity_max_observations=6,
                campaign_kind=CampaignKind.PROOF_ORDER,credit_eligible=False)
            soak_store.freeze_ticker(soak,freeze_id='original-freeze',campaign_id='historical-proof',
                ticker='000660',freeze_kind='AMBIGUITY',order_intent_id='original-ambiguous-intent')
        scope=guard.assert_account(broker._account,adapter)
        with pytest.raises(SubmissionDenied,match='TICKER_FROZEN'):
            guard._saved_safety(scope,'another-intent','000660')
        broker.place_order(Order(Ticker('005930'),OrderSide.SELL,1,Money(70000)),**args)
        assert adapter.post_attempts==1
        with sqlite3.connect(j.settings.trading_journal_paths[1]) as soak:
            assert soak.execute("SELECT state FROM soak_ticker_freezes WHERE freeze_id='original-freeze'").fetchall()==[('FROZEN',)]
    finally:lease.release();primary.close()


def test_raw_credential_capable_adapter_denies_opaque_authority_before_preparation():
    from tests.test_kis_order import _FakeClient,_FakeTokenManager,DOMAIN
    from trading_bot.kis_order import KisOrderAdapter,KisOrderAccount
    from trading_bot.submission_authority import SubmissionDenied
    from trading_bot.domain import Order,OrderSide,Money,Ticker
    client=_FakeClient([])
    adapter=KisOrderAdapter(token_manager=_FakeTokenManager(),client=client,domain=DOMAIN,tr_id_profile='mock')
    with pytest.raises(SubmissionDenied,match='ACTUAL_POST_ENTRY_REQUIRED'):
        adapter.place_order_cash(account=KisOrderAccount('12345678','01'),
            order=Order(Ticker('005930'),OrderSide.BUY,1,Money(70000)),snapped_price=70000,
            submission_entry=object())
    assert client.calls==[]


@pytest.mark.parametrize('invalid', ['real_token','opaque_token','none_token','opaque_client'])
def test_legacy_transport_capability_rejects_nonfixture_collaborators(invalid):
    from tests.test_kis_order import _FakeClient,_FakeTokenManager,DOMAIN
    from trading_bot.kis_order import KisOrderAdapter
    from trading_bot.kis_auth import KisTokenManager
    token=_FakeTokenManager()
    client=_FakeClient([])
    if invalid=='real_token':token=object.__new__(KisTokenManager)
    elif invalid=='opaque_token':token=object()
    elif invalid=='none_token':token=None
    else:client=object()
    with pytest.raises(ValueError,match='no-credential offline test'):
        KisOrderAdapter.for_test_legacy_mutation(token_manager=token,client=client,domain=DOMAIN,tr_id_profile='mock')


def test_spawn_live_owner_cannot_be_displaced_by_stale_heartbeat(tmp_path):
    module, settings, journal, _ = setup(tmp_path)
    ctx=multiprocessing.get_context('spawn')
    ready,release=ctx.Queue(),ctx.Event()
    child=ctx.Process(target=_hold,args=(settings,ready,release)); child.start()
    try:
        generation,state=ready.get(timeout=10)
        assert state=='RUNNING'
        with pytest.raises(module.ServiceLeaderBusy):
            module.ServiceLeader(settings,journal=journal).acquire()
        with journal.connection() as c:
            assert c.execute('SELECT COUNT(*) FROM service_generations').fetchone()[0]==1
            assert c.execute('SELECT COUNT(*) FROM service_restart_attempts').fetchone()[0]==0
    finally:
        release.set(); child.join(10)
        if child.is_alive(): child.kill(); child.join(5)
    assert child.exitcode==0
    with module.ServiceLeader(settings,journal=journal) as leader:
        assert leader.generation_id!=generation and leader.state=='RUNNING'


def test_killed_owner_enters_recovery_retaining_jobs_and_restart_reservation(tmp_path):
    module, settings, journal, clock = setup(tmp_path)
    from trading_bot.service_models import LogicalJobKey
    key=LogicalJobKey(scope=SCOPE,trading_date_kst=NOW.date(),kind='DAILY')
    job=journal.claim_job(key,due_at=NOW,dispatch_deadline_at=NOW+timedelta(minutes=20),owner_generation='previous')
    ctx=multiprocessing.get_context('spawn'); ready,release=ctx.Queue(),ctx.Event()
    child=ctx.Process(target=_hold,args=(settings,ready,release)); child.start()
    try:
        previous,_=ready.get(timeout=10)
    finally:
        child.kill(); child.join(10)
    clock.advance(5)
    with module.ServiceLeader(settings,journal=journal) as leader:
        assert leader.state=='RECOVERY_ONLY'
        leader.assert_owner()
        assert journal.load_job(job)['job_id']==job
        with journal.connection() as c:
            assert c.execute('SELECT state FROM service_generations WHERE generation_id=?',(previous,)).fetchone()[0]=='UNEXPECTED_EXIT'
            assert c.execute('SELECT generation_id FROM service_restart_attempts').fetchone()[0]==leader.generation_id


def test_exhausted_generation_releases_lock_and_never_constructs_worker(tmp_path):
    module,settings,journal,clock=setup(tmp_path)
    for i in range(3):
        leader=module.ServiceLeader(settings,journal=journal).acquire()
        leader.close(clean_stop=False)
        clock.advance(1)
    leader=module.ServiceLeader(settings,journal=journal).acquire()
    leader.close(clean_stop=False)
    with pytest.raises(module.ServiceRestartDenied):
        module.ServiceLeader(settings,journal=journal).acquire()
    clock.advance(1000)
    with pytest.raises(module.ServiceRestartDenied):
        module.ServiceLeader(settings,journal=journal).acquire()
    assert journal.request_attention_reset(safety_validated=True,recovery_validated=True)
    with module.ServiceLeader(settings,journal=journal) as leader:
        assert leader.state=='RECOVERY_ONLY'


def test_owner_checks_close_inode_and_no_account_capability(tmp_path):
    module,settings,journal,_=setup(tmp_path)
    leader=module.ServiceLeader(settings,journal=journal).acquire()
    assert os.get_inheritable(leader._lock_fd) is False
    assert leader.lock_path.name=='service-leader.lock'
    assert leader.lock_path.stat().st_mode&0o777==0o600
    assert not hasattr(leader,'submit') and not hasattr(leader,'assert_active_owner')
    assert leader.lock_path.name!=f'{SCOPE.account_scope_hash}.lock'
    leader.close(clean_stop=True)
    with pytest.raises(module.ServiceOwnershipLost): leader.assert_owner()


def test_nonowner_process_and_changed_durable_generation_fail_closed(tmp_path, monkeypatch):
    module,settings,journal,_=setup(tmp_path)
    leader=module.ServiceLeader(settings,journal=journal).acquire()
    original_pid=os.getpid()
    with monkeypatch.context() as patch:
        patch.setattr(module.os,'getpid',lambda: original_pid+1)
        with pytest.raises(module.ServiceOwnershipLost): leader.assert_owner()
    with journal.connection() as c:
        c.execute("UPDATE service_generations SET state='UNEXPECTED_EXIT' WHERE generation_id=?",(leader.generation_id,))
    with pytest.raises(module.ServiceOwnershipLost): leader.assert_owner()
    leader.close(clean_stop=False)


def test_replaced_lock_inode_is_never_accepted(tmp_path):
    module,settings,journal,_=setup(tmp_path)
    leader=module.ServiceLeader(settings,journal=journal).acquire()
    leader.lock_path.rename(leader.lock_path.with_suffix('.old'))
    leader.lock_path.touch(mode=0o600)
    with pytest.raises(module.ServiceOwnershipLost): leader.assert_owner()
    leader.close(clean_stop=False)


def test_automatic_launcher_attempt_counts_even_after_clean_stop(tmp_path):
    module,settings,journal,_=setup(tmp_path)
    with module.ServiceLeader(settings,journal=journal): pass
    for _ in range(3):
        with module.ServiceLeader(settings,journal=journal,automatic_restart=True): pass
    with pytest.raises(module.ServiceRestartDenied):
        module.ServiceLeader(settings,journal=journal,automatic_restart=True).acquire()
