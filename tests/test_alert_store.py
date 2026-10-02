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
    settings = WebSettings(operational_db_path=root / "operator.db", artifact_root=tmp_path / "artifacts")
    web = WebStore(settings)
    web.initialize()
    alerts = AlertStore(settings.operational_db_path)
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


def test_outbox_concurrent_claim_is_committed_before_fake_network(store):
    from concurrent.futures import ThreadPoolExecutor
    episode = store.observe(fact())
    event = store.pending_deliveries()[0]
    def claim(owner):
        return AlertStore(store.path, clock=store.clock).claim_delivery(event.event_key, owner)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, ("observer-one", "observer-two")))
    claimed = [value for value in results if value is not None]
    assert len(claimed) == 1
    attempt = claimed[0]
    assert attempt.episode_id == episode.episode_id and attempt.state == "CLAIMED"
    # Independent connection is the fake transport's view: claim was committed before send.
    independent = AlertStore(store.path, clock=store.clock)
    assert independent.get_delivery(event.event_key).claim_id == attempt.claim_id
    with pytest.raises(ValueError):
        independent.finalize_attempt(event.event_key, "wrong-owner", attempt.claim_id, "DELIVERED")
    completed = independent.finalize_attempt(event.event_key, attempt.owner, attempt.claim_id, "DELIVERED")
    assert completed.state == "DELIVERED"
    assert store.claim_delivery(event.event_key, "observer-three") is None


@pytest.mark.parametrize("sent_before_crash", [False, True])
def test_delivery_crash_is_unknown_and_never_blind_replayed(store, sent_before_crash):
    store.observe(fact())
    event = store.pending_deliveries()[0]
    claimed = store.claim_delivery(event.event_key, "crashed-observer")
    fake_sent = []
    if sent_before_crash:
        fake_sent.append(claimed.event_key)
    store.clock.now += timedelta(minutes=2)
    restarted = AlertStore(store.path, clock=store.clock)
    assert restarted.expire_claims(store.clock.now, stale_after_seconds=60) == 1
    assert restarted.get_delivery(event.event_key).state == "UNKNOWN"
    assert restarted.claim_delivery(event.event_key, "new-observer") is None
    assert restarted.pending_deliveries() == ()
    assert len(fake_sent) == int(sent_before_crash)
    assert [x.state for x in restarted.list_delivery_history(event.event_key)] == ["QUEUED", "CLAIMED", "UNKNOWN"]


def test_delivery_failure_remains_failed_and_secret_exception_codes_are_refused(store):
    store.observe(fact())
    claimed = store.claim_delivery(store.pending_deliveries()[0].event_key, "observer")
    with pytest.raises(ValueError):
        store.finalize_attempt(claimed.event_key, claimed.owner, claimed.claim_id, "FAILED",
                               failure_code="https://discord.invalid/secret")
    result = store.finalize_attempt(claimed.event_key, claimed.owner, claimed.claim_id,
                                    "FAILED", failure_code="TRANSPORT_FAILED")
    assert result.state == "FAILED" and result.failure_code == "TRANSPORT_FAILED"
    assert store.claim_delivery(claimed.event_key, "observer") is None


def test_outbox_producer_owned_missing_delivery_unknown_late_attempt_no_duplicate(store):
    episode = store.observe(fact(delivery_owner="producer", producer_event_id="state-one:STATE_BEGIN"))
    assert store.pending_deliveries() == ()
    attempts = store.list_attempts(episode.episode_id)
    assert len(attempts) == 1 and attempts[0].state == "UNKNOWN"
    assert attempts[0].delivery_owner == "producer"
    # Producer evidence arrives separately from its observation, retaining its durable row ID.
    linked = store.link_producer_delivery(episode.episode_id, 1, "OCCURRENCE",
        source_owner="phase11", resource_id="portfolio", producer_event_id="state-one:STATE_BEGIN",
        producer_attempt_id="transition-notification:42", state="FAILED", at=NOW)
    assert linked.state == "FAILED" and linked.producer_attempt_id == "transition-notification:42"
    assert store.link_producer_delivery(episode.episode_id, 1, "OCCURRENCE",
        source_owner="phase11", resource_id="portfolio", producer_event_id="state-one:STATE_BEGIN",
        producer_attempt_id="transition-notification:42", state="FAILED", at=NOW) == linked
    assert store.claim_delivery(linked.event_key, "observer") is None
    assert store.pending_deliveries() == ()


def test_outbox_occurrence_worsening_recovery_only_once_and_info_stays_web_only(store):
    episode = store.observe(fact())
    store.observe(fact())
    store.observe(fact("repeat", 1))
    store.observe(fact("worse", 2, severity="CRITICAL"))
    store.observe(fact("recovery", 3, severity="INFO", positive_recovery=True, recovery_proof_id="proof"))
    assert [item.kind for item in store.list_attempts(episode.episode_id)] == ["OCCURRENCE", "WORSENING", "RECOVERY"]
    info = store.observe(replace(fact("info", 4, severity="INFO"),
                                subject=replace(episode.subject, broker_subject="info-order")))
    assert store.list_attempts(info.episode_id) == ()


def test_reminder_critical_only_exact_boundary_ack_suppression_no_catchup(store):
    warning = store.observe(fact())
    critical = store.observe(replace(fact("critical", severity="CRITICAL"),
                                    subject=replace(warning.subject, broker_subject="critical-order")))
    assert store.due_reminders(NOW + timedelta(seconds=1799)) == ()
    due = store.due_reminders(NOW + timedelta(minutes=30))
    assert len(due) == 1 and due[0].episode_id == critical.episode_id
    # A long outage dispatches one existing window and schedules from the actual claim time.
    store.clock.now = NOW + timedelta(hours=10)
    assert len(store.due_reminders(store.clock.now)) == 1
    claimed = store.claim_delivery(due[0].event_key, "observer")
    assert claimed.kind == "REMINDER"
    assert store.get_incident(critical.episode_id).next_reminder_at == store.clock.now + timedelta(minutes=30)
    assert store.due_reminders(store.clock.now) == ()
    store.finalize_attempt(claimed.event_key, claimed.owner, claimed.claim_id, "UNKNOWN")
    store.clock.now += timedelta(minutes=30)
    next_due = store.due_reminders(store.clock.now)
    assert len(next_due) == 1 and next_due[0].event_key != claimed.event_key
    store.acknowledge(critical.episode_id, 1, "operator")
    assert store.due_reminders(store.clock.now + timedelta(days=1)) == ()
    assert store.claim_delivery(next_due[0].event_key, "observer") is None
    assert store.get_delivery(next_due[0].event_key).state == "SUPPRESSED"
    assert store.get_incident(critical.episode_id).active


def test_reminder_worsened_revision_old_queue_suppressed_and_new_unread(store):
    episode = store.observe(fact(severity="CRITICAL"))
    store.clock.now += timedelta(minutes=30)
    event = store.due_reminders(store.clock.now)[0]
    recovered = store.observe(fact("recovery", 1900, positive_recovery=True, recovery_proof_id="proof"))
    assert not recovered.active
    assert store.claim_delivery(event.event_key, "observer") is None
    assert store.get_delivery(event.event_key).state == "SUPPRESSED"
    again = store.observe(fact("again", 2000, severity="CRITICAL"))
    assert again.episode_id != episode.episode_id and not again.acknowledged
    assert again.next_reminder_at == store.clock.now + timedelta(minutes=30)
