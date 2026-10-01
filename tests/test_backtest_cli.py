import json
from pathlib import Path
from typer.testing import CliRunner
from trading_bot.cli import app
from trading_bot.backtest_reporting import load_backtest_result
from test_backtest_inputs import FIXTURE


def test_offline_run_and_saved_report_without_credentials(monkeypatch,tmp_path):
    import trading_bot.cli as cli
    import httpx
    import sqlite3
    def forbidden(*a,**k):raise AssertionError('offline capability violation')
    monkeypatch.setattr(cli,'Settings',forbidden)
    monkeypatch.setattr(httpx.Client,'request',forbidden)
    monkeypatch.setattr(sqlite3,'connect',forbidden)
    for k in ['OPENAI_API_KEY','ANTHROPIC_API_KEY','KIS_MOCK__APP_KEY','KIS_MOCK__APP_SECRET']:monkeypatch.delenv(k,raising=False)
    runner=CliRunner();f=tmp_path/'result.json';report=tmp_path/'report.txt'
    command=['backtest','run',str(FIXTURE),'--start','2023-01-09','--output',str(f)]
    result=runner.invoke(app,command)
    assert result.exit_code==0,result.output
    assert load_backtest_result(f).result_id in result.output
    assert '不' not in result.output
    read=runner.invoke(app,['report','backtest',str(f),'--output',str(report)])
    assert read.exit_code==0,read.output
    assert read.output==report.read_text()
    assert runner.invoke(app,command).exit_code==0


def test_bad_dates_profiles_and_sanitized_input(tmp_path):
    runner=CliRunner();f=tmp_path/'result.json'
    for args in [['--start','bad'],['--profile','unsafe'],['--start','2024-01-01','--end','2023-01-01']]:
        out=runner.invoke(app,['backtest','run',str(FIXTURE),'--output',str(f),*args])
        assert out.exit_code!=0 and not f.exists()
    bad=tmp_path/'bad.json';bad.write_text('{"private":"SECRET_PAYLOAD"}')
    out=runner.invoke(app,['backtest','run',str(bad)])
    assert out.exit_code!=0 and 'SECRET_PAYLOAD' not in out.output


def test_output_conflict_preserves_existing_file(tmp_path):
    f=tmp_path/'result.json';f.write_text('preserve')
    out=CliRunner().invoke(app,['backtest','run',str(FIXTURE),'--start','2023-01-09','--output',str(f)])
    assert out.exit_code!=0 and f.read_text()=='preserve'
