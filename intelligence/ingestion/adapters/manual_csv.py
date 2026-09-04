"""Analyst CSV imports (spec §48).

Reads ``<seeds_dir>/csv/*.csv``. Each row becomes a ``csv_row`` observation. A row may
carry an explicit ``fact_type`` / ``event_type`` (passed through by ``RuleBasedExtractor``)
or profile columns. Also reachable via ``POST /imports``.
"""

from __future__ import annotations

import csv
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from intelligence.config import get_settings
from intelligence.ingestion.adapters.base import PersonRef, RawObservationDraft, SourceHealth
from intelligence.models.enums import ContentType, SourceHealthStatus, SourceType


class ManualCSVSource:
    source_name = "manual_csv"
    source_type = SourceType.MANUAL_CSV
    reliability_tier = 3

    def __init__(self, seeds_dir: Path | str | None = None) -> None:
        base = Path(seeds_dir) if seeds_dir else get_settings().seeds_dir
        self._dir = base / "csv"

    def _rows(self, as_of: date) -> list[RawObservationDraft]:
        if not self._dir.exists():
            return []
        cutoff = datetime(as_of.year, as_of.month, as_of.day, 23, 59, 59, tzinfo=UTC)
        drafts: list[RawObservationDraft] = []
        for path in sorted(self._dir.glob("*.csv")):
            with path.open(newline="") as fh:
                for i, row in enumerate(csv.DictReader(fh)):
                    observed = _parse(row.get("observed_at")) or cutoff
                    if observed > cutoff:
                        continue
                    drafts.append(
                        RawObservationDraft(
                            provider_record_id=row.get("record_id") or f"{path.stem}:{i}",
                            content_type=ContentType.CSV_ROW,
                            subject_hint=row.get("person") or row.get("subject_hint"),
                            occurred_at=_parse(row.get("occurred_at")),
                            observed_at=observed,
                            source_url=row.get("source_url"),
                            raw_json={k: v for k, v in row.items() if v not in (None, "")},
                            metadata={"file": path.name},
                        )
                    )
        return drafts

    def discover(self, *, rules: Sequence[object], as_of: date) -> list[RawObservationDraft]:
        return [d for d in self._rows(as_of) if (d.raw_json or {}).get("mode") == "discover"]

    def update_known_entities(
        self, *, people: Sequence[PersonRef], as_of: date
    ) -> list[RawObservationDraft]:
        return [d for d in self._rows(as_of) if (d.raw_json or {}).get("mode") != "discover"]

    def health_check(self) -> SourceHealth:
        n = len(list(self._dir.glob("*.csv"))) if self._dir.exists() else 0
        return SourceHealth(
            source_name=self.source_name,
            status=SourceHealthStatus.SUCCESSFUL if n else SourceHealthStatus.PARTIAL,
            records=n,
        )


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        try:
            return datetime.fromisoformat(f"{value[:10]}T00:00:00").replace(tzinfo=UTC)
        except ValueError:
            return None
