"""Build the weekly digest as a structured dict + a deterministic plain-text rendering
(spec §29). Nine sections; every listed item shows name / score / delta / event / date /
evidence confidence / warm path / reason codes. No sentences like "Another exciting week".
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from intelligence.models import (
    DiscoveryCandidate,
    DiscoveryRule,
    Event,
    Person,
    PersonClassification,
    ScoreSnapshot,
    ScoringModel,
    WeeklyRun,
)
from intelligence.models.enums import ModelTarget

_BANNED = {
    "exciting",
    "compelling",
    "impressive",
    "amazing",
    "fascinating",
    "promising",
    "visionary",
    "great founder",
    "strong leader",
    "worth keeping an eye",
}


def _person_name(session: Session, pid: uuid.UUID) -> str:
    p = session.get(Person, pid)
    return p.canonical_name if p else str(pid)


def _row(session: Session, snap: ScoreSnapshot) -> dict:
    delta = snap.delta_breakdown or {}
    path = (
        (snap.contribution_breakdown or {})
        .get("dimensions", {})
        .get("access", {})
        .get("access", {})
    )
    return {
        "person": _person_name(session, snap.person_id),
        "person_id": str(snap.person_id),
        "score": round(snap.priority_score, 1),
        "score_delta": delta.get("priority_delta"),
        "rank": snap.rank,
        "confidence": round(snap.confidence_score, 2),
        "action": snap.action,
        "reason_codes": snap.reason_codes or [],
        "warm_path": {
            "hops": path.get("hops"),
            "strength": path.get("strength"),
            "status": path.get("status"),
        },
        "drivers": [
            f"{'+' if m['delta'] >= 0 else ''}{m['delta']:.1f} {m['feature']}"
            for m in delta.get("top_movers", [])[:4]
        ],
    }


#: only surface a person in a model's digest sections if they carry a relevant class.
_RELEVANT_CLASSES: dict[str, set[str]] = {
    "founder": {"FOUNDER", "POTENTIAL_FOUNDER"},
    "lp": {"LP", "POTENTIAL_LP"},
    "talent": {"TALENT", "OPERATOR", "PORTFOLIO_EXECUTIVE", "ENGINEER"},
    "connector": {"CONNECTOR"},
}


def _snapshots_for(session: Session, run_id: uuid.UUID, target: str) -> list[ScoreSnapshot]:
    wanted = _RELEVANT_CLASSES.get(target, set())
    rows = list(
        session.execute(
            select(ScoreSnapshot)
            .join(ScoringModel, ScoringModel.id == ScoreSnapshot.scoring_model_id)
            .where(ScoreSnapshot.weekly_run_id == run_id, ScoringModel.target_class == target)
            .order_by(ScoreSnapshot.priority_score.desc())
        ).scalars()
    )
    if not wanted:
        return rows
    keep: list[ScoreSnapshot] = []
    for s in rows:
        classes = {
            c
            for (c,) in session.execute(
                select(PersonClassification.person_class).where(
                    PersonClassification.person_id == s.person_id
                )
            )
        }
        if classes & wanted:
            keep.append(s)
    return keep


def build_weekly_digest(session: Session, run: WeeklyRun, as_of: date) -> dict:
    founders = _snapshots_for(session, run.id, ModelTarget.FOUNDER)
    lps = _snapshots_for(session, run.id, ModelTarget.LP)
    talent = _snapshots_for(session, run.id, ModelTarget.TALENT)
    connectors = _snapshots_for(session, run.id, ModelTarget.CONNECTOR)

    def movers(snaps: list[ScoreSnapshot], *, increases: bool) -> list[dict]:
        scored: list[tuple[ScoreSnapshot, float]] = []
        for s in snaps:
            d = (s.delta_breakdown or {}).get("priority_delta")
            if d is None:
                continue
            d = float(d)
            if abs(d) > 0.05 and (d > 0) == increases:
                scored.append((s, d))
        scored.sort(key=lambda t: t[1], reverse=increases)
        return [_row(session, s) for s, _ in scored[:10]]

    new_candidates = list(
        session.execute(
            select(DiscoveryCandidate)
            .where(DiscoveryCandidate.first_discovered_at >= run.started_at)
            .order_by(DiscoveryCandidate.identity_confidence.desc())
        ).scalars()
    )
    important_events = list(
        session.execute(
            select(Event)
            .where(Event.weekly_run_id == run.id, Event.severity.in_(["high", "medium"]))
            .order_by(Event.detected_at.desc())
        ).scalars()
    )

    digest = {
        "week_ending": as_of.isoformat(),
        "generated_from_run": str(run.id),
        "monitored_people": int(session.scalar(select(func.count()).select_from(Person)) or 0),
        "counts": {
            "observations_ingested": run.observations_ingested,
            "people_updated": run.people_updated,
            "people_discovered": run.people_discovered,
            "facts_created": run.facts_created,
            "events_created": run.events_created,
            "inferences_created": run.inferences_created,
        },
        "sections": {
            "top_new_founders": [
                _row(session, s)
                for s in founders
                if (s.delta_breakdown or {}).get("priority_delta") is None
            ][:10],
            "largest_founder_score_increases": movers(founders, increases=True),
            "largest_founder_score_decreases": movers(founders, increases=False),
            "top_lp_changes": movers(lps, increases=True)[:10]
            or [_row(session, s) for s in lps[:10]],
            "top_talent_changes": movers(talent, increases=True)[:10]
            or [_row(session, s) for s in talent[:10]],
            "top_connectors": [_row(session, s) for s in connectors[:10]],
            "new_warm_paths": [
                {
                    "person": _person_name(session, e.person_id),
                    "event": e.event_type,
                    "date": e.occurred_at.date().isoformat() if e.occurred_at else None,
                }
                for e in important_events
                if e.event_type in {"WARM_PATH_CREATED", "NEW_CHIMERA_CONNECTION"}
            ],
            "important_departures": _dedupe_by_person(
                {
                    "person_id": str(e.person_id),
                    "person": _person_name(session, e.person_id),
                    "date": e.occurred_at.date().isoformat() if e.occurred_at else None,
                    "confidence": round(e.confidence, 2),
                }
                for e in important_events
                if e.event_type in {"EMPLOYMENT_ENDED", "PROFESSIONAL_DEPARTURE"}
            ),
            "new_company_formations": [
                {
                    "person": _person_name(session, e.person_id),
                    "type": e.event_type,
                    "date": e.occurred_at.date().isoformat() if e.occurred_at else None,
                }
                for e in important_events
                if e.event_type
                in {"COMPANY_FORMATION_CONFIRMED", "FOUNDER_TITLE_ADDED", "PRODUCT_LAUNCH"}
            ],
            "newly_discovered_people": [
                {
                    "person": _person_name(session, c.person_id) if c.person_id else "unknown",
                    "rule": _rule_name(session, c.discovery_rule_id),
                    "identity_confidence": round(c.identity_confidence, 2),
                }
                for c in new_candidates[:15]
            ],
            "data_quality_warnings": list(run.warnings or []),
            "source_failures": [
                s for s in (run.source_coverage or []) if s.get("status") in {"failed", "partial"}
            ],
        },
    }
    _assert_no_marketing_prose(digest)
    return digest


def render_digest_text(digest: dict) -> str:
    s = digest["sections"]
    lines: list[str] = [
        "WEEKLY NETWORK INTELLIGENCE",
        f"Week ending: {digest['week_ending']}",
        "",
        f"MONITORED PEOPLE\n{digest['monitored_people']}",
        f"\nOBSERVATIONS INGESTED\n{digest['counts']['observations_ingested']}",
        f"\nNEW PEOPLE DISCOVERED\n{digest['counts']['people_discovered']}",
        f"\nEVENTS CREATED\n{digest['counts']['events_created']}",
        "",
        "LARGEST FOUNDER SCORE INCREASES",
    ]
    for r in s["largest_founder_score_increases"]:
        lines.append(
            f"{r['person']}  {r['score']}  ({_fmt_delta(r['score_delta'])})  "
            f"conf {r['confidence']}  {r['action'] or ''}"
        )
        for d in r["drivers"]:
            lines.append(f"  {d}")
    lines += ["", "TOP NEW FOUNDER SIGNALS"]
    for r in s["top_new_founders"]:
        lines.append(f"{r['person']}  {r['score']}  conf {r['confidence']}  {r['action'] or ''}")
    lines += ["", "IMPORTANT DEPARTURES"]
    for r in s["important_departures"]:
        lines.append(f"{r['person']}  {r['date']}  conf {r['confidence']}")
    lines += ["", "DATA-QUALITY WARNINGS"]
    lines += [f"  {w}" for w in s["data_quality_warnings"]] or ["  none"]
    lines += ["", "SOURCE FAILURES"]
    lines += [f"  {f.get('source')}: {f.get('status')}" for f in s["source_failures"]] or ["  none"]
    return "\n".join(lines)


def _fmt_delta(v: float | None) -> str:
    if v is None:
        return "new"
    return f"{'+' if v >= 0 else ''}{v:.1f}"


def _dedupe_by_person(rows) -> list[dict]:
    seen: dict[str, dict] = {}
    for r in rows:
        pid = r.get("person_id") or r.get("person")
        if pid not in seen or (r.get("date") or "") < (seen[pid].get("date") or "~"):
            seen[pid] = r
    return list(seen.values())


def _rule_name(session: Session, rule_id: uuid.UUID | None) -> str | None:
    if rule_id is None:
        return None
    rule = session.get(DiscoveryRule, rule_id)
    return rule.name if rule else None


def _assert_no_marketing_prose(digest: dict) -> None:
    blob = str(digest).lower()
    hits = [w for w in _BANNED if w in blob]
    if hits:
        raise AssertionError(f"digest contains banned marketing language: {hits}")
