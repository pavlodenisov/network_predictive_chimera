"""Feature building (spec §61 Phase 7). Raw feature values are stored, not just scores."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from intelligence.features import connector as _connector
from intelligence.features import founder as _founder
from intelligence.features import lp as _lp
from intelligence.features import talent as _talent
from intelligence.features.base import FeatureBundle, TimingSignal
from intelligence.features.registry import FEATURE_SET_VERSION, assert_feature_name_allowed
from intelligence.models import PersonFeatureSnapshot, PortfolioRoleNeed
from intelligence.observability import ensure_utc

_BUILDERS = {
    "founder": _founder.build,
    "lp": _lp.build,
    "connector": _connector.build,
}


def build_feature_bundle(
    session: Session,
    person_id: uuid.UUID,
    model_target: str,
    as_of: datetime,
    *,
    role_need: PortfolioRoleNeed | None = None,
) -> FeatureBundle:
    if model_target == "talent":
        if role_need is None:
            raise ValueError("talent features require a role_need")
        return _talent.build(session, person_id, as_of, role_need=role_need)
    builder = _BUILDERS.get(model_target)
    if builder is None:
        raise KeyError(f"no feature builder for model target {model_target!r}")
    return builder(session, person_id, as_of)


def persist_feature_snapshot(
    session: Session,
    person_id: uuid.UUID,
    bundle: FeatureBundle,
    *,
    as_of_date=None,
) -> PersonFeatureSnapshot:
    snap = PersonFeatureSnapshot(
        person_id=person_id,
        model_target=bundle.model_target,
        feature_set_version=FEATURE_SET_VERSION,
        calculated_at=ensure_utc(bundle.as_of),
        as_of_date=as_of_date or bundle.as_of.date(),
        features={
            **bundle.features_json(),
            "_timing_signals": [
                {
                    "event_type": s.event_type,
                    "occurred_at": s.occurred_at.isoformat() if s.occurred_at else None,
                    "days_since": s.days_since,
                    "probability": s.probability,
                    "evidence_ids": s.evidence_ids,
                }
                for s in bundle.timing_signals
            ],
            "_fit_evidence": bundle.fit_evidence,
        },
        missing_features=sorted(set(bundle.missing)),
        data_freshness=bundle.freshness,
    )
    session.add(snap)
    session.flush()
    return snap


__all__ = [
    "FEATURE_SET_VERSION",
    "FeatureBundle",
    "TimingSignal",
    "assert_feature_name_allowed",
    "build_feature_bundle",
    "persist_feature_snapshot",
]
