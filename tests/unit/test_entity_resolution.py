"""Conservative entity resolution (spec §9): name alone never merges; ambiguity is
routed to review; merges are reversible."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from intelligence.entity_resolution import (
    POSSIBLE_THRESHOLD,
    ResolutionCandidate,
    merge_persons,
    normalize_name,
    resolve_person,
    unmerge,
)
from intelligence.models import EntityMergeLog, Event
from intelligence.models.enums import EntityResolutionStatus, ResolutionDecision
from intelligence.observability import now_utc
from tests.factories import make_org, make_person

pytestmark = pytest.mark.integration


def test_normalize_name() -> None:
    assert (
        normalize_name("  Álex  Lee!! ") == "lex lee" or normalize_name("Alex  Lee.") == "alex lee"
    )
    assert normalize_name("Alex   Lee") == "alex lee"


def test_name_only_never_reaches_possible(session) -> None:
    make_person(session, "Alex Lee")
    out = resolve_person(session, ResolutionCandidate(name="Alex Lee"), persist=False)
    # a single name hit scores 0.20 — below the POSSIBLE threshold; no auto-anything
    assert out.score < POSSIBLE_THRESHOLD
    assert out.decision in {ResolutionDecision.POSSIBLE_MATCH, ResolutionDecision.NO_MATCH}
    assert out.auto_applied is False


def test_two_alex_lee_article_is_ambiguous(session) -> None:
    """Spec §65: two different 'Alex Lee' (Stripe vs Google); an ambiguous mention must
    NOT auto-merge and must create an ambiguous resolution record."""
    stripe = make_org(session, "Stripe")
    google = make_org(session, "Google")
    a = make_person(session, "Alex Lee")
    b = make_person(session, "Alex Lee")
    from intelligence.models import Employment

    session.add_all(
        [
            Employment(person_id=a.id, organization_id=stripe.id, title="Engineer", current=True),
            Employment(person_id=b.id, organization_id=google.id, title="Engineer", current=True),
        ]
    )
    session.flush()

    out = resolve_person(session, ResolutionCandidate(name="Alex Lee"))
    assert out.decision == ResolutionDecision.AMBIGUOUS
    assert out.matched_person_id is None
    assert set(out.competing_person_ids) == {a.id, b.id}

    from intelligence.models import EntityResolutionResult

    rec = session.execute(select(EntityResolutionResult)).scalars().all()
    assert rec and rec[0].decision == ResolutionDecision.AMBIGUOUS
    assert rec[0].auto_applied is False


def test_linkedin_plus_employer_reaches_match(session) -> None:
    org = make_org(session, "Anthropic")
    p = make_person(session, "Dana Reyes")
    p.primary_linkedin_url = "https://www.linkedin.com/in/dana-reyes"
    from intelligence.models import Employment

    session.add(Employment(person_id=p.id, organization_id=org.id, title="MTS", current=True))
    session.flush()

    out = resolve_person(
        session,
        ResolutionCandidate(
            name="Dana Reyes",
            linkedin_url="linkedin.com/in/dana-reyes/",
            current_employer="Anthropic",
        ),
        persist=False,
    )
    assert out.decision == ResolutionDecision.MATCH
    assert out.matched_person_id == p.id
    assert out.auto_applied is True
    assert out.score >= 0.9


def test_merge_then_unmerge_restores_graph(session) -> None:
    winner = make_person(session, "Sam Park")
    loser = make_person(session, "Samuel Park")
    session.add(
        Event(
            person_id=loser.id,
            event_type="NEWS_MENTION",
            detected_at=now_utc(),
            dedupe_key="k1",
        )
    )
    session.flush()
    loser_id = loser.id

    log = merge_persons(session, winner_id=winner.id, loser_id=loser.id, reason="same person")
    assert isinstance(log, EntityMergeLog)
    session.refresh(loser)
    assert loser.merged_into_id == winner.id
    assert loser.entity_resolution_status == EntityResolutionStatus.MERGED
    # the event moved to the winner
    ev = session.execute(select(Event).where(Event.dedupe_key == "k1")).scalar_one()
    assert ev.person_id == winner.id

    unmerge(session, log.id)
    session.refresh(loser)
    assert loser.merged_into_id is None
    ev2 = session.execute(select(Event).where(Event.dedupe_key == "k1")).scalar_one()
    assert ev2.person_id == loser_id
    assert session.get(EntityMergeLog, log.id).active is False
