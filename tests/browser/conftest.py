"""Lazy app harness: callers must provide explicit saved services/settings."""

from contextlib import contextmanager
import importlib
import errno
from threading import Event, Thread
from urllib.parse import urlsplit

import pytest


@contextmanager
def serve_saved_app(app):
    from waitress import create_server

    server = create_server(app, host="127.0.0.1", port=0, threads=2, asyncore_loop_timeout=0.1)
    stopping = Event()
    failures = []

    def run():
        try:
            server.run()
        except OSError as error:
            # select may observe the listener close during deliberate teardown.
            if not stopping.is_set() or error.errno != errno.EBADF:
                failures.append(error)
        except Exception as error:
            failures.append(error)

    thread = Thread(target=run, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.effective_port}"
    finally:
        stopping.set()
        server.close()
        server.task_dispatcher.shutdown()
        thread.join(timeout=3)
        if thread.is_alive():
            raise RuntimeError("saved browser test server did not stop")
        if failures:
            raise RuntimeError("saved browser test server failed") from failures[0]


@pytest.fixture
def operator_sources(tmp_path):
    from operator_fixtures import make_operator_sources
    return make_operator_sources(tmp_path)


@pytest.fixture
def operator_app_kwargs():
    pytest.fail("browser tests must override operator_app_kwargs with temporary settings and injected saved services")


@pytest.fixture
def operator_app(operator_app_kwargs):
    required = {"settings", "evidence_service", "report_service", "alert_store", "clock"}
    if not required <= operator_app_kwargs.keys() or any(operator_app_kwargs[k] is None for k in required):
        pytest.fail("explicit saved services/settings/clock are required; live fallback is forbidden")
    create_app = importlib.import_module("trading_bot.web_app").create_app
    return create_app(**operator_app_kwargs)


@pytest.fixture
def operator_server(operator_app):
    with serve_saved_app(operator_app) as origin:
        yield origin


@pytest.fixture
def operator_page(browser, operator_server):
    # Browser binary failures propagate from the real plugin; never skip requested tests.
    with browser.new_context(service_workers="block", accept_downloads=True) as context:
        origin = urlsplit(operator_server)
        violations = []

        def bounded_route(route):
            if urlsplit(route.request.url)[:2] == origin[:2]:
                route.continue_()
            else:
                violations.append(route.request.url)
                route.abort()

        context.route("**/*", bounded_route)
        page = context.new_page()
        page.set_default_timeout(5000)
        yield page
        assert not violations, "browser attempted a non-fixture origin"
