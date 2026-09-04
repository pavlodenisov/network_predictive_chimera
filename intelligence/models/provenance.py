"""The provenance layer: Source → RawObservation (immutable) → Evidence → Fact,
plus StoryCluster (syndicated-news dedup) and Inference (never presented as fact).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from intelligence.db import Base
from intelligence.models.base import CreatedAtMixin, UUIDPrimaryKey
from intelligence.models.enums import (
    ContentType,
    ExtractionMethod,
    SourceType,
    SubjectType,
)
from intelligence.types import GUID, JSONB, UTCDateTime


class Source(Base, UUIDPrimaryKey, CreatedAtMixin):
    __tablename__ = "source"

    source_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default=SourceType.SYNTHETIC
    )
    provider: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    #: 1 = best … 5 = weak / unverified (spec §55).
    reliability_tier: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=3)
    configuration: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    last_successful_run: Mapped[datetime | None] = mapped_column(UTCDateTime)


class StoryCluster(Base, UUIDPrimaryKey, CreatedAtMixin):
    """Groups near-duplicate syndicated articles (spec §26). Independent-source
    confidence uses ``distinct_domain_count``, not ``article_count``."""

    __tablename__ = "story_cluster"
    __table_args__ = (Index("ix_story_cluster_key", "cluster_key"),)

    cluster_key: Mapped[str] = mapped_column(String(255), nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(String(1024))
    first_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    article_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    distinct_domain_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class RawObservation(Base, UUIDPrimaryKey):
    """IMMUTABLE. No code path may UPDATE or DELETE this table (CLAUDE.md rule; §7)."""

    __tablename__ = "raw_observation"
    __table_args__ = (
        Index("ix_raw_observation_hash", "content_hash"),
        Index("ix_raw_observation_provider", "source_id", "provider_record_id"),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("source.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    provider_record_id: Mapped[str | None] = mapped_column(String(255))
    subject_hint: Mapped[str | None] = mapped_column(String(255))

    occurred_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    source_url: Mapped[str | None] = mapped_column(String(1024))
    content_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ContentType.JSON_RECORD
    )
    raw_text: Mapped[str | None] = mapped_column(Text)
    raw_json: Mapped[dict | None] = mapped_column(JSONB)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    story_cluster_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("story_cluster.id", ondelete="SET NULL")
    )
    obs_metadata: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)


class Fact(Base, UUIDPrimaryKey, CreatedAtMixin):
    __tablename__ = "fact"
    __table_args__ = (Index("ix_fact_subject", "subject_type", "subject_id", "fact_type"),)

    subject_type: Mapped[str] = mapped_column(
        String(24), nullable=False, default=SubjectType.PERSON
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(GUID, nullable=False)
    fact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    #: {"value": …, "unit": …}  OR  {"status": "unknown"}  — never a silent 0 (spec §2.3).
    structured_value: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    valid_from: Mapped[datetime | None] = mapped_column(UTCDateTime)
    valid_to: Mapped[datetime | None] = mapped_column(UTCDateTime)

    extraction_method: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ExtractionMethod.DETERMINISTIC_PARSE
    )
    extraction_confidence: Mapped[float | None] = mapped_column(Float)
    extractor_version: Mapped[str] = mapped_column(String(64), nullable=False, default="rules_v0.1")
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("fact.id", ondelete="SET NULL")
    )


class Evidence(Base, UUIDPrimaryKey, CreatedAtMixin):
    """Bridges a Fact to the immutable observation it came from. A Fact with no
    Evidence is a bug (CLAUDE.md rule 3)."""

    __tablename__ = "evidence"
    __table_args__ = (Index("ix_evidence_fact", "fact_id"),)

    fact_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("fact.id", ondelete="CASCADE")
    )
    observation_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("raw_observation.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_url: Mapped[str | None] = mapped_column(String(1024))
    source_label: Mapped[str] = mapped_column(String(255), nullable=False)
    quoted_fragment: Mapped[str | None] = mapped_column(Text)
    observed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    #: 0–1, derived from source reliability_tier + directness (spec §55).
    evidence_strength: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)


class Inference(Base, UUIDPrimaryKey, CreatedAtMixin):
    """A labelled, probabilistic interpretation. NEVER presented as fact (spec §2.2)."""

    __tablename__ = "inference"
    __table_args__ = (Index("ix_inference_person_type", "person_id", "inference_type"),)

    person_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    inference_type: Mapped[str] = mapped_column(String(64), nullable=False)
    probability: Mapped[float] = mapped_column(Float, nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    explanation_code: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
