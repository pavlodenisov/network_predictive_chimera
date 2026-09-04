"""The weekly intelligence cycle — 14 ordered, logged, idempotent stages (spec §6).

``run_weekly`` is the single entrypoint used by both ``python -m intelligence.jobs.weekly``
and the scheduled workflow. Re-running with the same inputs/``as_of`` creates no duplicate
observations, facts, or events.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from intelligence.config import get_settings
from intelligence.digest import build_weekly_digest, render_digest_text
from intelligence.discovery.engine import process_discovery_observation
from intelligence.discovery.rules import sync_discovery_rules
from intelligence.entity_resolution import ResolutionCandidate, resolve_person
from intelligence.entity_resolution.resolver import POSSIBLE_THRESHOLD, mark_resolved
from intelligence.events.detector import DetectionResult, persist_extraction
from intelligence.extraction import get_extractor
from intelligence.extraction.runner import run_extraction
from intelligence.features import build_feature_bundle, persist_feature_snapshot
from intelligence.ingestion.adapters import get_enabled_adapters
from intelligence.ingestion.adapters.base import PersonRef
from intelligence.ingestion.normalize import persist_drafts
from intelligence.models import (
    CandidateRoleMatch,
    DiscoveryRule,
    Employment,
    Event,
    Person,
    PersonClassification,
    PortfolioRoleNeed,
    RawObservation,
    ScoreSnapshot,
    Source,
    WeeklyRun,
)
from intelligence.models.enums import (
    EntityResolutionStatus,
    EventStatus,
    ModelTarget,
    MonitoringStatus,
    ResolutionDecision,
    RoleNeedStatus,
    Severity,
    WeeklyRunStatus,
)
from intelligence.observability import ensure_utc, get_logger, now_utc, stage_logger
from intelligence.ranking.deltas import rank_delta_summary
from intelligence.ranking.ranker import rank_snapshots
from intelligence.ranking.universe import UniverseSpec, ensure_universe
from intelligence.scoring.actions import decide_action, load_action_rules
from intelligence.scoring.config import load_all_model_configs
from intelligence.scoring.engine import score_person
from intelligence.scoring.persist import ensure_scoring_model, persist_score_snapshot

log = get_logger("chimera.weekly")

_MONITORED = (MonitoringStatus.ACTIVE_MONITORING, MonitoringStatus.PASSIVE_MONITORING)


@dataclass(slots=True)
class WeeklyResult:
    run_id: uuid.UUID
    status: str
    digest_text: str


def _as_of_dt(as_of: date) -> datetime:
    return datetime(as_of.year, as_of.month, as_of.day, 23, 59, 59, tzinfo=UTC)


def _subject_identifiers(obs: RawObservation) -> dict:
    rj = obs.raw_json or {}
    profile = rj.get("profile", rj) if isinstance(rj, dict) else {}
    return {
        "linkedin_url": profile.get("linkedin_url") or rj.get("linkedin_url"),
        "provider_ids": rj.get("provider_ids", {}) or profile.get("provider_ids", {}),
        "current_employer": profile.get("current_company"),
    }


def _previous_snapshot(session: Session, obs: RawObservation, person_id: uuid.UUID) -> dict | None:
    meta = obs.obs_metadata or {}
    if meta.get("previous_snapshot"):
        return meta["previous_snapshot"]
    prior = (
        session.execute(
            select(RawObservation)
            .where(
                RawObservation.subject_hint == obs.subject_hint,
                RawObservation.content_type == "profile_snapshot",
                RawObservation.id != obs.id,
                RawObservation.observed_at < obs.observed_at,
            )
            .order_by(RawObservation.observed_at.desc())
        )
        .scalars()
        .first()
    )
    if prior and prior.raw_json:
        return prior.raw_json.get("profile", prior.raw_json)
    return None


def run_weekly(
    session: Session,
    *,
    as_of: date | None = None,
    code_version: str | None = None,
    config_version: str = "v0.1",
    dry_run: bool = False,
) -> WeeklyResult:
    settings = get_settings()
    as_of = as_of or now_utc().date()
    as_of_dt = _as_of_dt(as_of)
    run = WeeklyRun(
        started_at=now_utc(),
        as_of_date=as_of,
        status=WeeklyRunStatus.RUNNING,
        code_version=code_version or settings.code_version,
        config_version=config_version,
    )
    session.add(run)
    session.flush()
    stats: list[dict] = []
    warnings: list[str] = []
    partial = False

    # ---- Stage 1: source health -----------------------------------------
    adapters = get_enabled_adapters(session)
    coverage: list[dict] = []
    with stage_logger(str(run.id), "source_health") as st:
        for src, adapter in adapters:
            health = adapter.health_check()
            coverage.append(
                {
                    "source": src.name,
                    "provider": src.provider,
                    "status": str(health.status),
                    "records": health.records,
                    "latency_ms": health.latency_ms,
                    "errors": health.errors,
                }
            )
            if str(health.status) == "successful":
                src.last_successful_run = now_utc()
            elif str(health.status) == "failed":
                partial = True
                warnings.append(f"source {src.name} health=failed: {'; '.join(health.errors)}")
        st["count"] = len(coverage)
    run.source_coverage = coverage
    stats.append(_stat(st, "source_health"))

    sync_discovery_rules(session)
    rules = list(
        session.execute(select(DiscoveryRule).where(DiscoveryRule.active.is_(True))).scalars()
    )

    # ---- Stage 2 + 3: gather drafts (update known + discover) --------------
    people_refs = [
        PersonRef(
            person_id=p.id, canonical_name=p.canonical_name, linkedin_url=p.primary_linkedin_url
        )
        for p in session.execute(
            select(Person).where(Person.monitoring_status.in_(_MONITORED))
        ).scalars()
    ]
    update_batches: list[tuple[Source, list]] = []
    discover_batches: list[tuple[Source, list]] = []
    with stage_logger(str(run.id), "update_known_people") as st:
        for src, adapter in adapters:
            drafts = adapter.update_known_entities(people=people_refs, as_of=as_of)
            if drafts:
                update_batches.append((src, drafts))
        st["count"] = sum(len(d) for _, d in update_batches)
    stats.append(_stat(st, "update_known_people"))

    with stage_logger(str(run.id), "discover_new_people") as st:
        for src, adapter in adapters:
            drafts = adapter.discover(rules=rules, as_of=as_of)
            if drafts:
                discover_batches.append((src, drafts))
        st["count"] = sum(len(d) for _, d in discover_batches)
    stats.append(_stat(st, "discover_new_people"))

    # ---- Stage 4 + 5: normalize + dedupe -------------------------------
    new_update_obs: list[RawObservation] = []
    new_discover_obs: list[RawObservation] = []
    ingested = 0
    with stage_logger(str(run.id), "normalize_and_dedupe") as st:
        for src, drafts in update_batches:
            res = persist_drafts(session, src, drafts)
            new_update_obs.extend(res.persisted)
            ingested += len(res.persisted)
        for src, drafts in discover_batches:
            res = persist_drafts(session, src, drafts)
            new_discover_obs.extend(res.persisted)
            ingested += len(res.persisted)
        st["count"] = ingested
    stats.append(_stat(st, "normalize_and_dedupe"))
    run.observations_ingested = ingested

    extractor = get_extractor()
    facts_created = events_created = inferences_created = people_updated = 0
    people_discovered = 0

    # ---- Stage 6 + 7 + 8: resolve, extract, detect (update stream) --------
    resolved_in_run: dict[str, Person] = {}
    seen_people: set[uuid.UUID] = set()
    with stage_logger(str(run.id), "resolve_extract_detect") as st:
        for obs in new_update_obs:
            hint = (obs.subject_hint or "").strip().lower()
            person = resolved_in_run.get(hint) if hint else None
            if person is None:
                person = _resolve_update_subject(session, obs, warnings)
                if person is not None and hint:
                    resolved_in_run[hint] = person
            if person is None:
                continue
            if person.id not in seen_people:
                seen_people.add(person.id)
                people_updated += 1
            person.last_observed_at = ensure_utc(obs.observed_at)
            prev = _previous_snapshot(session, obs, person.id)
            result = run_extraction(session, extractor, obs, previous_snapshot=prev)
            detection = persist_extraction(
                session,
                person_id=person.id,
                observation=obs,
                output=result.output,
                source=session.get(Source, obs.source_id),
                weekly_run_id=run.id,
                extractor_version=extractor.model_version,
            )
            facts_created += len(detection.facts)
            events_created += len(detection.events)
            inferences_created += len(detection.inferences)
            _reconcile_employment(session, person, detection, obs, as_of_dt)
            _maybe_classify(session, person, detection)
            obs.processed_at = now_utc()
        st["count"] = people_updated
    stats.append(_stat(st, "resolve_extract_detect"))

    # ---- Stage 3 (cont.): discovery candidates -----------------------------
    with stage_logger(str(run.id), "discovery_candidates") as st:
        for obs in new_discover_obs:
            disc_prev = (obs.obs_metadata or {}).get("previous_snapshot")
            result = run_extraction(session, extractor, obs, previous_snapshot=disc_prev)
            # resolve first so a discovered person that already exists is reused
            temp_person = _resolve_discover_subject(session, obs)
            disc_detection: DetectionResult | None = None
            if temp_person is not None:
                disc_detection = persist_extraction(
                    session,
                    person_id=temp_person.id,
                    observation=obs,
                    output=result.output,
                    source=session.get(Source, obs.source_id),
                    weekly_run_id=run.id,
                    extractor_version=extractor.model_version,
                )
                facts_created += len(disc_detection.facts)
                events_created += len(disc_detection.events)
                inferences_created += len(disc_detection.inferences)
            detected_types = {
                str(e.event_type) for e in (disc_detection.events if disc_detection else [])
            }
            detected_types |= {str(e.event_type) for e in result.output.events}
            outcome = process_discovery_observation(
                session, obs, rules=rules, detected_event_types=detected_types
            )
            if outcome.created_candidate is not None and outcome.is_new_person:
                people_discovered += 1
            obs.processed_at = now_utc()
        st["count"] = people_discovered
    stats.append(_stat(st, "discovery_candidates"))

    run.facts_created = facts_created
    run.events_created = events_created
    run.inferences_created = inferences_created
    run.people_updated = people_updated
    run.people_discovered = people_discovered

    # ---- Stage 9 + 10: features + scoring -------------------------------
    model_configs = load_all_model_configs()
    action_rules = load_action_rules()
    models = {name: ensure_scoring_model(session, cfg) for name, cfg in model_configs.items()}
    monitored = list(
        session.execute(
            select(Person).where(
                Person.monitoring_status.in_(
                    (*_MONITORED, MonitoringStatus.DISCOVERED, MonitoringStatus.REVIEW)
                ),
                Person.merged_into_id.is_(None),
            )
        ).scalars()
    )
    open_roles = list(
        session.execute(
            select(PortfolioRoleNeed).where(PortfolioRoleNeed.status == RoleNeedStatus.OPEN)
        ).scalars()
    )

    run_snapshots: dict[str, list[ScoreSnapshot]] = {t: [] for t in ModelTarget}
    with stage_logger(str(run.id), "features_and_scoring") as st:
        for person in monitored:
            for target in ("founder", "lp", "connector"):
                cfg = model_configs.get(_cfg_name(target))
                if cfg is None:
                    continue
                bundle = build_feature_bundle(session, person.id, target, as_of_dt)
                fs = persist_feature_snapshot(session, person.id, bundle, as_of_date=as_of)
                score_result = score_person(session, person, cfg, bundle, as_of_dt)
                _apply_action(score_result, action_rules, person, target, has_role_match=False)
                snap = persist_score_snapshot(
                    session,
                    person_id=person.id,
                    model=models[cfg.name],
                    feature_snapshot=fs,
                    result=score_result,
                    as_of=as_of_dt,
                    weekly_run_id=run.id,
                )
                run_snapshots[target].append(snap)

            # talent: one score per open role; the person's snapshot uses their best role
            tcfg = model_configs.get("talent")
            if tcfg and open_roles:
                best_result = None
                best_bundle = None
                for role in open_roles:
                    tbundle = build_feature_bundle(
                        session, person.id, "talent", as_of_dt, role_need=role
                    )
                    tresult = score_person(session, person, tcfg, tbundle, as_of_dt)
                    _upsert_role_match(session, person.id, role.id, tresult)
                    if best_result is None or tresult.priority > best_result.priority:
                        best_result, best_bundle = tresult, tbundle
                if best_result is not None and best_bundle is not None:
                    tfs = persist_feature_snapshot(
                        session, person.id, best_bundle, as_of_date=as_of
                    )
                    _apply_action(
                        best_result,
                        action_rules,
                        person,
                        "talent",
                        has_role_match=best_result.priority >= 55,
                    )
                    tsnap = persist_score_snapshot(
                        session,
                        person_id=person.id,
                        model=models[tcfg.name],
                        feature_snapshot=tfs,
                        result=best_result,
                        as_of=as_of_dt,
                        weekly_run_id=run.id,
                    )
                    run_snapshots["talent"].append(tsnap)
        st["count"] = sum(len(v) for v in run_snapshots.values())
    stats.append(_stat(st, "features_and_scoring"))
    run.scoring_models_run = [m.name for m in models.values()]

    # ---- Stage 11: rank deltas -----------------------------------------
    with stage_logger(str(run.id), "rank_deltas") as st:
        for target, snaps in run_snapshots.items():
            if not snaps:
                continue
            uni = ensure_universe(
                session,
                UniverseSpec(
                    label=f"{target} candidates — active monitoring",
                    model_target=target,
                    scoring_model_id=snaps[0].scoring_model_id,
                    as_of_date=as_of,
                    filter={"monitoring": "active+passive+discovered"},
                ),
                member_count=len(snaps),
            )
            rank_snapshots(session, snaps, universe_id=uni.id)
            for s in snaps:
                rank_delta_summary(session, s)
        st["count"] = sum(len(v) for v in run_snapshots.values())
    stats.append(_stat(st, "rank_deltas"))

    # ---- Stage 12 + 13 + 14: feed, store, digest -----------------------
    run.warnings = list(warnings)
    run.finished_at = now_utc()
    run.status = WeeklyRunStatus.PARTIAL if partial else WeeklyRunStatus.SUCCESS
    session.flush()

    with stage_logger(str(run.id), "digest") as st:
        digest = build_weekly_digest(session, run, as_of)
        run.digest = digest
        st["count"] = len(digest.get("sections", {}))
    stats.append(_stat(st, "digest"))
    run.stage_stats = list(stats)  # fresh list so the JSON column registers the change
    session.flush()

    if dry_run:
        session.rollback()

    return WeeklyResult(
        run_id=run.id, status=run.status, digest_text=render_digest_text(run.digest)
    )


# --------------------------------------------------------------------------- helpers
def _stat(st: dict, name: str) -> dict:
    return {
        "stage": name,
        "count": st.get("count", 0),
        "duration_ms": st.get("duration_ms"),
        "warnings": st.get("warnings", []),
        "errors": st.get("errors", []),
    }


def _cfg_name(target: str) -> str:
    return {"founder": "founder", "lp": "lp", "connector": "connector", "talent": "talent"}[target]


def _resolve_update_subject(
    session: Session, obs: RawObservation, warnings: list[str]
) -> Person | None:
    ident = _subject_identifiers(obs)
    outcome = resolve_person(
        session,
        ResolutionCandidate(
            name=obs.subject_hint or "",
            linkedin_url=ident["linkedin_url"],
            provider_ids=ident["provider_ids"] or {},
            current_employer=ident["current_employer"],
        ),
        context_observation_id=obs.id,
    )
    if outcome.decision == ResolutionDecision.AMBIGUOUS:
        warnings.append(f"ambiguous identity for '{obs.subject_hint}' — routed to analyst review")
        return None
    # The update stream only carries subjects an adapter selected from the monitored set, so
    # a single non-ambiguous candidate is attached (even a name-only hit). It is NOT a merge
    # of two Person rows — that still requires the high threshold (spec §9).
    single_candidate = not outcome.competing_person_ids
    if outcome.matched_person_id and (
        outcome.decision == ResolutionDecision.MATCH
        or (
            outcome.decision == ResolutionDecision.POSSIBLE_MATCH
            and (outcome.score >= 0.5 or single_candidate)
        )
    ):
        person = session.get(Person, outcome.matched_person_id)
        if person and person.entity_resolution_status == EntityResolutionStatus.UNRESOLVED:
            mark_resolved(session, person, max(outcome.score, 0.6))
        return person
    # genuinely new monitored person
    person = Person(
        canonical_name=obs.subject_hint or "unknown",
        primary_linkedin_url=ident["linkedin_url"],
        monitoring_status=MonitoringStatus.ACTIVE_MONITORING,
        entity_resolution_status=EntityResolutionStatus.RESOLVED,
        entity_resolution_confidence=0.7,
        first_seen_at=now_utc(),
        last_observed_at=ensure_utc(obs.observed_at),
    )
    session.add(person)
    session.flush()
    return person


def _resolve_discover_subject(session: Session, obs: RawObservation) -> Person | None:
    if not obs.subject_hint:
        return None
    outcome = resolve_person(
        session, ResolutionCandidate(name=obs.subject_hint), context_observation_id=obs.id
    )
    if outcome.decision == ResolutionDecision.AMBIGUOUS:
        return None
    if outcome.matched_person_id and outcome.score >= POSSIBLE_THRESHOLD:
        return session.get(Person, outcome.matched_person_id)
    return None


def _reconcile_employment(
    session: Session, person: Person, detection, obs: RawObservation, as_of_dt: datetime
) -> None:
    for ev in detection.events:
        if ev.event_type == "EMPLOYMENT_ENDED" and ev.organization_id:
            for emp in session.execute(
                select(Employment).where(
                    Employment.person_id == person.id,
                    Employment.organization_id == ev.organization_id,
                    Employment.current.is_(True),
                )
            ).scalars():
                emp.current = False
                emp.ended_at = (ev.occurred_at or as_of_dt).date()
            if person.current_organization_id == ev.organization_id:
                person.current_organization_id = None
                person.current_title = None
            # talent lens
            _ensure_event(
                session,
                person,
                "PROFESSIONAL_DEPARTURE",
                ev.occurred_at,
                ev.confidence,
                obs,
                run_id=ev.weekly_run_id,
            )
        elif ev.event_type == "EMPLOYMENT_STARTED" and ev.organization_id:
            exists = session.execute(
                select(Employment).where(
                    Employment.person_id == person.id,
                    Employment.organization_id == ev.organization_id,
                    Employment.current.is_(True),
                )
            ).scalar_one_or_none()
            if exists is None:
                title = (ev.structured_payload or {}).get("organization_name") or "unknown"
                session.add(
                    Employment(
                        person_id=person.id,
                        organization_id=ev.organization_id,
                        title=title,
                        current=True,
                        started_at=(ev.occurred_at or as_of_dt).date(),
                        evidence_ids=[str(x) for x in ev.evidence_ids],
                    )
                )
                person.current_organization_id = ev.organization_id
    session.flush()


def _ensure_event(
    session: Session,
    person: Person,
    event_type: str,
    occurred_at,
    confidence: float,
    obs: RawObservation,
    run_id=None,
) -> None:
    key = f"{person.id}:{event_type}:{(occurred_at or now_utc()).date()}"
    exists = session.execute(
        select(Event).where(Event.dedupe_key == key, Event.status == EventStatus.ACTIVE)
    ).scalar_one_or_none()
    if exists is not None:
        return
    session.add(
        Event(
            person_id=person.id,
            event_type=event_type,
            occurred_at=occurred_at,
            detected_at=now_utc(),
            confidence=confidence,
            severity=Severity.MEDIUM,
            evidence_ids=[str(obs.id)],
            structured_payload={"derived_from": "EMPLOYMENT_ENDED"},
            dedupe_key=key,
            status=EventStatus.ACTIVE,
            weekly_run_id=run_id,
        )
    )
    session.flush()


def _maybe_classify(session: Session, person: Person, detection) -> None:
    add: set[str] = set()
    for ev in detection.events:
        if ev.event_type in {"FOUNDER_TITLE_ADDED", "COMPANY_FORMATION_CONFIRMED"}:
            add.add("POTENTIAL_FOUNDER")
        if ev.event_type in {"PROFESSIONAL_DEPARTURE", "OPEN_TO_WORK_SIGNAL"}:
            add.add("TALENT")
        if ev.event_type in {
            "CIO_ROLE_STARTED",
            "PARTNER_ROLE_STARTED",
            "INVESTMENT_MANDATE_CHANGED",
        }:
            add.add("POTENTIAL_LP")
    for inf in detection.inferences:
        if inf.inference_type == "POSSIBLE_COMPANY_FORMATION":
            add.add("POTENTIAL_FOUNDER")
    for cls in add:
        exists = session.execute(
            select(PersonClassification).where(
                PersonClassification.person_id == person.id,
                PersonClassification.person_class == cls,
            )
        ).scalar_one_or_none()
        if exists is None:
            session.add(
                PersonClassification(
                    person_id=person.id, person_class=cls, source="pipeline", confidence=0.7
                )
            )
    session.flush()


def _apply_action(
    result, action_rules, person: Person, target: str, *, has_role_match: bool
) -> None:
    stale = any(
        f.get("stale")
        for dim in result.contribution_breakdown.get("dimensions", {}).values()
        for f in dim.get("features", {}).values()
        if isinstance(f, dict) and isinstance(f.get("freshness"), dict)
    )
    access_dim = result.contribution_breakdown.get("dimensions", {}).get("access", {})
    has_warm_path = bool((access_dim.get("access") or {}).get("score"))
    ctx = {
        "priority": result.priority,
        "confidence": result.confidence,
        "access": result.access,
        "quality": result.quality,
        "fit": result.fit,
        "timing": result.timing,
        "model_target": target,
        "has_role_match": has_role_match,
        "has_warm_path": has_warm_path,
        "is_newly_discovered": person.monitoring_status == MonitoringStatus.DISCOVERED,
        "data_stale": stale,
    }
    action, codes = decide_action(action_rules, ctx)
    result.action = action
    result.reason_codes = codes


def _upsert_role_match(session: Session, person_id: uuid.UUID, role_id: uuid.UUID, result) -> None:
    existing = session.execute(
        select(CandidateRoleMatch).where(
            CandidateRoleMatch.person_id == person_id,
            CandidateRoleMatch.portfolio_role_need_id == role_id,
            CandidateRoleMatch.model_version == "talent_v0.1",
        )
    ).scalar_one_or_none()
    breakdown = {
        "priority": result.priority,
        "dimensions": {
            k: v.get("score")
            for k, v in result.contribution_breakdown.get("dimensions", {}).items()
        },
    }
    if existing is None:
        session.add(
            CandidateRoleMatch(
                person_id=person_id,
                portfolio_role_need_id=role_id,
                model_version="talent_v0.1",
                calculated_at=now_utc(),
                score=result.priority,
                score_breakdown=breakdown,
            )
        )
    else:
        existing.score = result.priority
        existing.score_breakdown = breakdown
        existing.calculated_at = now_utc()
    session.flush()
