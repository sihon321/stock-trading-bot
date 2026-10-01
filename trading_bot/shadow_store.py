"""Dedicated append-only shadow journal; OS locks establish owner death."""
from __future__ import annotations
import fcntl
import os
import sqlite3
import uuid
from pathlib import Path
from .shadow_models import *
from .shadow_budget import ShadowBudget, reserve_bound, settle_attempt_usage

APPLICATION_ID=1397245015


def validate_events(manifest, run_id, events):
    attempts={}; previous='0'*64
    units={s.unit_id:s for s in manifest.snapshots}; variants={v.variant_id:(v,p) for v,p in zip(manifest.variants,manifest.pricing)}
    for seq,e in enumerate(events,1):
        if set(e)!={'seq','prev','type','data','hash'} or e['seq']!=seq or e['prev']!=previous or shadow_content_hash({k:v for k,v in e.items() if k!='hash'})!=e['hash']:
            raise ShadowInputError('JOURNAL_CHAIN_MISMATCH')
        previous=e['hash']; d=e['data']
        if e['type']=='DISPATCH_STARTED':
            if set(d)!={'attempt_id','unit_id','variant_id','repetition','retry_of','snapshot_id','charge'} or d['attempt_id'] in attempts or d['unit_id'] not in units or d['variant_id'] not in variants or type(d['repetition']) is not int or not 0<=d['repetition']<manifest.limits.repetitions or d['snapshot_id']!=units[d['unit_id']].snapshot_id:
                raise ShadowInputError('INVALID_DISPATCH_IDENTITY')
            if not units[d['unit_id']].eligible: raise ShadowInputError('INELIGIBLE_DISPATCH')
            logical=(d['unit_id'],d['variant_id'],d['repetition'])
            prior=d['retry_of']
            if prior:
                if prior not in attempts or attempts[prior].get('observation') is None or attempts[prior]['observation'].status=='SUCCESS' or logical!=tuple(attempts[prior][k] for k in ('unit_id','variant_id','repetition')): raise ShadowInputError('INVALID_RETRY_LINK')
            elif any(logical==tuple(a[k] for k in ('unit_id','variant_id','repetition')) for a in attempts.values()): raise ShadowInputError('DUPLICATE_LOGICAL_DISPATCH')
            v,p=variants[d['variant_id']];bound=reserve_bound(p,v.max_output_tokens)
            expected={'charged_tokens':bound.tokens,'charged_cost_usd':str(bound.cost_usd),'retained_reservation':True,'breach':False}
            if d['charge']!=expected: raise ShadowInputError('INVALID_RESERVATION')
            ShadowBudget(manifest.limits,[a['charge'] for a in attempts.values()]).reserve_attempt_group([(p,v.max_output_tokens)])
            attempts[d['attempt_id']]={**d,'observation':None}
        elif e['type']=='OBSERVATION':
            if set(d)!={'observation','charge'}: raise ShadowInputError('INVALID_OBSERVATION_EVENT')
            o=ShadowObservation.model_validate(d['observation']);a=attempts.get(o.attempt_id)
            if a is None or a['observation'] is not None or o.spec_id!=manifest.spec_id or o.run_id!=run_id or any(getattr(o,k)!=a[k] for k in ('unit_id','variant_id','snapshot_id','repetition','retry_of')): raise ShadowInputError('INVALID_OBSERVATION_TRANSITION')
            v,p=variants[a['variant_id']]
            if o.provider!=v.provider or o.requested_model!=v.model or o.status in ('EXCLUDED','NOT_DISPATCHED'): raise ShadowInputError('INVALID_PROVIDER_ATTRIBUTION')
            charge=settle_attempt_usage(p,v.max_output_tokens,o)
            if charge!=d['charge']: raise ShadowInputError('INVALID_SETTLEMENT')
            a['observation']=o;a['charge']=charge
        else: raise ShadowInputError('UNKNOWN_JOURNAL_EVENT')
    return attempts


class ShadowJournal:
    def __init__(self, path, manifest, *, resume=False):
        self.path=Path(path);self.manifest=manifest;self.conn=None;self.lock_fd=None
        if any(p.is_symlink() for p in (self.path,*self.path.parents)): raise ShadowInputError('UNSAFE_JOURNAL_PATH')
        self.path.parent.mkdir(parents=True,exist_ok=True)
        lock=self.path.with_name(self.path.name+'.owner')
        self.lock_fd=os.open(lock,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        try:
            try: fcntl.flock(self.lock_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError: raise ShadowInputError('SHADOW_OWNER_ACTIVE') from None
            existed=self.path.exists()
            if existed:
                if not self.path.is_file() or self.path.stat().st_size>256*1024*1024: raise ShadowInputError('INVALID_JOURNAL')
                check=sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True)
                try:
                    if check.execute('PRAGMA application_id').fetchone()[0]!=APPLICATION_ID or {r[0] for r in check.execute("SELECT name FROM sqlite_master WHERE type='table'")}!={'shadow_run','shadow_attempt','shadow_event'}: raise ShadowInputError('FOREIGN_JOURNAL')
                finally: check.close()
                if not resume: raise ShadowInputError('JOURNAL_ALREADY_EXISTS')
            elif resume: raise ShadowInputError('JOURNAL_NOT_FOUND')
            self.conn=sqlite3.connect(self.path)
            self.conn.execute('PRAGMA synchronous=FULL')
            if not existed:
                with self.conn:
                    self.conn.execute(f'PRAGMA application_id={APPLICATION_ID}')
                    self.conn.execute('CREATE TABLE shadow_run (run_id TEXT PRIMARY KEY, manifest TEXT NOT NULL)')
                    self.conn.execute('CREATE TABLE shadow_attempt (attempt_id TEXT PRIMARY KEY, document TEXT NOT NULL)')
                    self.conn.execute('CREATE TABLE shadow_event (seq INTEGER PRIMARY KEY, document TEXT NOT NULL)')
                    self.conn.execute('INSERT INTO shadow_run VALUES (?,?)',(uuid.uuid4().hex,canonical_json(manifest)))
            rows=self.conn.execute('SELECT run_id,manifest FROM shadow_run').fetchall()
            if len(rows)!=1 or rows[0][1]!=canonical_json(manifest): raise ShadowInputError('RESUME_MANIFEST_MISMATCH')
            self.run_id=rows[0][0];self.read_shadow_evidence()
        except BaseException:
            self.close();raise
    def close(self):
        if self.conn is not None: self.conn.close();self.conn=None
        if self.lock_fd is not None: os.close(self.lock_fd);self.lock_fd=None
    def __enter__(self): return self
    def __exit__(self,*args): self.close()
    def _append(self, kind, data):
        last=self.conn.execute('SELECT document FROM shadow_event ORDER BY seq DESC LIMIT 1').fetchone()
        last=strict_json(last[0]) if last else None
        body={'seq':last['seq']+1 if last else 1,'prev':last['hash'] if last else '0'*64,'type':kind,'data':data}
        event={**body,'hash':shadow_content_hash(body)}
        self.conn.execute('INSERT INTO shadow_event VALUES (?,?)',(body['seq'],canonical_json(event)))
    def read_shadow_evidence(self):
        events=[strict_json(r[0]) for r in self.conn.execute('SELECT document FROM shadow_event ORDER BY seq')]
        attempts=validate_events(self.manifest,self.run_id,events)
        cached={r[0]:strict_json(r[1]) for r in self.conn.execute('SELECT attempt_id,document FROM shadow_attempt')}
        expected={key:{**a,'observation':a['observation'].model_dump(mode='json') if a['observation'] else None} for key,a in attempts.items()}
        if cached!=expected: raise ShadowInputError('JOURNAL_CARDINALITY_MISMATCH')
        return attempts,events
    def record_dispatch_started(self, specifications):
        with self.conn:
            self.conn.execute('BEGIN IMMEDIATE')
            attempts,_=self.read_shadow_evidence()
            profiles=[]
            for spec in specifications:
                idx=next(i for i,v in enumerate(self.manifest.variants) if v.variant_id==spec['variant_id'])
                profiles.append((self.manifest.pricing[idx],self.manifest.variants[idx].max_output_tokens))
            bounds=ShadowBudget(self.manifest.limits,[a['charge'] for a in attempts.values()]).reserve_attempt_group(profiles)
            result=[]
            for spec,bound in zip(specifications,bounds):
                d={**spec,'attempt_id':uuid.uuid4().hex,'charge':{'charged_tokens':bound.tokens,'charged_cost_usd':str(bound.cost_usd),'retained_reservation':True,'breach':False}}
                self._append('DISPATCH_STARTED',d)
                self.conn.execute('INSERT INTO shadow_attempt VALUES (?,?)',(d['attempt_id'],canonical_json({**d,'observation':None})))
                result.append(d)
            self.read_shadow_evidence()
            return result
    def record_observation(self, observation):
        with self.conn:
            self.conn.execute('BEGIN IMMEDIATE');attempts,_=self.read_shadow_evidence()
            a=attempts.get(observation.attempt_id)
            if a is None or a['observation'] is not None: raise ShadowInputError('INVALID_OBSERVATION_TRANSITION')
            idx=next(i for i,v in enumerate(self.manifest.variants) if v.variant_id==a['variant_id'])
            charge=settle_attempt_usage(self.manifest.pricing[idx],self.manifest.variants[idx].max_output_tokens,observation)
            self._append('OBSERVATION',{'observation':observation.model_dump(mode='json'),'charge':charge})
            self.conn.execute('UPDATE shadow_attempt SET document=? WHERE attempt_id=?',(canonical_json({**a,'observation':observation.model_dump(mode='json'),'charge':charge}),observation.attempt_id))
            self.read_shadow_evidence()
    def recover_unknown_attempts(self):
        # Acquiring flock proves previous ownership ended; heartbeat age never does.
        attempts,_=self.read_shadow_evidence()
        for a in attempts.values():
            if a['observation'] is None:
                v=next(v for v in self.manifest.variants if v.variant_id==a['variant_id'])
                self.record_observation(ShadowObservation(provider=v.provider,requested_model=v.model,status='TIMEOUT_UNKNOWN',validation_code='OWNER_ENDED_AFTER_INTENT',output_complete=False,spec_id=self.manifest.spec_id,run_id=self.run_id,**{k:a[k] for k in ('attempt_id','unit_id','variant_id','snapshot_id','repetition','retry_of')}))

create_shadow_journal=ShadowJournal
acquire_shadow_owner=ShadowJournal
release_shadow_owner=lambda journal: journal.close()
record_dispatch_started=lambda journal,specs: journal.record_dispatch_started(specs)
record_observation=lambda journal,observation: journal.record_observation(observation)
recover_unknown_attempts=lambda journal: journal.recover_unknown_attempts()
read_shadow_evidence=lambda journal: journal.read_shadow_evidence()
