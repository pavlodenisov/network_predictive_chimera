"""Model YAML configs load, validate, and hash deterministically (spec §21)."""

from __future__ import annotations

import pytest

from intelligence.scoring.config import (
    ModelConfigError,
    load_all_model_configs,
    load_model_config,
    parse_model_config,
)


def test_all_shipped_model_configs_load() -> None:
    configs = load_all_model_configs()
    assert set(configs) == {"founder", "lp", "talent", "connector"}
    for cfg in configs.values():
        assert abs(sum(cfg.dimension_weights.values()) - 1.0) < 1e-6
        assert cfg.scale == 100
        assert cfg.hash() == cfg.hash()  # deterministic


def test_founder_config_structure() -> None:
    cfg = load_model_config("founder_v0.1")
    assert cfg.full_version == "founder_v0.1"
    assert set(cfg.dimensions) == {"quality", "fit", "timing", "access"}
    assert cfg.dimensions["quality"].kind == "weighted_features"
    assert cfg.dimensions["timing"].kind == "decay_signals"
    assert cfg.dimensions["access"].kind == "access_model"
    # prestige is capped as a weak signal
    assert cfg.dimensions["quality"].features["prestige_weak_signal"].weight <= 0.04


def test_bad_dimension_weights_rejected() -> None:
    raw = {
        "name": "x",
        "version": "v0",
        "target": "founder",
        "priority": {"quality": 0.5, "fit": 0.4},  # sums to 0.9
        "dimensions": {"quality": {"features": {}}, "fit": {"features": {}}},
    }
    with pytest.raises(ModelConfigError):
        parse_model_config(raw)


def test_unknown_normalization_rejected() -> None:
    raw = {
        "name": "x",
        "version": "v0",
        "target": "founder",
        "priority": {"quality": 1.0},
        "dimensions": {"quality": {"features": {"f": {"weight": 1.0, "normalization": "bogus"}}}},
    }
    with pytest.raises(ModelConfigError):
        parse_model_config(raw)
