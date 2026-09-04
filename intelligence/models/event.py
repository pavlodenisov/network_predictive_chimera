from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from intelligence.db import Base
from intelligence.models.base import CreatedAtMixin, UUIDPrimaryKey
from intelligence.models.enums import EventStatus, Severity
from intelligence.types import GUID, JSONB, UTCDateTime


class Event(Base, UUIDPrimaryKey, CreatedAtMixin):
    """Normalized 'something changed' record. Types come from the versioned taxonomy
    (``docs/EVENT_TAXONOMY.md`` / ``intelligence/events/taxonomy.py``)."""

    __tablename__ = "event"
    __table_args__ = (
        Index("ix_event_person_occurred", "person_id", "occurred_at"),
        Index("ix_event_dedupe", "dedupe_key"),
        Index("ix_event_type", "event_type"),
    )

    person_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("organization.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    detected_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default=Severity.LOW)
    evidence_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    structured_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    supersedes_event_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("event.id", ondelete="SET NULL")
    )
    #: sha1(person_id | event_type | occurred_at | sorted(evidence_ids)) — idempotency.
    dedupe_key: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=EventStatus.ACTIVE)
    weekly_run_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("weekly_run.id", ondelete="SET NULL")
    )
