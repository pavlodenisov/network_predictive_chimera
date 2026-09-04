"""Talent V0.1 feature builder — ``person x portfolio_role_need`` (spec §16;
docs/SCORING.md §4). Keys match ``configs/models/talent_v0.1.yaml``.

Availability is a LABELLED INFERENCE unless a ``OPEN_TO_WORK_DECLARED`` fact exists — the
builder never asserts "job searching" from a departure alone (spec §64).
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
    days_since,
    fact_bool,
    fact_number,
    fact_text,
    latest_facts,
)
from intelligence.models import Employment, Organization, PortfolioRoleNeed
from intelligence.models.enums import SENIORITY_LADDER

MODEL_TARGET = "talent"

_TIMING_EVENT_TYPES = {
    "OPEN_TO_WORK_SIGNAL",
    "PROFESSIONAL_DEPARTURE",
    "EMPLOYMENT_ENDED",
    "NEW_EXECUTIVE_ROLE",
    "COMPANY_ACQUIRED",
}

_ADJACENT_FUNCTIONS = {
    "engineering": {"product", "research"},
    "product": {"engineering", "design"},
    "research": {"engineering"},
    "operations": {"finance"},
}


def build(
    session: Session,
    person_id: uuid.UUID,
    as_of: datetime,
    *,
    role_need: PortfolioRoleNeed,
) -> FeatureBundle:
    bundle = FeatureBundle(model_target=MODEL_TARGET, as_of=as_of)
    facts = latest_facts(session, person_id, as_of)
    employments = list(
        session.execute(select(Employment).where(Employment.person_id == person_id)).scalars()
    )

    # ---- functional alignment ------------------------------------------
    person_functions = {e.function for e in employments if e.function}
    if not person_functions:
        bundle.unknown("function_alignment")
    else:
        if role_need.function in person_functions:
            fscore = "exact"
        elif person_functions & _ADJACENT_FUNCTIONS.get(role_need.function, set()):
            fscore = "adjacent"
        else:
            fscore = "none"
        bundle.known("function_alignment", fscore, "tier", [])

    # ---- seniority distance ------------------------------------------
    person_rank = max(
        (SENIORITY_LADDER.get((e.seniority or "").lower(), 0) for e in employments), default=0
    )
    role_rank = SENIORITY_LADDER.get(role_need.seniority.lower(), 0)
    if person_rank == 0:
        bundle.unknown("seniority_distance")
    else:
        bundle.known("seniority_distance", abs(role_rank - person_rank), "ladder_steps", [])

    # ---- domain overlap ------------------------------------------
    headline, _ = fact_text(facts, FactType.HEADLINE_TEXT)
    corpus = " ".join(
        [headline or ""] + [_org_name(session, e.organization_id) for e in employments]
    ).lower()
    reqs = [str(d).lower() for d in (role_need.domain_requirements or [])]
    if not reqs:
        bundle.unknown("domain_overlap")
    else:
        hits = [d for d in reqs if d in corpus]
        bundle.known("domain_overlap", round(len(hits) / len(reqs), 4), "unit", [])
        bundle.fit_evidence["domain_overlap"] = hits

    # ---- stage experience ------------------------------------------
    stage_reqs = {str(s).lower() for s in (role_need.stage_requirements or [])}
    person_stages: set[str] = set()
    for e in employments:
        org = session.get(Organization, e.organization_id)
        if org:
            person_stages.add((org.attributes or {}).get("stage", "").lower())
    person_stages.discard("")
    if not stage_reqs:
        bundle.unknown("stage_overlap")
    elif stage_reqs & person_stages:
        bundle.known("stage_overlap", "match", "tier", [])
    elif person_stages:
        bundle.known("stage_overlap", "adjacent", "tier", [])
    else:
        bundle.known("stage_overlap", "none", "tier", [])

    # ---- operating experience ------------------------------------------
    op_years = _operating_years(employments, as_of)
    if op_years is None:
        bundle.unknown("years_operating")
    else:
        bundle.known("years_operating", op_years, "years", [])

    # ---- execution evidence (subset of founder quality) -----------------
    for name, ft in (
        ("product_shipped", FactType.PRODUCT_SHIPPED),
        ("budget_ownership", FactType.BUDGET_OWNERSHIP),
    ):
        v, ids = fact_bool(facts, ft)
        bundle.known(name, bool(v), "bool", ids)
    n, _, ids = fact_number(facts, FactType.TEAM_SIZE_MANAGED)
    if n is None:
        bundle.unknown("org_built_team_size")
    else:
        bundle.known("org_built_team_size", n, "people", ids)
    n, _, ids = fact_number(facts, FactType.PROMOTION_COUNT)
    bundle.known("promotions", n if n is not None else 0, "count", ids)

    # ---- location alignment ------------------------------------------
    loc_req = role_need.location_requirements or {}
    person_loc = (fact_text(facts, FactType.LOCATION)[0] or "").lower()
    if not person_loc:
        bundle.unknown("location_alignment")
    else:
        bundle.known("location_alignment", _location_tier(loc_req, person_loc), "tier", [])

    # ---- availability timing (labelled inference unless declared) -------
    declared, _ = fact_bool(facts, FactType.OPEN_TO_WORK_DECLARED)
    for ev in active_events(session, person_id, as_of):
        if ev.event_type in _TIMING_EVENT_TYPES:
            bundle.timing_signals.append(
                TimingSignal(
                    event_type="OPEN_TO_WORK_SIGNAL"
                    if (ev.event_type == "OPEN_TO_WORK_SIGNAL" and declared)
                    else ev.event_type,
                    occurred_at=ev.occurred_at,
                    days_since=days_since(ev.occurred_at, as_of),
                    probability=None
                    if declared and ev.event_type == "OPEN_TO_WORK_SIGNAL"
                    else 0.5,
                    evidence_ids=[str(x) for x in (ev.evidence_ids or [])],
                )
            )
    bundle.fit_evidence["availability_is_declared"] = ["true"] if declared else []

    return bundle


def _org_name(session: Session, org_id: uuid.UUID | None) -> str:
    if org_id is None:
        return ""
    org = session.get(Organization, org_id)
    return org.canonical_name if org else ""


def _operating_years(employments: list[Employment], as_of: datetime) -> float | None:
    total = 0.0
    seen = False
    for e in employments:
        if (e.seniority or "").lower() in {"founder", "board", "advisor"}:
            continue
        if not e.started_at:
            continue
        seen = True
        end = e.ended_at or as_of.date()
        total += max(0.0, (end - e.started_at).days / 365.25)
    return round(total, 2) if seen else None


def _location_tier(loc_req: dict, person_loc: str) -> str:
    metro = str(loc_req.get("metro", "")).lower()
    country = str(loc_req.get("country", "")).lower()
    if loc_req.get("remote_ok"):
        return "remote_ok"
    if metro and metro in person_loc:
        return "same_metro"
    if country and country in person_loc:
        return "same_country"
    return "mismatch"
