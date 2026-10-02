"""Fresh-interpreter capability tripwire. Run directly; never import pytest conftest.

CLI: python tests/capability_probe.py --module MODULE --action import
     --registry '{"sources": [...], "writable_roots": [...], "paths": {...}}'
An action other than import/selfcheck is a named target callable accepting the registry.
This detects accidental capabilities; it is not an OS sandbox for malicious Python.
"""

import argparse
import builtins
import importlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import sys
from urllib.parse import unquote, urlsplit


class CapabilityViolation(RuntimeError):
    pass


FORBIDDEN = ("trading_bot.cli", "trading_bot.config", "trading_bot.kis_", "trading_bot.llm_provider",
    "trading_bot.execution", "trading_bot.market_cycle", "trading_bot.data_source",
    "trading_bot.pykrx_adapter", "trading_bot.naver_news", "trading_bot.portfolio_store",
    "trading_bot.portfolio", "trading_bot.mutation_lease", "trading_bot.soak_controller",
    "trading_bot.soak_store", "trading_bot.soak_reconcile", "trading_bot.soak_config",
    "trading_bot.sqlite_audit", "trading_bot.backtest_engine", "trading_bot.shadow_runner",
    "trading_bot.shadow_providers", "trading_bot.shadow_inputs", "trading_bot.calibration",
    "trading_bot.replay", "trading_bot.intraday", "trading_bot.mock_broker",
    "anthropic", "openai", "pykis", "pykrx", "conftest", "tests.conftest")


def forbidden(name):
    return any(name == p or name.startswith(p + ".") or (p.endswith("_") and name.startswith(p))
               for p in FORBIDDEN)


def install_tripwires(registry):
    sources = {Path(p).resolve() for p in registry["sources"]}
    roots = tuple(Path(p).resolve() for p in registry.get("writable_roots", []))
    for root in roots:
        if any(root == p or root in p.parents or p in root.parents for p in sources):
            raise CapabilityViolation("FORBIDDEN_WRITE")
    source_inodes = {(p.stat().st_dev, p.stat().st_ino) for p in sources}
    allowed = tuple(registry.get("allow_loopback", ()))
    if allowed and (len(allowed) != 2 or allowed[0] != "127.0.0.1" or not isinstance(allowed[1], int)):
        raise CapabilityViolation("FORBIDDEN_NETWORK")
    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        candidates = [name, *(f"{name}.{v}" for v in fromlist or () if v != "*")]
        if any(forbidden(n) for n in candidates):
            raise CapabilityViolation("FORBIDDEN_IMPORT")
        return original_import(name, globals, locals, fromlist, level)

    class ImportGuard:
        def find_spec(self, fullname, path=None, target=None):
            if forbidden(fullname):
                raise CapabilityViolation("FORBIDDEN_IMPORT")
            return None

    builtins.__import__ = guarded_import
    sys.meta_path.insert(0, ImportGuard())
    sys.dont_write_bytecode = True

    def audit(event, args):
        if event == "sqlite3.connect":
            text = os.fspath(args[0])
            if text != ":memory:":
                uri = text.startswith("file:")
                path = Path(unquote(urlsplit(text).path) if uri else text).resolve()
                alias = path.exists() and (path.stat().st_dev, path.stat().st_ino) in source_inodes
                if (path in sources or alias) and (not uri or "mode=ro" not in urlsplit(text).query.split("&")):
                    raise CapabilityViolation("FORBIDDEN_SOURCE_SQL")
                if path not in sources and not alias and not any(path.is_relative_to(r) for r in roots):
                    raise CapabilityViolation("FORBIDDEN_WRITE")
        if event in {"socket.connect", "socket.bind"}:
            if not allowed or tuple(args[1]) != allowed:
                raise CapabilityViolation("FORBIDDEN_NETWORK")
        if event in {"socket.getaddrinfo", "socket.gethostbyname"}:
            if not allowed or args[0] != allowed[0]:
                raise CapabilityViolation("FORBIDDEN_NETWORK")
        if event == "socket.__new__" and not allowed:
            raise CapabilityViolation("FORBIDDEN_NETWORK")
        if event in {"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn"}:
            raise CapabilityViolation("FORBIDDEN_PROCESS")
        if event == "open" and not isinstance(args[0], int):
            path = Path(args[0]).resolve()
            mode, flags = args[1], args[2]
            writing = (bool(mode and any(c in mode for c in "wax+"))
                       or bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)))
            if path.name == ".env" or (path.suffix in {".db", ".sqlite", ".sqlite3"} and path not in sources
                                       and not any(path.is_relative_to(r) for r in roots)):
                raise CapabilityViolation("FORBIDDEN_READ")
            alias = path.exists() and (path.stat().st_dev, path.stat().st_ino) in source_inodes
            if writing and (alias or not any(path.is_relative_to(r) for r in roots)):
                raise CapabilityViolation("FORBIDDEN_WRITE")
        if event in {"os.remove", "os.rename", "os.mkdir", "os.rmdir", "os.link", "os.symlink", "os.truncate"}:
            candidates = args[:2] if event in {"os.rename", "os.link", "os.symlink"} else args[:1]
            if any(not any(Path(p).resolve().is_relative_to(r) for r in roots) for p in candidates):
                raise CapabilityViolation("FORBIDDEN_WRITE")

    sys.addaudithook(audit)
    original_connect = sqlite3.connect

    def guarded_connect(database, *args, **kwargs):
        text = os.fspath(database)
        uri = text.startswith("file:")
        path = Path(unquote(urlsplit(text).path) if uri else text).resolve()
        is_source = path in sources or (path.exists() and (path.stat().st_dev, path.stat().st_ino) in source_inodes)
        if not is_source and text != ":memory:" and not any(path.is_relative_to(r) for r in roots):
            raise CapabilityViolation("FORBIDDEN_WRITE")
        if is_source:
            conn = original_connect(f"{path.as_uri()}?mode=ro", uri=True)
            conn.execute("PRAGMA query_only=ON")

            def authorizer(action, one, two, db, trigger):
                permitted = action in {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION,
                                       sqlite3.SQLITE_TRANSACTION, sqlite3.SQLITE_RECURSIVE}
                permitted |= action == sqlite3.SQLITE_PRAGMA and (
                    one in {"table_info", "table_xinfo", "index_list", "foreign_key_list"}
                    or (one in {"user_version", "query_only"} and two is None)
                    or (one == "query_only" and two in {"ON", "1"}))
                return sqlite3.SQLITE_OK if permitted else sqlite3.SQLITE_DENY

            conn.set_authorizer(authorizer)
            return conn
        return original_connect(database, *args, **kwargs)

    sqlite3.connect = guarded_connect
    sqlite3.dbapi2.connect = guarded_connect
    return registry


def selfcheck(action, registry):
    source = registry["paths"]["audit"]
    if action == "selfcheck-constructor":
        from trading_bot.config import Settings
        Settings()
    elif action in {"selfcheck-socket", "selfcheck-remote"}:
        socket.socket().connect(("203.0.113.1", 443))
    elif action == "selfcheck-loopback":
        with socket.socket() as sock:
            sock.bind(tuple(registry["allow_loopback"]))
    elif action in {"selfcheck-sql", "selfcheck-attach", "selfcheck-schema"}:
        with sqlite3.connect(source) as conn:
            statements = {"selfcheck-sql": "DELETE FROM runs", "selfcheck-schema": "CREATE TABLE forbidden(x)",
                          "selfcheck-attach": "ATTACH ':memory:' AS forbidden"}
            conn.execute(statements[action])
    elif action == "selfcheck-write":
        Path(source).write_bytes(b"forbidden")
    elif action == "selfcheck-env":
        Path(".env").read_bytes()
    elif action == "selfcheck-read":
        with sqlite3.connect(source) as conn:
            return {"count": conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]}
    else:
        raise ValueError("unknown selfcheck")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", required=True)
    parser.add_argument("--action", default="import")
    parser.add_argument("--registry", required=True)
    args = parser.parse_args()
    registry = json.loads(args.registry)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    try:
        install_tripwires(registry)
        module = importlib.import_module(args.module)
        if args.action.startswith("selfcheck-"):
            result = selfcheck(args.action, registry)
        elif args.action == "import":
            result = None
        else:
            result = getattr(module, args.action)(registry)
        print(json.dumps({"ok": True, "result": result, "shared_conftest": "conftest" in sys.modules}))
        return 0
    except CapabilityViolation as error:
        print(json.dumps({"ok": False, "code": str(error)}))
        return 23
    except sqlite3.DatabaseError as error:
        if "not authorized" in str(error):
            print(json.dumps({"ok": False, "code": "FORBIDDEN_SOURCE_SQL"}))
            return 23
        raise


if __name__ == "__main__":
    raise SystemExit(main())
