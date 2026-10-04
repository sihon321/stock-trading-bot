"""Offline exact-date obligations; no trading collaborators are constructed."""
from datetime import datetime, timedelta
import os

import pytest

from tests.service_fixtures import SCOPE, session_evidence
from trading_bot.service_models import AppliedControl, ExpectationInputs, InstallationScope, KST, OwnerLoginEvidence


def at(hour, minute=0, second=0, day=5):
    return datetime(2026, 10, day, hour, minute, second, tzinfo=KST)


def inputs(*, mode='RUNNING', kind='normal', day=5, login='CONFIRMED', enabled=True, observed=None):
    stamp = observed or at(8, day=day)
    return ExpectationInputs(registered_scopes=(SCOPE,), service_enabled=enabled,
        mode='KIS_MOCK' if enabled else 'DISABLED', config_hash='c'*64,
        config_effective_at=stamp, login_evidence=OwnerLoginEvidence(owner_uid=os.getuid(),
            gui_session_id='gui-1' if login=='CONFIRMED' else None, source_id='owner-gui',
            observed_at=stamp, effective_at=stamp, state=login),
        session=session_evidence(kind, at(8, day=day).date()),
        effective_controls=AppliedControl(revision=0, mode=mode, request_id=None,
            applied_at=stamp, safety_evidence_ids=()), control_scope=InstallationScope(registered_scopes=(SCOPE,)),
        controls_source_id='control-setup', controls_observed_at=stamp, controls_effective_at=stamp)


def test_locked_schedule_priority_cadence_and_no_backlog():
    from trading_bot.service_schedule import ServiceSchedule
    schedule = ServiceSchedule(SCOPE)
    args = inputs()
    assert schedule.tick(at(8,49,59), args.session, args.effective_controls, ()).due == ()
    assert [j.key.kind for j in schedule.tick(at(8,50), args.session, args.effective_controls, ()).due] == ['PREP']
    assert [j.key.kind for j in schedule.tick(at(9), args.session, args.effective_controls, ()).due] == ['RISK']
    now = at(9,10,30)
    result = schedule.tick(now, args.session, args.effective_controls, ())
    assert [j.key.kind for j in result.due] == ['DAILY','RISK']
    assert result.due[1].slot_at == at(9,10)
    saved = ({'kind':'RISK','trading_date_kst':'2026-10-05','state':'RUNNING','last_slot_at':at(9,10)},)
    assert not any(j.key.kind=='RISK' for j in schedule.tick(now,args.session,args.effective_controls,saved).due)
    assert len([j for j in schedule.tick(at(14),args.session,args.effective_controls,saved).due if j.key.kind=='RISK'])==1


@pytest.mark.parametrize('moment,expected', [(at(9,19,59),'DAILY'),(at(9,20),None),(at(14),None)])
def test_strict_daily_deadline(moment,expected):
    from trading_bot.service_schedule import ServiceSchedule
    args=inputs(); result=ServiceSchedule(SCOPE).tick(moment,args.session,args.effective_controls,())
    assert ('DAILY' if any(j.key.kind=='DAILY' for j in result.due) else None)==expected
    if not expected: assert result.missed[0].state=='MISSED'


def test_delayed_open_misses_daily_and_absolute_close_terminates():
    from trading_bot.service_schedule import ServiceSchedule
    args=inputs(kind='delayed'); schedule=ServiceSchedule(SCOPE)
    assert not schedule.tick(at(9,10),args.session,args.effective_controls,()).due
    assert schedule.tick(at(9,20),args.session,args.effective_controls,()).missed[0].state=='MISSED'
    assert [j.key.kind for j in schedule.tick(at(10),args.session,args.effective_controls,()).due]==['RISK']
    assert schedule.tick(at(15,20),args.session,args.effective_controls,()).reconcile_only
    assert schedule.tick(at(15,30),args.session,args.effective_controls,()).terminal


def test_partial_retains_remaining_and_old_dates_do_not_resume():
    from trading_bot.service_schedule import ServiceSchedule
    args=inputs(); schedule=ServiceSchedule(SCOPE)
    row={'kind':'DAILY','trading_date_kst':'2026-10-05','state':'RUNNING',
         'remaining_tickers':('005930','000660')}
    result=schedule.tick(at(9,20),args.session,args.effective_controls,(row,))
    assert result.missed[0].state=='PARTIAL' and result.missed[0].remaining_tickers==('005930','000660')
    tomorrow=inputs(day=6)
    assert schedule.tick(at(9,10,day=6),tomorrow.session,tomorrow.effective_controls,(row,)).due[0].key.trading_date_kst==at(9,day=6).date()


@pytest.mark.parametrize('kwargs,state', [({'kind':'holiday'},'NOT_EXPECTED'),({'enabled':False},'NOT_EXPECTED'),
    ({'login':'ABSENT'},'NOT_EXPECTED'),({'kind':'unknown'},'UNKNOWN'),({'login':'UNKNOWN'},'UNKNOWN')])
def test_expectation_negative_and_unknown(kwargs,state):
    from trading_bot.service_schedule import derive_expectations
    records=derive_expectations(inputs(**kwargs),at(8,40))
    assert {r.state for r in records}=={state}
    assert all(r.producer_kind=='OBSERVER_DERIVED' for r in records)


def test_pause_kill_and_present_samples_never_invent_due_history():
    from trading_bot.service_schedule import derive_expectations
    paused={r.kind:r for r in derive_expectations(inputs(mode='PAUSED'),at(8,40))}
    assert paused['DAILY'].state=='NOT_EXPECTED' and paused['RISK'].state=='EXPECTED'
    killed={r.kind:r for r in derive_expectations(inputs(mode='KILLED'),at(8,40))}
    assert killed['RISK'].state=='EXPECTED' and killed['RISK'].reason_code=='RECONCILIATION_ONLY'
    assert {r.state for r in derive_expectations(inputs(observed=at(10)),at(10))}=={'UNKNOWN'}
    delayed={r.kind:r for r in derive_expectations(inputs(kind='delayed'),at(8,40))}
    assert delayed['RISK'].due_at==at(10) and delayed['DAILY'].due_at==at(9,10)


def test_observer_running_crash_before_any_daily_job_is_detected(tmp_path):
    from trading_bot.service_leader import ServiceLeader
    from trading_bot.service_models import ControlRequest
    from trading_bot.control_runtime import ControlApplier
    from tests.test_service_controls import safety
    producer,reader,clock,journal,controls,probe=producer_fixture(tmp_path)
    leader=ServiceLeader(producer.settings,journal=journal);leader.acquire()
    controls.request_writer(actor='owner').append_request(ControlRequest(request_id='observer-fixture-resume',
        actor='owner',requested_at=clock(),scope=controls.scope,action='RESUME',expected_revision=0))
    ControlApplier(controls.service_capability(leader),validate_resume=lambda scope,now:safety(scope,now),
        current_safety=lambda scope,now:safety(scope,now),clock=clock).apply_pending()
    leader.close()
    producer.publish()
    clock.advance(40*60);producer.publish()
    assert [r.kind for r in reader.absent_obligations(clock(),())]==['PREP','DAILY','RISK']
    with journal.connection() as conn:assert conn.execute('SELECT count(*) FROM service_jobs').fetchone()[0]==0


def test_probe_rejects_wrong_owner_future_or_unbounded_result():
    from trading_bot.service_schedule import OwnerLoginProbe
    valid=inputs().login_evidence
    assert OwnerLoginProbe(lambda:valid,clock=lambda:at(8)).observe_owner_gui()==valid
    for value in ({'state':'CONFIRMED'},valid.model_copy(update={'owner_uid':os.getuid()+1}),
                  valid.model_copy(update={'observed_at':at(9),'effective_at':at(9)})):
        assert OwnerLoginProbe(lambda:value,clock=lambda:at(8)).observe_owner_gui().state=='UNKNOWN'


def producer_fixture(tmp_path, *, day=5, kind='normal', login='CONFIRMED'):
    from tests.service_fixtures import FakeOwnerLoginProbe, FakeServiceClock, TempServiceTopology
    from trading_bot.service_store import ServiceJournal
    from trading_bot.control_store import ControlStore
    from trading_bot.service_schedule import ExpectationProducer, ExpectationHistoryReader
    clock=FakeServiceClock(at(8,40,day=day))
    settings=TempServiceTopology(tmp_path).registration(enabled=True)
    config=tmp_path/'config'/'enabled.json'
    os.utime(config,(at(8,day=day).timestamp(),at(8,day=day).timestamp()))
    evidence=session_evidence(kind,at(8,day=day).date()).model_copy(update={
        'source_id':f'krx-notice-{day}', 'notice_id':f'notice-{day}', 'reviewer':'owner'})
    settings.session_evidence_path.write_text(evidence.model_dump_json())
    controls=ControlStore(settings,clock=clock); controls.initialize(actor='owner')
    journal=ServiceJournal(settings,clock=clock); journal.initialize()
    probe=FakeOwnerLoginProbe(login,clock)
    producer=ExpectationProducer(settings,config_path=config,login_probe=probe,
        control_reader=controls.reader(),writer=journal.expectation_writer(),clock=clock)
    return producer,ExpectationHistoryReader(settings),clock,journal,controls,probe


def test_observer_only_absent_jobs_survive_midnight_and_restart(tmp_path):
    producer,reader,clock,journal,controls,probe=producer_fixture(tmp_path)
    first=producer.publish()
    assert len(first)==3 and not journal.load_job(first[0].source_id)
    clock.advance(40*60)
    producer.publish()
    missed=reader.absent_obligations(clock(),())
    assert [r.kind for r in missed]==['PREP','RISK']  # conservative initial PAUSE suppresses DAILY
    clock.advance(24*3600)
    producer.publish()  # no exact notice for tomorrow, never reuse yesterday
    assert any(r.kind=='PREP' and r.trading_date_kst==at(8).date() for r in reader.absent_obligations(clock(),()))
    assert {r.state for r in reader.for_date(at(8,day=6).date())}=={'UNKNOWN'}
    assert len(reader.for_date(at(8).date()))>=3


@pytest.mark.parametrize('change', ['holiday','disabled','logout','calendar','login','control'])
def test_observer_negative_unknown_inputs_do_not_create_false_miss(tmp_path,change):
    producer,reader,clock,journal,controls,probe=producer_fixture(tmp_path,
        kind='holiday' if change=='holiday' else 'normal', login='ABSENT' if change=='logout' else 'UNKNOWN' if change=='login' else 'CONFIRMED')
    if change=='disabled':
        disabled=producer.settings.model_copy(update={'mode':'DISABLED','service_enabled':False})
        producer.config_path.write_text(disabled.model_dump_json())
    elif change=='calendar': producer.settings.session_evidence_path.unlink()
    elif change=='control': controls.path.chmod(0o644)
    producer.publish()
    clock.advance(3600)
    producer.publish()
    assert reader.absent_obligations(clock(),())==()
