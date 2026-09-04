from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from intelligence.db import Base
from intelligence.models.base import CreatedAtMixin, UUIDPrimaryKey
from intelligence.models.enums import ScoringModelStatus
from intelligence.types import JSONB, UTCDateTime


class ThesisConfiguration(Base, UUIDPrimaryKey, CreatedAtMixin):
    """Chimera investment thesis (spec §12, §60). Seeded from configs/thesis/*.yaml."""

    __tablename__ = "thesis_configuration"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_thesis_name_version"),)

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    is_sample: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sectors: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    technologies: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    business_models: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    stages: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    geographies: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    technical_topics: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    embedding_model: Mapped[str | None] = mapped_column(String(120))
    embedding_model_version: Mapped[str | None] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ActionRuleSet(Base, UUIDPrimaryKey, CreatedAtMixin):
    """Versioned deterministic action rules (spec §57). Seeded from configs/actions/*.yaml."""

    __tablename__ = "action_rule_set"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_action_rule_set_name_version"),
        Index("ix_action_rule_set_status", "status"),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    rules: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ScoringModelStatus.DRAFT
    )
    activated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
