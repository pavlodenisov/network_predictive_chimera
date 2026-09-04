"""Wave 2 smoke: column types round-trip, models import, timestamps are tz-aware."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from intelligence.models import Person, RawObservation, Source
from intelligence.models.enums import ContentType, SourceType
from intelligence.observability import ensure_utc, now_utc


def test_now_utc_is_timezone_aware() -> None:
    ts = now_utc()
    assert ts.tzinfo is not None
    assert ensure_utc(datetime(2026, 1, 1)).tzinfo is UTC  # noqa: DTZ001 - intentional naive input


def test_guid_and_utcdatetime_roundtrip(session: Session) -> None:
    person = Person(canonical_name="Sarah Chen", first_seen_at=now_utc())
    session.add(person)
    session.flush()

    assert isinstance(person.id, uuid.UUID)
    reloaded = session.get(Person, person.id)
    assert reloaded is not None
    assert reloaded.first_seen_at.tzinfo is not None
    assert reloaded.monitoring_status == "REVIEW"
    assert reloaded.is_chimera_seed is False


def test_jsonb_column_roundtrip(session: Session) -> None:
    src = Source(
        source_type=SourceType.SYNTHETIC,
        provider="synthetic",
        name="Synthetic",
        reliability_tier=2,
        configuration={"seed": 42, "weeks": [1, 2]},
    )
    session.add(src)
    session.flush()
    obs = RawObservation(
        source_id=src.id,
        observed_at=now_utc(),
        ingested_at=now_utc(),
        content_type=ContentType.JSON_RECORD,
        raw_json={"headline": "building", "tags": ["ai", "infra"]},
        content_hash="abc123",
        obs_metadata={"k": "v"},
    )
    session.add(obs)
    session.flush()

    got = session.get(RawObservation, obs.id)
    assert got is not None
    assert got.raw_json["tags"] == ["ai", "infra"]
    assert got.obs_metadata == {"k": "v"}
    assert session.get(Source, src.id).configuration["weeks"] == [1, 2]


def test_unknown_is_not_zero_for_relationship_strength(session: Session) -> None:
    from intelligence.models import RelationshipEdge
    from intelligence.models.enums import RelationshipStrength

    a = Person(canonical_name="A")
    b = Person(canonical_name="B")
    session.add_all([a, b])
    session.flush()
    edge = RelationshipEdge(source_person_id=a.id, target_person_id=b.id)
    session.add(edge)
    session.flush()

    got = session.get(RelationshipEdge, edge.id)
    assert got.relationship_strength == RelationshipStrength.UNKNOWN
    assert got.strength_numeric is None  # unknown, NOT 0.0
