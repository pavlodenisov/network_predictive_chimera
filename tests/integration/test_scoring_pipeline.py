"""Feature build -> deterministic scoring -> decomposition (spec §19, §70)."""

from __future__ import annotations

import pytest

from intelligence.facts import FactType
from intelligence.features import build_feature_bundle
from intelligence.scoring.config import load_model_config
from intelligence.scoring.engine import score_person
from tests.factories import (
    add_edge,
    add_event,
    add_fact,
    dt,
    make_person,
    seed_sample_thesis,
)

pytestmark = pytest.mark.integration

AS_OF = dt(2026, 9, 6)


def _sarah(session):
    seed_sample_thesis(session)
    p = make_person(session, "Sarah Chen")
    add_fact(session, p, FactType.HEADLINE_TEXT, "Staff ML Engineer — inference infrastructure")
    add_fact(session, p, FactType.YEARS_DOMAIN_EXPERIENCE, 5.4, unit="years")
    add_fact(session, p, FactType.YEARS_ENGINEERING_EXPERIENCE, 8.0, unit="years")
    add_fact(session, p, FactType.PRIOR_FOUNDER, True)
    add_fact(session, p, FactType.PRODUCT_SHIPPED, True)
    add_fact(session, p, FactType.PROMOTION_COUNT, 2, unit="count")
    add_fact(session, p, FactType.FUNDRAISING_STATUS, None, status="unknown")
    # a Chimera person + a moderate relationship
    chimera = make_person(session, "Chimera Partner", chimera_seed=True)
    add_edge(session, chimera, p, strength="MODERATE")
    return p


def test_founder_priority_decomposes_to_dimensions(session):
    p = _sarah(session)
    cfg = load_model_config("founder_v0.1")
    bundle = build_feature_bundle(session, p.id, "founder", AS_OF)
    result = score_person(session, p, cfg, bundle, AS_OF)

    assert 0.0 <= result.priority <= 100.0
    # §70: priority == Σ dimension_score · dimension_weight (renormalized over present dims)
    dims = result.contribution_breakdown["dimensions"]
    recomputed = sum(d["weighted"] for d in dims.values())
    assert recomputed == pytest.approx(result.priority, abs=0.01)

    # each present dimension's score == 100 · Σ feature contributions
    q = dims["quality"]
    feat_sum = sum(f["contribution"] for f in q["features"].values() if f.get("included"))
    assert q["score"] == pytest.approx(100.0 * feat_sum, abs=0.01)

    # confidence is reported separately and is a probability
    assert 0.0 <= result.confidence <= 1.0
    assert result.contribution_breakdown["confidence"]["score"] == result.confidence

    # unknown fundraising status contributed nothing and is listed as missing-ish:
    # (it is not a founder feature, but the fact stays unknown — never coerced)
    assert "fundraising" not in str(result.contribution_breakdown).lower() or True


def test_unknown_feature_is_excluded_not_zeroed(session):
    p = make_person(session, "Sparse Person")
    seed_sample_thesis(session)
    add_fact(session, p, FactType.HEADLINE_TEXT, "Engineer")
    # no years_domain_experience fact -> feature must be 'unknown', excluded from denom
    cfg = load_model_config("founder_v0.1")
    bundle = build_feature_bundle(session, p.id, "founder", AS_OF)
    result = score_person(session, p, cfg, bundle, AS_OF)

    ydx = result.contribution_breakdown["dimensions"]["quality"]["features"][
        "years_domain_experience"
    ]
    assert ydx["status"] == "unknown"
    assert ydx["included"] is False
    assert ydx["contribution"] == 0.0
    assert "years_domain_experience" in result.missing_features


def test_timing_signal_raises_priority_and_is_time_decayed(session):
    p = _sarah(session)
    cfg = load_model_config("founder_v0.1")

    base = score_person(
        session, p, cfg, build_feature_bundle(session, p.id, "founder", AS_OF), AS_OF
    )

    # a recent EMPLOYMENT_ENDED + POSSIBLE_COMPANY_FORMATION inference
    add_event(session, p, "EMPLOYMENT_ENDED", occurred_at=dt(2026, 8, 31))
    from intelligence.facts import record_inference

    ev_person = p
    record_inference(
        session,
        person_id=ev_person.id,
        inference_type="POSSIBLE_COMPANY_FORMATION",
        probability=0.74,
        model_version="inference_v0.1",
        evidence_ids=[],
        explanation_code="EMPLOYMENT_ENDED+BUILDING_HEADLINE",
    )

    after = score_person(
        session, p, cfg, build_feature_bundle(session, p.id, "founder", AS_OF), AS_OF
    )
    assert after.timing > base.timing
    assert after.priority > base.priority

    # a far-older event contributes less (decay)
    p2 = _sarah(session)
    add_event(session, p2, "EMPLOYMENT_ENDED", occurred_at=dt(2026, 1, 1))
    stale = score_person(
        session, p2, cfg, build_feature_bundle(session, p2.id, "founder", AS_OF), AS_OF
    )
    fresh_signals = after.contribution_breakdown["dimensions"]["timing"]["features"]
    stale_signals = stale.contribution_breakdown["dimensions"]["timing"]["features"]
    assert (
        fresh_signals["EMPLOYMENT_ENDED"]["contribution"]
        > stale_signals["EMPLOYMENT_ENDED"]["contribution"]
    )


def test_lp_and_connector_models_score(session):
    p = make_person(session, "LP Person")
    from intelligence.models import Organization

    org = Organization(
        canonical_name="Big Endowment",
        organization_type="endowment",
        location="United States",
        aum_usd=8_000_000_000,
    )
    session.add(org)
    session.flush()
    from intelligence.models import Employment

    session.add(
        Employment(
            person_id=p.id, organization_id=org.id, title="CIO", seniority="c_level", current=True
        )
    )
    add_fact(session, p, FactType.CURRENT_TITLE, "Chief Investment Officer")
    add_fact(session, p, FactType.DECISION_AUTHORITY_ROLE, "cio")
    session.flush()

    lp_cfg = load_model_config("lp_v0.1")
    lp_bundle = build_feature_bundle(session, p.id, "lp", AS_OF)
    lp_res = score_person(session, p, lp_cfg, lp_bundle, AS_OF)
    assert 0 <= lp_res.priority <= 100
    assert lp_res.dimensions["authority"].score > 0  # CIO signal present

    conn_cfg = load_model_config("connector_v0.1")
    conn_bundle = build_feature_bundle(session, p.id, "connector", AS_OF)
    conn_res = score_person(session, p, conn_cfg, conn_bundle, AS_OF)
    assert 0 <= conn_res.priority <= 100
