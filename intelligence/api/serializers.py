"""Plain-dict serializers for API responses (spec §43). Routers stay thin — no math here."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from intelligence.models import (
    Employment,
    Event,
    Evidence,
    Fact,
    Inference,
    Organization,
    Person,
    PersonClassification,
    RawObservation,
    RelationshipEdge,
    ScoreSnapshot,
    ScoringModel,
)


def _org_name(session: Session, org_id: uuid.UUID | None) -> str | None:
    if org_id is None:
        return None
    o = session.get(Organization, org_id)
    return o.canonical_name if o else None


def classes_for(session: Session, person_id: uuid.UUID) -> list[str]:
    return [
        c
        for (c,) in session.execute(
            select(PersonClassification.person_class).where(
                PersonClassification.person_id == person_id
            )
        )
    ]


def current_and_previous_role(
    session: Session, person_id: uuid.UUID
) -> tuple[dict | None, dict | None]:
    emps = list(
        session.execute(
            select(Employment)
            .where(Employment.person_id == person_id)
            .order_by(Employment.current.desc(), Employment.started_at.desc().nullslast())
        ).scalars()
    )
    cur = next((e for e in emps if e.current), None)
    prev = next((e for e in emps if not e.current and e.ended_at), None)

    def _fmt(e: Employment | None) -> dict | None:
        if e is None:
            return None
        return {
            "company": _org_name(session, e.organization_id),
            "title": e.title,
            "started_at": e.started_at.isoformat() if e.started_at else None,
            "ended_at": e.ended_at.isoformat() if e.ended_at else None,
        }

    return _fmt(cur), _fmt(prev)


def latest_scores(session: Session, person_id: uuid.UUID) -> dict[str, dict]:
    out: dict[str, dict] = {}
    rows = session.execute(
        select(ScoreSnapshot, ScoringModel)
        .join(ScoringModel, ScoringModel.id == ScoreSnapshot.scoring_model_id)
        .where(ScoreSnapshot.person_id == person_id)
        .order_by(ScoreSnapshot.scored_at.desc())
    ).all()
    for snap, model in rows:
        if model.target_class in out:
            continue
        delta = (snap.delta_breakdown or {}).get("priority_delta")
        out[model.target_class] = {
            "model": model.name,
            "model_version": model.version,
            "priority": round(snap.priority_score, 2),
            "quality": snap.quality_score,
            "fit": snap.fit_score,
            "timing": snap.timing_score,
            "access": snap.access_score,
            "confidence": round(snap.confidence_score, 3),
            "weekly_delta": round(delta, 2) if delta is not None else None,
            "rank": snap.rank,
            "percentile": snap.percentile,
            "action": snap.action,
            "reason_codes": snap.reason_codes or [],
            "scored_at": snap.scored_at.isoformat(),
            "score_snapshot_id": str(snap.id),
        }
    return out


def latest_events(session: Session, person_id: uuid.UUID, limit: int = 10) -> list[dict]:
    rows = session.execute(
        select(Event)
        .where(Event.person_id == person_id)
        .order_by(Event.occurred_at.desc().nullslast(), Event.detected_at.desc())
        .limit(limit)
    ).scalars()
    return [event_summary(session, e) for e in rows]


def event_summary(session: Session, e: Event) -> dict:
    return {
        "id": str(e.id),
        "type": e.event_type,
        "occurred_at": e.occurred_at.isoformat() if e.occurred_at else None,
        "detected_at": e.detected_at.isoformat(),
        "confidence": round(e.confidence, 2),
        "severity": e.severity,
        "status": e.status,
        "organization": _org_name(session, e.organization_id),
        "evidence_ids": e.evidence_ids or [],
    }


def inferences_for(session: Session, person_id: uuid.UUID) -> list[dict]:
    rows = session.execute(
        select(Inference)
        .where(Inference.person_id == person_id)
        .order_by(Inference.created_at.desc())
    ).scalars()
    return [
        {
            "id": str(i.id),
            "type": i.inference_type,
            "probability": i.probability,
            "model_version": i.model_version,
            "explanation_code": i.explanation_code,
            "evidence_ids": i.evidence_ids or [],
            "created_at": i.created_at.isoformat(),
            "expires_at": i.expires_at.isoformat() if i.expires_at else None,
            "label": "inference",
        }
        for i in rows
    ]


def strongest_path(scores: dict[str, dict], session: Session, person_id: uuid.UUID) -> dict | None:
    # the access payload lives on any model with an access dimension (founder / lp / talent)
    snaps = (
        session.execute(
            select(ScoreSnapshot)
            .where(ScoreSnapshot.person_id == person_id)
            .order_by(ScoreSnapshot.scored_at.desc())
        )
        .scalars()
        .all()
    )
    access = None
    for snap in snaps:
        access = (
            (snap.contribution_breakdown or {})
            .get("dimensions", {})
            .get("access", {})
            .get("access")
        )
        if access:
            break
    if not access:
        return None
    return {
        "hops": access.get("hops"),
        "relationship_strength": access.get("strength"),
        "status": access.get("status"),
        "node_names": access.get("node_names", []),
        "last_verified_at": access.get("last_verified_at"),
        "score": access.get("score"),
    }


def person_detail(session: Session, person: Person) -> dict:
    cur, prev = current_and_previous_role(session, person.id)
    scores = latest_scores(session, person.id)
    return {
        "id": str(person.id),
        "name": person.canonical_name,
        "classes": classes_for(session, person.id),
        "primary_location": person.primary_location,
        "primary_linkedin_url": person.primary_linkedin_url,
        "monitoring_status": person.monitoring_status,
        "entity_resolution_status": person.entity_resolution_status,
        "entity_resolution_confidence": person.entity_resolution_confidence,
        "pinned": person.pinned,
        "merged_into_id": str(person.merged_into_id) if person.merged_into_id else None,
        "first_seen_at": person.first_seen_at.isoformat() if person.first_seen_at else None,
        "last_observed_at": person.last_observed_at.isoformat()
        if person.last_observed_at
        else None,
        "current_role": cur,
        "previous_role": prev,
        "scores": scores,
        "latest_events": latest_events(session, person.id),
        "inferences": inferences_for(session, person.id),
        "strongest_path": strongest_path(scores, session, person.id),
        "notes": person.notes,
    }


def person_row(session: Session, person: Person) -> dict:
    """Compact row for the Intelligence table."""
    scores = latest_scores(session, person.id)
    founder = scores.get("founder", {})
    cur, _ = current_and_previous_role(session, person.id)
    latest_ev = latest_events(session, person.id, limit=1)
    return {
        "id": str(person.id),
        "name": person.canonical_name,
        "classes": classes_for(session, person.id),
        "monitoring_status": person.monitoring_status,
        "current_role": cur,
        "scores": {
            k: {
                "priority": v["priority"],
                "quality": v["quality"],
                "fit": v["fit"],
                "timing": v["timing"],
                "access": v["access"],
                "confidence": v["confidence"],
                "weekly_delta": v["weekly_delta"],
                "rank": v["rank"],
                "percentile": v["percentile"],
                "action": v["action"],
            }
            for k, v in scores.items()
        },
        "latest_event": latest_ev[0] if latest_ev else None,
        "founder_priority": founder.get("priority"),
    }


def fact_detail(session: Session, f: Fact) -> dict:
    ev = list(session.execute(select(Evidence).where(Evidence.fact_id == f.id)).scalars())
    return {
        "id": str(f.id),
        "fact_type": f.fact_type,
        "subject_type": f.subject_type,
        "value": f.structured_value,
        "valid_from": f.valid_from.isoformat() if f.valid_from else None,
        "valid_to": f.valid_to.isoformat() if f.valid_to else None,
        "extraction_method": f.extraction_method,
        "extraction_confidence": f.extraction_confidence,
        "extractor_version": f.extractor_version,
        "superseded_by_id": str(f.superseded_by_id) if f.superseded_by_id else None,
        "created_at": f.created_at.isoformat(),
        "label": "fact",
        "evidence": [evidence_detail(session, e) for e in ev],
    }


def evidence_detail(session: Session, e: Evidence) -> dict:
    obs = session.get(RawObservation, e.observation_id)
    return {
        "id": str(e.id),
        "fact_id": str(e.fact_id) if e.fact_id else None,
        "source_label": e.source_label,
        "source_url": e.source_url,
        "quoted_fragment": e.quoted_fragment,
        "observed_at": e.observed_at.isoformat() if e.observed_at else None,
        "evidence_strength": e.evidence_strength,
        "observation": {
            "id": str(obs.id),
            "content_type": obs.content_type,
            "source_url": obs.source_url,
            "provider_record_id": obs.provider_record_id,
            "occurred_at": obs.occurred_at.isoformat() if obs.occurred_at else None,
            "observed_at": obs.observed_at.isoformat(),
            "ingested_at": obs.ingested_at.isoformat(),
            "raw_text": obs.raw_text,
            "raw_json": obs.raw_json,
        }
        if obs
        else None,
    }


def relationship_row(session: Session, edge: RelationshipEdge, focus_id: uuid.UUID) -> dict:
    other_id = edge.target_person_id if edge.source_person_id == focus_id else edge.source_person_id
    other = session.get(Person, other_id)
    return {
        "id": str(edge.id),
        "other_person_id": str(other_id),
        "other_person_name": other.canonical_name if other else None,
        "relationship_type": edge.relationship_type,
        "relationship_strength": edge.relationship_strength,
        "strength_numeric": edge.strength_numeric,
        "confidence": edge.confidence,
        "last_verified_at": edge.last_verified_at.isoformat() if edge.last_verified_at else None,
        "source": edge.source,
    }
