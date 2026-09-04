"""Fact + Evidence writer. The ONLY sanctioned way to create a ``Fact``.

Every fact is written together with at least one ``Evidence`` row pointing at an immutable
``RawObservation`` (CLAUDE.md rule 3). ``unknown`` is stored as ``{"status": "unknown"}``
and never as ``0`` / ``false`` / ``null`` (rule 4).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy.orm import Session

from intelligence.events.taxonomy import TIER_WEIGHT
from intelligence.models import Evidence, Fact, Inference, RawObservation, Source
from intelligence.models.enums import ExtractionMethod, SubjectType


class FactType(StrEnum):
    EMPLOYMENT_STARTED_AT = "EMPLOYMENT_STARTED_AT"
    EMPLOYMENT_ENDED_AT = "EMPLOYMENT_ENDED_AT"
    CURRENT_TITLE = "CURRENT_TITLE"
    HEADLINE_TEXT = "HEADLINE_TEXT"
    HEADLINE_CHANGED = "HEADLINE_CHANGED"
    PRIOR_EXIT = "PRIOR_EXIT"
    PRIOR_FOUNDER = "PRIOR_FOUNDER"
    COMPANIES_FOUNDED_COUNT = "COMPANIES_FOUNDED_COUNT"
    INSTITUTIONAL_FUNDRAISE = "INSTITUTIONAL_FUNDRAISE"
    PRODUCT_SHIPPED = "PRODUCT_SHIPPED"
    YEARS_DOMAIN_EXPERIENCE = "YEARS_DOMAIN_EXPERIENCE"
    YEARS_ENGINEERING_EXPERIENCE = "YEARS_ENGINEERING_EXPERIENCE"
    PATENT_COUNT = "PATENT_COUNT"
    PUBLICATION_COUNT = "PUBLICATION_COUNT"
    OSS_PROJECT_MAJOR = "OSS_PROJECT_MAJOR"
    EARLY_EMPLOYEE_RANK = "EARLY_EMPLOYEE_RANK"
    PROMOTION_COUNT = "PROMOTION_COUNT"
    TEAM_SIZE_MANAGED = "TEAM_SIZE_MANAGED"
    BUDGET_OWNERSHIP = "BUDGET_OWNERSHIP"
    BOARD_ROLE = "BOARD_ROLE"
    ADVISOR_ROLE = "ADVISOR_ROLE"
    LOCATION = "LOCATION"
    DECISION_AUTHORITY_ROLE = "DECISION_AUTHORITY_ROLE"
    ORG_TYPE_ALLOCATOR = "ORG_TYPE_ALLOCATOR"
    VENTURE_ALLOCATION_EVIDENCE = "VENTURE_ALLOCATION_EVIDENCE"
    EMERGING_MANAGER_EVIDENCE = "EMERGING_MANAGER_EVIDENCE"
    INVESTMENT_MANDATE = "INVESTMENT_MANDATE"
    FUNDRAISING_STATUS = "FUNDRAISING_STATUS"
    OPEN_TO_WORK_DECLARED = "OPEN_TO_WORK_DECLARED"
    GITHUB_IDENTITY = "GITHUB_IDENTITY"
    EDUCATION_INSTITUTION = "EDUCATION_INSTITUTION"
    TIME_TO_LEADERSHIP_YEARS = "TIME_TO_LEADERSHIP_YEARS"
    PRESTIGE_FLAG = "PRESTIGE_FLAG"
    VERIFIED_SCALE_MILESTONE = "VERIFIED_SCALE_MILESTONE"


UNKNOWN_VALUE: dict[str, str] = {"status": "unknown"}


def known(value: Any, unit: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"value": value, "status": "known"}
    if unit is not None:
        out["unit"] = unit
    return out


def unknown() -> dict[str, str]:
    return dict(UNKNOWN_VALUE)


def is_unknown(structured_value: dict[str, Any] | None) -> bool:
    return not structured_value or structured_value.get("status") == "unknown"


def evidence_strength_for(reliability_tier: int, directness: float = 1.0) -> float:
    """0–1 from source reliability tier * directness (spec §55)."""
    return round(TIER_WEIGHT.get(reliability_tier, 0.5) * max(0.0, min(1.0, directness)), 3)


def record_fact(
    session: Session,
    *,
    subject_type: SubjectType | str,
    subject_id: uuid.UUID,
    fact_type: FactType | str,
    value: dict[str, Any],
    observation: RawObservation,
    source: Source | None = None,
    source_label: str | None = None,
    source_url: str | None = None,
    quoted_fragment: str | None = None,
    extraction_method: ExtractionMethod | str = ExtractionMethod.DETERMINISTIC_PARSE,
    extractor_version: str = "rules_v0.1",
    extraction_confidence: float | None = None,
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
    directness: float = 1.0,
) -> Fact:
    """Create a ``Fact`` and its bridging ``Evidence`` atomically."""
    if source is None:
        source = session.get(Source, observation.source_id)
    tier = source.reliability_tier if source else 3
    label = source_label or (source.name if source else "unknown source")

    fact = Fact(
        subject_type=str(subject_type),
        subject_id=subject_id,
        fact_type=str(fact_type),
        structured_value=value,
        valid_from=valid_from,
        valid_to=valid_to,
        extraction_method=str(extraction_method),
        extractor_version=extractor_version,
        extraction_confidence=extraction_confidence,
    )
    session.add(fact)
    session.flush()

    session.add(
        Evidence(
            fact_id=fact.id,
            observation_id=observation.id,
            source_url=source_url or observation.source_url,
            source_label=label,
            quoted_fragment=quoted_fragment,
            observed_at=observation.observed_at,
            evidence_strength=evidence_strength_for(tier, directness),
        )
    )
    session.flush()
    return fact


def record_inference(
    session: Session,
    *,
    person_id: uuid.UUID,
    inference_type: str,
    probability: float,
    model_version: str,
    evidence_ids: list[uuid.UUID],
    explanation_code: str,
    expires_at: datetime | None = None,
) -> Inference:
    inf = Inference(
        person_id=person_id,
        inference_type=inference_type,
        probability=round(max(0.0, min(1.0, probability)), 4),
        model_version=model_version,
        evidence_ids=[str(e) for e in evidence_ids],
        explanation_code=explanation_code,
        expires_at=expires_at or None,
    )
    session.add(inf)
    session.flush()
    return inf


def supersede_fact(session: Session, old: Fact, new: Fact) -> None:
    """Mark ``old`` superseded by ``new`` — never delete (spec §2.7)."""
    old.superseded_by_id = new.id
    session.flush()
