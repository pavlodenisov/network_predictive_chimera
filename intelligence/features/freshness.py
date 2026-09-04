"""Per-feature-type staleness thresholds (spec §27). Configurable; these are the V0
defaults. A stale feature is shown, not dropped — it lowers the ``recency`` component of
``confidence_score`` and can trigger ``DATA_STALE`` reason codes.
"""

from __future__ import annotations

from datetime import datetime

from intelligence.observability import days_between, ensure_utc

STALE_THRESHOLD_DAYS: dict[str, int] = {
    "current_employment": 60,
    "network_relationship": 365,
    "company_stage": 120,
    "headline": 45,
    "education": 10_000,  # effectively never
    "default": 180,
}

#: fact_type -> freshness bucket
FACT_FRESHNESS_BUCKET: dict[str, str] = {
    "CURRENT_TITLE": "current_employment",
    "EMPLOYMENT_ENDED_AT": "current_employment",
    "HEADLINE_TEXT": "headline",
    "HEADLINE_CHANGED": "headline",
    "EDUCATION_INSTITUTION": "education",
    "INVESTMENT_MANDATE": "company_stage",
    "VENTURE_ALLOCATION_EVIDENCE": "company_stage",
}


def threshold_for(bucket: str) -> int:
    return STALE_THRESHOLD_DAYS.get(bucket, STALE_THRESHOLD_DAYS["default"])


def bucket_for_fact(fact_type: str) -> str:
    return FACT_FRESHNESS_BUCKET.get(fact_type, "default")


def freshness_entry(
    *, verified_at: datetime | None, as_of: datetime, bucket: str
) -> dict[str, object]:
    age = days_between(ensure_utc(verified_at), ensure_utc(as_of))
    limit = threshold_for(bucket)
    return {
        "verified_at": verified_at.isoformat() if verified_at else None,
        "age_days": round(age, 1) if age is not None else None,
        "stale_threshold_days": limit,
        "stale": bool(age is not None and age > limit),
    }
