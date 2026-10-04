"""Only injected clients and temporary journals exercise composition."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tests.service_fixtures import NoExternalCapabilities, NOW, TempServiceTopology
from tests.test_service_activation import activation_fixture


def test_disabled_and_missing_acceptance_construct_zero_capabilities(tmp_path):
    from trading_bot.service_composition import build_service_composition
    settings=TempServiceTopology(tmp_path).registration()
    for current in (settings, settings.model_copy(update={'service_enabled':True,'mode':'KIS_MOCK'})):
        with NoExternalCapabilities() as probe, \
                patch('trading_bot.soak_config.SoakSettings',side_effect=AssertionError('settings')), \
                patch('trading_bot.kis_auth.KisTokenManager',side_effect=AssertionError('token')), \
                patch('trading_bot.kis_order.KisOrderAdapter',side_effect=AssertionError('adapter')), \
                patch('trading_bot.kis_broker.KISBroker',side_effect=AssertionError('broker')):
            result=build_service_composition(current,clock=lambda:NOW)
        assert not result.activation.allowed and result.provider_factory is None
        assert result.guarded_broker_builder is None and not probe.attempts


def test_saved_synthetic_receipt_does_not_load_credentials(tmp_path):
    from trading_bot.service_composition import build_service_composition
    settings,receipt,reader,safety,_,_=activation_fixture(tmp_path)
    with patch('trading_bot.service_composition.load_mock_trading_settings',side_effect=AssertionError('credential')):
        result=build_service_composition(settings,receipt=receipt,saved_evidence_reader=reader,
            current_safety=lambda *a:safety,clock=lambda:NOW)
    assert not result.activation.allowed


def test_dry_run_requires_frozen_injection_and_separate_temporary_stores(tmp_path):
    from trading_bot.service_composition import build_service_composition, OfflineServiceCollaborators
    from trading_bot.service_activation import OfflineActivationAuthority
    settings=TempServiceTopology(tmp_path).registration(enabled=True,mode='DRY_RUN')
    assert not build_service_composition(settings,clock=lambda:NOW).activation.allowed
    frozen=OfflineServiceCollaborators(authority=OfflineActivationAuthority(tmp_path),
        prep_read_only=lambda:'SYNTHETIC_PREP',read_portfolio=lambda request:'SYNTHETIC_PORTFOLIO',
        read_quote=lambda ticker:'SYNTHETIC_QUOTE',reconcile_orders=lambda request:'SYNTHETIC_RECONCILIATION',
        read_freezes=lambda:('000660',))
    with NoExternalCapabilities() as probe, patch('trading_bot.service_composition.load_mock_trading_settings',side_effect=AssertionError('secret')):
        result=build_service_composition(settings,offline=frozen,clock=lambda:NOW)
        assert result.read_portfolio(None)=='SYNTHETIC_PORTFOLIO'
        assert result.read_freezes()==('000660',)
    assert result.authentication=='OFFLINE_ONLY' and result.provider_factory is None
    assert result.guarded_broker_builder is None and not probe.attempts


def mock_fixture(tmp_path):
    import json
    from trading_bot.service_composition import OfflineMockClients
    settings,receipt,reader,safety,authority,evidence=activation_fixture(tmp_path)
    settings.trading_config_path.write_text(json.dumps({
        'kis_mock':{'domain':'https://openapivts.koreainvestment.com:29443',
            'app_key':'OFFLINE_KEY','app_secret':'OFFLINE_SECRET','tr_id_profile':'official-example-v1','label':'offline'},
        'kis_mock_account_cano':'00001234','accepted_profile_versions':['official-example-v1'],
        'primary_audit_db_path':str(settings.trading_journal_paths[0]),
        'soak_db_path':str(settings.trading_journal_paths[1]),
        'controller_db_path':str(settings.trading_journal_paths[2]),
        'kis_token_cache_path':str(tmp_path/'cache'/'tokens.json'),'llm_provider':'codex_cli'}))
    from trading_bot.portfolio import canonical_account_scope_hash
    from trading_bot.service_models import ServiceScope
    scope=ServiceScope(account_scope_hash=canonical_account_scope_hash('mock','1234'),execution_target='mock')
    settings=settings.model_copy(update={'registered_scopes':(scope,)})
    receipt=receipt.model_copy(update={'scope':scope})
    evidence=evidence.model_copy(update={'scope':scope})
    reader.read=lambda receipt:evidence
    reader.read_freezes=lambda:()
    safety=safety.model_copy(update={'scope':scope})
    class FakeClient:
        def __init__(self):self.calls=[]
        def post(self,*args,**kwargs):
            self.calls.append((args,kwargs));raise AssertionError('no POST authorized')
        def get(self,*args,**kwargs):
            self.calls.append((args,kwargs));raise AssertionError('inject normalized inquiry instead')
        def close(self):pass
    clients=OfflineMockClients(authority=authority,auth_client=FakeClient(),
        order_client=FakeClient(),quote_client=FakeClient())
    class Policy:
        session_evidence_provider=SimpleNamespace(for_date=lambda day:None)
        def classify(self,now):return SimpleNamespace(executable=True,reason='SYNTHETIC')
        def completed_bar_cutoff(self,day):return SimpleNamespace(available=True,cutoff_date=date(2026,10,2))
    return settings,receipt,reader,safety,clients,Policy()


def composition(tmp_path,**changes):
    from trading_bot.service_composition import build_service_composition
    settings,receipt,reader,safety,clients,policy=mock_fixture(tmp_path)
    return build_service_composition(settings,receipt=receipt,saved_evidence_reader=reader,
        current_safety=lambda *a:safety,clock=lambda:NOW,offline_mock_clients=clients,
        policy=policy,**changes)


def test_authentic_adapter_identity_is_labeled_offline_in_harness(tmp_path):
    from trading_bot.kis_order import KisOrderAdapter
    result=composition(tmp_path)
    assert result.activation.allowed and result.authentication=='OFFLINE_FIXTURE'
    assert result.execution_target=='mock' and result.runtime_wired is False
    assert isinstance(result._test_order_adapter, KisOrderAdapter)
    assert result._test_order_adapter.tr_ids.buy=='VTTC0012U'
    assert result._test_order_adapter.tr_ids.sell=='VTTC0011U'
    assert result._test_order_adapter._timeout_seconds==10
    assert result._test_order_adapter._query_timeout_seconds<=15


def test_saved_acceptance_rechecked_before_every_lazy_capability(tmp_path):
    from trading_bot.service_composition import build_service_composition, ServiceCompositionBlocked
    settings,receipt,reader,safety,clients,policy=mock_fixture(tmp_path)
    result=build_service_composition(settings,receipt=receipt,saved_evidence_reader=reader,
        current_safety=lambda *a:safety,clock=lambda:NOW,offline_mock_clients=clients,policy=policy)
    previous=reader.read(receipt)
    reader.read=lambda receipt:previous.model_copy(update={'frozen_tickers':('000660',)})
    with pytest.raises(ServiceCompositionBlocked,match='UNRESOLVED_FREEZE'):
        result.read_quote('000660')
    assert not clients.quote_client.calls
    with pytest.raises(ServiceCompositionBlocked):result.provider_factory()


def test_whole_account_inquiry_uses_shipped_normalizer_no_campaign_mutation(tmp_path):
    from trading_bot.service_composition import PortfolioReadRequest
    from trading_bot.soak_models import BrokerPageEnvelope
    from trading_bot.portfolio import PortfolioCompleteness
    result=composition(tmp_path)
    adapter=result._test_order_adapter
    calls=[]
    def daily(**kwargs):
        calls.append(kwargs);return BrokerPageEnvelope(page_count=1,completeness='COMPLETE',reason_code='COMPLETE')
    def balance(**kwargs):
        calls.append(kwargs);return BrokerPageEnvelope(page_count=1,completeness='COMPLETE',reason_code='COMPLETE',
            summary={'dnca_tot_amt':'1000','tot_evlu_amt':'1000','ord_psbl_cash':'1000'})
    adapter.query_daily_ccld_pages=daily;adapter.query_balance_pages=balance
    snapshot=result.read_portfolio(PortfolioReadRequest(trading_date=NOW.date(),
        previous_trading_date=date(2026,10,2),local_unresolved=()))
    assert snapshot.completeness is PortfolioCompleteness.COMPLETE
    assert len(calls)==2 and all(c['profile'].version=='official-example-v1' for c in calls)
    assert result.reconcile_orders(PortfolioReadRequest(trading_date=NOW.date(),
        previous_trading_date=date(2026,10,2),local_unresolved=())).completeness is PortfolioCompleteness.COMPLETE


def test_broker_builder_requires_later_final_guard_and_audit_sink(tmp_path):
    from trading_bot.service_composition import BrokerGuardBindings, ServiceCompositionBlocked
    result=composition(tmp_path)
    with pytest.raises(ServiceCompositionBlocked,match='FINAL_ORDER_GUARD_REQUIRED'):
        result.guarded_broker_builder(None)
    with pytest.raises(ServiceCompositionBlocked,match='AUDIT_SINK_REQUIRED'):
        result.guarded_broker_builder(BrokerGuardBindings(order_adapter_guard=lambda *a:object(),
            evidence_sink=None,data_fresh=lambda:True))
    class Guard:
        def __init__(self,delegate):self.delegate=delegate
        def __getattr__(self,name):return getattr(self.delegate,name)
    seen=[]
    def guarded(adapter,context):
        seen.append(context);return Guard(adapter)
    broker=result.guarded_broker_builder(BrokerGuardBindings(order_adapter_guard=guarded,
        evidence_sink=lambda event:None,data_fresh=lambda:True))
    from trading_bot.kis_broker import KISBroker
    assert type(broker) is KISBroker and broker._test_only_allow_unguarded_mutation is False
    assert seen[0].scope.execution_target=='mock' and callable(seen[0].validate_activation)
    assert callable(seen[0].read_freezes) and seen[0].post_timeout_seconds==10


@pytest.mark.parametrize('change', [
    {'kis_real':{}}, {'trading_mode':'real'}, {'confirm_real_trading':True},
    {'target_eligible_days':21}, {'availability_failure_budget':3},
    {'kis_mock_account_cano':'99991235'}, {'accepted_profile_versions':['repository-legacy-v1']},
])
def test_invalid_secret_config_never_constructs_clients(tmp_path,change):
    import json
    from trading_bot.service_composition import build_service_composition
    settings,receipt,reader,safety,clients,policy=mock_fixture(tmp_path)
    document=json.loads(settings.trading_config_path.read_text());document.update(change)
    settings.trading_config_path.write_text(json.dumps(document))
    with patch('trading_bot.kis_auth.KisTokenManager',side_effect=AssertionError('client')):
        result=build_service_composition(settings,receipt=receipt,saved_evidence_reader=reader,
            current_safety=lambda *a:safety,clock=lambda:NOW,offline_mock_clients=clients,policy=policy)
    assert not result.activation.allowed


def test_mock_domain_exact_and_unverified_codex_fail_closed(tmp_path):
    from trading_bot.service_composition import ServiceCompositionBlocked
    result=composition(tmp_path)
    with NoExternalCapabilities() as probe:
        with pytest.raises(ServiceCompositionBlocked,match='PROVIDER_SINGLE_SHOT_UNVERIFIED'):
            result.provider_factory()
    assert not probe.attempts


@pytest.mark.parametrize('domain', [
    'https://openapi.koreainvestment.com:9443',
    'https://openapivts.koreainvestment.com:29443/foreign',
    'https://user@openapivts.koreainvestment.com:29443',
    'https://openapivts.koreainvestment.com:29443?real=true',
])
def test_domain_cannot_redirect_or_select_real_target(tmp_path,domain):
    import json
    from trading_bot.service_composition import build_service_composition
    settings,receipt,reader,safety,clients,policy=mock_fixture(tmp_path)
    document=json.loads(settings.trading_config_path.read_text())
    document['kis_mock']['domain']=domain
    settings.trading_config_path.write_text(json.dumps(document))
    with patch('trading_bot.kis_auth.KisTokenManager',side_effect=AssertionError('client')):
        result=build_service_composition(settings,receipt=receipt,saved_evidence_reader=reader,
            current_safety=lambda *a:safety,clock=lambda:NOW,offline_mock_clients=clients,policy=policy)
    assert not result.activation.allowed


def test_protected_explicit_secret_path_ignores_real_and_secret_env(tmp_path,monkeypatch):
    from trading_bot.service_composition import load_mock_trading_settings
    settings,*_=mock_fixture(tmp_path)
    monkeypatch.setenv('SOAK_KIS_MOCK_ACCOUNT_CANO','99998888')
    monkeypatch.setenv('TRADING_MODE','real')
    monkeypatch.setenv('CONFIRM_REAL_TRADING','true')
    loaded=load_mock_trading_settings(settings.trading_config_path)
    assert loaded.kis_mock_account_cano.get_secret_value()=='00001234'
    assert not hasattr(loaded,'kis_real') and not hasattr(loaded,'confirm_real_trading')
