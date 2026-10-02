"""Offline canonical snapshots. Historical inputs never fetch current data."""
from __future__ import annotations
import hashlib
import subprocess
import html
from functools import lru_cache
from datetime import date, datetime
from pathlib import Path
from .shadow_models import *
from .backtest_engine import run_backtest, checked_float
from .backtest_models import content_hash
from .shadow_evidence import FrozenHistoricalNews, select_shadow_sample, _stratum, _coverage
from .backtest_reporting import build_backtest_result
from .domain import DataContext, Money, Ticker
from .portfolio import HeldPositionContext
from .prompts import render_prompt


def collect_shadow_snapshots(bundle, baseline=None, *, start=None, end=None, profile='baseline'):
    if baseline is not None:
        if build_backtest_result(baseline.run) != baseline or baseline.run.manifest['input_hash'] != content_hash(bundle):
            raise ShadowInputError('BASELINE_INPUT_MISMATCH')
        window=baseline.run.manifest['window']
        if start is not None and start.isoformat()!=window['requested_start'] or end is not None and end.isoformat()!=window['requested_end']: raise ShadowInputError('BASELINE_WINDOW_MISMATCH')
        start=date.fromisoformat(window['requested_start'])
        end=date.fromisoformat(window['requested_end'])
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
        prompt='Historical simulation; held quantities are simulated, not broker authority.\n'+render_prompt(DataContext(Ticker(snapshot.ticker),Money(checked_float(snapshot.price)),strict_json(snapshot.technicals_json),tuple(html.escape(n.text,quote=False) for n in visible)),held_position=held)
    return ShadowSnapshot.model_validate({**snapshot.model_dump(),'news':tuple(n.text for n in visible),'news_source_hashes':tuple(n.source_hash for n in visible),'news_available':bool(visible),'rendered_prompt':prompt,'snapshot_id':''})


def shadow_code_identity():
    root=Path(__file__).parent; digest=hashlib.sha256()
    for path in sorted(root.glob('*.py')):
        digest.update(path.name.encode());digest.update(path.read_bytes())
    return digest.hexdigest()


def prepare_shadow_manifest(bundle, variants, pricing, *, baseline=None, limits=None, seed='shadow-v1', news=(), start=None, end=None, profile='baseline', parent_result=None):
    limits=limits or ShadowLimits()
    snapshots,baseline=collect_shadow_snapshots(bundle,baseline,start=start,end=end,profile=profile)
    snapshots=tuple(render_snapshot(s,news) for s in snapshots)
    selected=select_shadow_sample(snapshots,limits.sample_limit,seed)
    coverage=_coverage(snapshots,selected,baseline)
    revision=subprocess.run(['git','-C',str(Path(__file__).resolve().parent.parent),'rev-parse','HEAD'],capture_output=True,text=True,check=True,timeout=5).stdout.strip()
    return ShadowManifest(parent_spec_id=parent_result.manifest.spec_id if parent_result else None,parent_run_id=parent_result.run_id if parent_result else None,baseline_hash=shadow_content_hash(baseline),bundle_hash=content_hash(bundle),bundle_document_json=canonical_json(bundle),news_document_json=canonical_json([n.model_dump(mode='json') for n in news]),baseline_document_json=canonical_json(baseline),snapshots=selected,variants=tuple(variants),pricing=tuple(pricing),limits=limits,seed=seed,coverage_json=canonical_json(coverage),source_hashes=bundle.sources.source_hashes,code_revision=revision,code_content_hash=shadow_code_identity())


@lru_cache(maxsize=8)
def _validate_frozen_document(document, current_code_hash):
    """Replay frozen sources to reject self-consistent fabricated snapshot states."""
    from .backtest_models import BacktestBundle
    from .backtest_reporting import BacktestResult
    m=ShadowManifest.model_validate(strict_json(document));bundle=BacktestBundle.model_validate(strict_json(m.bundle_document_json))
    baseline=BacktestResult.model_validate(strict_json(m.baseline_document_json))
    snapshots,baseline=collect_shadow_snapshots(bundle,baseline)
    news=tuple(FrozenHistoricalNews.model_validate(n) for n in strict_json(m.news_document_json))
    snapshots=tuple(render_snapshot(s,news) for s in snapshots)
    expected=select_shadow_sample(snapshots,m.limits.sample_limit,m.seed)
    if expected!=m.snapshots or canonical_json(_coverage(snapshots,expected,baseline))!=m.coverage_json:raise ShadowInputError('FROZEN_INPUT_REPLAY_MISMATCH')
    return snapshots


def validate_shadow_preparation(manifest,*,return_inventory=False):
    try:
        inventory=_validate_frozen_document(canonical_json(manifest),shadow_code_identity())
        return inventory if return_inventory else True
    except ShadowInputError:raise
    except (ValueError,TypeError,KeyError):raise ShadowInputError('INVALID_FROZEN_SOURCE_EVIDENCE') from None
