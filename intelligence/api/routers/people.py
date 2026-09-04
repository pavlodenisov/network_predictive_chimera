from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import or_, select

from intelligence.api.deps import PaginationDep, SessionDep
from intelligence.api.serializers import (
    evidence_detail,
    fact_detail,
    person_detail,
    person_row,
    relationship_row,
)
from intelligence.models import (
    Event,
    Evidence,
    Fact,
    Person,
    PersonClassification,
    PersonFeatureSnapshot,
    RelationshipEdge,
    ScoreSnapshot,
    ScoringModel,
)
from intelligence.observability import now_utc
from intelligence.repositories.base import apply_sort, paginate
from intelligence.scoring.access import compute_access

router = APIRouter(prefix="/people", tags=["people"])

_SORTABLE = {
    "name": Person.canonical_name,
    "created_at": Person.created_at,
    "last_observed_at": Person.last_observed_at,
}


@router.get("")
def list_people(
    session: SessionDep,
    page: PaginationDep,
    q: str | None = Query(None, description="name substring"),
    person_class: str | None = Query(None),
    monitoring_status: str | None = Query(None),
) -> dict:
    stmt = select(Person).where(Person.merged_into_id.is_(None))
    if q:
        stmt = stmt.where(Person.canonical_name.ilike(f"%{q}%"))
    if monitoring_status:
        stmt = stmt.where(Person.monitoring_status == monitoring_status)
    if person_class:
        stmt = stmt.where(
            Person.id.in_(
                select(PersonClassification.person_id).where(
                    PersonClassification.person_class == person_class
                )
            )
        )
    stmt = apply_sort(stmt, sort=page.sort, sortable=_SORTABLE, default="name")
    result = paginate(session, stmt, page=page.page, page_size=page.page_size)
    return result.as_dict(lambda p: person_row(session, p))


def _get_person(session, person_id: str) -> Person:
    try:
        pid = uuid.UUID(person_id)
    except ValueError as exc:
        raise HTTPException(422, "invalid person id") from exc
    person = session.get(Person, pid)
    if person is None:
        raise HTTPException(404, "person not found")
    return person


@router.get("/{person_id}")
def get_person(person_id: str, session: SessionDep) -> dict:
    return person_detail(session, _get_person(session, person_id))


@router.get("/{person_id}/events")
def person_events(person_id: str, session: SessionDep) -> dict:
    person = _get_person(session, person_id)
    from intelligence.api.serializers import event_summary

    rows = session.execute(
        select(Event)
        .where(Event.person_id == person.id)
        .order_by(Event.occurred_at.desc().nullslast(), Event.detected_at.desc())
    ).scalars()
    return {"items": [event_summary(session, e) for e in rows]}


@router.get("/{person_id}/evidence")
def person_evidence(person_id: str, session: SessionDep) -> dict:
    person = _get_person(session, person_id)
    fact_ids = select(Fact.id).where(Fact.subject_id == person.id)
    rows = session.execute(
        select(Evidence).where(Evidence.fact_id.in_(fact_ids)).order_by(Evidence.created_at.desc())
    ).scalars()
    return {"items": [evidence_detail(session, e) for e in rows]}


@router.get("/{person_id}/facts")
def person_facts(person_id: str, session: SessionDep) -> dict:
    person = _get_person(session, person_id)
    rows = session.execute(
        select(Fact)
        .where(Fact.subject_id == person.id)
        .order_by(Fact.fact_type, Fact.valid_from.desc().nullslast())
    ).scalars()
    return {"items": [fact_detail(session, f) for f in rows]}


@router.get("/{person_id}/scores")
def person_scores(person_id: str, session: SessionDep) -> dict:
    person = _get_person(session, person_id)
    rows = session.execute(
        select(ScoreSnapshot, ScoringModel)
        .join(ScoringModel, ScoringModel.id == ScoreSnapshot.scoring_model_id)
        .where(ScoreSnapshot.person_id == person.id)
        .order_by(ScoreSnapshot.scored_at.desc())
    ).all()
    return {
        "items": [
            {
                "id": str(s.id),
                "model": m.name,
                "model_version": m.version,
                "scored_at": s.scored_at.isoformat(),
                "as_of_date": s.as_of_date.isoformat() if s.as_of_date else None,
                "priority_score": s.priority_score,
                "quality_score": s.quality_score,
                "fit_score": s.fit_score,
                "timing_score": s.timing_score,
                "access_score": s.access_score,
                "confidence_score": s.confidence_score,
                "rank": s.rank,
                "percentile": s.percentile,
                "action": s.action,
                "reason_codes": s.reason_codes,
                "contribution_breakdown": s.contribution_breakdown,
                "delta_breakdown": s.delta_breakdown,
            }
            for s, m in rows
        ]
    }


@router.get("/{person_id}/features")
def person_features(person_id: str, session: SessionDep) -> dict:
    person = _get_person(session, person_id)
    rows = session.execute(
        select(PersonFeatureSnapshot)
        .where(PersonFeatureSnapshot.person_id == person.id)
        .order_by(PersonFeatureSnapshot.calculated_at.desc())
    ).scalars()
    return {
        "items": [
            {
                "id": str(f.id),
                "model_target": f.model_target,
                "feature_set_version": f.feature_set_version,
                "calculated_at": f.calculated_at.isoformat(),
                "as_of_date": f.as_of_date.isoformat() if f.as_of_date else None,
                "features": f.features,
                "missing_features": f.missing_features,
                "data_freshness": f.data_freshness,
            }
            for f in rows
        ]
    }


@router.get("/{person_id}/relationships")
def person_relationships(person_id: str, session: SessionDep) -> dict:
    person = _get_person(session, person_id)
    rows = session.execute(
        select(RelationshipEdge).where(
            or_(
                RelationshipEdge.source_person_id == person.id,
                RelationshipEdge.target_person_id == person.id,
            )
        )
    ).scalars()
    return {"items": [relationship_row(session, e, person.id) for e in rows]}


@router.get("/{person_id}/paths")
def person_paths(person_id: str, session: SessionDep) -> dict:
    person = _get_person(session, person_id)
    acc = compute_access(session, person.id, now_utc())
    return acc.as_dict()
