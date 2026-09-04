"""Persist an ``ExtractionOutput`` into the provenance + event layers (spec §7-8, §38).

Pipeline: extraction output ->
  * ``fact`` (+ ``evidence`` -> immutable ``raw_observation``)   [directly observed]
  * ``event``  (deduped, taxonomy-typed)                          [directly observed change]
  * ``inference`` (labelled, probabilistic)                       [interpretation]

Idempotent: a re-run over the same observation creates no duplicate facts or events
(``dedupe_key``).
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from intelligence.events.taxonomy import (
    default_confidence,
    is_inference_type,
    spec_for,
    ttl_days_for,
)
from intelligence.facts import record_fact, record_inference
from intelligence.models import (
    Event,
    Evidence,
    Fact,
    Inference,
    Organization,
    RawObservation,
    Source,
)
from intelligence.models.enums import EventStatus, ExtractionMethod, Severity, SubjectType
from intelligence.observability import ensure_utc, now_utc
from intelligence.schemas.extraction import ExtractionOutput

_INFERENCE_MODEL_VERSION = "inference_v0.1"

#: event types where two reports within a window describe the same real-world change.
_WINDOWED_EVENT_TYPES = {
    "EMPLOYMENT_ENDED",
    "EMPLOYMENT_STARTED",
    "PROFESSIONAL_DEPARTURE",
    "FOUNDER_TITLE_ADDED",
    "COMPANY_FORMATION_CONFIRMED",
    "FUNDRAISE_ANNOUNCED",
    "PROMOTION",
}
_WINDOW_DAYS = 60


def _has_recent_similar(
    session: Session,
    person_id: uuid.UUID,
    event_type: str,
    org_id: uuid.UUID | None,
    occurred: datetime | None,
) -> bool:
    q = select(Event).where(
        Event.person_id == person_id,
        Event.event_type == event_type,
        Event.status == EventStatus.ACTIVE,
    )
    if org_id is not None:
        q = q.where(Event.organization_id == org_id)
    this = ensure_utc(occurred)
    for other in session.execute(q).scalars():
        that = ensure_utc(other.occurred_at)
        if this is None or that is None:
            return True
        if abs((that - this).days) <= _WINDOW_DAYS:
            return True
    return False


@dataclass(slots=True)
class DetectionResult:
    facts: list[Fact] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    inferences: list[Inference] = field(default_factory=list)
    skipped_events: int = 0


def _dt(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return ensure_utc(value)
    try:
        return datetime.fromisoformat(f"{str(value)[:10]}T00:00:00").replace(tzinfo=UTC)
    except ValueError:
        return None


def dedupe_key(person_id: uuid.UUID, event_type: str, occurred_at: datetime | None) -> str:
    stamp = occurred_at.date().isoformat() if occurred_at else "none"
    return hashlib.sha1(  # noqa: S324 - non-crypto idempotency key
        f"{person_id}|{event_type}|{stamp}".encode()
    ).hexdigest()


def _get_or_create_org(session: Session, name: str | None) -> Organization | None:
    if not name or not name.strip():
        return None
    name = name.strip()
    org = session.execute(
        select(Organization).where(Organization.canonical_name == name)
    ).scalar_one_or_none()
    if org is None:
        org = Organization(canonical_name=name)
        session.add(org)
        session.flush()
    return org


def _bare_evidence(
    session: Session,
    observation: RawObservation,
    source: Source | None,
    label: str,
    quote: str | None,
) -> Evidence:
    from intelligence.facts import evidence_strength_for

    tier = source.reliability_tier if source else 3
    ev = Evidence(
        fact_id=None,
        observation_id=observation.id,
        source_url=observation.source_url,
        source_label=label,
        quoted_fragment=quote,
        observed_at=observation.observed_at,
        evidence_strength=evidence_strength_for(tier),
    )
    session.add(ev)
    session.flush()
    return ev


def persist_extraction(
    session: Session,
    *,
    person_id: uuid.UUID,
    observation: RawObservation,
    output: ExtractionOutput,
    source: Source | None = None,
    weekly_run_id: uuid.UUID | None = None,
    extractor_version: str = "rules_v0.1",
    extraction_method: str = ExtractionMethod.DETERMINISTIC_PARSE,
) -> DetectionResult:
    if source is None:
        source = session.get(Source, observation.source_id)
    result = DetectionResult()
    label = source.name if source else "unknown source"
    tier = source.reliability_tier if source else 3

    # --- facts (+ evidence) --------------------------------------------------
    evidence_ids: list[str] = []
    for ef in output.facts:
        fact = record_fact(
            session,
            subject_type=SubjectType.PERSON,
            subject_id=person_id,
            fact_type=ef.fact_type,
            value=ef.value,
            observation=observation,
            source=source,
            source_label=label,
            quoted_fragment=ef.evidence_quote,
            extraction_method=extraction_method,
            extractor_version=extractor_version,
            extraction_confidence=ef.confidence,
            valid_from=_dt(ef.occurred_at) or observation.observed_at,
        )
        result.facts.append(fact)
        ev = session.execute(select(Evidence).where(Evidence.fact_id == fact.id)).scalars().first()
        if ev:
            evidence_ids.append(str(ev.id))

    # --- events & inferences ------------------------------------------------
    for ee in output.events:
        etype = str(ee.event_type)
        occurred = _dt(ee.occurred_at) or observation.occurred_at or observation.observed_at
        route_as_inference = ee.is_inference or is_inference_type(etype)

        if route_as_inference:
            ev = _bare_evidence(session, observation, source, label, ee.evidence_quote)
            inf = record_inference(
                session,
                person_id=person_id,
                inference_type=etype,
                probability=ee.probability if ee.probability is not None else ee.confidence,
                model_version=_INFERENCE_MODEL_VERSION,
                evidence_ids=[ev.id, *[uuid.UUID(e) for e in evidence_ids]],
                explanation_code=ee.explanation_code or etype,
                expires_at=_expiry(etype, occurred),
            )
            result.inferences.append(inf)
            continue

        key = dedupe_key(person_id, etype, occurred)
        existing = session.execute(
            select(Event).where(Event.dedupe_key == key, Event.status == EventStatus.ACTIVE)
        ).scalar_one_or_none()
        if existing is not None:
            result.skipped_events += 1
            continue

        spec = spec_for(etype)
        ev = _bare_evidence(session, observation, source, label, ee.evidence_quote)
        org = _get_or_create_org(session, ee.organization_name)

        # collapse near-duplicate life events reported by different sources on different
        # dates (e.g. a profile snapshot + a news article about the same departure)
        if etype in _WINDOWED_EVENT_TYPES and _has_recent_similar(
            session, person_id, etype, org.id if org else None, occurred
        ):
            result.skipped_events += 1
            continue

        confidence = round(
            min(ee.confidence, default_confidence(reliability_tier=tier, extraction=ee.confidence))
            if ee.confidence
            else default_confidence(reliability_tier=tier),
            2,
        )
        event = Event(
            person_id=person_id,
            organization_id=org.id if org else None,
            event_type=etype,
            occurred_at=occurred,
            detected_at=now_utc(),
            confidence=confidence,
            severity=spec.severity if spec else Severity.LOW,
            evidence_ids=[str(ev.id), *evidence_ids],
            structured_payload={
                "observation_id": str(observation.id),
                "organization_name": ee.organization_name,
                "source": label,
            },
            dedupe_key=key,
            status=EventStatus.ACTIVE,
            weekly_run_id=weekly_run_id,
        )
        session.add(event)
        session.flush()
        result.events.append(event)

    return result


def _expiry(event_type: str, occurred: datetime | None) -> datetime | None:
    base = ensure_utc(occurred)
    if base is None:
        return None
    from datetime import timedelta

    return base + timedelta(days=ttl_days_for(event_type))
