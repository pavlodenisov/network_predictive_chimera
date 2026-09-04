"""Founder V0.1 feature builder (spec §11-13; docs/SCORING.md §2).

Reads facts / events / inferences / employment for a person as of ``as_of`` and produces
a ``FeatureBundle`` whose keys match ``configs/models/founder_v0.1.yaml``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from intelligence.facts import FactType
from intelligence.features.base import (
    FeatureBundle,
    TimingSignal,
    active_events,
    active_inferences,
    days_since,
    fact_bool,
    fact_number,
    fact_text,
    latest_facts,
)
from intelligence.features.freshness import bucket_for_fact, freshness_entry
from intelligence.features.thesis import (
    active_thesis,
    dimension_match,
    person_corpus,
    portfolio_adjacency,
)
from intelligence.models import Employment, Organization

MODEL_TARGET = "founder"

# events / inference types that feed the founder timing dimension
_TIMING_EVENT_TYPES = {
    "EMPLOYMENT_ENDED",
    "FOUNDER_TITLE_ADDED",
    "STEALTH_COMPANY_SIGNAL",
    "POSSIBLE_COMPANY_FORMATION",
    "COMPANY_FORMATION_CONFIRMED",
    "PRODUCT_LAUNCH",
    "FUNDRAISE_ANNOUNCED",
    "COFOUNDER_SEARCH",
    "HIRING_STARTED",
    "DOMAIN_ACTIVITY_SPIKE",
}

_NUMERIC_FACTS: tuple[tuple[str, str, str], ...] = (
    ("years_domain_experience", FactType.YEARS_DOMAIN_EXPERIENCE, "years"),
    ("years_engineering_experience", FactType.YEARS_ENGINEERING_EXPERIENCE, "years"),
    ("research_depth", FactType.PUBLICATION_COUNT, "count"),
    ("patents", FactType.PATENT_COUNT, "count"),
    ("early_employee_rank", FactType.EARLY_EMPLOYEE_RANK, "rank"),
    ("promotions", FactType.PROMOTION_COUNT, "count"),
    ("time_to_leadership_years", FactType.TIME_TO_LEADERSHIP_YEARS, "years"),
)

_BOOL_FACTS: tuple[tuple[str, str], ...] = (
    ("prior_exit", FactType.PRIOR_EXIT),
    ("institutional_fundraise", FactType.INSTITUTIONAL_FUNDRAISE),
    ("product_shipped", FactType.PRODUCT_SHIPPED),
    ("verified_scale_milestone", FactType.VERIFIED_SCALE_MILESTONE),
    ("oss_major", FactType.OSS_PROJECT_MAJOR),
    ("budget_ownership", FactType.BUDGET_OWNERSHIP),
    ("prestige_weak_signal", FactType.PRESTIGE_FLAG),
)


def build(session: Session, person_id: uuid.UUID, as_of: datetime) -> FeatureBundle:
    bundle = FeatureBundle(model_target=MODEL_TARGET, as_of=as_of)
    facts = latest_facts(session, person_id, as_of)

    # ---- QUALITY ---------------------------------------------------------
    for name, ft in _BOOL_FACTS:
        bval, bids = fact_bool(facts, ft)
        if bval is None:
            # binary features default to 0 (missing_behavior: zero in the config) but we
            # still record them present-as-false so contribution math is complete
            bundle.known(name, False, "bool", [])
        else:
            bundle.known(name, bval, "bool", bids, verified_at=_vf(facts, ft))

    for name, ft, unit in _NUMERIC_FACTS:
        nval, u, nids = fact_number(facts, ft)
        if nval is None:
            bundle.unknown(name)
        else:
            bundle.known(name, nval, u or unit, nids, verified_at=_vf(facts, ft))
            bundle.freshness[name] = freshness_entry(
                verified_at=_vf(facts, ft), as_of=as_of, bucket=bucket_for_fact(ft)
            )

    # prior_founder: prefer COMPANIES_FOUNDED_COUNT, fall back to PRIOR_FOUNDER bool
    n, _, ids = fact_number(facts, FactType.COMPANIES_FOUNDED_COUNT)
    if n is not None:
        bundle.known("prior_founder", n, "count", ids)
    else:
        b, bids = fact_bool(facts, FactType.PRIOR_FOUNDER)
        if b is None:
            bundle.known("prior_founder", 0, "count", [])
        else:
            bundle.known("prior_founder", 1 if b else 0, "count", bids)

    # org_built_team_size
    n, _, ids = fact_number(facts, FactType.TEAM_SIZE_MANAGED)
    if n is None:
        bundle.unknown("org_built_team_size")
    else:
        bundle.known("org_built_team_size", n, "people", ids)

    # ---- FIT -----------------------------------------------------------
    headline, _ = fact_text(facts, FactType.HEADLINE_TEXT)
    location, _ = fact_text(facts, FactType.LOCATION)
    thesis = active_thesis(session)
    corpus = person_corpus(session, person_id, headline, location)
    if thesis is None:
        for f in (
            "sector_match",
            "technology_match",
            "technical_topic_match",
            "business_model_match",
            "stage_match",
            "geography_match",
            "portfolio_adjacency",
        ):
            bundle.unknown(f)
    else:
        mapping = {
            "sector_match": thesis.sectors,
            "technology_match": thesis.technologies,
            "technical_topic_match": thesis.technical_topics,
            "business_model_match": thesis.business_models,
            "stage_match": thesis.stages,
            "geography_match": thesis.geographies,
        }
        for fname, phrases in mapping.items():
            score, hits = dimension_match(corpus, list(phrases or []))
            bundle.known(fname, score, "unit_similarity", [])
            bundle.fit_evidence[fname] = hits
        padj, phits = portfolio_adjacency(session, corpus)
        bundle.known("portfolio_adjacency", padj, "unit_similarity", [])
        bundle.fit_evidence["portfolio_adjacency"] = phits

    # embedding similarity: unknown until a provider is configured (never silently 0)
    if thesis is not None and thesis.embedding_model:
        bundle.known("thesis_embedding_similarity", 0.0, "cosine", [])  # placeholder wiring
    else:
        bundle.unknown("thesis_embedding_similarity")

    # ---- TIMING (decay signals) ------------------------------------------
    for ev in active_events(session, person_id, as_of):
        if ev.event_type in _TIMING_EVENT_TYPES:
            bundle.timing_signals.append(
                TimingSignal(
                    event_type=ev.event_type,
                    occurred_at=ev.occurred_at,
                    days_since=days_since(ev.occurred_at, as_of),
                    evidence_ids=[str(x) for x in (ev.evidence_ids or [])],
                )
            )
    for inf in active_inferences(session, person_id, as_of):
        if inf.inference_type in _TIMING_EVENT_TYPES:
            bundle.timing_signals.append(
                TimingSignal(
                    event_type=inf.inference_type,
                    occurred_at=inf.created_at,
                    days_since=days_since(inf.created_at, as_of),
                    probability=inf.probability,
                    evidence_ids=[str(x) for x in (inf.evidence_ids or [])],
                )
            )

    return bundle


def _vf(facts, fact_type: str) -> datetime | None:
    f = facts.get(fact_type)
    return f.valid_from if f else None


def current_and_prior_orgs(session: Session, person_id: uuid.UUID) -> list[Organization]:
    return list(
        session.execute(
            select(Organization)
            .join(Employment, Employment.organization_id == Organization.id)
            .where(Employment.person_id == person_id)
        ).scalars()
    )
