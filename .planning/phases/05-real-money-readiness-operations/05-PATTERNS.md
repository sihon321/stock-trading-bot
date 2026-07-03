# Phase 5: Real-Money Readiness & Operations - Pattern Map

**Mapped:** 2026-07-02
**Files analyzed:** 7 (5 new, 2 modified)
**Analogs found:** 7 / 7

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `trading_bot/cli.py` (NEW) | CLI / orchestrator | request-response (batch loop) | `trading_bot/llm_provider.py` (`run_llm_cycle` + `build_llm_provider`) | role-match (orchestration + factory) |
| `trading_bot/kis_broker.py` (NEW) | adapter (Broker port impl) | request-response | `trading_bot/mock_broker.py` | exact (same `Broker` port) |
| `trading_bot/kis_order.py` (NEW) | adapter (direct-REST) | request-response (order/query) | `trading_bot/kis_quote.py` | exact (direct-REST + shared token) |
| `trading_bot/sqlite_audit.py` (NEW) | persistence / sink | file-I/O (batch write) | `trading_bot/execution.py` (`CycleAuditEvent` shape) | role-match (consumer of frozen domain type) |
| `trading_bot/notifier.py` (NEW) | adapter (Notifier port impl) | request-response (fire-and-forget POST) | `trading_bot/kis_quote.py` (httpx POST + tenacity + fail-soft) | role-match (fail-soft httpx) |
| `trading_bot/ports.py` (EDIT) | port (Protocol) | — | existing `Broker`/`DataSource`/`LLMProvider` Protocols in same file | exact |
| `trading_bot/config.py` (EDIT) | config | — | existing `Settings` fields + `KisCredentialGroup` | exact |

Test files (mirror `tests/test_kis_quote.py` + `tests/conftest.py`): `tests/test_kis_broker.py`, `tests/test_kis_order.py`, `tests/test_cli.py`, `tests/test_sqlite_audit.py`, `tests/test_notifier.py`, extend `tests/test_ports.py`.

---

## Pattern Assignments

### `trading_bot/ports.py` (EDIT — add `Notifier` Protocol)

**Analog:** the three existing Protocols in the same file.

Add alongside `Broker`/`LLMProvider`/`DataSource` (ports.py lines 10-38). Match the exact shape: `@runtime_checkable`, `class X(Protocol)`, synchronous semantic method, `...` body, docstring, and imports only from `trading_bot.domain`. Do NOT import any adapter/httpx/kis module (guarded by `tests/test_ports.py` lines 10-24 `FORBIDDEN_*` lists and the fresh-interpreter test lines 116-144).

```python
@runtime_checkable
class Notifier(Protocol):
    """Operator notification boundary (fail-soft; never raises)."""

    def send(self, summary: str) -> bool:
        """Deliver a run summary; return True on delivery, False on give-up."""
        ...
```

Extend `tests/test_ports.py`: add a `FakeNotifier` (mirror `FakeBroker` lines 27-36) and a `test_notifier_protocol_is_runtime_checkable_and_structural` (mirror lines 58-69). Note: research names the method `send`; RESEARCH.md Pattern 3 (lines 275-279) shows `send(self, summary: str) -> bool`.

---

### `trading_bot/kis_broker.py` (NEW — Broker adapter, EXEC-04)

**Analog:** `trading_bot/mock_broker.py` (interface/shape) + `trading_bot/kis_quote.py` (network/injection posture).

**Interface pattern** — satisfy `Broker` structurally, exactly like `MockBroker` (mock_broker.py lines 25-52): a plain class (NOT inheriting from `ports.Broker`), `get_position(ticker) -> Optional[Position]`, `place_order(order) -> str`. `test_ports.py` line 34 shows `place_order` returns a broker order-id string.

**Constructor injection** — mirror `KisQuoteAdapter.__init__` (kis_quote.py lines 85-109): keyword-only args, an injectable `client`/order-adapter, real object constructed lazily only when `None`. The order adapter (`kis_order`) MUST be built from the shared `KisTokenManager` — never a second token path (kis_auth.py module docstring lines 1-20; data_source.py lines 330-334 raises rather than opening a second token flow).

**place_order control flow (D-06/D-07)** — query-before-POST, POST never retried:

```python
def place_order(self, order: Order) -> str:
    client_ref = self._client_ref(order)          # local audit tag only; KIS ignores it
    existing = self._order.find_open_or_recent(order)   # QUERY broker truth (retryable GET)
    if existing is not None:
        return existing.odno                       # already placed -> never re-POST
    odno = self._order.place(order)                # single-shot POST, NOT wrapped in @retry
    fill = self._order.query_fill(odno)            # read tot_ccld_qty / rmn_qty
    self._reconcile(order, fill)                   # tracked position -> filled qty (D-07)
    return odno
```

**Anti-pattern to avoid:** never place a `@retry` above `self._order.place(...)` (RESEARCH.md Pitfall 1, lines 315-319; anti-patterns lines 282-283). Retry decorators wrap only the query legs.

---

### `trading_bot/kis_order.py` (NEW — direct-REST order/query adapter)

**Analog:** `trading_bot/kis_quote.py` (the closest existing direct-REST adapter). Copy its whole structure; add a POST path and query paths.

**Imports + token reuse** (kis_quote.py lines 19-34): `from trading_bot.kis_auth import KisAuthError, KisTokenManager`, tenacity imports, `from trading_bot.domain import Money`. The adapter takes a `token_manager` and calls `get_token()` / `app_key` / `app_secret` — it NEVER issues tokens (D-14).

**Header pattern** (kis_quote.py lines 152-159) — reuse verbatim, adding `hashkey` and deriving `tr_id` from mode:

```python
headers = {
    "content-type": "application/json",
    "authorization": f"Bearer {token}",
    "appkey": getattr(self._token_manager, "app_key", ""),
    "appsecret": getattr(self._token_manager, "app_secret", ""),
    "tr_id": self._tr_id,        # derive from Settings.active_kis.tr_id_profile — NEVER hard-code
    "custtype": "P",
}
```

**Response validation** (kis_quote.py lines 179-206) — copy the fail-safe validation: check `body` is a dict, `rt_cd == "0"`, `output` present, fields numeric/finite. Treat all KIS output as untrusted; on malformed → fail safe (RESEARCH.md Security V5, lines 577; Pitfall 2). Order fields: `ODNO`, `KRX_FWDG_ORD_ORGNO`, `ORD_TMD`; fill fields: `tot_ccld_qty`/`rmn_qty`/`ord_qty` (RESEARCH.md lines 412-435 — verify spellings on portal, A2).

**Retry split** — the query legs (`inquire-daily-ccld`, `inquire-balance`) use the bounded `@retry(...)` wrapper (kis_quote.py lines 136-145). The order-cash POST is single-shot: structure it so the retry decorator physically cannot wrap it.

**TR_IDs** (RESEARCH.md lines 408, 601): buy real `TTTC0802U` / mock `VTTC0802U`; sell real `TTTC0801U` / mock `VTTC0801U`; derive from `active_kis` — see Pitfall 4 (lines 333-337). Order body: `CANO/ACNT_PRDT_CD/PDNO/ORD_DVSN="00"/ORD_QTY/ORD_UNPR` (lines 392-400).

**Tick-size snap** (D-08) — RESEARCH.md `_TICK_BANDS` + `snap_to_tick` (lines 363-383). Snap `ORD_UNPR` to a valid band or KRX rejects (Pitfall 3).

---

### `trading_bot/sqlite_audit.py` (NEW — two-table writer, OPS-02)

**Analog:** consumes the frozen `CycleAuditEvent` (execution.py lines 59-75) and `ExecutionResult` (lines 78-93). Do NOT Pydantic-ify or change `CycleAuditEvent` (D-11; RESEARCH.md anti-pattern lines 285).

**Available fields to persist** (execution.py lines 67-75): `ticker`, `parsed_decision`, `parse_error`, `risk_override`, `override_reason`, `final_action`, `order_reason`, `dry_run`, `broker_order_id`. Add `confidence`/`current_price`/`filled_qty`/`correlation_id` from the surrounding cycle.

**Schema + connect** (RESEARCH.md Pattern 2, lines 246-268) — stdlib `sqlite3`, two tables `runs`→`decisions`, `PRAGMA journal_mode=WAL`, `executescript(SCHEMA)`, indexes on `run_id`/`ticker`. Commit per decision row (Pitfall 6, lines 345-349) so a crash preserves completed rows.

**Correlation ID (D-10):** store an ID matching the Phase 4 structlog `llm_signal_cycle` line (llm_provider.py `_log_cycle` lines 85-103). Raw prompt/response stay in structlog — never duplicated in SQLite.

**Config:** DB path from a new `Settings.audit_db_path` (default `./data/audit.db`, gitignored).

---

### `trading_bot/notifier.py` (NEW — Discord webhook, OPS-03)

**Analog:** `trading_bot/kis_quote.py` for the httpx + tenacity + fail-soft posture; `build_llm_provider` (llm_provider.py lines 288-318) for the factory that lazily constructs the real client.

**Fail-soft pattern (D-14):** wrap the webhook POST in bounded tenacity (mirror `_fetch_body` kis_quote.py lines 135-145 or `_call_provider_with_retry` llm_provider.py lines 106-129). On final failure, log and return `False` — NEVER raise, never block the cycle (mirrors the fail-soft Naver-news posture and `run_llm_cycle`'s fail-safe HOLD, llm_provider.py lines 334-357).

```python
def send(self, summary: str) -> bool:
    try:
        # bounded @retry on the httpx POST to the webhook URL; short timeout
        self._post(summary)
        return True
    except Exception:      # noqa: BLE001 — notification failure never crashes the cycle
        # log a non-secret category; webhook URL is a secret, never logged
        return False
```

**Consolidated summary (D-13):** one message per run (not per ticker) — Pitfall 7 (lines 351-355). Webhook URL is a `SecretStr` secret, redacted from logs/reprs (mirror `KisAuthConfig.__repr__` kis_auth.py lines 88-97).

**Factory:** `build_notifier(settings, *, client=None)` mirroring `build_llm_provider` (llm_provider.py lines 288-318) and `build_data_source` (data_source.py lines 302-355) — lazily construct `httpx.Client()` when `client is None`.

---

### `trading_bot/cli.py` (NEW — typer app, OPS-01/CFG-04)

**Analog:** `run_llm_cycle` (llm_provider.py lines 321-375) is the per-ticker cycle the CLI orchestrates; the `build_*` factories are the wiring pattern to compose.

**Surface + gate** (RESEARCH.md lines 437-455): `typer.Typer()`, commands `run`/`screen`/`status`. `run` options `--ticker`/`--execute`/`--live-confirm`. Load `Settings()` (fires the Phase 1 gate config.py lines 104-113), print `startup_banner(settings)` (config.py lines 166-180). `dry_run = not execute` (D-03). Real execute requires `--live-confirm` else `typer.Exit` (D-04):

```python
settings = Settings()
print(startup_banner(settings))
dry_run = not execute
if settings.trading_mode is TradingMode.REAL and execute and not live_confirm:
    raise typer.Exit("real execute requires --live-confirm")
```

**Universe loop (D-02/D-13):** iterate the screener universe (`MarketDataSource.screen_daily_candidates` data_source.py lines 225-238, or `screener.screen_candidates`); per-ticker: `build_context` → `run_llm_cycle` → `sqlite_audit.write` → accumulate. Wrap each ticker in try/except so one failure is captured and reported, never fatal — then send one consolidated `Notifier.send` summary at the end plus an immediate push on cycle-level error.

**Broker selection:** `MockBroker` when `TradingMode.MOCK`, `KISBroker` when `REAL` — chosen by `settings.trading_mode`, passed into `run_llm_cycle(..., broker=...)`.

---

### `trading_bot/config.py` (EDIT — new settings)

**Analog:** existing `Settings` fields (config.py lines 45-102) and the `KisCredentialGroup` `SecretStr` discipline (lines 26-33).

Add typed fields following the existing style: `audit_db_path: str = "./data/audit.db"`, `discord_webhook_url: Optional[SecretStr] = None`, and any real-order params (tick policy, order timeout). Add positive-value guards to `_require_positive_source_policy` (lines 115-135) if numeric. Keep secrets as `SecretStr`, redacted from `startup_banner` (lines 166-180). Do not surface the webhook URL in the banner.

---

## Shared Patterns

### Shared token manager (never a second auth path)
**Source:** `trading_bot/kis_auth.py` `KisTokenManager` (lines 148-192: `get_token()`, `app_key`, `app_secret`).
**Apply to:** `kis_order.py`, `kis_broker.py`.
`kis_order` consumes an injected `KisTokenManager`; the CLI/factory owns the single instance and passes it in (data_source.py lines 330-334 shows the "provide the shared manager, don't open a second flow" enforcement). Never call `/oauth2/tokenP` outside `kis_auth`.

### Bounded tenacity retry (query/notify legs only)
**Source:** `kis_quote.py` `_fetch_body` (lines 135-145) / `kis_auth.py` `_issue_token` (lines 216-238) / `llm_provider.py` `_call_provider_with_retry` (lines 106-129).
**Apply to:** `kis_order.py` query legs, `notifier.py`. Use `stop_after_attempt(kis_max_retries)`, `wait_fixed(kis_retry_backoff_seconds)`, `retry_if_exception_type(<internal marker>)`, `reraise=True`. NEVER on the order-cash POST.

### Fail-safe / fail-soft normalization
**Source:** `kis_quote.py` `_unavailable` + `_parse_price` (lines 59-63, 179-206); `run_llm_cycle` fail-safe HOLD (llm_provider.py lines 334-357).
**Apply to:** `kis_order` (malformed KIS response → safe), `kis_broker` (transport failure → caller fails safe, no blind retry), `notifier` (delivery failure → `False`, cycle continues), CLI (per-ticker error isolation).

### Secret redaction
**Source:** `KisAuthConfig.__repr__` (kis_auth.py lines 88-97); `startup_banner` allowlist (config.py lines 166-180); `_json_default` drops `api_key` (llm_provider.py lines 69-78).
**Apply to:** `notifier.py` (webhook URL), `kis_order.py`/`kis_broker.py` (token/appkey/appsecret), `sqlite_audit.py` (store only non-secret fields — never credentials in the DB or Discord message).

### Injectable HTTP client + factory
**Source:** `build_llm_provider` (llm_provider.py lines 288-318), `build_data_source` (data_source.py lines 302-355), `KisQuoteAdapter.__init__` (kis_quote.py lines 85-100 — `if client is None: import httpx`).
**Apply to:** `kis_order.py`, `notifier.py`, `kis_broker.py` factories — keyword-only injection, lazy real-client construction, so tests run fully offline.

### Offline test pattern (injected fakes + deterministic clocks)
**Source:** `tests/test_kis_quote.py` (`_FakeTokenManager` lines 42-58, `_FakeClient` lines 60-75, `_response` helper lines 77-84, `assert_no_secret_leaked` lines 36-39, source-scan acceptance test lines 305-311); `tests/conftest.py` (`make_settings` lines 32-53, fake clients).
**Apply to:** all Phase 5 test files. Inject a fake HTTP client capturing `calls`; queue responses; assert on captured headers/params/body; no live KIS/Discord. Use `tmp_path`/`:memory:` for `sqlite_audit` tests.

---

## No Analog Found

None — every Phase 5 file maps to a concrete existing analog. The genuinely new logic (order-cash POST body, query-before-POST reconciliation control flow, tick-size snapping, market-hours guard) has no direct code analog but is fully specified in RESEARCH.md Code Examples (lines 357-435) and layers onto the `kis_quote.py` adapter skeleton.

## Metadata

**Analog search scope:** `trading_bot/`, `tests/`
**Files scanned:** ports.py, mock_broker.py, kis_quote.py, kis_auth.py, execution.py, config.py, data_source.py, llm_provider.py, domain.py, tests/test_kis_quote.py, tests/conftest.py, tests/test_ports.py
**Pattern extraction date:** 2026-07-02
