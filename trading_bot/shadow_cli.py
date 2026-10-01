"""Offline preparation and explicit paid shadow entry points."""
from __future__ import annotations
from pathlib import Path
from decimal import Decimal
import sqlite3
import typer
from .shadow_models import *
from .backtest_inputs import load_backtest_bundle
from .backtest_models import BacktestInputError
from .backtest_reporting import load_backtest_result, _write_evidence_bytes
from .shadow_inputs import prepare_shadow_manifest, load_historical_news
from .shadow_runner import run_shadow, resume_shadow, request_shadow_retry
from .shadow_reporting import load_shadow_result, build_shadow_result, write_shadow_result, render_shadow_report

shadow_app=typer.Typer(no_args_is_help=True,help='비실행 과거 LLM 비교: prepare는 오프라인, run/resume/retry는 명시적 유료 호출')


def _diagnostic(exc):
    code=str(exc) if isinstance(exc,(ShadowInputError,BacktestInputError)) else 'INVALID_SHADOW_COMMAND'
    typer.echo(f'Shadow 실패: {code[:100]}',err=True)
    raise typer.Exit(2) from None


def _destination(path,extension):
    from .report_cli import _validated_output_parent
    if path.suffix not in extension or any(part in {'.planning','.codex','.agents','trading_bot'} for part in path.parts):raise ShadowInputError('UNSAFE_SHADOW_OUTPUT')
    _validated_output_parent(path)
    return path


@shadow_app.command('prepare')
def prepare_command(
    bundle:Path=typer.Argument(...,help='동결된 백테스트 묶음 JSON'),
    variants:Path=typer.Option(...,'--variants',help='명시적 모델·프롬프트 변형 배열 JSON'),
    pricing:Path=typer.Option(...,'--pricing',help='변형 순서와 일치하는 검토된 요금표 배열 JSON'),
    baseline:Path|None=typer.Option(None,'--baseline'),
    parent_result:Path|None=typer.Option(None,'--parent-result'),
    news:Path|None=typer.Option(None,'--news'),
    seed:str=typer.Option('shadow-v1','--seed'),
    sample_limit:int=typer.Option(100,'--sample-limit'),
    max_attempts:int=typer.Option(100,'--max-attempts'),
    max_total_tokens:int=typer.Option(200000,'--max-total-tokens'),
    max_cost_usd:str=typer.Option('5','--max-cost-usd'),
    concurrency:int=typer.Option(1,'--concurrency'),
    repetitions:int=typer.Option(1,'--repetitions'),
    variant_limit:int=typer.Option(2,'--variant-limit'),
    start:str|None=typer.Option(None,'--start'),
    end:str|None=typer.Option(None,'--end'),
    output:Path|None=typer.Option(None,'--output'),
):
    try:
        from .report_cli import parse_kst_date
        limits=ShadowLimits(sample_limit=sample_limit,max_attempts=max_attempts,max_total_tokens=max_total_tokens,max_cost_usd=Decimal(max_cost_usd),concurrency=concurrency,repetitions=repetitions,variant_limit=variant_limit)
        manifest=prepare_shadow_manifest(load_backtest_bundle(bundle),[ShadowVariant.model_validate(v) for v in read_shadow_json(variants)],[ShadowPricing.model_validate(p) for p in read_shadow_json(pricing)],baseline=load_backtest_result(baseline) if baseline else None,news=load_historical_news(news) if news else (),limits=limits,seed=seed,parent_result=load_shadow_result(parent_result) if parent_result else None,start=parse_kst_date(start) if start else None,end=parse_kst_date(end) if end else None)
        destination=_destination(output or Path('data/shadow')/(manifest.spec_id+'.manifest.json'),{'.json'})
        payload=(canonical_json(manifest)+'\n').encode('utf-8')
        if len(payload)>DOCUMENT_LIMIT:raise ShadowInputError('MANIFEST_TOO_LARGE')
        _write_evidence_bytes(payload,destination)
        typer.echo(f'명세: {manifest.spec_id}\n표본: {len(manifest.snapshots)}\n저장 위치: {destination}\n준비는 오프라인입니다. 호출은 run을 명시적으로 실행할 때 시작됩니다.')
    except (ValueError,OSError,TypeError,KeyError) as exc:_diagnostic(exc)


def _paid_command(mode,manifest_path,journal,output,attempt=None):
    try:
        manifest=load_shadow_manifest(manifest_path)
        journal=_destination(journal or Path('data/shadow')/(manifest.spec_id+'.sqlite'),{'.sqlite','.db'})
        if journal.resolve()==manifest_path.resolve():raise ShadowInputError('SHADOW_PATH_COLLISION')
        if output is not None:
            _destination(output,{'.json'})
            if output.exists():raise ShadowInputError('OUTPUT_ALREADY_EXISTS_USE_NEW_PATH')
            if output.resolve() in (journal.resolve(),manifest_path.resolve()):raise ShadowInputError('SHADOW_PATH_COLLISION')
        if mode=='run':execution=run_shadow(manifest,journal)
        elif mode=='resume':execution=resume_shadow(manifest,journal)
        else:execution=request_shadow_retry(manifest,journal,attempt)
        result=build_shadow_result(execution)
        destination=_destination(output or Path('data/shadow')/(result.result_id+'.result.json'),{'.json'})
        write_shadow_result(result,destination)
        typer.echo(render_shadow_report(result),nl=False);typer.echo(f'저장 위치: {destination}')
        if result.status!='COMPLETE':raise typer.Exit(1)
    except typer.Exit:raise
    except (ValueError,OSError,TypeError,KeyError,sqlite3.Error) as exc:_diagnostic(exc)


@shadow_app.command('run')
def run_command(manifest:Path=typer.Argument(...),journal:Path|None=typer.Option(None,'--journal'),output:Path|None=typer.Option(None,'--output')):
    _paid_command('run',manifest,journal,output)


@shadow_app.command('resume')
def resume_command(manifest:Path=typer.Argument(...),journal:Path|None=typer.Option(None,'--journal'),output:Path|None=typer.Option(None,'--output')):
    _paid_command('resume',manifest,journal,output)


@shadow_app.command('retry')
def retry_command(manifest:Path=typer.Argument(...),attempt:str=typer.Option(...,'--attempt'),journal:Path|None=typer.Option(None,'--journal'),output:Path|None=typer.Option(None,'--output')):
    _paid_command('retry',manifest,journal,output,attempt)
