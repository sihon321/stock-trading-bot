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
