"""Draft -> immutable ``RawObservation`` (spec §4-5).

Deduplicates on ``(source_id, provider_record_id)`` and ``content_hash`` so re-runs and
multi-week runs never double-ingest. ``RawObservation`` is append-only.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from intelligence.ingestion.adapters.base import RawObservationDraft
from intelligence.ingestion.dedupe import assign_story_cluster, content_hash
from intelligence.models import RawObservation, Source
from intelligence.observability import now_utc


@dataclass(slots=True)
class IngestResult:
    persisted: list[RawObservation]
    skipped_duplicates: int
    total: int


def _existing_hashes(session: Session, source_id, hashes: set[str]) -> set[str]:
    if not hashes:
        return set()
    rows = session.execute(
        select(RawObservation.content_hash).where(RawObservation.content_hash.in_(hashes))
    ).scalars()
    return set(rows)


def _existing_provider_ids(session: Session, source_id, provider_ids: set[str]) -> set[str]:
    if not provider_ids:
        return set()
    rows = session.execute(
        select(RawObservation.provider_record_id).where(
            RawObservation.source_id == source_id,
            RawObservation.provider_record_id.in_(provider_ids),
        )
    ).scalars()
    return {r for r in rows if r}


def persist_drafts(
    session: Session,
    source: Source,
    drafts: list[RawObservationDraft],
) -> IngestResult:
    now = now_utc()
    hashed = [(d, content_hash(d)) for d in drafts]
    seen_hashes = _existing_hashes(session, source.id, {h for _, h in hashed})
    seen_pids = _existing_provider_ids(
        session, source.id, {d.provider_record_id for d in drafts if d.provider_record_id}
    )

    persisted: list[RawObservation] = []
    skipped = 0
    batch_hashes: set[str] = set()
    for draft, chash in hashed:
        if chash in seen_hashes or chash in batch_hashes:
            skipped += 1
            continue
        if draft.provider_record_id and draft.provider_record_id in seen_pids:
            skipped += 1
            continue
        batch_hashes.add(chash)

        metadata = dict(draft.metadata)
        if draft.previous_snapshot is not None:
            metadata["previous_snapshot"] = draft.previous_snapshot

        obs = RawObservation(
            source_id=source.id,
            provider_record_id=draft.provider_record_id,
            subject_hint=draft.subject_hint,
            occurred_at=draft.occurred_at,
            observed_at=draft.observed_at or now,
            ingested_at=now,
            source_url=draft.source_url,
            content_type=str(draft.content_type),
            raw_text=draft.raw_text,
            raw_json=draft.raw_json,
            content_hash=chash,
            obs_metadata=metadata,
        )
        session.add(obs)
        session.flush()
        assign_story_cluster(session, obs)
        persisted.append(obs)

    return IngestResult(persisted=persisted, skipped_duplicates=skipped, total=len(drafts))
