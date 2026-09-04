from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import select

from intelligence.api.deps import PaginationDep, SessionDep
from intelligence.api.serializers import person_row
from intelligence.models import (
    Person,
    RankingUniverse,
    ScoreSnapshot,
    ScoringModel,
    WeeklyRun,
)

router = APIRouter(prefix="/rankings", tags=["rankings"])


def _latest_run_id(session) -> str | None:
    r = session.execute(select(WeeklyRun).order_by(WeeklyRun.started_at.desc())).scalars().first()
    return str(r.id) if r else None


def _ranking(
    session,
    page,
    target: str,
    *,
    min_priority: float | None,
    warm_path: bool | None,
    min_confidence: float | None,
) -> dict:
    run_id = _latest_run_id(session)
    stmt = (
        select(ScoreSnapshot, Person)
        .join(ScoringModel, ScoringModel.id == ScoreSnapshot.scoring_model_id)
        .join(Person, Person.id == ScoreSnapshot.person_id)
        .where(ScoringModel.target_class == target, Person.merged_into_id.is_(None))
    )
    if run_id:
        stmt = stmt.where(ScoreSnapshot.weekly_run_id == run_id)
    if min_priority is not None:
        stmt = stmt.where(ScoreSnapshot.priority_score >= min_priority)
    if min_confidence is not None:
        stmt = stmt.where(ScoreSnapshot.confidence_score >= min_confidence)
    if warm_path is True:
        stmt = stmt.where(ScoreSnapshot.access_score > 0)
    stmt = stmt.order_by(ScoreSnapshot.priority_score.desc(), Person.canonical_name)

    total = len(session.execute(stmt).all())
    rows = session.execute(
        stmt.limit(page.page_size).offset((page.page - 1) * page.page_size)
    ).all()

    universe = (
        session.execute(
            select(RankingUniverse)
            .where(RankingUniverse.model_target == target)
            .order_by(RankingUniverse.created_at.desc())
        )
        .scalars()
        .first()
    )

    items = []
    for snap, person in rows:
        base = person_row(session, person)
        base["rank"] = snap.rank
        base["percentile"] = snap.percentile
        base["priority"] = round(snap.priority_score, 2)
        base["confidence"] = round(snap.confidence_score, 3)
        base["delta"] = (snap.delta_breakdown or {}).get("priority_delta")
        base["action"] = snap.action
        base["reason_codes"] = snap.reason_codes
        items.append(base)

    return {
        "model_target": target,
        "universe": {
            "label": universe.label if universe else f"{target} candidates",
            "member_count": universe.member_count if universe else total,
            "as_of_date": universe.as_of_date.isoformat()
            if universe and universe.as_of_date
            else None,
        },
        "items": items,
        "total": total,
        "page": page.page,
        "page_size": page.page_size,
    }


@router.get("/founders")
def founders(
    session: SessionDep,
    page: PaginationDep,
    min_priority: float | None = Query(None),
    warm_path: bool | None = Query(None),
    min_confidence: float | None = Query(None),
) -> dict:
    return _ranking(
        session,
        page,
        "founder",
        min_priority=min_priority,
        warm_path=warm_path,
        min_confidence=min_confidence,
    )


@router.get("/lps")
def lps(
    session: SessionDep,
    page: PaginationDep,
    min_priority: float | None = Query(None),
    warm_path: bool | None = Query(None),
    min_confidence: float | None = Query(None),
) -> dict:
    return _ranking(
        session,
        page,
        "lp",
        min_priority=min_priority,
        warm_path=warm_path,
        min_confidence=min_confidence,
    )


@router.get("/talent")
def talent(
    session: SessionDep,
    page: PaginationDep,
    min_priority: float | None = Query(None),
    warm_path: bool | None = Query(None),
    min_confidence: float | None = Query(None),
) -> dict:
    return _ranking(
        session,
        page,
        "talent",
        min_priority=min_priority,
        warm_path=warm_path,
        min_confidence=min_confidence,
    )


@router.get("/connectors")
def connectors(
    session: SessionDep,
    page: PaginationDep,
    min_priority: float | None = Query(None),
    warm_path: bool | None = Query(None),
    min_confidence: float | None = Query(None),
) -> dict:
    return _ranking(
        session,
        page,
        "connector",
        min_priority=min_priority,
        warm_path=warm_path,
        min_confidence=min_confidence,
    )
