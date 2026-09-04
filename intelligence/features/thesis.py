"""Deterministic thesis-fit features (spec §12).

V0 uses keyword/topic overlap between a person's text corpus (headline, employer names,
employer sectors, location) and the active ``ThesisConfiguration``. The similarity score,
the matched keywords, and (later) the embedding model/version are all stored so the number
is explainable — embedding similarity is ``unknown`` until an embedding provider is
configured (never silently 0).
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from intelligence.models import Employment, Organization, ThesisConfiguration

_WORD = re.compile(r"[a-z0-9][a-z0-9+.#-]*")


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def _phrase_hits(corpus: str, phrases: list[str]) -> list[str]:
    low = corpus.lower()
    return [p for p in phrases if p.lower() in low]


def active_thesis(session: Session) -> ThesisConfiguration | None:
    return (
        session.execute(select(ThesisConfiguration).where(ThesisConfiguration.active.is_(True)))
        .scalars()
        .first()
    )


def person_corpus(
    session: Session, person_id: uuid.UUID, headline: str | None, location: str | None
) -> str:
    parts: list[str] = [headline or "", location or ""]
    for org in session.execute(
        select(Organization)
        .join(Employment, Employment.organization_id == Organization.id)
        .where(Employment.person_id == person_id)
    ).scalars():
        parts.append(org.canonical_name)
        attrs = org.attributes or {}
        parts += [str(v) for v in attrs.get("sectors", [])]
        parts.append(str(attrs.get("sector", "")))
    return " . ".join(p for p in parts if p)


def dimension_match(corpus: str, phrases: list[str]) -> tuple[float, list[str]]:
    if not phrases:
        return 0.0, []
    hits = _phrase_hits(corpus, phrases)
    # also credit single-token overlaps for multi-word phrases
    if not hits:
        ctoks = _tokens(corpus)
        token_hits = [p for p in phrases if _tokens(p) & ctoks]
        hits = token_hits
    score = min(1.0, len(set(hits)) / max(1, min(len(phrases), 4)))
    return round(score, 4), sorted(set(hits))


def portfolio_adjacency(session: Session, corpus: str) -> tuple[float, list[str]]:
    sectors: set[str] = set()
    for org in session.execute(
        select(Organization).where(Organization.is_portfolio.is_(True))
    ).scalars():
        attrs = org.attributes or {}
        for s in attrs.get("sectors", []):
            sectors.add(str(s).lower())
        if attrs.get("sector"):
            sectors.add(str(attrs["sector"]).lower())
    if not sectors:
        return 0.0, []
    low = corpus.lower()
    hits = sorted(s for s in sectors if s and s in low)
    return (min(1.0, len(hits) / max(1, min(len(sectors), 3))), hits)
