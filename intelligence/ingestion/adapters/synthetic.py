"""Deterministic synthetic source (spec §48). Powers the reproducible weekly demo.

Reads fixture drafts from ``<seeds_dir>/synthetic/``. Returns every draft whose
``observed_at`` is on or before the run's ``as_of`` — dedup (content hash / provider id)
makes re-runs and multi-week runs idempotent.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from pathlib import Path

from intelligence.config import get_settings
from intelligence.ingestion.adapters.base import PersonRef, RawObservationDraft, SourceHealth
from intelligence.ingestion.adapters.loader import load_fixture_drafts
from intelligence.models.enums import SourceHealthStatus, SourceType


class SyntheticSource:
    source_name = "synthetic"
    source_type = SourceType.SYNTHETIC
    reliability_tier = 2

    def __init__(self, seeds_dir: Path | str | None = None) -> None:
        base = Path(seeds_dir) if seeds_dir else get_settings().seeds_dir
        self._dir = base / "synthetic"

    def discover(self, *, rules: Sequence[object], as_of: date) -> list[RawObservationDraft]:
        return load_fixture_drafts(self._dir, as_of=as_of, mode="discover")

    def update_known_entities(
        self, *, people: Sequence[PersonRef], as_of: date
    ) -> list[RawObservationDraft]:
        return load_fixture_drafts(self._dir, as_of=as_of, mode="update")

    def health_check(self) -> SourceHealth:
        n = len(list(self._dir.glob("*.json"))) if self._dir.exists() else 0
        return SourceHealth(
            source_name=self.source_name,
            status=SourceHealthStatus.SUCCESSFUL if n else SourceHealthStatus.PARTIAL,
            records=n,
            errors=[] if n else [f"no fixtures in {self._dir}"],
        )
