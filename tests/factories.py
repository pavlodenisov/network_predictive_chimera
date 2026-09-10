"""Lightweight object factories for tests (not synthetic seed data — see db/seeds/)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from intelligence.ingestion.adapters.base import RawObservationDraft
from intelligence.ingestion.dedupe import content_hash
from intelligence.models import (
    Event,
    Evidence,
    Fact,
    Organization,
    Person,
    RawObservation,
    RelationshipEdge,
    Source,
    ThesisConfiguration,
)
from intelligence.models.enums import (
    ContentType,
    EventStatus,
    MonitoringStatus,
    RelationshipStrength,
    Severity,
    SourceType,
    SubjectType,
)
from intelligence.observability import now_utc


def make_source(
    session: Session, *, provider: str = "synthetic", tier: int = 2, **kw: Any
) -> Source:
    src = Source(
        source_type=kw.get("source_type", SourceType.SYNTHETIC),
        provider=provider,
        name=kw.get("name", provider),
        enabled=kw.get("enabled", True),
        reliability_tier=tier,
        configuration=kw.get("configuration", {}),
    )
    session.add(src)
    session.flush()
    return src


def make_person(
    session: Session, name: str = "Sarah Chen", *, chimera_seed: bool = False, **kw: Any
) -> Person:
    p = Person(
        canonical_name=name,
        monitoring_status=kw.get("monitoring_status", MonitoringStatus.ACTIVE_MONITORING),
        is_chimera_seed=chimera_seed,
        first_seen_at=now_utc(),
        **{k: v for k, v in kw.items() if k not in {"monitoring_status"}},
    )
    session.add(p)
    session.flush()
    return p


def make_org(session: Session, name: str, **kw: Any) -> Organization:
    o = Organization(canonical_name=name, **kw)
    session.add(o)
    session.flush()
    return o


def make_observation(
    session: Session,
    source: Source,
    *,
    content_type: str = ContentType.PROFILE_SNAPSHOT,
    subject_hint: str = "Sarah Chen",
    raw_json: dict | None = None,
    raw_text: str | None = None,
    previous_snapshot: dict | None = None,
    observed_at: datetime | None = None,
    occurred_at: datetime | None = None,
    source_url: str | None = None,
    provider_record_id: str | None = "rec-1",
) -> RawObservation:
    draft = RawObservationDraft(
        provider_record_id=provider_record_id,
        content_type=content_type,
        subject_hint=subject_hint,
        raw_json=raw_json,
        raw_text=raw_text,
        previous_snapshot=previous_snapshot,
        source_url=source_url,
    )
    meta: dict[str, Any] = {}
    if previous_snapshot is not None:
        meta["previous_snapshot"] = previous_snapshot
    obs = RawObservation(
        source_id=source.id,
        provider_record_id=provider_record_id,
        subject_hint=subject_hint,
        observed_at=observed_at or now_utc(),
        ingested_at=now_utc(),
        occurred_at=occurred_at,
        content_type=str(content_type),
        raw_text=raw_text,
        raw_json=raw_json,
        content_hash=content_hash(draft),
        source_url=source_url,
        obs_metadata=meta,
    )
    session.add(obs)
    session.flush()
    return obs


def dt(y: int, m: int, d: int) -> datetime:
    return datetime(y, m, d, tzinfo=UTC)


def add_fact(
    session: Session,
    person: Person,
    fact_type: str,
    value: Any,
    *,
    status: str = "known",
    unit: str | None = None,
    valid_from: datetime | None = None,
    extraction_confidence: float = 1.0,
) -> Fact:
    structured = (
        {"status": "unknown"} if status == "unknown" else {"value": value, "status": "known"}
    )
    if unit and status == "known":
        structured["unit"] = unit
    f = Fact(
        subject_type=SubjectType.PERSON,
        subject_id=person.id,
        fact_type=fact_type,
        structured_value=structured,
        # default well before any test `as_of` so the fact is "currently known"
        # (tests score against fixed past dates; wall-clock `now` would hide the fact)
        valid_from=valid_from or datetime(2026, 1, 1, tzinfo=UTC),
        extraction_method="deterministic_parse",
        extractor_version="test",
        extraction_confidence=extraction_confidence,
    )
    session.add(f)
    session.flush()
    # a fact always has evidence -> an immutable observation (CLAUDE.md rule 3)
    src = _test_source(session)
    obs = _test_observation(session, src, person.canonical_name)
    session.add(
        Evidence(
            fact_id=f.id,
            observation_id=obs.id,
            source_label="test",
            observed_at=obs.observed_at,
            evidence_strength=0.85,
        )
    )
    session.flush()
    return f


def _test_source(session: Session) -> Source:
    from sqlalchemy import select

    row = session.execute(select(Source).where(Source.provider == "test-factory")).scalars().first()
    if row is None:
        row = Source(
            source_type=SourceType.SYNTHETIC,
            provider="test-factory",
            name="test",
            enabled=False,
            reliability_tier=3,
        )
        session.add(row)
        session.flush()
    return row


def _test_observation(session: Session, src: Source, subject: str) -> RawObservation:
    obs = RawObservation(
        source_id=src.id,
        provider_record_id=None,
        subject_hint=subject,
        observed_at=now_utc(),
        ingested_at=now_utc(),
        content_type=ContentType.JSON_RECORD,
        content_hash=f"test:{subject}:{now_utc().timestamp()}",
        raw_json={"subject": subject},
        obs_metadata={"test": True},
    )
    session.add(obs)
    session.flush()
    return obs


def add_event(
    session: Session,
    person: Person,
    event_type: str,
    *,
    occurred_at: datetime,
    confidence: float = 0.9,
    severity: str = Severity.MEDIUM,
    org_id: Any = None,
) -> Event:
    e = Event(
        person_id=person.id,
        organization_id=org_id,
        event_type=event_type,
        occurred_at=occurred_at,
        detected_at=now_utc(),
        confidence=confidence,
        severity=severity,
        evidence_ids=[],
        structured_payload={},
        dedupe_key=f"{person.id}:{event_type}:{occurred_at.date()}",
        status=EventStatus.ACTIVE,
    )
    session.add(e)
    session.flush()
    return e


def add_edge(
    session: Session,
    a: Person,
    b: Person,
    *,
    strength: str = RelationshipStrength.MODERATE,
    confidence: float = 0.9,
    last_verified_at: datetime | None = None,
) -> RelationshipEdge:
    edge = RelationshipEdge(
        source_person_id=a.id,
        target_person_id=b.id,
        relationship_type="colleague",
        relationship_strength=strength,
        confidence=confidence,
        source="test",
        last_verified_at=last_verified_at or now_utc(),
        evidence_ids=[],
    )
    session.add(edge)
    session.flush()
    return edge


def seed_sample_thesis(session: Session) -> ThesisConfiguration:
    from sqlalchemy import select

    existing = (
        session.execute(
            select(ThesisConfiguration).where(
                ThesisConfiguration.name == "chimera-sample", ThesisConfiguration.version == "v0.1"
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        return existing
    t = ThesisConfiguration(
        name="chimera-sample",
        version="v0.1",
        is_sample=True,
        active=True,
        sectors=["artificial intelligence", "AI infrastructure", "developer tools"],
        technologies=["inference optimization", "distributed systems", "training infrastructure"],
        technical_topics=["inference", "distributed systems", "GPU", "model serving"],
        business_models=["usage-based infrastructure", "API platform"],
        stages=["seed", "series A"],
        geographies=["United States", "Canada", "United Kingdom"],
    )
    session.add(t)
    session.flush()
    return t
