"""Access model (spec §14; docs/SCORING.md §5).

BFS (<= max_hops) over ``relationship_edge`` from every ``person.is_chimera_seed`` node to
the target. Base score by the strongest path; bounded adjustments for independent paths,
staleness, and mean edge confidence. If every candidate path contains an ``UNKNOWN``-
strength edge and there is no better path, the access score is reported as ``unknown`` —
NOT 0 (spec §2.3).
"""

from __future__ import annotations

import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from intelligence.config import get_settings
from intelligence.models import Person, RelationshipEdge
from intelligence.models.enums import RelationshipStrength
from intelligence.observability import days_between, ensure_utc

_STRENGTH_RANK: dict[str, int] = {
    RelationshipStrength.UNKNOWN: 0,
    RelationshipStrength.WEAK: 1,
    RelationshipStrength.MODERATE: 2,
    RelationshipStrength.STRONG: 3,
    RelationshipStrength.DIRECT: 4,
}


@lru_cache(maxsize=8)
def _load_access_config(path_str: str) -> dict:
    return yaml.safe_load(Path(path_str).read_text())


def access_config(model: str = "access_v0.1") -> dict:
    return _load_access_config(str(get_settings().models_dir / f"{model}.yaml"))


@dataclass(slots=True)
class AccessPath:
    node_ids: list[str]
    node_names: list[str]
    strength: str
    hops: int
    edge_evidence_ids: list[str] = field(default_factory=list)
    last_verified_at: str | None = None
    mean_confidence: float | None = None


@dataclass(slots=True)
class AccessResult:
    score: float | None  # None == unknown (never silently 0)
    status: str  # known | unknown
    strongest_path: AccessPath | None
    independent_path_count: int
    base: float | None
    adjusted: float | None
    all_paths: list[AccessPath] = field(default_factory=list)

    def as_dict(self) -> dict:
        p = self.strongest_path
        return {
            "score": self.score,
            "status": self.status,
            "hops": p.hops if p else None,
            "strength": p.strength if p else None,
            "node_names": p.node_names if p else [],
            "edge_evidence_ids": p.edge_evidence_ids if p else [],
            "last_verified_at": p.last_verified_at if p else None,
            "independent_path_count": self.independent_path_count,
            "base": self.base,
            "adjusted": self.adjusted,
        }


def _adjacency(session: Session, as_of: datetime) -> dict[uuid.UUID, list[RelationshipEdge]]:
    from sqlalchemy import func

    from intelligence.features.base import POINT_IN_TIME_CUTOFF

    known_since = func.coalesce(RelationshipEdge.first_seen_at, RelationshipEdge.created_at)
    conds = [known_since <= ensure_utc(as_of)]
    cutoff = POINT_IN_TIME_CUTOFF.get()
    if cutoff is not None:
        conds.append(RelationshipEdge.created_at <= ensure_utc(cutoff))
    edges = session.execute(select(RelationshipEdge).where(*conds)).scalars()
    adj: dict[uuid.UUID, list[RelationshipEdge]] = {}
    for e in edges:
        adj.setdefault(e.source_person_id, []).append(e)
        adj.setdefault(e.target_person_id, []).append(e)
    return adj


def _seed_ids(session: Session) -> list[uuid.UUID]:
    return list(
        session.execute(select(Person.id).where(Person.is_chimera_seed.is_(True))).scalars()
    )


def _path_base(cfg: dict, hops: int, weakest_rank: int) -> float | None:
    """Base score for a path, or ``None`` when the path's weakest edge is UNKNOWN and
    there is no scoreable band (hops 1-2)."""
    table = cfg["path_base"]
    if hops == 0:
        return float(table["DIRECT"])
    strong_word = {3: "STRONG", 2: "MODERATE", 1: "WEAK"}.get(weakest_rank)
    if strong_word is None:  # rank 0 == UNKNOWN strength
        return float(table.get("HOP3_ANY", 0)) if hops >= 3 else None
    if hops == 1:
        return float(table.get(f"HOP1_{strong_word}", 0))
    if hops == 2:
        return float(table.get(f"HOP2_{strong_word}", 0))
    return float(table.get("HOP3_ANY", 0))


def compute_access(
    session: Session,
    person_id: uuid.UUID,
    as_of: datetime,
    *,
    model: str = "access_v0.1",
) -> AccessResult:
    cfg = access_config(model)
    max_hops = int(cfg.get("max_hops", 3))
    target = session.get(Person, person_id)

    if target is not None and target.is_chimera_seed:
        path = AccessPath([str(person_id)], [target.canonical_name], "DIRECT", 0)
        base = float(cfg["path_base"]["DIRECT"])
        return AccessResult(base, "known", path, 1, base, base, [path])

    seeds = set(_seed_ids(session))
    if not seeds:
        return AccessResult(0.0, "known", None, 0, 0.0, 0.0, [])
    adj = _adjacency(session, as_of)

    # BFS from every seed; collect simple paths to the target
    found: list[AccessPath] = []
    for seed in seeds:
        queue: deque[tuple[uuid.UUID, list[uuid.UUID], list[RelationshipEdge]]] = deque()
        queue.append((seed, [seed], []))
        visited_depth: dict[uuid.UUID, int] = {seed: 0}
        while queue:
            node, path_nodes, path_edges = queue.popleft()
            if len(path_nodes) - 1 > max_hops:
                continue
            if node == person_id and len(path_nodes) > 1:
                found.append(_materialize_path(session, path_nodes, path_edges, as_of))
                continue
            for edge in adj.get(node, []):
                nxt = (
                    edge.target_person_id
                    if edge.source_person_id == node
                    else edge.source_person_id
                )
                if nxt in path_nodes:
                    continue
                depth = len(path_nodes)
                if visited_depth.get(nxt, 99) < depth and nxt != person_id:
                    continue
                visited_depth[nxt] = depth
                queue.append((nxt, [*path_nodes, nxt], [*path_edges, edge]))

    if not found:
        return AccessResult(0.0, "known", None, 0, 0.0, 0.0, [])

    # score each path, pick the best
    scored: list[tuple[float | None, AccessPath]] = []
    for p in found:
        weakest = _STRENGTH_RANK.get(p.strength, 0)
        scored.append((_path_base(cfg, p.hops, weakest), p))

    concrete: list[tuple[float, AccessPath]] = [(b, p) for b, p in scored if b is not None]
    independent = len({p.node_ids[1] for _, p in scored if len(p.node_ids) > 1})

    if not concrete:
        # every path had an unknown-strength edge and none scored
        best_unknown = max(found, key=lambda p: -p.hops)
        return AccessResult(None, "unknown", best_unknown, independent, None, None, found)

    concrete.sort(key=lambda t: t[0], reverse=True)
    best_base, best_path = concrete[0]
    adjusted = _apply_adjustments(cfg, best_base, best_path, independent, as_of)
    return AccessResult(
        round(adjusted, 2),
        "known",
        best_path,
        independent,
        round(best_base, 2),
        round(adjusted, 2),
        found,
    )


def _materialize_path(
    session: Session, node_ids: list[uuid.UUID], edges: list[RelationshipEdge], as_of: datetime
) -> AccessPath:
    names = [p.canonical_name for nid in node_ids if (p := session.get(Person, nid)) is not None]
    ranks = [_STRENGTH_RANK.get(e.relationship_strength, 0) for e in edges] or [0]
    weakest_rank = min(ranks)
    strength = next(
        (k for k, v in _STRENGTH_RANK.items() if v == weakest_rank), RelationshipStrength.UNKNOWN
    )
    ev: list[str] = []
    verifieds: list[datetime] = []
    confs: list[float] = []
    for e in edges:
        ev += [str(x) for x in (e.evidence_ids or [])]
        if e.last_verified_at:
            verifieds.append(e.last_verified_at)
        if e.confidence is not None:
            confs.append(e.confidence)
    return AccessPath(
        node_ids=[str(n) for n in node_ids],
        node_names=[n for n in names if n],
        strength=str(strength),
        hops=len(node_ids) - 1,
        edge_evidence_ids=ev,
        last_verified_at=min(verifieds).isoformat() if verifieds else None,
        mean_confidence=round(sum(confs) / len(confs), 3) if confs else None,
    )


def _apply_adjustments(
    cfg: dict, base: float, path: AccessPath, independent: int, as_of: datetime
) -> float:
    adj = cfg.get("adjustments", {})
    score = base

    ip = adj.get("independent_paths", {})
    if independent > 1:
        score += min(
            float(ip.get("max_bonus", 8)),
            float(ip.get("per_extra_path", 4)) * (independent - 1),
        )

    st = adj.get("staleness", {})
    if path.last_verified_at:
        age = days_between(
            ensure_utc(datetime.fromisoformat(path.last_verified_at)), ensure_utc(as_of)
        )
        if age is not None and age > float(st.get("threshold_days", 365)):
            months_stale = (age - float(st.get("threshold_days", 365))) / 30.0
            score -= min(
                float(st.get("max_penalty", 15)),
                float(st.get("per_month_penalty", 4)) * months_stale,
            )

    cc = adj.get("confidence_clamp", {})
    if cc.get("enabled") and path.mean_confidence is not None:
        score *= max(float(cc.get("floor", 0.5)), path.mean_confidence)

    return max(0.0, min(100.0, score))
