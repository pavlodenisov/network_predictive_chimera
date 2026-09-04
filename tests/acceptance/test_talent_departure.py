"""Acceptance scenario §64 — talent departure + role match.

Person: VP Engineering at a synthetic fintech company. New observation: employment ended.
Portfolio role: VP Engineering, Series B fintech portfolio company. Expected:
PROFESSIONAL_DEPARTURE event, candidate-role match with a score, availability inference
clearly labelled, network path, talent ranking update. The system must NOT state the
candidate is job searching without evidence.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from intelligence.models import (
    CandidateRoleMatch,
    Event,
    Fact,
    Person,
    PortfolioRoleNeed,
    ScoreSnapshot,
    ScoringModel,
)

pytestmark = pytest.mark.acceptance


def test_priya_nair_talent_chain(ro):
    priya = (
        ro.execute(
            select(Person).where(
                Person.canonical_name == "Priya Nair", Person.merged_into_id.is_(None)
            )
        )
        .scalars()
        .first()
    )
    assert priya is not None

    events = {
        e.event_type for e in ro.execute(select(Event).where(Event.person_id == priya.id)).scalars()
    }
    assert "EMPLOYMENT_ENDED" in events
    assert "PROFESSIONAL_DEPARTURE" in events  # talent lens, derived

    # NO "job searching" fact was invented — availability stays an inference unless declared
    facts = {
        f.fact_type for f in ro.execute(select(Fact).where(Fact.subject_id == priya.id)).scalars()
    }
    assert "OPEN_TO_WORK_DECLARED" not in facts

    # candidate <-> role match with a score + breakdown
    matches = (
        ro.execute(select(CandidateRoleMatch).where(CandidateRoleMatch.person_id == priya.id))
        .scalars()
        .all()
    )
    assert matches, "expected at least one portfolio role match"
    assert all(0.0 <= m.score <= 100.0 for m in matches)
    assert all(m.score_breakdown for m in matches)

    # the VP Engineering / fintech role should be the person's best match
    roles = {r.id: r for r in ro.execute(select(PortfolioRoleNeed)).scalars()}
    best = max(matches, key=lambda m: m.score)
    best_role = roles[best.portfolio_role_need_id]
    assert best_role.role_title == "VP Engineering"

    # talent ranking updated
    snaps = (
        ro.execute(
            select(ScoreSnapshot)
            .join(ScoringModel, ScoringModel.id == ScoreSnapshot.scoring_model_id)
            .where(ScoreSnapshot.person_id == priya.id, ScoringModel.name == "talent")
            .order_by(ScoreSnapshot.scored_at)
        )
        .scalars()
        .all()
    )
    assert len(snaps) >= 2
    assert snaps[-1].priority_score > snaps[0].priority_score
    assert snaps[-1].rank is not None

    # availability is a labelled inference feeding the timing dimension — not a fact
    dims = snaps[-1].contribution_breakdown["dimensions"]
    assert "availability_timing" in dims
    assert dims["availability_timing"]["features"], "departure should feed availability timing"
    assert (dims["availability_timing"]["score"] or 0) > 0
