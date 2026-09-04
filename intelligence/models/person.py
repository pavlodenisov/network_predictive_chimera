from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from intelligence.db import Base
from intelligence.models.base import CreatedAtMixin, TimestampMixin, UUIDPrimaryKey
from intelligence.models.enums import (
    AliasType,
    EntityResolutionStatus,
    MonitoringStatus,
    PersonClass,
)
from intelligence.types import GUID, UTCDateTime


class Person(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "person"
    __table_args__ = (
        Index("ix_person_canonical_name", "canonical_name"),
        Index("ix_person_linkedin", "primary_linkedin_url"),
        Index("ix_person_email", "primary_email"),
    )

    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(120))
    last_name: Mapped[str | None] = mapped_column(String(120))
    primary_location: Mapped[str | None] = mapped_column(String(255))
    primary_email: Mapped[str | None] = mapped_column(String(320))
    primary_linkedin_url: Mapped[str | None] = mapped_column(String(512))
    current_title: Mapped[str | None] = mapped_column(String(255))
    current_organization_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("organization.id", ondelete="SET NULL")
    )

    monitoring_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=MonitoringStatus.REVIEW
    )
    entity_resolution_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=EntityResolutionStatus.UNRESOLVED
    )
    entity_resolution_confidence: Mapped[float | None] = mapped_column(Float)
    #: set when this row was merged away into ``merged_into_id`` (reversible — row kept).
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("person.id", ondelete="SET NULL")
    )

    is_chimera_seed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text)

    first_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_observed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<Person {self.canonical_name!r} {self.id}>"


class PersonAlias(Base, UUIDPrimaryKey, CreatedAtMixin):
    __tablename__ = "person_alias"
    __table_args__ = (Index("ix_person_alias_value", "alias_value"),)

    person_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("person.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alias_type: Mapped[str] = mapped_column(String(32), nullable=False, default=AliasType.OTHER)
    alias_value: Mapped[str] = mapped_column(String(512), nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("source.id", ondelete="SET NULL")
    )
    confidence: Mapped[float | None] = mapped_column(Float)


class PersonClassification(Base, UUIDPrimaryKey, CreatedAtMixin):
    """Many-to-many person ↔ class (spec §4). A person may hold several at once."""

    __tablename__ = "person_classification"
    __table_args__ = (
        UniqueConstraint("person_id", "person_class", name="uq_person_class"),
        Index("ix_person_classification_person", "person_id"),
    )

    person_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    person_class: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PersonClass.UNKNOWN
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="pipeline")
    confidence: Mapped[float | None] = mapped_column(Float)
    assigned_by: Mapped[str | None] = mapped_column(String(120))
    rationale_code: Mapped[str | None] = mapped_column(String(64))
