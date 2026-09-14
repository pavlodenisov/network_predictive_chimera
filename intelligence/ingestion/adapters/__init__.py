"""Adapter registry. ``get_enabled_adapters`` maps ``source`` rows to adapter instances."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from intelligence.ingestion.adapters.base import (
    DisabledAdapter,
    PersonRef,
    RawObservationDraft,
    SourceAdapter,
    SourceHealth,
)
from intelligence.ingestion.adapters.json_snapshot import JSONSnapshotSource
from intelligence.ingestion.adapters.manual_csv import ManualCSVSource
from intelligence.ingestion.adapters.rss_news import RSSNewsSource
from intelligence.ingestion.adapters.stubs import (
    STUB_ADAPTERS,
    CRMSource,
    CrunchbaseSource,
    GitHubSource,
    LinkedInSnapshotSource,
    PitchBookSource,
)
from intelligence.ingestion.adapters.synthetic import SyntheticSource
from intelligence.ingestion.adapters.web_search import WebSearchSource
from intelligence.models import Source

#: adapter classes keyed by ``source.provider`` / ``source.name``.
ADAPTER_CLASSES: dict[str, type] = {
    "synthetic": SyntheticSource,
    "json_snapshot": JSONSnapshotSource,
    "manual_csv": ManualCSVSource,
    "rss_news": RSSNewsSource,
    "web_search": WebSearchSource,
    "linkedin_snapshot": LinkedInSnapshotSource,
    "crm": CRMSource,
    "crunchbase": CrunchbaseSource,
    "pitchbook": PitchBookSource,
    "github": GitHubSource,
}

#: real (non-stub) adapters. `web_search` still no-ops cleanly without TAVILY_API_KEY.
WORKING_ADAPTERS = ("synthetic", "json_snapshot", "manual_csv", "rss_news", "web_search")


def build_adapter(provider: str, configuration: dict | None = None) -> Any:
    """Returns a source-adapter instance (structurally a ``SourceAdapter``) or ``None``."""
    cls = ADAPTER_CLASSES.get(provider)
    if cls is None:
        return None
    cfg = configuration or {}
    if provider == "rss_news":
        return RSSNewsSource(feed_urls=cfg.get("feed_urls"))
    if provider == "web_search":
        return WebSearchSource(
            max_results=cfg.get("max_results", 5),
            max_queries_per_run=cfg.get("max_queries_per_run", 25),
        )
    return cls()


def get_enabled_adapters(session: Session) -> list[tuple[Source, Any]]:
    """Return ``(source_row, adapter_instance)`` for every enabled source with a known adapter."""
    pairs: list[tuple[Source, Any]] = []
    for src in session.execute(select(Source).where(Source.enabled.is_(True))).scalars():
        adapter = build_adapter(src.provider, src.configuration)
        if adapter is not None:
            pairs.append((src, adapter))
    return pairs


__all__ = [
    "ADAPTER_CLASSES",
    "STUB_ADAPTERS",
    "WORKING_ADAPTERS",
    "CRMSource",
    "CrunchbaseSource",
    "DisabledAdapter",
    "GitHubSource",
    "JSONSnapshotSource",
    "LinkedInSnapshotSource",
    "ManualCSVSource",
    "PersonRef",
    "PitchBookSource",
    "RSSNewsSource",
    "RawObservationDraft",
    "SourceAdapter",
    "SourceHealth",
    "SyntheticSource",
    "WebSearchSource",
    "build_adapter",
    "get_enabled_adapters",
]
