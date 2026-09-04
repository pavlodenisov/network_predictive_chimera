"""Feature primitives shared by the four model builders.

A feature is ``{value, status, raw_unit, source_fact_ids}``. ``status`` is
``known`` | ``unknown`` — ``unknown`` is NEVER silently 0 (spec §2.3, CLAUDE.md #4). A
feature the builder could not compute is listed in ``bundle.missing`` and left out of the
dimension's weight renormalization.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from intelligence.facts import is_unknown
from intelligence.models import Event, Fact, Inference
from intelligence.models.enums import EventStatus
from intelligence.observability import days_between, ensure_utc

#: when set (by the backtest), fact/event visibility additionally excludes anything
#: recorded/detected after this instant — no later knowledge leaks into a historical run.
POINT_IN_TIME_CUTOFF: ContextVar[datetime | None] = ContextVar("pit_cutoff", default=None)

#: guardrail — feature names touching these substrings are forbidden (spec §39).
FORBIDDEN_FEATURE_SUBSTRINGS = (
    "race",
    "ethnic",
    "religio",
    "sexual",
    "gender",
    "health",
    "disab",
    "politic",
    "ideolog",
    "union_member",
    "genetic",
    "biometric",
)


def assert_feature_name_allowed(name: str) -> None:
    low = name.lower()
    for bad in FORBIDDEN_FEATURE_SUBSTRINGS:
        if bad in low:
            raise ValueError(
                f"feature {name!r} matches forbidden substring {bad!r} — sensitive/protected "
                "attributes must never be used as features (spec §39)"
            )


@dataclass(slots=True)
class FeatureValue:
    value: Any
    status: str = "known"  # known | unknown
    raw_unit: str | None = None
    source_fact_ids: list[str] = field(default_factory=list)
    verified_at: datetime | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "value": self.value if self.status == "known" else None,
            "status": self.status,
            "raw_unit": self.raw_unit,
            "source_fact_ids": self.source_fact_ids,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
        }


UNKNOWN = FeatureValue(value=None, status="unknown")


@dataclass(slots=True)
class TimingSignal:
    event_type: str
    occurred_at: datetime | None
    days_since: float | None
    probability: float | None = None
    evidence_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class FeatureBundle:
    model_target: str
    as_of: datetime
    features: dict[str, FeatureValue] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    timing_signals: list[TimingSignal] = field(default_factory=list)
    freshness: dict[str, dict] = field(default_factory=dict)
    fit_evidence: dict[str, list[str]] = field(default_factory=dict)

    def set(self, name: str, value: FeatureValue) -> None:
        assert_feature_name_allowed(name)
        self.features[name] = value
        if value.status != "known":
            self.missing.append(name)

    def known(
        self,
        name: str,
        value: Any,
        unit: str | None = None,
        fact_ids: list[str] | None = None,
        verified_at: datetime | None = None,
    ) -> None:
        self.set(name, FeatureValue(value, "known", unit, fact_ids or [], verified_at))

    def unknown(self, name: str) -> None:
        self.set(name, FeatureValue(None, "unknown"))

    def features_json(self) -> dict[str, dict]:
        return {k: v.as_dict() for k, v in self.features.items()}


# --------------------------------------------------------------------------- fact access
def latest_facts(
    session: Session,
    person_id: uuid.UUID,
    as_of: datetime,
    *,
    strict_created_at: datetime | None = None,
) -> dict[str, Fact]:
    """Most recent non-superseded fact per ``fact_type`` for a person, true as of ``as_of``.

    Visibility is keyed on when the fact *became true* (``valid_from``, falling back to
    ``created_at``) — not when we happened to record it. Pass ``strict_created_at`` (used by
    the backtest) to additionally exclude facts recorded after that instant, so no
    later-extracted knowledge leaks into a historical point-in-time run (spec §35).
    """
    as_of_utc = ensure_utc(as_of)
    became_true = func.coalesce(Fact.valid_from, Fact.created_at)
    conditions = [
        Fact.subject_type == "person",
        Fact.subject_id == person_id,
        Fact.superseded_by_id.is_(None),
        became_true <= as_of_utc,
    ]
    cutoff = strict_created_at or POINT_IN_TIME_CUTOFF.get()
    if cutoff is not None:
        conditions.append(Fact.created_at <= ensure_utc(cutoff))
    rows = (
        session.execute(
            select(Fact)
            .where(*conditions)
            .order_by(Fact.fact_type, Fact.valid_from.desc().nullslast(), Fact.created_at.desc())
        )
        .scalars()
        .all()
    )
    out: dict[str, Fact] = {}
    for f in rows:
        out.setdefault(f.fact_type, f)
    return out


def fact_number(
    facts: dict[str, Fact], fact_type: str
) -> tuple[float | None, str | None, list[str]]:
    f = facts.get(fact_type)
    if f is None or is_unknown(f.structured_value):
        return None, None, []
    val = f.structured_value.get("value")
    unit = f.structured_value.get("unit")
    if val is None:
        return None, unit, [str(f.id)]
    try:
        return float(val), unit, [str(f.id)]
    except (TypeError, ValueError):
        return None, unit, [str(f.id)]


def fact_bool(facts: dict[str, Fact], fact_type: str) -> tuple[bool | None, list[str]]:
    f = facts.get(fact_type)
    if f is None or is_unknown(f.structured_value):
        return None, []
    return bool(f.structured_value.get("value")), [str(f.id)]


def fact_text(facts: dict[str, Fact], fact_type: str) -> tuple[str | None, list[str]]:
    f = facts.get(fact_type)
    if f is None or is_unknown(f.structured_value):
        return None, []
    return str(f.structured_value.get("value") or ""), [str(f.id)]


def active_events(session: Session, person_id: uuid.UUID, as_of: datetime) -> list[Event]:
    return list(
        session.execute(
            select(Event)
            .where(
                Event.person_id == person_id,
                Event.status == EventStatus.ACTIVE,
                Event.detected_at <= ensure_utc(as_of),
            )
            .order_by(Event.occurred_at.desc().nullslast())
        )
        .scalars()
        .all()
    )


def active_inferences(session: Session, person_id: uuid.UUID, as_of: datetime) -> list[Inference]:
    as_of_utc = ensure_utc(as_of)
    rows = session.execute(
        select(Inference)
        .where(Inference.person_id == person_id, Inference.created_at <= as_of_utc)
        .order_by(Inference.created_at.desc())
    ).scalars()
    out: list[Inference] = []
    for inf in rows:
        exp = ensure_utc(inf.expires_at)
        if exp is not None and as_of_utc is not None and exp < as_of_utc:
            continue
        out.append(inf)
    return out


def days_since(occurred_at: datetime | None, as_of: datetime) -> float | None:
    return days_between(ensure_utc(occurred_at), ensure_utc(as_of))
