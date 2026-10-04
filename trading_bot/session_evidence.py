"""Bounded owner-local, reviewed exact-date KRX session evidence. No network IO."""
from __future__ import annotations

from datetime import date, datetime
import json
import os
from pathlib import Path
import stat
from typing import Callable
from urllib.parse import urlsplit

from .service_config import protected_file
from .service_models import KST, SessionEligibility, SessionEvidence

MAX_BUNDLE_BYTES = 65536
_EXCHANGE_HOSTS = frozenset({'krx.co.kr', 'www.krx.co.kr', 'global.krx.co.kr', 'kind.krx.co.kr'})


def unknown_session(day: date, now: datetime) -> SessionEvidence:
    """Absence carries no session bounds and cannot grant permission."""
    return SessionEvidence(trading_date_kst=day, source_id='session-unknown',
        source_hash='0' * 64, source_url='unknown', notice_id='unknown',
        reviewed_at=now, reviewer='unknown', observed_at=now, effective_at=now,
        eligibility=SessionEligibility.UNKNOWN, continuous_open=None, continuous_close=None)


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('duplicate JSON field')
        value[key] = item
    return value


def _reviewed(evidence: SessionEvidence, day: date, now: datetime) -> bool:
    url = urlsplit(evidence.source_url)
    return (
        evidence.trading_date_kst == day
        and evidence.effective_at.astimezone(KST).date() == day
        and evidence.observed_at.astimezone(KST).date() == day
        and evidence.observed_at <= now
        and evidence.reviewed_at <= now
        and url.scheme == 'https' and url.hostname in _EXCHANGE_HOSTS
        and url.username is None and url.password is None and url.port in (None, 443)
        and bool(url.path.strip('/')) and not url.fragment
        and evidence.source_hash != '0' * 64
        and all(not item.lower().startswith(('synthetic', 'unknown', 'guessed'))
                for item in (evidence.source_id, evidence.notice_id, evidence.reviewer))
    )


def load_session_evidence(path: Path, requested_date: date,
                          clock: Callable[[], datetime]) -> SessionEvidence:
    """Read a single notice or {sessions: [...]} bundle, failing closed on uncertainty.

    Owner review attests the saved source digest; this loader does not fetch or
    authenticate remote content. Observation and effective coverage must be current
    exact-date facts. Duplicate notices are ambiguous even if one looks preferable.
    """
    now = clock()
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('session clock must be timezone-aware')
    unknown = unknown_session(requested_date, now)
    try:
        path = protected_file(Path(path))
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, encoding='utf-8') as file:
            info = os.fstat(file.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_mode & 0o077 or info.st_size > MAX_BUNDLE_BYTES):
                return unknown
            raw = file.read(MAX_BUNDLE_BYTES + 1)
        if len(raw.encode('utf-8')) > MAX_BUNDLE_BYTES:
            return unknown
        bundle = json.loads(raw, object_pairs_hook=_unique_object)
        if type(bundle) is not dict:
            return unknown
        rows = bundle.get('sessions') if set(bundle) == {'sessions'} else [bundle]
        if type(rows) is not list or not 1 <= len(rows) <= 366:
            return unknown
        notices = []
        for row in rows:
            if type(row) is not dict:
                return unknown
            row = dict(row)
            for alias, field in (('date', 'trading_date_kst'), ('content_hash', 'source_hash')):
                if alias in row:
                    if field in row:
                        return unknown
                    row[field] = row.pop(alias)
            # JSON decoding validates aware datetime strings against the shared model.
            notice = SessionEvidence.model_validate_json(json.dumps(row))
            if notice.trading_date_kst == requested_date:
                notices.append(notice)
        if len(notices) != 1 or not _reviewed(notices[0], requested_date, now):
            return unknown
        return notices[0]
    except (OSError, ValueError, TypeError, RecursionError):
        return unknown


class SessionEvidenceProvider:
    """Re-read saved authority on every observation; no permanent UNKNOWN cache."""
    def __init__(self, path: Path, clock: Callable[[], datetime]):
        self.path = Path(path)
        self.clock = clock

    def for_date(self, requested_date: date) -> SessionEvidence:
        return load_session_evidence(self.path, requested_date, self.clock)

    def __call__(self, requested_date: date) -> SessionEvidence:
        return self.for_date(requested_date)
