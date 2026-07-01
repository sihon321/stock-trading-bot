"""Compliance-gated, fail-soft, sanitized Naver Finance news adapter (DATA-04).

This module is the ONLY place that fetches and parses Naver Finance per-ticker
news HTML. It exists to satisfy DATA-04 without letting scraping failures crash a
cycle or letting untrusted third-party text pollute the compact LLM context.

Contract (D-06/D-15, Plan 03-01 acceptable-use decision):

  - **Compliance-gated.** Network fetching is enabled only when the operator
    approved acceptable use in Plan 03-01 (``Settings.naver_news_enabled``).
    Naver Finance ``robots.txt`` disallows general crawlers, so the default is
    DISABLED. When disabled/unapproved the adapter returns empty rendered news
    with an UNAVAILABLE :class:`~trading_bot.data_models.SourceHealth` reason and
    never touches the network.
  - **Fail-soft.** HTTP 403/429/errors, network exceptions, encoding/decode
    errors, a missing expected DOM, parser failure, and malformed article rows
    all normalize to empty news plus source-health evidence — never a raised
    exception (threats T-03-05-D, T-03-05-R).
  - **Untrusted text.** Scraped HTML/news is treated as untrusted input for the
    later LLM phase: :func:`sanitize_news_text` strips tags/scripts/controls,
    collapses whitespace, and removes prompt-like instruction language, then caps
    per-item length. :func:`render_news_for_context` additionally caps item count
    (threat T-03-05-T). Structured :class:`NewsArticle` details stay internal;
    only capped sanitized STRINGS reach ``DataContext.news`` (D-04/D-06).

This adapter does NOT construct prompts, call an LLM, notify, or schedule.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, List, Optional, Sequence, Tuple

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

from trading_bot.data_models import SourceHealth, SourceStatus

_SOURCE = "naver_news"
_NEWS_URL = "https://finance.naver.com/item/news_news.naver"
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) trading-bot/1.0"
)

# Prompt-injection / instruction-like phrases stripped from untrusted news text
# before it can reach a later LLM phase (threat T-03-05-T). These are matched
# case-insensitively and removed; legitimate news content around them survives.
_PROMPT_INJECTION_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(previous|prior|above)\s+instructions", re.IGNORECASE),
    re.compile(r"forget\s+(all\s+)?(previous|prior|above)\s+instructions", re.IGNORECASE),
    re.compile(r"system\s+prompt", re.IGNORECASE),
    re.compile(r"act\s+as\s+(a\s+)?(system|assistant|developer)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+", re.IGNORECASE),
    re.compile(r"\bignore\s+the\s+above\b", re.IGNORECASE),
    re.compile(r"</?(system|assistant|user)>", re.IGNORECASE),
)

# Control characters (except common whitespace) removed as untrusted noise.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WHITESPACE = re.compile(r"\s+")


class _TransientNewsError(Exception):
    """Internal marker for retryable transient news-fetch failures."""


@dataclass(frozen=True)
class NewsArticle:
    """A structured, INTERNAL news article kept out of the compact LLM context.

    Only sanitized rendered strings derived from these articles ever reach
    ``DataContext.news`` (D-04/D-06); the raw structured details stay here.
    """

    title: str
    body: str = ""


@dataclass(frozen=True)
class NaverNewsResult:
    """Adapter result pairing internal articles, rendered strings, and health.

    ``rendered`` is always a tuple of capped, sanitized strings suitable for
    ``DataContext.news``. It is empty whenever news is disabled/unapproved or any
    source failure occurred, so a scraping problem degrades to "no news" rather
    than crashing the cycle.
    """

    articles: Tuple[NewsArticle, ...] = ()
    rendered: Tuple[str, ...] = ()
    health: SourceHealth = field(
        default_factory=lambda: SourceHealth(
            source=_SOURCE, status=SourceStatus.UNAVAILABLE, reason="uninitialized"
        )
    )


def _empty(reason: str, *, status: SourceStatus = SourceStatus.UNAVAILABLE) -> NaverNewsResult:
    return NaverNewsResult(
        articles=(),
        rendered=(),
        health=SourceHealth(source=_SOURCE, status=status, reason=reason),
    )


def sanitize_news_text(value: Any, *, max_chars: int) -> str:
    """Sanitize a single untrusted news string and cap its length.

    Strips HTML tags/scripts, control characters, and prompt-like instruction
    phrases, collapses whitespace, then truncates to ``max_chars``. A non-string
    or empty input yields ``""``. The result is safe to embed as delimited,
    untrusted context in a later LLM phase (threat T-03-05-T).
    """

    if not isinstance(value, str) or not value:
        return ""

    text = value
    # Drop entire <script>/<style> bodies before generic tag stripping so their
    # contents (e.g. JS) never survive as text.
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    # Strip any remaining HTML/XML tags.
    text = re.sub(r"<[^>]*>", " ", text)
    # Remove prompt-injection / instruction-like phrases.
    for pattern in _PROMPT_INJECTION_PATTERNS:
        text = pattern.sub(" ", text)
    # Remove control characters.
    text = _CONTROL_CHARS.sub(" ", text)
    # Collapse all whitespace runs to single spaces.
    text = _WHITESPACE.sub(" ", text).strip()

    if max_chars is not None and max_chars > 0 and len(text) > max_chars:
        text = text[:max_chars].rstrip()
    return text


def render_news_for_context(
    articles: Sequence[NewsArticle],
    *,
    max_items: int,
    max_chars: int,
) -> Tuple[str, ...]:
    """Render internal articles into capped, sanitized ``DataContext.news`` strings.

    Caps the number of items to ``max_items`` and sanitizes/caps each string to
    ``max_chars``. Blank results after sanitization are dropped. The output is a
    tuple of plain strings only — no article objects or raw HTML (D-04/D-06).
    """

    rendered: List[str] = []
    limit = max_items if (isinstance(max_items, int) and max_items > 0) else 0
    for article in articles:
        if limit and len(rendered) >= limit:
            break
        title = sanitize_news_text(getattr(article, "title", ""), max_chars=max_chars)
        body = sanitize_news_text(getattr(article, "body", ""), max_chars=max_chars)
        combined = title
        if body and body != title:
            combined = f"{title} {body}".strip() if title else body
            combined = combined[:max_chars].rstrip() if max_chars > 0 else combined
        if combined:
            rendered.append(combined)
    return tuple(rendered)


def parse_naver_news_html(html: str) -> List[NewsArticle]:
    """Parse Naver Finance item-news HTML into structured :class:`NewsArticle`.

    Isolates all BeautifulSoup/lxml DOM knowledge so a Naver layout change is a
    one-file fix. Raises :class:`_TransientNewsError` when the expected news
    container is absent or parsing fails, so the adapter can normalize it into
    empty news. Malformed individual rows are skipped, not fatal.
    """

    if not isinstance(html, str) or not html.strip():
        raise _TransientNewsError("empty news HTML")

    try:
        from bs4 import BeautifulSoup
    except Exception as exc:  # pragma: no cover - dependency guard.
        raise _TransientNewsError(f"news parser unavailable: {type(exc).__name__}") from None

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        # lxml missing/failed - fall back to the stdlib parser rather than crash.
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception as exc:
            raise _TransientNewsError(f"news HTML parse failed: {type(exc).__name__}") from None

    table = soup.find("table", class_="type5")
    if table is None:
        raise _TransientNewsError("expected news table not found")

    articles: List[NewsArticle] = []
    for cell in table.find_all("td", class_="title"):
        try:
            link = cell.find("a")
            text = (link.get_text() if link is not None else cell.get_text()) or ""
            title = text.strip()
        except Exception:
            # A malformed row is skipped, never fatal (fail-soft per row).
            continue
        if title:
            articles.append(NewsArticle(title=title))
    return articles


class NaverNewsAdapter:
    """Synchronous, compliance-gated Naver Finance news adapter.

    Args:
        enabled: Operator acceptable-use decision (``Settings.naver_news_enabled``).
            When ``False`` the adapter never fetches and returns empty news.
        max_items: Maximum rendered news strings (``Settings.naver_news_max_items``).
        max_chars: Per-item character cap (``Settings.naver_news_max_chars``).
        client: Object exposing ``get(url, *, params, headers, timeout)`` returning
            an ``httpx.Response``-like object with ``status_code`` and ``text``.
            Injectable for offline tests; created lazily only when enabled.
        timeout_seconds/max_retries/retry_backoff_seconds: bounded network controls.
    """

    def __init__(
        self,
        *,
        enabled: bool,
        max_items: int,
        max_chars: int,
        client: Any = None,
        timeout_seconds: float = 5.0,
        max_retries: int = 3,
        retry_backoff_seconds: float = 1.0,
    ) -> None:
        self._enabled = bool(enabled)
        self._max_items = max(0, int(max_items))
        self._max_chars = max(0, int(max_chars))
        self._client = client
        self._timeout_seconds = float(timeout_seconds)
        self._max_retries = max(1, int(max_retries))
        self._retry_backoff_seconds = max(0.0, float(retry_backoff_seconds))

    def __repr__(self) -> str:  # pragma: no cover - trivial.
        return f"NaverNewsAdapter(enabled={self._enabled})"

    def fetch_news(self, ticker: str) -> NaverNewsResult:
        """Fetch, parse, sanitize, and cap per-ticker news, failing soft on error.

        Returns empty news with source-health evidence when disabled/unapproved
        or on any HTTP/network/encoding/DOM/parse failure; never raises.
        """

        if not self._enabled:
            # Plan 03-01 acceptable-use decision keeps this disabled by default.
            return _empty("naver news disabled by acceptable-use policy")

        if not (isinstance(ticker, str) and len(ticker) == 6 and ticker.isdigit()):
            return _empty("ticker must be a 6-digit KRX code")

        try:
            html = self._fetch_html(ticker)
        except _TransientNewsError as exc:
            return _empty(str(exc))
        except Exception as exc:  # noqa: BLE001 - fail soft on any transport failure.
            return _empty(f"news fetch failed: {type(exc).__name__}")

        try:
            articles = parse_naver_news_html(html)
        except _TransientNewsError as exc:
            return _empty(str(exc))
        except Exception as exc:  # noqa: BLE001 - fail soft on any parse failure.
            return _empty(f"news parse failed: {type(exc).__name__}")

        rendered = render_news_for_context(
            articles, max_items=self._max_items, max_chars=self._max_chars
        )
        return NaverNewsResult(
            articles=tuple(articles),
            rendered=rendered,
            health=SourceHealth(source=_SOURCE, status=SourceStatus.AVAILABLE, reason="ok"),
        )

    def _client_instance(self) -> Any:
        if self._client is None:
            import httpx

            self._client = httpx.Client()
        return self._client

    def _fetch_html(self, ticker: str) -> str:
        @retry(
            reraise=True,
            stop=stop_after_attempt(self._max_retries),
            wait=wait_fixed(self._retry_backoff_seconds),
            retry=retry_if_exception_type(_TransientNewsError),
        )
        def _attempt() -> str:
            return self._request(ticker)

        return _attempt()

    def _request(self, ticker: str) -> str:
        client = self._client_instance()
        headers = {"User-Agent": _USER_AGENT}
        params = {"code": ticker}

        try:
            response = client.get(
                _NEWS_URL, params=params, headers=headers, timeout=self._timeout_seconds
            )
        except Exception as exc:  # noqa: BLE001 - transient transport failure.
            raise _TransientNewsError(f"news request failed: {type(exc).__name__}") from None

        status = getattr(response, "status_code", None)
        if status is None or int(status) >= 400:
            raise _TransientNewsError(f"news request returned HTTP {status}")

        try:
            text = response.text
        except UnicodeDecodeError:
            # Naver Finance is EUC-KR; a decode failure is terminal, not retryable.
            raise _TransientNewsError("news response decode failed") from None
        except Exception as exc:  # noqa: BLE001 - unexpected body access failure.
            raise _TransientNewsError(f"news response read failed: {type(exc).__name__}") from None

        if not isinstance(text, str) or not text.strip():
            raise _TransientNewsError("empty news response body")
        return text
