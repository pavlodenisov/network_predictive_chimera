"""Events, discovery, models, weekly runs, data quality, search (spec §42)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from intelligence.api.deps import PaginationDep, SessionDep
from intelligence.api.serializers import event_summary
from intelligence.models import (
    DiscoveryCandidate,
    DiscoveryRule,
    Employment,
    EntityResolutionResult,
    Event,
    ExtractionRun,
    Organization,
    Person,
    RawObservation,
    ScoringModel,
    WeeklyRun,
)
from intelligence.models.enums import EntityResolutionStatus, ParseStatus
from intelligence.scoring.config import load_all_model_configs

router = APIRouter(tags=["catalog"])


# --------------------------------------------------------------------------- events
@router.get("/events")
def list_events(
    session: SessionDep,
    page: PaginationDep,
    event_type: str | None = Query(None),
    status: str | None = Query(None),
    min_confidence: float | None = Query(None),
) -> dict:
    stmt = select(Event)
    if event_type:
        stmt = stmt.where(Event.event_type == event_type)
    if status:
        stmt = stmt.where(Event.status == status)
    if min_confidence is not None:
        stmt = stmt.where(Event.confidence >= min_confidence)
    stmt = stmt.order_by(Event.detected_at.desc())
    total = session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = session.execute(
        stmt.limit(page.page_size).offset((page.page - 1) * page.page_size)
    ).scalars()
    items = []
    for e in rows:
        d = event_summary(session, e)
        p = session.get(Person, e.person_id)
        d["person"] = p.canonical_name if p else None
        d["person_id"] = str(e.person_id)
        items.append(d)
    return {"items": items, "total": int(total), "page": page.page, "page_size": page.page_size}


# --------------------------------------------------------------------------- discovery
@router.get("/discoveries")
def list_discoveries(session: SessionDep) -> dict:
    rules = {str(r.id): r.name for r in session.execute(select(DiscoveryRule)).scalars()}
    cands = session.execute(
        select(DiscoveryCandidate).order_by(DiscoveryCandidate.first_discovered_at.desc())
    ).scalars()
    items = []
    for c in cands:
        p = session.get(Person, c.person_id) if c.person_id else None
        items.append(
            {
                "id": str(c.id),
                "person_id": str(c.person_id) if c.person_id else None,
                "person": p.canonical_name if p else None,
                "rule": rules.get(str(c.discovery_rule_id)),
                "identity_confidence": c.identity_confidence,
                "candidate_classification": c.candidate_classification,
                "first_discovered_at": c.first_discovered_at.isoformat(),
                "promoted": c.promoted_to_person_id is not None,
                "dismissed": c.dismissed,
                "false_positive": c.false_positive,
                "score": c.score,
                "triggering_evidence_ids": c.triggering_evidence_ids,
            }
        )
    return {
        "candidates": items,
        "rules": [
            {
                "id": str(r.id),
                "name": r.name,
                "active": r.active,
                "target_class": r.target_class,
                "keywords": r.keywords,
                "technical_topics": r.technical_topics,
                "lookback_days": r.lookback_days,
                "minimum_evidence": r.minimum_evidence,
            }
            for r in session.execute(select(DiscoveryRule)).scalars()
        ],
    }


@router.get("/discoveries/{candidate_id}")
def get_discovery(candidate_id: str, session: SessionDep) -> dict:
    try:
        cid = uuid.UUID(candidate_id)
    except ValueError as exc:
        raise HTTPException(422, "invalid id") from exc
    c = session.get(DiscoveryCandidate, cid)
    if c is None:
        raise HTTPException(404, "candidate not found")
    obs = [
        session.get(RawObservation, uuid.UUID(o)) for o in c.triggering_evidence_ids if _is_uuid(o)
    ]
    return {
        "id": str(c.id),
        "person_id": str(c.person_id) if c.person_id else None,
        "score_breakdown": c.score_breakdown,
        "triggering_observations": [
            {
                "id": str(o.id),
                "content_type": o.content_type,
                "source_url": o.source_url,
                "raw_text": o.raw_text,
                "raw_json": o.raw_json,
            }
            for o in obs
            if o is not None
        ],
    }


def _is_uuid(s: str) -> bool:
    try:
        uuid.UUID(s)
        return True
    except (ValueError, TypeError):
        return False


# --------------------------------------------------------------------------- models
@router.get("/models")
def list_models(session: SessionDep) -> dict:
    configs = load_all_model_configs()
    rows = session.execute(
        select(ScoringModel).order_by(ScoringModel.name, ScoringModel.version)
    ).scalars()
    persisted = {f"{m.name}_{m.version}": m for m in rows}
    out = []
    for cfg in configs.values():
        pm = persisted.get(cfg.full_version)
        out.append(
            {
                "name": cfg.name,
                "version": cfg.version,
                "full_version": cfg.full_version,
                "target": cfg.target,
                "config_hash": cfg.hash(),
                "status": pm.status if pm else "draft",
                "dimension_weights": cfg.dimension_weights,
                "confidence_weights": cfg.confidence_weights,
                "dimensions": {
                    dn: {
                        "kind": d.kind,
                        "weight": d.weight,
                        "renormalize_over_present": d.renormalize_over_present,
                        "features": {
                            fn: {
                                "weight": fs.weight,
                                "normalization": fs.normalization,
                                "params": fs.params,
                                "missing_behavior": fs.missing_behavior,
                                "direction": fs.direction,
                                "source": fs.source,
                                "rationale": fs.rationale,
                            }
                            for fn, fs in d.features.items()
                        },
                        "signals": d.signals,
                        "access_model": d.access_model,
                    }
                    for dn, d in cfg.dimensions.items()
                },
            }
        )
    return {"items": out}


@router.get("/models/{name}")
def get_model(name: str, session: SessionDep) -> dict:
    configs = load_all_model_configs()
    key = name.split("_v")[0]
    cfg = configs.get(key)
    if cfg is None:
        raise HTTPException(404, "model not found")
    return {"name": cfg.name, "version": cfg.version, "raw": cfg.raw, "config_hash": cfg.hash()}


@router.get("/models/{name}/compare/{other}")
def compare_models(name: str, other: str) -> dict:
    configs = load_all_model_configs()
    a = configs.get(name.split("_v")[0])
    b = configs.get(other.split("_v")[0])
    if a is None or b is None:
        raise HTTPException(404, "model(s) not found")
    diffs = {
        "dimension_weights": {
            k: {"a": a.dimension_weights.get(k), "b": b.dimension_weights.get(k)}
            for k in set(a.dimension_weights) | set(b.dimension_weights)
            if a.dimension_weights.get(k) != b.dimension_weights.get(k)
        }
    }
    return {"a": a.full_version, "b": b.full_version, "differences": diffs}


# --------------------------------------------------------------------------- weekly runs
@router.get("/weekly-runs")
def list_weekly_runs(session: SessionDep, page: PaginationDep) -> dict:
    stmt = select(WeeklyRun).order_by(WeeklyRun.started_at.desc())
    total = session.scalar(select(func.count()).select_from(WeeklyRun)) or 0
    rows = session.execute(
        stmt.limit(page.page_size).offset((page.page - 1) * page.page_size)
    ).scalars()
    return {
        "items": [
            {
                "id": str(r.id),
                "started_at": r.started_at.isoformat(),
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "as_of_date": r.as_of_date.isoformat() if r.as_of_date else None,
                "status": r.status,
                "observations_ingested": r.observations_ingested,
                "people_updated": r.people_updated,
                "people_discovered": r.people_discovered,
                "events_created": r.events_created,
                "facts_created": r.facts_created,
                "inferences_created": r.inferences_created,
                "scoring_models_run": r.scoring_models_run,
                "code_version": r.code_version,
                "config_version": r.config_version,
                "warnings": r.warnings,
            }
            for r in rows
        ],
        "total": int(total),
        "page": page.page,
        "page_size": page.page_size,
    }


@router.get("/weekly-runs/{run_id}")
def get_weekly_run(run_id: str, session: SessionDep) -> dict:
    try:
        rid = uuid.UUID(run_id)
    except ValueError as exc:
        raise HTTPException(422, "invalid id") from exc
    r = session.get(WeeklyRun, rid)
    if r is None:
        raise HTTPException(404, "run not found")
    return {
        "id": str(r.id),
        "started_at": r.started_at.isoformat(),
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        "status": r.status,
        "source_coverage": r.source_coverage,
        "stage_stats": r.stage_stats,
        "errors": r.errors,
        "warnings": r.warnings,
        "digest": r.digest,
        "code_version": r.code_version,
        "config_version": r.config_version,
    }


# --------------------------------------------------------------------------- data quality
@router.get("/data-quality")
def data_quality(session: SessionDep) -> dict:
    latest = (
        session.execute(select(WeeklyRun).order_by(WeeklyRun.started_at.desc())).scalars().first()
    )
    source_failures = (
        [s for s in (latest.source_coverage or []) if s.get("status") in {"failed", "partial"}]
        if latest
        else []
    )

    extraction_failures = (
        session.scalar(
            select(func.count())
            .select_from(ExtractionRun)
            .where(ExtractionRun.parse_status == ParseStatus.FAILED)
        )
        or 0
    )

    unresolved = (
        session.scalar(
            select(func.count())
            .select_from(Person)
            .where(
                Person.entity_resolution_status.in_(
                    [EntityResolutionStatus.UNRESOLVED, EntityResolutionStatus.NEEDS_REVIEW]
                )
            )
        )
        or 0
    )
    ambiguous = list(
        session.execute(
            select(EntityResolutionResult).where(
                EntityResolutionResult.decision == "AMBIGUOUS",
                EntityResolutionResult.reviewed.is_(False),
            )
        ).scalars()
    )

    # conflicting current employment: >1 current employment for the same person
    conflicting = session.execute(
        select(Employment.person_id, func.count().label("n"))
        .where(Employment.current.is_(True))
        .group_by(Employment.person_id)
        .having(func.count() > 1)
    ).all()

    # suspicious duplicates: same canonical_name, >1 unmerged person
    dup_names = session.execute(
        select(Person.canonical_name, func.count().label("n"))
        .where(Person.merged_into_id.is_(None))
        .group_by(Person.canonical_name)
        .having(func.count() > 1)
    ).all()

    return {
        "source_failures": source_failures,
        "extraction_failures": int(extraction_failures),
        "unresolved_or_review_entities": int(unresolved),
        "ambiguous_resolutions": [
            {
                "id": str(a.id),
                "candidate_name": (a.scorecard or {}).get("candidate_name"),
                "competing_person_ids": a.competing_person_ids,
                "created_at": a.created_at.isoformat(),
            }
            for a in ambiguous
        ],
        "conflicting_employment": [
            {"person_id": str(pid), "current_count": n} for pid, n in conflicting
        ],
        "suspicious_duplicate_names": [{"name": name, "count": n} for name, n in dup_names],
    }


# --------------------------------------------------------------------------- search
@router.get("/search")
def search(session: SessionDep, q: str = Query(..., min_length=2)) -> dict:
    like = f"%{q}%"
    people = session.execute(
        select(Person)
        .where(Person.canonical_name.ilike(like), Person.merged_into_id.is_(None))
        .limit(20)
    ).scalars()
    orgs = session.execute(
        select(Organization).where(Organization.canonical_name.ilike(like)).limit(20)
    ).scalars()
    events = session.execute(select(Event).where(Event.event_type.ilike(like)).limit(20)).scalars()
    return {
        "people": [{"id": str(p.id), "name": p.canonical_name} for p in people],
        "organizations": [
            {"id": str(o.id), "name": o.canonical_name, "type": o.organization_type} for o in orgs
        ],
        "event_types": sorted({e.event_type for e in events}),
    }
