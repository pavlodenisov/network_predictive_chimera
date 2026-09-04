"""RSS / public-news source (spec §26, §48).

OFFLINE BY DEFAULT: parses local feeds in ``<seeds_dir>/news/*.xml``. Set
``CHIMERA_RSS_LIVE=1`` and provide feed URLs in the source configuration to fetch live
feeds with ``httpx`` (respecting each feed's terms). A news article may mention several
entities; near-duplicate syndicated articles are grouped into a ``story_cluster`` by the
dedup stage — independent-source confidence uses distinct domains, not article count.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

import feedparser

from intelligence.config import get_settings
from intelligence.ingestion.adapters.base import PersonRef, RawObservationDraft, SourceHealth
from intelligence.models.enums import ContentType, SourceHealthStatus, SourceType


class RSSNewsSource:
    source_name = "rss_news"
    source_type = SourceType.RSS
    reliability_tier = 4  # secondary reporting by default

    def __init__(
        self, seeds_dir: Path | str | None = None, feed_urls: Sequence[str] | None = None
    ) -> None:
        base = Path(seeds_dir) if seeds_dir else get_settings().seeds_dir
        self._dir = base / "news"
        self._feed_urls = list(feed_urls or [])
        self._live = get_settings().rss_live
        self._errors: list[str] = []

    # ------------------------------------------------------------------ parsing
    def _entries(self, as_of: date) -> list[RawObservationDraft]:
        cutoff = datetime(as_of.year, as_of.month, as_of.day, 23, 59, 59, tzinfo=UTC)
        drafts: list[RawObservationDraft] = []
        sources: list[tuple[str, object]] = []

        if self._live and self._feed_urls:
            import httpx

            for url in self._feed_urls:
                try:
                    sources.append((url, httpx.get(url, timeout=10.0).text))
                except Exception as exc:  # noqa: BLE001 - degraded coverage, recorded
                    self._errors.append(f"{url}: {exc!r}")
        else:
            for path in sorted(self._dir.glob("*.xml")) if self._dir.exists() else []:
                sources.append((path.name, path.read_text()))

        for origin, blob in sources:
            parsed = feedparser.parse(blob)
            for e in parsed.entries:
                published = _entry_dt(e) or cutoff
                if published > cutoff:
                    continue
                link = getattr(e, "link", None)
                summary = getattr(e, "summary", "") or ""
                title = getattr(e, "title", "") or ""
                drafts.append(
                    RawObservationDraft(
                        provider_record_id=getattr(e, "id", None) or link or f"{origin}:{title}",
                        content_type=ContentType.NEWS_ARTICLE,
                        subject_hint=_subject_hint(e),
                        occurred_at=published,
                        observed_at=published,
                        source_url=link,
                        raw_text=f"{title}. {summary}".strip(),
                        raw_json={
                            "title": title,
                            "summary": summary,
                            "feed": origin,
                            "subjects": _subjects(e),
                        },
                        metadata={"feed": origin},
                    )
                )
        return drafts

    def discover(self, *, rules: Sequence[object], as_of: date) -> list[RawObservationDraft]:
        # news is a discovery channel: every article is a candidate mention
        return self._entries(as_of)

    def update_known_entities(
        self, *, people: Sequence[PersonRef], as_of: date
    ) -> list[RawObservationDraft]:
        names = {p.canonical_name.lower() for p in people}
        return [
            d
            for d in self._entries(as_of)
            if (d.subject_hint or "").lower() in names
            or any(s.lower() in names for s in (d.raw_json or {}).get("subjects", []))
        ]

    def health_check(self) -> SourceHealth:
        available = len(list(self._dir.glob("*.xml"))) if self._dir.exists() else 0
        live_ok = not self._live or bool(self._feed_urls)
        status = SourceHealthStatus.SUCCESSFUL
        if self._errors:
            status = SourceHealthStatus.PARTIAL
        if not available and not (self._live and self._feed_urls):
            status = SourceHealthStatus.PARTIAL
        return SourceHealth(
            source_name=self.source_name,
            status=status,
            records=available,
            errors=self._errors or ([] if live_ok else ["live mode set but no feed_urls"]),
        )


def _entry_dt(entry: object) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        tm = getattr(entry, attr, None)
        if tm:
            y, mo, d, h, mi, s = (int(x) for x in tm[:6])
            return datetime(y, mo, d, h, mi, s, tzinfo=UTC)
    for attr in ("published", "updated"):
        raw = getattr(entry, attr, None)
        if raw:
            try:
                dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
            except ValueError:
                continue
    return None


def _subjects(entry: object) -> list[str]:
    tags = getattr(entry, "tags", None) or []
    out: list[str] = []
    for t in tags:
        term = t.get("term") if isinstance(t, dict) else None
        if term:
            out.append(str(term))
    return out


def _subject_hint(entry: object) -> str | None:
    subs = _subjects(entry)
    return subs[0] if subs else None
