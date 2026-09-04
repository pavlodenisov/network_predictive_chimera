"""Persist scoring models + score snapshots (spec §2.5, §2.8).

``ensure_scoring_model`` enforces CLAUDE.md #5: a config whose ``config_hash`` differs from
the stored row for the same ``name``+``version`` raises — a weight change requires a new
``version``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from intelligence.models import PersonFeatureSnapshot, ScoreSnapshot, ScoringModel
from intelligence.models.enums import ScoringModelStatus
from intelligence.observability import ensure_utc, now_utc
from intelligence.scoring.config import ModelConfig
from intelligence.scoring.contributions import build_delta_breakdown
from intelligence.scoring.engine import ScoreResult


class ModelHashMismatch(RuntimeError):
    pass


def ensure_scoring_model(session: Session, cfg: ModelConfig) -> ScoringModel:
    row = session.execute(
        select(ScoringModel).where(
            ScoringModel.name == cfg.name, ScoringModel.version == cfg.version
        )
    ).scalar_one_or_none()
    chash = cfg.hash()
    if row is None:
        row = ScoringModel(
            name=cfg.name,
            version=cfg.version,
            target_class=cfg.target,
            configuration=cfg.raw,
            config_hash=chash,
            status=ScoringModelStatus.ACTIVE,
            activated_at=now_utc(),
        )
        session.add(row)
        session.flush()
        return row
    if row.config_hash and row.config_hash != chash:
        raise ModelHashMismatch(
            f"{cfg.full_version} config changed (stored {row.config_hash} != {chash}). "
            "Bump the model version — silent weight changes are forbidden (CLAUDE.md #5)."
        )
    if row.status != ScoringModelStatus.ACTIVE:
        row.status = ScoringModelStatus.ACTIVE
        row.activated_at = row.activated_at or now_utc()
    session.flush()
    return row


def previous_snapshot(
    session: Session, person_id: uuid.UUID, scoring_model_id: uuid.UUID, before: datetime
) -> ScoreSnapshot | None:
    return (
        session.execute(
            select(ScoreSnapshot)
            .where(
                ScoreSnapshot.person_id == person_id,
                ScoreSnapshot.scoring_model_id == scoring_model_id,
                ScoreSnapshot.scored_at < ensure_utc(before),
            )
            .order_by(ScoreSnapshot.scored_at.desc())
        )
        .scalars()
        .first()
    )


def persist_score_snapshot(
    session: Session,
    *,
    person_id: uuid.UUID,
    model: ScoringModel,
    feature_snapshot: PersonFeatureSnapshot | None,
    result: ScoreResult,
    as_of: datetime,
    weekly_run_id: uuid.UUID | None = None,
) -> ScoreSnapshot:
    prev = previous_snapshot(session, person_id, model.id, as_of)
    delta = build_delta_breakdown(
        result.contribution_breakdown, prev.contribution_breakdown if prev else None
    )
    snap = ScoreSnapshot(
        person_id=person_id,
        scoring_model_id=model.id,
        feature_snapshot_id=feature_snapshot.id if feature_snapshot else None,
        weekly_run_id=weekly_run_id,
        scored_at=ensure_utc(as_of),
        as_of_date=as_of.date(),
        quality_score=result.quality,
        fit_score=result.fit,
        timing_score=result.timing,
        access_score=result.access,
        priority_score=result.priority,
        confidence_score=result.confidence,
        previous_score_snapshot_id=prev.id if prev else None,
        contribution_breakdown=result.contribution_breakdown,
        delta_breakdown=delta,
        action=result.action,
        reason_codes=result.reason_codes,
    )
    session.add(snap)
    session.flush()
    return snap
