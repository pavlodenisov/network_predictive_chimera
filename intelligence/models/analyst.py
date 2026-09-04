"""Human-in-the-loop tables: feedback, non-destructive overrides, entity-resolution
audit, reversible merges (spec §9, §31, §32)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from intelligence.db import Base
from intelligence.models.base import CreatedAtMixin, UUIDPrimaryKey
from intelligence.models.enums import (
    DecisionSource,
    FeedbackType,
    OverrideTargetType,
    ResolutionDecision,
)
from intelligence.types import GUID, JSONB, UTCDateTime


class AnalystFeedback(Base, UUIDPrimaryKey, CreatedAtMixin):
    __tablename__ = "analyst_feedback"
    __table_args__ = (Index("ix_feedback_person", "person_id"),)

    person_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(120), nullable=False)
    score_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("score_snapshot.id", ondelete="SET NULL")
    )
    feedback_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default=FeedbackType.VIEWED
    )
    feedback_value: Mapped[dict | None] = mapped_column(JSONB)
    reason_code: Mapped[str | None] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(Text)
    #: for connector intro-tracking: the person credited with the intro.
    connector_person_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("person.id", ondelete="SET NULL")
    )


class AnalystOverride(Base, UUIDPrimaryKey, CreatedAtMixin):
    """Never destroys the original — stores original + override + who + when + why."""

    __tablename__ = "analyst_override"
    __table_args__ = (Index("ix_override_person", "person_id"),)

    target_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default=OverrideTargetType.EVENT
    )
    target_id: Mapped[uuid.UUID | None] = mapped_column(GUID)
    person_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("person.id", ondelete="CASCADE")
    )
    original_value: Mapped[dict | None] = mapped_column(JSONB)
    override_value: Mapped[dict | None] = mapped_column(JSONB)
    analyst_user_id: Mapped[str] = mapped_column(String(120), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reverted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class EntityResolutionResult(Base, UUIDPrimaryKey, CreatedAtMixin):
    __tablename__ = "entity_resolution_result"

    candidate_observation_id: Mapped[uuid.UUID | None] = mapped_column(GUID)
    candidate_person_id: Mapped[uuid.UUID | None] = mapped_column(GUID)
    matched_person_id: Mapped[uuid.UUID | None] = mapped_column(GUID)
    decision: Mapped[str] = mapped_column(
        String(24), nullable=False, default=ResolutionDecision.NO_MATCH
    )
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    scorecard: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    competing_person_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    auto_applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reviewer_user_id: Mapped[str | None] = mapped_column(String(120))


class EntityMergeLog(Base, UUIDPrimaryKey, CreatedAtMixin):
    """Every merge is reversible. ``merged_fields`` snapshots the loser for restore."""

    __tablename__ = "entity_merge_log"
    __table_args__ = (
        Index("ix_merge_winner", "winner_person_id"),
        Index("ix_merge_loser", "loser_person_id"),
    )

    winner_person_id: Mapped[uuid.UUID] = mapped_column(GUID, nullable=False)
    loser_person_id: Mapped[uuid.UUID] = mapped_column(GUID, nullable=False)
    decision_source: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DecisionSource.AUTO
    )
    resolution_result_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("entity_resolution_result.id", ondelete="SET NULL")
    )
    merged_fields: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    analyst_user_id: Mapped[str | None] = mapped_column(String(120))
    reason: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reverted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
