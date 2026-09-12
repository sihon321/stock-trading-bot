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
    CampaignKind,
    CampaignState,
    DayCreditState,
    DrillVerdict,
    FreezeState,
    PageCompleteness,
    ReconciliationStage,
    ReconciliationVerdict,
    SoakEvidenceClass,
)

SOAK_SCHEMA_VERSION = 2
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
    "soak_identity_receipts", "soak_days", "soak_events", "soak_snapshots",
    "soak_snapshot_orders",
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
    if version == 1:
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("ALTER TABLE soak_campaigns ADD COLUMN campaign_kind TEXT NOT NULL DEFAULT 'SOAK' CHECK(campaign_kind IN ('SOAK','PROOF_ORDER'))")
            conn.execute("ALTER TABLE soak_campaigns ADD COLUMN credit_eligible INTEGER NOT NULL DEFAULT 1 CHECK(credit_eligible IN (0,1))")
            conn.execute(
                """CREATE TRIGGER soak_proof_campaign_non_credit_insert
                BEFORE INSERT ON soak_campaigns
                WHEN NEW.campaign_kind='PROOF_ORDER' AND NEW.credit_eligible!=0
                BEGIN SELECT RAISE(ABORT, 'proof campaign cannot earn credit'); END"""
            )
            conn.execute(
                """CREATE TRIGGER soak_proof_campaign_contract_immutable
                BEFORE UPDATE ON soak_campaigns
                WHEN OLD.campaign_kind!=NEW.campaign_kind OR OLD.credit_eligible!=NEW.credit_eligible
                BEGIN SELECT RAISE(ABORT, 'immutable proof campaign contract'); END"""
            )
            conn.execute(f"PRAGMA user_version={SOAK_SCHEMA_VERSION}")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """CREATE TABLE soak_campaigns (
                campaign_id TEXT PRIMARY KEY,
                state TEXT NOT NULL CHECK(state IN ('ACTIVE','COMPLETED','FAILED')),
                campaign_kind TEXT NOT NULL CHECK(campaign_kind IN ('SOAK','PROOF_ORDER')),
                credit_eligible INTEGER NOT NULL CHECK(credit_eligible IN (0,1)),
                target_eligible_days INTEGER NOT NULL CHECK(target_eligible_days > 0),
                availability_failure_budget INTEGER NOT NULL CHECK(availability_failure_budget > 0),
                availability_failures_used INTEGER NOT NULL DEFAULT 0 CHECK(availability_failures_used >= 0),
                safety_failure_code TEXT,
                availability_failure_code TEXT,
                accepted_profile_fingerprint TEXT NOT NULL,
                accepted_profile_version TEXT NOT NULL,
                field_contract_version TEXT NOT NULL,
                ambiguity_policy_version TEXT NOT NULL,
                ambiguity_window_seconds INTEGER NOT NULL CHECK(ambiguity_window_seconds > 0),
                ambiguity_poll_cadence_seconds INTEGER NOT NULL CHECK(ambiguity_poll_cadence_seconds > 0),
                ambiguity_max_observations INTEGER NOT NULL CHECK(ambiguity_max_observations > 0),
                created_at TEXT NOT NULL,
                CHECK(ambiguity_poll_cadence_seconds <= ambiguity_window_seconds),
                CHECK(campaign_kind!='PROOF_ORDER' OR credit_eligible=0),
                CHECK(state != 'FAILED' OR safety_failure_code IS NOT NULL
                      OR availability_failure_code IS NOT NULL)
            )"""
        )
        conn.execute(
            """CREATE TRIGGER soak_proof_campaign_contract_immutable
            BEFORE UPDATE ON soak_campaigns
            WHEN OLD.campaign_kind!=NEW.campaign_kind OR OLD.credit_eligible!=NEW.credit_eligible
            BEGIN SELECT RAISE(ABORT, 'immutable proof campaign contract'); END"""
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
            """CREATE TRIGGER soak_campaign_latches_monotonic
            BEFORE UPDATE ON soak_campaigns
            WHEN NEW.availability_failures_used < OLD.availability_failures_used
              OR (OLD.safety_failure_code IS NOT NULL
                  AND NEW.safety_failure_code IS NOT OLD.safety_failure_code)
              OR (OLD.availability_failure_code IS NOT NULL
                  AND NEW.availability_failure_code IS NOT OLD.availability_failure_code)
            BEGIN SELECT RAISE(ABORT, 'campaign latches are monotonic'); END"""
        )
        conn.execute(
            """CREATE TRIGGER soak_campaign_no_delete BEFORE DELETE ON soak_campaigns
            BEGIN SELECT RAISE(ABORT, 'campaign evidence cannot be deleted'); END"""
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
            """CREATE TRIGGER soak_identity_profile_matches_campaign
            BEFORE INSERT ON soak_identity_receipts
            WHEN NEW.profile_version != (
                SELECT accepted_profile_version FROM soak_campaigns
                WHERE campaign_id=NEW.campaign_id)
            BEGIN SELECT RAISE(ABORT, 'identity profile does not match campaign'); END"""
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
    campaign_kind: CampaignKind = CampaignKind.SOAK,
    credit_eligible: bool = True,
    created_at: str | None = None,
) -> dict[str, Any]:
    kind = CampaignKind(campaign_kind)
    if kind is CampaignKind.PROOF_ORDER and credit_eligible:
        raise ValueError("proof campaign cannot earn eligible-day credit")
    if not campaign_id or not accepted_profile_fingerprint:
        raise ValueError("campaign_id and accepted profile fingerprint are required")
    try:
        conn.execute(
            """INSERT INTO soak_campaigns (
            campaign_id,state,campaign_kind,credit_eligible,target_eligible_days,availability_failure_budget,
            accepted_profile_fingerprint,accepted_profile_version,field_contract_version,
            ambiguity_policy_version,ambiguity_window_seconds,ambiguity_poll_cadence_seconds,
            ambiguity_max_observations,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (campaign_id, CampaignState.ACTIVE.value, kind.value, int(credit_eligible), target_eligible_days,
             availability_failure_budget, accepted_profile_fingerprint,
             accepted_profile_version, field_contract_version, ambiguity_policy_version,
             ambiguity_window_seconds, ambiguity_poll_cadence_seconds,
             ambiguity_max_observations, created_at or _now()),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return load_campaign_state(conn, campaign_id=campaign_id)


def create_or_resume_campaign(
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
    campaign_kind: CampaignKind = CampaignKind.SOAK,
    credit_eligible: bool = True,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Create a soak campaign or admit only its pristine incomplete STARTUP retry."""

    kind = CampaignKind(campaign_kind)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM soak_campaigns WHERE campaign_id=?", (campaign_id,)
    ).fetchone()
    if row is None:
        return create_campaign(
            conn,
            campaign_id=campaign_id,
            accepted_profile_fingerprint=accepted_profile_fingerprint,
            accepted_profile_version=accepted_profile_version,
            field_contract_version=field_contract_version,
            ambiguity_policy_version=ambiguity_policy_version,
            ambiguity_window_seconds=ambiguity_window_seconds,
            ambiguity_poll_cadence_seconds=ambiguity_poll_cadence_seconds,
            ambiguity_max_observations=ambiguity_max_observations,
            target_eligible_days=target_eligible_days,
            availability_failure_budget=availability_failure_budget,
            campaign_kind=kind,
            credit_eligible=credit_eligible,
            created_at=created_at,
        )

    expected = {
        "campaign_kind": kind.value,
        "credit_eligible": int(credit_eligible),
        "target_eligible_days": target_eligible_days,
        "availability_failure_budget": availability_failure_budget,
        "accepted_profile_fingerprint": accepted_profile_fingerprint,
        "accepted_profile_version": accepted_profile_version,
        "field_contract_version": field_contract_version,
        "ambiguity_policy_version": ambiguity_policy_version,
        "ambiguity_window_seconds": ambiguity_window_seconds,
        "ambiguity_poll_cadence_seconds": ambiguity_poll_cadence_seconds,
        "ambiguity_max_observations": ambiguity_max_observations,
    }
    if any(row[key] != value for key, value in expected.items()):
        raise ValueError("SOAK_START_RESUME_BLOCKED:POLICY_DRIFT")
    if row["state"] != CampaignState.ACTIVE.value:
        raise ValueError("SOAK_START_RESUME_BLOCKED:TERMINAL_STATE")
    if (
        int(row["availability_failures_used"]) != 0
        or row["safety_failure_code"] is not None
        or row["availability_failure_code"] is not None
    ):
        raise ValueError("SOAK_START_RESUME_BLOCKED:MUTABLE_CAMPAIGN_STATE")

    for table in (
        "soak_days",
        "soak_events",
        "soak_comparisons",
        "soak_ambiguity_observations",
        "soak_ticker_freezes",
        "soak_drill_links",
    ):
        if conn.execute(
            f"SELECT 1 FROM {table} WHERE campaign_id=? LIMIT 1", (campaign_id,)
        ).fetchone() is not None:
            raise ValueError("SOAK_START_RESUME_BLOCKED:MUTABLE_EVIDENCE")

    snapshots = conn.execute(
        """SELECT run_id,stage,ticker,completeness FROM soak_snapshots
           WHERE campaign_id=?""",
        (campaign_id,),
    ).fetchall()
    if not snapshots:
        raise ValueError("SOAK_START_RESUME_BLOCKED:NO_INCOMPLETE_STARTUP")
    if any(
        snapshot["run_id"] != "startup"
        or snapshot["stage"] != ReconciliationStage.STARTUP.value
        or snapshot["ticker"] is not None
        or snapshot["completeness"] != PageCompleteness.INCOMPLETE.value
        for snapshot in snapshots
    ):
        raise ValueError("SOAK_START_RESUME_BLOCKED:NON_STARTUP_EVIDENCE")
    return load_campaign_state(conn, campaign_id=campaign_id)


def create_or_load_proof_campaign(
    conn: sqlite3.Connection,
    *,
    campaign_id: str,
    accepted_profile_fingerprint: str,
    accepted_profile_version: str,
    field_contract_version: str,
    ambiguity_policy: Any,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Create the immutable non-credit proof campaign, or reject any reopen drift."""

    expected = {
        "campaign_kind": CampaignKind.PROOF_ORDER.value,
        "credit_eligible": 0,
        "accepted_profile_fingerprint": accepted_profile_fingerprint,
        "accepted_profile_version": accepted_profile_version,
        "field_contract_version": field_contract_version,
        "ambiguity_policy_version": ambiguity_policy.version,
        "ambiguity_window_seconds": ambiguity_policy.duration_seconds,
        "ambiguity_poll_cadence_seconds": ambiguity_policy.poll_seconds,
        "ambiguity_max_observations": ambiguity_policy.max_observations,
    }
    row = conn.execute("SELECT * FROM soak_campaigns WHERE campaign_id=?", (campaign_id,)).fetchone()
    if row is None:
        return create_campaign(
            conn,
            campaign_id=campaign_id,
            accepted_profile_fingerprint=accepted_profile_fingerprint,
            accepted_profile_version=accepted_profile_version,
            field_contract_version=field_contract_version,
            ambiguity_policy_version=ambiguity_policy.version,
            ambiguity_window_seconds=ambiguity_policy.duration_seconds,
            ambiguity_poll_cadence_seconds=ambiguity_policy.poll_seconds,
            ambiguity_max_observations=ambiguity_policy.max_observations,
            target_eligible_days=1,
            availability_failure_budget=1,
            campaign_kind=CampaignKind.PROOF_ORDER,
            credit_eligible=False,
            created_at=created_at,
        )
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM soak_campaigns WHERE campaign_id=?", (campaign_id,)).fetchone()
    if row is None or any(row[key] != value for key, value in expected.items()):
        raise ValueError("immutable proof campaign contract drift")
    return load_campaign_state(conn, campaign_id=campaign_id)


def append_identity_receipt(
    conn: sqlite3.Connection, *, receipt_id: str, campaign_id: str, target: str,
    domain_class: str, account_suffix: str, profile_version: str,
    policy_version: str, detail: Mapping[str, Any] | None = None,
    observed_at: str | None = None,
) -> int:
    if target != "mock":
        raise ValueError("soak identity target must be mock")
    if re.fullmatch(r"[0-9]{4}", account_suffix) is None:
        raise ValueError("account_suffix must contain exactly four digits")
    return _write(conn, """INSERT INTO soak_identity_receipts
        (receipt_id,campaign_id,target,domain_class,account_suffix,profile_version,
         policy_version,detail_json,observed_at) VALUES (?,?,?,?,?,?,?,?,?)""",
        (receipt_id,campaign_id,target,domain_class,account_suffix,profile_version,
         policy_version,_detail(detail),observed_at or _now()))


def append_or_validate_identity_receipt(
    conn: sqlite3.Connection, *, receipt_id: str, campaign_id: str, target: str,
    domain_class: str, account_suffix: str, profile_version: str,
    policy_version: str, detail: Mapping[str, Any] | None = None,
    observed_at: str | None = None,
) -> int:
    """Append the initial receipt, or return its id only on an exact retry match."""

    expected_detail = _detail(detail)
    rows = conn.execute(
        """SELECT id,receipt_id,target,domain_class,account_suffix,profile_version,
                  policy_version,detail_json
           FROM soak_identity_receipts WHERE campaign_id=?""",
        (campaign_id,),
    ).fetchall()
    if not rows:
        if conn.execute(
            "SELECT 1 FROM soak_snapshots WHERE campaign_id=? LIMIT 1", (campaign_id,)
        ).fetchone() is not None:
            raise ValueError("SOAK_START_RESUME_BLOCKED:IDENTITY_MISSING")
        conflicting = conn.execute(
            "SELECT 1 FROM soak_identity_receipts WHERE receipt_id=?", (receipt_id,)
        ).fetchone()
        if conflicting is not None:
            raise ValueError("SOAK_START_RESUME_BLOCKED:IDENTITY_DRIFT")
        return append_identity_receipt(
            conn,
            receipt_id=receipt_id,
            campaign_id=campaign_id,
            target=target,
            domain_class=domain_class,
            account_suffix=account_suffix,
            profile_version=profile_version,
            policy_version=policy_version,
            detail=detail,
            observed_at=observed_at,
        )
    expected = (
        receipt_id,
        target,
        domain_class,
        account_suffix,
        profile_version,
        policy_version,
        expected_detail,
    )
    if len(rows) != 1 or tuple(rows[0][1:]) != expected:
        raise ValueError("SOAK_START_RESUME_BLOCKED:IDENTITY_DRIFT")
    return int(rows[0][0])


def designate_day(
    conn: sqlite3.Connection, *, campaign_id: str, trading_date: str, run_id: str,
    run_kind: str, terminal: bool, credit_state: DayCreditState = DayCreditState.ELIGIBLE,
    detail: Mapping[str, Any] | None = None, designated_at: str | None = None,
) -> int:
    if run_kind not in _RUN_KINDS:
        raise ValueError("unknown soak run kind")
    credit = DayCreditState(credit_state)
    campaign = conn.execute(
        "SELECT credit_eligible FROM soak_campaigns WHERE campaign_id=?", (campaign_id,)
    ).fetchone()
    if campaign is None:
        raise KeyError(campaign_id)
    if credit is DayCreditState.CREDITED and not bool(campaign[0]):
        raise ValueError("campaign is permanently ineligible for day credit")
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


def consume_availability_failure(
    conn: sqlite3.Connection, *, campaign_id: str, reason_code: str,
    run_id: str | None = None, observed_at: str | None = None,
) -> dict[str, Any]:
    """Consume one D-08 budget unit without setting the safety-breach latch."""

    _code(reason_code, "reason_code")
    timestamp = observed_at or _now()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """SELECT state, availability_failures_used, availability_failure_budget
               FROM soak_campaigns WHERE campaign_id=?""", (campaign_id,)
        ).fetchone()
        if row is None:
            raise KeyError(campaign_id)
        if row[0] != CampaignState.ACTIVE.value:
            raise ValueError("campaign is not active")
        used = int(row[1]) + 1
        exceeded = used > int(row[2])
        conn.execute(
            """UPDATE soak_campaigns SET availability_failures_used=?,
               state=?, availability_failure_code=? WHERE campaign_id=?""",
            (used, CampaignState.FAILED.value if exceeded else CampaignState.ACTIVE.value,
             "D08_BUDGET_EXCEEDED" if exceeded else None, campaign_id),
        )
        conn.execute(
            """INSERT INTO soak_events
               (campaign_id,run_id,event_code,detail_json,observed_at)
               VALUES (?,?,?,?,?)""",
            (campaign_id,run_id,
             "AVAILABILITY_BUDGET_EXCEEDED" if exceeded else "AVAILABILITY_FAILURE_CONSUMED",
             _detail({"reason_code": reason_code, "failures_used": used}), timestamp),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return load_campaign_state(conn, campaign_id=campaign_id)


def latch_safety_failure(
    conn: sqlite3.Connection, *, campaign_id: str, reason_code: str,
    run_id: str | None = None, ticker: str | None = None,
    order_intent_id: str | None = None, observed_at: str | None = None,
) -> dict[str, Any]:
    """Permanently latch one stable D-09 safety breach."""

    code = _code(reason_code, "reason_code")
    if not code.startswith("D09_"):
        raise ValueError("safety failure reason must be a D09 stable code")
    timestamp = observed_at or _now()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT state FROM soak_campaigns WHERE campaign_id=?", (campaign_id,)
        ).fetchone()
        if row is None:
            raise KeyError(campaign_id)
        if row[0] != CampaignState.ACTIVE.value:
            raise ValueError("campaign is not active")
        conn.execute(
            """UPDATE soak_campaigns SET state='FAILED', safety_failure_code=?
               WHERE campaign_id=? AND state='ACTIVE'""", (code,campaign_id),
        )
        conn.execute(
            """INSERT INTO soak_events
               (campaign_id,run_id,ticker,order_intent_id,event_code,detail_json,observed_at)
               VALUES (?,?,?,?,?,?,?)""",
            (campaign_id,run_id,ticker,order_intent_id,"SAFETY_FAILURE_LATCHED",
             _detail({"reason_code": code}),timestamp),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return load_campaign_state(conn, campaign_id=campaign_id)


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


def freeze_ticker(
    conn: sqlite3.Connection, *, freeze_id: str, campaign_id: str, ticker: str,
    freeze_kind: str, order_intent_id: str | None = None,
    detail: Mapping[str, Any] | None = None, observed_at: str | None = None,
) -> int:
    if freeze_kind not in {"AMBIGUITY", "REMAINING_ORDER"}:
        raise ValueError("freeze_kind must be AMBIGUITY or REMAINING_ORDER")
    active = conn.execute(
        """SELECT 1 FROM soak_ticker_freezes f WHERE f.campaign_id=? AND f.ticker=?
           AND f.state='FROZEN' AND NOT EXISTS (
             SELECT 1 FROM soak_ticker_freezes r
             WHERE r.freeze_id=f.freeze_id AND r.state='RELEASED')""",
        (campaign_id,ticker),
    ).fetchone()
    if active is not None:
        raise ValueError("ticker already has an active freeze")
    return _write(conn, """INSERT INTO soak_ticker_freezes
        (freeze_id,campaign_id,ticker,order_intent_id,freeze_kind,state,
         detail_json,observed_at) VALUES (?,?,?,?,?,'FROZEN',?,?)""",
        (freeze_id,campaign_id,ticker,order_intent_id,freeze_kind,
         _detail(detail),observed_at or _now()))


def transition_freeze(
    conn: sqlite3.Connection, *, freeze_id: str, release_evidence_type: str,
    release_evidence_id: str, detail: Mapping[str, Any] | None = None,
    observed_at: str | None = None,
) -> int:
    """Append a RELEASED transition only for determinate terminal broker truth."""

    frozen = conn.execute(
        """SELECT id,campaign_id,ticker,order_intent_id,freeze_kind
           FROM soak_ticker_freezes WHERE freeze_id=? AND state='FROZEN'""",
        (freeze_id,),
    ).fetchone()
    if frozen is None:
        raise ValueError("freeze does not exist")
    if conn.execute(
        "SELECT 1 FROM soak_ticker_freezes WHERE freeze_id=? AND state='RELEASED'",
        (freeze_id,),
    ).fetchone() is not None:
        raise ValueError("freeze is already released")
    if release_evidence_type == "COMPARISON":
        evidence = conn.execute(
            """SELECT campaign_id,ticker,order_intent_id,verdict,remaining_order_terminal
               FROM soak_comparisons WHERE comparison_id=?""", (release_evidence_id,)
        ).fetchone()
        determinate = evidence is not None and evidence[3] == ReconciliationVerdict.MATCHED.value
    elif release_evidence_type == "AMBIGUITY_OBSERVATION":
        evidence = conn.execute(
            """SELECT campaign_id,ticker,order_intent_id,verdict,remaining_order_terminal
               FROM soak_ambiguity_observations WHERE observation_id=?""",
            (release_evidence_id,),
        ).fetchone()
        determinate = evidence is not None and evidence[3] in {
            AmbiguityVerdict.NO_MATCH_CONFIRMED.value,
            AmbiguityVerdict.ONE_MATCH_DETERMINATE.value,
        }
    else:
        raise ValueError("unknown release evidence type")
    same_subject = evidence is not None and (
        evidence[0] == frozen[1] and evidence[1] == frozen[2]
        and evidence[2] == frozen[3]
    )
    if not determinate or not same_subject or not bool(evidence[4]):
        raise ValueError("freeze release requires determinate terminal broker evidence")
    return _write(conn, """INSERT INTO soak_ticker_freezes
        (freeze_id,campaign_id,ticker,order_intent_id,freeze_kind,state,
         prior_transition_id,release_evidence_type,release_evidence_id,detail_json,observed_at)
        VALUES (?,?,?,?,?,'RELEASED',?,?,?,?,?)""",
        (freeze_id,frozen[1],frozen[2],frozen[3],frozen[4],frozen[0],
         release_evidence_type,release_evidence_id,_detail(detail),observed_at or _now()))


def load_campaign_state(conn: sqlite3.Connection, *, campaign_id: str) -> dict[str, Any]:
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM soak_campaigns WHERE campaign_id=?", (campaign_id,)).fetchone()
    if row is None:
        raise KeyError(campaign_id)
    result = dict(row)
    result["state"] = CampaignState(result["state"])
    result["campaign_kind"] = CampaignKind(result["campaign_kind"])
    result["credit_eligible"] = bool(result["credit_eligible"])
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
    "fingerprint_accepted_profile", "create_campaign", "create_or_resume_campaign",
    "create_or_load_proof_campaign", "append_identity_receipt",
    "append_or_validate_identity_receipt",
    "designate_day", "append_campaign_event", "consume_availability_failure",
    "latch_safety_failure", "append_snapshot", "read_snapshot",
    "append_comparison", "append_ambiguity_observation", "append_drill_link",
    "freeze_ticker", "transition_freeze", "load_campaign_state", "bind",
]
