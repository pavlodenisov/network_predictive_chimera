"""Load + validate versioned model configuration (spec §21).

Weights live ONLY in ``configs/models/*.yaml``. The loader asserts dimension weights sum
to 1.0, every feature names a known normalization, and ``missing_behavior`` is valid. A
changed config produces a changed ``config_hash`` — a mismatch without a ``version`` bump
must fail the run (CLAUDE.md #5).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from intelligence.config import get_settings
from intelligence.features.normalization import is_known_normalization

_MISSING_BEHAVIORS = {"unknown", "zero", "neutral"}
_DIMENSION_KINDS = {"weighted_features", "decay_signals", "access_model"}
_WEIGHT_TOLERANCE = 1e-6


class ModelConfigError(ValueError):
    pass


@dataclass(slots=True)
class FeatureSpec:
    name: str
    weight: float
    normalization: str
    params: dict[str, Any] = field(default_factory=dict)
    missing_behavior: str = "unknown"
    direction: str = "positive"
    source: str = ""
    rationale: str = ""


@dataclass(slots=True)
class DimensionSpec:
    name: str
    weight: float
    kind: str
    renormalize_over_present: bool = True
    features: dict[str, FeatureSpec] = field(default_factory=dict)
    signals: dict[str, dict[str, Any]] = field(default_factory=dict)
    access_model: str | None = None


@dataclass(slots=True)
class ModelConfig:
    name: str
    version: str
    target: str
    scale: float
    dimension_weights: dict[str, float]
    dimensions: dict[str, DimensionSpec]
    confidence_weights: dict[str, float]
    raw: dict[str, Any]
    source_path: str | None = None

    @property
    def full_version(self) -> str:
        return f"{self.name}_{self.version}"

    def hash(self) -> str:
        return config_hash(self.raw)


def config_hash(raw: dict[str, Any]) -> str:
    blob = json.dumps(raw, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _parse_features(block: dict[str, Any]) -> dict[str, FeatureSpec]:
    out: dict[str, FeatureSpec] = {}
    for fname, spec in (block or {}).items():
        spec = spec or {}
        norm = spec.get("normalization", "passthrough_unit")
        if not is_known_normalization(norm):
            raise ModelConfigError(f"feature {fname!r}: unknown normalization {norm!r}")
        mb = spec.get("missing_behavior", "unknown")
        if mb not in _MISSING_BEHAVIORS:
            raise ModelConfigError(f"feature {fname!r}: bad missing_behavior {mb!r}")
        out[fname] = FeatureSpec(
            name=fname,
            weight=float(spec.get("weight", 0.0)),
            normalization=norm,
            params=spec.get("params", {}) or {},
            missing_behavior=mb,
            direction=spec.get("direction", "positive"),
            source=spec.get("source", ""),
            rationale=spec.get("rationale", ""),
        )
    return out


def parse_model_config(raw: dict[str, Any], *, source_path: str | None = None) -> ModelConfig:
    for key in ("name", "version", "target", "priority", "dimensions"):
        if key not in raw:
            raise ModelConfigError(f"model config missing required key {key!r}")

    dimension_weights = {k: float(v) for k, v in raw["priority"].items()}
    total = sum(dimension_weights.values())
    if abs(total - 1.0) > _WEIGHT_TOLERANCE:
        raise ModelConfigError(
            f"dimension weights must sum to 1.0 (got {total:.6f}) in {raw['name']} {raw['version']}"
        )

    dimensions: dict[str, DimensionSpec] = {}
    for dname, dweight in dimension_weights.items():
        dblock = raw["dimensions"].get(dname)
        if dblock is None:
            raise ModelConfigError(f"priority names dimension {dname!r} with no 'dimensions' entry")
        kind = dblock.get("kind", "weighted_features")
        if kind not in _DIMENSION_KINDS:
            raise ModelConfigError(f"dimension {dname!r}: unknown kind {kind!r}")
        dimensions[dname] = DimensionSpec(
            name=dname,
            weight=dweight,
            kind=kind,
            renormalize_over_present=bool(dblock.get("renormalize_over_present", True)),
            features=_parse_features(dblock.get("features", {}))
            if kind == "weighted_features"
            else {},
            signals=dblock.get("signals", {}) if kind == "decay_signals" else {},
            access_model=dblock.get("model") if kind == "access_model" else None,
        )

    conf = (raw.get("confidence") or {}).get("weights") or {
        "reliability": 0.22,
        "independence": 0.18,
        "recency": 0.18,
        "extraction": 0.15,
        "identity": 0.12,
        "completeness": 0.15,
    }
    return ModelConfig(
        name=raw["name"],
        version=raw["version"],
        target=raw["target"],
        scale=float(raw.get("scale", 100)),
        dimension_weights=dimension_weights,
        dimensions=dimensions,
        confidence_weights={k: float(v) for k, v in conf.items()},
        raw=raw,
        source_path=source_path,
    )


def load_model_config(name: str, *, models_dir: Path | None = None) -> ModelConfig:
    models_dir = models_dir or get_settings().models_dir
    path = models_dir / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"model config not found: {path}")
    raw = yaml.safe_load(path.read_text())
    return parse_model_config(raw, source_path=str(path))


def load_all_model_configs(*, models_dir: Path | None = None) -> dict[str, ModelConfig]:
    models_dir = models_dir or get_settings().models_dir
    out: dict[str, ModelConfig] = {}
    for path in sorted(models_dir.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text())
        if raw.get("target") in {"founder", "lp", "talent", "connector"} and "priority" in raw:
            cfg = parse_model_config(raw, source_path=str(path))
            out[cfg.name] = cfg
    return out
