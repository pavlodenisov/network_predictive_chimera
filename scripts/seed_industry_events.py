"""``python -m scripts.seed_industry_events`` — load real, sourced ecosystem events.

Every entry below was verified by live web search (see the commit that introduced this
file for the queries run) against the event's own listing page. Nothing is generated:
each row's `source_url` is the primary source, and dates/venues are copied verbatim from
it. Idempotent on `(name, starts_at)`.

This is a **snapshot, not a live feed** — re-run this after doing fresh research to keep
it current, or wire `intelligence.ingestion.adapters.web_search.WebSearchSource` (spec
addendum) into the weekly pipeline once a real search-API key is configured, which
populates this table automatically from `DiscoveryRule` geographies/keywords.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from intelligence.db import session_scope
from intelligence.models import IndustryEvent
from intelligence.observability import get_logger, now_utc

log = get_logger("chimera.seed_industry_events")

# name, description, city, country, venue, starts_at, ends_at, topics, source_url, source_label
_EVENTS: list[dict] = [
    {
        "name": "Bengaluru 2026 Venture Capital World Summit",
        "description": (
            "Regional edition of the Venture Capital World Summit series — investor and "
            "founder networking focused on the Indian startup ecosystem."
        ),
        "city": "Bengaluru",
        "country": "India",
        "venue": "WeWork Prestige Central, Infantry Road, Bengaluru",
        "starts_at": datetime(2026, 10, 7, 13, 0, tzinfo=UTC),
        "ends_at": datetime(2026, 10, 7, 18, 0, tzinfo=UTC),
        "topics": ["venture capital", "founders", "networking"],
        "source_url": "https://vcworldsummit.com/tickets/bengaluru-2026/",
        "source_label": "Venture Capital World Summit — official listing",
    },
    {
        "name": "New Delhi 2026 Venture Capital World Summit",
        "description": (
            "Regional edition of the Venture Capital World Summit series — investor and "
            "founder networking focused on the Indian startup ecosystem."
        ),
        "city": "New Delhi",
        "country": "India",
        "venue": (
            "CorporatEdge World Trade Center, Tower E, Nauroji Nagar, "
            "Safdarjung Enclave, New Delhi"
        ),
        "starts_at": datetime(2026, 10, 9, 13, 0, tzinfo=UTC),
        "ends_at": datetime(2026, 10, 9, 18, 0, tzinfo=UTC),
        "topics": ["venture capital", "founders", "networking"],
        "source_url": "https://vcworldsummit.com/tickets/new-delhi-2026/",
        "source_label": "Venture Capital World Summit — official listing",
    },
    {
        "name": "Bengaluru Tech Summit 2026",
        "description": (
            "29th edition; theme 'AI & Beyond'. Asia-focused technology and innovation "
            "summit — industry leaders, researchers, startups, investors, and "
            "policymakers; reported 1,600+ exhibitors including 1,000+ startups and "
            "25+ unicorns/VCs."
        ),
        "city": "Bengaluru",
        "country": "India",
        "venue": "Bangalore International Exhibition Centre (BIEC)",
        "starts_at": datetime(2026, 11, 17, tzinfo=UTC),
        "ends_at": datetime(2026, 11, 19, tzinfo=UTC),
        "topics": ["technology", "AI", "startups", "venture capital"],
        "source_url": "https://www.bengalurutechsummit.com/",
        "source_label": "Bengaluru Tech Summit — official site",
    },
]


def seed_industry_events() -> int:
    created = 0
    with session_scope() as session:
        for row in _EVENTS:
            exists = session.execute(
                select(IndustryEvent).where(
                    IndustryEvent.name == row["name"],
                    IndustryEvent.starts_at == row["starts_at"],
                )
            ).scalar_one_or_none()
            if exists:
                continue
            session.add(IndustryEvent(retrieved_at=now_utc(), added_by="manual_research", **row))
            created += 1
    log.info("industry_events.seeded", created=created, total=len(_EVENTS))
    return created


def main() -> int:
    n = seed_industry_events()
    print(f"Industry events: {n} added ({len(_EVENTS)} total known).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
