"""Generic professional-profile snapshot source (spec §48).

Expects authorized profile snapshots as JSON — one object per person per capture — under
``<seeds_dir>/json_snapshots/``. Repeated captures of the same subject are diffed
downstream (``snapshot.diff``). This is also the shape ``LinkedInSnapshotSource`` expects
once authorized data is supplied.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from pathlib import Path

from intelligence.config import get_settings
from intelligence.ingestion.adapters.base import PersonRef, RawObservationDraft, SourceHealth
from intelligence.ingestion.adapters.loader import load_fixture_drafts
from intelligence.models.enums import SourceHealthStatus, SourceType


class JSONSnapshotSource:
    source_name = "json_snapshot"
    source_type = SourceType.JSON_SNAPSHOT
    reliability_tier = 3  # self-reported profile data

    def __init__(self, seeds_dir: Path | str | None = None) -> None:
        base = Path(seeds_dir) if seeds_dir else get_settings().seeds_dir
        self._dir = base / "json_snapshots"

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
        )
