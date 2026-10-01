"""Offline canonical snapshots. Historical inputs never fetch current data."""
from __future__ import annotations
import hashlib
import subprocess
from datetime import datetime
from pathlib import Path
from .shadow_models import *
from .backtest_engine import run_backtest, checked_float
from .backtest_models import content_hash
from .backtest_reporting import build_backtest_result
from .domain import DataContext, Money, Ticker
from .portfolio import HeldPositionContext
from .prompts import render_prompt


def collect_shadow_snapshots(bundle, baseline=None, *, start=None, end=None, profile='baseline'):
    if baseline is not None:
        if build_backtest_result(baseline.run) != baseline or baseline.run.manifest['input_hash'] != content_hash(bundle):
            raise ShadowInputError('BASELINE_INPUT_MISMATCH')
        window=baseline.run.manifest['window']
        start=__import__('datetime').date.fromisoformat(window['requested_start'])
        end=__import__('datetime').date.fromisoformat(window['requested_end'])
        profile=baseline.run.manifest['profile']['name']
    snapshots=[]
    run=run_backtest(bundle,start,end,profile,decision_observer=snapshots.append)
    fresh=build_backtest_result(run)
    if baseline is not None:
        old=baseline.run.model_dump(mode='json'); new=run.model_dump(mode='json')
        for value in (old,new):
            value['manifest'].pop('code_identity',None); value['manifest'].pop('scenario_group',None)
        if old != new: raise ShadowInputError('BASELINE_TRADING_SEMANTICS_MISMATCH')
    return tuple(snapshots), baseline or fresh


class FrozenHistoricalNews(Frozen):
    ticker: str
    known_at: datetime
    source_hash: Hash
    text: Text


def load_historical_news(path):
    try: return tuple(FrozenHistoricalNews.model_validate(n) for n in read_shadow_json(path,NEWS_LIMIT))
    except (ValueError,TypeError): raise ShadowInputError('INVALID_HISTORICAL_NEWS') from None


def render_snapshot(snapshot, news=()):
    visible=tuple(n for n in news if n.ticker==snapshot.ticker and n.known_at<=snapshot.cutoff)
    held=None
    if snapshot.quantity and snapshot.price is not None:
        held=HeldPositionContext(checked_float(snapshot.average_price),snapshot.quantity,snapshot.orderable_quantity,checked_float(snapshot.price),checked_float(snapshot.price/snapshot.average_price-1),snapshot.open_sell_quantity)
    prompt=''
    if snapshot.eligible:
        prompt='Historical simulation; held quantities are simulated, not broker authority.\n'+render_prompt(DataContext(Ticker(snapshot.ticker),Money(checked_float(snapshot.price)),strict_json(snapshot.technicals_json),tuple(n.text for n in visible)),held_position=held)
    return ShadowSnapshot.model_validate({**snapshot.model_dump(),'news':tuple(n.text for n in visible),'news_source_hashes':tuple(n.source_hash for n in visible),'news_available':bool(visible),'rendered_prompt':prompt,'snapshot_id':''})


def _stratum(s):
    try: action=strict_trade_signal(s.fixture_raw).decision.value
    except ValueError: action='INVALID'
    return f'{s.session.year}-{(s.session.month-1)//3+1}/{action}/{"HELD" if s.held else "SCREENED"}/{"RISK" if s.baseline_risk_override else "NORMAL"}'


def select_shadow_sample(snapshots, limit=100, seed='shadow-v1'):
    groups={}
    for s in snapshots:
        if s.eligible: groups.setdefault(_stratum(s),[]).append(s)
    for group in groups.values(): group.sort(key=lambda s:hashlib.sha256((seed+s.unit_id).encode()).hexdigest())
    selected=[]
    while len(selected)<limit and any(groups.values()):
        for key in sorted(groups):
            if groups[key] and len(selected)<limit: selected.append(groups[key].pop(0))
    return tuple(sorted(selected,key=lambda s:(s.session,s.ticker)))


def shadow_code_identity():
    root=Path(__file__).parent; digest=hashlib.sha256()
    for path in sorted(root.glob('*.py')):
        digest.update(path.name.encode());digest.update(path.read_bytes())
    return digest.hexdigest()


def prepare_shadow_manifest(bundle, variants, pricing, *, baseline=None, limits=None, seed='shadow-v1', news=(), start=None, end=None, profile='baseline'):
    limits=limits or ShadowLimits()
    snapshots,baseline=collect_shadow_snapshots(bundle,baseline,start=start,end=end,profile=profile)
    snapshots=tuple(render_snapshot(s,news) for s in snapshots)
    selected=select_shadow_sample(snapshots,limits.sample_limit,seed)
    strata={}
    for s in selected: strata[_stratum(s)]=strata.get(_stratum(s),0)+1
    decisions=set(k.split('/')[1] for k in strata)
    coverage={'observed_units':len(snapshots),'eligible_units':sum(s.eligible for s in snapshots),'selected_units':len(selected),'excluded_units':sum(not s.eligible for s in snapshots),'exclusions':sorted({r for s in snapshots for r in s.exclusions}),'strata':strata,'missing_decision_strata':sorted({'BUY','HOLD','SELL'}-decisions),'missing_news_units':sum(not s.news_available for s in selected),'baseline_limitations':list(baseline.run.limitations),'limitations':['CURRENT_MODEL_HINDSIGHT_CONTAMINATION','AGREEMENT_IS_NOT_QUALITY','CANONICAL_SIMULATED_STATE_NOT_ALTERNATIVE_PORTFOLIO']}
    revision=subprocess.run(['git','rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip()
    return ShadowManifest(baseline_hash=shadow_content_hash(baseline),bundle_hash=content_hash(bundle),baseline_document_json=canonical_json(baseline),snapshots=selected,variants=tuple(variants),pricing=tuple(pricing),limits=limits,seed=seed,coverage_json=canonical_json(coverage),source_hashes=bundle.sources.source_hashes,code_revision=revision,code_content_hash=shadow_code_identity())
