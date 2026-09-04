"""Shared fixture loading for the offline adapters (Synthetic / JSON snapshot / CSV / RSS).

Each fixture draft is a JSON object with the ``RawObservationDraft`` fields plus two
adapter-only keys:
  ``mode``:  "update" (default) | "discover"
  ``as_of`` / ``observed_at``: ISO date/datetime — a draft is visible only when
      ``observed_at <= run as_of`` (point-in-time correctness for backtests, spec §35).
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

from intelligence.ingestion.adapters.base import RawObservationDraft


def _parse_dt(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value)
    for parser in (datetime.fromisoformat, lambda s: datetime.fromisoformat(f"{s[:10]}T00:00:00")):
        try:
            dt = parser(text)
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def draft_from_dict(d: dict) -> tuple[RawObservationDraft, str]:
    mode = str(d.get("mode", "update"))
    observed = _parse_dt(d.get("observed_at") or d.get("as_of")) or datetime.now(tz=UTC)
    draft = RawObservationDraft(
        provider_record_id=d.get("provider_record_id"),
        content_type=d.get("content_type", "json_record"),
        subject_hint=d.get("subject_hint"),
        occurred_at=_parse_dt(d.get("occurred_at")),
        observed_at=observed,
        source_url=d.get("source_url"),
        raw_text=d.get("raw_text"),
        raw_json=d.get("raw_json"),
        metadata=d.get("metadata", {}),
        previous_snapshot=d.get("previous_snapshot"),
    )
    return draft, mode


def load_fixture_drafts(directory: Path, *, as_of: date, mode: str) -> list[RawObservationDraft]:
    if not directory.exists():
        return []
    cutoff = datetime(as_of.year, as_of.month, as_of.day, 23, 59, 59, tzinfo=UTC)
    out: list[RawObservationDraft] = []
    for path in sorted(directory.glob("*.json")):
        payload = json.loads(path.read_text())
        rows = payload if isinstance(payload, list) else payload.get("observations", [])
        for row in rows:
            draft, row_mode = draft_from_dict(row)
            if row_mode != mode:
                continue
            if draft.observed_at and draft.observed_at > cutoff:
                continue  # not knowable yet at `as_of`
            out.append(draft)
    return out
