"""Real-world ecosystem events (spec addendum — "what events should we be at").

Every row requires a `source_url`; nothing here is generated. See
`intelligence/models/industry_event.py` and `scripts/seed_industry_events.py`.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import select

from intelligence.api.deps import SessionDep
from intelligence.models import IndustryEvent
from intelligence.observability import now_utc

router = APIRouter(prefix="/industry-events", tags=["industry-events"])


def _row(e: IndustryEvent) -> dict:
    return {
        "id": str(e.id),
        "name": e.name,
        "description": e.description,
        "city": e.city,
        "country": e.country,
        "venue": e.venue,
        "starts_at": e.starts_at.isoformat(),
        "ends_at": e.ends_at.isoformat() if e.ends_at else None,
        "topics": e.topics or [],
        "source_url": e.source_url,
        "source_label": e.source_label,
        "retrieved_at": e.retrieved_at.isoformat(),
    }


@router.get("")
def list_industry_events(
    session: SessionDep,
    city: str | None = Query(None),
    upcoming_only: bool = Query(True),
) -> dict:
    stmt = select(IndustryEvent)
    if city:
        stmt = stmt.where(IndustryEvent.city.ilike(f"%{city}%"))
    if upcoming_only:
        stmt = stmt.where(IndustryEvent.starts_at >= now_utc())
    stmt = stmt.order_by(IndustryEvent.starts_at.asc())
    rows = session.execute(stmt).scalars().all()
    return {"items": [_row(e) for e in rows], "total": len(rows)}
