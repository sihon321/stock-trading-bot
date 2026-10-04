"""Final service control application; RUNNING remains independent of trading activation."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import uuid

from pydantic import AwareDatetime, Field, model_validator

from .control_store import _ServiceControlCapability, _stamp
from .service_models import ControlAction, ControlMode, Identity, ServiceContract, ServiceScope, SourceHash


class ResumeSafetyEvidence(ServiceContract):
    """Fresh scoped broker/evidence/calendar/authority facts, never a trading grant.

    current_safety must read the same current local source identities and flags
    without network work. The slower fresh broker/evidence checks belong solely
    in validate_resume, which is always called outside the global admission lock.
    Frozen subjects and the independent latch are checked, never cleared here.
    """
    scope: ServiceScope
    observed_at: AwareDatetime
    expires_at: AwareDatetime
    broker_complete: bool = Field(strict=True)
    evidence_complete: bool = Field(strict=True)
    calendar_confirmed: bool = Field(strict=True)
    authority_current: bool = Field(strict=True)
    safety_latched: bool = Field(strict=True)
    frozen_subjects: tuple[Identity, ...] = Field(max_length=128)
    source_hashes: tuple[SourceHash, ...] = Field(min_length=4, max_length=128)

    @model_validator(mode='after')
    def source_contract(self):
        if (len({s.source_id for s in self.source_hashes}) != len(self.source_hashes)
                or not self.observed_at < self.expires_at <= self.observed_at + timedelta(seconds=10)):
            raise ValueError('unique current sources and bounded freshness required')
        return self

    @property
    def safe(self):
        return (self.broker_complete and self.evidence_complete and self.calendar_confirmed
                and self.authority_current and not self.safety_latched and not self.frozen_subjects)


class ControlApplier:
    """Only the actual live final-service capability may append applied evidence.

    validate_resume(scope, now) performs fresh checks before taking admission.lock.
    current_safety(scope, now) is a bounded local reread of those very same source
    hashes, observations and safety flags while locked. Missing callbacks deny.
    Neither callback may reset a freeze, latch, account lease or acceptance gate.
    """
    def __init__(self, capability, *, validate_resume=None, current_safety=None, clock=None):
        if type(capability) is not _ServiceControlCapability:
            raise ValueError('explicit final service control capability required')
        capability.assert_owner()
        self.__capability = capability
        self.__store = capability._store
        self.__validate = validate_resume
        self.__current = current_safety
        self.__clock = clock or self.__store.clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _valid(evidence, scope, now, requested_at):
        if type(evidence) is not ResumeSafetyEvidence or evidence.scope != scope:
            return 'SAFETY_UNAVAILABLE'
        if not evidence.observed_at <= now < evidence.expires_at or evidence.observed_at < requested_at:
            return 'SAFETY_STALE'
        if not evidence.safe: return 'SAFETY_BLOCKED'
        return None

    def apply_pending(self, *, limit=100):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('bounded application batch required')
        self.__capability.assert_owner()
        with self.__store._connection() as conn:
            rows = conn.execute('SELECT r.* FROM control_requests r WHERE NOT EXISTS '
                '(SELECT 1 FROM control_applications a WHERE a.request_id=r.request_id) '
                'ORDER BY r.acceptance_revision LIMIT ?', (limit,)).fetchall()
        results = []
        for row in rows:
            result = self._apply_one(dict(row))
            if result is not None: results.append(result)
        return tuple(results)

    def _apply_one(self, row):
        self.__capability.assert_owner()
        request = self.__store._request_from_row(row)
        evidence, failure = {}, None
        if request.action == ControlAction.RESUME:
            # An already-stale resume needs no permissive validation.
            with self.__store._connection() as conn:
                latest = self.__store._effective(conn).acceptance_revision
                owner = conn.execute("SELECT actor FROM control_request_audit WHERE event='OWNER_SETUP'").fetchone()[0]
            if latest != row['acceptance_revision']:
                failure = 'REVISION_CONFLICT'
            elif request.actor != owner:
                failure = 'OWNER_REQUIRED'
            elif self.__validate is None or self.__current is None:
                failure = 'SAFETY_UNAVAILABLE'
            else:
                # All registered money-moving accounts belong to the same stop domain.
                for scope in self.__store.scope.registered_scopes:
                    try:
                        fresh = self.__validate(scope, self.__clock())
                        failure = self._valid(fresh, scope, self.__clock(), request.requested_at)
                    except Exception:
                        failure = 'SAFETY_UNAVAILABLE'
                    if failure: break
                    evidence[scope] = fresh

        with self.__store.admission_lock() as lock:
            self.__capability.assert_owner()
            with self.__store._connection() as conn:
                state = self.__store._effective(conn)
                exists = conn.execute('SELECT 1 FROM control_applications WHERE request_id=?', (request.request_id,)).fetchone()
            if exists: return None
            if request.action == ControlAction.RESUME:
                if state.acceptance_revision != row['acceptance_revision']:
                    failure = 'REVISION_CONFLICT'
                elif failure is None:
                    for scope, fresh in evidence.items():
                        try:
                            current = self.__current(scope, self.__clock())
                            failure = self._valid(current,scope,self.__clock(),request.requested_at)
                            if failure is None and current != fresh:
                                failure = 'SAFETY_SOURCE_CHANGED'
                            if failure is None:
                                failure = self._valid(fresh,scope,self.__clock(),request.requested_at)
                        except Exception:
                            failure = 'SAFETY_UNAVAILABLE'
                        if failure: break
                result = 'CONFLICT' if failure == 'REVISION_CONFLICT' else 'REJECTED' if failure else 'APPLIED'
                mode = state.mode if failure else ControlMode.RUNNING
                reason = failure or 'FRESH_OWNER_RESUME'
            else:
                result, reason = 'APPLIED', 'RESTRICTIVE_APPLICATION'
                mode = ControlMode.KILLED if request.action == ControlAction.KILL or state.mode == ControlMode.KILLED else ControlMode.PAUSED

            sources = tuple(dict.fromkeys(s.source_id for e in evidence.values() for s in e.source_hashes))
            if len(sources) > 128:
                result, mode, reason, sources = 'REJECTED', state.mode, 'SAFETY_UNAVAILABLE', ()
            # Local checks can consume their own elapsed time; validate all freshness
            # once more immediately before opening the short SQLite transaction.
            if request.action == ControlAction.RESUME and result == 'APPLIED':
                for scope, fresh in evidence.items():
                    failure = self._valid(fresh,scope,self.__clock(),request.requested_at)
                    if failure:
                        result,mode,reason = 'REJECTED',state.mode,failure
                        break
            self.__capability.assert_owner()
            application = dict(application_id=str(uuid.uuid4()),request_id=request.request_id,
                revision=row['acceptance_revision'],mode=mode.value,applied_at=_stamp(self.__clock()),
                safety_evidence_ids_json=json.dumps(sources),result=result,reason_code=reason)
            with self.__store._connection(write=True,lock=lock) as conn:
                final = self.__store._effective(conn)
                if request.action == ControlAction.RESUME and final.acceptance_revision != row['acceptance_revision']:
                    application.update(result='CONFLICT',mode=final.mode.value,reason_code='REVISION_CONFLICT')
                if request.action == ControlAction.RESUME and application['result'] == 'APPLIED':
                    # SQLite acquisition and durable owner assertions may have waited.
                    for scope, fresh in evidence.items():
                        stale = self._valid(fresh,scope,self.__clock(),request.requested_at)
                        if stale:
                            application.update(result='REJECTED',mode=final.mode.value,reason_code=stale)
                            break
                application['applied_at'] = _stamp(self.__clock())
                conn.execute('INSERT INTO control_applications VALUES(?,?,?,?,?,?,?,?)',tuple(application.values()))
            return application
