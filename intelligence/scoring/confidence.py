"""Confidence scoring (spec §18). SEPARATE from priority — never folded in.

confidence = Σ weight_c · component_c  over
  reliability · independence · recency · extraction · identity · completeness
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from intelligence.models import Evidence, Fact, Person, RawObservation, Source
from intelligence.models.enums import EntityResolutionStatus
from intelligence.observability import days_between, ensure_utc

_IDENTITY_SCORE: dict[str, float] = {
    EntityResolutionStatus.RESOLVED: 1.0,
    EntityResolutionStatus.MERGED: 1.0,
    EntityResolutionStatus.NEEDS_REVIEW: 0.6,
    EntityResolutionStatus.UNRESOLVED: 0.75,
}


@dataclass(slots=True)
class ConfidenceResult:
    score: float
    components: dict[str, float]

    def as_dict(self) -> dict:
        return {
            "score": round(self.score, 4),
            "components": {k: round(v, 4) for k, v in self.components.items()},
        }


def _feeding_fact_ids(bundle_features: dict) -> set[uuid.UUID]:
    ids: set[uuid.UUID] = set()
    for spec in bundle_features.values():
        if isinstance(spec, dict):
            for fid in spec.get("source_fact_ids", []):
                try:
                    ids.add(uuid.UUID(str(fid)))
                except ValueError:
                    continue
    return ids


def compute_confidence(
    session: Session,
    *,
    person: Person,
    features_json: dict,
    missing_features: list[str],
    dimension_present_weight: float,
    dimension_total_weight: float,
    weights: dict[str, float],
    as_of: datetime,
) -> ConfidenceResult:
    fact_ids = _feeding_fact_ids(features_json)

    reliability = 0.5
    recency = 0.5
    extraction = 1.0
    domains: set[str] = set()

    if fact_ids:
        facts = session.execute(select(Fact).where(Fact.id.in_(fact_ids))).scalars().all()
        ev_rows = (
            session.execute(select(Evidence).where(Evidence.fact_id.in_(fact_ids))).scalars().all()
        )
        if ev_rows:
            reliability = sum(e.evidence_strength for e in ev_rows) / len(ev_rows)
        # independence: distinct originating source providers / domains
        obs_ids = {e.observation_id for e in ev_rows}
        if obs_ids:
            for obs in session.execute(
                select(RawObservation).where(RawObservation.id.in_(obs_ids))
            ).scalars():
                src = session.get(Source, obs.source_id)
                domains.add(src.provider if src else "unknown")
        if facts:
            ages: list[float] = [
                d
                for f in facts
                if (d := days_between(ensure_utc(f.valid_from or f.created_at), ensure_utc(as_of)))
                is not None
            ]
            if ages:
                recency = sum(math.exp(-0.005 * max(0.0, a)) for a in ages) / len(ages)
            xs = [f.extraction_confidence for f in facts if f.extraction_confidence is not None]
            if xs:
                extraction = sum(xs) / len(xs)

    independence = min(1.0, 0.5 + 0.25 * max(0, len(domains) - 0)) if domains else 0.5
    identity = _IDENTITY_SCORE.get(person.entity_resolution_status, 0.7)
    completeness = (
        dimension_present_weight / dimension_total_weight if dimension_total_weight else 0.0
    )

    components = {
        "reliability": round(reliability, 4),
        "independence": round(independence, 4),
        "recency": round(recency, 4),
        "extraction": round(extraction, 4),
        "identity": round(identity, 4),
        "completeness": round(completeness, 4),
    }
    wsum = sum(weights.values()) or 1.0
    score = sum(weights.get(k, 0.0) * v for k, v in components.items()) / wsum
    return ConfidenceResult(score=max(0.0, min(1.0, score)), components=components)
