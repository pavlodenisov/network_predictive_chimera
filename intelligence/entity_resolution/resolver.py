"""Blocking + scorecard resolver.

Decision bands:
  score >= AUTO_MERGE_THRESHOLD and margin over runner-up >= AUTO_MERGE_MARGIN -> MATCH (auto)
  score >= POSSIBLE_THRESHOLD                                                  -> POSSIBLE_MATCH
  >=2 candidates tied near the top, none decisive                              -> AMBIGUOUS
  otherwise                                                                    -> NO_MATCH

A name-only hit maxes out at ``W_NAME_EXACT`` (0.20) — far below POSSIBLE_THRESHOLD — so a
name match alone can never trigger a merge or even a "possible" attach (spec §9).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from intelligence.models import (
    Education,
    Employment,
    EntityResolutionResult,
    Organization,
    Person,
    PersonAlias,
)
from intelligence.models.enums import AliasType, EntityResolutionStatus, ResolutionDecision

AUTO_MERGE_THRESHOLD = 0.90
AUTO_MERGE_MARGIN = 0.25
POSSIBLE_THRESHOLD = 0.60
AMBIGUOUS_FLOOR = 0.15

W_LINKEDIN_EXACT = 0.55
W_PROVIDER_ID_EXACT = 0.50
W_EMAIL_EXACT = 0.42
W_GITHUB_EXACT = 0.35
W_NAME_EXACT = 0.20
W_NAME_SUBSET = 0.08
W_EMPLOYER_EACH = 0.18
W_EMPLOYER_CAP = 0.32
W_EDUCATION = 0.12
W_GEOGRAPHY = 0.06
PENALTY_DIFF_CURRENT_EMPLOYER = -0.15

_NAME_CLEAN = re.compile(r"[^a-z0-9 ]+")
_WS = re.compile(r"\s+")


def normalize_name(name: str | None) -> str:
    if not name:
        return ""
    return _WS.sub(" ", _NAME_CLEAN.sub(" ", name.lower())).strip()


def normalize_linkedin(url: str | None) -> str | None:
    if not url:
        return None
    u = url.strip().lower().split("?")[0].rstrip("/")
    u = u.replace("https://", "").replace("http://", "").replace("www.", "")
    return u or None


@dataclass(slots=True)
class ResolutionCandidate:
    name: str
    linkedin_url: str | None = None
    provider_ids: dict[str, str] = field(default_factory=dict)
    github_username: str | None = None
    email: str | None = None
    current_employer: str | None = None
    prior_employers: list[str] = field(default_factory=list)
    geography: str | None = None
    education: list[str] = field(default_factory=list)

    @property
    def all_employers(self) -> set[str]:
        out = {e.strip().lower() for e in self.prior_employers if e and e.strip()}
        if self.current_employer:
            out.add(self.current_employer.strip().lower())
        return out


@dataclass(slots=True)
class PersonScore:
    person_id: uuid.UUID
    score: float
    reasons: dict[str, float]


@dataclass(slots=True)
class ResolutionOutcome:
    decision: ResolutionDecision
    matched_person_id: uuid.UUID | None
    score: float
    scorecard: dict
    competing_person_ids: list[uuid.UUID]
    ranked: list[PersonScore]
    auto_applied: bool = False


# --------------------------------------------------------------------------- blocking
def _block(session: Session, cand: ResolutionCandidate) -> dict[uuid.UUID, Person]:
    found: dict[uuid.UUID, Person] = {}

    def add(rows) -> None:
        for p in rows:
            if p is not None and p.merged_into_id is None:
                found[p.id] = p

    norm_url = normalize_linkedin(cand.linkedin_url)
    if norm_url:
        add(
            session.execute(
                select(Person).where(func.lower(Person.primary_linkedin_url).like(f"%{norm_url}%"))
            ).scalars()
        )

    alias_values = [v for v in [norm_url, cand.github_username, cand.email] if v]
    alias_values += list(cand.provider_ids.values())
    if alias_values:
        lowered = [str(v).lower() for v in alias_values]
        aliases = session.execute(
            select(PersonAlias).where(func.lower(PersonAlias.alias_value).in_(lowered))
        ).scalars()
        add(session.get(Person, a.person_id) for a in aliases)

    norm = normalize_name(cand.name)
    if norm:
        add(
            session.execute(
                select(Person).where(func.lower(Person.canonical_name) == cand.name.strip().lower())
            ).scalars()
        )
        # normalized-name match (handles punctuation / spacing)
        for p in session.execute(select(Person)).scalars():
            if normalize_name(p.canonical_name) == norm:
                found.setdefault(p.id, p)

    return found


def _employers_for(session: Session, person_id: uuid.UUID) -> set[str]:
    rows = session.execute(
        select(Organization.canonical_name)
        .join(Employment, Employment.organization_id == Organization.id)
        .where(Employment.person_id == person_id)
    ).scalars()
    return {r.strip().lower() for r in rows if r}


def _education_for(session: Session, person_id: uuid.UUID) -> set[str]:
    rows = session.execute(
        select(Education.institution_name_raw).where(Education.person_id == person_id)
    ).scalars()
    return {r.strip().lower() for r in rows if r}


def _alias_index(session: Session, person_id: uuid.UUID) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for a in session.execute(
        select(PersonAlias).where(PersonAlias.person_id == person_id)
    ).scalars():
        out.setdefault(a.alias_type, set()).add(a.alias_value.lower())
    return out


# --------------------------------------------------------------------------- scoring
def _score_person(session: Session, cand: ResolutionCandidate, person: Person) -> PersonScore:
    reasons: dict[str, float] = {}
    aliases = _alias_index(session, person.id)

    norm_url = normalize_linkedin(cand.linkedin_url)
    if norm_url and (
        normalize_linkedin(person.primary_linkedin_url) == norm_url
        or norm_url in aliases.get(AliasType.LINKEDIN_URL, set())
    ):
        reasons["linkedin_url_exact"] = W_LINKEDIN_EXACT

    for pid in cand.provider_ids.values():
        if str(pid).lower() in aliases.get(AliasType.PROVIDER_ID, set()):
            reasons["provider_id_exact"] = W_PROVIDER_ID_EXACT
            break

    if cand.github_username and cand.github_username.lower() in aliases.get(
        AliasType.GITHUB_USERNAME, set()
    ):
        reasons["github_exact"] = W_GITHUB_EXACT

    if cand.email and (
        (person.primary_email or "").lower() == cand.email.lower()
        or cand.email.lower() in aliases.get(AliasType.EMAIL, set())
    ):
        reasons["email_exact"] = W_EMAIL_EXACT

    cand_norm, person_norm = normalize_name(cand.name), normalize_name(person.canonical_name)
    if cand_norm and cand_norm == person_norm:
        reasons["name_exact"] = W_NAME_EXACT
    elif cand_norm and person_norm and _name_subset(cand_norm, person_norm):
        reasons["name_subset"] = W_NAME_SUBSET

    person_employers = _employers_for(session, person.id)
    overlap = cand.all_employers & person_employers
    if overlap:
        reasons["employer_overlap"] = min(W_EMPLOYER_CAP, W_EMPLOYER_EACH * len(overlap))
    elif (
        cand.current_employer
        and person_employers
        and (cand.current_employer.strip().lower() not in person_employers)
        and not any(k for k in reasons if k.endswith("_exact"))
    ):
        reasons["different_current_employer"] = PENALTY_DIFF_CURRENT_EMPLOYER

    if cand.education and (
        _education_for(session, person.id) & {e.lower() for e in cand.education}
    ):
        reasons["education_overlap"] = W_EDUCATION

    if (
        cand.geography
        and person.primary_location
        and (cand.geography.split(",")[0].strip().lower() in person.primary_location.lower())
    ):
        reasons["geography_match"] = W_GEOGRAPHY

    score = max(0.0, min(1.0, sum(reasons.values())))
    return PersonScore(person_id=person.id, score=round(score, 4), reasons=reasons)


def _name_subset(a: str, b: str) -> bool:
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return False
    return ta <= tb or tb <= ta


# --------------------------------------------------------------------------- resolve
def resolve_person(
    session: Session,
    cand: ResolutionCandidate,
    *,
    persist: bool = True,
    context_observation_id: uuid.UUID | None = None,
) -> ResolutionOutcome:
    blocked = _block(session, cand)
    ranked = sorted(
        (_score_person(session, cand, p) for p in blocked.values()),
        key=lambda s: s.score,
        reverse=True,
    )
    scorecard = {str(s.person_id): s.reasons for s in ranked}

    if not ranked:
        outcome = ResolutionOutcome(ResolutionDecision.NO_MATCH, None, 0.0, scorecard, [], ranked)
        return _maybe_persist(session, cand, outcome, persist, context_observation_id)

    best = ranked[0]
    runner_up = ranked[1].score if len(ranked) > 1 else 0.0
    margin = best.score - runner_up
    tied = [s for s in ranked if abs(s.score - best.score) < 1e-6]

    if best.score >= AUTO_MERGE_THRESHOLD and margin >= AUTO_MERGE_MARGIN and len(tied) == 1:
        decision = ResolutionDecision.MATCH
        matched: uuid.UUID | None = best.person_id
        auto = True
    elif (
        len(tied) >= 2
        and best.score >= AMBIGUOUS_FLOOR
        or best.score >= POSSIBLE_THRESHOLD
        and margin < AUTO_MERGE_MARGIN
        and runner_up >= POSSIBLE_THRESHOLD
    ):
        decision = ResolutionDecision.AMBIGUOUS
        matched = None
        auto = False
    elif best.score >= POSSIBLE_THRESHOLD or best.score >= AMBIGUOUS_FLOOR:
        decision = ResolutionDecision.POSSIBLE_MATCH
        matched = best.person_id
        auto = False
    else:
        decision = ResolutionDecision.NO_MATCH
        matched = None
        auto = False

    competing = [
        s.person_id for s in ranked if s.score >= AMBIGUOUS_FLOOR and s.person_id != matched
    ]
    outcome = ResolutionOutcome(
        decision=decision,
        matched_person_id=matched,
        score=best.score,
        scorecard=scorecard,
        competing_person_ids=competing,
        ranked=ranked,
        auto_applied=auto,
    )
    return _maybe_persist(session, cand, outcome, persist, context_observation_id)


def _maybe_persist(
    session: Session,
    cand: ResolutionCandidate,
    outcome: ResolutionOutcome,
    persist: bool,
    context_observation_id: uuid.UUID | None,
) -> ResolutionOutcome:
    if not persist or outcome.decision == ResolutionDecision.NO_MATCH:
        return outcome
    session.add(
        EntityResolutionResult(
            candidate_observation_id=context_observation_id,
            candidate_person_id=None,
            matched_person_id=outcome.matched_person_id,
            decision=outcome.decision,
            score=outcome.score,
            scorecard={"candidate_name": cand.name, "signals": outcome.scorecard},
            competing_person_ids=[str(c) for c in outcome.competing_person_ids],
            auto_applied=outcome.auto_applied,
        )
    )
    session.flush()
    return outcome


def resolve_subject(
    session: Session,
    *,
    subject_hint: str | None,
    linkedin_url: str | None = None,
    provider_ids: dict[str, str] | None = None,
    current_employer: str | None = None,
    context_observation_id: uuid.UUID | None = None,
) -> ResolutionOutcome:
    """Convenience wrapper used by the ingestion pipeline for observation subjects."""
    cand = ResolutionCandidate(
        name=subject_hint or "",
        linkedin_url=linkedin_url,
        provider_ids=provider_ids or {},
        current_employer=current_employer,
    )
    return resolve_person(session, cand, context_observation_id=context_observation_id)


def mark_resolved(session: Session, person: Person, confidence: float) -> None:
    person.entity_resolution_status = EntityResolutionStatus.RESOLVED
    person.entity_resolution_confidence = round(confidence, 4)
    session.flush()
