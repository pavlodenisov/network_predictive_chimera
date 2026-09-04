"""Connector V0.1 feature builder (spec §17; docs/SCORING.md §6). Keys match
``configs/models/connector_v0.1.yaml``. Vanity metrics (follower counts) are NOT features.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from intelligence.features.base import FeatureBundle
from intelligence.models import (
    AnalystFeedback,
    Employment,
    Organization,
    Person,
    PersonClassification,
    RelationshipEdge,
)
from intelligence.models.enums import PersonClass
from intelligence.observability import days_between, ensure_utc

MODEL_TARGET = "connector"

_RELEVANT_CLASSES = {
    PersonClass.FOUNDER,
    PersonClass.POTENTIAL_FOUNDER,
    PersonClass.LP,
    PersonClass.POTENTIAL_LP,
    PersonClass.PORTFOLIO_EXECUTIVE,
}


def build(session: Session, person_id: uuid.UUID, as_of: datetime) -> FeatureBundle:
    bundle = FeatureBundle(model_target=MODEL_TARGET, as_of=as_of)

    known_since = func.coalesce(RelationshipEdge.first_seen_at, RelationshipEdge.created_at)
    edges = list(
        session.execute(
            select(RelationshipEdge).where(
                or_(
                    RelationshipEdge.source_person_id == person_id,
                    RelationshipEdge.target_person_id == person_id,
                ),
                known_since <= ensure_utc(as_of),
            )
        ).scalars()
    )
    neighbour_ids = {
        e.target_person_id if e.source_person_id == person_id else e.source_person_id for e in edges
    }
    neighbour_ids.discard(person_id)

    classes_by_person = _classes(session, neighbour_ids)
    founder_n = _count(classes_by_person, {PersonClass.FOUNDER, PersonClass.POTENTIAL_FOUNDER})
    lp_n = _count(classes_by_person, {PersonClass.LP, PersonClass.POTENTIAL_LP})
    portfolio_n = _portfolio_count(session, neighbour_ids, classes_by_person)
    relevant_n = sum(
        1 for pid in neighbour_ids if classes_by_person.get(pid, set()) & _RELEVANT_CLASSES
    )

    bundle.known("relevant_connections", relevant_n, "count", [])
    bundle.known("founder_connectivity", founder_n, "count", [])
    bundle.known("lp_connectivity", lp_n, "count", [])
    bundle.known("portfolio_connectivity", portfolio_n, "count", [])

    # independent Chimera -> X paths this person bridges (first-hop distinct)
    chimera_neighbours = {
        pid
        for pid in neighbour_ids
        if (p := session.get(Person, pid)) is not None and p.is_chimera_seed
    }
    bundle.known("independent_path_count", len(chimera_neighbours), "count", [])

    # distinct sectors among connections
    sectors: set[str] = set()
    for pid in neighbour_ids:
        for org in session.execute(
            select(Organization)
            .join(Employment, Employment.organization_id == Organization.id)
            .where(Employment.person_id == pid, Employment.current.is_(True))
        ).scalars():
            attrs = org.attributes or {}
            sectors.add(str(attrs.get("sector", "")).lower())
            for s in attrs.get("sectors", []):
                sectors.add(str(s).lower())
    sectors.discard("")
    bundle.known("distinct_sectors", len(sectors), "count", [])

    # relationship freshness: share of this person's edges verified within 365d
    if not edges:
        bundle.unknown("fresh_edge_share")
    else:
        fresh = 0
        for e in edges:
            age = days_between(ensure_utc(e.last_verified_at), ensure_utc(as_of))
            if age is not None and age <= 365:
                fresh += 1
        bundle.known("fresh_edge_share", round(fresh / len(edges), 4), "unit", [])

    # successful intros credited to this person
    intros = session.scalar(
        select(func.count())
        .select_from(AnalystFeedback)
        .where(
            AnalystFeedback.connector_person_id == person_id,
            AnalystFeedback.feedback_type.in_(["INTRO_COMPLETED", "MEETING_BOOKED"]),
        )
    )
    bundle.known("successful_intros", int(intros or 0), "count", [])

    return bundle


def _classes(session: Session, person_ids: set[uuid.UUID]) -> dict[uuid.UUID, set[str]]:
    if not person_ids:
        return {}
    out: dict[uuid.UUID, set[str]] = {}
    for row in session.execute(
        select(PersonClassification).where(PersonClassification.person_id.in_(person_ids))
    ).scalars():
        out.setdefault(row.person_id, set()).add(row.person_class)
    return out


def _count(classes_by_person: dict[uuid.UUID, set[str]], wanted: set[str]) -> int:
    return sum(1 for cs in classes_by_person.values() if cs & wanted)


def _portfolio_count(
    session: Session, person_ids: set[uuid.UUID], classes_by_person: dict[uuid.UUID, set[str]]
) -> int:
    n = _count(classes_by_person, {PersonClass.PORTFOLIO_EXECUTIVE})
    for pid in person_ids:
        is_portfolio_emp = session.scalar(
            select(func.count())
            .select_from(Employment)
            .join(Organization, Organization.id == Employment.organization_id)
            .where(Employment.person_id == pid, Organization.is_portfolio.is_(True))
        )
        if is_portfolio_emp:
            n += 1
    return n
