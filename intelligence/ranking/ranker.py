"""Assign rank + percentile to a set of score snapshots within a universe (spec §53)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from intelligence.models import ScoreSnapshot


@dataclass(slots=True)
class RankedRow:
    snapshot_id: uuid.UUID
    person_id: uuid.UUID
    priority: float
    rank: int
    percentile: float


def rank_snapshots(
    session: Session,
    snapshots: list[ScoreSnapshot],
    *,
    universe_id: uuid.UUID | None = None,
) -> list[RankedRow]:
    """Rank descending by ``priority_score`` (ties share a rank; standard competition
    ranking). Percentile = share of the universe with priority <= this row."""
    ordered = sorted(snapshots, key=lambda s: (-(s.priority_score or 0.0), str(s.person_id)))
    n = len(ordered)
    out: list[RankedRow] = []
    prev_score: float | None = None
    prev_rank = 0
    for i, snap in enumerate(ordered, start=1):
        score = snap.priority_score or 0.0
        rank = prev_rank if (prev_score is not None and abs(score - prev_score) < 1e-9) else i
        at_or_below = sum(1 for s in ordered if (s.priority_score or 0.0) <= score)
        percentile = round(100.0 * at_or_below / n, 2) if n else 0.0

        snap.rank = rank
        snap.percentile = percentile
        if universe_id is not None:
            snap.rank_universe_id = universe_id
        out.append(RankedRow(snap.id, snap.person_id, score, rank, percentile))
        prev_score, prev_rank = score, rank
    session.flush()
    return out
