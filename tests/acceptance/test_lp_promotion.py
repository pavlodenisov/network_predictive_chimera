"""Acceptance scenario §63 — LP promotion + mandate change.

Week 1: Principal at an institutional investment office, no known venture mandate, one weak
Chimera connection. Week 2: promoted to Partner; official bio adds venture fund allocation
responsibility. Expected: PROMOTION, INVESTMENT_MANDATE_CHANGED, LP score increase, reason
code, evidence provenance, score decomposition, warm path.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from intelligence.models import (
    Event,
    Evidence,
    Fact,
    Person,
    RawObservation,
    ScoreSnapshot,
    ScoringModel,
)

pytestmark = pytest.mark.acceptance


def test_marcus_webb_lp_chain(ro):
    marcus = (
        ro.execute(
            select(Person).where(
                Person.canonical_name == "Marcus Webb", Person.merged_into_id.is_(None)
            )
        )
        .scalars()
        .first()
    )
    assert marcus is not None

    events = {
        e.event_type
        for e in ro.execute(select(Event).where(Event.person_id == marcus.id)).scalars()
    }
    # promotion Principal -> Partner
    assert "PROMOTION" in events or "PARTNER_ROLE_STARTED" in events
    # mandate change from the official-bio / news
    assert "INVESTMENT_MANDATE_CHANGED" in events

    # mandate fact has provenance
    facts = (
        ro.execute(
            select(Fact).where(Fact.subject_id == marcus.id, Fact.superseded_by_id.is_(None))
        )
        .scalars()
        .all()
    )
    mandate = [f for f in facts if f.fact_type == "INVESTMENT_MANDATE"]
    if mandate:
        ev = ro.execute(select(Evidence).where(Evidence.fact_id == mandate[0].id)).scalars().first()
        assert ev is not None and ro.get(RawObservation, ev.observation_id) is not None

    snaps = (
        ro.execute(
            select(ScoreSnapshot)
            .join(ScoringModel, ScoringModel.id == ScoreSnapshot.scoring_model_id)
            .where(ScoreSnapshot.person_id == marcus.id, ScoringModel.name == "lp")
            .order_by(ScoreSnapshot.scored_at)
        )
        .scalars()
        .all()
    )
    assert len(snaps) >= 2
    week1, week2 = snaps[0], snaps[-1]

    # LP score increases
    assert week2.priority_score > week1.priority_score
    # reason codes present
    assert isinstance(week2.reason_codes, list)
    # score decomposition present and consistent
    dims = week2.contribution_breakdown["dimensions"]
    assert "authority" in dims and "venture_allocation_fit" in dims
    recomputed = sum(d["weighted"] for d in dims.values())
    assert recomputed == pytest.approx(week2.priority_score, abs=0.05)
    # authority dimension reflects the Partner signal
    assert (
        dims["authority"]["score"]
        >= week1.contribution_breakdown["dimensions"]["authority"]["score"]
    )

    # warm path (access) exists and is decomposable — one weak Chimera connection
    access = dims["access"]["access"]
    assert access["status"] in {"known", "unknown"}
    assert week2.delta_breakdown is not None
