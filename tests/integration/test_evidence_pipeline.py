"""observation -> extraction -> fact(+evidence) -> event / inference, with provenance
and idempotency (spec §61 Phase 4, §38)."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from intelligence.events.detector import persist_extraction
from intelligence.events.taxonomy import EventType
from intelligence.extraction import RuleBasedExtractor
from intelligence.extraction.runner import run_extraction
from intelligence.facts import FactType, is_unknown
from intelligence.models import Event, Evidence, ExtractionRun, Fact, Inference
from intelligence.models.enums import ParseStatus

pytestmark = pytest.mark.integration

WEEK1 = {
    "headline": "Staff ML Engineer at Synthetic AI Labs",
    "current_company": "Synthetic AI Labs",
    "current_title": "Staff ML Engineer",
    "current_seniority": "senior_ic",
    "years_domain_experience": 5.4,
    "prior_founder": True,
}
WEEK2_PROFILE = {"headline": "Building", "current_company": None, "current_title": None}


def _ingest_week2(session, source, person):
    from tests.factories import make_observation

    obs = make_observation(
        session,
        source,
        content_type="profile_snapshot",
        subject_hint=person.canonical_name,
        raw_json={"profile": WEEK2_PROFILE, "observed_on": "2026-08-31"},
        previous_snapshot=WEEK1,
        provider_record_id="snap-sarah-w2",
    )
    result = run_extraction(
        session, RuleBasedExtractor(), obs, previous_snapshot=obs.obs_metadata["previous_snapshot"]
    )
    detection = persist_extraction(
        session, person_id=person.id, observation=obs, output=result.output, source=source
    )
    return obs, result, detection


def test_evidence_chain_and_event_creation(session):
    from tests.factories import make_person, make_source

    source = make_source(session, provider="synthetic", tier=2)
    person = make_person(session, "Sarah Chen")

    obs, result, detection = _ingest_week2(session, source, person)

    # extraction observability
    assert result.parse_status == ParseStatus.OK
    er = session.execute(
        select(ExtractionRun).where(ExtractionRun.observation_id == obs.id)
    ).scalar_one()
    assert er.extractor_name == "rules"
    assert er.parse_status == ParseStatus.OK

    # every fact has evidence pointing at the IMMUTABLE observation (CLAUDE.md #3)
    facts = session.execute(select(Fact).where(Fact.subject_id == person.id)).scalars().all()
    assert facts
    for fact in facts:
        ev = session.execute(select(Evidence).where(Evidence.fact_id == fact.id)).scalars().all()
        assert ev, f"fact {fact.fact_type} has no evidence"
        assert all(e.observation_id == obs.id for e in ev)
        assert all(0.0 <= e.evidence_strength <= 1.0 for e in ev)

    fact_types = {f.fact_type for f in facts}
    assert FactType.EMPLOYMENT_ENDED_AT in fact_types
    assert FactType.HEADLINE_CHANGED in fact_types

    # EMPLOYMENT_ENDED is a factual event; POSSIBLE_COMPANY_FORMATION is an inference
    events = session.execute(select(Event).where(Event.person_id == person.id)).scalars().all()
    assert {e.event_type for e in events} >= {
        EventType.EMPLOYMENT_ENDED,
        EventType.HEADLINE_CHANGED,
    }
    assert all(e.event_type != EventType.POSSIBLE_COMPANY_FORMATION for e in events)

    infs = (
        session.execute(select(Inference).where(Inference.person_id == person.id)).scalars().all()
    )
    assert any(i.inference_type == EventType.POSSIBLE_COMPANY_FORMATION for i in infs)
    pcf = next(i for i in infs if i.inference_type == EventType.POSSIBLE_COMPANY_FORMATION)
    assert 0.0 < pcf.probability <= 0.85
    assert pcf.model_version == "inference_v0.1"


def test_pipeline_is_idempotent_on_reingest(session):
    from tests.factories import make_person, make_source

    source = make_source(session, provider="synthetic", tier=2)
    person = make_person(session, "Sarah Chen")

    _ingest_week2(session, source, person)
    events_after_first = session.scalar(
        select(func.count()).select_from(Event).where(Event.person_id == person.id)
    )

    # re-run persist over the SAME observation content -> no new events
    obs2, _, detection2 = _ingest_week2(session, source, person)
    events_after_second = session.scalar(
        select(func.count()).select_from(Event).where(Event.person_id == person.id)
    )
    assert events_after_second == events_after_first
    assert detection2.skipped_events >= 1


def test_unknown_fundraising_status_recorded_as_unknown(session):
    from tests.factories import make_observation, make_person, make_source

    source = make_source(session, provider="synthetic", tier=2)
    person = make_person(session, "New Person")
    obs = make_observation(
        session,
        source,
        content_type="profile_snapshot",
        subject_hint="New Person",
        raw_json={"profile": {"headline": "Engineer", "fundraising_status": None}},
        provider_record_id="snap-newp-w1",
    )
    result = run_extraction(session, RuleBasedExtractor(), obs)
    persist_extraction(
        session, person_id=person.id, observation=obs, output=result.output, source=source
    )

    fs = session.execute(
        select(Fact).where(
            Fact.subject_id == person.id, Fact.fact_type == FactType.FUNDRAISING_STATUS
        )
    ).scalar_one()
    assert is_unknown(fs.structured_value)
    assert fs.structured_value != {"value": 0}
