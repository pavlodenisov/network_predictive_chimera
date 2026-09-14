"""Live web-search source (spec addendum — "web search that helps us know what new
founders, LPs, and potential team members we need to be in contact with").

Backed by the Tavily search API (https://tavily.com) — a real, third-party search
index. Disabled cleanly (``health_check`` -> ``disabled``, empty lists from both
methods) when ``TAVILY_API_KEY`` is not set; it never raises and never scrapes
(spec §5, §39, CLAUDE.md #11).

Two query modes:

``update_known_entities``
    One targeted query per already-monitored person (``"<name>" (raise OR funding
    OR ...)``), producing ``NEWS_ARTICLE`` observations attributed to that person —
    the same free-text extraction path as ``RSSNewsSource``, just backed by a live,
    query-driven search instead of a static feed.

``discover``
    One query per active ``DiscoveryRule`` with ``titles`` configured, scoped to
    ``site:linkedin.com/in`` so the search index's own results can surface a named
    candidate. This never contacts linkedin.com — it only reads the title/url the
    search API's own crawl already returned, the same way a Google result card shows
    a LinkedIn profile today. A candidate's name is read from the search index's own
    title metadata (``"<Name> - <headline> | LinkedIn"``) via a strict, deterministic
    parse (`_parse_linkedin_name`); a result that doesn't cleanly match is skipped
    rather than guessed at — an unnamed lead is better than a fabricated identity.

Every draft keeps its live ``source_url``; nothing here is generated.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import UTC, date, datetime

import httpx

from intelligence.config import get_settings
from intelligence.ingestion.adapters.base import PersonRef, RawObservationDraft, SourceHealth
from intelligence.models.discovery import DiscoveryRule
from intelligence.models.enums import ContentType, SourceHealthStatus, SourceType

_TAVILY_URL = "https://api.tavily.com/search"
_TIMEOUT = 10.0

# A search index's title for a LinkedIn profile page is consistently
# "<Name> - <headline> | LinkedIn" or "<Name> | LinkedIn" — never free text we'd have
# to guess at. Anything that doesn't match this shape is left alone.
_LINKEDIN_TITLE = re.compile(r"^(?P<name>.+?)\s*\|\s*LinkedIn\s*$", re.IGNORECASE)
_NAME_WORD = re.compile(r"^[A-Z][A-Za-z.'-]*$")


def _parse_linkedin_name(title: str, url: str) -> str | None:
    """Strict, deterministic name parse from a LinkedIn search-result title. Returns
    ``None`` (never a guess) unless the title cleanly matches the expected shape."""
    if "linkedin.com/in/" not in url:
        return None
    m = _LINKEDIN_TITLE.match((title or "").strip())
    if not m:
        return None
    candidate = m.group("name").split(" - ")[0].strip()
    words = candidate.split()
    if not (1 < len(words) <= 5):
        return None
    if not all(_NAME_WORD.match(w) for w in words):
        return None
    return candidate


def _linkedin_query(rule: DiscoveryRule) -> str | None:
    """Only issued when a rule names specific titles — an untargeted LinkedIn
    query would just be a generic scan, not a rule-driven discovery signal."""
    if not rule.titles:
        return None
    parts = [f"site:linkedin.com/in ({' OR '.join(f'{t!r}' for t in rule.titles[:5])})"]
    if rule.geographies:
        parts.append(f"({' OR '.join(f'{g!r}' for g in rule.geographies[:5])})")
    return " ".join(parts)


def _parse_published(value: object) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        return None


def _draft_from_result(result: dict, *, subject_hint: str, query: str) -> RawObservationDraft:
    title = result.get("title") or ""
    content = result.get("content") or ""
    url = result.get("url")
    return RawObservationDraft(
        provider_record_id=url,
        content_type=ContentType.NEWS_ARTICLE,
        subject_hint=subject_hint,
        occurred_at=_parse_published(result.get("published_date")),
        observed_at=datetime.now(tz=UTC),
        source_url=url,
        raw_text=f"{title}. {content}".strip(" ."),
        raw_json={"title": title, "content": content, "query": query},
        metadata={"query": query, "provider": "tavily"},
    )


def _tavily_search(query: str, *, api_key: str, max_results: int) -> list[dict]:
    resp = httpx.post(
        _TAVILY_URL,
        json={
            "api_key": api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    return list(results) if isinstance(results, list) else []


class WebSearchSource:
    source_name = "web_search"
    source_type = SourceType.WEB_SEARCH
    reliability_tier = 4  # secondary / aggregated reporting, same tier as RSS (spec §55)

    def __init__(
        self,
        api_key: str | None = None,
        max_results: int = 5,
        max_queries_per_run: int = 25,
    ) -> None:
        self._api_key = api_key if api_key is not None else get_settings().tavily_api_key
        self._max_results = max_results
        self._max_queries = max_queries_per_run
        self._queries_run = 0
        self._errors: list[str] = []

    @property
    def _enabled(self) -> bool:
        return bool(self._api_key)

    def _search(self, query: str) -> list[dict]:
        if self._queries_run >= self._max_queries:
            return []
        self._queries_run += 1
        try:
            assert self._api_key is not None  # guarded by `_enabled` at call sites
            return _tavily_search(query, api_key=self._api_key, max_results=self._max_results)
        except Exception as exc:  # noqa: BLE001 - degraded coverage, recorded not silent
            self._errors.append(f"{query!r}: {exc!r}")
            return []

    def update_known_entities(
        self, *, people: Sequence[PersonRef], as_of: date
    ) -> list[RawObservationDraft]:
        if not self._enabled:
            return []
        drafts: list[RawObservationDraft] = []
        ordered = sorted(people, key=lambda p: p.canonical_name)[: self._max_queries]
        for person in ordered:
            query = (
                f'"{person.canonical_name}" '
                '(raise OR funding OR stealth OR "new role" OR appointed OR joins OR promoted)'
            )
            for result in self._search(query):
                drafts.append(_draft_from_result(result, subject_hint=person.canonical_name, query=query))
        return drafts

    def discover(self, *, rules: Sequence[object], as_of: date) -> list[RawObservationDraft]:
        if not self._enabled:
            return []
        drafts: list[RawObservationDraft] = []
        for rule in rules:
            if not getattr(rule, "active", True):
                continue
            query = _linkedin_query(rule)  # type: ignore[arg-type]
            if query is None:
                continue
            for result in self._search(query):
                url = result.get("url") or ""
                name = _parse_linkedin_name(result.get("title") or "", url)
                if not name:
                    continue
                drafts.append(_draft_from_result(result, subject_hint=name, query=query))
        return drafts

    def health_check(self) -> SourceHealth:
        if not self._enabled:
            return SourceHealth(
                source_name=self.source_name,
                status=SourceHealthStatus.DISABLED,
                errors=["WebSearchSource is disabled: TAVILY_API_KEY not set."],
            )
        status = SourceHealthStatus.SUCCESSFUL if not self._errors else SourceHealthStatus.PARTIAL
        return SourceHealth(
            source_name=self.source_name,
            status=status,
            records=self._queries_run,
            errors=list(self._errors),
        )
