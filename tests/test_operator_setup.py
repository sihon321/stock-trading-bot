"""Packaging prerequisites; runtime entry points are tested after 14-12 creates them."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib
from importlib.metadata import version

WEB = {"Flask": "3.1.3", "Flask-WTF": "1.3.0", "waitress": "3.0.2",
       "Werkzeug": "3.1.9", "Jinja2": "3.1.6"}
BROWSER = {"playwright": "1.63.0", "pytest-playwright": "0.9.0"}


def test_exact_reviewed_extras_and_independent_scripts():
    data = tomllib.loads(Path("pyproject.toml").read_text())
    extras = data["project"]["optional-dependencies"]
    assert set(extras["web"]) == {f"{k}=={v}" for k, v in WEB.items()}
    assert set(extras["browser"]) == {f"{k}=={v}" for k, v in BROWSER.items()}
    assert data["project"]["scripts"] == {
        "bot": "trading_bot.cli:app", "bot-web": "trading_bot.web_cli:app",
        "bot-alerts": "trading_bot.alert_cli:app",
        "bot-service": "trading_bot.service_cli:app",
    }
    patterns = data["tool"]["setuptools"]["package-data"]["trading_bot"]
    assert "templates/**/*.html" in patterns
    assert "static/**/*" in patterns
    assert any(m.startswith("browser:") for m in data["tool"]["pytest"]["ini_options"]["markers"])


def test_framework_smoke_in_fresh_interpreter():
    for package, expected in (WEB | BROWSER).items():
        assert version(package) == expected, "install the reviewed .[web,browser] prerequisites"
    result = subprocess.run([sys.executable, "-c", (
        "import flask,flask_wtf,waitress,werkzeug,jinja2,playwright.sync_api,sys,json; "
        "print(json.dumps({'trading_cli': 'trading_bot.cli' in sys.modules}))"
    )], capture_output=True, text=True, check=True, timeout=15, env=os.environ.copy())
    assert json.loads(result.stdout) == {"trading_cli": False}


def test_chromium_launch_is_real_and_missing_binary_is_explicit(tmp_path):
    # The browser plugin keeps its own event loop alive for the pytest session.
    # A fresh process proves provisioning without nesting a second sync driver.
    result = subprocess.run([sys.executable, "-c", '''
import json
from playwright.sync_api import sync_playwright
with sync_playwright() as playwright:
    with playwright.chromium.launch() as browser:
        page = browser.new_page()
        page.set_content("<title>operator infrastructure</title>")
        print(json.dumps({"title": page.title(), "version": browser.version}))
'''], capture_output=True, text=True, check=True, timeout=15,
        env=os.environ.copy())
    launched = json.loads(result.stdout)
    assert launched["title"] == "operator infrastructure"
    assert launched["version"]
    env = {**os.environ, "PLAYWRIGHT_BROWSERS_PATH": str(tmp_path / "absent")}
    result = subprocess.run([sys.executable, "-c", (
        "from playwright.sync_api import sync_playwright; "
        "p=sync_playwright().start(); p.chromium.launch()"
    )], env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode != 0
    assert "playwright install" in result.stderr
