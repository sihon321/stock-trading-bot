"""Thread-safe shared pacing for a single KIS API credential set."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class KisRequestLimiter:
    """Serialize requests so all KIS endpoints respect one minimum interval."""

    def __init__(
        self,
        min_interval_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._interval = max(0.0, float(min_interval_seconds))
        self._clock = clock
        self._sleeper = sleeper
        self._last_request_at: float | None = None
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            if self._last_request_at is not None:
                remaining = self._interval - (self._clock() - self._last_request_at)
                if remaining > 0:
                    self._sleeper(remaining)
            self._last_request_at = self._clock()
