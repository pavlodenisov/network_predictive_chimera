"""Acceptance scenario §62 — the 15-step Sarah Chen founder chain.

Week 1: Staff ML Engineer at Synthetic AI Labs, 5.4y ML infra, prior founder, one moderate
Chimera relationship. Week 2: employment ended, headline -> "building", news references a
new infrastructure project. The system must produce the full explainable chain.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from intelligence.facts import FactType, is_unknown
from intelligence.models import (
    Event,
    Evidence,
    Fact,
    Inference,
    Person,
    RawObservation,
    ScoreSnapshot,
    ScoringModel,
)

pytestmark = pytest.mark.acceptance


def _sarah(ro):
    return (
        ro.execute(
            select(Person).where(
                Person.canonical_name == "Sarah Chen", Person.merged_into_id.is_(None)
            )
        )
        .scalars()
        .first()
    )


def _founder_snaps(ro, person_id):
    return (
        ro.execute(
            select(ScoreSnapshot)
            .join(ScoringModel, ScoringModel.id == ScoreSnapshot.scoring_model_id)
            .where(ScoreSnapshot.person_id == person_id, ScoringModel.name == "founder")
            .order_by(ScoreSnapshot.scored_at)
        )
        .scalars()
        .all()
    )


def test_sarah_chen_full_chain(ro):
    sarah = _sarah(ro)
    assert sarah is not None

    # 1. Raw observations stored (week-2 snapshot + news)
    obs = (
        ro.execute(select(RawObservation).where(RawObservation.subject_hint == "Sarah Chen"))
        .scalars()
        .all()
    )
    assert any(o.content_type == "profile_snapshot" for o in obs)
    assert any(o.content_type == "news_article" for o in obs)

    facts = (
        ro.execute(select(Fact).where(Fact.subject_id == sarah.id, Fact.superseded_by_id.is_(None)))
        .scalars()
        .all()
    )
    ft = {f.fact_type for f in facts}

    # 2. Employment-end fact created
    assert FactType.EMPLOYMENT_ENDED_AT in ft
    # 3. Headline-change fact created
    assert FactType.HEADLINE_CHANGED in ft

    # every fact traces to evidence -> an immutable observation (provenance chain §70)
    for f in facts:
        ev = ro.execute(select(Evidence).where(Evidence.fact_id == f.id)).scalars().all()
        assert ev, f"{f.fact_type} has no evidence"
        for e in ev:
            assert ro.get(RawObservation, e.observation_id) is not None

    # 4. EMPLOYMENT_ENDED event created
    events = ro.execute(select(Event).where(Event.person_id == sarah.id)).scalars().all()
    assert any(e.event_type == "EMPLOYMENT_ENDED" for e in events)
    # ... and it is a factual event, not an inference
    assert all(e.event_type != "POSSIBLE_COMPANY_FORMATION" for e in events)

    # 5. POSSIBLE_COMPANY_FORMATION inference created (labelled, probabilistic)
    infs = ro.execute(select(Inference).where(Inference.person_id == sarah.id)).scalars().all()
    pcf = [i for i in infs if i.inference_type == "POSSIBLE_COMPANY_FORMATION"]
    assert pcf
    assert 0.0 < pcf[0].probability <= 0.85
    assert pcf[0].model_version

    snaps = _founder_snaps(ro, sarah.id)
    assert len(snaps) >= 2, "expected a week-1 baseline and a week-2 snapshot"
    week1, week2 = snaps[0], snaps[-1]

    # 6. Timing features increase
    assert (week2.timing_score or 0) > (week1.timing_score or 0)
    # 7. Founder score rises
    assert week2.priority_score > week1.priority_score
    # 8. ScoreSnapshot stored (with model version + feature snapshot ref)
    assert week2.scoring_model_id is not None
    assert week2.feature_snapshot_id is not None
    # 9. Delta calculated
    assert week2.delta_breakdown is not None
    assert week2.delta_breakdown["priority_delta"] == pytest.approx(
        week2.priority_score - week1.priority_score, abs=0.01
    )
    # 10. Person moves upward in ranking
    assert week2.rank is not None and week1.rank is not None
    assert week2.rank < week1.rank

    # 11. Intelligence feed (digest) shows the new position
    from intelligence.models import WeeklyRun

    run = ro.execute(select(WeeklyRun).order_by(WeeklyRun.started_at.desc())).scalars().first()
    increases = run.digest["sections"]["largest_founder_score_increases"]
    assert any(r["person"] == "Sarah Chen" for r in increases)

    # 12. Clicking the delta shows mathematical contribution
    movers = week2.delta_breakdown["top_movers"]
    assert any("EMPLOYMENT_ENDED" in m["feature"] for m in movers)
    dims = week2.contribution_breakdown["dimensions"]
    recomputed = sum(d["weighted"] for d in dims.values())
    assert recomputed == pytest.approx(week2.priority_score, abs=0.05)

    # 13. Clicking evidence reveals the original source record
    ended_fact = next(f for f in facts if f.fact_type == FactType.EMPLOYMENT_ENDED_AT)
    ev = ro.execute(select(Evidence).where(Evidence.fact_id == ended_fact.id)).scalars().first()
    src_obs = ro.get(RawObservation, ev.observation_id)
    assert src_obs is not None and src_obs.raw_json is not None

    # 14. Confidence remains visible and separate from priority
    assert 0.0 <= week2.confidence_score <= 1.0
    assert week2.confidence_score != week2.priority_score
    assert week2.contribution_breakdown["confidence"]["score"] == week2.confidence_score

    # 15. Unknown fundraising status remains UNKNOWN
    fs = next((f for f in facts if f.fact_type == FactType.FUNDRAISING_STATUS), None)
    assert fs is not None
    assert is_unknown(fs.structured_value)
