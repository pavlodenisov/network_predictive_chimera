"""Rank + score deltas vs the previous week (spec §11). Pure arithmetic."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from intelligence.models import ScoreSnapshot
from intelligence.observability import ensure_utc


@dataclass(slots=True)
class RankDelta:
    person_id: uuid.UUID
    current_rank: int | None
    previous_rank: int | None
    rank_change: int | None
    current_score: float
    previous_score: float | None
    score_change: float | None
    top_movers: list[dict]


def rank_delta_summary(session: Session, snapshot: ScoreSnapshot) -> RankDelta:
    prev = None
    if snapshot.previous_score_snapshot_id:
        prev = session.get(ScoreSnapshot, snapshot.previous_score_snapshot_id)
    if prev is None:
        prev = (
            session.execute(
                select(ScoreSnapshot)
                .where(
                    ScoreSnapshot.person_id == snapshot.person_id,
                    ScoreSnapshot.scoring_model_id == snapshot.scoring_model_id,
                    ScoreSnapshot.scored_at < ensure_utc(snapshot.scored_at),
                )
                .order_by(ScoreSnapshot.scored_at.desc())
            )
            .scalars()
            .first()
        )

    prev_rank = prev.rank if prev else None
    prev_score = prev.priority_score if prev else None
    rank_change = (
        (prev_rank - snapshot.rank)
        if (prev_rank is not None and snapshot.rank is not None)
        else None
    )
    score_change = (
        round(snapshot.priority_score - prev_score, 4) if prev_score is not None else None
    )
    movers = (snapshot.delta_breakdown or {}).get("top_movers", [])
    return RankDelta(
        person_id=snapshot.person_id,
        current_rank=snapshot.rank,
        previous_rank=prev_rank,
        rank_change=rank_change,
        current_score=round(snapshot.priority_score, 4),
        previous_score=round(prev_score, 4) if prev_score is not None else None,
        score_change=score_change,
        top_movers=movers[:8],
    )
