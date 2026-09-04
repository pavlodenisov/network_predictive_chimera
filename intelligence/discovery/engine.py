"""Discovery candidate staging (spec §24).

Workflow: discover-mode observation -> entity extraction -> entity resolution ->
new/existing? -> candidate qualification -> feature calc -> ranking.

A ``DiscoveryCandidate`` never becomes a trusted entity automatically — it stays
``monitoring_status = DISCOVERED`` until an analyst promotes it.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from intelligence.discovery.rules import matches_rule
from intelligence.entity_resolution import ResolutionCandidate, resolve_person
from intelligence.entity_resolution.resolver import POSSIBLE_THRESHOLD
from intelligence.models import DiscoveryCandidate, DiscoveryRule, Person, RawObservation
from intelligence.models.enums import MonitoringStatus, ResolutionDecision
from intelligence.observability import now_utc


@dataclass(slots=True)
class DiscoveryOutcome:
    created_candidate: DiscoveryCandidate | None
    person: Person | None
    is_new_person: bool
    matched_rule: str | None
    reasons: list[str]


def _observation_text(obs: RawObservation) -> str:
    rj = obs.raw_json or {}
    return " ".join(
        str(x)
        for x in (
            obs.raw_text,
            rj.get("title"),
            rj.get("summary"),
            rj.get("body"),
            (rj.get("profile") or {}).get("headline"),
        )
        if x
    )


def process_discovery_observation(
    session: Session,
    obs: RawObservation,
    *,
    rules: list[DiscoveryRule],
    detected_event_types: set[str],
) -> DiscoveryOutcome:
    text = _observation_text(obs)
    subject = (obs.subject_hint or "").strip()

    matched: DiscoveryRule | None = None
    reasons: list[str] = []
    for rule in rules:
        if not rule.active:
            continue
        ok, why = matches_rule(rule, text=text, event_types=detected_event_types)
        if ok:
            matched, reasons = rule, why
            break
    if matched is None or not subject:
        return DiscoveryOutcome(None, None, False, None, [])

    outcome = resolve_person(
        session,
        ResolutionCandidate(name=subject),
        persist=True,
        context_observation_id=obs.id,
    )

    person: Person | None = None
    is_new = False
    if outcome.decision == ResolutionDecision.MATCH or (
        outcome.decision == ResolutionDecision.POSSIBLE_MATCH
        and outcome.score >= POSSIBLE_THRESHOLD
        and outcome.matched_person_id
    ):
        person = session.get(Person, outcome.matched_person_id)
    elif outcome.decision == ResolutionDecision.AMBIGUOUS:
        # do not attach; the ambiguous ER record is the analyst's queue
        return DiscoveryOutcome(None, None, False, matched.name, ["ambiguous_identity"])
    else:
        person = Person(
            canonical_name=subject,
            monitoring_status=MonitoringStatus.DISCOVERED,
            first_seen_at=now_utc(),
            last_observed_at=now_utc(),
        )
        session.add(person)
        session.flush()
        is_new = True

    if person is None:
        return DiscoveryOutcome(None, None, False, matched.name, ["unresolved"])

    existing = session.execute(
        select(DiscoveryCandidate).where(
            DiscoveryCandidate.discovery_rule_id == matched.id,
            DiscoveryCandidate.person_id == person.id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return DiscoveryOutcome(existing, person, is_new, matched.name, reasons)

    candidate = DiscoveryCandidate(
        discovery_rule_id=matched.id,
        person_id=person.id,
        first_discovered_at=now_utc(),
        source_id=obs.source_id,
        triggering_evidence_ids=[str(obs.id)],
        identity_confidence=round(outcome.score, 4),
        candidate_classification=matched.target_class,
    )
    session.add(candidate)
    session.flush()
    return DiscoveryOutcome(candidate, person, is_new, matched.name, reasons)


def qualify_candidates(session: Session) -> int:
    """Number of open (non-dismissed, non-promoted) discovery candidates. Feature
    calculation + ranking for a candidate reuses the founder/talent builders via the
    weekly pipeline once the person is monitored."""
    return int(
        session.scalar(
            select(func.count())
            .select_from(DiscoveryCandidate)
            .where(
                DiscoveryCandidate.dismissed.is_(False),
                DiscoveryCandidate.promoted_to_person_id.is_(None),
            )
        )
        or 0
    )
