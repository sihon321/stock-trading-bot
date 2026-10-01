import sqlite3
import pytest
from trading_bot.shadow_store import ShadowJournal
from trading_bot.shadow_inputs import prepare_shadow_manifest
from trading_bot.shadow_models import ShadowObservation
from test_shadow_inputs import bundle
from test_shadow_models import variant,pricing


def frozen():
    b=bundle(); return prepare_shadow_manifest(b,[variant()],[pricing()],start=b.calendar[5].session)


def spec(m):
    s=m.snapshots[0];v=m.variants[0]
    return dict(unit_id=s.unit_id,variant_id=v.variant_id,snapshot_id=s.snapshot_id,repetition=0,retry_of=None)


def test_owner_conflict_recovery_and_no_repeated_logical_dispatch(tmp_path):
    m=frozen();path=tmp_path/'shadow.db'
    with ShadowJournal(path,m) as j:
        a=j.record_dispatch_started([spec(m)])[0]
        with pytest.raises(ValueError,match='OWNER_ACTIVE'): ShadowJournal(path,m,resume=True)
    with ShadowJournal(path,m,resume=True) as j:
        j.recover_unknown_attempts();attempts,_=j.read_shadow_evidence()
        assert attempts[a['attempt_id']]['observation'].status=='TIMEOUT_UNKNOWN'
        assert attempts[a['attempt_id']]['charge']['retained_reservation']
        with pytest.raises(ValueError,match='DUPLICATE'): j.record_dispatch_started([spec(m)])
        retry=j.record_dispatch_started([{**spec(m),'retry_of':a['attempt_id']}])
        assert len(retry)==1 and len(j.read_shadow_evidence()[0])==2


def test_foreign_database_unchanged_and_manifest_mismatch(tmp_path):
    path=tmp_path/'audit.db';c=sqlite3.connect(path);c.execute('CREATE TABLE runs (id TEXT)');c.close();before=path.read_bytes()
    with pytest.raises(ValueError,match='FOREIGN'): ShadowJournal(path,frozen(),resume=True)
    assert path.read_bytes()==before
    path=tmp_path/'shadow.db';m=frozen()
    with ShadowJournal(path,m): pass
    from trading_bot.shadow_models import ShadowManifest
    changed=ShadowManifest.model_validate({**m.model_dump(),'seed':'changed','spec_id':''})
    with pytest.raises(ValueError,match='MANIFEST_MISMATCH'): ShadowJournal(path,changed,resume=True)


def test_final_observation_reused_and_cache_tamper_rejected(tmp_path):
    m=frozen();path=tmp_path/'shadow.db'
    with ShadowJournal(path,m) as j:
        a=j.record_dispatch_started([spec(m)])[0]
        o=ShadowObservation(provider='openai',requested_model='fixture-model',status='MALFORMED',validation_code='INVALID',raw_output='bad',spec_id=m.spec_id,run_id=j.run_id,**{k:a[k] for k in ('attempt_id','unit_id','variant_id','snapshot_id','repetition','retry_of')})
        j.record_observation(o)
        with pytest.raises(ValueError): j.record_observation(o)
    with ShadowJournal(path,m,resume=True) as j:
        j.recover_unknown_attempts();assert next(iter(j.read_shadow_evidence()[0].values()))['observation']==o
    c=sqlite3.connect(path);c.execute('DELETE FROM shadow_attempt');c.commit();c.close()
    with pytest.raises(ValueError,match='CARDINALITY'): ShadowJournal(path,m,resume=True)
