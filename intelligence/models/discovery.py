from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from intelligence.db import Base
from intelligence.models.base import TimestampMixin, UUIDPrimaryKey
from intelligence.models.enums import PersonClass
from intelligence.types import GUID, JSONB, UTCDateTime


class DiscoveryRule(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "discovery_rule"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    target_class: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PersonClass.UNKNOWN
    )
    industries: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    technical_topics: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    titles: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    prior_employers: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    geographies: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    keywords: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    excluded_keywords: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    source_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    lookback_days: Mapped[int] = mapped_column(Integer, nullable=False, default=120)
    minimum_evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False, default="seed")


class DiscoveryCandidate(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "discovery_candidate"
    __table_args__ = (Index("ix_discovery_candidate_rule", "discovery_rule_id"),)

    discovery_rule_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("discovery_rule.id", ondelete="CASCADE"), nullable=False
    )
    #: staging person (entity_resolution_status stays UNRESOLVED until promoted).
    person_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("person.id", ondelete="SET NULL")
    )
    first_discovered_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("source.id", ondelete="SET NULL")
    )
    triggering_evidence_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    identity_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    candidate_classification: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PersonClass.UNKNOWN
    )
    promoted_to_person_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("person.id", ondelete="SET NULL")
    )
    promoted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    dismissed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dismissed_reason: Mapped[str | None] = mapped_column(Text)
    false_positive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    score: Mapped[float | None] = mapped_column(Float)
    score_breakdown: Mapped[dict | None] = mapped_column(JSONB)
