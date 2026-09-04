"""Content hashing + syndicated-news story clustering (spec §5, §26)."""

from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from intelligence.ingestion.adapters.base import RawObservationDraft
from intelligence.models import RawObservation, StoryCluster
from intelligence.observability import now_utc

_WORD = re.compile(r"[a-z0-9]+")
# Common headline filler that carries no clustering signal — syndicated rewrites of the
# same story routinely add/drop these words.
_TITLE_STOP = frozenset(
    [
        "the",
        "a",
        "an",
        "of",
        "to",
        "in",
        "on",
        "for",
        "and",
        "or",
        "with",
        "is",
        "are",
        "as",
        "at",
        "by",
        "from",
        "into",
        "over",
        "after",
        "new",
        "round",
        "report",
        "says",
        "say",
        "said",
        "announces",
        "announce",
        "announced",
        "reveals",
        "unveils",
        "update",
        "startup",
        "company",
        "firm",
        "inc",
        "llc",
        "ltd",
        "exclusive",
        "breaking",
        "today",
        "this",
        "week",
        "amid",
    ]
)


def content_hash(draft: RawObservationDraft) -> str:
    payload = {
        "content_type": str(draft.content_type),
        "subject_hint": (draft.subject_hint or "").strip().lower(),
        "source_url": (draft.source_url or "").strip().lower(),
        "raw_text": (draft.raw_text or "").strip(),
        "raw_json": draft.raw_json or {},
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def story_cluster_key(*parts: str | None) -> str:
    tokens: list[str] = []
    for p in parts:
        if not p:
            continue
        tokens += [w for w in _WORD.findall(p.lower()) if w not in _TITLE_STOP and len(w) > 2]
    sig = " ".join(sorted(set(tokens))[:12])
    return hashlib.sha1(sig.encode("utf-8")).hexdigest()  # noqa: S324 - non-crypto bucket key


def _domain(url: str | None) -> str | None:
    if not url:
        return None
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host or None


def assign_story_cluster(session: Session, observation: RawObservation) -> StoryCluster | None:
    """Group near-duplicate syndicated articles. Independent-source confidence downstream
    uses ``distinct_domain_count`` — never article count."""
    if str(observation.content_type) != "news_article":
        return None
    rj = observation.raw_json or {}
    key = story_cluster_key(rj.get("title"), observation.subject_hint, rj.get("summary"))
    cluster = session.execute(
        select(StoryCluster).where(StoryCluster.cluster_key == key)
    ).scalar_one_or_none()
    if cluster is None:
        cluster = StoryCluster(
            cluster_key=key,
            canonical_url=observation.source_url,
            first_seen_at=observation.observed_at or now_utc(),
            article_count=0,
            distinct_domain_count=0,
        )
        session.add(cluster)
        session.flush()

    observation.story_cluster_id = cluster.id
    cluster.article_count += 1
    domains = {
        _domain(o.source_url)
        for o in session.execute(
            select(RawObservation).where(RawObservation.story_cluster_id == cluster.id)
        ).scalars()
    }
    domains.discard(None)
    cluster.distinct_domain_count = max(1, len(domains))
    session.flush()
    return cluster
