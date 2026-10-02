"""Dedicated local password and authoritative, non-sliding operator sessions."""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import re
import secrets
from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from .web_store import Session, WebStore, identifier, timestamp

SCRYPT_METHOD = 'scrypt:131072:8:1'
_TOKEN = re.compile(r'[a-zA-Z0-9_-]{43}\Z')


def _password(value: str) -> str:
    if not isinstance(value, str) or not 12 <= len(value) <= 1024:
        raise ValueError('operator password must have 12 to 1024 characters')
    return value


def hash_password(password: str) -> str:
    return generate_password_hash(_password(password), method=SCRYPT_METHOD, salt_length=16)


def _reference(token) -> str | None:
    if not isinstance(token, str) or not _TOKEN.fullmatch(token):
        return None
    return hashlib.sha256(token.encode('ascii')).hexdigest()


class WebAuth:
    """Flask stores only the returned opaque token; server rows remain authoritative."""
    def __init__(self, store: WebStore, *, clock=None, hasher=hash_password,
                 verifier=check_password_hash):
        self.store = store
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.hasher, self.verifier = hasher, verifier
        # Equal-cost verification for unknown accounts; never a stored operator credential.
        self._dummy_hash = hasher(secrets.token_urlsafe(32))

    def _now(self):
        at = self.clock()
        timestamp(at)
        return at

    def provision_operator(self, username: str, password: str):
        identifier(username)
        self.store.provision_operator(username, self.hasher(_password(password)), self._now())

    def reset_password(self, password: str):
        """Only the local CLI calls this; no HTTP password reset route is provided."""
        password_hash = self.hasher(_password(password))
        operator = self.store.get_operator()
        if operator is None:
            raise ValueError('operator provisioning required')
        self.store.provision_operator(operator.username, password_hash, self._now(), reset=True)

    def authenticate(self, username: str, password: str, source_address: str) -> str | None:
        at = self._now()
        if (not isinstance(username, str) or len(username) > 64
                or not isinstance(password, str) or len(password) > 1024):
            return None
        try:
            address = str(ipaddress.ip_address(source_address))
        except (ValueError, TypeError):
            return None
        token = secrets.token_urlsafe(32)

        def verify(operator):
            hashed = self._dummy_hash if operator is None else operator.password_hash
            try:
                matched = self.verifier(hashed, password)
            except (ValueError, TypeError):
                matched = False
            identity = operator is not None and hmac.compare_digest(
                operator.username.encode(), username.encode())
            return bool(matched and identity)

        # Password verification and session issuance share one writer transaction.
        # A concurrent local reset cannot issue a new session from the previous hash.
        result = self.store.login_attempt(username, address, at, verify,
                                          session_reference_hash=_reference(token))
        return token if result == 'SUCCESS' else None

    def validate_session(self, token) -> Session | None:
        reference = _reference(token)
        if reference is None:
            return None
        session = self.store.get_session(reference)
        now = self._now()
        if (session is None or session.revoked_at is not None
                or not session.issued_at <= now < session.expires_at):
            return None
        return session

    def logout(self, token):
        reference = _reference(token)
        session = self.validate_session(token)
        if reference is not None and session is not None:
            at = self._now()
            self.store.revoke_session(reference, at)
            self.store.append_action(actor=session.actor, action='LOGOUT', result_code='SUCCESS', at=at)
