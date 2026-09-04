"""Write endpoints: analyst feedback, non-destructive overrides, CSV imports, manual
weekly-run trigger (spec §31, §32, §42)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from intelligence.api.deps import CurrentUser, SessionDep, require_role
from intelligence.entity_resolution import merge_persons, unmerge
from intelligence.models import (
    AnalystFeedback,
    AnalystOverride,
    Event,
    Person,
)
from intelligence.models.enums import DecisionSource, EventStatus, OverrideTargetType
from intelligence.observability import now_utc

router = APIRouter(tags=["writes"])


class FeedbackIn(BaseModel):
    person_id: uuid.UUID
    feedback_type: str
    score_snapshot_id: uuid.UUID | None = None
    reason_code: str | None = None
    notes: str | None = None
    feedback_value: dict[str, Any] | None = None
    connector_person_id: uuid.UUID | None = None


@router.post("/feedback", status_code=201)
def post_feedback(body: FeedbackIn, session: SessionDep, user: CurrentUser) -> dict:
    if session.get(Person, body.person_id) is None:
        raise HTTPException(404, "person not found")
    fb = AnalystFeedback(
        person_id=body.person_id,
        user_id=user.id,
        feedback_type=body.feedback_type,
        score_snapshot_id=body.score_snapshot_id,
        reason_code=body.reason_code,
        notes=body.notes,
        feedback_value=body.feedback_value,
        connector_person_id=body.connector_person_id,
    )
    session.add(fb)
    session.commit()
    return {"id": str(fb.id), "created_at": fb.created_at.isoformat()}


class OverrideIn(BaseModel):
    target_type: str
    target_id: uuid.UUID | None = None
    person_id: uuid.UUID | None = None
    override_value: dict[str, Any] | None = None
    reason: str = Field(default="", max_length=2000)


@router.post("/analyst-overrides", status_code=201)
def post_override(body: OverrideIn, session: SessionDep, user: CurrentUser) -> dict:
    original: dict[str, Any] | None = None

    if body.target_type == OverrideTargetType.EVENT and body.target_id:
        ev = session.get(Event, body.target_id)
        if ev is None:
            raise HTTPException(404, "event not found")
        original = {"status": ev.status, "confidence": ev.confidence}
        ev.status = EventStatus.RETRACTED  # marked incorrect; original kept in the override row
    elif body.target_type == OverrideTargetType.PERSON_PIN and body.person_id:
        p = session.get(Person, body.person_id)
        if p is None:
            raise HTTPException(404, "person not found")
        original = {"pinned": p.pinned}
        p.pinned = bool((body.override_value or {}).get("pinned", True))
    elif body.target_type == OverrideTargetType.ENTITY_MERGE:
        ov = body.override_value or {}
        try:
            merge_persons(
                session,
                winner_id=uuid.UUID(ov["winner_id"]),
                loser_id=uuid.UUID(ov["loser_id"]),
                decision_source=DecisionSource.ANALYST,
                reason=body.reason,
                analyst_user_id=user.id,
            )
        except (KeyError, ValueError) as exc:
            raise HTTPException(422, f"merge failed: {exc}") from exc
    elif body.target_type == OverrideTargetType.ENTITY_UNMERGE and body.target_id:
        try:
            unmerge(session, body.target_id)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    row = AnalystOverride(
        target_type=body.target_type,
        target_id=body.target_id,
        person_id=body.person_id,
        original_value=original,
        override_value=body.override_value,
        analyst_user_id=user.id,
        reason=body.reason,
    )
    session.add(row)
    session.commit()
    return {"id": str(row.id), "created_at": row.created_at.isoformat()}


class ImportIn(BaseModel):
    source_provider: str = "manual_csv"
    rows: list[dict[str, Any]]


@router.post("/imports", status_code=202)
def post_import(body: ImportIn, session: SessionDep, user: CurrentUser) -> dict:
    """Stage rows for the next weekly run. V0 records them as raw observations under a
    manual source; the pipeline picks them up on its next pass."""
    from intelligence.ingestion.adapters.base import RawObservationDraft
    from intelligence.ingestion.normalize import persist_drafts
    from intelligence.models import Source
    from intelligence.models.enums import ContentType, SourceType

    src = session.execute(
        select(Source).where(Source.provider == body.source_provider)
    ).scalar_one_or_none()
    if src is None:
        src = Source(
            source_type=SourceType.MANUAL_CSV,
            provider=body.source_provider,
            name=f"import:{user.id}",
            enabled=True,
            reliability_tier=3,
        )
        session.add(src)
        session.flush()

    drafts = [
        RawObservationDraft(
            provider_record_id=r.get("record_id") or f"import:{now_utc().timestamp()}:{i}",
            content_type=ContentType.CSV_ROW,
            subject_hint=r.get("person") or r.get("subject_hint"),
            raw_json=r,
        )
        for i, r in enumerate(body.rows)
    ]
    res = persist_drafts(session, src, drafts)
    session.commit()
    return {"accepted": len(res.persisted), "skipped_duplicates": res.skipped_duplicates}


class WeeklyRunIn(BaseModel):
    as_of: date | None = None
    dry_run: bool = False


@router.post("/weekly-runs", status_code=202, dependencies=[Depends(require_role("analyst"))])
def trigger_weekly_run(body: WeeklyRunIn, session: SessionDep) -> dict:
    from intelligence.jobs.pipeline import run_weekly

    result = run_weekly(session, as_of=body.as_of, dry_run=body.dry_run)
    session.commit()
    return {"run_id": str(result.run_id), "status": result.status}
