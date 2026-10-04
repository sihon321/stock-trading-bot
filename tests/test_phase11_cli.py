from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone

import pytest
from tests.service_fixtures import FakeServiceClock, TempServiceTopology, SCOPE, session_evidence

_test_root = None
_dependencies = {}


@pytest.fixture(autouse=True)
def protected_daily_topology(tmp_path):
    global _test_root, _dependencies
    _test_root, _dependencies = tmp_path, {}
    yield
    for dependencies in _dependencies.values():
        if not dependencies['mutation_lease'].closed:
            dependencies['mutation_lease'].release()


def dependencies(conn, day='20260904'):
    from trading_bot.cli import DailyDispatchRuntime
    from trading_bot.control_store import ControlStore
    from trading_bot.control_runtime import ControlApplier
    from trading_bot.service_store import ServiceJournal
    from trading_bot.service_leader import ServiceLeader
    from trading_bot.service_models import ControlRequest
    from trading_bot.portfolio_store import migrate_portfolio
    from trading_bot.mutation_lease import acquire_mutation_lease
    from tests.test_service_controls import safety
    current = datetime.strptime(day,'%Y%m%d').replace(hour=0,minute=10,tzinfo=timezone.utc)
    if id(conn) in _dependencies:
        result=_dependencies[id(conn)]
        result['daily_dispatch_runtime'].clock.wall=current
        return result
    root=_test_root / str(len(_dependencies)); root.mkdir()
    settings=TempServiceTopology(root).registration()
    clock=FakeServiceClock(current)
    journal=ServiceJournal(settings,clock=clock); journal.initialize()
    controls=ControlStore(settings,clock=clock); controls.initialize(actor='tester')
    with ServiceLeader(settings,journal=journal) as leader:
        controls.request_writer(actor='tester').append_request(ControlRequest(request_id='resume',actor='tester',
            requested_at=clock(),scope=controls.scope,action='RESUME',expected_revision=0))
        ControlApplier(controls.service_capability(leader),clock=clock,
            validate_resume=lambda scope,now:safety(scope,now),current_safety=lambda scope,now:safety(scope,now)).apply_pending()
    migrate_portfolio(conn)
    lease=acquire_mutation_lease(conn,account_scope_hash=SCOPE.account_scope_hash,
        lock_dir=root/'account-locks',command='run',cycle_id='test-owner',observed_at=clock())
    result=dict(mutation_lease=lease,daily_dispatch_runtime=DailyDispatchRuntime(settings,journal,controls,
        lambda day:session_evidence(day=day),clock))
    _dependencies[id(conn)]=result
    return result

from conftest import make_data_context, make_settings
from trading_bot.domain import Decision, LLMSignal, Money, Position, Ticker
from trading_bot.portfolio import (
    PortfolioAccountSummary,
    PortfolioCompleteness,
    PortfolioHolding,
    PortfolioSnapshot,
)


class DataSource:
    def __init__(self, candidates=("005930", "035420")):
        self.candidates = candidates
        self.contexts: list[str] = []

    def screen_daily_candidates(self, trading_date):
        return type("Screen", (), {"selected": self.candidates})()

    def build_context(self, ticker):
        self.contexts.append(ticker.value)
        return make_data_context(ticker=ticker, current_price=Money(70_000.0, "KRW"))


class Provider:
    def __init__(self, calls, failures=0):
        self.calls = calls
        self.failures = failures

    def generate_signal(self, context):
        self.calls.append(context.ticker.value)
        if self.failures:
            self.failures -= 1
            raise RuntimeError("provider unavailable")
        return LLMSignal(Decision.HOLD, 0.9, "durable daily hold")

    def generate_signal_from_envelope(self,envelope,admission):
        from trading_bot.domain import Ticker
        import re
        ticker=re.search(r'\b\d{6}\b',envelope.prompt_bytes.decode()).group()
        def transport(ack):
            ack()
            return self.generate_signal(type('Context',(),{'ticker':Ticker(ticker)})())
        return admission.admit_at_transport_entry(transport)


class Broker:
    def __init__(self):
        self.orders = []
        self.positions = {
            "005930": Position(Ticker("005930"), 2, Money(65_000.0, "KRW"))
        }

    def get_position(self, ticker):
        return self.positions.get(ticker.value)

    def place_order(self, order, **kwargs):
        self.orders.append(order)
        return "ORDER-1"


class Lease:
    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail

    def assert_active_owner(self):
        self.calls += 1
        if self.fail:
            raise RuntimeError("lease lost")


class Notifier:
    def send(self, summary):
        return True


def snapshot(*, cash=1_000_000.0, observed_second=0, snapshot_id=None):
    return PortfolioSnapshot(
        snapshot_id=snapshot_id or f"snapshot-{cash}-{observed_second}",
        account_scope_hash="a" * 64,
        trading_date=date(2026, 9, 4),
        previous_trading_date=date(2026, 9, 3),
        observed_at=datetime(2026, 9, 4, 0, 10, observed_second, tzinfo=timezone.utc),
        completeness=PortfolioCompleteness.COMPLETE,
        reason_code="COMPLETE",
        daily_page_count=1,
        balance_page_count=1,
        holdings=(PortfolioHolding("005930", 2, 2, 65_000.0),),
        orders=(),
        fills=(),
        account=PortfolioAccountSummary(cash, 2_000_000.0),
    )


def invoke(conn, *, run_id, trading_date="20260904", reader=None, factory=None,
           lease=None, cycle=None, candidates=("005930", "035420")):
    from trading_bot.cli import run_cycle

    if reader is None:
        read_index = [0]

        def reader():
            read_index[0] += 1
            return snapshot(
                observed_second=read_index[0],
                snapshot_id=f"snapshot-{run_id}-{read_index[0]}",
            )

    collaborators=dependencies(conn,trading_date).copy()
    if lease is not None: collaborators['mutation_lease']=lease
    return run_cycle(
        settings=make_settings(llm_max_retries=2),
        data_source=DataSource(candidates),
        llm_provider_factory=factory,
        broker=Broker(),
        audit_conn=conn,
        notifier=Notifier(),
        run_cycle=cycle,
        trading_date=trading_date,
        run_id=run_id,
        portfolio_snapshot_reader=reader,
        **collaborators,
    )


def test_same_day_overlap_reuses_one_final_signal_without_provider_construction():
    conn = sqlite3.connect(":memory:")
    calls: list[str] = []
    constructions = []

    def factory():
        constructions.append("built")
        return Provider(calls)

    first = invoke(conn, run_id="phase11-first", factory=factory)
    second = invoke(conn, run_id="phase11-second", factory=factory)

    assert [item["ticker"] for item in first["outcomes"]] == ["005930", "035420"]
    assert [item["ticker"] for item in second["outcomes"]] == ["005930", "035420"]
    assert calls == ["005930", "035420"]
    assert constructions == ["built", "built"]
    assert conn.execute("SELECT COUNT(*) FROM daily_evaluations").fetchone() == (2,)
    provenance = conn.execute(
        "SELECT provenance_json FROM daily_evaluations WHERE ticker='005930'"
    ).fetchone()[0]
    assert provenance == '["HELD","SCREENED"]'


def test_started_crash_is_finalized_unavailable_and_never_calls_provider():
    from trading_bot.portfolio_store import migrate_portfolio, start_daily_evaluation

    conn = sqlite3.connect(":memory:")
    migrate_portfolio(conn)
    start_daily_evaluation(
        conn,
        trading_date_kst=date(2026, 9, 4),
        ticker="005930",
        provenance=("HELD", "SCREENED"),
        canonical_input=b"committed-before-crash",
        account_scope_hash="a" * 64,
    )
    calls = []

    result = invoke(conn, run_id="phase11-recovery", factory=lambda: Provider(calls))

    assert calls == ["035420"]
    assert result["outcomes"][0]["final_action"] == "HOLD", result["outcomes"][0]["order_reason"]
    assert conn.execute(
        "SELECT reason_code FROM daily_evaluation_events WHERE event_type='LLM_UNAVAILABLE'"
    ).fetchone() == ("LLM_UNAVAILABLE",)


def test_held_market_failure_is_durable_hold_and_does_not_block_sibling():
    class FailingHeldDataSource(DataSource):
        def build_context(self, ticker):
            self.contexts.append(ticker.value)
            if ticker.value == "005930":
                raise RuntimeError("raw provider error must not be persisted")
            return super().build_context(ticker)

    conn = sqlite3.connect(":memory:")
    source = FailingHeldDataSource()
    calls: list[str] = []
    snapshots = iter(
        (snapshot(snapshot_id="held-market-gap-1"), snapshot(snapshot_id="held-market-gap-2"))
    )
    from trading_bot.cli import run_cycle

    result = run_cycle(
        settings=make_settings(llm_max_retries=1),
        data_source=source,
        llm_provider_factory=lambda: Provider(calls),
        broker=Broker(),
        audit_conn=conn,
        notifier=Notifier(),
        trading_date="20260904",
        run_id="held-market-gap",
        portfolio_snapshot_reader=lambda: next(snapshots),
        **dependencies(conn),
    )

    assert result["outcomes"][0]["final_action"] == "HOLD", result["outcomes"][0]["order_reason"]
    assert result["outcomes"][0]["order_reason"] == "DATA_INCOMPLETE"
    assert calls == ["035420"]
    assert conn.execute(
        "SELECT action, reason_code FROM daily_evaluation_events "
        "WHERE reason_code='DATA_INCOMPLETE'"
    ).fetchone() == ("HOLD", "DATA_INCOMPLETE")


def test_date_rollover_allows_one_new_provider_boundary():
    conn = sqlite3.connect(":memory:")
    calls = []
    factory = lambda: Provider(calls)

    invoke(conn, run_id="phase11-day-one", trading_date="20260904", factory=factory)
    invoke(conn, run_id="phase11-day-two", trading_date="20260905", factory=factory)

    assert calls == ["005930", "035420", "005930", "035420"]
    assert conn.execute("SELECT COUNT(*) FROM daily_evaluations").fetchone() == (4,)


def test_provider_uncertainty_consumes_once_and_finalizes_inside_one_identity():
    conn = sqlite3.connect(":memory:")
    retry_calls = []
    retry_provider = Provider(retry_calls, failures=1)

    invoke(
        conn, run_id="phase11-retry", factory=lambda: retry_provider,
        candidates=("005930",),
    )

    assert retry_calls == ["005930"]
    assert conn.execute(
        "SELECT COUNT(*) FROM daily_evaluation_events WHERE event_type='DISPATCH_CLAIMED'"
    ).fetchone() == (1,)
    assert conn.execute('SELECT dispatch_state FROM daily_evaluation_dispatches').fetchone()==('DISPATCHED_UNKNOWN',)

    failed_conn = sqlite3.connect(":memory:")
    failed_calls = []
    failed_provider = Provider(failed_calls, failures=9)
    invoke(
        failed_conn, run_id="phase11-failed", factory=lambda: failed_provider,
        candidates=("005930",),
    )
    invoke(
        failed_conn, run_id="phase11-failed-replay",
        factory=lambda: pytest.fail("final unavailable HOLD must be reused"),
        candidates=("005930",),
    )

    assert failed_calls == ["005930"]
    assert failed_conn.execute(
        "SELECT COUNT(*) FROM daily_evaluation_events WHERE event_type='LLM_UNAVAILABLE'"
    ).fetchone() == (1,)


def test_reused_signal_rechecks_lease_before_execution_and_post_boundary():
    conn = sqlite3.connect(":memory:")
    calls = []
    invoke(conn, run_id="phase11-seed", factory=lambda: Provider(calls))
    lost = dependencies(conn)['mutation_lease']
    lost.release()

    with pytest.raises(RuntimeError):
        invoke(conn, run_id="phase11-replay", factory=lambda: pytest.fail("must not construct"),lease=lost)

    assert calls == ["005930", "035420"]
    assert conn.execute('SELECT COUNT(*) FROM daily_evaluations').fetchone()==(2,)


def test_screened_only_sizing_uses_post_held_broker_cash_snapshot():
    conn = sqlite3.connect(":memory:")
    snapshots = iter((snapshot(cash=100.0), snapshot(cash=900.0, observed_second=1)))
    seen_cash = []

    def cycle(provider, context, **kwargs):
        seen_cash.append((context.ticker.value, kwargs["available_cash"]))
        from trading_bot.llm_provider import run_llm_cycle
        return run_llm_cycle(provider, context, **kwargs)

    invoke(
        conn,
        run_id="phase11-cash-refresh",
        reader=lambda: next(snapshots),
        factory=lambda: Provider([]),
        cycle=cycle,
    )

    assert seen_cash == [("005930", 100.0), ("035420", 900.0)]


def seed_dispatch(conn, *, consumed=False):
    from trading_bot.cli import _daily_envelope
    from trading_bot.portfolio_store import start_daily_evaluation,claim_daily_dispatch
    deps=dependencies(conn)
    runtime=deps['daily_dispatch_runtime']; lease=deps['mutation_lease']
    saved=_daily_envelope(make_settings(),make_data_context())
    evaluation=start_daily_evaluation(conn,trading_date_kst=date(2026,9,4),ticker='005930',
        provenance=('HELD','SCREENED'),canonical_input=saved.prompt_bytes,account_scope_hash=SCOPE.account_scope_hash,
        envelope=saved,execution_target='mock',lease=lease,observed_at=runtime.clock())
    if consumed:
        claim_daily_dispatch(conn,evaluation.evaluation_id,lease,runtime.clock(),runtime.clock().replace(minute=20))
    return saved,evaluation


def test_first_saved_envelope_and_complete_signal_survive_current_input_change():
    from trading_bot.cli import _load_or_generate_daily_signal,_terminal_daily_signal
    from trading_bot.portfolio import EvaluationTarget,EvaluationProvenance
    from trading_bot.portfolio_store import load_daily_evaluation
    conn=sqlite3.connect(':memory:'); saved,evaluation=seed_dispatch(conn)
    deps=dependencies(conn); runtime=deps['daily_dispatch_runtime']
    runtime.commit_universe(SCOPE,date(2026,9,4),('005930',),'manual-test')
    seen=[]
    class SavedProvider(Provider):
        def generate_signal_from_envelope(self,envelope,admission):
            seen.append(envelope)
            return super().generate_signal_from_envelope(envelope,admission)
    kwargs=dict(conn=conn,trading_date_kst=date(2026,9,4),target=EvaluationTarget('005930',(EvaluationProvenance.HELD,)),
        context=make_data_context(current_price=Money(12345,'KRW')),account_scope_hash=SCOPE.account_scope_hash,
        provider_factory=lambda:SavedProvider([]),lease=deps['mutation_lease'],dispatch_runtime=runtime,
        settings=make_settings(anthropic_model='changed-model'))
    signal,identity=_load_or_generate_daily_signal(**kwargs)
    assert seen==[saved] and identity==evaluation.evaluation_id
    stored=load_daily_evaluation(conn,identity)
    assert _terminal_daily_signal(stored)==signal
    kwargs['provider_factory']=lambda:pytest.fail('final saved signal cannot call a provider')
    assert _load_or_generate_daily_signal(**kwargs)==(signal,identity)


def test_consumed_crash_is_unknown_never_replayed():
    conn=sqlite3.connect(':memory:'); saved,evaluation=seed_dispatch(conn,consumed=True)
    calls=[]
    result=invoke(conn,run_id='consumed-crash',factory=lambda:Provider(calls),candidates=('005930',))
    assert calls==[] and result['outcomes'][0]['final_action']=='HOLD'
    assert conn.execute('SELECT dispatch_state FROM daily_evaluation_dispatches').fetchone()==('DISPATCHED_UNKNOWN',)


def test_cutoff_during_provider_construction_consumes_suppression_without_call():
    conn=sqlite3.connect(':memory:'); deps=dependencies(conn); calls=[]
    def construct():
        deps['daily_dispatch_runtime'].clock.advance(600)
        return Provider(calls)
    invoke(conn,run_id='cutoff',factory=construct,candidates=('005930',))
    assert calls==[]
    with deps['daily_dispatch_runtime'].journal.connection() as c:
        assert tuple(c.execute('SELECT state,invocation_started_at FROM service_provider_admissions').fetchone())==('SUPPRESSED_NO_CALL',None)
    assert conn.execute('SELECT dispatch_state FROM daily_evaluation_dispatches').fetchone()==('DISPATCHED_UNKNOWN',)


def test_entry_before_cutoff_may_finalize_after_cutoff_without_new_sibling_call():
    conn=sqlite3.connect(':memory:'); deps=dependencies(conn); runtime=deps['daily_dispatch_runtime']; calls=[]
    class SlowProvider(Provider):
        def generate_signal(self,context):
            runtime.clock.advance(601)
            return super().generate_signal(context)
    result=invoke(conn,run_id='late-response',factory=lambda:SlowProvider(calls))
    assert calls==['005930'] and all(item['final_action']=='HOLD' for item in result['outcomes'])
    rows=conn.execute('SELECT dispatch_state FROM daily_evaluation_dispatches ORDER BY rowid').fetchall()
    assert rows==[('FINALIZED',),('EXPIRED_NEVER_DISPATCHED',)]


def test_daily_provider_wait_releases_account_and_admission_locks():
    from trading_bot.mutation_lease import acquire_mutation_lease
    from pathlib import Path
    conn = sqlite3.connect(':memory:')
    deps = dependencies(conn)
    runtime = deps['daily_dispatch_runtime']
    original = deps['mutation_lease']
    probes = []
    class ProbeProvider(Provider):
        def generate_signal(self, context):
            assert original.closed
            assert not conn.in_transaction
            competitor = acquire_mutation_lease(conn, account_scope_hash=SCOPE.account_scope_hash,
                lock_dir=Path(original.lock_path).parent, command='risk', cycle_id='risk-during-provider',
                observed_at=runtime.clock())
            assert not competitor.recovery_required
            competitor.release()
            with runtime.controls.admission_lock(): probes.append('both-released')
            return super().generate_signal(context)
    result = invoke(conn, run_id='provider-without-authority', factory=lambda: ProbeProvider([]), candidates=('005930',))
    assert probes == ['both-released']
    assert result['outcomes'][0]['final_action'] == 'HOLD'


def test_daily_data_collection_never_holds_account_lease():
    from trading_bot.cli import run_cycle
    conn = sqlite3.connect(':memory:'); deps = dependencies(conn)
    original = deps['mutation_lease']; seen = []
    class UnownedData(DataSource):
        def screen_daily_candidates(self, day):
            assert original.closed
            seen.append('screen')
            return super().screen_daily_candidates(day)
        def build_context(self, ticker):
            assert conn.execute('SELECT state FROM mutation_leases').fetchone()[0] == 'RELEASED'
            seen.append('context')
            return super().build_context(ticker)
    run_cycle(settings=make_settings(), data_source=UnownedData(('005930',)),
        llm_provider_factory=lambda: Provider([]), broker=Broker(), audit_conn=conn,
        notifier=Notifier(), trading_date='20260904', run_id='unowned-data',
        portfolio_snapshot_reader=lambda: snapshot(snapshot_id=__import__('uuid').uuid4().hex), **deps)
    assert seen == ['screen', 'context']
