"""Deterministic, config-driven scoring engine (spec §2.4, §19-21; docs/SCORING.md §8).

For each dimension:
  weighted_features -> 100 · Σ(norm_i·w_i) / Σ(w_i over present features)
  decay_signals     -> 100 · clip(Σ initial·exp(-ln2/half_life·days_since), 0, 1)
  access_model      -> intelligence.scoring.access.compute_access  (may be `unknown`)

priority = Σ dimension_score · dimension_weight, with dimension weights renormalized over
the dimensions that produced a score (an `unknown` access dimension drops out rather than
scoring 0 — spec §2.3). No LLM produces any number here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from intelligence.features.base import FeatureBundle
from intelligence.features.normalization import describe, normalize
from intelligence.models import Person
from intelligence.scoring.access import compute_access
from intelligence.scoring.confidence import compute_confidence
from intelligence.scoring.config import DimensionSpec, ModelConfig


@dataclass(slots=True)
class DimensionScore:
    name: str
    kind: str
    score: float | None  # None == unknown
    weight: float
    features: dict[str, dict] = field(default_factory=dict)
    extra: dict = field(default_factory=dict)


@dataclass(slots=True)
class ScoreResult:
    model_name: str
    model_version: str
    config_hash: str
    priority: float
    confidence: float
    confidence_components: dict[str, float]
    quality: float | None
    fit: float | None
    timing: float | None
    access: float | None
    dimensions: dict[str, DimensionScore]
    contribution_breakdown: dict
    missing_features: list[str]
    action: str | None = None
    reason_codes: list[str] = field(default_factory=list)


def _score_weighted_features(
    dim: DimensionSpec, bundle: FeatureBundle
) -> tuple[float, dict[str, dict], float, float]:
    metas: dict[str, dict] = {}
    total_weight = sum(fs.weight for fs in dim.features.values()) or 0.0

    for fname, fs in dim.features.items():
        fv = bundle.features.get(fname)
        status = fv.status if fv else "unknown"
        raw = fv.value if fv else None

        if status == "known":
            norm = normalize(fs.normalization, raw, fs.params)
            include = True
        elif fs.missing_behavior == "zero":
            norm, include = 0.0, True
        elif fs.missing_behavior == "neutral":
            norm, include = 0.5, True
        else:  # "unknown" -> excluded from the denominator (never silently 0)
            norm, include = 0.0, False

        metas[fname] = {
            "raw": raw,
            "status": status,
            "normalized": round(norm, 4),
            "weight": round(fs.weight, 4),
            "normalization": fs.normalization,
            "normalization_detail": describe(fs.normalization, fs.params),
            "missing_behavior": fs.missing_behavior,
            "source_fact_ids": fv.source_fact_ids if fv else [],
            "included": include,
            "freshness": bundle.freshness.get(fname),
            "fit_evidence": bundle.fit_evidence.get(fname),
        }

    denom = (
        sum(m["weight"] for m in metas.values() if m["included"])
        if dim.renormalize_over_present
        else (total_weight or 1.0)
    ) or 1.0

    dim_score = 0.0
    for m in metas.values():
        if m["included"]:
            eff = m["weight"] / denom
            contrib = m["normalized"] * eff
            m["effective_weight"] = round(eff, 4)
            m["contribution"] = round(contrib, 4)
            dim_score += contrib
        else:
            m["effective_weight"] = 0.0
            m["contribution"] = 0.0

    return round(100.0 * dim_score, 4), metas, denom, total_weight or 1.0


def _score_decay_signals(
    dim: DimensionSpec, bundle: FeatureBundle
) -> tuple[float, dict[str, dict]]:
    total = 0.0
    features_out: dict[str, dict] = {}
    for sig_type, cfg in dim.signals.items():
        matches = [s for s in bundle.timing_signals if s.event_type == sig_type]
        if not matches:
            continue
        half_life = float(cfg.get("half_life_days", 60))
        lam = math.log(2) / half_life
        contrib = 0.0
        detail: list[dict] = []
        for s in matches:
            days = s.days_since if s.days_since is not None else 0.0
            if cfg.get("initial_from") == "probability":
                initial = float(cfg.get("factor", 1.0)) * (s.probability or 0.0)
            else:
                initial = float(cfg.get("initial", 0.0))
            decay = math.exp(-lam * max(0.0, days))
            value = initial * decay
            contrib += value
            detail.append(
                {
                    "occurred_at": s.occurred_at.isoformat() if s.occurred_at else None,
                    "days_since": round(days, 1),
                    "half_life_days": half_life,
                    "initial": round(initial, 4),
                    "decay_factor": round(decay, 4),
                    "value": round(value, 4),
                    "probability": s.probability,
                    "evidence_ids": s.evidence_ids,
                }
            )
        total += contrib
        features_out[sig_type] = {
            "status": "known",
            "raw": detail[0]["days_since"] if detail else None,
            "normalized": round(detail[0]["decay_factor"], 4) if detail else 0.0,
            "weight": round(sum(d["initial"] for d in detail), 4),
            "contribution": round(contrib, 4),
            "included": True,
            "signals": detail,
        }
    return round(100.0 * max(0.0, min(1.0, total)), 4), features_out


def score_person(
    session: Session,
    person: Person,
    model_config: ModelConfig,
    bundle: FeatureBundle,
    as_of: datetime,
) -> ScoreResult:
    dims: dict[str, DimensionScore] = {}
    conf_present_weight = 0.0
    conf_total_weight = 0.0

    for dname, dspec in model_config.dimensions.items():
        if dspec.kind == "weighted_features":
            score, feats, denom, total = _score_weighted_features(dspec, bundle)
            dims[dname] = DimensionScore(dname, dspec.kind, score, dspec.weight, feats)
            conf_present_weight += denom
            conf_total_weight += total
        elif dspec.kind == "decay_signals":
            score, feats = _score_decay_signals(dspec, bundle)
            dims[dname] = DimensionScore(dname, dspec.kind, score, dspec.weight, feats)
        elif dspec.kind == "access_model":
            acc = compute_access(
                session, person.id, as_of, model=dspec.access_model or "access_v0.1"
            )
            dims[dname] = DimensionScore(
                dname, dspec.kind, acc.score, dspec.weight, {}, {"access": acc.as_dict()}
            )
        else:  # pragma: no cover - guarded by the config loader
            raise ValueError(f"unknown dimension kind {dspec.kind!r}")

    scored = {n: d for n, d in dims.items() if d.score is not None}
    weight_sum = sum(model_config.dimension_weights[n] for n in scored) or 1.0

    priority = 0.0
    dim_breakdown: dict[str, dict] = {}
    for n, d in dims.items():
        w = model_config.dimension_weights[n]
        eff_w = (w / weight_sum) if d.score is not None else 0.0
        weighted = (d.score or 0.0) * eff_w
        priority += weighted
        dim_breakdown[n] = {
            "score": d.score,
            "status": "known" if d.score is not None else "unknown",
            "weight": round(w, 4),
            "effective_weight": round(eff_w, 4),
            "weighted": round(weighted, 4),
            "kind": d.kind,
            "features": d.features,
            **d.extra,
        }
    priority = round(priority, 4)

    conf = compute_confidence(
        session,
        person=person,
        features_json=bundle.features_json(),
        missing_features=bundle.missing,
        dimension_present_weight=conf_present_weight or 1.0,
        dimension_total_weight=conf_total_weight or 1.0,
        weights=model_config.confidence_weights,
        as_of=as_of,
    )

    timing_dim = dims.get("timing") or dims.get("availability_timing")
    breakdown = {
        "model": model_config.full_version,
        "config_hash": model_config.hash(),
        "scale": model_config.scale,
        "priority": priority,
        "dimensions": dim_breakdown,
        "missing_features": sorted(set(bundle.missing)),
        "as_of": as_of.date().isoformat(),
        "confidence": conf.as_dict(),
    }

    return ScoreResult(
        model_name=model_config.name,
        model_version=model_config.version,
        config_hash=model_config.hash(),
        priority=priority,
        confidence=round(conf.score, 4),
        confidence_components=conf.components,
        quality=dims["quality"].score if "quality" in dims else None,
        fit=dims["fit"].score if "fit" in dims else None,
        timing=timing_dim.score if timing_dim else None,
        access=dims["access"].score if "access" in dims else None,
        dimensions=dims,
        contribution_breakdown=breakdown,
        missing_features=sorted(set(bundle.missing)),
    )
