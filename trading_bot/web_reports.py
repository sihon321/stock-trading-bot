"""Registered saved reports: immutable, attributable projections without execution.

Proof catalogs are server-owned registration data. They are never request inputs.
No saved fact can grant trading, policy mutation or promotion authority.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, replace
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
import re
import sqlite3
from types import MappingProxyType
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .web_config import checked_path
from .web_evidence import _clean, _transaction, _check_run, EvidenceUnavailable
from .web_models import ResourceScope, EvidenceSelection, SourceEnvelope
from .replay_evidence import canonical_json_bytes

FAMILIES = ('daily', 'period', 'replay', 'backtest', 'shadow', 'soak', 'calibration', 'readiness')
FORMATS = ('txt', 'json', 'csv')
_ID = r'^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$'


class ReportRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid', hide_input_in_errors=True)
    family: Literal['daily','period','replay','backtest','shadow','soak','calibration','readiness']
    resource_id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')
    result_id: str | None = Field(default=None, pattern=_ID)
    start: date | None = None
    end: date | None = None
    formats: tuple[Literal['txt','json','csv'], ...] = FORMATS

    @model_validator(mode='after')
    def bounded(self):
        if not self.formats or len(set(self.formats)) != len(self.formats):
            raise ValueError('unique formats required')
        if self.family == 'daily' and (self.start is None or self.end is not None):
            raise ValueError('daily date required')
        if self.family == 'period' and (self.start is None or self.end is None or
                not 0 <= (self.end-self.start).days < 366):
            raise ValueError('bounded report period required')
        if self.family not in {'daily','period'} and (self.start is not None or self.end is not None):
            raise ValueError('saved result window cannot be changed')
        return self


@dataclass(frozen=True)
class ReportCatalogEntry:
    family: str
    resource_ids: tuple[str, ...]
    formats: tuple[str, ...] = FORMATS


@dataclass(frozen=True)
class ReportRow:
    record_id: str
    kind: str
    state: str
    fields: tuple[tuple[str, object], ...]

    @property
    def data(self):
        return MappingProxyType(dict(self.fields))


@dataclass(frozen=True)
class ReportMetric:
    metric_id: str
    selection_id: str
    value: object
    numerator: int | None
    denominator: int | None
    constituent_ids: tuple[str, ...]
    excluded_ids: tuple[str, ...] = ()
    unknown_ids: tuple[str, ...] = ()
    unit: str = 'saved_fact'
    determinate_denominator: int | None = None


@dataclass(frozen=True)
class SavedReportProjection:
    family: str
    status: str
    selection: EvidenceSelection
    envelope: SourceEnvelope
    rows: tuple[ReportRow, ...] = ()
    metrics: tuple[ReportMetric, ...] = ()
    facts: tuple[tuple[str, object], ...] = ()
    labels: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()
    period: tuple[str, str] | None = None

    def metric_detail(self, metric_id):
        metric = next((m for m in self.metrics if m.metric_id == metric_id), None)
        if metric is None:
            raise ValueError('unknown metric')
        ids = set(metric.constituent_ids + metric.excluded_ids + metric.unknown_ids)
        return tuple(row for row in self.rows if row.record_id in ids)


@dataclass(frozen=True)
class SavedCalibrationProof:
    resource_id: str
    campaign_id: str
    evaluations: tuple
    source_identities: tuple[str, ...]
    # Each recorded outcome has an independently saved price for exposure arithmetic.
    outcome_prices: tuple[tuple[str, str, float], ...]
    expected_hash: str

    def document(self):
        return (self.resource_id, self.campaign_id, self.evaluations,
                self.source_identities, self.outcome_prices)


@dataclass(frozen=True)
class SavedReadinessFacts:
    resource_id: str
    campaign_id: str
    evidence: object
    policy_snapshot: tuple
    rollback_ack: bool
    kill_ack: bool
    manual_approval: bool
    expected_hash: str

    def document(self):
        return (self.resource_id, self.campaign_id, self.evidence, self.policy_snapshot,
                self.rollback_ack, self.kill_ack, self.manual_approval)


def proof_hash(document):
    def default(value):
        if isinstance(value, Decimal):return {'decimal':str(value)}
        if isinstance(value, (date,datetime)):return value.isoformat()
        if hasattr(type(value),'__dataclass_fields__'):
            return {f.name:getattr(value,f.name) for f in fields(value)}
        raise TypeError('unsupported saved proof value')
    return hashlib.sha256(json.dumps(document,default=default,sort_keys=True,
        separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def _scalar(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise EvidenceUnavailable('NONFINITE_SOURCE_NUMBER')
        return value
    if value is None or isinstance(value, (str, int, float, bool)):
        return _clean(value)
    raise EvidenceUnavailable('INVALID_PROJECTION_FIELD')


def _row(record_id, kind, obj, names, state='COMPLETE'):
    if len(record_id) > 512 or _clean(record_id) != record_id:
        raise EvidenceUnavailable('INVALID_SOURCE_ID')
    def get(name):
        return obj[name] if isinstance(obj, (dict, sqlite3.Row)) else getattr(obj, name)
    return ReportRow(record_id, kind, state, tuple((n, _scalar(get(n))) for n in names))


class SavedReportService:
    def __init__(self, settings, *, store=None, clock=lambda: datetime.now(timezone.utc),
                 shadow_proof_catalog=None, calibration_proof_catalog=(), readiness_proof_catalog=()):
        self.settings, self.store, self.clock = settings, store, clock
        self.shadow_proof_catalog = shadow_proof_catalog
        self.calibration_proofs = self._proofs(calibration_proof_catalog, SavedCalibrationProof)
        self.readiness_proofs = self._proofs(readiness_proof_catalog, SavedReadinessFacts)

    @staticmethod
    def _proofs(proofs, cls):
        result = {}
        for proof in proofs:
            if not isinstance(proof, cls) or not re.fullmatch(r'[a-f0-9]{64}', proof.expected_hash):
                raise ValueError('registered proof required')
            key = (proof.resource_id, proof.campaign_id)
            if key in result:
                raise ValueError('duplicate registered proof')
            result[key] = proof
        return MappingProxyType(result)

    def catalog(self):
        owners = {'daily':('audit',), 'period':('audit',), 'replay':('replay',),
            'backtest':('backtest',), 'shadow':('shadow',), 'soak':('soak',),
            'calibration':('soak','calibration'), 'readiness':('soak',)}
        return tuple(ReportCatalogEntry(f, tuple(r.id for r in self.settings.registered_resources
            if r.owner in owners[f])) for f in FAMILIES)

    def _linked(self, resource, owner):
        matched = tuple(r for r in self.settings.registered_resources if r.owner == owner
            and r.account_hash == resource.account_hash and r.target == resource.target)
        if len(matched) != 1:
            raise EvidenceUnavailable('REGISTERED_SOURCE_LINK_MISSING')
        return matched[0]

    def project(self, request):
        request = ReportRequest.model_validate(request)
        resource = self.settings.resource(request.resource_id)
        if resource.id not in next(e.resource_ids for e in self.catalog() if e.family == request.family):
            raise ValueError('report family does not own resource')
        if request.family == 'period' and (request.end-request.start).days >= self.settings.export_days:
            raise ValueError('export period bound exceeded')
        scope = ResourceScope(resource.account_hash, resource.target, resource.id)
        period = (request.start.isoformat(), (request.end or request.start).isoformat()) if request.start else None
        sid = proof_hash((request.family, resource.id, scope, request.result_id, period))
        selection = EvidenceSelection(sid, resource.id, request.family, scope)
        env = SourceEnvelope(resource.id, resource.owner, None, resource.account_hash,
            resource.target, self.clock(), provenance='saved')
        try:
            path = checked_path(resource.path)
            if not path.is_file():
                raise EvidenceUnavailable('SOURCE_MISSING')
            if resource.owner in {'replay','backtest','shadow','calibration'} and path.stat().st_size > self.settings.export_bytes:
                raise EvidenceUnavailable('SOURCE_BYTE_BOUND')
            rows, values, facts, labels, source_ids = getattr(self, '_'+request.family)(request, resource)
            if len(rows) > self.settings.export_rows:
                raise EvidenceUnavailable('SOURCE_ROW_BOUND')
            ids = tuple(row.record_id for row in rows)
            if len(set(ids)) != len(ids):
                raise EvidenceUnavailable('DUPLICATE_SOURCE_ID')
            # Selection identity binds the exact sanitized facts/constituents, not format/query time.
            sid = proof_hash((sid, ids, source_ids, rows, values, facts))
            selection = replace(selection, selection_id=sid, record_ids=ids,
                source_ids=tuple(source_ids), denominator=len(rows))
            metrics = tuple(ReportMetric(name, sid, value, numerator, denominator,
                tuple(used), tuple(excluded), tuple(unknown), unit, determinate)
                for name,value,numerator,denominator,used,excluded,unknown,unit,determinate in values)
            if any(not set(m.constituent_ids+m.excluded_ids+m.unknown_ids) <= set(ids) for m in metrics):
                raise EvidenceUnavailable('BROKEN_METRIC_LINK')
            completeness = 'UNKNOWN' if any(row.state == 'UNKNOWN' for row in rows) else (
                'INCOMPLETE' if any(row.state == 'INCOMPLETE' for row in rows) else 'COMPLETE')
            return SavedReportProjection(request.family, 'AVAILABLE', selection,
                replace(env, completeness=completeness), tuple(rows), metrics,
                tuple(facts), tuple(labels), period=period)
        except (ValueError, KeyError, OSError, sqlite3.Error, TypeError, RuntimeError) as exc:
            code = str(exc) if isinstance(exc, EvidenceUnavailable) else getattr(exc, 'code', None)
            if request.family == 'shadow' and type(exc).__name__ == 'SavedShadowUnavailable':
                code = exc.code
            if not isinstance(code, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,95}', code):
                code = 'SAVED_EVIDENCE_UNAVAILABLE'
            return SavedReportProjection(request.family, 'UNKNOWN', selection,
                replace(env, completeness='UNKNOWN', diagnostic_code=code),
                diagnostics=(code,), period=period)

    @staticmethod
    def _metric(name, value, rows, *, numerator=None, denominator=None, excluded=(), unknown=(), unit='saved_fact', determinate=None):
        return (name, _scalar(value), numerator, denominator,
            tuple(r.record_id for r in rows), tuple(excluded), tuple(unknown), unit, determinate)

    def _daily(self, request, resource):
        return self._audit(request, resource)

    def _period(self, request, resource):
        return self._audit(request, resource)

    def _audit(self, request, resource):
        from .reporting import ReadOnlyAuditRepository, build_daily_report, build_period_report
        start, end = request.start, request.end or request.start
        with _transaction(resource) as conn:
            runs = conn.execute("SELECT run_id FROM runs WHERE REPLACE(trading_date_kst,'-','') BETWEEN ? AND ? LIMIT 10001",
                (start.strftime('%Y%m%d'), end.strftime('%Y%m%d'))).fetchall()
            if len(runs) > self.settings.export_rows:
                raise EvidenceUnavailable('SOURCE_ROW_BOUND')
            for row in runs:
                _check_run(conn, resource, row['run_id'])
            count = conn.execute("SELECT count(*) FROM ticker_outcomes t JOIN runs r ON r.run_id=t.run_id WHERE REPLACE(r.trading_date_kst,'-','') BETWEEN ? AND ?",
                (start.strftime('%Y%m%d'), end.strftime('%Y%m%d'))).fetchone()[0]
            if count > self.settings.export_rows:
                raise EvidenceUnavailable('SOURCE_ROW_BOUND')
        repo = ReadOnlyAuditRepository(resource.path)
        report = build_daily_report(repo, start) if request.family == 'daily' else build_period_report(repo, start, end)
        rows = []
        for run in report.runs:
            if run.target != resource.target:
                raise EvidenceUnavailable('SCOPE_CONFLICT')
            rows.append(_row('runs:'+run.run_id,'runs',run,
                ('run_id','run_kind','target','run_status','run_state','final_summary_notification_state'), str(run.run_state)))
            for candidate in run.candidates:
                rows.append(_row(f'candidates:{run.run_id}:{candidate.processing_id}', 'candidates', candidate,
                    ('run_id','run_kind','ticker','target','decision','confidence','reason_code','reason_ko',
                     'reason_detail','ticker_state','order_state','reconciliation_state'), str(candidate.ticker_state)))
                for attempt in candidate.notification_attempts:
                    rows.append(_row(f'notifications:{attempt.attempt_id}','notifications',attempt,
                        ('attempt_id','kind','delivery_state','failure_category','observed_at')))
            for attempt in run.run_notification_attempts:
                rows.append(_row(f'notifications:{attempt.attempt_id}','notifications',attempt,
                    ('attempt_id','kind','delivery_state','failure_category','observed_at')))
        candidates = tuple(r for r in rows if r.kind == 'candidates')
        unknown = tuple(r.record_id for r in candidates if r.state == 'UNKNOWN')
        metrics = [self._metric('total_candidates', report.total_candidates,candidates, denominator=len(candidates))]
        for state in ('complete','incomplete','unknown'):
            count = getattr(report,state)
            metrics.append(self._metric(state,count.numerator,
                tuple(r for r in candidates if r.state == state.upper()), numerator=count.numerator,
                denominator=count.total_denominator, unknown=unknown,
                excluded=tuple(r.record_id for r in candidates if r.state not in {state.upper(),'UNKNOWN'}),
                determinate=count.determinate_denominator))
        return rows,metrics,(),('SAVED','TARGET_SEPARATE','RUN_KIND_SEPARATE'),tuple(r.run_id for r in report.runs)

    def _replay(self, request, resource):
        from .reporting import load_replay_results, build_replay_report, _strict_json
        document = _strict_json(resource.path)
        loaded = load_replay_results((resource.path,))
        if _strict_json(resource.path) != document:
            raise EvidenceUnavailable('SOURCE_CHANGED')
        report = build_replay_report(loaded)
        result = loaded[0]
        if request.result_id and request.result_id != result.stable_result_id:
            raise EvidenceUnavailable('RESULT_NOT_FOUND')
        names = ('scenario_id','ticker','action','decision','confidence','reason','blocked_reason',
            'selected','buy_signaled','confidence_qualified','risk_qualified','validly_sized','order_eligible','matched','position_quantity_after')
        rows = tuple(_row(f'outcomes:{result.stable_result_id}:{i}','outcomes',outcome,
            tuple(n for n in names if n in outcome))
            for i,outcome in enumerate(document['evidence']['outcomes']))
        metrics=[]
        for name in ('evaluated','selected','buy_signaled','confidence_qualified','risk_qualified','validly_sized','order_eligible'):
            count=getattr(result.funnel,name)
            chosen=rows if name=='evaluated' else tuple(r for r in rows if r.data.get(name) is True)
            if len(chosen)!=count.numerator:raise EvidenceUnavailable('SAVED_REPLAY_METRIC_LINK_MISMATCH')
            metrics.append(self._metric(name,count.numerator,chosen,numerator=count.numerator,denominator=count.denominator,
                excluded=tuple(r.record_id for r in rows if r not in chosen)))
        for group, counts in (('actions',result.funnel.actions),('blocked_reasons',result.funnel.blocked_reasons)):
            for name,count in counts.items():
                chosen=tuple(r for r in rows if r.data.get('action' if group=='actions' else 'blocked_reason')==name)
                metrics.append(self._metric(group+'.'+name,count.numerator,chosen,numerator=count.numerator,
                    denominator=count.denominator,excluded=tuple(r.record_id for r in rows if r not in chosen)))
        return rows,metrics,(('verification_status',result.verification_status),),('SIMULATION',report.disclaimer),(result.stable_result_id,)

    def _backtest(self, request, resource):
        from .backtest_reporting import load_backtest_result
        result=load_backtest_result(resource.path)
        if request.result_id and request.result_id != result.result_id:
            raise EvidenceUnavailable('RESULT_NOT_FOUND')
        run=result.run;rows=[]
        for kind,items,names in (
            ('sessions',run.sessions,('session','settled_cash','reserved_cash','pending_cash','net_equity','gross_equity','coverage_status','realized_pnl','unrealized_pnl','action_cash')),
            ('decisions',run.decisions,('session','ticker','action','reason','selected','risk_override','intent_id','quantity')),
            ('fills',run.fills,('intent_id','ticker','side','session','quantity','reference_price','executed_price','commission','sell_tax','surtax','slippage_drag','reason')),
            ('benchmark',run.benchmark,('session','close'))):
            for i,item in enumerate(items):
                state=str(item.coverage_status.value) if kind=='sessions' else ('INCOMPLETE' if kind=='fills' and not item.quantity else 'COMPLETE')
                rows.append(_row(f'{kind}:{result.result_id}:{i}',kind,item,names,state))
        metrics=[]
        fill_names={'commission','sell_tax','surtax','slippage_drag','fill_count','partial_count','nonfill_count','turnover'}
        for name in type(result.metrics).model_fields:
            value=getattr(result.metrics,name)
            constituents=tuple(r for r in rows if r.kind==('fills' if name in fill_names else 'sessions'))
            if name=='benchmark_return':constituents=tuple(r for r in rows if r.kind=='benchmark')
            if isinstance(value,(dict,tuple)):
                facts=value.items() if isinstance(value,dict) else enumerate(value)
                for sub,number in facts:
                    subset=tuple(r for r in rows if r.kind==('decisions' if name=='decision_reasons' else 'fills') and r.data.get('reason')==sub) if isinstance(value,dict) else constituents[int(sub):int(sub)+1]
                    metrics.append(self._metric(f'{name}.{sub}',number,subset))
            else:metrics.append(self._metric(name,value,constituents,unknown=tuple(r.record_id for r in constituents if r.state!='COMPLETE')))
        facts=[('result_id',result.result_id),('coverage',run.final_coverage.value),('initial_equity',run.initial_equity)]
        for group in ('window','profile'):
            facts.extend((group+'.'+key,_scalar(value)) for key,value in run.manifest[group].items()
                if value is None or isinstance(value,(str,int,float,bool,Decimal)))
        facts.extend((f'limitation.{i}',_scalar(v)) for i,v in enumerate(run.limitations))
        return rows,metrics,facts,('MODELED','모의 계산 · 수익 보장이나 실거래 승인이 아닙니다.'),(result.result_id,)

    def _shadow(self, request, resource):
        from .shadow_reporting import load_shadow_result
        from .shadow_models import strict_json
        result=load_shadow_result(resource.path,proof_catalog=self.shadow_proof_catalog)
        if request.result_id and request.result_id!=result.result_id:
            raise EvidenceUnavailable('RESULT_NOT_FOUND')
        m=strict_json(result.metrics_document_json);rows=[]
        for o in result.observations:
            rows.append(_row('observations:'+o.attempt_id,'observations',o,
                ('attempt_id','unit_id','variant_id','status','requested_model','returned_model'),
                'COMPLETE' if o.status=='SUCCESS' else 'UNKNOWN'))
        for i,c in enumerate(m['comparisons']):
            rows.append(_row(f'comparisons:{result.run_id}:{i}','comparisons',c,
                tuple(c), 'COMPLETE' if c['valid_pair'] else 'UNKNOWN'))
        from .shadow_evidence import SavedShadowProof
        registered=self.shadow_proof_catalog.resolve(result.manifest.spec_id,result.run_id)
        proof=SavedShadowProof.model_validate(strict_json(registered.document_json))
        for unit in proof.inventory:
            rows.append(_row('inventory:'+unit.unit_id,'inventory',unit,
                ('unit_id','ticker','session','eligible','selected','critical_unknown','news_available'),
                'COMPLETE' if unit.unit_id in {s.unit_id for s in result.manifest.snapshots} else 'EXCLUDED'))
            for kind,reasons in (('exclusions',unit.exclusions),('unknowns',unit.unknowns)):
                rows.extend(ReportRow(f'{kind}:{unit.unit_id}:{i}',kind,
                    'EXCLUDED' if kind=='exclusions' else 'UNKNOWN',
                    (('unit_id',unit.unit_id),('reason',_scalar(reason)))) for i,reason in enumerate(reasons))
        metrics=[]
        for v in m['variants']:
            variant=v['variant_id']
            constituents=tuple(r for r in rows if r.data.get('variant_id')==variant or r.kind=='inventory')
            for key,value in v.items():
                if value is None or isinstance(value,(str,int,float,bool)):
                    metrics.append(self._metric(variant+'.'+key,value,constituents,
                        numerator=v.get(key.replace('_denominator','_numerator')) if key.endswith('_denominator') else None,
                        denominator=value if key.endswith('_denominator') else None,
                        unknown=tuple(r.record_id for r in constituents if r.state=='UNKNOWN'),unit='ESTIMATED' if 'estimated' in key else 'saved_fact'))
        facts=[('result_id',result.result_id),('run_id',result.run_id),('spec_id',result.manifest.spec_id),('status',result.status)]
        for key,value in m['coverage'].items():
            if value is None or isinstance(value,(str,int,float,bool)):facts.append(('coverage.'+key,_scalar(value)))
        for v in result.manifest.variants:
            facts.extend((v.variant_id+'.'+key,_scalar(getattr(v,key))) for key in ('model','prompt_hash'))
        facts.extend(('limits.'+key,_scalar(getattr(result.manifest.limits,key))) for key in type(result.manifest.limits).model_fields)
        return rows,metrics,facts,('SHADOW','ADVISORY','UNKNOWN_USAGE','ESTIMATED','CURRENT_MODEL_HINDSIGHT_CONTAMINATION'),(result.result_id,result.manifest.baseline_hash,result.manifest.spec_id)

    def _soak_data(self, request, resource):
        from .soak_reporting import ReadOnlySoakRepository, build_soak_report
        if not request.result_id:
            raise EvidenceUnavailable('CAMPAIGN_ID_REQUIRED')
        audit=self._linked(resource,'audit');controller=self._linked(resource,'controller')
        # Preflight caps every owner table the saved reader scans; no truncated aggregate.
        for r in (audit,resource,controller):
            with _transaction(r) as conn:
                tables=conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                for table in tables:
                    name=table[0]
                    if not re.fullmatch('[A-Za-z0-9_]+',name):raise EvidenceUnavailable('UNSUPPORTED_SCHEMA')
                    if conn.execute(f'SELECT count(*) FROM {name}').fetchone()[0]>self.settings.export_rows:
                        raise EvidenceUnavailable('SOURCE_ROW_BOUND')
                if r.owner=='audit':
                    for row in conn.execute('SELECT run_id FROM runs'):_check_run(conn,r,row[0])
        data=ReadOnlySoakRepository(audit.path,resource.path,controller.path).load(request.result_id)
        class Snapshot:
            def load(self, campaign_id):return data
        return data,build_soak_report(Snapshot(),request.result_id),(audit.id,resource.id,controller.id,request.result_id)

    def _soak(self, request, resource):
        from .soak_reporting import _valid_snapshot_reference, _valid_comparison_reference, _valid_primary_reference, _valid_release
        data,report,sources=self._soak_data(request,resource);rows=[]
        specs={'days':('id',('run_id','trading_date','credit_state')),
            'events':('id',('run_id','event_code','evidence_class')),
            'snapshots':('snapshot_id',('run_id','snapshot_id','stage','completeness','ticker','order_intent_id')),
            'comparisons':('comparison_id',('run_id','snapshot_id','ticker','order_intent_id','verdict','remaining_order_terminal')),
            'freezes':('id',('freeze_id','ticker','order_intent_id','freeze_kind','state')),
            'releases':('id',('freeze_id','ticker','order_intent_id','state','release_evidence_id')),
            'ambiguity_observations':('id',('observation_id','run_id','ticker','order_intent_id','verdict')),
            'links':('id',('drill_id','evidence_class','verdict','primary_run_id'))}
        for kind,(key,names) in specs.items():
            for item in data[kind]:
                valid=True
                if kind=='snapshots':valid=_valid_snapshot_reference(data,item)
                if kind=='comparisons':valid=_valid_comparison_reference(data,item)
                if kind=='links':valid=_valid_primary_reference(data,item) and (item['evidence_class']!='CONTROLLED_INJECTION' or bool(data['controller'].get(item['drill_id']) and data['controller'][item['drill_id']]['verdict']==item['verdict']))
                if kind=='releases':
                    valid=any(_valid_release(data,f,item) for f in data['freezes'] if f['freeze_id']==item['freeze_id'])
                state='UNKNOWN' if not valid else ('INCOMPLETE' if kind=='snapshots' and item['completeness']=='INCOMPLETE' else 'COMPLETE')
                rows.append(_row(f'{kind}:{request.result_id}:{item[key]}',kind,item,tuple(n for n in names if n in item.keys()),state))
        metrics=[]
        for group,obj,kinds in (('campaign',report.campaign,('days','events')),
            ('reconciliation',report.reconciliation,('snapshots','comparisons')),
            ('freezes',report.freezes,('freezes','releases','ambiguity_observations'))):
            selected=tuple(r for r in rows if r.kind in kinds)
            for f in fields(obj):
                value=getattr(obj,f.name)
                if value is None or isinstance(value,(str,int,float,bool)):
                    metrics.append(self._metric(group+'.'+f.name,value,selected,unknown=tuple(r.record_id for r in selected if r.state=='UNKNOWN')))
        for drill in report.drills:
            selected=tuple(r for r in rows if r.kind=='links' and r.data['evidence_class']==drill.evidence_class.value)
            for name in ('passed','failed','unknown'):
                metrics.append(self._metric('drills.'+drill.evidence_class.value+'.'+name,getattr(drill,name),selected,
                    numerator=getattr(drill,name),denominator=drill.required,unit=drill.evidence_class.value))
        facts=(('cross_store_unknown',report.cross_store_unknown),('resolved_historical_ambiguity',report.resolved_historical_ambiguity))
        return rows,metrics,facts,('SAVED','INDEPENDENT_OWNER_TRANSACTIONS','INDEPENDENT_DENOMINATORS'),sources

    def _calibration(self, request, resource):
        from .calibration_reporting import ReadOnlyCalibrationEvidenceRepository, build_calibration_report
        from .calibration_evidence import VariantMetrics
        proof=self.calibration_proofs.get((resource.id,request.result_id))
        if proof is None:raise EvidenceUnavailable('SAVED_CALIBRATION_PROOF_MISSING')
        if proof_hash(proof.document())!=proof.expected_hash:raise EvidenceUnavailable('SAVED_CALIBRATION_PROOF_INVALID')
        audit=self._linked(resource,'audit');soak=resource if resource.owner=='soak' else self._linked(resource,'soak')
        evidence=ReadOnlyCalibrationEvidenceRepository(audit.path,soak.path).load(proof.campaign_id)
        prices={(scenario,ticker):price for scenario,ticker,price in proof.outcome_prices}
        normal_subjects={(c.run_id,o.ticker) for c in evidence.normal_cycles for o in c.observations}
        if set(prices)!=normal_subjects or len(prices)!=len(proof.outcome_prices):
            raise EvidenceUnavailable('SAVED_CALIBRATION_SOURCE_LINK_MISSING')
        rows=[]
        for evaluation in proof.evaluations:
            outcomes=evaluation.outcomes
            if not outcomes or len(outcomes)!=evaluation.metrics.denominator or len({(o.scenario_id,o.ticker) for o in outcomes})!=len(outcomes):
                raise EvidenceUnavailable('SAVED_CALIBRATION_OUTCOMES_MISSING')
            if set(prices)!={(o.scenario_id,o.ticker) for o in outcomes}:
                raise EvidenceUnavailable('SAVED_CALIBRATION_PRICE_LINK_MISSING')
            if any(type(v) not in {int,float} or not math.isfinite(v) or v<=0 for v in prices.values()):
                raise EvidenceUnavailable('SAVED_CALIBRATION_PRICE_INVALID')
            metrics=VariantMetrics(len(outcomes),len(outcomes),sum(o.action=='BUY' for o in outcomes),
                sum(o.action=='HOLD' for o in outcomes),sum(o.action=='SELL' for o in outcomes),
                sum(o.order_eligible for o in outcomes),sum(o.blocked_reason=='LOW_CONFIDENCE' for o in outcomes),
                sum(o.blocked_reason=='RISK_BLOCK' for o in outcomes),sum(o.reason=='risk override: stop_loss' for o in outcomes),
                sum(o.reason=='risk override: take_profit' for o in outcomes),
                sum(o.position_quantity_after*prices[o.scenario_id,o.ticker] for o in outcomes),sum(not o.matched for o in outcomes))
            if metrics!=evaluation.metrics:raise EvidenceUnavailable('SAVED_CALIBRATION_METRICS_MISMATCH')
            for i,o in enumerate(outcomes):
                rows.append(_row(f'outcomes:{evaluation.variant.variant_id}:{i}','outcomes',o,
                    ('scenario_id','ticker','action','reason','blocked_reason','order_eligible','matched','position_quantity_after')))
        for kind,ids in (('excluded',evidence.excluded_cycle_ids),('unknown',evidence.unknown_cycle_ids)):
            rows.extend(ReportRow(f'{kind}:{i}',kind,kind.upper(),(('run_id',_scalar(i)),)) for i in ids)
        report=build_calibration_report(evidence,proof.evaluations,source_identities=proof.source_identities)
        metrics=[]
        for e in proof.evaluations:
            selected=tuple(r for r in rows if r.record_id.startswith('outcomes:'+e.variant.variant_id+':'))
            for f in fields(e.metrics):metrics.append(self._metric(e.variant.variant_id+'.'+f.name,getattr(e.metrics,f.name),selected,denominator=e.metrics.denominator,
                excluded=tuple(r.record_id for r in rows if r.kind=='excluded'),unknown=tuple(r.record_id for r in rows if r.kind=='unknown')))
        facts=(('calibration_id',report.calibration_id),('grade',report.evidence_grade.value),('eligible_days',report.eligible_days),('normal_cycles',report.normal_cycles),('excluded_cycles',report.excluded_cycles),('unknown_cycles',report.unknown_cycles),('judgment',report.judgment.status.value))
        return rows,metrics,facts,('ADVISORY','NO_POLICY_MUTATION'),proof.source_identities+(report.calibration_id,)

    def _readiness(self, request, resource):
        from .promotion_readiness import build_readiness_assessment
        proof=self.readiness_proofs.get((resource.id,request.result_id))
        if proof is None:raise EvidenceUnavailable('SAVED_READINESS_FACTS_MISSING')
        if proof_hash(proof.document())!=proof.expected_hash or any(type(v) is not bool for v in (proof.rollback_ack,proof.kill_ack,proof.manual_approval)):
            raise EvidenceUnavailable('SAVED_READINESS_FACTS_INVALID')
        _,soak,sources=self._soak_data(request,resource)
        # Saved approval cannot waive current saved campaign/freeze/link evidence.
        evidence=replace(proof.evidence,credited_days=soak.campaign.credited_days,
            target_days=soak.campaign.target_days,safety_failure_code=soak.campaign.safety_failure_code,
            reconciliation_incomplete=soak.reconciliation.incomplete,reconciliation_unknown=soak.reconciliation.unknown,
            active_freezes=soak.freezes.active_count,cross_store_unknown=soak.cross_store_unknown,
            resolved_historical_ambiguity=soak.resolved_historical_ambiguity)
        result=build_readiness_assessment(evidence,policy_snapshot=proof.policy_snapshot,
            rollback_ack=proof.rollback_ack,kill_ack=proof.kill_ack,manual_approval=proof.manual_approval)
        rows=tuple(ReportRow('checks:'+c.code,'checks',c.state.value,
            (('code',c.code),('state',c.state.value))+tuple((k,_scalar(v)) for k,v in c.evidence)) for c in result.checks)
        metrics=tuple(self._metric(c.code,c.state.value,(r,),numerator=int(c.state.value=='PASS'),denominator=1,
            unknown=(r.record_id,) if c.state.value=='UNKNOWN' else ()) for c,r in zip(result.checks,rows))
        return rows,metrics,(('assessment_id',result.assessment_id),('calibration_id',result.calibration_id),('state',result.state.value)),('ADVISORY','READ_ONLY_ASSESSMENT'),proof.evidence.source_identities+sources+(result.assessment_id,)
