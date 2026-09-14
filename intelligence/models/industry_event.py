"""Real-world ecosystem events (conferences, summits, meetups) worth attending — distinct
from `Event` (a taxonomy-typed change in a person's state, spec §8). An `IndustryEvent`
row is only ever created from a verifiable source: `source_url` is required and nothing
here is generated — this is a calendar, not a recommendation engine (CLAUDE.md #1, #9).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from intelligence.db import Base
from intelligence.models.base import CreatedAtMixin, UUIDPrimaryKey
from intelligence.types import JSONB, UTCDateTime


class IndustryEvent(Base, UUIDPrimaryKey, CreatedAtMixin):
    __tablename__ = "industry_event"

    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str] = mapped_column(String(120), nullable=False)
    country: Mapped[str] = mapped_column(String(120), nullable=False, default="India")
    venue: Mapped[str | None] = mapped_column(String(300))
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    topics: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    #: provenance is mandatory — an event with no source is not a fact, it's a guess.
    source_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_label: Mapped[str] = mapped_column(String(200), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    added_by: Mapped[str] = mapped_column(String(120), nullable=False, default="manual_research")
