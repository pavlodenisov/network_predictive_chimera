from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, Float, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from intelligence.db import Base
from intelligence.models.base import CreatedAtMixin, TimestampMixin, UUIDPrimaryKey
from intelligence.models.enums import OrganizationType
from intelligence.types import GUID, JSONB, UTCDateTime


class Organization(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "organization"
    __table_args__ = (
        Index("ix_organization_name", "canonical_name"),
        Index("ix_organization_domain", "domain"),
    )

    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    organization_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default=OrganizationType.OTHER
    )
    domain: Mapped[str | None] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(String(255))
    founding_date: Mapped[date | None] = mapped_column(Date)
    #: only from disclosed figures — never estimated (spec §15).
    aum_usd: Mapped[float | None] = mapped_column(Numeric(20, 2))
    is_portfolio: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class Employment(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "employment"
    __table_args__ = (Index("ix_employment_person_current", "person_id", "current"),)

    person_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("person.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("organization.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_title: Mapped[str | None] = mapped_column(String(255))
    function: Mapped[str | None] = mapped_column(String(32))
    seniority: Mapped[str | None] = mapped_column(String(32))
    started_at: Mapped[date | None] = mapped_column(Date)
    ended_at: Mapped[date | None] = mapped_column(Date)
    current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    evidence_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    confidence: Mapped[float | None] = mapped_column(Float)
    #: provisional-canonical bookkeeping when sources conflict (spec §56).
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("employment.id", ondelete="SET NULL")
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Education(Base, UUIDPrimaryKey, CreatedAtMixin):
    __tablename__ = "education"

    person_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("person.id", ondelete="CASCADE"), nullable=False, index=True
    )
    institution_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("organization.id", ondelete="SET NULL")
    )
    institution_name_raw: Mapped[str | None] = mapped_column(String(255))
    degree: Mapped[str | None] = mapped_column(String(120))
    field: Mapped[str | None] = mapped_column(String(160))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    evidence_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
