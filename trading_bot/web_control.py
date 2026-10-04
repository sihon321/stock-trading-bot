"""Fixed installation control requests, without service or trading authority."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import sqlite3
from uuid import UUID

from .control_store import control_request_capabilities
from .service_models import ControlRequest, InstallationScope, ServiceScope
from .web_config import ControlResourceDescriptor
from .web_evidence import _clean

ACTIONS = {'pause': 'PAUSE', 'resume': 'RESUME', 'kill': 'KILL'}
FIELDS = {'csrf_token', 'request_id', 'expected_revision', 'note'}


@dataclass(frozen=True)
class WebControlResult:
    status: str
    request_id: str
    acceptance_revision: int | None
    reason_code: str
    audit_pending: bool = False


class WebControlRequestService:
    def __init__(self, descriptor, *, clock=None):
        if not isinstance(descriptor, ControlResourceDescriptor):
            raise TypeError('registered descriptor required')
        self.descriptor = descriptor
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.scope = InstallationScope(registered_scopes=tuple(ServiceScope(
            account_scope_hash=account, execution_target=target)
            for account, target in descriptor.registered_scopes))

    def snapshot(self, *, actor):
        reader, _ = control_request_capabilities(self.descriptor, actor=actor, clock=self.clock)
        return dict(state=reader.effective_state(), requests=reader.list_requests(limit=100),
            applications=reader.list_applications(limit=100), admissions=reader.list_admissions(limit=100))

    def append_request(self, action, form, *, actor, audit):
        if action not in ACTIONS or set(form) - FIELDS or any(len(form.getlist(k)) != 1 for k in form):
            raise ValueError('invalid fields')
        request_id, revision, note = form.get('request_id', ''), form.get('expected_revision', ''), form.get('note', '')
        if (str(UUID(request_id)) != request_id or not revision.isascii() or not revision.isdecimal()
                or len(revision) > 12 or len(note) > 500):
            raise ValueError('invalid request')
        expected = int(revision)
        reader, writer = control_request_capabilities(self.descriptor, actor=actor, clock=self.clock)
        try:
            original = reader.get_request(request_id)
            # Reuse committed server time; a later browser replay cannot change its identity.
            control = ControlRequest(request_id=request_id, actor=actor,
                requested_at=original.requested_at if original else self.clock(), scope=self.scope,
                action=ACTIONS[action], expected_revision=expected)
            result = writer.append_request(control)
        except (OSError, ValueError, sqlite3.Error):
            return WebControlResult('UNAVAILABLE', request_id, None, 'STORAGE_UNAVAILABLE')
        if result.status != 'REQUESTED':
            return WebControlResult(result.status, request_id, result.acceptance_revision, result.reason_code)
        try:
            audit(actor=actor, resource_id=self.descriptor.resource_id, request_id=request_id,
                accepted_revision=result.acceptance_revision, at=control.requested_at, note=_clean(note))
        except (OSError, ValueError, sqlite3.Error):
            return WebControlResult('REQUESTED', request_id, result.acceptance_revision,
                'WEB_AUDIT_PENDING', audit_pending=True)
        return WebControlResult('REQUESTED', request_id, result.acceptance_revision, result.reason_code)
