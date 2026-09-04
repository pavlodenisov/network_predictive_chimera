"""Every ranking specifies its universe (spec §54). Rank is meaningless without it."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from intelligence.models import RankingUniverse


@dataclass(slots=True)
class UniverseSpec:
    label: str
    model_target: str
    scoring_model_id: uuid.UUID | None
    as_of_date: date
    filter: dict = field(default_factory=dict)

    def key(self) -> str:
        parts = [self.model_target, str(self.scoring_model_id), self.as_of_date.isoformat()]
        parts += [f"{k}={v}" for k, v in sorted(self.filter.items())]
        return "|".join(parts)


def ensure_universe(session: Session, spec: UniverseSpec, member_count: int) -> RankingUniverse:
    existing = (
        session.execute(
            select(RankingUniverse).where(
                RankingUniverse.model_target == spec.model_target,
                RankingUniverse.as_of_date == spec.as_of_date,
                RankingUniverse.label == spec.label,
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        existing.member_count = member_count
        existing.filter = spec.filter
        existing.scoring_model_id = spec.scoring_model_id
        session.flush()
        return existing
    row = RankingUniverse(
        label=spec.label,
        model_target=spec.model_target,
        scoring_model_id=spec.scoring_model_id,
        filter=spec.filter,
        as_of_date=spec.as_of_date,
        member_count=member_count,
    )
    session.add(row)
    session.flush()
    return row
