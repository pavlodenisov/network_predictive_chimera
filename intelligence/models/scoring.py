from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from intelligence.db import Base
from intelligence.models.base import CreatedAtMixin, UUIDPrimaryKey
from intelligence.models.enums import ModelTarget, ScoringModelStatus
from intelligence.types import GUID, JSONB, UTCDateTime


class PersonFeatureSnapshot(Base, UUIDPrimaryKey, CreatedAtMixin):
    """Raw feature values (not just scores) — reproducibility (spec §7)."""

    __tablename__ = "person_feature_snapshot"
    __table_args__ = (Index("ix_pfs_person_calc", "person_id", "calculated_at"),)

    person_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    model_target: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ModelTarget.FOUNDER
    )
    feature_set_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v0.1")
    calculated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    as_of_date: Mapped[date | None] = mapped_column(Date)
    #: {name: {value, status, raw_unit, source_fact_ids}}
    features: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    missing_features: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    data_freshness: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class ScoringModel(Base, UUIDPrimaryKey, CreatedAtMixin):
    __tablename__ = "scoring_model"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_scoring_model_name_version"),
        Index("ix_scoring_model_name", "name"),
    )

    name: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    target_class: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ModelTarget.FOUNDER
    )
    configuration: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ScoringModelStatus.DRAFT
    )
    activated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    retired_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class RankingUniverse(Base, UUIDPrimaryKey, CreatedAtMixin):
    """Every rank is meaningless without its universe (spec §54)."""

    __tablename__ = "ranking_universe"

    label: Mapped[str] = mapped_column(String(200), nullable=False)
    model_target: Mapped[str] = mapped_column(String(16), nullable=False)
    scoring_model_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("scoring_model.id", ondelete="SET NULL")
    )
    filter: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    as_of_date: Mapped[date | None] = mapped_column(Date)
    member_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ScoreSnapshot(Base, UUIDPrimaryKey, CreatedAtMixin):
    __tablename__ = "score_snapshot"
    __table_args__ = (
        Index("ix_score_snapshot_lookup", "person_id", "scoring_model_id", "scored_at"),
    )

    person_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    scoring_model_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("scoring_model.id", ondelete="RESTRICT"), nullable=False
    )
    feature_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("person_feature_snapshot.id", ondelete="SET NULL")
    )
    weekly_run_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("weekly_run.id", ondelete="SET NULL")
    )
    scored_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    as_of_date: Mapped[date | None] = mapped_column(Date)

    quality_score: Mapped[float | None] = mapped_column(Float)
    fit_score: Mapped[float | None] = mapped_column(Float)
    timing_score: Mapped[float | None] = mapped_column(Float)
    access_score: Mapped[float | None] = mapped_column(Float)
    priority_score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    rank: Mapped[int | None] = mapped_column(Integer)
    percentile: Mapped[float | None] = mapped_column(Float)
    rank_universe_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("ranking_universe.id", ondelete="SET NULL")
    )
    previous_score_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("score_snapshot.id", ondelete="SET NULL")
    )
    contribution_breakdown: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    delta_breakdown: Mapped[dict | None] = mapped_column(JSONB)
    action: Mapped[str | None] = mapped_column(String(32))
    reason_codes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
