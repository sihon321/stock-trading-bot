"""Independent, append-only SQLite ledger for KIS mock soak campaigns."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .audit_models import sanitize_detail
from .soak_models import (
    AmbiguityVerdict,
    CampaignState,
    DayCreditState,
    DrillVerdict,
    FreezeState,
    PageCompleteness,
    ReconciliationStage,
    ReconciliationVerdict,
    SoakEvidenceClass,
)

SOAK_SCHEMA_VERSION = 1
PathLike = str | Path
_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")
_RUN_KINDS = {"RUN", "SCREEN", "DRILL", "DRY_RUN", "PROOF_ORDER"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _code(value: str, name: str) -> str:
    if not isinstance(value, str) or _CODE.fullmatch(value) is None:
        raise ValueError(f"{name} must be a bounded stable code")
    return value


def _detail(value: Mapping[str, Any] | None) -> str:
    return json.dumps(sanitize_detail(value), sort_keys=True, separators=(",", ":"))


def fingerprint_accepted_profile(profile: Mapping[str, Any]) -> str:
    """Return a stable fingerprint without retaining the authenticated payload."""

    canonical = json.dumps(profile, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


_TABLES: tuple[str, ...] = (
    "soak_identity_receipts", "soak_days", "soak_events", "soak_snapshot_orders",
    "soak_snapshot_fills", "soak_snapshot_holdings", "soak_snapshot_accounts",
    "soak_comparisons", "soak_ambiguity_observations", "soak_ticker_freezes",
    "soak_drill_links",
)


def migrate_soak_store(
    conn: sqlite3.Connection, *, fail_after_step: str | None = None
) -> None:
    """Create the soak-only schema in one rollback-safe transaction."""

    version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if version > SOAK_SCHEMA_VERSION:
        raise RuntimeError(f"unsupported soak schema version: {version}")
    if version == SOAK_SCHEMA_VERSION:
        return
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """CREATE TABLE soak_campaigns (
                campaign_id TEXT PRIMARY KEY,
                state TEXT NOT NULL CHECK(state IN ('ACTIVE','COMPLETED','FAILED')),
                target_eligible_days INTEGER NOT NULL CHECK(target_eligible_days > 0),
                availability_failure_budget INTEGER NOT NULL CHECK(availability_failure_budget > 0),
                availability_failures_used INTEGER NOT NULL DEFAULT 0 CHECK(availability_failures_used >= 0),
                safety_failure_code TEXT,
                accepted_profile_fingerprint TEXT NOT NULL,
                accepted_profile_version TEXT NOT NULL,
                field_contract_version TEXT NOT NULL,
                ambiguity_policy_version TEXT NOT NULL,
                ambiguity_window_seconds INTEGER NOT NULL CHECK(ambiguity_window_seconds > 0),
                ambiguity_poll_cadence_seconds INTEGER NOT NULL CHECK(ambiguity_poll_cadence_seconds > 0),
                ambiguity_max_observations INTEGER NOT NULL CHECK(ambiguity_max_observations > 0),
                created_at TEXT NOT NULL,
                CHECK(ambiguity_poll_cadence_seconds <= ambiguity_window_seconds),
                CHECK(state != 'FAILED' OR safety_failure_code IS NOT NULL)
            )"""
        )
        conn.execute(
            """CREATE TRIGGER soak_campaign_policy_immutable
            BEFORE UPDATE ON soak_campaigns
            WHEN OLD.target_eligible_days != NEW.target_eligible_days
              OR OLD.availability_failure_budget != NEW.availability_failure_budget
              OR OLD.accepted_profile_fingerprint != NEW.accepted_profile_fingerprint
              OR OLD.accepted_profile_version != NEW.accepted_profile_version
              OR OLD.field_contract_version != NEW.field_contract_version
              OR OLD.ambiguity_policy_version != NEW.ambiguity_policy_version
              OR OLD.ambiguity_window_seconds != NEW.ambiguity_window_seconds
              OR OLD.ambiguity_poll_cadence_seconds != NEW.ambiguity_poll_cadence_seconds
              OR OLD.ambiguity_max_observations != NEW.ambiguity_max_observations
            BEGIN SELECT RAISE(ABORT, 'immutable campaign policy'); END"""
        )
        conn.execute(
            """CREATE TRIGGER soak_campaign_failed_irreversible
            BEFORE UPDATE OF state ON soak_campaigns
            WHEN OLD.state = 'FAILED' AND NEW.state != 'FAILED'
            BEGIN SELECT RAISE(ABORT, 'failed campaign is terminal'); END"""
        )
        conn.execute(
            """CREATE TABLE soak_identity_receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                receipt_id TEXT NOT NULL UNIQUE,
                campaign_id TEXT NOT NULL REFERENCES soak_campaigns(campaign_id),
                target TEXT NOT NULL CHECK(target='mock'), domain_class TEXT NOT NULL,
                account_suffix TEXT NOT NULL, profile_version TEXT NOT NULL,
                policy_version TEXT NOT NULL, detail_json TEXT NOT NULL, observed_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE soak_days (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id TEXT NOT NULL REFERENCES soak_campaigns(campaign_id),
                trading_date TEXT NOT NULL, run_id TEXT NOT NULL, run_kind TEXT NOT NULL,
                terminal INTEGER NOT NULL CHECK(terminal IN (0,1)),
                credit_state TEXT NOT NULL CHECK(credit_state IN ('ELIGIBLE','CREDITED','NOT_CREDITED')),
                credit_detail_json TEXT NOT NULL, designated_at TEXT NOT NULL,
                UNIQUE(campaign_id, trading_date), UNIQUE(campaign_id, run_id)
            )"""
        )
        conn.execute(
            """CREATE TABLE soak_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                observation_id TEXT UNIQUE,
                campaign_id TEXT NOT NULL REFERENCES soak_campaigns(campaign_id),
                run_id TEXT, ticker TEXT, order_intent_id TEXT, drill_id TEXT,
                event_code TEXT NOT NULL, evidence_class TEXT,
                detail_json TEXT NOT NULL, observed_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE soak_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                campaign_id TEXT NOT NULL REFERENCES soak_campaigns(campaign_id),
                run_id TEXT NOT NULL, stage TEXT NOT NULL, ticker TEXT,
                completeness TEXT NOT NULL, detail_json TEXT NOT NULL, observed_at TEXT NOT NULL
            )"""
        )
        if fail_after_step == "snapshots":
            raise RuntimeError("injected migration failure")
        for table, columns in (
            ("orders", "order_id TEXT, status TEXT, remaining_qty INTEGER"),
            ("fills", "order_id TEXT, fill_id TEXT, quantity INTEGER, price REAL"),
            ("holdings", "ticker TEXT, quantity INTEGER, average_price REAL"),
            ("accounts", "available_cash REAL, total_value REAL"),
        ):
            conn.execute(
                f"""CREATE TABLE soak_snapshot_{table} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    observation_id TEXT NOT NULL UNIQUE,
                    snapshot_id TEXT NOT NULL REFERENCES soak_snapshots(snapshot_id),
                    {columns}, detail_json TEXT NOT NULL
                )"""
            )
        conn.execute(
            """CREATE TABLE soak_comparisons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                comparison_id TEXT NOT NULL UNIQUE,
                campaign_id TEXT NOT NULL REFERENCES soak_campaigns(campaign_id),
                snapshot_id TEXT REFERENCES soak_snapshots(snapshot_id), run_id TEXT NOT NULL,
                ticker TEXT, order_intent_id TEXT, verdict TEXT NOT NULL,
                remaining_order_terminal INTEGER NOT NULL CHECK(remaining_order_terminal IN (0,1)),
                detail_json TEXT NOT NULL, observed_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE soak_ambiguity_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                observation_id TEXT NOT NULL UNIQUE,
                campaign_id TEXT NOT NULL REFERENCES soak_campaigns(campaign_id),
                run_id TEXT NOT NULL, ticker TEXT NOT NULL, order_intent_id TEXT NOT NULL,
                verdict TEXT NOT NULL, remaining_order_terminal INTEGER NOT NULL CHECK(remaining_order_terminal IN (0,1)),
                detail_json TEXT NOT NULL, observed_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE soak_ticker_freezes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                freeze_id TEXT NOT NULL, campaign_id TEXT NOT NULL REFERENCES soak_campaigns(campaign_id),
                ticker TEXT NOT NULL, order_intent_id TEXT, freeze_kind TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('FROZEN','RELEASED')),
                prior_transition_id INTEGER REFERENCES soak_ticker_freezes(id),
                release_evidence_type TEXT, release_evidence_id TEXT,
                detail_json TEXT NOT NULL, observed_at TEXT NOT NULL,
                UNIQUE(freeze_id, state),
                CHECK((state='FROZEN' AND release_evidence_id IS NULL) OR
                      (state='RELEASED' AND release_evidence_id IS NOT NULL))
            )"""
        )
        conn.execute(
            """CREATE TABLE soak_drill_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                link_id TEXT NOT NULL UNIQUE,
                campaign_id TEXT NOT NULL REFERENCES soak_campaigns(campaign_id),
                drill_id TEXT NOT NULL, run_id TEXT, ticker TEXT, order_intent_id TEXT,
                evidence_class TEXT NOT NULL, verdict TEXT NOT NULL,
                detail_json TEXT NOT NULL, observed_at TEXT NOT NULL
            )"""
        )
        for table in _TABLES:
            conn.execute(
                f"""CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table}
                BEGIN SELECT RAISE(ABORT, 'append-only evidence'); END"""
            )
            conn.execute(
                f"""CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table}
                BEGIN SELECT RAISE(ABORT, 'append-only evidence'); END"""
            )
        for statement in (
            "CREATE INDEX ix_soak_days_campaign_date ON soak_days(campaign_id,trading_date)",
            "CREATE INDEX ix_soak_events_cross_ids ON soak_events(campaign_id,run_id,ticker,order_intent_id,observed_at)",
            "CREATE INDEX ix_soak_snapshots_cross_ids ON soak_snapshots(campaign_id,run_id,ticker,observed_at)",
            "CREATE INDEX ix_soak_comparisons_cross_ids ON soak_comparisons(campaign_id,run_id,ticker,order_intent_id,observed_at)",
            "CREATE INDEX ix_soak_ambiguity_cross_ids ON soak_ambiguity_observations(campaign_id,run_id,ticker,order_intent_id,observed_at)",
            "CREATE INDEX ix_soak_freezes_current ON soak_ticker_freezes(campaign_id,ticker,freeze_id,id)",
            "CREATE INDEX ix_soak_drills_cross_ids ON soak_drill_links(campaign_id,drill_id,run_id,ticker,order_intent_id)",
        ):
            conn.execute(statement)
        conn.execute(f"PRAGMA user_version={SOAK_SCHEMA_VERSION}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def connect_soak_store(path: PathLike) -> sqlite3.Connection:
    db_path = Path(path)
    if str(db_path) != ":memory:":
        db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    migrate_soak_store(conn)
    return conn


def _write(conn: sqlite3.Connection, sql: str, values: tuple[Any, ...]) -> int:
    try:
        cursor = conn.execute(sql, values)
        conn.commit()
        return int(cursor.lastrowid)
    except Exception:
        conn.rollback()
        raise


def create_campaign(
    conn: sqlite3.Connection,
    *,
    campaign_id: str,
    accepted_profile_fingerprint: str,
    accepted_profile_version: str,
    field_contract_version: str,
    ambiguity_policy_version: str,
    ambiguity_window_seconds: int,
    ambiguity_poll_cadence_seconds: int,
    ambiguity_max_observations: int,
    target_eligible_days: int = 20,
    availability_failure_budget: int = 2,
    created_at: str | None = None,
) -> dict[str, Any]:
    if not campaign_id or not accepted_profile_fingerprint:
        raise ValueError("campaign_id and accepted profile fingerprint are required")
    conn.execute(
        """INSERT INTO soak_campaigns (
        campaign_id,state,target_eligible_days,availability_failure_budget,
        accepted_profile_fingerprint,accepted_profile_version,field_contract_version,
        ambiguity_policy_version,ambiguity_window_seconds,ambiguity_poll_cadence_seconds,
        ambiguity_max_observations,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (campaign_id, CampaignState.ACTIVE.value, target_eligible_days,
         availability_failure_budget, accepted_profile_fingerprint,
         accepted_profile_version, field_contract_version, ambiguity_policy_version,
         ambiguity_window_seconds, ambiguity_poll_cadence_seconds,
         ambiguity_max_observations, created_at or _now()),
    )
    conn.commit()
    return load_campaign_state(conn, campaign_id=campaign_id)


def append_identity_receipt(
    conn: sqlite3.Connection, *, receipt_id: str, campaign_id: str, target: str,
    domain_class: str, account_suffix: str, profile_version: str,
    policy_version: str, detail: Mapping[str, Any] | None = None,
    observed_at: str | None = None,
) -> int:
    if target != "mock":
        raise ValueError("soak identity target must be mock")
    return _write(conn, """INSERT INTO soak_identity_receipts
        (receipt_id,campaign_id,target,domain_class,account_suffix,profile_version,
         policy_version,detail_json,observed_at) VALUES (?,?,?,?,?,?,?,?,?)""",
        (receipt_id,campaign_id,target,domain_class,account_suffix,profile_version,
         policy_version,_detail(detail),observed_at or _now()))


def designate_day(
    conn: sqlite3.Connection, *, campaign_id: str, trading_date: str, run_id: str,
    run_kind: str, terminal: bool, credit_state: DayCreditState = DayCreditState.ELIGIBLE,
    detail: Mapping[str, Any] | None = None, designated_at: str | None = None,
) -> int:
    if run_kind not in _RUN_KINDS:
        raise ValueError("unknown soak run kind")
    credit = DayCreditState(credit_state)
    if credit is DayCreditState.CREDITED and (run_kind != "RUN" or not terminal):
        raise ValueError("only a terminal designated RUN may earn day credit")
    return _write(conn, """INSERT INTO soak_days
        (campaign_id,trading_date,run_id,run_kind,terminal,credit_state,credit_detail_json,designated_at)
        VALUES (?,?,?,?,?,?,?,?)""",
        (campaign_id,trading_date,run_id,run_kind,int(terminal),credit.value,
         _detail(detail),designated_at or _now()))


def append_campaign_event(
    conn: sqlite3.Connection, *, campaign_id: str, event_code: str,
    observation_id: str | None = None, run_id: str | None = None,
    ticker: str | None = None, order_intent_id: str | None = None,
    drill_id: str | None = None, evidence_class: SoakEvidenceClass | None = None,
    detail: Mapping[str, Any] | None = None, observed_at: str | None = None,
) -> int:
    _code(event_code, "event_code")
    evidence = SoakEvidenceClass(evidence_class).value if evidence_class is not None else None
    return _write(conn, """INSERT INTO soak_events
        (observation_id,campaign_id,run_id,ticker,order_intent_id,drill_id,event_code,
         evidence_class,detail_json,observed_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (observation_id,campaign_id,run_id,ticker,order_intent_id,drill_id,event_code,
         evidence,_detail(detail),observed_at or _now()))


def append_snapshot(
    conn: sqlite3.Connection, *, snapshot_id: str, campaign_id: str, run_id: str,
    stage: ReconciliationStage | str, ticker: str | None = None,
    completeness: PageCompleteness | str = PageCompleteness.COMPLETE,
    orders: Sequence[Mapping[str, Any]] = (), fills: Sequence[Mapping[str, Any]] = (),
    holdings: Sequence[Mapping[str, Any]] = (), accounts: Sequence[Mapping[str, Any]] = (),
    detail: Mapping[str, Any] | None = None, observed_at: str | None = None,
) -> str:
    stage_value = ReconciliationStage(stage).value
    completeness_value = PageCompleteness(completeness).value
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("""INSERT INTO soak_snapshots
            (snapshot_id,campaign_id,run_id,stage,ticker,completeness,detail_json,observed_at)
            VALUES (?,?,?,?,?,?,?,?)""",
            (snapshot_id,campaign_id,run_id,stage_value,ticker,completeness_value,
             _detail(detail),observed_at or _now()))
        _append_snapshot_rows(conn, "orders", snapshot_id, orders,
            ("order_id","status","remaining_qty"))
        _append_snapshot_rows(conn, "fills", snapshot_id, fills,
            ("order_id","fill_id","quantity","price"))
        _append_snapshot_rows(conn, "holdings", snapshot_id, holdings,
            ("ticker","quantity","average_price"))
        _append_snapshot_rows(conn, "accounts", snapshot_id, accounts,
            ("available_cash","total_value"))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return snapshot_id


def _append_snapshot_rows(
    conn: sqlite3.Connection, kind: str, snapshot_id: str,
    rows: Sequence[Mapping[str, Any]], columns: tuple[str, ...],
) -> None:
    for index, row in enumerate(rows):
        clean = sanitize_detail(row)
        observation_id = str(clean.pop("observation_id", f"{snapshot_id}:{kind}:{index}"))
        known = [clean.pop(column, None) for column in columns]
        names = ",".join(columns)
        marks = ",".join("?" for _ in columns)
        conn.execute(
            f"INSERT INTO soak_snapshot_{kind} (observation_id,snapshot_id,{names},detail_json) VALUES (?,?,{marks},?)",
            (observation_id,snapshot_id,*known,_detail(clean)),
        )


def read_snapshot(conn: sqlite3.Connection, *, snapshot_id: str) -> dict[str, Any]:
    conn.row_factory = sqlite3.Row
    started = not conn.in_transaction
    if started:
        conn.execute("BEGIN")
    try:
        parent = conn.execute(
            "SELECT * FROM soak_snapshots WHERE snapshot_id=?", (snapshot_id,)
        ).fetchone()
        if parent is None:
            raise KeyError(snapshot_id)
        result: dict[str, Any] = {"snapshot": dict(parent)}
        for kind in ("orders", "fills", "holdings", "accounts"):
            result[kind] = [dict(row) for row in conn.execute(
                f"SELECT * FROM soak_snapshot_{kind} WHERE snapshot_id=? ORDER BY id", (snapshot_id,)
            )]
        if started:
            conn.commit()
        return result
    except Exception:
        if started:
            conn.rollback()
        raise


def append_comparison(
    conn: sqlite3.Connection, *, comparison_id: str, campaign_id: str,
    run_id: str, verdict: ReconciliationVerdict | str,
    remaining_order_terminal: bool, snapshot_id: str | None = None,
    ticker: str | None = None, order_intent_id: str | None = None,
    detail: Mapping[str, Any] | None = None, observed_at: str | None = None,
) -> int:
    return _write(conn, """INSERT INTO soak_comparisons
        (comparison_id,campaign_id,snapshot_id,run_id,ticker,order_intent_id,verdict,
         remaining_order_terminal,detail_json,observed_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (comparison_id,campaign_id,snapshot_id,run_id,ticker,order_intent_id,
         ReconciliationVerdict(verdict).value,int(remaining_order_terminal),
         _detail(detail),observed_at or _now()))


def append_ambiguity_observation(
    conn: sqlite3.Connection, *, observation_id: str, campaign_id: str, run_id: str,
    ticker: str, order_intent_id: str, verdict: AmbiguityVerdict | str,
    remaining_order_terminal: bool, detail: Mapping[str, Any] | None = None,
    observed_at: str | None = None,
) -> int:
    return _write(conn, """INSERT INTO soak_ambiguity_observations
        (observation_id,campaign_id,run_id,ticker,order_intent_id,verdict,
         remaining_order_terminal,detail_json,observed_at) VALUES (?,?,?,?,?,?,?,?,?)""",
        (observation_id,campaign_id,run_id,ticker,order_intent_id,
         AmbiguityVerdict(verdict).value,int(remaining_order_terminal),
         _detail(detail),observed_at or _now()))


def append_drill_link(
    conn: sqlite3.Connection, *, link_id: str, campaign_id: str, drill_id: str,
    evidence_class: SoakEvidenceClass | str, verdict: DrillVerdict | str,
    run_id: str | None = None, ticker: str | None = None,
    order_intent_id: str | None = None, detail: Mapping[str, Any] | None = None,
    observed_at: str | None = None,
) -> int:
    return _write(conn, """INSERT INTO soak_drill_links
        (link_id,campaign_id,drill_id,run_id,ticker,order_intent_id,evidence_class,
         verdict,detail_json,observed_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (link_id,campaign_id,drill_id,run_id,ticker,order_intent_id,
         SoakEvidenceClass(evidence_class).value,DrillVerdict(verdict).value,
         _detail(detail),observed_at or _now()))


def load_campaign_state(conn: sqlite3.Connection, *, campaign_id: str) -> dict[str, Any]:
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM soak_campaigns WHERE campaign_id=?", (campaign_id,)).fetchone()
    if row is None:
        raise KeyError(campaign_id)
    result = dict(row)
    result["state"] = CampaignState(result["state"])
    result["credited_days"] = int(conn.execute(
        "SELECT COUNT(*) FROM soak_days WHERE campaign_id=? AND credit_state='CREDITED'",
        (campaign_id,),
    ).fetchone()[0])
    result["active_freezes"] = [dict(item) for item in conn.execute(
        """SELECT f.* FROM soak_ticker_freezes f WHERE f.campaign_id=? AND f.state='FROZEN'
        AND NOT EXISTS (SELECT 1 FROM soak_ticker_freezes r
                        WHERE r.freeze_id=f.freeze_id AND r.state='RELEASED') ORDER BY f.id""",
        (campaign_id,),
    )]
    return result


class _BoundStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create_campaign(self, **kwargs: Any) -> dict[str, Any]:
        return create_campaign(self.conn, **kwargs)


def bind(conn: sqlite3.Connection) -> _BoundStore:
    """Small convenience facade for dependency-injected services."""

    return _BoundStore(conn)


__all__ = [
    "SOAK_SCHEMA_VERSION", "connect_soak_store", "migrate_soak_store",
    "fingerprint_accepted_profile", "create_campaign", "append_identity_receipt",
    "designate_day", "append_campaign_event", "append_snapshot", "read_snapshot",
    "append_comparison", "append_ambiguity_observation", "append_drill_link",
    "load_campaign_state", "bind",
]
