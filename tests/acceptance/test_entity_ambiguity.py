"""Acceptance scenario §65 — data-quality / entity ambiguity.

Two different people named "Alex Lee": one worked at Stripe, one at Google. A new article
mentions "Alex Lee". The system must NOT automatically merge the article with either
individual and must create an ambiguous entity-resolution record for analyst review.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from intelligence.models import (
    EntityMergeLog,
    EntityResolutionResult,
    Person,
)
from intelligence.models.enums import ResolutionDecision

pytestmark = pytest.mark.acceptance


def test_two_alex_lee_are_not_merged(ro):
    alexes = (
        ro.execute(
            select(Person).where(
                Person.canonical_name == "Alex Lee", Person.merged_into_id.is_(None)
            )
        )
        .scalars()
        .all()
    )
    # both Alex Lee rows still exist and neither was merged away
    assert len(alexes) == 2
    assert all(a.merged_into_id is None for a in alexes)

    # no auto-merge happened for these people
    merges = ro.execute(select(EntityMergeLog)).scalars().all()
    alex_ids = {a.id for a in alexes}
    assert not any(m.loser_person_id in alex_ids or m.winner_person_id in alex_ids for m in merges)

    # an ambiguous entity-resolution record exists for the "Alex Lee" mention
    ambiguous = (
        ro.execute(
            select(EntityResolutionResult).where(
                EntityResolutionResult.decision == ResolutionDecision.AMBIGUOUS
            )
        )
        .scalars()
        .all()
    )
    assert ambiguous, "expected an AMBIGUOUS entity-resolution record"
    alex_amb = [
        r for r in ambiguous if (r.scorecard or {}).get("candidate_name", "").lower() == "alex lee"
    ]
    assert alex_amb
    rec = alex_amb[0]
    assert rec.auto_applied is False
    assert rec.matched_person_id is None
    assert len(rec.competing_person_ids) == 2

    # the ambiguity did not silently create a 3rd "Alex Lee" or attach to one
    assert (
        ro.scalar(
            select(func.count()).select_from(Person).where(Person.canonical_name == "Alex Lee")
        )
        == 2
    )
