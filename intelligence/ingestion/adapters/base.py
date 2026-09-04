"""Source adapter contract (spec §5, §48).

The analytical pipeline downstream of ingestion is identical regardless of source. An
adapter that lacks credentials returns ``status=disabled`` from ``health_check`` and empty
lists from ``discover`` / ``update_known_entities`` — it never raises and never scrapes.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol, runtime_checkable

from intelligence.models.enums import ContentType, SourceHealthStatus
from intelligence.observability import now_utc


@dataclass(slots=True)
class PersonRef:
    person_id: uuid.UUID
    canonical_name: str
    linkedin_url: str | None = None
    provider_ids: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class RawObservationDraft:
    """Pre-persistence observation. ``normalize.persist_drafts`` turns these into rows."""

    provider_record_id: str | None
    content_type: ContentType | str
    subject_hint: str | None = None
    occurred_at: datetime | None = None
    observed_at: datetime = field(default_factory=now_utc)
    source_url: str | None = None
    raw_text: str | None = None
    raw_json: dict | None = None
    metadata: dict = field(default_factory=dict)
    #: prior structured profile snapshot for the same subject (repeated-snapshot diffing).
    previous_snapshot: dict | None = None


@dataclass(slots=True)
class SourceHealth:
    source_name: str
    status: SourceHealthStatus | str
    records: int = 0
    latency_ms: int = 0
    last_successful_run: datetime | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status in (SourceHealthStatus.SUCCESSFUL, SourceHealthStatus.PARTIAL)


@runtime_checkable
class SourceAdapter(Protocol):
    source_name: str
    source_type: str
    reliability_tier: int

    def discover(self, *, rules: Sequence[object], as_of: date) -> list[RawObservationDraft]: ...

    def update_known_entities(
        self, *, people: Sequence[PersonRef], as_of: date
    ) -> list[RawObservationDraft]: ...

    def health_check(self) -> SourceHealth: ...


class DisabledAdapter:
    """Base for provider stubs with no credentials. Cleanly no-ops (spec §48)."""

    source_name = "disabled"
    source_type = "enrichment"
    reliability_tier = 3
    reason = "not configured"

    def discover(self, *, rules: Sequence[object], as_of: date) -> list[RawObservationDraft]:
        return []

    def update_known_entities(
        self, *, people: Sequence[PersonRef], as_of: date
    ) -> list[RawObservationDraft]:
        return []

    def health_check(self) -> SourceHealth:
        return SourceHealth(
            source_name=self.source_name,
            status=SourceHealthStatus.DISABLED,
            errors=[self.reason],
        )
