"""Normalization function registry (spec §20).

Every numeric feature declares raw_unit, normalization, params, cap, floor,
missing_behavior, direction. These functions map a raw value to [0, 1]. They are pure and
individually unit-tested (CLAUDE.md #8). ``missing`` handling is the caller's job — a
normalization function never sees a missing value.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

NormFn = Callable[[float, dict[str, Any]], float]


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def norm_binary(raw: float, params: dict[str, Any]) -> float:
    return 1.0 if raw else 0.0


def norm_capped_count(raw: float, params: dict[str, Any]) -> float:
    m = float(params.get("max", 1) or 1)
    return _clip(float(raw) / m)


def norm_linear_cap(raw: float, params: dict[str, Any]) -> float:
    d = float(params.get("divisor", 1) or 1)
    return _clip(float(raw) / d)


def norm_min_ratio(raw: float, params: dict[str, Any]) -> float:
    target = float(params.get("target", 1) or 1)
    v = float(raw)
    if params.get("invert"):
        # lower is better: full credit at 0, zero at >= target
        return _clip(1.0 - v / target)
    return _clip(v / target)


def norm_exp_decay(raw: float, params: dict[str, Any]) -> float:
    """``raw`` is days since the event."""
    hl = params.get("half_life_days")
    lam = params.get("lambda")
    if hl:
        lam = math.log(2) / float(hl)
    if lam is None:
        raise ValueError("exp_decay needs 'half_life_days' or 'lambda'")
    return _clip(math.exp(-float(lam) * max(0.0, float(raw))))


def norm_tiered(raw: float, params: dict[str, Any]) -> float:
    tiers: dict[str, float] = params.get("tiers", {})
    key = str(raw)
    if key in tiers:
        return _clip(float(tiers[key]))
    return _clip(float(tiers.get("_default", 0.0)))


def norm_passthrough_unit(raw: float, params: dict[str, Any]) -> float:
    return _clip(float(raw))


def norm_bucket(raw: float, params: dict[str, Any]) -> float:
    thresholds = params.get("thresholds", [])
    values = params.get("values", [])
    if len(values) != len(thresholds) + 1:
        raise ValueError("bucket needs len(values) == len(thresholds) + 1")
    v = float(raw)
    for i, t in enumerate(thresholds):
        if v <= float(t):
            return _clip(float(values[i]))
    return _clip(float(values[-1]))


NORMALIZERS: dict[str, NormFn] = {
    "binary": norm_binary,
    "capped_count": norm_capped_count,
    "linear_cap": norm_linear_cap,
    "min_ratio": norm_min_ratio,
    "exp_decay": norm_exp_decay,
    "tiered": norm_tiered,
    "passthrough_unit": norm_passthrough_unit,
    "bucket": norm_bucket,
}

_FORMULA_TEXT: dict[str, str] = {
    "binary": "1 if value else 0",
    "capped_count": "min(value, max) / max",
    "linear_cap": "clip(value / divisor, 0, 1)",
    "min_ratio": "clip(value / target, 0, 1)   [invert: 1 - value/target]",
    "exp_decay": "exp(-ln(2)/half_life_days * days_since_event)",
    "tiered": "lookup(value) in tiers",
    "passthrough_unit": "clip(value, 0, 1)",
    "bucket": "step function over thresholds -> values",
}


def normalize(name: str, raw: Any, params: dict[str, Any] | None = None) -> float:
    """``raw`` is usually a float; ``binary`` accepts any truthy value and ``tiered``
    accepts a label string."""
    fn = NORMALIZERS.get(name)
    if fn is None:
        raise KeyError(f"unknown normalization: {name!r}")
    return _clip(fn(raw, params or {}))


def is_known_normalization(name: str) -> bool:
    return name in NORMALIZERS


def describe(name: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """UI/audit description of a normalization (spec §20, §70)."""
    return {
        "normalization": name,
        "formula": _FORMULA_TEXT.get(name, "n/a"),
        "params": params or {},
        "cap": 1.0,
        "floor": 0.0,
    }
