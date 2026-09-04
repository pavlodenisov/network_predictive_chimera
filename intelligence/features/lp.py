"""LP V0.1 feature builder (spec §15; docs/SCORING.md §3). Keys match
``configs/models/lp_v0.1.yaml``. Never speculates about private personal wealth.
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
from intelligence.features.thesis import active_thesis
from intelligence.models import Employment, Organization

MODEL_TARGET = "lp"

_ALLOCATOR_TYPES = {"family_office", "endowment", "foundation", "fund_of_funds", "fund"}

_TIMING_EVENT_TYPES = {
    "CIO_ROLE_STARTED",
    "PARTNER_ROLE_STARTED",
    "INVESTMENT_MANDATE_CHANGED",
    "LP_ROLE_STARTED",
    "FAMILY_OFFICE_ROLE_STARTED",
    "VENTURE_ALLOCATION_SIGNAL",
    "EMERGING_MANAGER_SIGNAL",
    "INVESTMENT_COMMITTEE_ROLE",
}

_AUTHORITY_ROLES = {
    "is_cio": ("cio", "chief investment officer"),
    "is_partner": ("partner",),
    "is_head_of_venture": ("head of venture", "head of ventures"),
    "is_head_of_alternatives": ("head of alternatives", "head of alts"),
    "is_family_office_lead": ("family office lead", "family office investment lead"),
}


def build(session: Session, person_id: uuid.UUID, as_of: datetime) -> FeatureBundle:
    bundle = FeatureBundle(model_target=MODEL_TARGET, as_of=as_of)
    facts = latest_facts(session, person_id, as_of)
    events = active_events(session, person_id, as_of)
    event_types = {e.event_type for e in events}

    authority_text = " ".join(
        [
            (fact_text(facts, FactType.DECISION_AUTHORITY_ROLE)[0] or ""),
            (fact_text(facts, FactType.CURRENT_TITLE)[0] or ""),
            (fact_text(facts, FactType.HEADLINE_TEXT)[0] or ""),
        ]
    ).lower()
    da_ids = latest_facts(session, person_id, as_of)
    da_fact = da_ids.get(FactType.DECISION_AUTHORITY_ROLE)
    src_ids = [str(da_fact.id)] if da_fact else []

    for fname, needles in _AUTHORITY_ROLES.items():
        bundle.known(fname, any(n in authority_text for n in needles), "bool", src_ids)
    bundle.known(
        "is_ic_member",
        "INVESTMENT_COMMITTEE_ROLE" in event_types or "investment committee" in authority_text,
        "bool",
        [],
    )
    bundle.known(
        "principal_with_mandate",
        "principal" in authority_text and bool(facts.get(FactType.INVESTMENT_MANDATE)),
        "bool",
        [],
    )

    # ---- capital relevance -------------------------------------------------
    org = _current_org(session, person_id)
    bundle.known(
        "org_is_allocator_type",
        bool(org and org.organization_type in _ALLOCATOR_TYPES),
        "bool",
        [],
    )
    if org and org.aum_usd:
        bundle.known("disclosed_aum", float(org.aum_usd), "usd", [])
    else:
        bundle.unknown("disclosed_aum")  # disclosed only — never estimated
    bundle.known(
        "known_fund_investment_activity",
        "FUND_INVESTMENT_ACTIVITY" in event_types,
        "bool",
        [],
    )

    # ---- venture allocation fit -----------------------------------------
    va_val, va_ids = fact_bool(facts, FactType.VENTURE_ALLOCATION_EVIDENCE)
    _present_or_unknown(bundle, "allocates_to_vc", va_val, va_ids)
    _present_or_unknown(
        bundle,
        "allocates_to_emerging_managers",
        "EMERGING_MANAGER_SIGNAL" in event_types or _b(facts, FactType.EMERGING_MANAGER_EVIDENCE),
        [],
    )
    _present_or_unknown(bundle, "allocates_early_stage", va_val, va_ids)

    thesis = active_thesis(session)
    geo_hit = bool(
        thesis
        and org
        and org.location
        and any(g.lower() in org.location.lower() for g in (thesis.geographies or []))
    )
    bundle.known("geo_match", 1.0 if geo_hit else 0.0, "unit", [])
    bundle.known("strategy_match", 0.0, "unit", [])  # deterministic placeholder; refined later

    # ---- emerging manager fit -----------------------------------------
    bundle.known(
        "emerging_manager_program_evidence",
        "EMERGING_MANAGER_SIGNAL" in event_types or _b(facts, FactType.EMERGING_MANAGER_EVIDENCE),
        "bool",
        [],
    )
    n, _, ids = fact_number(facts, FactType.EMERGING_MANAGER_EVIDENCE)
    bundle.known("prior_emerging_commitments", n if n is not None else 0, "count", ids)

    # ---- chimera fit (org profile vs Chimera fund characteristics) --------
    for fname in ("stage_fit", "size_fit", "sector_fit", "geo_fit"):
        if org is None:
            bundle.unknown(fname)
        else:
            bundle.known(fname, 1.0 if geo_hit and fname == "geo_fit" else 0.4, "unit", [])

    # ---- timing --------------------------------------------------------
    for ev in events:
        if ev.event_type in _TIMING_EVENT_TYPES:
            bundle.timing_signals.append(
                TimingSignal(
                    event_type=ev.event_type,
                    occurred_at=ev.occurred_at,
                    days_since=days_since(ev.occurred_at, as_of),
                    evidence_ids=[str(x) for x in (ev.evidence_ids or [])],
                )
            )

    return bundle


def _b(facts, fact_type: str) -> bool:
    v, _ = fact_bool(facts, fact_type)
    return bool(v)


def _present_or_unknown(bundle: FeatureBundle, name: str, val, ids) -> None:
    if val is None:
        bundle.unknown(name)
    else:
        bundle.known(name, bool(val), "bool", ids or [])


def _current_org(session: Session, person_id: uuid.UUID) -> Organization | None:
    return (
        session.execute(
            select(Organization)
            .join(Employment, Employment.organization_id == Organization.id)
            .where(Employment.person_id == person_id, Employment.current.is_(True))
            .order_by(Employment.started_at.desc().nullslast())
        )
        .scalars()
        .first()
    )
