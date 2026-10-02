"""Operational alerts use temporary metadata only; never mutate source facts."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from trading_bot.alert_models import AlertSubject, AlertSourceFact, Severity
from trading_bot.alert_store import AlertStore, RevisionConflict

NOW = datetime(2026, 10, 2, 1, tzinfo=timezone.utc)


class Clock:
    def __init__(self):
        self.now = NOW

    def __call__(self):
        return self.now


@pytest.fixture
def store(tmp_path):
    clock = Clock()
    result = AlertStore(tmp_path / "operation.db", clock=clock)
    result.initialize()
    return result


def fact(identity="one", seconds=0, **changes):
    base = AlertSourceFact(
        subject=AlertSubject("portfolio", "a" * 64, "mock", "005930", "BROKER_ORDER", "order-1"),
        source_owner="phase11", source_id=identity, sequence=seconds,
        observed_at=NOW + timedelta(seconds=seconds), normalized_state="LONG_OPEN_ORDER",
        severity=Severity.WARNING,
    )
    return replace(base, **changes)


def test_episode_unique_observations_duration_restart_and_backdated_insert(store):
    first = store.observe(fact())
    assert store.observe(fact()) == first
    second = store.observe(fact("two", 60))
    assert second.episode_id == first.episode_id
    assert second.occurrence_count == 2 and second.duration_seconds == 60
    reopened = AlertStore(store.path, clock=store.clock)
    assert reopened.observe(fact("two", 60)) == second
    earlier = reopened.observe(fact("backdated", 0, observed_at=NOW - timedelta(seconds=10)))
    assert earlier.occurrence_count == 3 and earlier.duration_seconds == 70
    assert reopened.get_cursor("phase11", "portfolio") == 60
    assert reopened.get_incident(first.episode_id) == earlier


def test_revision_worsening_and_episode_recurrence_cannot_inherit_acknowledgement(store):
    first = store.observe(fact())
    ack = store.acknowledge(first.episode_id, first.revision, "operator", note="")
    assert ack.note == "" and store.get_incident(first.episode_id).acknowledged
    worse = store.observe(fact("worse", 1, severity=Severity.CRITICAL, normalized_state="ORDER_AMBIGUOUS"))
    assert worse.revision == 2 and not worse.acknowledged
    assert len(store.list_revisions(first.episode_id)) == 2
    assert len(store.list_acknowledgements(first.episode_id)) == 1
    recovered = store.observe(fact("recovery", 2, normalized_state="RESOLVED", positive_recovery=True,
                                   recovery_proof_id="saved-same-subject-proof"))
    assert not recovered.active and recovered.recovered_at == NOW + timedelta(seconds=2)
    again = store.observe(fact("again", 3))
    assert again.episode_id != first.episode_id and not again.acknowledged
    assert len(store.list_incidents()) == 2
    assert store.list_incidents(active=True) == (again,)


def test_acknowledge_compare_and_swap_server_time_bounded_note_no_source_write(store, tmp_path):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE frozen(ticker TEXT,active INTEGER)")
        conn.execute("INSERT INTO frozen VALUES('000660',1)")
    before = source.read_bytes()
    episode = store.observe(fact())
    store.clock.now += timedelta(minutes=1)
    with pytest.raises(ValueError):
        store.acknowledge(episode.episode_id, 1, "", note="")
    with pytest.raises(ValueError):
        store.acknowledge(episode.episode_id, 1, "operator", note="x" * 501)
    ack = store.acknowledge(episode.episode_id, 1, "operator", at=NOW-timedelta(days=10), note="x" * 500)
    assert ack.at == store.clock.now and ack.actor == "operator"
    worse = store.observe(fact("worse", 90, severity="CRITICAL"))
    with pytest.raises(RevisionConflict):
        store.acknowledge(episode.episode_id, 1, "operator")
    assert not store.get_incident(worse.episode_id).acknowledged
    assert source.read_bytes() == before
    assert store.list_actions()[-1].result_code == "REVISION_CONFLICT"


def test_episode_recovery_requires_positive_matching_subject_and_monotonic_proof(store):
    episode = store.observe(fact())
    uncertain = store.observe(fact("missing", 1, normalized_state="UNKNOWN"))
    assert uncertain.active
    with pytest.raises(ValueError):
        fact("unproven", positive_recovery=True)
    other = replace(fact("other", 2, positive_recovery=True, recovery_proof_id="proof"),
                    subject=replace(episode.subject, broker_subject="other-order"))
    assert store.observe(other) is None
    assert store.get_incident(episode.episode_id).active
    stale = fact("old-proof", 0, positive_recovery=True, recovery_proof_id="proof")
    assert store.observe(stale).active


def test_schema_ownership_coexists_and_unknown_version_refuses_without_writes(tmp_path):
    from trading_bot.web_config import WebSettings
    from trading_bot.web_store import WebStore
    root = tmp_path / "operation"
    settings = WebSettings(operational_db=root / "operator.db", artifact_root=root / "artifacts")
    web = WebStore(settings)
    web.initialize()
    alerts = AlertStore(settings.operational_db)
    alerts.initialize()
    web.initialize()
    with sqlite3.connect(alerts.path) as conn:
        assert conn.execute("SELECT version FROM phase14_web_metadata").fetchone() == (2,)
        conn.execute("UPDATE phase14_alert_metadata SET version=999")
    before = alerts.path.read_bytes()
    with pytest.raises(ValueError, match="schema"):
        alerts.initialize()
    assert alerts.path.read_bytes() == before


def test_schema_rejects_source_database_without_migration(tmp_path):
    path = tmp_path / "source.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE orders(order_id TEXT)")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="ownership"):
        AlertStore(path).initialize()
    assert path.read_bytes() == before


@pytest.mark.parametrize("changes", [{"sequence": -1}, {"observed_at": NOW.replace(tzinfo=None)},
    {"normalized_state": "x" * 129}, {"severity": "not-a-severity"}])
def test_episode_fact_contract_is_strict(changes):
    with pytest.raises(ValueError):
        fact(**changes)
