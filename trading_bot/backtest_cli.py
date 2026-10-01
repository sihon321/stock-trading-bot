"""Credential-free backtest controllers; no live runtime is constructed."""
from pathlib import Path

import typer

from .backtest_engine import run_backtest
from .backtest_inputs import load_backtest_bundle
from .backtest_models import BacktestInputError
from .backtest_reporting import build_backtest_result, render_backtest_report, write_backtest_result

backtest_app = typer.Typer(no_args_is_help=True,help='오프라인 포트폴리오 백테스트')


@backtest_app.command('run')
def run_command(
    bundle: Path = typer.Argument(...,help='동결된 JSON 데이터 묶음'),
    start: str | None = typer.Option(None,'--start',help='YYYY-MM-DD'),
    end: str | None = typer.Option(None,'--end',help='YYYY-MM-DD'),
    profile: str = typer.Option('baseline','--profile',help='baseline 또는 stress'),
    output: Path | None = typer.Option(None,'--output',help='결과 JSON 파일; 기본 data/backtests/ID.json'),
):
    from .report_cli import parse_kst_date
    try:
        start_date=parse_kst_date(start) if start else None
        end_date=parse_kst_date(end) if end else None
        result=build_backtest_result(run_backtest(load_backtest_bundle(bundle),start_date,end_date,profile))
        destination=output or Path('data/backtests')/(result.result_id+'.json')
        path=write_backtest_result(result,destination)
        typer.echo(render_backtest_report(result),nl=False)
        typer.echo(f'저장 위치: {path}')
    except (BacktestInputError,ValueError,OSError) as exc:
        code=str(exc) if isinstance(exc,BacktestInputError) else 'INVALID_COMMAND_INPUT'
        typer.echo(f'백테스트 실패: {code[:100]}',err=True)
        raise typer.Exit(2) from None
