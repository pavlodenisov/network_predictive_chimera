from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from intelligence.db import Base
from intelligence.models.base import TimestampMixin, UUIDPrimaryKey
from intelligence.models.enums import RelationshipStrength, RelationshipType
from intelligence.types import GUID, JSONB, UTCDateTime


class RelationshipEdge(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "relationship_edge"
    __table_args__ = (
        Index("ix_edge_source", "source_person_id"),
        Index("ix_edge_target", "target_person_id"),
    )

    source_person_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    target_person_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    relationship_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default=RelationshipType.UNKNOWN
    )
    relationship_strength: Mapped[str] = mapped_column(
        String(16), nullable=False, default=RelationshipStrength.UNKNOWN
    )
    #: only populated when data supports it — else NULL, never 0 (spec §7, §2.3).
    strength_numeric: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    first_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    evidence_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
