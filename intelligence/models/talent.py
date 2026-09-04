from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from intelligence.db import Base
from intelligence.models.base import CreatedAtMixin, TimestampMixin, UUIDPrimaryKey
from intelligence.models.enums import Function, RoleNeedStatus, Seniority
from intelligence.types import GUID, JSONB, UTCDateTime


class PortfolioRoleNeed(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "portfolio_role_need"
    __table_args__ = (Index("ix_role_need_company", "portfolio_company_id"),)

    portfolio_company_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    role_title: Mapped[str] = mapped_column(String(200), nullable=False)
    function: Mapped[str] = mapped_column(String(32), nullable=False, default=Function.ENGINEERING)
    seniority: Mapped[str] = mapped_column(String(32), nullable=False, default=Seniority.VP)
    domain_requirements: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    stage_requirements: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    location_requirements: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=RoleNeedStatus.OPEN)


class CandidateRoleMatch(Base, UUIDPrimaryKey, CreatedAtMixin):
    __tablename__ = "candidate_role_match"
    __table_args__ = (
        UniqueConstraint(
            "person_id", "portfolio_role_need_id", "model_version", name="uq_candidate_role_model"
        ),
        Index("ix_crm_person", "person_id"),
        Index("ix_crm_role", "portfolio_role_need_id"),
    )

    person_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    portfolio_role_need_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("portfolio_role_need.id", ondelete="CASCADE"), nullable=False
    )
    model_version: Mapped[str] = mapped_column(String(32), nullable=False, default="talent_v0.1")
    calculated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    score_breakdown: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
