from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from intelligence.db import Base
from intelligence.models.base import CreatedAtMixin, UUIDPrimaryKey
from intelligence.models.enums import ParseStatus, WeeklyRunStatus
from intelligence.types import GUID, JSONB, UTCDateTime


class WeeklyRun(Base, UUIDPrimaryKey):
    __tablename__ = "weekly_run"
    __table_args__ = (Index("ix_weekly_run_started", "started_at"),)

    started_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    as_of_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=WeeklyRunStatus.RUNNING)

    source_coverage: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    observations_ingested: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    people_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    people_discovered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    facts_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    events_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inferences_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scoring_models_run: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    stage_stats: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    errors: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    warnings: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    code_version: Mapped[str] = mapped_column(String(64), nullable=False, default="dev")
    config_version: Mapped[str] = mapped_column(String(64), nullable=False, default="v0.1")
    digest: Mapped[dict | None] = mapped_column(JSONB)


class ExtractionRun(Base, UUIDPrimaryKey, CreatedAtMixin):
    """Observability for every extraction attempt (spec §23)."""

    __tablename__ = "extraction_run"
    __table_args__ = (Index("ix_extraction_run_obs", "observation_id"),)

    observation_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("raw_observation.id", ondelete="CASCADE"), nullable=False
    )
    extractor_name: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    model_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    input_observation_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    output: Mapped[dict | None] = mapped_column(JSONB)
    parse_status: Mapped[str] = mapped_column(String(24), nullable=False, default=ParseStatus.OK)
    error: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    token_usage: Mapped[dict | None] = mapped_column(JSONB)
