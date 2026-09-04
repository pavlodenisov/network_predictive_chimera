"""Every normalization function, at its boundaries (spec §20, CLAUDE.md #8)."""

from __future__ import annotations

import math

import pytest

from intelligence.features.normalization import describe, is_known_normalization, normalize


def test_binary() -> None:
    assert normalize("binary", True) == 1.0
    assert normalize("binary", 0) == 0.0
    assert normalize("binary", "") == 0.0
    assert normalize("binary", "x") == 1.0


def test_capped_count() -> None:
    assert normalize("capped_count", 0, {"max": 3}) == 0.0
    assert normalize("capped_count", 2, {"max": 3}) == pytest.approx(2 / 3)
    assert normalize("capped_count", 5, {"max": 3}) == 1.0  # capped


def test_linear_cap() -> None:
    assert normalize("linear_cap", 25, {"divisor": 50}) == 0.5
    assert normalize("linear_cap", 100, {"divisor": 50}) == 1.0
    assert normalize("linear_cap", -5, {"divisor": 50}) == 0.0


def test_min_ratio_and_invert() -> None:
    assert normalize("min_ratio", 6.4, {"target": 8}) == pytest.approx(0.8)
    assert normalize("min_ratio", 20, {"target": 8}) == 1.0
    # invert: lower is better
    assert normalize("min_ratio", 0, {"target": 6, "invert": True}) == 1.0
    assert normalize("min_ratio", 3, {"target": 6, "invert": True}) == pytest.approx(0.5)
    assert normalize("min_ratio", 9, {"target": 6, "invert": True}) == 0.0


def test_exp_decay_half_life() -> None:
    # at exactly one half-life, value halves
    v = normalize("exp_decay", 45, {"half_life_days": 45})
    assert v == pytest.approx(0.5, abs=1e-6)
    assert normalize("exp_decay", 0, {"half_life_days": 45}) == 1.0
    lam = math.log(2) / 45
    assert normalize("exp_decay", 90, {"lambda": lam}) == pytest.approx(0.25, abs=1e-6)


def test_tiered() -> None:
    tiers = {"exact": 1.0, "adjacent": 0.6, "none": 0.1}
    assert normalize("tiered", "exact", {"tiers": tiers}) == 1.0
    assert normalize("tiered", "adjacent", {"tiers": tiers}) == 0.6
    assert normalize("tiered", "missing", {"tiers": tiers}) == 0.0


def test_bucket() -> None:
    params = {"thresholds": [10, 50, 200], "values": [1.0, 0.7, 0.4, 0.1]}
    assert normalize("bucket", 5, params) == 1.0
    assert normalize("bucket", 40, params) == 0.7
    assert normalize("bucket", 150, params) == 0.4
    assert normalize("bucket", 500, params) == 0.1


def test_passthrough_unit_clips() -> None:
    assert normalize("passthrough_unit", 0.42) == 0.42
    assert normalize("passthrough_unit", 1.5) == 1.0
    assert normalize("passthrough_unit", -0.2) == 0.0


def test_unknown_normalization_raises() -> None:
    assert is_known_normalization("binary")
    assert not is_known_normalization("nope")
    with pytest.raises(KeyError):
        normalize("nope", 1)


def test_describe_shape() -> None:
    d = describe("min_ratio", {"target": 8})
    assert d["normalization"] == "min_ratio"
    assert d["cap"] == 1.0 and d["floor"] == 0.0
    assert "value / target" in d["formula"]
