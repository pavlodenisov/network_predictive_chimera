"""Reversible person merges (spec §9, §31).

``merge_persons`` repoints every dependent row from ``loser`` to ``winner`` and records
exactly which rows moved in ``EntityMergeLog.merged_fields['moved']`` so ``unmerge`` can
restore the original graph. The loser row is retained (``merged_into_id`` set,
``monitoring_status = ARCHIVED``) — nothing is deleted.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from intelligence.models import (
    AnalystFeedback,
    CandidateRoleMatch,
    DiscoveryCandidate,
    Education,
    Employment,
    EntityMergeLog,
    Event,
    Fact,
    Inference,
    Person,
    PersonAlias,
    PersonClassification,
    PersonFeatureSnapshot,
    RelationshipEdge,
    ScoreSnapshot,
)
from intelligence.models.enums import (
    AliasType,
    DecisionSource,
    EntityResolutionStatus,
    MonitoringStatus,
)
from intelligence.observability import now_utc

#: (model, foreign-key attribute) pairs repointed on merge.
_PERSON_FKS: tuple[tuple[type, str], ...] = (
    (PersonAlias, "person_id"),
    (PersonClassification, "person_id"),
    (Employment, "person_id"),
    (Education, "person_id"),
    (Event, "person_id"),
    (Inference, "person_id"),
    (RelationshipEdge, "source_person_id"),
    (RelationshipEdge, "target_person_id"),
    (PersonFeatureSnapshot, "person_id"),
    (ScoreSnapshot, "person_id"),
    (DiscoveryCandidate, "person_id"),
    (DiscoveryCandidate, "promoted_to_person_id"),
    (AnalystFeedback, "person_id"),
    (CandidateRoleMatch, "person_id"),
)

_SNAPSHOT_FIELDS = (
    "canonical_name",
    "first_name",
    "last_name",
    "primary_location",
    "primary_email",
    "primary_linkedin_url",
    "current_title",
    "monitoring_status",
    "entity_resolution_status",
)


def merge_persons(
    session: Session,
    *,
    winner_id: uuid.UUID,
    loser_id: uuid.UUID,
    decision_source: DecisionSource | str = DecisionSource.ANALYST,
    reason: str | None = None,
    analyst_user_id: str | None = None,
    resolution_result_id: uuid.UUID | None = None,
) -> EntityMergeLog:
    if winner_id == loser_id:
        raise ValueError("cannot merge a person into itself")
    winner = session.get(Person, winner_id)
    loser = session.get(Person, loser_id)
    if winner is None or loser is None:
        raise ValueError("winner and loser must both exist")
    if loser.merged_into_id is not None:
        raise ValueError(f"person {loser_id} is already merged")

    moved: dict[str, list[str]] = {}
    for model, attr in _PERSON_FKS:
        col = getattr(model, attr)
        ids = [
            str(r)
            for r in session.execute(
                select(model.id).where(col == loser_id)  # type: ignore[attr-defined]
            ).scalars()
        ]
        if ids:
            session.execute(update(model).where(col == loser_id).values({attr: winner_id}))
            moved.setdefault(f"{model.__tablename__}.{attr}", []).extend(ids)  # type: ignore[attr-defined]

    # person-subject facts
    fact_ids = [
        str(r)
        for r in session.execute(
            select(Fact.id).where(Fact.subject_type == "person", Fact.subject_id == loser_id)
        ).scalars()
    ]
    if fact_ids:
        session.execute(
            update(Fact)
            .where(Fact.subject_type == "person", Fact.subject_id == loser_id)
            .values(subject_id=winner_id)
        )
        moved["fact.subject_id"] = fact_ids

    # carry the loser's name forward as an alias so future resolution still finds it
    if loser.canonical_name and loser.canonical_name != winner.canonical_name:
        session.add(
            PersonAlias(
                person_id=winner_id,
                alias_type=AliasType.NAME,
                alias_value=loser.canonical_name,
                confidence=0.9,
            )
        )
    if loser.primary_linkedin_url and not winner.primary_linkedin_url:
        winner.primary_linkedin_url = loser.primary_linkedin_url

    snapshot = {f: getattr(loser, f) for f in _SNAPSHOT_FIELDS}
    snapshot["moved"] = moved

    loser.merged_into_id = winner_id
    loser.entity_resolution_status = EntityResolutionStatus.MERGED
    loser.monitoring_status = MonitoringStatus.ARCHIVED
    winner.entity_resolution_status = EntityResolutionStatus.RESOLVED

    log = EntityMergeLog(
        winner_person_id=winner_id,
        loser_person_id=loser_id,
        decision_source=str(decision_source),
        resolution_result_id=resolution_result_id,
        merged_fields=snapshot,
        analyst_user_id=analyst_user_id,
        reason=reason,
        active=True,
    )
    session.add(log)
    session.flush()
    return log


def unmerge(session: Session, merge_log_id: uuid.UUID) -> Person:
    log = session.get(EntityMergeLog, merge_log_id)
    if log is None or not log.active:
        raise ValueError("no active merge log with that id")

    loser = session.get(Person, log.loser_person_id)
    if loser is None:
        raise ValueError("loser person row is gone")

    moved: dict[str, list[str]] = dict(log.merged_fields.get("moved", {}))
    by_model: dict[str, type] = {m.__tablename__: m for m, _ in _PERSON_FKS}  # type: ignore[attr-defined]
    by_model["fact"] = Fact
    for key, ids in moved.items():
        table, attr = key.split(".", 1)
        model = by_model[table]
        target_col = "subject_id" if table == "fact" else attr
        session.execute(
            update(model)
            .where(model.id.in_([uuid.UUID(i) for i in ids]))  # type: ignore[attr-defined]
            .values({target_col: log.loser_person_id})
        )

    for f in _SNAPSHOT_FIELDS:
        if f in log.merged_fields:
            setattr(loser, f, log.merged_fields[f])
    loser.merged_into_id = None

    log.active = False
    log.reverted_at = now_utc()
    session.flush()
    return loser
